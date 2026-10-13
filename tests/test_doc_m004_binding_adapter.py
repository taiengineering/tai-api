"""WO-TAI-DOC-M004-WP-L2-BINDING-001 — Binding Adapter 테스트

T01 파일럿: OSH_ACCIDENT_REPORT → OSHACT-FORM-030 → CATALOG_LINKED
T02 매핑 없는 의무 → NOT_LINKED
T03 form_templates 없는 매핑 → PARTIAL (충돌 아님, 연결 불완전)
T04 법령 식별자 미확인 시 VERIFIED 금지 (CATALOG_LINKED 유지)
T05 법령 버전 충돌 시 REVIEW_REQUIRED
T06 복수 의무 → 동일 서식 허용 (오류 아님, 둘 다 CATALOG_LINKED)
T07 rule_doc_mapping 0건 → doc_id, catalog_document_id 모두 UNVERIFIED
T08 기존 WP-L1 결과 계약 유지 (필수 컬럼 + reuse_status 포함)
T09 DB write = 0

Production DB write = 0 (mock 전용).
운영 DB 제약: legal_obligations=0, rule_doc_mapping=0
파일럿 결과: VERIFIED_BINDING_COUNT=0 허용 (공식 증거 미확인 → CATALOG_LINKED)
"""
from __future__ import annotations

from unittest.mock import MagicMock

from services.doc_m004_binding_adapter import (
    resolve_binding,
    run_binding,
    VERIFIED,
    CATALOG_LINKED,
    PARTIAL,
    REVIEW_REQUIRED,
    NOT_LINKED,
)
from services.doc_m004_dryrun import UNVERIFIED


# ─── fixture helpers ─────────────────────────────────────────────────────────

class _R:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if isinstance(data, list) else 0)


def _sb(table_data: dict) -> MagicMock:
    sb = MagicMock()
    insert_calls: list = []

    def _tbl(name):
        rows = table_data.get(name, [])
        tbl = MagicMock()
        q = MagicMock()
        tbl.select.return_value = q
        tbl.insert.side_effect = (
            lambda d: insert_calls.append(("INSERT", name, d))
            or MagicMock(execute=lambda: _R([]))
        )
        q.eq.return_value = q
        q.limit.return_value = q
        q.execute.return_value = _R(rows)
        q.single.return_value = MagicMock(execute=lambda: _R(rows[0] if rows else None))
        return tbl

    sb.table.side_effect = _tbl
    sb._insert_calls = insert_calls
    return sb


# ─── shared fixtures ─────────────────────────────────────────────────────────

FT_030 = {
    "id": "ft-030",
    "form_code": "OSHACT-FORM-030",
    "form_name": "중대재해 발생 보고서",
    "law_code": "OSHACT",
    "bylseq": "17853759",
    "is_active": True,
}

FT_002 = {
    "id": "ft-002",
    "form_code": "OSHACT-FORM-002",
    "form_name": "안전보건교육 기록서",
    "law_code": "OSHACT",
    "bylseq": "BYL-002",
    "is_active": True,
}


def _pilot_sb() -> MagicMock:
    """OSH_ACCIDENT_REPORT → OSHACT-FORM-030 파일럿 mock."""
    return _sb({
        "obligation_form_mapping": [{"form_code": "OSHACT-FORM-030"}],
        "form_templates":          [FT_030],
        "rule_doc_mapping":        [],
        "document_forms":          [],
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })


# ─── T01: 파일럿 CATALOG_LINKED ───────────────────────────────────────────────

def test_T01_pilot_osh_accident_report_catalog_linked():
    """OSH_ACCIDENT_REPORT → OSHACT-FORM-030: CATALOG_LINKED (공식 증거 미확인)."""
    sb = _pilot_sb()
    r = resolve_binding(sb, "OSH_ACCIDENT_REPORT")

    assert r["binding_status"] == CATALOG_LINKED
    assert r["form_code"] == "OSHACT-FORM-030"
    assert r["bylseq"] == "17853759"
    assert r["source_namespace"] == UNVERIFIED   # law_code ≠ source_namespace
    assert r["doc_id"] == UNVERIFIED              # rule_doc_mapping = 0건
    assert r["catalog_document_id"] == UNVERIFIED
    assert r["reuse_status"] == "B"               # form_templates 존재, catalog 없음
    assert r["review_reason"] is None


# ─── T02: 매핑 없는 의무 → NOT_LINKED ─────────────────────────────────────────

