"""doc_m004_binding_adapter.py — WP-L2: Obligation → Form Binding Adapter

MASTERPLAN-004 WP-L2: 기존 법령 의무 코드와 공식서식·문서 카탈로그를 연결하는
최소 Binding Adapter.

- 기존 WP-L1 서비스 재사용 (doc_m004_dryrun.classify_one_obligation)
- READ-ONLY — Production DB write = 0
- 신규 테이블 생성 없음 / 신규 분류엔진 생성 없음
- 식별자 추정 연결 금지

Binding 상태:
  VERIFIED        — 공식 법령 증거(law_api_id + law_mst_no) + form_templates 연결 확인
  CATALOG_LINKED  — TAI 내부 의무→서식 연결 확인, 공식 법령 증거 미확인
  PARTIAL         — 의무→form_code 연결 있으나 form_templates 없음 (충돌 아님)
  REVIEW_REQUIRED — 법령 버전 충돌, 복수 후보, 식별자 충돌 등
  NOT_LINKED      — 의무→서식 매핑 없음

운영 DB 현황 (2026-10-13):
  legal_obligations = 0  → ob.id = "" (가짜 row 생성 금지)
  rule_doc_mapping = 0   → doc_id 항상 UNVERIFIED
  obligation_form_mapping = 11건 중 form_templates 일치 = 5건
  파일럿: OSH_ACCIDENT_REPORT → OSHACT-FORM-030, bylseq=17853759 → CATALOG_LINKED
  OSHACT-FORM-002: 기존 충돌 이력 → REVIEW_REQUIRED 유지
"""
from __future__ import annotations

from typing import Optional

from services.doc_m004_dryrun import classify_one_obligation, UNVERIFIED

# Binding 상태값
VERIFIED = "VERIFIED"
CATALOG_LINKED = "CATALOG_LINKED"
PARTIAL = "PARTIAL"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
NOT_LINKED = "NOT_LINKED"


def _determine_binding_status(
    form_code: str,
    bylseq: str,
    has_official_evidence: bool,
    review_reason: Optional[str],
    law_version_conflict: bool,
) -> str:
    """Binding 상태 판정.

    review_reason 분석:
      "form_templates 없음:" 단독 → PARTIAL (연결 불완전, 충돌 아님)
      그 외 review_reason       → REVIEW_REQUIRED (충돌/불명확)
    """
    if form_code == UNVERIFIED:
        return NOT_LINKED

    if law_version_conflict:
        return REVIEW_REQUIRED

    if review_reason:
        reasons = [r.strip() for r in review_reason.split(";")]
        conflict_reasons = [
            r for r in reasons
            if not r.startswith("form_templates 없음")
        ]
        if conflict_reasons:
            return REVIEW_REQUIRED

    # form_code 있으나 form_templates 없음 (bylseq UNVERIFIED)
    if bylseq == UNVERIFIED:
        return PARTIAL

    if has_official_evidence:
        return VERIFIED
    return CATALOG_LINKED


def resolve_binding(
    sb,
    obligation_code: str,
    official_evidence: Optional[dict] = None,
) -> dict:
    """단일 obligation_code에 대한 Binding 해결.

    Args:
        sb: Supabase 클라이언트 (READ-ONLY)
        obligation_code: legal_obligations.category_code 기준 의무 코드
        official_evidence: {
            "law_api_id": str,            # 법제처 API ID (확인 시)
            "law_mst_no": str,            # 법령 일련번호 (확인 시)
            "law_version_conflict": bool, # 버전 충돌 플래그
        }

    Returns:
        obligation_code, form_code, bylseq, source_namespace,
        law_api_id, law_mst_no, doc_id, catalog_document_id,
        runtime_form_schema_id, binding_status, reuse_status,
        evidence_reference, review_reason

        없는 값은 UNVERIFIED.
        CATALOG_LINKED를 VERIFIED로 자동 승격 금지.
    """
    ev = official_evidence or {}
    law_api_id = ev.get("law_api_id") or UNVERIFIED
    law_mst_no = ev.get("law_mst_no") or UNVERIFIED
    law_version_conflict = bool(ev.get("law_version_conflict", False))

    has_official_evidence = (
        law_api_id != UNVERIFIED and law_mst_no != UNVERIFIED
    )

    # WP-L1 분류 재사용
    # legal_obligations = 0건 → ob.id = "" (가짜 row 생성 금지)
    ob = {
        "id": "",
        "category_code": obligation_code,
        "law_api_id": law_api_id,
        "law_mst_no": law_mst_no,
        # legal_rule_id: 실제 legal_obligations에 없는 컬럼 → 미포함
    }
    wpl1 = classify_one_obligation(sb, ob)

    binding_status = _determine_binding_status(
        form_code=wpl1["form_code"],
        bylseq=wpl1["bylseq"],
        has_official_evidence=has_official_evidence,
        review_reason=wpl1["review_reason"],
        law_version_conflict=law_version_conflict,
    )

    return {
        "obligation_code":        obligation_code,
        "form_code":              wpl1["form_code"],
        "bylseq":                 wpl1["bylseq"],
        "source_namespace":       wpl1["source_namespace"],
        "law_api_id":             law_api_id,
        "law_mst_no":             law_mst_no,
        "doc_id":                 wpl1["doc_id"],
        "catalog_document_id":    wpl1["document_form_id"],
        "runtime_form_schema_id": wpl1["runtime_form_schema_id"],
        "binding_status":         binding_status,
        "reuse_status":           wpl1["reuse_status"],
        "evidence_reference":     wpl1["evidence_reference"],
        "review_reason":          wpl1["review_reason"],
    }


def run_binding(sb, obligations: list[dict]) -> dict:
    """obligations 리스트 전체 Binding 해결 + 요약 반환.

    Args:
        obligations: [{"obligation_code": str, "official_evidence": dict | None}, ...]

    Returns:
        {
            "results": [per-obligation binding rows],
            "summary": {status: count, "total": n},
            "verified_bindings": [VERIFIED rows],
            "catalog_linked":    [CATALOG_LINKED rows],
            "unresolved":        [REVIEW_REQUIRED + NOT_LINKED rows],
        }
    """
    results = []
    for item in obligations:
        code = item.get("obligation_code") or ""
        ev = item.get("official_evidence")
        results.append(resolve_binding(sb, code, ev))

    counts: dict[str, int] = {
        VERIFIED: 0,
        CATALOG_LINKED: 0,
        PARTIAL: 0,
        REVIEW_REQUIRED: 0,
        NOT_LINKED: 0,
    }
    for r in results:
        bs = r["binding_status"]
        counts[bs] = counts.get(bs, 0) + 1

    return {
        "results": results,
        "summary": {**counts, "total": len(results)},
        "verified_bindings": [r for r in results if r["binding_status"] == VERIFIED],
        "catalog_linked":    [r for r in results if r["binding_status"] == CATALOG_LINKED],
        "unresolved": [
            r for r in results
            if r["binding_status"] in (REVIEW_REQUIRED, NOT_LINKED)
        ],
    }
