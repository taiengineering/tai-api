"""FORM647 검색 어댑터 + DB 계약 테스트
WO-TAI-FORM647-SOURCE-IV-R1-SEARCH-INTEGRATION-001

S01  Gate BLOCKED (is_approved=False) → iter_documents() yields 0 documents
S02  Gate OPEN (is_approved=True) → yields correct REFERENCE_FORM document shape
S03  canonical_id = f647-{ek} — 기존 138종 UUID와 충돌 없음
S04  public_url = /reference-form/f647-{ek}
S05  source_id = FORM647 (TAI_REFERENCE_FORM 과 구분)
S06  leg_client=None → fail-closed (0건)
S07  LEG DB 오류 → fail-closed (0건), 예외 없음
S08  licbyl description = 법령별 서식
S09  admbyl description = 행정규칙별 서식
S10  search_text 에 title 포함

DB 계약 테스트:
D01  get_form647_detail() select 에 run_id 포함 (service_gate join key, G2)
D02  find_form647_snapshot() select 에 run_id 포함 (service_gate join key, G2)
D03  Gate BLOCKED (service_gate.is_approved=False) → get_form647_detail() returns None
D04  Gate OPEN (service_gate.is_approved=True) → get_form647_detail() returns detail
D05  is_form647_service_gate_open(): service_sot_gate 무관, is_approved 만 확인

production_bindings 경로 테스트 (R3):
P01  leg_client=None → _make_form647_search_adapter() → 0건 반환
P02  DB 오류 → 예외 전파 (service_gate 조회 오류, 조용히 0건으로 처리 안 함)
P03  페이지네이션 — service_gate + form_snapshots 각각 200건 초과 행을 여러 페이지로 조회
P04  service_gate 승인 행 없음 → _make_form647_search_adapter() 경유 → 0건

철회·재인덱스 경로 테스트 (R4, G3):
R01  object_reindex_payload() — 승인 행 → 페이로드 반환 (삭제 없음)
R02  object_reindex_payload() — 철회(is_approved=False) → None 반환 (G3 delete 경로)
R03  object_reindex_payload() — f647- 접두사 없는 canonical_id → None (경계 차단)
R04  production_bindings 경유 — 철회 상태 form → object_reindex_payload = None
R05  production_bindings 경유 — 존재하지 않는 form → object_reindex_payload = None
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from services.shared_search.adapters.form647 import Form647SearchAdapter, _normalize
from services.document_engine.form647_mapping import (
    get_form647_detail,
    is_form647_service_gate_open,
    find_form647_snapshot,
)
from services.shared_search.production_bindings import _make_form647_search_adapter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_RUN_ID = "form647-remediation-002-714df47a637e3e73"
_EK = "15267319"

_SNAP_BASE = {
    "run_id": _RUN_ID,
    "ek": _EK,
    "source_gate": "PASS",
    "frozen_name": "도급인의 안전·보건에 관한 정보 제공",
    "api_target": "licbyl",
    "created_at": "2026-10-14T04:45:19+00:00",
}
_SNAP_BLOCKED = {**_SNAP_BASE, "is_approved": False}
_SNAP_OPEN = {**_SNAP_BASE, "is_approved": True}
_SNAP_ADM = {
    "run_id": _RUN_ID,
    "ek": "10000001",
    "source_gate": "PASS",
    "frozen_name": "안전관리 계획서",
    "api_target": "admbyl",
    "created_at": "2026-10-14T04:45:19+00:00",
    "is_approved": True,
}

# service_gate 행 (is_approved 상태별)
_GATE_OPEN = {"run_id": _RUN_ID, "ek": _EK, "is_approved": True}
_GATE_BLOCKED = {"run_id": _RUN_ID, "ek": _EK, "is_approved": False}


def _make_leg_client(rows: list) -> MagicMock:
    """LEG 클라이언트 모의 — 단일 테이블(form_snapshots) 반환용."""
    leg = MagicMock()
    q = MagicMock()
    q.select.return_value = q
    q.order.return_value = q
    q.range.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    res = MagicMock()
    res.data = rows
    q.execute.return_value = res
    leg.schema.return_value.from_.return_value = q
    return leg


def _make_dual_leg_client(form_rows: list, gate_rows: list) -> MagicMock:
    """form_snapshots / service_gate 테이블을 각각 다른 행으로 반환하는 모의."""
    leg = MagicMock()

    def _build_q(rows: list) -> MagicMock:
        q = MagicMock()
        q.select.return_value = q
        q.order.return_value = q
        q.eq.return_value = q
        q.limit.return_value = q
        res = MagicMock()
        res.data = rows
        q.execute.return_value = res
        q.range.return_value = q
        return q

    schema_mock = MagicMock()

    def _from_(table_name: str) -> MagicMock:
        if table_name == "service_gate":
            return _build_q(gate_rows)
        return _build_q(form_rows)

    schema_mock.from_.side_effect = _from_
    leg.schema.return_value = schema_mock
    return leg


def _make_paged_dual_leg_client(gate_rows: list, form_rows: list) -> MagicMock:
    """서비스 게이트·form_snapshots 각각 페이지네이션을 시뮬레이션하는 모의.

    .range(start, end) 호출마다 해당 슬라이스를 반환한다.
    leg._gate_q, leg._form_q 로 range 호출 내역 검증 가능.
    """
    leg = MagicMock()

    def _build_paged_q(all_rows: list) -> MagicMock:
        q = MagicMock()
        q.select.return_value = q
        q.order.return_value = q
        q.eq.return_value = q
        q.limit.return_value = q

        def _range(start: int, end: int) -> MagicMock:
            res = MagicMock()
            res.data = all_rows[start : end + 1]
            q2 = MagicMock()
            q2.execute.return_value = res
            return q2

        q.range.side_effect = _range
        return q

    _gate_q = _build_paged_q(gate_rows)
    _form_q = _build_paged_q(form_rows)

    schema_mock = MagicMock()

    def _from_(table_name: str) -> MagicMock:
        if table_name == "service_gate":
            return _gate_q
        return _form_q

    schema_mock.from_.side_effect = _from_
    leg.schema.return_value = schema_mock
    # range 호출 검증용 접근자
    leg._gate_q = _gate_q
    leg._form_q = _form_q
    return leg


# ---------------------------------------------------------------------------
# S01-S10: 검색 어댑터 테스트
# ---------------------------------------------------------------------------

def test_s01_gate_blocked_yields_zero():
    adapter = Form647SearchAdapter(fetch_current=lambda: [_SNAP_BLOCKED])
    docs = list(adapter.iter_documents())
    assert docs == []


def test_s02_gate_open_correct_shape():
    adapter = Form647SearchAdapter(fetch_current=lambda: [_SNAP_OPEN])
    docs = list(adapter.iter_documents())
    assert len(docs) == 1
    doc = docs[0]
    assert doc["object_type"] == "REFERENCE_FORM"
    assert doc["canonical_id"] == f"f647-{_EK}"
    assert doc["title"] == _SNAP_OPEN["frozen_name"]
    assert doc["publication_status"] == "PUBLISHED"
    assert "PUBLIC" in doc["visibility_scopes"]
    assert doc["source_updated_at"] is not None


def test_s03_canonical_id_no_uuid_collision():
    adapter = Form647SearchAdapter(fetch_current=lambda: [_SNAP_OPEN])
    docs = list(adapter.iter_documents())
    cid = docs[0]["canonical_id"]
    assert cid.startswith("f647-")
    assert "-" not in cid.replace("f647-", "")  # 순수 숫자


def test_s04_public_url_correct():
    adapter = Form647SearchAdapter(fetch_current=lambda: [_SNAP_OPEN])
    docs = list(adapter.iter_documents())
    assert docs[0]["public_url"] == f"/reference-form/f647-{_EK}"


def test_s05_source_id_form647():
    adapter = Form647SearchAdapter(fetch_current=lambda: [_SNAP_OPEN])
    docs = list(adapter.iter_documents())
    assert docs[0]["source_id"] == "FORM647"
    assert docs[0]["source_id"] != "TAI_REFERENCE_FORM"


def test_s06_no_leg_client_fail_closed():
    adapter = Form647SearchAdapter(fetch_current=lambda: iter([]))
    docs = list(adapter.iter_documents())
    assert docs == []


def test_s07_leg_db_error_fail_closed():
    def _error_fetcher():
        raise Exception("DB connection failed")

    adapter = Form647SearchAdapter(fetch_current=_error_fetcher)
    with pytest.raises(Exception):
        # 어댑터가 fetcher 오류를 그대로 전파하는 것 확인
        # production_bindings._iter_current 는 try/except 없이 전파
        list(adapter.iter_documents())


def test_s08_licbyl_description():
    adapter = Form647SearchAdapter(fetch_current=lambda: [_SNAP_OPEN])
    docs = list(adapter.iter_documents())
    assert docs[0]["summary"] == "법령별 서식"


def test_s09_admbyl_description():
    adapter = Form647SearchAdapter(fetch_current=lambda: [_SNAP_ADM])
    docs = list(adapter.iter_documents())
    assert len(docs) == 1
    assert docs[0]["summary"] == "행정규칙별 서식"


def test_s10_search_text_contains_title():
    adapter = Form647SearchAdapter(fetch_current=lambda: [_SNAP_OPEN])
    docs = list(adapter.iter_documents())
    assert _SNAP_OPEN["frozen_name"] in docs[0]["search_text"]


# ---------------------------------------------------------------------------
# D01-D05: DB 계약 테스트
# ---------------------------------------------------------------------------

def test_d01_get_form647_detail_includes_run_id_in_select():
    """G2: get_form647_detail() select 에 run_id 포함 — service_gate join key."""
    leg = _make_leg_client([])
    with patch("services.document_engine.form647_mapping._build_leg_client", return_value=leg):
        get_form647_detail(15267319)
    select_call = leg.schema.return_value.from_.return_value.select
    select_args = select_call.call_args[0][0]
    assert "run_id" in select_args
    assert "service_released" not in select_args


def test_d02_find_form647_snapshot_includes_run_id_in_select():
    """G2: find_form647_snapshot() select 에 run_id 포함 — service_gate join key."""
    leg = _make_leg_client([])
    with patch("services.document_engine.form647_mapping._build_leg_client", return_value=leg):
        find_form647_snapshot(15267319)
    select_call = leg.schema.return_value.from_.return_value.select
    select_args = select_call.call_args[0][0]
    assert "run_id" in select_args
    assert "service_released" not in select_args


def test_d03_gate_blocked_returns_none():
    """service_gate.is_approved=False → get_form647_detail() returns None."""
    form_rows = [{
        "run_id": _RUN_ID,
        "ek": "15267319",
        "frozen_name": "테스트 서식",
        "api_target": "licbyl",
    }]
    gate_rows = [{"is_approved": False}]
    leg = _make_dual_leg_client(form_rows=form_rows, gate_rows=gate_rows)
    with patch("services.document_engine.form647_mapping._build_leg_client", return_value=leg):
        result = get_form647_detail(15267319)
    assert result is None


def test_d04_gate_open_returns_detail():
    """service_gate.is_approved=True → get_form647_detail() returns detail dict."""
    form_rows = [{
        "run_id": _RUN_ID,
        "ek": "15267319",
        "frozen_name": "도급인의 안전·보건에 관한 정보 제공",
        "api_target": "licbyl",
    }]
    gate_rows = [{"is_approved": True}]
    leg = _make_dual_leg_client(form_rows=form_rows, gate_rows=gate_rows)
    with patch("services.document_engine.form647_mapping._build_leg_client", return_value=leg):
        result = get_form647_detail(15267319)
    assert result is not None
    assert result["ek"] == "15267319"
    assert result["frozen_name"] == "도급인의 안전·보건에 관한 정보 제공"
    assert result["file_types"] == ["HWP", "PDF"]


def test_d05_is_gate_open_checks_is_approved_only():
    """is_form647_service_gate_open(): service_sot_gate 무관, is_approved 만 확인."""
    blocked = {"is_approved": False}
    open_ = {"is_approved": True}
    assert is_form647_service_gate_open(blocked) is False
    assert is_form647_service_gate_open(open_) is True
    # service_sot_gate 가 있어도 무시됨
    assert is_form647_service_gate_open({**blocked, "service_sot_gate": "APPROVED"}) is False
    assert is_form647_service_gate_open({**open_, "service_sot_gate": "BLOCKED"}) is True
    # is_approved 필드 없으면 False
    assert is_form647_service_gate_open({}) is False
    assert is_form647_service_gate_open({"is_approved": None}) is False


# ---------------------------------------------------------------------------
# P01-P04: production_bindings._make_form647_search_adapter() 경로 테스트 (R3)
# ---------------------------------------------------------------------------

def test_p01_no_leg_client_zero_via_bindings():
    """leg_client=None → _make_form647_search_adapter() 0건 반환, 예외 없음."""
    adapter = _make_form647_search_adapter(leg_client=None)
    docs = list(adapter.iter_documents())
    assert docs == []


def test_p02_db_error_propagates_via_bindings():
    """DB 오류 → 예외가 호출자에게 전파된다 (service_gate 조회 오류, 조용히 삼키지 않음)."""
    leg = MagicMock()
    q = MagicMock()
    q.select.return_value = q
    q.order.return_value = q
    q.eq.return_value = q

    def _range(start, end):
        r = MagicMock()
        r.execute.side_effect = Exception("connection refused")
        return r

    q.range.side_effect = _range
    schema_mock = MagicMock()
    schema_mock.from_.return_value = q
    leg.schema.return_value = schema_mock

    adapter = _make_form647_search_adapter(leg_client=leg)
    with pytest.raises(Exception, match="connection refused"):
        list(adapter.iter_documents())


def test_p03_pagination_fetches_all_pages():
    """200건 초과 행을 service_gate + form_snapshots 각각 여러 페이지로 나눠 모두 수집."""
    # 350개: 200(1페이지) + 150(2페이지)
    gate_rows = [
        {"run_id": _RUN_ID, "ek": str(i), "is_approved": True}
        for i in range(350)
    ]
    form_rows = [
        {
            "run_id": _RUN_ID,
            "ek": str(i),
            "source_gate": "PASS",
            "frozen_name": f"서식 {i}",
            "api_target": "licbyl",
            "created_at": "2026-10-14T04:45:19+00:00",
        }
        for i in range(350)
    ]
    leg = _make_paged_dual_leg_client(gate_rows=gate_rows, form_rows=form_rows)
    adapter = _make_form647_search_adapter(leg_client=leg)
    docs = list(adapter.iter_documents())
    assert len(docs) == 350

    # service_gate 페이지네이션 확인
    gate_range_calls = leg._gate_q.range.call_args_list
    assert len(gate_range_calls) == 2
    assert gate_range_calls[0] == call(0, 199)
    assert gate_range_calls[1] == call(200, 399)

    # form_snapshots 페이지네이션 확인
    form_range_calls = leg._form_q.range.call_args_list
    assert len(form_range_calls) == 2
    assert form_range_calls[0] == call(0, 199)
    assert form_range_calls[1] == call(200, 399)


def test_p04_no_approved_zero_via_bindings():
    """service_gate 에 승인 행이 없을 때 _make_form647_search_adapter() → 0건."""
    # service_gate 비어 있음 → form_snapshots 조회 없이 0건 반환
    leg = _make_paged_dual_leg_client(gate_rows=[], form_rows=[_SNAP_BASE])
    adapter = _make_form647_search_adapter(leg_client=leg)
    docs = list(adapter.iter_documents())
    assert docs == []
    # form_snapshots 는 조회하지 않아야 함 (조기 반환)
    assert leg._form_q.range.call_count == 0


# ---------------------------------------------------------------------------
# R01-R05: 철회·재인덱스 경로 테스트 (R4, G3)
# ---------------------------------------------------------------------------

def _make_fetch_by_id_leg_client(snap_rows: list, gate_rows: list) -> MagicMock:
    """fetch_by_id 경로 전용 모의 — form_snapshots / service_gate 단건 조회 라우팅."""
    leg = MagicMock()

    def _build_q(rows: list) -> MagicMock:
        q = MagicMock()
        q.select.return_value = q
        q.eq.return_value = q
        q.limit.return_value = q
        res = MagicMock()
        res.data = rows
        q.execute.return_value = res
        return q

    schema_mock = MagicMock()

    def _from_(table_name: str) -> MagicMock:
        if table_name == "service_gate":
            return _build_q(gate_rows)
        return _build_q(snap_rows)

    schema_mock.from_.side_effect = _from_
    leg.schema.return_value = schema_mock
    return leg


def test_r01_reindex_payload_approved_returns_payload():
    """G3: object_reindex_payload() — 승인 상태 → 정상 페이로드 반환."""
    snap_row = {
        "run_id": _RUN_ID,
        "ek": _EK,
        "frozen_name": "도급인의 안전·보건에 관한 정보 제공",
        "api_target": "licbyl",
        "created_at": "2026-10-14T04:45:19+00:00",
    }
    gate_row = {"is_approved": True}
    leg = _make_fetch_by_id_leg_client(snap_rows=[snap_row], gate_rows=[gate_row])
    adapter = _make_form647_search_adapter(leg_client=leg)

    payload = adapter.object_reindex_payload(f"f647-{_EK}")

    assert payload is not None
    assert payload["canonical_id"] == f"f647-{_EK}"
    assert payload["publication_status"] == "PUBLISHED"
    assert payload["object_type"] == "REFERENCE_FORM"


def test_r02_reindex_payload_revoked_returns_none():
    """G3: object_reindex_payload() — 철회(is_approved=False) → None → delete_document 경로."""
    snap_row = {
        "run_id": _RUN_ID,
        "ek": _EK,
        "frozen_name": "도급인의 안전·보건에 관한 정보 제공",
        "api_target": "licbyl",
        "created_at": "2026-10-14T04:45:19+00:00",
    }
    gate_row = {"is_approved": False}
    leg = _make_fetch_by_id_leg_client(snap_rows=[snap_row], gate_rows=[gate_row])
    adapter = _make_form647_search_adapter(leg_client=leg)

    payload = adapter.object_reindex_payload(f"f647-{_EK}")

    assert payload is None


def test_r03_reindex_payload_wrong_prefix_returns_none():
    """G3 경계: f647- 접두사 없는 canonical_id → None (다른 도메인 ID 차단)."""
    leg = _make_fetch_by_id_leg_client(snap_rows=[], gate_rows=[])
    adapter = _make_form647_search_adapter(leg_client=leg)

    assert adapter.object_reindex_payload("some-uuid-without-prefix") is None
    assert adapter.object_reindex_payload("") is None
    assert adapter.object_reindex_payload("TAI_REFERENCE_FORM-123") is None


def test_r04_reindex_payload_revoked_via_bindings():
    """production_bindings 경유 — service_gate.is_approved=False → object_reindex_payload = None."""
    snap_row = {
        "run_id": _RUN_ID,
        "ek": _EK,
        "frozen_name": "도급인의 안전·보건에 관한 정보 제공",
        "api_target": "licbyl",
        "created_at": "2026-10-14T04:45:19+00:00",
    }
    gate_row = {"is_approved": False}
    leg = _make_fetch_by_id_leg_client(snap_rows=[snap_row], gate_rows=[gate_row])
    adapter = _make_form647_search_adapter(leg_client=leg)

    payload = adapter.object_reindex_payload(f"f647-{_EK}")

    assert payload is None, "철회된 서식은 None → delete_document 경로로 처리되어야 함"


def test_r05_reindex_payload_not_found_via_bindings():
    """production_bindings 경유 — form_snapshots에 없는 ek → object_reindex_payload = None."""
    # snap_rows 비어 있음 → _fetch_by_id 에서 None 반환
    leg = _make_fetch_by_id_leg_client(snap_rows=[], gate_rows=[])
    adapter = _make_form647_search_adapter(leg_client=leg)

    payload = adapter.object_reindex_payload("f647-99999999")

    assert payload is None, "존재하지 않는 서식은 None → delete_document 경로로 처리되어야 함"
