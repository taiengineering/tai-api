"""WAVE 2 KOSHA Smart Search provider — A1–A12."""
from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.kosha_smart_search import (
    DATASET_ID,
    DEFAULT_CATEGORY,
    MATCH_TYPE,
    PROVIDER,
    SOURCE_HOST,
    SOURCE_PATH,
    SmartSearchQueryError,
    normalize_item,
    normalize_query,
    response_contains_secret,
)
import services.kosha_smart_search as kss
import routers.kosha_apis as kosha_apis

SECRET = "TEST_SECRET_KEY_DO_NOT_LEAK"
PUBLIC = "/public/safety-search/kosha"


def _ok_payload(items, total=None, result_code="00"):
    if total is None:
        total = len(items)
    return {
        "header": {"resultCode": result_code, "resultMsg": "NORMAL_CODE"},
        "body": {
            "pageNo": "1",
            "numOfRows": str(len(items) or 2),
            "totalCount": str(total),
            "dataType": "JSON",
            "items": {"item": items},
        },
    }


def _item(**overrides):
    row = {
        "doc_id": "DOC-1",
        "title": "지게차 안전기준",
        "content": "지게차 작업 시 준수사항",
        "category": "1",
        "score": 99.1,
        "highlight_content": "<em>지게차</em>",
        "filepath": "/internal/files/a.pdf",
        "keyword": "지게차",
    }
    row.update(overrides)
    return row


def _client():
    from routers.public_safety_search import router as public_router

    app = FastAPI()
    app.include_router(public_router)
    app.include_router(kosha_apis.router)
    return TestClient(app)


def _patch_key(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", SECRET)
    monkeypatch.delenv("KOSHA_SERVICE_KEY", raising=False)
    monkeypatch.delenv("BUILDING_API_KEY", raising=False)


def _capture(monkeypatch, handler):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=25):
        calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        return handler(url, params, timeout)

    monkeypatch.setattr(kss, "kr_get", fake_get)
    return calls


def test_official_source_constants():
    assert DATASET_ID == "15123696"
    assert SOURCE_PATH == "srch/smartSearch"
    assert SOURCE_HOST == "https://apis.data.go.kr/B552468"
    assert DEFAULT_CATEGORY == "0"
    assert PROVIDER == "KOSHA"
    assert MATCH_TYPE == "SOURCE_SEARCH"


def test_a1_valid_q_normalized_results(monkeypatch):
    _patch_key(monkeypatch)

    def handler(url, params, timeout):
        assert url == f"{SOURCE_HOST}/{SOURCE_PATH}"
        assert params["searchValue"] == "지게차"
        assert params["pageNo"] == "1"
        assert params["numOfRows"] == "10"
        assert params["category"] == "0"
        assert params["serviceKey"] == SECRET
        assert "keyword" not in params
        assert "company" not in params
        payload = _ok_payload([_item()], total=17)
        return 200, json.dumps(payload, ensure_ascii=False)

    calls = _capture(monkeypatch, handler)
    res = _client().get(PUBLIC, params={"q": "지게차", "page": 1, "page_size": 10})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["provider"] == "KOSHA"
    assert body["query"] == "지게차"
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert body["total"] == 17
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["external_id"] == "DOC-1"
    assert item["title"] == "지게차 안전기준"
    assert item["summary"] == "지게차 작업 시 준수사항"
    assert item["source_name"] == "KOSHA"
    assert item["source_url"] is None
    assert item["original_url"] is None
    assert item["published_at"] is None
    assert item["category"] == "1"
    assert item["source_type"] is None
    assert item["match_type"] == "SOURCE_SEARCH"
    assert "score" not in item
    assert "provider_error" not in body
    assert len(calls) == 1
    assert SECRET not in json.dumps(body, ensure_ascii=False)


