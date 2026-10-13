"""WO-TAI-DOC-M004-WP-L3-RUNTIME-BRIDGE-001 — Runtime Bridge 테스트

T01 WP-L2 Binding 결과 정상 수신 (form_code, binding_status 포함)
T02 카탈로그 연결 없음 → NO_CATALOG_BINDING
T03 REVIEW_REQUIRED → Runtime 연결 차단
T04 CANDIDATE 존재 → PREPARING (can_create_document=False)
T05 Schema 없음 → NO_SCHEMA (ValueError 처리)
T06 단일 APPROVED schema + 유효 필드 → READY_FOR_EDIT 계약
T07 기존 catalog_resolver 재사용 확인 (mock call 검증)
T08 법령 미검증 상태가 VERIFIED 처리되지 않음 (law_verified=False)
T09 DB/Storage write 0, 문서 생성 호출 0

Production DB write = 0 (mock + patch 전용).
파일럿 A: OSH_ACCIDENT_REPORT → NO_CATALOG_BINDING (rule_doc_mapping=0)
파일럿 B: CANDIDATE 독립 조회 → PREPARING (법령 연결 귀속 없음)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.doc_m004_runtime_bridge import (
    resolve_runtime_bridge,
    resolve_catalog_bridge,
)
from services.doc_m004_binding_adapter import (
    CATALOG_LINKED,
    REVIEW_REQUIRED,
    VERIFIED,
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
    "id": "ft-030", "form_code": "OSHACT-FORM-030",
    "form_name": "중대재해 발생 보고서", "law_code": "OSHACT",
    "bylseq": "17853759", "is_active": True,
}

FT_002 = {
    "id": "ft-002", "form_code": "OSHACT-FORM-002",
    "form_name": "안전보건교육 기록서", "law_code": "OSHACT",
    "bylseq": "BYL-002", "is_active": True,
}

# catalog_resolver 표준 반환 예시
CATALOG_PREPARING = {
    "availability":         "PREPARING",
    "active_schema_id":     None,
    "candidate_schema_id":  "rfs-cand-001",
    "active_schema_status": None,
    "candidate_schema_status": "CANDIDATE",
    "schema":               None,
    "fields":               [{"id": "f1"}, {"id": "f2"}, {"id": "f3"}],
    "checklists":           [{"id": "c1"}],
    "evidence_fields":      [],
}

CATALOG_READY = {
    "availability":         "READY_FOR_EDIT",
    "active_schema_id":     "rfs-approved-001",
    "candidate_schema_id":  None,
    "active_schema_status": "APPROVED_FOR_RUNTIME_USE",
    "candidate_schema_status": None,
    "schema":               {"id": "rfs-approved-001", "status": "APPROVED_FOR_RUNTIME_USE"},
    "fields":               [{"id": f"f{i}"} for i in range(8)],
    "checklists":           [{"id": "c1"}, {"id": "c2"}],
    "evidence_fields":      [{"id": "ev1"}],
}

CATALOG_NO_SCHEMA = {
    "availability":         "NO_SCHEMA",
    "active_schema_id":     None,
    "candidate_schema_id":  None,
    "schema":               None,
    "fields":               [],
    "checklists":           [],
    "evidence_fields":      [],
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


def _conflict_sb() -> MagicMock:
    """OSHACT-FORM-002 충돌 이력 → REVIEW_REQUIRED mock."""
    return _sb({
        "obligation_form_mapping": [{"form_code": "OSHACT-FORM-002"}],
        "form_templates":          [FT_002],
        "rule_doc_mapping":        [],
        "document_forms":          [],
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })


# ─── T01: WP-L2 Binding 결과 정상 수신 ───────────────────────────────────────

def test_T01_wpl2_binding_received():
    """resolve_runtime_bridge 결과에 WP-L2 binding 정보 포함."""
    sb = _pilot_sb()
    r = resolve_runtime_bridge(sb, "OSH_ACCIDENT_REPORT")

    assert r["obligation_code"] == "OSH_ACCIDENT_REPORT"
    assert r["form_code"] == "OSHACT-FORM-030"
    assert r["binding_status"] == CATALOG_LINKED
    assert r["reuse_status"] == "B"
    # 필수 계약 컬럼 전체 존재 확인
    required = {
        "obligation_code", "form_code", "binding_status", "reuse_status",
        "doc_id", "catalog_document_id", "runtime_form_schema_id",
        "runtime_availability", "field_count", "checklist_count",
        "evidence_field_count", "law_verified", "can_create_document",
        "review_reason", "evidence_reference",
    }
    assert required.issubset(r.keys()), f"missing: {required - r.keys()}"


# ─── T02: 카탈로그 연결 없음 → NO_CATALOG_BINDING ─────────────────────────────

def test_T02_no_catalog_binding():
    """catalog_document_id=UNVERIFIED → NO_CATALOG_BINDING (파일럿 A)."""
    sb = _pilot_sb()
    r = resolve_runtime_bridge(sb, "OSH_ACCIDENT_REPORT")

    assert r["runtime_availability"] == "NO_CATALOG_BINDING"
    assert r["catalog_document_id"] == UNVERIFIED
    assert r["can_create_document"] is False


# ─── T03: REVIEW_REQUIRED → Runtime 연결 차단 ────────────────────────────────

def test_T03_review_required_blocks_runtime():
    """binding_status=REVIEW_REQUIRED → runtime_availability=REVIEW_REQUIRED."""
    sb = _conflict_sb()  # OSHACT-FORM-002 → 알려진 법령 충돌 → REVIEW_REQUIRED
    r = resolve_runtime_bridge(sb, "OB-CONFLICT")

    assert r["binding_status"] == REVIEW_REQUIRED
    assert r["runtime_availability"] == "REVIEW_REQUIRED"
    assert r["can_create_document"] is False


# ─── T04: CANDIDATE 존재 → PREPARING (파일럿 B) ───────────────────────────────

@patch("services.doc_m004_runtime_bridge.resolve_catalog_runtime_schema")
def test_T04_candidate_schema_preparing(mock_resolver):
    """catalog_document_id 유효 + CANDIDATE schema → PREPARING.
    이 조회는 특정 법령 의무에 연결됐다고 주장하지 않는다."""
    mock_resolver.return_value = CATALOG_PREPARING

    r = resolve_catalog_bridge("df-uuid-candidate-001")

    assert r["runtime_availability"] == "PREPARING"
    assert r["can_create_document"] is False
    assert r["field_count"] == 3
    assert r["checklist_count"] == 1
    assert r["evidence_field_count"] == 0
    assert r["runtime_form_schema_id"] == "rfs-cand-001"
    # 카탈로그 독립 조회 → 법령 연결 없음
    assert r["binding_status"] == UNVERIFIED
    assert r["obligation_code"] is None


# ─── T05: Schema 없음 → NO_SCHEMA ────────────────────────────────────────────

@patch("services.doc_m004_runtime_bridge.resolve_catalog_runtime_schema")
def test_T05_no_schema(mock_resolver):
    """resolve_catalog_runtime_schema가 ValueError → NO_SCHEMA."""
    mock_resolver.side_effect = ValueError("catalog document not found: df-missing")

    r = resolve_catalog_bridge("df-missing")

    assert r["runtime_availability"] == "NO_SCHEMA"
    assert r["can_create_document"] is False
    assert r["field_count"] == 0


# ─── T06: READY_FOR_EDIT 계약 ─────────────────────────────────────────────────

@patch("services.doc_m004_runtime_bridge.resolve_catalog_runtime_schema")
def test_T06_ready_for_edit_contract(mock_resolver):
    """단일 APPROVED schema + 유효 필드 → READY_FOR_EDIT 계약."""
    mock_resolver.return_value = CATALOG_READY

    r = resolve_catalog_bridge("df-uuid-approved-001")

    assert r["runtime_availability"] == "READY_FOR_EDIT"
    assert r["can_create_document"] is True
    assert r["runtime_form_schema_id"] == "rfs-approved-001"
    assert r["field_count"] == 8
    assert r["checklist_count"] == 2
    assert r["evidence_field_count"] == 1
    # 카탈로그 독립 조회 → law_verified=False (법령 연결 없음)
    assert r["law_verified"] is False


# ─── T07: 기존 catalog_resolver 재사용 확인 ──────────────────────────────────

@patch("services.doc_m004_runtime_bridge.resolve_catalog_runtime_schema")
def test_T07_catalog_resolver_reused(mock_resolver):
    """유효한 catalog_document_id → 기존 resolve_catalog_runtime_schema 호출."""
    mock_resolver.return_value = CATALOG_PREPARING

    resolve_catalog_bridge("df-uuid-test-001")

    mock_resolver.assert_called_once_with("df-uuid-test-001")


# ─── T08: 법령 미검증 → law_verified=False ───────────────────────────────────

def test_T08_law_not_verified_when_catalog_linked():
    """binding_status=CATALOG_LINKED → law_verified=False (공식 증거 없음)."""
    sb = _pilot_sb()
    r = resolve_runtime_bridge(sb, "OSH_ACCIDENT_REPORT")

    assert r["binding_status"] == CATALOG_LINKED
    assert r["law_verified"] is False
    # CATALOG_LINKED를 VERIFIED로 임의 처리하지 않음
    assert r["binding_status"] != VERIFIED


# ─── T09: DB write 0, 문서 생성 호출 0 ───────────────────────────────────────

def test_T09_no_db_write_no_create():
    """Bridge 호출 중 insert 미호출, can_create_document=False."""
    sb = _pilot_sb()
    r = resolve_runtime_bridge(sb, "OSH_ACCIDENT_REPORT")

    assert len(sb._insert_calls) == 0, f"insert 호출 감지: {sb._insert_calls}"
    # WP-L3는 작성 활성화 단계 아님 — NO_CATALOG_BINDING이므로 False
    assert r["can_create_document"] is False
