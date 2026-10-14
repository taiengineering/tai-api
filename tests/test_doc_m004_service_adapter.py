"""WO-TAI-DOC-M004-EXISTING-DOCUMENT-SERVICE-ADAPTER-004 — Service Adapter 테스트

T01 DOWNLOAD: obligation_code + hwp_url 있음 → AVAILABLE
T02 DOWNLOAD: obligation_code + hwp_url 없음 → UNRESOLVED
T03 DOWNLOAD: obligation_form_mapping 없음 → UNRESOLVED
T04 atom_id 단독 → 모든 경로 UNRESOLVED, mc001_gap=True (MC-001)
T05 obligation_code·atom_id 모두 없음 → ALL_UNRESOLVED, mc001_gap=False
T06 REVIEW_REQUIRED binding → DOWNLOAD REVIEW_REQUIRED, WEB_EDIT REVIEW_REQUIRED
T07 WEB_EDIT: READY_FOR_EDIT → AVAILABLE, can confirm schema_id
T08 WEB_EDIT: NO_CATALOG_BINDING → UNRESOLVED
T09 WEB_EDIT: PREPARING → PREPARING (not available)
T10 WEB_EDIT: NO_SCHEMA → NO_SCHEMA (not available)
T11 PARTIAL_AVAILABLE: DOWNLOAD 가능 + WEB_EDIT 불가
T12 AUTO == WEB_EDIT (동일 스키마 기반)
T13 필수 계약 컬럼 전체 존재
T14 DB write = 0 (READ-ONLY)

Production DB write = 0 (mock 전용).
운영 DB 현황 (2026-10-15):
  APPROVED schema with catalog_document_id → 0건 (WEB_EDIT AVAILABLE = 현재 0)
  obligation_form_mapping → form_templates(hwp_url) → 5건 (DOWNLOAD 경로 가능)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.doc_m004_service_adapter import (
    get_service_availability,
    AVAILABLE,
    UNRESOLVED,
    REVIEW_REQUIRED,
    PREPARING,
    NO_SCHEMA,
)


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

FT_030_WITH_URL = {
    "id": "ft-030",
    "form_code": "OSHACT-FORM-030",
    "form_name": "중대재해 발생 보고서",
    "law_code": "OSHACT",
    "bylseq": "17853759",
    "is_active": True,
    "hwp_url": "https://www.law.go.kr/flDownload.do?flSeq=17853759",
}

FT_030_NO_URL = {**FT_030_WITH_URL, "hwp_url": None}

FT_002_CONFLICT = {
    "id": "ft-002",
    "form_code": "OSHACT-FORM-002",
    "form_name": "안전보건교육 기록서",
    "law_code": "OSHACT",
    "bylseq": "BYL-002",
    "is_active": True,
    "hwp_url": "https://www.law.go.kr/flDownload.do?flSeq=BYL-002",
}

CATALOG_READY = {
    "availability": "READY_FOR_EDIT",
    "active_schema_id": "rfs-approved-001",
    "candidate_schema_id": None,
    "active_schema_status": "APPROVED_FOR_RUNTIME_USE",
    "candidate_schema_status": None,
    "schema": {"id": "rfs-approved-001", "status": "APPROVED_FOR_RUNTIME_USE"},
    "fields": [{"id": f"f{i}"} for i in range(5)],
    "checklists": [{"id": "c1"}],
    "evidence_fields": [{"id": "ev1"}],
}

CATALOG_PREPARING = {
    "availability": "PREPARING",
    "active_schema_id": None,
    "candidate_schema_id": "rfs-cand-001",
    "schema": None,
    "fields": [{"id": "f1"}],
    "checklists": [],
    "evidence_fields": [],
}

CATALOG_NO_SCHEMA_RESULT = {
    "availability": "NO_SCHEMA",
    "active_schema_id": None,
    "candidate_schema_id": None,
    "schema": None,
    "fields": [],
    "checklists": [],
    "evidence_fields": [],
}


def _pilot_sb_with_url() -> MagicMock:
    """OSH_ACCIDENT_REPORT → OSHACT-FORM-030 + hwp_url 있음."""
    return _sb({
        "obligation_form_mapping": [{"form_code": "OSHACT-FORM-030"}],
        "form_templates": [FT_030_WITH_URL],
        "rule_doc_mapping": [],
        "document_forms": [],
        "runtime_form_schema": [],
        "runtime_field": [],
    })


def _pilot_sb_no_url() -> MagicMock:
    """OSH_ACCIDENT_REPORT → OSHACT-FORM-030 + hwp_url 없음."""
    return _sb({
        "obligation_form_mapping": [{"form_code": "OSHACT-FORM-030"}],
        "form_templates": [FT_030_NO_URL],
        "rule_doc_mapping": [],
        "document_forms": [],
        "runtime_form_schema": [],
        "runtime_field": [],
    })


def _no_mapping_sb() -> MagicMock:
    """obligation_form_mapping 없음."""
    return _sb({
        "obligation_form_mapping": [],
        "form_templates": [],
        "rule_doc_mapping": [],
        "document_forms": [],
        "runtime_form_schema": [],
        "runtime_field": [],
    })


def _conflict_sb() -> MagicMock:
    """OSHACT-FORM-002 충돌 이력 → REVIEW_REQUIRED."""
    return _sb({
        "obligation_form_mapping": [{"form_code": "OSHACT-FORM-002"}],
        "form_templates": [FT_002_CONFLICT],
        "rule_doc_mapping": [],
        "document_forms": [],
        "runtime_form_schema": [],
        "runtime_field": [],
    })


def _catalog_linked_sb(catalog_id: str) -> MagicMock:
    """rule_doc_mapping + document_forms + runtime_form_schema 모두 존재."""
    return _sb({
        "obligation_form_mapping": [{"form_code": "OSHACT-FORM-030"}],
        "form_templates": [FT_030_WITH_URL],
        "rule_doc_mapping": [{"doc_id": "doc-001"}],
        "document_forms": [{"id": catalog_id, "doc_id": "doc-001", "doc_name": "test", "category": "LEGAL", "law_ref": "OSHACT", "is_active": True}],
        "runtime_form_schema": [{"id": "rfs-approved-001", "status": "APPROVED_FOR_RUNTIME_USE", "catalog_document_id": catalog_id}],
        "runtime_field": [{"id": "f1"}],
    })


# ─── T01: DOWNLOAD AVAILABLE ─────────────────────────────────────────────────

def test_T01_download_available_with_hwp_url():
    """obligation_code + hwp_url 있음 → DOWNLOAD AVAILABLE."""
    sb = _pilot_sb_with_url()
    r = get_service_availability(sb, obligation_code="OSH_ACCIDENT_REPORT")

    assert r["DOWNLOAD"]["available"] is True
    assert r["DOWNLOAD"]["status"] == AVAILABLE
    assert r["DOWNLOAD"]["form_code"] == "OSHACT-FORM-030"
    assert r["DOWNLOAD"]["hwp_url"] is not None
    assert r["DOWNLOAD"]["reason"] is None


# ─── T02: DOWNLOAD UNRESOLVED (hwp_url 없음) ─────────────────────────────────

def test_T02_download_unresolved_no_hwp_url():
    """hwp_url = None → DOWNLOAD UNRESOLVED."""
    sb = _pilot_sb_no_url()
    r = get_service_availability(sb, obligation_code="OSH_ACCIDENT_REPORT")

    assert r["DOWNLOAD"]["available"] is False
    assert r["DOWNLOAD"]["status"] == UNRESOLVED
    assert r["DOWNLOAD"]["hwp_url"] is None


# ─── T03: DOWNLOAD UNRESOLVED (매핑 없음) ────────────────────────────────────

def test_T03_download_unresolved_no_mapping():
    """obligation_form_mapping 없음 → DOWNLOAD UNRESOLVED."""
    sb = _no_mapping_sb()
    r = get_service_availability(sb, obligation_code="OB-UNKNOWN")

    assert r["DOWNLOAD"]["available"] is False
    assert r["DOWNLOAD"]["status"] == UNRESOLVED
    assert r["DOWNLOAD"]["form_code"] is None


# ─── T04: atom_id 단독 → MC-001 UNRESOLVED ──────────────────────────────────

def test_T04_atom_id_only_mc001_gap():
    """atom_id만 있고 obligation_code 없음 → 모든 경로 UNRESOLVED, mc001_gap=True."""
    sb = MagicMock()  # 호출되어선 안 됨
    r = get_service_availability(sb, atom_id="uuid-atom-001")

    assert r["mc001_gap"] is True
    assert r["obligation_code"] is None
    assert r["atom_id"] == "uuid-atom-001"
    assert r["overall_status"] == "ALL_UNRESOLVED"
    assert r["DOWNLOAD"]["available"] is False
    assert r["WEB_EDIT"]["available"] is False
    assert r["AUTO"]["available"] is False
    assert "MC-001" in r["DOWNLOAD"]["reason"]
    # atom_id only → DB 조회 없음
    sb.table.assert_not_called()


# ─── T05: 둘 다 없음 → ALL_UNRESOLVED ────────────────────────────────────────

def test_T05_no_identifiers_all_unresolved():
    """obligation_code·atom_id 모두 없음 → ALL_UNRESOLVED, mc001_gap=False."""
    sb = MagicMock()
    r = get_service_availability(sb)

    assert r["overall_status"] == "ALL_UNRESOLVED"
    assert r["mc001_gap"] is False
    assert r["obligation_code"] is None
    assert r["atom_id"] is None
    sb.table.assert_not_called()


# ─── T06: REVIEW_REQUIRED binding → DOWNLOAD·WEB_EDIT 모두 차단 ──────────────

def test_T06_review_required_blocks_all_paths():
    """OSHACT-FORM-002 충돌 → DOWNLOAD REVIEW_REQUIRED, WEB_EDIT REVIEW_REQUIRED."""
    sb = _conflict_sb()
    r = get_service_availability(sb, obligation_code="OB-CONFLICT")

    assert r["DOWNLOAD"]["available"] is False
    assert r["DOWNLOAD"]["status"] == REVIEW_REQUIRED
    assert r["WEB_EDIT"]["available"] is False
    assert r["WEB_EDIT"]["status"] == REVIEW_REQUIRED
    assert r["overall_status"] == "ALL_UNRESOLVED"


# ─── T07: WEB_EDIT READY_FOR_EDIT ────────────────────────────────────────────

@patch("services.doc_m004_service_adapter.resolve_runtime_bridge")
def test_T07_web_edit_ready_for_edit(mock_bridge):
    """WP-L3 READY_FOR_EDIT → WEB_EDIT AVAILABLE."""
    mock_bridge.return_value = {
        "obligation_code": "OB-READY",
        "form_code": "OSHACT-FORM-030",
        "binding_status": "CATALOG_LINKED",
        "reuse_status": "A",
        "doc_id": "doc-001",
        "catalog_document_id": "cat-001",
        "runtime_form_schema_id": "rfs-approved-001",
        "runtime_availability": "READY_FOR_EDIT",
        "field_count": 5,
        "checklist_count": 1,
        "evidence_field_count": 1,
        "law_verified": False,
        "can_create_document": True,
        "review_reason": None,
        "evidence_reference": "form_templates:OSHACT-FORM-030",
    }
    sb = _pilot_sb_with_url()
    r = get_service_availability(sb, obligation_code="OB-READY")

    assert r["WEB_EDIT"]["available"] is True
    assert r["WEB_EDIT"]["status"] == AVAILABLE
    assert r["WEB_EDIT"]["schema_id"] == "rfs-approved-001"


# ─── T08: WEB_EDIT NO_CATALOG_BINDING → UNRESOLVED ───────────────────────────

def test_T08_web_edit_no_catalog_binding():
    """WP-L3 NO_CATALOG_BINDING → WEB_EDIT UNRESOLVED (파일럿 실제 현황)."""
    sb = _pilot_sb_with_url()
    r = get_service_availability(sb, obligation_code="OSH_ACCIDENT_REPORT")

    # 운영 DB rule_doc_mapping=0 → NO_CATALOG_BINDING
    assert r["WEB_EDIT"]["available"] is False
    assert r["WEB_EDIT"]["status"] == UNRESOLVED
    assert r["WEB_EDIT"]["schema_id"] is None


# ─── T09: WEB_EDIT PREPARING ─────────────────────────────────────────────────

@patch("services.doc_m004_service_adapter.resolve_runtime_bridge")
def test_T09_web_edit_preparing(mock_bridge):
    """WP-L3 PREPARING → WEB_EDIT PREPARING (not available)."""
    mock_bridge.return_value = {
        "obligation_code": "OB-CAND",
        "form_code": "OSHACT-FORM-030",
        "binding_status": "CATALOG_LINKED",
        "reuse_status": "B",
        "doc_id": "doc-001",
        "catalog_document_id": "cat-001",
        "runtime_form_schema_id": "rfs-cand-001",
        "runtime_availability": "PREPARING",
        "field_count": 3,
        "checklist_count": 0,
        "evidence_field_count": 0,
        "law_verified": False,
        "can_create_document": False,
        "review_reason": None,
        "evidence_reference": "form_templates:OSHACT-FORM-030",
    }
    sb = _pilot_sb_with_url()
    r = get_service_availability(sb, obligation_code="OB-CAND")

    assert r["WEB_EDIT"]["available"] is False
    assert r["WEB_EDIT"]["status"] == PREPARING


# ─── T10: WEB_EDIT NO_SCHEMA ─────────────────────────────────────────────────

@patch("services.doc_m004_service_adapter.resolve_runtime_bridge")
def test_T10_web_edit_no_schema(mock_bridge):
    """WP-L3 NO_SCHEMA → WEB_EDIT NO_SCHEMA (not available)."""
    mock_bridge.return_value = {
        "obligation_code": "OB-NOSCHEMA",
        "form_code": "OSHACT-FORM-030",
        "binding_status": "CATALOG_LINKED",
        "reuse_status": "C",
        "doc_id": "doc-001",
        "catalog_document_id": "cat-001",
        "runtime_form_schema_id": "UNVERIFIED",
        "runtime_availability": "NO_SCHEMA",
        "field_count": 0,
        "checklist_count": 0,
        "evidence_field_count": 0,
        "law_verified": False,
        "can_create_document": False,
        "review_reason": None,
        "evidence_reference": "document_forms:doc-001",
    }
    sb = _pilot_sb_with_url()
    r = get_service_availability(sb, obligation_code="OB-NOSCHEMA")

    assert r["WEB_EDIT"]["available"] is False
    assert r["WEB_EDIT"]["status"] == NO_SCHEMA


# ─── T11: PARTIAL_AVAILABLE (DOWNLOAD만 가능) ────────────────────────────────

def test_T11_partial_available_download_only():
    """DOWNLOAD AVAILABLE + WEB_EDIT UNRESOLVED → PARTIAL_AVAILABLE."""
    sb = _pilot_sb_with_url()
    r = get_service_availability(sb, obligation_code="OSH_ACCIDENT_REPORT")

    # WP-L1/L2에서 rule_doc_mapping=0 → WEB_EDIT UNRESOLVED
    # form_templates에 hwp_url 있음 → DOWNLOAD AVAILABLE
    assert r["DOWNLOAD"]["available"] is True
    assert r["WEB_EDIT"]["available"] is False
    assert r["overall_status"] == "PARTIAL_AVAILABLE"


# ─── T12: AUTO == WEB_EDIT ───────────────────────────────────────────────────

def test_T12_auto_matches_web_edit():
    """AUTO는 WEB_EDIT과 동일 스키마 기반 — status·available 일치."""
    sb = _pilot_sb_with_url()
    r = get_service_availability(sb, obligation_code="OSH_ACCIDENT_REPORT")

    assert r["AUTO"]["available"] == r["WEB_EDIT"]["available"]
    assert r["AUTO"]["status"] == r["WEB_EDIT"]["status"]
    assert r["AUTO"]["schema_id"] == r["WEB_EDIT"]["schema_id"]


# ─── T13: 필수 계약 컬럼 전체 존재 ──────────────────────────────────────────

def test_T13_contract_columns_present():
    """결과 dict에 필수 계약 컬럼 전체 존재."""
    sb = _pilot_sb_with_url()
    r = get_service_availability(sb, obligation_code="OSH_ACCIDENT_REPORT")

    top_keys = {"obligation_code", "atom_id", "DOWNLOAD", "WEB_EDIT", "AUTO", "overall_status", "mc001_gap"}
    assert top_keys.issubset(r.keys()), f"missing top keys: {top_keys - r.keys()}"

    download_keys = {"available", "form_code", "hwp_url", "status", "reason"}
    assert download_keys.issubset(r["DOWNLOAD"].keys()), f"DOWNLOAD missing: {download_keys - r['DOWNLOAD'].keys()}"

    runtime_keys = {"available", "schema_id", "status", "reason"}
    assert runtime_keys.issubset(r["WEB_EDIT"].keys()), f"WEB_EDIT missing: {runtime_keys - r['WEB_EDIT'].keys()}"
    assert runtime_keys.issubset(r["AUTO"].keys()), f"AUTO missing: {runtime_keys - r['AUTO'].keys()}"


# ─── T14: DB write = 0 ───────────────────────────────────────────────────────

def test_T14_no_db_write():
    """서비스 조회 중 INSERT 미호출 — READ-ONLY."""
    sb = _pilot_sb_with_url()
    get_service_availability(sb, obligation_code="OSH_ACCIDENT_REPORT")
    assert len(sb._insert_calls) == 0, f"INSERT 호출 감지: {sb._insert_calls}"
