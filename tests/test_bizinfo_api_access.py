"""OBJ-BZI-001 Bizinfo API Access unit tests.

WO-TAI-BIZINFO-OBJ-001-API-ACCESS-001.
No real API calls — all tests inject a mock get_fn.

Test IDs:
  F-xx = fetch_source_batch cases

Test categories:
  Normal paths      — F-01 to F-03 (PROGRAM list, EVENT single-dict, provider fields)
  Error paths       — F-04 to F-11 (empty, HTTP auth, JSON auth, invalid JSON,
                                     timeout, HTTP error, size limit, key missing)
  Contract          — F-12 to F-18 (get_fn not called early, key not in batch,
                                     items is tuple, error_code=None on success,
                                     normalizer compatibility, page/size params,
                                     total_count from response)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from services.bizinfo.api_access import (
    ERR_AUTH_FAIL,
    ERR_EMPTY,
    ERR_HTTP_ERROR,
    ERR_INVALID_RESPONSE,
    ERR_KEY_MISSING,
    ERR_SIZE_LIMIT,
    ERR_TIMEOUT,
    SourceBatch,
    fetch_source_batch,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_PROGRAM_KEY = "TEST_PROGRAM_KEY_001"
_FAKE_EVENT_KEY   = "TEST_EVENT_KEY_001"


def _env(monkeypatch, program_key: str = _FAKE_PROGRAM_KEY,
         event_key: str = _FAKE_EVENT_KEY) -> None:
    monkeypatch.setenv("BIZINFO_API_KEY",       program_key)
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", event_key)


def _ok(body: dict):
    """Return a get_fn that yields HTTP 200 with the given JSON body."""
    text = json.dumps(body)
    def _fn(url, *, params=None, timeout=None):
        return 200, text
    return _fn


def _program_body(items: list | dict, total: int = None) -> dict:
    if total is None:
        total = len(items) if isinstance(items, list) else 1
    return {"jsonArray": {"totalCount": str(total), "item": items}}


def _event_body(items: list | dict, total: int = None) -> dict:
    if total is None:
        total = len(items) if isinstance(items, list) else 1
    return {"jsonArray": {"totalCount": str(total), "item": items}}


_PROGRAM_ITEM = {
    "pblancId":       "PBLN_TEST_001",
    "pblancNm":       "산업재해 예방설비 설치비 지원",
    "pblancUrl":      "https://www.bizinfo.go.kr/web/lay1/program/PBLN_TEST_001",
    "jrsdInsttNm":    "고용노동부",
    "excInsttNm":     "한국산업안전보건공단",
    "bsnsSumryCn":    "<p>산업재해 예방을 위한 안전설비 설치를 지원합니다.</p>",
    "trgetNm":        "50인 미만 제조업 사업장",
    "hashtags":       "산업안전,안전설비,재해예방",
    "reqstBeginEndDe": "2026-10-01 ~ 2026-12-31",
}

_EVENT_ITEM = {
    "eventInfoId":    "EVEN_TEST_001",
    "nttNm":          "산업안전보건 교육 행사",
    "bizinfoUrl":     "/portal/event/detail/EVEN_TEST_001",
    "eventBeginEndDe": "20261101~20261130",
    "rceptPd":        "2026-10-01 ~ 2026-10-31",
    "originOrg":      "한국산업안전보건공단",
    "nttCn":          "<p>산업안전보건 교육 행사입니다.</p>",
    "hashtags":       "산업안전,교육",
}


# ---------------------------------------------------------------------------
# Normal paths
# ---------------------------------------------------------------------------


def test_F01_program_normal_list_response(monkeypatch):
    """F-01: PROGRAM API 정상 응답 (item이 리스트) → SourceBatch.error_code=None. [SYNTHETIC]"""
    _env(monkeypatch)
    batch = fetch_source_batch(
        "PROGRAM",
        page=1,
        size=10,
        get_fn=_ok(_program_body([_PROGRAM_ITEM])),
    )
    assert batch.error_code is None
    assert batch.source_kind == "PROGRAM"
    assert batch.provider == "BIZINFO_PROGRAM"
    assert len(batch.items) == 1
    assert batch.items[0]["pblancId"] == "PBLN_TEST_001"
    assert batch.total_count == 1


def test_F02_event_single_dict_item(monkeypatch):
    """F-02: EVENT API item이 리스트가 아닌 dict (단건) → tuple로 정규화. [SYNTHETIC]"""
    _env(monkeypatch)
    batch = fetch_source_batch(
        "EVENT",
        page=1,
        size=10,
        get_fn=_ok(_event_body(_EVENT_ITEM, total=1)),
    )
    assert batch.error_code is None
    assert batch.source_kind == "EVENT"
    assert batch.provider == "BIZINFO_EVENT"
    assert len(batch.items) == 1
    assert batch.items[0]["eventInfoId"] == "EVEN_TEST_001"


def test_F03_provider_fields_set_correctly(monkeypatch):
    """F-03: PROGRAM → provider=BIZINFO_PROGRAM, EVENT → provider=BIZINFO_EVENT. [SYNTHETIC]"""
    _env(monkeypatch)
    for kind, expected_provider in [
        ("PROGRAM", "BIZINFO_PROGRAM"),
        ("EVENT",   "BIZINFO_EVENT"),
    ]:
        body = _program_body([_PROGRAM_ITEM]) if kind == "PROGRAM" else _event_body([_EVENT_ITEM])
        batch = fetch_source_batch(kind, get_fn=_ok(body))
        assert batch.provider == expected_provider


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_F04_empty_response(monkeypatch):
    """F-04: API가 item 없는 빈 응답 반환 → ERR_EMPTY. [SYNTHETIC]"""
    _env(monkeypatch)
    batch = fetch_source_batch(
        "PROGRAM",
        get_fn=_ok({"jsonArray": {"totalCount": "0"}}),
    )
    assert batch.error_code == ERR_EMPTY
    assert batch.items == ()


def test_F05_http_401_auth_fail(monkeypatch):
    """F-05: HTTP 401 → ERR_AUTH_FAIL. [SYNTHETIC]"""
    _env(monkeypatch)
    def _fn(url, *, params=None, timeout=None):
        return 401, "Unauthorized"
    batch = fetch_source_batch("PROGRAM", get_fn=_fn)
    assert batch.error_code == ERR_AUTH_FAIL
    assert batch.items == ()


def test_F06_json_auth_error_marker(monkeypatch):
    """F-06: HTTP 200이지만 returnAuthMsg 포함 → ERR_AUTH_FAIL. [SYNTHETIC]"""
    _env(monkeypatch)
    body = {
        "returnAuthMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
        "errMsg": "SERVICETYPE_OR_SERVICEKEY_ERROR",
    }
    batch = fetch_source_batch("PROGRAM", get_fn=_ok(body))
    assert batch.error_code == ERR_AUTH_FAIL
    assert batch.items == ()


def test_F07_invalid_json_response(monkeypatch):
    """F-07: 응답이 JSON이 아님 → ERR_INVALID_RESPONSE. [SYNTHETIC]"""
    _env(monkeypatch)
    def _fn(url, *, params=None, timeout=None):
        return 200, "<html>서버 오류</html>"
    batch = fetch_source_batch("PROGRAM", get_fn=_fn)
    assert batch.error_code == ERR_INVALID_RESPONSE
    assert batch.items == ()


def test_F08_timeout_exception(monkeypatch):
    """F-08: get_fn이 Timeout 예외 발생 → ERR_TIMEOUT. [SYNTHETIC]"""
    _env(monkeypatch)
    class _FakeTimeout(Exception):
        pass
    def _fn(url, *, params=None, timeout=None):
        raise _FakeTimeout("Connection timed out")
    batch = fetch_source_batch("PROGRAM", get_fn=_fn)
    assert batch.error_code == ERR_TIMEOUT
    assert batch.items == ()


def test_F09_http_500_error(monkeypatch):
    """F-09: HTTP 500 → ERR_HTTP_ERROR. [SYNTHETIC]"""
    _env(monkeypatch)
    def _fn(url, *, params=None, timeout=None):
        return 500, "Internal Server Error"
    batch = fetch_source_batch("PROGRAM", get_fn=_fn)
    assert batch.error_code == ERR_HTTP_ERROR
    assert batch.items == ()


def test_F10_size_exceeds_limit(monkeypatch):
    """F-10: size=101 (MAX_PAGE_SIZE 초과) → ERR_SIZE_LIMIT. [SYNTHETIC]"""
    _env(monkeypatch)
    batch = fetch_source_batch("PROGRAM", size=101, get_fn=_ok({}))
    assert batch.error_code == ERR_SIZE_LIMIT
    assert batch.items == ()


def test_F11_size_zero(monkeypatch):
    """F-11: size=0 → ERR_SIZE_LIMIT. [SYNTHETIC]"""
    _env(monkeypatch)
    batch = fetch_source_batch("PROGRAM", size=0, get_fn=_ok({}))
    assert batch.error_code == ERR_SIZE_LIMIT


def test_F12_key_missing_from_env(monkeypatch):
    """F-12: BIZINFO_API_KEY 환경변수 없음 → ERR_KEY_MISSING. [SYNTHETIC]"""
    monkeypatch.delenv("BIZINFO_API_KEY",       raising=False)
    monkeypatch.delenv("BIZINFO_EVENT_API_KEY", raising=False)
    batch = fetch_source_batch("PROGRAM", get_fn=_ok({}))
    assert batch.error_code == ERR_KEY_MISSING
    assert batch.items == ()


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_F13_get_fn_not_called_on_size_limit(monkeypatch):
    """F-13: size 초과 시 get_fn 호출 없음 — API 키 불필요 경로. [SYNTHETIC]"""
    _env(monkeypatch)
    called = []
    def _fn(url, *, params=None, timeout=None):
        called.append(True)
        return 200, "{}"
    fetch_source_batch("PROGRAM", size=200, get_fn=_fn)
    assert not called, "get_fn must not be called when size limit exceeded"


def test_F14_get_fn_not_called_on_key_missing(monkeypatch):
    """F-14: 키 없을 때 get_fn 호출 없음 — 키 노출 경로 차단. [SYNTHETIC]"""
    monkeypatch.delenv("BIZINFO_API_KEY",       raising=False)
    monkeypatch.delenv("BIZINFO_EVENT_API_KEY", raising=False)
    called = []
    def _fn(url, *, params=None, timeout=None):
        called.append(True)
        return 200, "{}"
    fetch_source_batch("PROGRAM", get_fn=_fn)
    assert not called, "get_fn must not be called when API key is missing"


def test_F15_api_key_not_in_batch_fields(monkeypatch):
    """F-15: 반환된 SourceBatch에 실제 API 키 값 없음 — 키 마스킹 계약. [SYNTHETIC]"""
    _env(monkeypatch)
    batch = fetch_source_batch(
        "PROGRAM",
        get_fn=_ok(_program_body([_PROGRAM_ITEM])),
    )
    batch_repr = repr(batch)
    assert _FAKE_PROGRAM_KEY not in batch_repr
    assert _FAKE_EVENT_KEY not in batch_repr


def test_F16_items_is_tuple(monkeypatch):
    """F-16: SourceBatch.items는 항상 tuple 타입. [SYNTHETIC]"""
    _env(monkeypatch)
    batch = fetch_source_batch(
        "PROGRAM",
        get_fn=_ok(_program_body([_PROGRAM_ITEM])),
    )
    assert isinstance(batch.items, tuple)


def test_F17_error_code_none_on_success(monkeypatch):
    """F-17: 성공 시 error_code=None. [SYNTHETIC]"""
    _env(monkeypatch)
    batch = fetch_source_batch(
        "EVENT",
        get_fn=_ok(_event_body([_EVENT_ITEM])),
    )
    assert batch.error_code is None


def test_F18_total_count_from_response(monkeypatch):
    """F-18: total_count는 API 응답 totalCount 값에서 읽음. [SYNTHETIC]"""
    _env(monkeypatch)
    items = [dict(_PROGRAM_ITEM, pblancId=f"PBLN_{i:03d}") for i in range(5)]
    batch = fetch_source_batch(
        "PROGRAM",
        size=5,
        get_fn=_ok(_program_body(items, total=200)),
    )
    assert batch.total_count == 200
    assert len(batch.items) == 5


def test_F19_page_and_size_in_batch(monkeypatch):
    """F-19: SourceBatch.page / .size가 요청 값과 일치. [SYNTHETIC]"""
    _env(monkeypatch)
    batch = fetch_source_batch(
        "PROGRAM",
        page=3,
        size=20,
        get_fn=_ok(_program_body([_PROGRAM_ITEM], total=100)),
    )
    assert batch.page == 3
    assert batch.size == 20


def test_F20_normalizer_compatible(monkeypatch):
    """F-20: SourceBatch.items 항목을 normalize_bizinfo_record에 직접 전달 가능. [SYNTHETIC]"""
    _env(monkeypatch)
    batch = fetch_source_batch(
        "PROGRAM",
        get_fn=_ok(_program_body([_PROGRAM_ITEM])),
    )
    from services.bizinfo.normalizer import normalize_bizinfo_record
    for item in batch.items:
        result = normalize_bizinfo_record("PROGRAM", item, batch.retrieved_at)
        # Must not raise; returns NormalizedSourceRecord or ParseFailure
        assert result is not None