def test_T02_no_mapping_not_linked():
    """obligation_form_mapping 없는 의무 → NOT_LINKED."""
    sb = _sb({
        "obligation_form_mapping": [],
        "form_templates":          [],
        "rule_doc_mapping":        [],
        "document_forms":          [],
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })
    r = resolve_binding(sb, "OB-UNKNOWN-999")

    assert r["binding_status"] == NOT_LINKED
    assert r["form_code"] == UNVERIFIED


# ─── T03: form_templates 없는 매핑 → PARTIAL ──────────────────────────────────

def test_T03_missing_form_template_partial():
    """obligation_form_mapping 있으나 form_templates 없음 → PARTIAL."""
    sb = _sb({
        "obligation_form_mapping": [{"form_code": "FORM-MISSING-999"}],
        "form_templates":          [],   # form_templates 없음
        "rule_doc_mapping":        [],
        "document_forms":          [],
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })
    r = resolve_binding(sb, "OB-PARTIAL")

    assert r["binding_status"] == PARTIAL
    assert r["form_code"] == "FORM-MISSING-999"
    assert r["bylseq"] == UNVERIFIED


# ─── T04: 법령 식별자 미확인 시 VERIFIED 금지 ─────────────────────────────────

def test_T04_incomplete_evidence_not_verified():
    """law_api_id만 있고 law_mst_no 없음 → VERIFIED 아닌 CATALOG_LINKED."""
    sb = _pilot_sb()
    r = resolve_binding(
        sb,
        "OSH_ACCIDENT_REPORT",
        official_evidence={"law_api_id": "LA-001"},  # law_mst_no 없음
    )

    assert r["binding_status"] == CATALOG_LINKED
    assert r["binding_status"] != VERIFIED


# ─── T05: 법령 버전 충돌 시 REVIEW_REQUIRED ───────────────────────────────────

def test_T05_law_version_conflict_review_required():
    """official_evidence에 law_version_conflict=True → REVIEW_REQUIRED."""
    sb = _pilot_sb()
    r = resolve_binding(
        sb,
        "OSH_ACCIDENT_REPORT",
        official_evidence={
            "law_api_id": "LA-001",
            "law_mst_no": "MST-001",
            "law_version_conflict": True,
        },
    )

    assert r["binding_status"] == REVIEW_REQUIRED


# ─── T06: 복수 의무 → 동일 서식 허용 ─────────────────────────────────────────

def test_T06_multiple_obligations_same_form_allowed():
    """복수 의무가 동일 form_code 사용 → 오류 아님, 둘 다 CATALOG_LINKED."""
    sb = _pilot_sb()  # 모든 의무에 OSHACT-FORM-030 반환
    result = run_binding(sb, [
        {"obligation_code": "OB-A", "official_evidence": None},
        {"obligation_code": "OB-B", "official_evidence": None},
    ])

    assert result["summary"]["total"] == 2
    assert result["summary"][CATALOG_LINKED] == 2
    assert result["summary"][REVIEW_REQUIRED] == 0


# ─── T07: rule_doc_mapping 0건 → catalog 연결 UNVERIFIED ─────────────────────

def test_T07_no_rule_doc_mapping_catalog_unverified():
    """rule_doc_mapping = 0건 → doc_id, catalog_document_id, schema_id 모두 UNVERIFIED."""
    sb = _pilot_sb()
    r = resolve_binding(sb, "OSH_ACCIDENT_REPORT")

    assert r["doc_id"] == UNVERIFIED
    assert r["catalog_document_id"] == UNVERIFIED
    assert r["runtime_form_schema_id"] == UNVERIFIED


# ─── T08: WP-L1 결과 계약 유지 ───────────────────────────────────────────────

def test_T08_wpl1_contract_maintained():
    """resolve_binding 결과에 WP-L1 필수 컬럼 포함 및 reuse_status 유효값."""
    sb = _pilot_sb()
    r = resolve_binding(sb, "OSH_ACCIDENT_REPORT")

    required_keys = {
        "obligation_code", "form_code", "bylseq", "source_namespace",
        "law_api_id", "law_mst_no", "doc_id", "catalog_document_id",
        "runtime_form_schema_id", "binding_status", "reuse_status",
        "evidence_reference", "review_reason",
    }
    missing = required_keys - r.keys()
    assert not missing, f"missing keys: {missing}"
    assert r["reuse_status"] in ("A", "B", "C", "D")


# ─── T09: DB write = 0 ────────────────────────────────────────────────────────

def test_T09_no_db_write():
    """Binding 해결 중 insert 미호출 — READ-ONLY."""
    sb = _pilot_sb()
    resolve_binding(sb, "OSH_ACCIDENT_REPORT")
    assert len(sb._insert_calls) == 0, f"insert 호출 감지: {sb._insert_calls}"
