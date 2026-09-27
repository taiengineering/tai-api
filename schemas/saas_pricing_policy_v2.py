"""TAI Safe SaaS Pricing Policy V2 — Canonical Policy Contract.

이 모듈은 가격정책값을 버전 가능한 Domain Object로 정의한다.
- 가격 계산 없음
- DB lookup 없음
- Runtime wiring 없음
- API endpoint 없음
- Base price (price_master) 복제 없음
- Worker Pack 없음
- CUSTOM 가격 없음
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator, model_validator

# ── Policy Version ─────────────────────────────────────────────────────────────

PRICING_POLICY_VERSION = "TAI_SAFE_PRICING_POLICY_2026_09_27"
_POLICY_EFFECTIVE_FROM = date(2026, 9, 27)

VALID_TERM_MONTHS_POLICY: frozenset[int] = frozenset({1, 3, 6, 9, 12})


# ── Worker Rate Bracket ────────────────────────────────────────────────────────

class SaasWorkerRateBracketPolicy(BaseModel):
    """작업자 단가 구간 정책 한 줄."""

    model_config = ConfigDict(frozen=True)

    range_from: StrictInt
    range_to: Optional[StrictInt]
    unit_rate: StrictInt

    @field_validator("range_from")
    @classmethod
    def _range_from_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("range_from은 1 이상이어야 합니다.")
        return v

    @field_validator("unit_rate")
    @classmethod
    def _unit_rate_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("unit_rate는 0 이상이어야 합니다.")
        return v

    @model_validator(mode="after")
    def _range_to_not_less_than_from(self) -> "SaasWorkerRateBracketPolicy":
        if self.range_to is not None and self.range_to < self.range_from:
            raise ValueError("range_to는 range_from보다 작을 수 없습니다.")
        return self


# ── Term Discount ──────────────────────────────────────────────────────────────

class SaasTermDiscountPolicy(BaseModel):
    """계약기간별 할인율 정책. discount_rate_bps=None = Owner 미확정."""

    model_config = ConfigDict(frozen=True)

    term_months: StrictInt
    discount_rate_bps: Optional[StrictInt]

    @field_validator("term_months")
    @classmethod
    def _term_months_allowed(cls, v: int) -> int:
        if v not in VALID_TERM_MONTHS_POLICY:
            raise ValueError(f"term_months는 {sorted(VALID_TERM_MONTHS_POLICY)} 중 하나여야 합니다.")
        return v

    @field_validator("discount_rate_bps")
    @classmethod
    def _discount_rate_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 10000):
            raise ValueError("discount_rate_bps는 0~10000 범위여야 합니다.")
        return v


# ── Bracket List Validator ─────────────────────────────────────────────────────

def _validate_bracket_list(brackets: List[SaasWorkerRateBracketPolicy]) -> None:
    """Worker bracket list 연속성 검증. 호출 순서: null check → continuity check."""
    if not brackets:
        raise ValueError("worker_brackets는 비어 있을 수 없습니다.")

    sorted_b = sorted(brackets, key=lambda b: b.range_from)

    # (1) 첫 range_from == 1
    if sorted_b[0].range_from != 1:
        raise ValueError("첫 번째 bracket의 range_from은 1이어야 합니다.")

    # (2) null 규칙: 마지막만 range_to=null
    for i, b in enumerate(sorted_b):
        is_last = i == len(sorted_b) - 1
        if is_last:
            if b.range_to is not None:
                raise ValueError("마지막 bracket의 range_to는 null이어야 합니다.")
        else:
            if b.range_to is None:
                raise ValueError("마지막 bracket을 제외하고 range_to는 null일 수 없습니다.")

    # (3) 연속성: gap / overlap
    for i in range(len(sorted_b) - 1):
        curr = sorted_b[i]
        nxt = sorted_b[i + 1]
        expected = curr.range_to + 1  # type: ignore[operator]  # non-null guaranteed above
        if nxt.range_from < expected:
            raise ValueError(
                f"bracket 겹침(overlap): {curr.range_from}~{curr.range_to} 다음에 {nxt.range_from} 시작"
            )
        if nxt.range_from > expected:
            raise ValueError(
                f"bracket 간격(gap): {curr.range_to}와 {nxt.range_from} 사이 간격 존재"
            )


# ── Full Pricing Policy ────────────────────────────────────────────────────────

class SaasPricingPolicyV2(BaseModel):
    """TAI Safe SaaS 가격정책 V2 — 계산에 사용하는 정책값만 정의."""

    model_config = ConfigDict(frozen=True)

    policy_version: str
    effective_from: date
    effective_to: Optional[date] = None

    field_uplift_amount: StrictInt

    primary_site_rate_bps: StrictInt
    additional_site_rate_bps: StrictInt

    worker_brackets: List[SaasWorkerRateBracketPolicy]

    vat_rate_bps: StrictInt

    term_discounts: List[SaasTermDiscountPolicy]

    currency: str = "KRW"

    @field_validator("field_uplift_amount")
    @classmethod
    def _field_uplift_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("field_uplift_amount는 0 이상이어야 합니다.")
        return v

    @field_validator("primary_site_rate_bps", "additional_site_rate_bps")
    @classmethod
    def _site_rate_range(cls, v: int) -> int:
        if not (0 <= v <= 10000):
            raise ValueError("site rate_bps는 0~10000 범위여야 합니다.")
        return v

    @field_validator("vat_rate_bps")
    @classmethod
    def _vat_rate_range(cls, v: int) -> int:
        if not (0 <= v <= 10000):
            raise ValueError("vat_rate_bps는 0~10000 범위여야 합니다.")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_krw_only(cls, v: str) -> str:
        if v != "KRW":
            raise ValueError("currency는 'KRW'만 허용합니다.")
        return v

    @field_validator("worker_brackets", mode="after")
    @classmethod
    def _validate_worker_brackets(
        cls, v: List[SaasWorkerRateBracketPolicy]
    ) -> List[SaasWorkerRateBracketPolicy]:
        # (1) 입력 순서가 range_from 오름차순이어야 한다 — out-of-order REJECT
        input_order = [b.range_from for b in v]
        if input_order != sorted(input_order):
            raise ValueError(
                f"worker_brackets는 range_from 오름차순으로 입력해야 합니다. (입력: {input_order})"
            )
        # (2) 연속성 검증
        _validate_bracket_list(v)
        return v

    @field_validator("term_discounts", mode="after")
    @classmethod
    def _validate_term_discounts(
        cls, v: List[SaasTermDiscountPolicy]
    ) -> List[SaasTermDiscountPolicy]:
        # (1) 정확히 5개
        if len(v) != 5:
            raise ValueError(
                f"term_discounts는 정확히 5개여야 합니다. (입력: {len(v)}개)"
            )
        # (2) canonical order 1,3,6,9,12 — duplicate 및 out-of-order REJECT
        canonical_order = sorted(VALID_TERM_MONTHS_POLICY)  # [1, 3, 6, 9, 12]
        input_months = [td.term_months for td in v]
        if input_months != canonical_order:
            raise ValueError(
                f"term_discounts는 {canonical_order} 순서여야 합니다. (입력: {input_months})"
            )
        return v


# ── Canonical Policy Factory ───────────────────────────────────────────────────

def get_canonical_pricing_policy_v2() -> SaasPricingPolicyV2:
    """Canonical Pricing Policy V2 반환. Pure function — DB/env/API 없음.

    매 호출마다 새 frozen instance 반환 → 호출자 간 mutable state 공유 없음.
    """
    return SaasPricingPolicyV2(
        policy_version=PRICING_POLICY_VERSION,
        effective_from=_POLICY_EFFECTIVE_FROM,
        field_uplift_amount=100000,
        primary_site_rate_bps=10000,
        additional_site_rate_bps=8000,
        worker_brackets=[
            SaasWorkerRateBracketPolicy(range_from=1,   range_to=20,   unit_rate=3000),
            SaasWorkerRateBracketPolicy(range_from=21,  range_to=50,   unit_rate=2500),
            SaasWorkerRateBracketPolicy(range_from=51,  range_to=100,  unit_rate=2000),
            SaasWorkerRateBracketPolicy(range_from=101, range_to=300,  unit_rate=1500),
            SaasWorkerRateBracketPolicy(range_from=301, range_to=None, unit_rate=1200),
        ],
        vat_rate_bps=1000,
        term_discounts=[
            SaasTermDiscountPolicy(term_months=1,  discount_rate_bps=None),
            SaasTermDiscountPolicy(term_months=3,  discount_rate_bps=None),
            SaasTermDiscountPolicy(term_months=6,  discount_rate_bps=None),
            SaasTermDiscountPolicy(term_months=9,  discount_rate_bps=None),
            SaasTermDiscountPolicy(term_months=12, discount_rate_bps=None),
        ],
    )
