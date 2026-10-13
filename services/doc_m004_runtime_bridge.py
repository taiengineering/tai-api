"""doc_m004_runtime_bridge.py — WP-L3: Runtime Bridge

WP-L2 Binding → 기존 catalog_resolver → Runtime Schema 상태 반환.
기존 문서엔진 수정 없음. 신규 테이블 없음. READ-ONLY.

Runtime Availability 상태:
  READY_FOR_EDIT     — 단일 APPROVED_FOR_RUNTIME_USE schema + 필드 유효
                       기존 문서엔진 작성 계약 사용 가능
  PREPARING          — CANDIDATE schema 존재, 작성 활성화 금지
  NO_SCHEMA          — 카탈로그 존재, runtime_form_schema 없음
  NO_CATALOG_BINDING — 법령→카탈로그 연결 없음 (rule_doc_mapping=0 등)
  REVIEW_REQUIRED    — Binding 충돌/식별자 검증 필요, 자동 연결 금지

READY_FOR_EDIT는 schema 준비 상태이며 법령 의무의 공식 검증 완료를 뜻하지 않는다.
  → law_verified 별도 확인 필수 (binding_status == "VERIFIED" 시에만 True).
can_create_document = (runtime_availability == "READY_FOR_EDIT")
  → 기존 문서엔진 계약 사용 가능 여부 표시.
  → WP-L3는 작성 활성화 단계 아님 — 실제 create_document 호출 없음.

운영 DB 현황 (2026-10-13):
  rule_doc_mapping = 0건 → 의무 기반 catalog_document_id 항상 UNVERIFIED
  APPROVED schema catalog_linked = 0건
  → 의무 기반 READY_FOR_EDIT = 0 (정상)
  → CANDIDATE 260건은 resolve_catalog_bridge로 독립 조회 가능
"""
from __future__ import annotations

from typing import Optional

from services.doc_m004_binding_adapter import resolve_binding
from services.doc_m004_dryrun import UNVERIFIED
from services.document_engine.catalog_resolver import resolve_catalog_runtime_schema


def _empty_bridge(obligation_code: Optional[str], binding: dict) -> dict:
    """전체 계약 컬럼 포함 기본 결과."""
    return {
        "obligation_code":        obligation_code,
        "form_code":              binding.get("form_code", UNVERIFIED),
        "binding_status":         binding.get("binding_status", UNVERIFIED),
        "reuse_status":           binding.get("reuse_status", UNVERIFIED),
        "doc_id":                 binding.get("doc_id", UNVERIFIED),
        "catalog_document_id":    binding.get("catalog_document_id", UNVERIFIED),
        "runtime_form_schema_id": UNVERIFIED,
        "runtime_availability":   UNVERIFIED,
        "field_count":            0,
        "checklist_count":        0,
        "evidence_field_count":   0,
        "law_verified":           False,
        "can_create_document":    False,
        "review_reason":          binding.get("review_reason"),
        "evidence_reference":     binding.get("evidence_reference", UNVERIFIED),
    }


def _merge_catalog(
    obligation_code: Optional[str],
    binding: dict,
    catalog_result: dict,
) -> dict:
    """Binding + Catalog Resolver 결과 병합."""
    availability = catalog_result["availability"]
    schema_id = (
        catalog_result.get("active_schema_id")
        or catalog_result.get("candidate_schema_id")
        or UNVERIFIED
    )
    fields          = catalog_result.get("fields", [])
    checklists      = catalog_result.get("checklists", [])
    evidence_fields = catalog_result.get("evidence_fields", [])

    # law_verified: 공식 법령 증거 + binding 확인된 경우에만 True
    law_verified        = binding.get("binding_status") == "VERIFIED"
    can_create_document = availability == "READY_FOR_EDIT"

    result = _empty_bridge(obligation_code, binding)
    result.update({
        "runtime_form_schema_id": schema_id,
        "runtime_availability":   availability,
        "field_count":            len(fields),
        "checklist_count":        len(checklists),
        "evidence_field_count":   len(evidence_fields),
        "law_verified":           law_verified,
        "can_create_document":    can_create_document,
    })
    return result


def resolve_runtime_bridge(
    sb,
    obligation_code: str,
    official_evidence: Optional[dict] = None,
) -> dict:
    """의무 기반 Runtime Schema 연결.

    절차:
      1. WP-L2 resolve_binding 호출
      2. REVIEW_REQUIRED → runtime_availability=REVIEW_REQUIRED (차단)
      3. catalog_document_id == UNVERIFIED → NO_CATALOG_BINDING
      4. 유효한 catalog_document_id → 기존 resolve_catalog_runtime_schema 호출
      5. 결과 반환

    법령 식별자 추정 및 catalog_document_id 임의 생성 금지.
    기존 문서엔진 create_document 호출 없음.
    """
    binding = resolve_binding(sb, obligation_code, official_evidence)

    if binding["binding_status"] == "REVIEW_REQUIRED":
        result = _empty_bridge(obligation_code, binding)
        result["runtime_availability"] = "REVIEW_REQUIRED"
        return result

    catalog_id = binding["catalog_document_id"]
    if catalog_id == UNVERIFIED:
        result = _empty_bridge(obligation_code, binding)
        result["runtime_availability"] = "NO_CATALOG_BINDING"
        return result

    try:
        catalog_result = resolve_catalog_runtime_schema(catalog_id)
    except (ValueError, RuntimeError):
        result = _empty_bridge(obligation_code, binding)
        result["runtime_availability"] = "NO_SCHEMA"
        return result

    return _merge_catalog(obligation_code, binding, catalog_result)


def resolve_catalog_bridge(catalog_document_id: str) -> dict:
    """카탈로그 독립 조회 — 법령 연결 여부와 무관.

    기존 document_forms.id로 Runtime Schema 상태를 조회한다.
    특정 법령 의무에 자동 귀속하지 않는다.
    카탈로그 독립 조회 결과를 법령 검증 근거로 사용하지 않는다.
    """
    null_binding = {
        "form_code":           UNVERIFIED,
        "binding_status":      UNVERIFIED,
        "reuse_status":        UNVERIFIED,
        "doc_id":              UNVERIFIED,
        "catalog_document_id": catalog_document_id,
        "review_reason":       None,
        "evidence_reference":  UNVERIFIED,
    }

    try:
        catalog_result = resolve_catalog_runtime_schema(catalog_document_id)
    except (ValueError, RuntimeError):
        result = _empty_bridge(None, null_binding)
        result["runtime_availability"] = "NO_SCHEMA"
        return result

    return _merge_catalog(None, null_binding, catalog_result)
