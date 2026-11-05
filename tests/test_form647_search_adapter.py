"""FORM647 검색 어댑터 + DB 계약 테스트
WO-TAI-FORM647-SOURCE-IV-R1-SEARCH-INTEGRATION-001

S01  Gate BLOCKED → iter_documents() yields 0 documents
S02  Gate OPEN (mocked) → yields correct REFERENCE_FORM document shape
S03  canonical_id = f647-{ek} — 기존 138종 UUID와 충돌 없음
S04  public_url = /reference-form/f647-{ek}
S05  source_id = FORM647 (TAI_REFERENCE_FORM 과 구분)
S06  leg_client=None → fail-closed (0건)
S07  LEG DB 오류 → fail-closed (0건), 예외 없음
S08  licbyl description = 법령별 서식
S09  admbyl description = 행정규칙별 서식
S10  search_text 에 title 포함

DB 계약 테스트:
D01  get_form647_detail() select 에 service_released 없음
D02  find_form647_snapshot() select 에 service_released 없음
D03  Gate BLOCKED (service_sot_gate='BLOCKED') → get_form647_detail() returns None
D04  Gate OPEN (service_sot_gate='APPROVED') → get_form647_detail() returns detail
D05  is_form647_service_gate_open(): service_released 무관, service_sot_gate 만 확인

production_bindings 경로 테스트 (R2):
P01  leg_client=None → _make_form647_search_adapter() → 0건 반환
P02  DB 오류 → 예외 전파 (조용히 0건으로 처리 안 함)
P03  페이지네이션 — 200건 초과 행을 여러 페이지로 조회
P04  Gate BLOCKED 행 → _make_form647_search_adapter() 경유 → 0건
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

_EK = "15267319"
_SNAP_BLOCKED = {
    "ek": _EK,
    "service_sot_gate": "BLOCKED",
    "frozen_name": "도급인의 안전·보건에 관한 정보 제공",
    "api_target": "licbyl",
    "created_at": "2026-10-14T04:45:19+00:00",
}
_SNAP_OPEN = {**_SNAP_BLOCKED, "service_sot_gate": "APPROVED"}
_SNAP_ADM = {
    "ek": "10000001",
    "service_sot_gate": "APPROVED",
    "frozen_name": "안전관리 계획서",
    "api_target": "admbyl",
    "created_at": "2026-10-14T04:45:19+00:00",
}


def _make_leg_client(rows: list) -> MagicMock:
    """LEG 클라이언트 모의 — form647_review.form_snapshots 반환."""
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
    # f647- prefix 확인 — UUID 형식 아님
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
    # 기존 TAI_REFERENCE_FORM 과 다름
    assert docs[0]["source_id"] != "TAI_REFERENCE_FORM"


def test_s06_no_leg_client_fail_closed():
    # _iter_current 가 아무것도 반환 안 하는 경우 (None leg_client)
    adapter = Form647SearchAdapter(fetch_current=lambda: iter([]))
    docs = list(adapter.iter_documents())
    assert docs == []


def test_s07_leg_db_error_fail_closed():
    def _error_fetcher():
        raise Exception("DB connection failed")

    adapter = Form647SearchAdapter(fetch_current=_error_fetcher)
    with pytest.raises(Exception):
        # 어댑터가 fetcher 오류를 그대로 전파하는 것 확인
        # production_bindings._iter_current 는 try/except 로 감쌈
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

def test_d01_get_form647_detail_no_service_released_in_select():
    """get_form647_detail() 이 form_snapshots.service_released 를 select 하지 않는다."""
    leg = _make_leg_client([])
    with patch("services.document_engine.form647_mapping._build_leg_client", return_value=leg):
        get_form647_detail(15267319)
    # schema("form647_review").from_("form_snapshots").select(...) 호출 확인
    select_call = leg.schema.return_value.from_.return_value.select
    select_args = select_call.call_args[0][0]
    assert "service_released" not in select_args


def test_d02_find_form647_snapshot_no_service_released_in_select():
    """find_form647_snapshot() 이 form_snapshots.service_released 를 select 하지 않는다."""
    leg = _make_leg_client([])
    with patch("services.document_engine.form647_mapping._build_leg_client", return_value=leg):
        find_form647_snapshot(15267319)
    select_call = leg.schema.return_value.from_.return_value.select
    select_args = select_call.call_args[0][0]
    assert "service_released" not in select_args


def test_d03_gate_blocked_returns_none():
    """service_sot_gate='BLOCKED' → get_form647_detail() returns None."""
    leg = _make_leg_client([{
        "ek": "15267319",
        "service_sot_gate": "BLOCKED",
        "frozen_name": "테스트 서식",
        "api_target": "licbyl",
    }])
    with patch("services.document_engine.form647_mapping._build_leg_client", return_value=leg):
        result = get_form647_detail(15267319)
    assert result is None


def test_d04_gate_open_returns_detail():
    """service_sot_gate='APPROVED' → get_form647_detail() returns detail dict."""
    leg = _make_leg_client([{
        "ek": "15267319",
        "service_sot_gate": "APPROVED",
        "frozen_name": "도급인의 안전·보건에 관한 정보 제공",
        "api_target": "licbyl",
    }])
    with patch("services.document_engine.form647_mapping._build_leg_client", return_value=leg):
        result = get_form647_detail(15267319)
    assert result is not None
    assert result["ek"] == "15267319"
    assert result["frozen_name"] == "도급인의 안전·보건에 관한 정보 제공"
    assert result["file_types"] == ["HWP", "PDF"]


def test_d05_is_gate_open_ignores_service_released():
    """is_form647_service_gate_open(): service_released 없이 service_sot_gate 만 확인."""
    blocked = {"service_sot_gate": "BLOCKED"}
    open_ = {"service_sot_gate": "APPROVED"}
    # service_released 필드 없이도 정상 동작
    assert is_form647_service_gate_open(blocked) is False
    assert is_form647_service_gate_open(open_) is True
    # service_released 가 있어도 무시됨
    assert is_form647_service_gate_open({**blocked, "service_released": True}) is False
    assert is_form647_service_gate_open({**open_, "service_released": False}) is True


# ---------------------------------------------------------------------------
# P01-P04: production_bindings._make_form647_search_adapter() 경로 테스트 (R2)
# ---------------------------------------------------------------------------

def _make_paged_leg_client(all_rows: list, page_size: int = 200) -> MagicMock:
    """페이지네이션을 시뮬레이션하는 LEG 클라이언트 모의.

    .range(start, end) 호출마다 해당 슬라이스를 반환한다.
    """
    leg = MagicMock()

    def _build_q():
        q = MagicMock()
        q.select.return_value = q
        q.order.return_value = q
        q.eq.return_value = q
        q.limit.return_value = q

        # range 호출 시 슬라이스된 데이터 반환
        def _range(start, end):
            res = MagicMock()
            res.data = all_rows[start : end + 1]
            q2 = MagicMock()
            q2.execute.return_value = res
            return q2

        q.range.side_effect = _range
        return q

    leg.schema.return_value.from_.return_value = _build_q()
    return leg


def test_p01_no_leg_client_zero_via_bindings():
    """leg_client=None → _make_form647_search_adapter() 0건 반환, 예외 없음."""
    adapter = _make_form647_search_adapter(leg_client=None)
    docs = list(adapter.iter_documents())
    assert docs == []


def test_p02_db_error_propagates_via_bindings():
    """DB 오류 → 예외가 호출자에게 전파된다 (조용히 0건으로 삼키지 않음)."""
    leg = MagicMock()
    q = MagicMock()
    q.select.return_value = q
    q.order.return_value = q
    q.range.return_value = q
    q.range.return_value.execute.side_effect = Exception("connection refused")
    leg.schema.return_value.from_.return_value = q

    adapter = _make_form647_search_adapter(leg_client=leg)
    with pytest.raises(Exception, match="connection refused"):
        list(adapter.iter_documents())


def test_p03_pagination_fetches_all_pages():
    """200건 초과 행을 여러 페이지로 나눠 모두 수집한다."""
    # 350개 행: 200 + 150 (2페이지)
    rows = [
        {
            "ek": str(i),
            "service_sot_gate": "APPROVED",
            "frozen_name": f"서식 {i}",
            "api_target": "licbyl",
            "created_at": "2026-10-14T04:45:19+00:00",
        }
        for i in range(350)
    ]
    leg = _make_paged_leg_client(rows)
    adapter = _make_form647_search_adapter(leg_client=leg)
    docs = list(adapter.iter_documents())
    assert len(docs) == 350
    # 두 번째 페이지 range 호출 확인 (offset=200)
    range_calls = leg.schema.return_value.from_.return_value.range.call_args_list
    assert len(range_calls) == 2
    assert range_calls[0] == call(0, 199)
    assert range_calls[1] == call(200, 399)


def test_p04_gate_blocked_zero_via_bindings():
    """Gate BLOCKED 행만 있을 때 _make_form647_search_adapter() 경유 → 0건."""
    leg = MagicMock()
    q = MagicMock()
    q.select.return_value = q
    q.order.return_value = q

    def _range(start, end):
        res = MagicMock()
        # 첫 페이지만 BLOCKED 행 반환, 이후 빈 페이지
        res.data = [_SNAP_BLOCKED] if start == 0 else []
        r = MagicMock()
        r.execute.return_value = res
        return r

    q.range.side_effect = _range
    leg.schema.return_value.from_.return_value = q

    adapter = _make_form647_search_adapter(leg_client=leg)
    docs = list(adapter.iter_documents())
    assert docs == []
