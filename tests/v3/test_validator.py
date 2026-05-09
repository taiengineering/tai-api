"""TAI 법령엔진 v3.0 — engine.validator 단위 테스트.

실행: pytest tests/v3/test_validator.py -v

평가 함수(staticmethod) 중심 검증 — DB 의존 X. 높은 커버리지 확보.
"""

from __future__ import annotations

import pytest

from engine.validator import (
    SAMPLE_ACCURACY_THRESHOLDS,
    VALID_CHECK_TYPE,
    VALID_RESULT_STATUS,
    VALID_STAGES,
    CheckResult,
    Validator,
)


@pytest.fixture
def validator() -> Validator:
    return Validator(supabase=None)


# ----- 임계값 상수 -----

class TestThresholds:
    def test_thresholds_match_master_spec(self):
        """마스터 §3.4 임계값과 일치."""
        assert SAMPLE_ACCURACY_THRESHOLDS[1] == 0.95
        assert SAMPLE_ACCURACY_THRESHOLDS[2] == 0.90
        assert SAMPLE_ACCURACY_THRESHOLDS[3] == 0.90

    def test_valid_status_set(self):
        assert VALID_RESULT_STATUS == frozenset({"PASS", "FAIL", "WARNING", "INFO"})

    def test_valid_check_type_set(self):
        assert VALID_CHECK_TYPE == frozenset({"AUTO_HOOK", "MANUAL_USER"})

    def test_valid_stages_set(self):
        assert VALID_STAGES == frozenset({1, 2, 3})


# ----- count_mapping 평가 -----

class TestCountMapping:
    def test_perfect_match_passes(self):
        r = Validator.evaluate_count_mapping(expected=100, actual=100, stage=1)
        assert r.result_status == "PASS"
        assert r.error_count == 0
        assert r.expected_value == "100"
        assert r.actual_value == "100"
        assert r.stage == 1
        assert r.check_type == "AUTO_HOOK"

    def test_loss_fails(self):
        r = Validator.evaluate_count_mapping(expected=100, actual=98, stage=2)
        assert r.result_status == "FAIL"
        assert r.error_count == 2

    def test_overshoot_clipped_to_zero(self):
        """actual > expected도 error_count 음수 X."""
        r = Validator.evaluate_count_mapping(expected=100, actual=105, stage=1)
        assert r.error_count == 0

    def test_zero_zero_passes(self):
        r = Validator.evaluate_count_mapping(expected=0, actual=0, stage=1)
        assert r.result_status == "PASS"

    def test_custom_check_name(self):
        r = Validator.evaluate_count_mapping(
            expected=10, actual=10, stage=1, check_name="my_check"
        )
        assert r.check_name == "my_check"


# ----- sample_accuracy 평가 -----

class TestSampleAccuracy:
    def test_pass_above_stage_1_threshold(self):
        r = Validator.evaluate_sample_accuracy(stage=1, accuracy=0.96, sample_size=100)
        assert r.result_status == "PASS"

    def test_pass_at_exact_threshold(self):
        r = Validator.evaluate_sample_accuracy(stage=1, accuracy=0.95, sample_size=100)
        assert r.result_status == "PASS"

    def test_warning_within_5pct(self):
        """임계값 5%p 이내 미달 → WARNING."""
        r = Validator.evaluate_sample_accuracy(stage=1, accuracy=0.92, sample_size=100)
        assert r.result_status == "WARNING"

    def test_fail_far_below(self):
        """임계값 5%p 초과 미달 → FAIL."""
        r = Validator.evaluate_sample_accuracy(stage=1, accuracy=0.85, sample_size=100)
        assert r.result_status == "FAIL"

    def test_stage_2_lower_threshold(self):
        r = Validator.evaluate_sample_accuracy(stage=2, accuracy=0.91, sample_size=100)
        assert r.result_status == "PASS"

    def test_stage_3_lower_threshold(self):
        r = Validator.evaluate_sample_accuracy(stage=3, accuracy=0.90, sample_size=100)
        assert r.result_status == "PASS"

    def test_error_count_calculated(self):
        """error_count = round((1 - accuracy) * sample_size)."""
        r = Validator.evaluate_sample_accuracy(stage=2, accuracy=0.90, sample_size=100)
        assert r.error_count == 10

    def test_unknown_stage_fallback_threshold(self):
        """알 수 없는 stage → 기본 0.90 임계."""
        r = Validator.evaluate_sample_accuracy(stage=99, accuracy=0.91, sample_size=10)
        assert r.result_status == "PASS"


