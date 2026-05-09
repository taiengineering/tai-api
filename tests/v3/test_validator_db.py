"""tests/v3/test_validator_db.py — Validator DB 의존 케이스 (mock supabase).

기존 test_validator.py는 순수 함수 단위 테스트.
본 파일은 mock supabase로 log() / log_batch()의 happy path + error path 검증.
"""

from __future__ import annotations

import pytest  # noqa: F401

from engine.validator import CheckResult, Validator

from tests.v3.conftest import MockSupabase  # noqa: F401


# ----- log() happy path -----

class TestLogSuccess:
    def test_log_inserts_to_verification_log(self, mock_sb_with_data: MockSupabase):
        """정상 입력 + supabase 정상 → True 반환, verification_log에 1건 INSERT."""
        v = Validator(supabase=mock_sb_with_data)
        r = CheckResult(
            stage=1, check_name="count_check",
            check_type="AUTO_HOOK", result_status="PASS",
        )
        assert v.log(r) is True
        inserted = mock_sb_with_data.inserted.get("verification_log", [])
        assert len(inserted) == 1
        # 직렬화 결과 필드 검증
        assert inserted[0]["stage"] == 1
        assert inserted[0]["check_name"] == "count_check"
        assert inserted[0]["result_status"] == "PASS"

    def test_log_with_full_fields(self, mock_sb_with_data: MockSupabase):
        """모든 선택적 필드 설정 → row에 정상 반영."""
        v = Validator(supabase=mock_sb_with_data)
        r = CheckResult(
            stage=2, check_name="sample_acc", check_type="MANUAL_USER",
            result_status="WARNING", expected_value="≥ 0.90",
            actual_value="0.87", threshold="0.90",
            sample_size=100, error_count=13,
            error_examples=[{"id": "x", "reason": "y"}],
            duration_ms=1234, verified_by="taiwangsim",
            notes="sample",
        )
        assert v.log(r) is True
        inserted = mock_sb_with_data.inserted["verification_log"]
        assert inserted[0]["verified_by"] == "taiwangsim"
        assert inserted[0]["sample_size"] == 100
        assert inserted[0]["error_examples"] == [{"id": "x", "reason": "y"}]


# ----- log() error path -----

class TestLogFailure:
    def test_log_supabase_exception_returns_false(self, mock_sb_failing: MockSupabase):
        """INSERT 시 예외 발생 → False 반환 (예외 전파 X)."""
        v = Validator(supabase=mock_sb_failing)
        r = CheckResult(
            stage=1, check_name="x",
            check_type="AUTO_HOOK", result_status="PASS",
        )
        assert v.log(r) is False


# ----- log_batch() -----

class TestLogBatchSuccess:
    def test_batch_inserts_all(self, mock_sb_with_data: MockSupabase):
        """정상 batch → 주입 row 수 반환."""
        v = Validator(supabase=mock_sb_with_data)
        rs = [
            CheckResult(stage=1, check_name="a",
                        check_type="AUTO_HOOK", result_status="PASS"),
            CheckResult(stage=2, check_name="b",
                        check_type="AUTO_HOOK", result_status="FAIL"),
            CheckResult(stage=3, check_name="c",
                        check_type="MANUAL_USER", result_status="WARNING"),
        ]
        n = v.log_batch(rs)
        assert n == 3
        assert len(mock_sb_with_data.inserted.get("verification_log", [])) == 3

    def test_batch_skips_invalid_rows(self, mock_sb_with_data: MockSupabase):
        """입력 검증 실패 row는 skip 후 나머지만 INSERT."""
        v = Validator(supabase=mock_sb_with_data)
        rs = [
            CheckResult(stage=1, check_name="ok1",
                        check_type="AUTO_HOOK", result_status="PASS"),
            # invalid stage
            CheckResult(stage=99, check_name="bad",
                        check_type="AUTO_HOOK", result_status="PASS"),
            CheckResult(stage=2, check_name="ok2",
                        check_type="AUTO_HOOK", result_status="PASS"),
            # invalid status
            CheckResult(stage=1, check_name="bad2",
                        check_type="AUTO_HOOK", result_status="BOGUS"),
        ]
        n = v.log_batch(rs)
        assert n == 2
        inserted = mock_sb_with_data.inserted["verification_log"]
        assert {row["check_name"] for row in inserted} == {"ok1", "ok2"}

    def test_batch_all_invalid_returns_zero(self, mock_sb_with_data: MockSupabase):
        """모든 row 입력 검증 실패 → 0 반환, INSERT 호출 X."""
        v = Validator(supabase=mock_sb_with_data)
        rs = [
            CheckResult(stage=99, check_name="x",
                        check_type="AUTO_HOOK", result_status="PASS"),
            CheckResult(stage=1, check_name="y",
                        check_type="BAD", result_status="PASS"),
        ]
        assert v.log_batch(rs) == 0
        assert "verification_log" not in mock_sb_with_data.inserted


class TestLogBatchFailure:
    def test_batch_supabase_exception_returns_zero(
        self, mock_sb_failing: MockSupabase,
    ):
        """INSERT 예외 → 0 반환 (예외 전파 X)."""
        v = Validator(supabase=mock_sb_failing)
        rs = [CheckResult(
            stage=1, check_name="x",
            check_type="AUTO_HOOK", result_status="PASS",
        )]
        assert v.log_batch(rs) == 0