def test_a2_blank_q_rejects_without_external_call(monkeypatch):
    _patch_key(monkeypatch)
    calls = _capture(monkeypatch, lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    client = _client()
    for params in ({"q": ""}, {"q": "   "}, {}):
        res = client.get(PUBLIC, params=params)
        assert res.status_code == 422, params
    assert calls == []
    with pytest.raises(SmartSearchQueryError) as err:
        normalize_query("  ", 1, 10)
    assert err.value.code == "QUERY_EMPTY"


def test_a3_page_bounds(monkeypatch):
    _patch_key(monkeypatch)
    calls = _capture(monkeypatch, lambda *a, **k: (200, json.dumps(_ok_payload([]))))
    client = _client()
    assert client.get(PUBLIC, params={"q": "지게차", "page": 0}).status_code == 422
    assert client.get(PUBLIC, params={"q": "지게차", "page": -1}).status_code == 422
    assert calls == []
    with pytest.raises(SmartSearchQueryError) as err:
        normalize_query("지게차", 0, 10)
    assert err.value.code == "PAGE_INVALID"


def test_a4_page_size_bounds(monkeypatch):
    _patch_key(monkeypatch)
    calls = _capture(monkeypatch, lambda *a, **k: (200, json.dumps(_ok_payload([]))))
    client = _client()
    assert client.get(PUBLIC, params={"q": "지게차", "page_size": 0}).status_code == 422
    assert client.get(PUBLIC, params={"q": "지게차", "page_size": 51}).status_code == 422
    assert calls == []
    with pytest.raises(SmartSearchQueryError) as err:
        normalize_query("지게차", 1, 51)
    assert err.value.code == "PAGE_SIZE_INVALID"


def test_a5_official_no_result_ok_empty(monkeypatch):
    _patch_key(monkeypatch)
    payload = _ok_payload([], total=0, result_code="00")
    _capture(monkeypatch, lambda *a, **k: (200, json.dumps(payload)))
    res = _client().get(PUBLIC, params={"q": "없는검색어xyz"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["items"] == []
    assert body["total"] == 0


def test_a5_nodata_result_code_unavailable(monkeypatch):
    _patch_key(monkeypatch)
    payload = _ok_payload([], total=0, result_code="03")
    _capture(monkeypatch, lambda *a, **k: (200, json.dumps(payload)))
    res = _client().get(PUBLIC, params={"q": "없는검색어xyz"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "unavailable"
    assert body["items"] == []
    assert body["provider_error"] == "upstream_error"


def test_a6_timeout_normalized_unavailable(monkeypatch):
    _patch_key(monkeypatch)

    def handler(*a, **k):
        raise TimeoutError("timed out")

    _capture(monkeypatch, handler)
    res = _client().get(PUBLIC, params={"q": "지게차"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "unavailable"
    assert body["items"] == []
    assert body["provider_error"] == "timeout"
    assert SECRET not in json.dumps(body)


def test_a7_429_normalized_unavailable(monkeypatch):
    _patch_key(monkeypatch)
    _capture(monkeypatch, lambda *a, **k: (429, "slow down"))
    body = _client().get(PUBLIC, params={"q": "지게차"}).json()
    assert body["status"] == "unavailable"
    assert body["items"] == []
    assert body["provider_error"] == "rate_limited"


def test_a8_5xx_normalized_unavailable(monkeypatch):
    _patch_key(monkeypatch)
    _capture(monkeypatch, lambda *a, **k: (502, "bad gateway"))
    res = _client().get(PUBLIC, params={"q": "지게차"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "unavailable"
    assert body["provider_error"] == "upstream_http"
    assert "bad gateway" not in json.dumps(body)


def test_a9_schema_mismatch_unavailable(monkeypatch):
    _patch_key(monkeypatch)
    _capture(monkeypatch, lambda *a, **k: (200, '{"not":"kosha"}'))
    body = _client().get(PUBLIC, params={"q": "지게차"}).json()
    assert body["status"] == "unavailable"
    assert body["items"] == []
    assert body["provider_error"] == "schema_error"


def test_a9_items_wrong_type_unavailable(monkeypatch):
    _patch_key(monkeypatch)
    payload = {
        "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
        "body": {"totalCount": "1", "items": "oops"},
    }
    _capture(monkeypatch, lambda *a, **k: (200, json.dumps(payload)))
    body = _client().get(PUBLIC, params={"q": "지게차"}).json()
    assert body["status"] == "unavailable"
    assert body["provider_error"] == "schema_error"


def test_success_total_count_missing_schema_error(monkeypatch):
    _patch_key(monkeypatch)
    payload = {
        "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
        "body": {"items": {"item": []}},
    }
    _capture(monkeypatch, lambda *a, **k: (200, json.dumps(payload)))
    res = _client().get(PUBLIC, params={"q": "지게차"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "unavailable"
    assert body["items"] == []
    assert body["provider_error"] == "schema_error"


def test_success_total_count_malformed_schema_error(monkeypatch):
    _patch_key(monkeypatch)
    payload = {
        "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
        "body": {"totalCount": "broken", "items": {"item": []}},
    }
    _capture(monkeypatch, lambda *a, **k: (200, json.dumps(payload)))
    res = _client().get(PUBLIC, params={"q": "지게차"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "unavailable"
    assert body["items"] == []
    assert body["provider_error"] == "schema_error"


def test_success_total_positive_items_missing_schema_error(monkeypatch):
    _patch_key(monkeypatch)
    payload = {
        "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
        "body": {"totalCount": 5},
    }
    _capture(monkeypatch, lambda *a, **k: (200, json.dumps(payload)))
    res = _client().get(PUBLIC, params={"q": "지게차"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "unavailable"
    assert body["items"] == []
    assert body["provider_error"] == "schema_error"


def test_success_wrong_item_schema_schema_error(monkeypatch):
    _patch_key(monkeypatch)
    payload = {
        "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
        "body": {
            "totalCount": 1,
            "items": {"item": [{"lawNm": "산안법", "url": "https://example.invalid"}]},
        },
    }
    _capture(monkeypatch, lambda *a, **k: (200, json.dumps(payload)))
    res = _client().get(PUBLIC, params={"q": "지게차"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "unavailable"
    assert body["items"] == []
    assert body["provider_error"] == "schema_error"


def test_success_core_fields_present_null_values_ok(monkeypatch):
    _patch_key(monkeypatch)
    payload = {
        "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
        "body": {
            "totalCount": 1,
            "items": {
                "item": [{
                    "doc_id": None,
                    "title": "",
                    "content": None,
                    "category": "",
                }]
            },
        },
    }
    _capture(monkeypatch, lambda *a, **k: (200, json.dumps(payload)))
    res = _client().get(PUBLIC, params={"q": "지게차"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert len(body["items"]) == 1
    assert body["items"][0]["external_id"] is None
    assert body["items"][0]["title"] is None
    assert body["items"][0]["summary"] is None
    assert body["items"][0]["category"] is None


def test_a10_service_key_not_in_response_or_logs(monkeypatch, caplog):
    _patch_key(monkeypatch)
    caplog.set_level(logging.DEBUG)
    payload = _ok_payload([_item(title=f"title {SECRET}")])
    _capture(monkeypatch, lambda *a, **k: (200, json.dumps(payload, ensure_ascii=False)))
    res = _client().get(PUBLIC, params={"q": "지게차"})
    body = res.json()
    dumped = json.dumps(body, ensure_ascii=False)
    assert SECRET not in dumped
    assert not response_contains_secret(body, SECRET)
    assert body["items"][0]["title"] == "title [REDACTED]"
    assert SECRET not in caplog.text
    _capture(monkeypatch, lambda *a, **k: (_ for _ in ()).throw(TimeoutError("timeout")))
    fail = _client().get(PUBLIC, params={"q": "지게차"}).json()
    assert SECRET not in json.dumps(fail)
    assert SECRET not in caplog.text


def test_a11_unknown_fields_null_no_inference():
    raw = {"title": "제목만 있음", "score": 12.3, "mystery": "nope"}
    item = normalize_item(raw, SECRET)
    assert item == {
        "external_id": None,
        "title": "제목만 있음",
        "summary": None,
        "source_name": "KOSHA",
        "source_url": None,
        "original_url": None,
        "published_at": None,
        "category": None,
        "source_type": None,
        "match_type": "SOURCE_SEARCH",
    }
    assert "score" not in item
    assert "mystery" not in item
    assert "legal" not in json.dumps(item).lower()
    assert "applicab" not in json.dumps(item).lower()


def test_upstream_result_code_42_unavailable(monkeypatch):
    _patch_key(monkeypatch)
    payload = {
        "header": {"resultCode": "42", "resultMsg": "UNKNOWN_ERROR(null)"},
        "body": {"msg": "error", "result": "error", "totalCount": 0, "items": {"item": []}},
    }
    _capture(monkeypatch, lambda *a, **k: (200, json.dumps(payload)))
    res = _client().get(PUBLIC, params={"q": "지게차"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "unavailable"
    assert body["items"] == []
    assert body["provider_error"] == "upstream_error"
    assert "UNKNOWN_ERROR" not in json.dumps(body)
    assert "NoneType" not in json.dumps(body)


def test_a12_legacy_law_search_shape(monkeypatch):
    _patch_key(monkeypatch)
    payload = _ok_payload([_item()], total=4)

    def handler(url, params, timeout):
        assert params["searchValue"] == "지게차"
        assert params["category"] == "0"
        assert "keyword" not in params
        return 200, json.dumps(payload, ensure_ascii=False)

    _capture(monkeypatch, handler)
    res = _client().get("/kosha/law-search", params={"keyword": "지게차", "page_no": 1, "num_of_rows": 10})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert "data" in body
    assert body["data"]["header"]["resultCode"] == "00"
    assert body["data"]["body"]["totalCount"] == "4"


def test_context_params_are_not_forwarded(monkeypatch):
    _patch_key(monkeypatch)
    calls = _capture(monkeypatch, lambda *a, **k: (200, json.dumps(_ok_payload([]))))
    res = _client().get(
        PUBLIC,
        params={
            "q": "지게차",
            "company": "acme",
            "factory": "1",
            "user_id": "u1",
            "diagnosis": "d1",
            "equipment": "fork",
            "process": "p",
            "task": "t",
        },
    )
    assert res.status_code == 200
    sent = calls[0]["params"]
    for blocked in ("company", "factory", "user_id", "diagnosis", "equipment", "process", "task", "keyword"):
        assert blocked not in sent
    assert set(sent) <= {
        "serviceKey",
        "pageNo",
        "numOfRows",
        "searchValue",
        "category",
        "returnType",
    }


def test_q_too_long_no_external_call(monkeypatch):
    _patch_key(monkeypatch)
    calls = _capture(monkeypatch, lambda *a, **k: (200, json.dumps(_ok_payload([]))))
    res = _client().get(PUBLIC, params={"q": "가" * 101})
    assert res.status_code == 422
    assert res.json()["detail"] == "QUERY_TOO_LONG"
    assert calls == []