# ----- duplicates 평가 -----

class TestDuplicates:
    def test_zero_passes(self):
        r = Validator.evaluate_duplicates(duplicate_count=0, stage=1)
        assert r.result_status == "PASS"
        assert r.error_count == 0

    def test_any_duplicate_fails(self):
        r = Validator.evaluate_duplicates(duplicate_count=1, stage=1)
        assert r.result_status == "FAIL"
        assert r.error_count == 1

    def test_many_duplicates(self):
        r = Validator.evaluate_duplicates(duplicate_count=42, stage=2)
        assert r.result_status == "FAIL"
        assert r.error_count == 42


# ----- 입력 검증 -----

class TestInputValidation:
    def test_invalid_status_raises(self, validator: Validator):
        bad = CheckResult(
            stage=1, check_name="x", check_type="AUTO_HOOK", result_status="INVALID"
        )
        with pytest.raises(ValueError, match="result_status"):
            validator.log(bad)

    def test_invalid_check_type_raises(self, validator: Validator):
        bad = CheckResult(
            stage=1, check_name="x", check_type="BAD", result_status="PASS"
        )
        with pytest.raises(ValueError, match="check_type"):
            validator.log(bad)

    def test_invalid_stage_raises(self, validator: Validator):
        bad = CheckResult(
            stage=4, check_name="x", check_type="AUTO_HOOK", result_status="PASS"
        )
        with pytest.raises(ValueError, match="stage"):
            validator.log(bad)

    def test_valid_input_passes_validation(self, validator: Validator):
        """정상 입력은 ValueError 발생 X (DB 미설정도 False 반환만)."""
        good = CheckResult(
            stage=1, check_name="x", check_type="AUTO_HOOK", result_status="PASS"
        )
        # 예외 X, False (supabase=None) 반환
        assert validator.log(good) is False


# ----- DB 없을 때 안전성 -----

class TestNoSupabaseSafety:
    def test_log_no_supabase_returns_false(self, validator: Validator):
        r = CheckResult(
            stage=1, check_name="x", check_type="AUTO_HOOK", result_status="PASS"
        )
        assert validator.log(r) is False

    def test_log_batch_no_supabase_returns_zero(self, validator: Validator):
        rs = [CheckResult(
            stage=1, check_name="x", check_type="AUTO_HOOK", result_status="PASS"
        )]
        assert validator.log_batch(rs) == 0

    def test_log_batch_empty(self, validator: Validator):
        assert validator.log_batch([]) == 0


# ----- 행 직렬화 -----

class TestResultToRow:
    def test_row_complete(self):
        r = CheckResult(
            stage=2,
            check_name="sample_accuracy",
            check_type="AUTO_HOOK",
            result_status="PASS",
            expected_value="≥ 0.90",
            actual_value="0.92",
            threshold="0.90",
            sample_size=100,
            error_count=8,
            error_examples=[{"id": "x", "reason": "y"}],
            duration_ms=1234,
            verified_by="system",
            notes="test note",
        )
        row = Validator._result_to_row(r)
        assert row["stage"] == 2
        assert row["check_name"] == "sample_accuracy"
        assert row["result_status"] == "PASS"
        assert row["error_examples"] == [{"id": "x", "reason": "y"}]
        assert row["duration_ms"] == 1234
        assert row["verified_by"] == "system"

    def test_row_minimal(self):
        r = CheckResult(
            stage=1, check_name="x", check_type="AUTO_HOOK", result_status="PASS"
        )
        row = Validator._result_to_row(r)
        assert row["stage"] == 1
        assert row["error_count"] == 0
        assert row["error_examples"] == []
        assert row["sample_size"] is None
        assert row["notes"] is None
