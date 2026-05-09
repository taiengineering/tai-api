"""TAI 법령엔진 v3.0 — 검증 hook 모듈 (validator).

각 Stage 완료 시 자동 실행되는 검증 + 사용자 직접 검증 결과 기록.
verification_log 테이블에 PASS / FAIL / WARNING / INFO 로그.

설계 원칙 (MASTER_HANDOFF §3.4):
  - 단계별 검증 기준:
    Stage 1: 카운트 매핑 100%, 누락 0, 중복 0, sample 정확도 ≥ 95%
    Stage 2: 카운트 매핑 100%, 누락 0, 중복 0, sample 정확도 ≥ 90%
    Stage 3: 카운트 매핑 100%, 누락 0, 중복 0, sample 정확도 ≥ 90%
  - 통과 기준 미달 = 데이터셋 truncate + 룰 수정 + 재실행 (마스터 §9.2)
  - Sample 검증 단위 = 조문 (의미절 X)

본 모듈은 이러한 검증 결과의 "평가 + 기록" 인터페이스. 실제 검증 SQL/로직은
각 stage 모듈 또는 별도 검증 스크립트에서 호출.

계층: Service (FastAPI import 금지).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient

logger = logging.getLogger(__name__)


# ----- 통과 기준 (마스터 §3.4) -----
SAMPLE_ACCURACY_THRESHOLDS: dict[int, float] = {
    1: 0.95,
    2: 0.90,
    3: 0.90,
}

VALID_RESULT_STATUS: frozenset[str] = frozenset({"PASS", "FAIL", "WARNING", "INFO"})
VALID_CHECK_TYPE: frozenset[str] = frozenset({"AUTO_HOOK", "MANUAL_USER"})
VALID_STAGES: frozenset[int] = frozenset({1, 2, 3})


@dataclass
class CheckResult:
    """단일 검증 결과. verification_log INSERT에 그대로 사용."""
    stage: int
    check_name: str
    check_type: str  # AUTO_HOOK | MANUAL_USER
    result_status: str  # PASS | FAIL | WARNING | INFO
    expected_value: str | None = None
    actual_value: str | None = None
    threshold: str | None = None
    sample_size: int | None = None
    error_count: int = 0
    error_examples: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int | None = None
    verified_by: str | None = None
    notes: str | None = None


class Validator:
    """검증 hook + 결과 로깅.

    Usage:
        v = Validator(supabase=sb)
        # 카운트 매핑 검증
        result = Validator.evaluate_count_mapping(expected=100, actual=100, stage=1)
        v.log(result)
        # Sample 정확도 검증
        result = Validator.evaluate_sample_accuracy(stage=1, accuracy=0.96, sample_size=100)
        v.log(result)
    """

    def __init__(self, supabase: SupabaseClient | None = None) -> None:
        self.supabase = supabase

    # ----- 평가 (순수 함수, DB 의존 X) -----

    @staticmethod
    def evaluate_count_mapping(
        expected: int,
        actual: int,
        stage: int,
        check_name: str = "count_mapping_loss",
    ) -> CheckResult:
        """N → N+1 카운트 매핑 검증. 100% 일치하면 PASS."""
        loss = expected - actual
        status = "PASS" if loss == 0 else "FAIL"
        return CheckResult(
            stage=stage,
            check_name=check_name,
            check_type="AUTO_HOOK",
            result_status=status,
            expected_value=str(expected),
            actual_value=str(actual),
            threshold="0",
            error_count=max(loss, 0),
        )

    @staticmethod
    def evaluate_sample_accuracy(
        stage: int,
        accuracy: float,
        sample_size: int,
        check_name: str = "sample_accuracy",
    ) -> CheckResult:
        """Sample 정확도 vs 마스터 §3.4 임계값. PASS / WARNING (5%p 이내) / FAIL 3단계."""
        threshold = SAMPLE_ACCURACY_THRESHOLDS.get(stage, 0.90)
        if accuracy >= threshold:
            status = "PASS"
        elif accuracy >= threshold - 0.05:
            status = "WARNING"
        else:
            status = "FAIL"
        return CheckResult(
            stage=stage,
            check_name=check_name,
            check_type="AUTO_HOOK",
            result_status=status,
            expected_value=f"≥ {threshold:.2f}",
            actual_value=f"{accuracy:.4f}",
            threshold=str(threshold),
            sample_size=sample_size,
            error_count=int(round((1 - accuracy) * sample_size)),
        )

    @staticmethod
    def evaluate_duplicates(
        duplicate_count: int,
        stage: int,
        check_name: str = "duplicate_count",
    ) -> CheckResult:
        """중복 row 검증. 0건이면 PASS."""
        status = "PASS" if duplicate_count == 0 else "FAIL"
        return CheckResult(
            stage=stage,
            check_name=check_name,
            check_type="AUTO_HOOK",
            result_status=status,
            expected_value="0",
            actual_value=str(duplicate_count),
            threshold="0",
            error_count=duplicate_count,
        )

    # ----- 입력 검증 (순수 함수) -----

    @staticmethod
    def _validate_input(result: CheckResult) -> None:
        """verification_log INSERT 전 입력 검증. 잘못된 데이터 차단."""
        if result.result_status not in VALID_RESULT_STATUS:
            raise ValueError(
                f"Invalid result_status: {result.result_status!r}. "
                f"Valid: {sorted(VALID_RESULT_STATUS)}"
            )
        if result.check_type not in VALID_CHECK_TYPE:
            raise ValueError(
                f"Invalid check_type: {result.check_type!r}. "
                f"Valid: {sorted(VALID_CHECK_TYPE)}"
            )
        if result.stage not in VALID_STAGES:
            raise ValueError(
                f"Invalid stage: {result.stage}. Valid: {sorted(VALID_STAGES)}"
            )

    # ----- DB 쓰기 -----

    def log(self, result: CheckResult) -> bool:
        """verification_log에 검증 결과 INSERT.

        Returns:
            True 성공, False 또는 도달 안 됨 (supabase 미설정 등).
        Raises:
            ValueError: 입력 검증 실패.
        """
        self._validate_input(result)

        if self.supabase is None:
            logger.warning(
                "Supabase 미설정 — log 스킵: stage=%d check=%s status=%s",
                result.stage, result.check_name, result.result_status,
            )
            return False

        row = self._result_to_row(result)
        try:
            self.supabase.table("verification_log").insert(row).execute()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("verification_log INSERT 실패: %s", e)
            return False

    def log_batch(self, results: list[CheckResult]) -> int:
        """일괄 검증 결과 INSERT. 입력 검증 실패 row는 skip."""
        if self.supabase is None:
            logger.warning("Supabase 미설정 — log_batch 스킵 (%d건)", len(results))
            return 0
        if not results:
            return 0
        rows: list[dict[str, Any]] = []
        for r in results:
            try:
                self._validate_input(r)
                rows.append(self._result_to_row(r))
            except ValueError as e:
                logger.warning("검증 입력 실패 skip: %s", e)
        if not rows:
            return 0
        try:
            res = self.supabase.table("verification_log").insert(rows).execute()
            return len(res.data or [])
        except Exception as e:  # noqa: BLE001
            logger.error("verification_log batch INSERT 실패: %s", e)
            return 0

    # ----- 행 직렬화 -----

    @staticmethod
    def _result_to_row(r: CheckResult) -> dict[str, Any]:
        return {
            "stage": r.stage,
            "check_name": r.check_name,
            "check_type": r.check_type,
            "result_status": r.result_status,
            "expected_value": r.expected_value,
            "actual_value": r.actual_value,
            "threshold": r.threshold,
            "sample_size": r.sample_size,
            "error_count": r.error_count,
            "error_examples": r.error_examples,
            "duration_ms": r.duration_ms,
            "verified_by": r.verified_by,
            "notes": r.notes,
        }
