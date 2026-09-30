"""API contract tests for GET /public/safety-search/legal/{canonical_id}.

A01–A08: response structure contract
A09: SOURCE_UI_STUB stub text must NOT appear in response display_text
A10: SOURCE_CONTENT_UNRESOLVED when no CLEAN attachment
A11: ATTACHMENT_BODY when exactly one CLEAN attachment
A12: ATTACHMENT_INDEX when multiple CLEAN attachments
A13: LEG_DB_URL missing → 500 (fail-closed)
A14: identity mismatch → 503
A15: normal article_text identity preserved

P46: additive contract — raw article_text preserved in response
P47: KC real-shape — 2 CLEAN (45983 + 227 chars) → ATTACHMENT_BODY (only 1 substantial)
P48: multi substantial — 2 CLEAN ≥ 1000 chars each → ATTACHMENT_INDEX
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_safety_search as pss_mod
from services.shared_search.production_bindings import get_current_legal_article_by_id


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pss_mod.router)
    return app


@pytest.fixture
def client():
    return TestClient(_make_app(), raise_server_exceptions=False)


NORMAL_TEXT = "사업주는 근로자에게 안전교육을 실시하여야 한다." * 3

KC_STUB = (
    '「전기용품 안전기준(KC 62619)」의 자세한 내용은 상단 메뉴 "<img id="40425753">'
    '자세한 내용</img>" 버튼을 이용하십시오.'
)

CLEAN_ATTACHMENT = {
    "id": "att-001",
    "attachment_title": "KC 62619 Ed 2.0",
    "download_status": "SUCCESS",
    "extraction_verdict": "CLEAN",
    "attachment_text": "가" * 45983,
    "attachment_no": 1,
}

MULTI_CLEAN = [
    {
        "id": "att-001", "attachment_title": "시험방법 A",
        "download_status": "SUCCESS", "extraction_verdict": "CLEAN",
        "attachment_text": "가" * 2000, "attachment_no": 1,
    },
    {
        "id": "att-002", "attachment_title": "시험방법 B",
        "download_status": "SUCCESS", "extraction_verdict": "CLEAN",
        "attachment_text": "나" * 1500, "attachment_no": 2,
    },
]

# KC 62619 real-shape: 1 substantial body (45983) + 1 non-substantial (227)
KC_REAL_SHAPE_ATTACHMENTS = [
    {
        "id": "att-body", "attachment_title": "KC 62619 Ed 2.0",
        "download_status": "SUCCESS", "extraction_verdict": "CLEAN",
        "attachment_text": "가" * 45983, "attachment_no": 1,
    },
    {
        "id": "att-reason", "attachment_title": "개정이유서",
        "download_status": "SUCCESS", "extraction_verdict": "CLEAN",
        "attachment_text": "나" * 227, "attachment_no": 2,
    },
]

BASE_ROW = {
    "id": "9b685f82-797a-4187-a14d-991b08247810",
    "law_id": "law-001",
    "law_version_id": "ver-001",
    "article_no": 1,
    "article_sub_no": None,
    "article_title": "목적",
    "is_deleted_in_version": False,
    "enforcement_date": "2023-03-20",
    "updated_at": "2023-03-20T00:00:00",
    "law_name": "전기용품 안전기준(KC 62619)",
    "record_kind": "law_article",
}


def _mock_sb(row, attachments):
    sb = MagicMock()

    def _fetch_one_side(table_name, key_column=None, key_value=None, **_):
        if table_name == "law_article":
            return row
        if table_name == "law_master":
            return {
                "id": "law-001",
                "law_name": row.get("law_name", ""),
                "is_active": True,
                "current_version_id": row.get("law_version_id"),
            }
        return None

    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q

    def _att_execute():
        res = MagicMock()
        res.data = attachments
        return res

    q.execute.side_effect = _att_execute
    sb.table.return_value = q
    return sb


def _patched(row, attachments, fn):
    sb = _mock_sb(row, attachments)
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb), \
         patch.object(pss_mod, "get_current_legal_article_by_id",
                      return_value=row), \
         patch.object(pss_mod, "_fetch_attachments_for_version",
                      return_value=attachments):
        return fn()


# A01 — 200 OK for normal article
def test_a01_normal_article_200(client):
    row = {**BASE_ROW, "article_text": NORMAL_TEXT}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, [], run)
    assert r.status_code == 200


# A02 — response has required top-level keys
def test_a02_response_top_level_keys(client):
    row = {**BASE_ROW, "article_text": NORMAL_TEXT}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, [], run)
    body = r.json()
    for k in ("object_type", "canonical_id", "title", "detail"):
        assert k in body, f"missing key: {k}"


# A03 — detail has content_mode, display_text, attachments, has_unresolved_media
def test_a03_detail_projection_keys_present(client):
    row = {**BASE_ROW, "article_text": NORMAL_TEXT}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, [], run)
    detail = r.json()["detail"]
    for k in ("content_mode", "display_text", "attachments", "has_unresolved_media"):
        assert k in detail, f"missing detail key: {k}"


# A04 — ARTICLE_TEXT mode for normal text
def test_a04_article_text_mode(client):
    row = {**BASE_ROW, "article_text": NORMAL_TEXT}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, [], run)
    assert r.json()["detail"]["content_mode"] == "ARTICLE_TEXT"


# A05 — normal text display_text identity preserved
def test_a05_normal_text_identity_preserved(client):
    row = {**BASE_ROW, "article_text": NORMAL_TEXT}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, [], run)
    assert r.json()["detail"]["display_text"] == NORMAL_TEXT


# A06 — object_type is LEGAL
def test_a06_object_type_is_legal(client):
    row = {**BASE_ROW, "article_text": NORMAL_TEXT}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, [], run)
    assert r.json()["object_type"] == "LEGAL"


# A07 — canonical_id echoed back
def test_a07_canonical_id_echoed(client):
    row = {**BASE_ROW, "article_text": NORMAL_TEXT}
    cid = "9b685f82-797a-4187-a14d-991b08247810"

    def run():
        return client.get(f"/public/safety-search/legal/{cid}")

    r = _patched(row, [], run)
    assert r.json()["canonical_id"] == cid
    assert r.json()["detail"]["law_article_id"] == cid


# A08 — 404 when row not found
def test_a08_404_when_not_found(client):
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=MagicMock()), \
         patch.object(pss_mod, "get_current_legal_article_by_id", return_value=None):
        r = client.get("/public/safety-search/legal/missing-uuid")
    assert r.status_code == 404
    assert r.json()["detail"] == "LEGAL_NOT_FOUND"


# A09 — SOURCE_UI_STUB text must NOT appear in display_text (KC 62619 use case)
def test_a09_stub_text_not_in_display_text(client):
    row = {**BASE_ROW, "article_text": KC_STUB}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, [], run)
    detail = r.json()["detail"]
    assert detail["display_text"] != KC_STUB
    assert "상단 메뉴" not in (detail.get("display_text") or "")
    assert "버튼을 이용하십시오" not in (detail.get("display_text") or "")


# A10 — SOURCE_CONTENT_UNRESOLVED when stub and no CLEAN attachment
def test_a10_unresolved_when_stub_no_attachment(client):
    row = {**BASE_ROW, "article_text": KC_STUB}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, [], run)
    assert r.json()["detail"]["content_mode"] == "SOURCE_CONTENT_UNRESOLVED"


# A11 — ATTACHMENT_BODY when exactly one CLEAN attachment
def test_a11_attachment_body_single_clean(client):
    row = {**BASE_ROW, "article_text": KC_STUB}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, [CLEAN_ATTACHMENT], run)
    detail = r.json()["detail"]
    assert detail["content_mode"] == "ATTACHMENT_BODY"
    assert len(detail["display_text"]) == 45983


# A12 — ATTACHMENT_INDEX when multiple CLEAN attachments
def test_a12_attachment_index_multi_clean(client):
    row = {**BASE_ROW, "article_text": KC_STUB}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, MULTI_CLEAN, run)
    detail = r.json()["detail"]
    assert detail["content_mode"] == "ATTACHMENT_INDEX"
    assert detail["display_text"] is None
    assert len(detail["attachments"]) == 2


# A13 — missing LEG env vars → RuntimeError → 500
def test_a13_missing_leg_env_raises(client):
    pss_mod._legal_supabase = None  # reset singleton
    with patch.dict(os.environ, {}, clear=False):
        env_backup = {
            k: os.environ.pop(k)
            for k in ("LEG_DB_URL", "LEG_DB_KEY")
            if k in os.environ
        }
        try:
            r = client.get("/public/safety-search/legal/any-uuid")
            assert r.status_code in (500, 503)
        finally:
            os.environ.update(env_backup)
            pss_mod._legal_supabase = None  # reset again for next test


# A14 — identity mismatch → 503
def test_a14_identity_mismatch_503(client):
    row = {**BASE_ROW, "article_text": NORMAL_TEXT, "id": "different-uuid"}

    with patch.object(pss_mod, "_legal_supabase_dep", return_value=MagicMock()), \
         patch.object(pss_mod, "get_current_legal_article_by_id", return_value=row):
        r = client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    assert r.status_code == 503
    assert r.json()["detail"] == "LEGAL_IDENTITY_MISMATCH"


# A15 — normal article has no unresolved_media_ids
def test_a15_normal_article_no_unresolved_media(client):
    row = {**BASE_ROW, "article_text": NORMAL_TEXT}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, [], run)
    detail = r.json()["detail"]
    assert detail["has_unresolved_media"] is False
    assert detail["unresolved_media_ids"] == []


# P46 — additive contract: raw article_text must remain in response unchanged
def test_p46_additive_contract_article_text_preserved(client):
    row = {**BASE_ROW, "article_text": NORMAL_TEXT}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, [], run)
    detail = r.json()["detail"]
    assert "article_text" in detail, "article_text must be present (additive contract)"
    assert detail["article_text"] == NORMAL_TEXT


# P47 — KC real-shape: 2 CLEAN attachments (45983 + 227 chars)
#        Only 1 meets SUBSTANTIAL_TEXT_MIN_CHARS (1000) → ATTACHMENT_BODY, not ATTACHMENT_INDEX
def test_p47_kc_real_shape_two_clean_one_substantial(client):
    row = {**BASE_ROW, "article_text": KC_STUB}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, KC_REAL_SHAPE_ATTACHMENTS, run)
    detail = r.json()["detail"]
    assert detail["content_mode"] == "ATTACHMENT_BODY", (
        "2 CLEAN attachments with only 1 substantial must yield ATTACHMENT_BODY, not ATTACHMENT_INDEX"
    )
    assert len(detail["display_text"]) == 45983


# P48 — multi substantial: 2 CLEAN attachments both ≥ 1000 chars → ATTACHMENT_INDEX
def test_p48_multi_substantial_yields_attachment_index(client):
    row = {**BASE_ROW, "article_text": KC_STUB}

    def run():
        return client.get("/public/safety-search/legal/9b685f82-797a-4187-a14d-991b08247810")

    r = _patched(row, MULTI_CLEAN, run)
    detail = r.json()["detail"]
    assert detail["content_mode"] == "ATTACHMENT_INDEX"
    assert detail["display_text"] is None
    assert len(detail["attachments"]) == 2
