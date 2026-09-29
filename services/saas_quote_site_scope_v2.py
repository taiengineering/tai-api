"""Quote V2 Site Scope Resolver — WO-BE-FE-QUOTE-SCOPE-01.

역할: POST /me/quotes/v2/issue 발행 전 사업장 소유권·섹터·가격기준 검증 및 Canonical Request 재구성.

DB Read: factories (id, company_id, sector, employee_count, building_area)
         construction_sites (id, company_id, contract_amount)
DB Write: 0.
가격 계산: 0.
Pricing Composer 직접 호출: 0.

Sector canonical source:
  INDUSTRY/BUILDING → factories.sector (enum 필드)
  CONSTRUCTION      → construction_sites 소속 전체 CONSTRUCTION 고정

Criteria canonical source:
  INDUSTRY     → factories.employee_count (명, 정수)
  BUILDING     → factories.building_area (㎡, float 허용)
  CONSTRUCTION → construction_sites.contract_amount (억원) × _EOK_TO_WON → 원

Errors:
  QUOTE_SITE_SCOPE_INVALID    422 — 소유권 불일치 / 미존재 / 섹터 불일치 (정보 비노출)
  QUOTE_SITE_CRITERIA_REQUIRED 422 — DB canonical criteria NULL / 음수
  QUOTE_SITE_DATA_CHANGED     409 — request criteria ≠ DB canonical criteria
"""
from __future__ import annotations

from typing import List

from schemas.saas_pricing_preview_v2 import SaasPricingPreviewSiteRequestV2
from services.legal_rules import normalize_sector_db

# construction_sites.contract_amount 는 억원. pricing criteria 는 원.
_EOK_TO_WON = 100_000_000

_FACTORY_SECTORS = frozenset({"INDUSTRY", "BUILDING"})


class QuoteSiteScopeError(Exception):
    """Quote Site Scope 도메인 오류. router 가 HTTP 로 번역한다."""

    def __init__(self, code: str, message: str = "", http_status: int = 422) -> None:
        self.code = code
        self.message = message or code
        self.http_status = http_status
        super().__init__(self.message)


# ── DB loaders ────────────────────────────────────────────────────────────────

def _load_factory(supabase, entity_id: str) -> dict | None:
    rows = (
        supabase.table("factories")
        .select("id, company_id, sector, employee_count, building_area")
        .eq("id", entity_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def _load_construction_site(supabase, entity_id: str) -> dict | None:
    rows = (
        supabase.table("construction_sites")
        .select("id, company_id, contract_amount")
        .eq("id", entity_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


# ── Canonical criteria extraction ─────────────────────────────────────────────

def _canonical_criteria(sector: str, row: dict):
    """DB row → canonical pricing criteria value.

    Returns None when the DB field is absent or None.
    CONSTRUCTION: 억원 → 원 변환 후 반환.
    """
    if sector == "INDUSTRY":
        return row.get("employee_count")
    if sector == "BUILDING":
        return row.get("building_area")
    if sector == "CONSTRUCTION":
        raw = row.get("contract_amount")
        if raw is None:
            return None
        return float(raw) * _EOK_TO_WON
    return None


# ── Public resolver ───────────────────────────────────────────────────────────

def resolve_quote_site_scope_v2(
    supabase,
    company_id: str,
    requested_sites: List[SaasPricingPreviewSiteRequestV2],
) -> List[SaasPricingPreviewSiteRequestV2]:
    """소유권·섹터·기준 검증 후 Canonical sites 반환.

    성공 시 returned list = 입력과 동일 순서, DB 권위 값으로 재구성된 사업장 목록.
    실패 시 QuoteSiteScopeError.
    """
    canonical: list[SaasPricingPreviewSiteRequestV2] = []

    for req in requested_sites:
        entity_id_str = str(req.entity_id)
        sector = req.sector

        # 1. DB lookup (sector 기반 테이블 분기)
        if sector in _FACTORY_SECTORS:
            row = _load_factory(supabase, entity_id_str)
        else:
            row = _load_construction_site(supabase, entity_id_str)

        # 2. Ownership guard — 미존재/타사 동일 응답 (정보 비노출)
        if row is None or str(row.get("company_id")) != str(company_id):
            raise QuoteSiteScopeError(
                "QUOTE_SITE_SCOPE_INVALID",
                "사업장 정보를 확인할 수 없습니다.",
            )

        # 3. Sector guard — DB↔API 경계 normalize 후 비교
        #    DB: INDUSTRIAL / API(request): INDUSTRY — normalize_sector_db 로 동일 canonical 변환
        if sector in _FACTORY_SECTORS:
            db_sector_raw = (row.get("sector") or "").strip()
            if normalize_sector_db(db_sector_raw) != normalize_sector_db(sector):
                raise QuoteSiteScopeError(
                    "QUOTE_SITE_SCOPE_INVALID",
                    "사업장 정보를 확인할 수 없습니다.",
                )

        # 4. Canonical criteria
        canonical_value = _canonical_criteria(sector, row)
        if canonical_value is None:
            raise QuoteSiteScopeError(
                "QUOTE_SITE_CRITERIA_REQUIRED",
                "사업장 규모 정보를 먼저 보완해 주세요.",
            )
        canonical_float = float(canonical_value)
        if canonical_float < 0:
            raise QuoteSiteScopeError(
                "QUOTE_SITE_CRITERIA_REQUIRED",
                "사업장 규모 정보를 먼저 보완해 주세요.",
            )

        # 5. Criteria divergence guard
        if float(req.criteria_value) != canonical_float:
            raise QuoteSiteScopeError(
                "QUOTE_SITE_DATA_CHANGED",
                "사업장 정보가 변경되었습니다. 최신 정보로 이용료를 다시 확인해 주세요.",
                http_status=409,
            )

        # 6. Canonical site (DB 권위값으로 재구성)
        canonical.append(
            SaasPricingPreviewSiteRequestV2(
                entity_id=req.entity_id,
                sector=sector,
                criteria_value=canonical_value if isinstance(canonical_value, int)
                               else (int(canonical_float) if canonical_float == int(canonical_float)
                                     else canonical_float),
            )
        )

    return canonical
