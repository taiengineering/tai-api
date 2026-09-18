"""WO-CHEM-SEO-PREVIEW-LIVE-001 — SEO preview membership tests.

P1-P12 (WO §21) + additional regression guards. Uses in-memory stores
and the deterministic preview manifest at docs/chem/seo-preview-manifest.json.

No Supabase network I/O. No hydration artifact mutation. No production DB
write. No live router activation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import kosha_public_msds as router_mod
from services.kosha_msds import publish, read, search_adapter
from services.kosha_msds.contract import (
    ALLOWED_PUBLIC_MODES,
    ENUMERATION_FULL_OFFICIAL,
    PUBLICATION_SCOPE_FULL,
    PUBLICATION_SCOPE_SEO_PREVIEW,
    PUBLIC_MODE_ENV_VAR,
    PUBLIC_MODE_FULL,
    PUBLIC_MODE_OFF,
    PUBLIC_MODE_SEO_PREVIEW,
    PUBLISH_PUBLISHED_FULL,
    PUBLISH_PUBLISHED_SEO_PREVIEW,
    SEO_PREVIEW_REQUIRED_SECTION_COUNT,
    SNAPSHOT_COMPLETED,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "docs" / "chem" / "seo-preview-manifest.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _chem_row(chem_id: str, *, name_ko: str, name_en: str,
              cas_no: str | None = None) -> dict:
    return {
        "id": f"uid-{chem_id}",
        "content_id": f"CHEM:{chem_id}",
        "source_id": "KOSHA_MSDS",
        "source_key": chem_id,
        "chem_id": chem_id,
        "identity_status": "READY",
        "chemical_name_ko": name_ko,
        "chemical_name_en": name_en,
        "cas_no": cas_no,
        "ke_no": None,
        "en_no": None,
        "un_no": None,
        "source_content_hash": f"sha-{chem_id}",
        "source_dataset_url": "https://www.data.go.kr/data/15157612/openapi.do",
        "snapshot_id": "snap-preview-1",
    }


def _section_row(chemical_id: str, section_no: int) -> dict:
    return {
        "chemical_id": chemical_id,
        "section_no": section_no,
        "payload_json": [{
            "msdsItemCode": f"C{section_no:02d}",
            "msdsItemNameKor": f"항목{section_no}",
            "itemDetail": "값",
            "ordrIdx": "1",
            "lev": "1",
            "upMsdsItemCode": "A",
        }],
        "section_hash": f"sha-{chemical_id}-{section_no}",
        "result_code": "00",
        "result_message": "OK",
        "fetched_at": "2026-09-18T00:00:00Z",
    }


def _make_preview_store() -> read.MemoryMsdsReadStore:
    """Two preview chemicals with all 16 sections each. Includes a stale
    'FULL' current view row for the SAME chem_id so we can prove that the
    scope switch actually flips the source, not just filters."""
    preview_rows = [
        _chem_row("001008", name_ko="구리분말", name_en="Copper Powder", cas_no="7440-50-8"),
        _chem_row("027621", name_ko="메탄올", name_en="Methanol", cas_no="67-56-1"),
    ]
    # A different chemical only in FULL, never in preview: verifies isolation.
    # Names must share no character substring with any preview chemical
    # so CHEM-09's Kiwi tokenizer cannot generate a false positive.
    current_rows = [
        _chem_row("999999", name_ko="가나다라마바", name_en="ZZZUNIQUEONLY",
                  cas_no="0-0-0"),
    ]
    sections = []
    # 16 sections each for preview chemicals
    for uid in ("uid-001008", "uid-027621"):
        for n in range(1, 17):
            sections.append(_section_row(uid, n))
    # sections for 999999 too (irrelevant for preview reads)
    for n in range(1, 17):
        sections.append(_section_row("uid-999999", n))
    chemicals = [
        {"id": "uid-001008", "last_date": "2025-10-01"},
        {"id": "uid-027621", "last_date": "2025-11-20"},
        {"id": "uid-999999", "last_date": "2025-09-30"},
    ]
    return read.MemoryMsdsReadStore(
        current_rows=current_rows,
        preview_rows=preview_rows,
        chemicals=chemicals,
        sections=sections,
    )


@pytest.fixture
def preview_store():
    return _make_preview_store()


@pytest.fixture
def preview_client(monkeypatch, preview_store):
    monkeypatch.setenv(PUBLIC_MODE_ENV_VAR, PUBLIC_MODE_SEO_PREVIEW)
    monkeypatch.setattr(router_mod, "get_store", lambda: preview_store)
    app = FastAPI()
    app.include_router(router_mod.router)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def dormant_client(monkeypatch, preview_store):
    # Default mode is off (unset env var or invalid value).
    monkeypatch.delenv(PUBLIC_MODE_ENV_VAR, raising=False)
    monkeypatch.setattr(router_mod, "get_store", lambda: preview_store)
    app = FastAPI()
    app.include_router(router_mod.router)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# P1 · complete 16/16 chemical → preview eligible
# ---------------------------------------------------------------------------


def test_P1_complete_16_of_16_is_preview_eligible(preview_client):
    r = preview_client.get("/public/kosha/msds/001008")
    assert r.status_code == 200
    body = r.json()
    assert body["chem_id"] == "001008"
    assert len(body["sections"]) == 16
    assert [s["section_no"] for s in body["sections"]] == list(range(1, 17))


# ---------------------------------------------------------------------------
# P2 · 15/16 → excluded (chemical whole)
# ---------------------------------------------------------------------------


def test_P2_partial_15_of_16_excluded_from_preview(monkeypatch):
    """A chemical with only 15 sections in the source artifact must NOT
    appear in preview_rows. Manifest builder handles the exclusion; here
    we verify the store contract: if not in preview_rows, the router
    returns 404 in preview mode.
    """
    preview_rows = [_chem_row("027621", name_ko="메탄올", name_en="Methanol", cas_no="67-56-1")]
    # partial_chem is present in `sections` but NOT in preview_rows.
    sections = []
    for n in range(1, 17):
        sections.append(_section_row("uid-027621", n))
    for n in range(1, 16):  # 15/16 → intentionally excluded from preview_rows
        sections.append(_section_row("uid-partial", n))
    store = read.MemoryMsdsReadStore(
        preview_rows=preview_rows,
        sections=sections,
        chemicals=[{"id": "uid-027621", "last_date": "2025-11-20"}],
    )
    monkeypatch.setenv(PUBLIC_MODE_ENV_VAR, PUBLIC_MODE_SEO_PREVIEW)
    monkeypatch.setattr(router_mod, "get_store", lambda: store)
    app = FastAPI()
    app.include_router(router_mod.router)
    with TestClient(app) as c:
        r = c.get("/public/kosha/msds/partial15")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# P3 · chemId 432377 (9/16) → excluded
# ---------------------------------------------------------------------------


def test_P3_manifest_excludes_chemId_432377():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    excluded = manifest["census"]["excluded_chem_ids"]
    assert "432377" in excluded, "chemId 432377 (9/16) must be in excluded_chem_ids"
    for row in manifest["chemicals"]:
        assert row["chem_id"] != "432377", "chemId 432377 must NOT appear in chemicals list"


# ---------------------------------------------------------------------------
# P4 · duplicate section → exclusion (defense-in-depth: manifest builder
# de-dupes by (chem_id, section_no); if artifact has duplicates the last
# write wins but section_count is still counted correctly).
# ---------------------------------------------------------------------------


def test_P4_manifest_section_count_distribution_no_double_counted():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    dist = manifest["census"]["section_count_distribution"]
    # Only two buckets expected under the current artifact: 9 (partial) and 16 (complete).
    assert set(dist.keys()) == {"9", "16"}
    # Every preview chemical has exactly 16 sections.
    for row in manifest["chemicals"]:
        assert row["section_count"] == SEO_PREVIEW_REQUIRED_SECTION_COUNT


# ---------------------------------------------------------------------------
# P5 · preview detail → 200
# ---------------------------------------------------------------------------


def test_P5_preview_detail_200_with_all_16_sections(preview_client):
    r = preview_client.get("/public/kosha/msds/027621")
    assert r.status_code == 200
    body = r.json()
    assert body["chemical_name_ko"] == "메탄올"
    assert len(body["sections"]) == 16


# ---------------------------------------------------------------------------
# P6 · non-preview canonical chemical → public 404 in preview mode
# ---------------------------------------------------------------------------


def test_P6_non_preview_chem_public_404_in_preview_mode(preview_client):
    # chem_id "999999" is only in current_rows (FULL scope), not preview_rows.
    r = preview_client.get("/public/kosha/msds/999999")
    assert r.status_code == 404, "non-preview chem must be public-404 in preview mode"


# ---------------------------------------------------------------------------
# P7 · search result → preview membership only
# ---------------------------------------------------------------------------


def test_P7_search_result_preview_membership_only(preview_client):
    # q=구리분말 would match a name that lives only in preview_rows.
    r = preview_client.get("/public/kosha/msds", params={"q": "구리분말"})
    assert r.status_code == 200
    body = r.json()
    chem_ids = [it["chem_id"] for it in body["items"]]
    assert "001008" in chem_ids
    assert "999999" not in chem_ids, "FULL-only chemical must not leak into preview search"

    # q that would match the FULL-only chemical must return no rows in preview.
    # "ZZZUNIQUEONLY" has no character overlap with any preview chemical name.
    r2 = preview_client.get("/public/kosha/msds", params={"q": "ZZZUNIQUEONLY"})
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["total"] == 0, "FULL-only chemical must not surface in preview search"


# ---------------------------------------------------------------------------
# P8 · identifier exact → existing CHEM-09 behavior preserved
# ---------------------------------------------------------------------------


def test_P8_identifier_exact_preserves_behavior(preview_client):
    # 6-digit chem_id triggers identifier-exact path (CHEM-09).
    r = preview_client.get("/public/kosha/msds", params={"q": "001008"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["chem_id"] == "001008"
    assert body["items"][0]["match_type"] == "IDENTIFIER_EXACT"
    # Match metadata carries the plan.
    assert body["match_metadata"]["identifier_kind"] == "chem_id"


# ---------------------------------------------------------------------------
# P9 · Kiwi/terminology → existing adapter preserved (no per-scope duplication)
# ---------------------------------------------------------------------------


def test_P9_kiwi_terminology_adapter_reused_for_preview(preview_client, monkeypatch):
    # No new adapter — search_by_q is the only entry point and it accepts scope.
    calls = []
    orig = search_adapter.search_by_q

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return orig(*args, **kwargs)

    monkeypatch.setattr(search_adapter, "search_by_q", spy)
    # Re-import router's alias binding so the spy is visible.
    monkeypatch.setattr(router_mod, "search_by_q", spy)
    r = preview_client.get("/public/kosha/msds", params={"q": "메탄올"})
    assert r.status_code == 200
    assert len(calls) == 1
    assert calls[0]["scope"] == PUBLICATION_SCOPE_SEO_PREVIEW, \
        "router must forward SEO_PREVIEW scope to search_by_q"


# ---------------------------------------------------------------------------
# P10 · preview mode → PUBLISHED_FULL untouched
# ---------------------------------------------------------------------------


def test_P10_preview_mode_does_not_touch_published_full():
    # The read layer view mapping keeps PUBLISHED_FULL sourced from
    # kosha_msds_current and PUBLISHED_SEO_PREVIEW from the preview view.
    assert read._view_for_scope(PUBLICATION_SCOPE_FULL) == "kosha_msds_current"
    assert read._view_for_scope(PUBLICATION_SCOPE_SEO_PREVIEW) == "kosha_msds_seo_preview_current"

    # The CHEM-10 target state mapping is scope-aware and PUBLISHED_FULL
    # is reserved for the FULL scope.
    assert publish.target_publish_state(PUBLICATION_SCOPE_FULL) == PUBLISH_PUBLISHED_FULL
    assert publish.target_publish_state(PUBLICATION_SCOPE_SEO_PREVIEW) == PUBLISH_PUBLISHED_SEO_PREVIEW


# ---------------------------------------------------------------------------
# P11 · full mode → existing FULL behavior unchanged
# ---------------------------------------------------------------------------


def test_P11_full_mode_behavior_unchanged(monkeypatch, preview_store):
    monkeypatch.setenv(PUBLIC_MODE_ENV_VAR, PUBLIC_MODE_FULL)
    monkeypatch.setattr(router_mod, "get_store", lambda: preview_store)
    app = FastAPI()
    app.include_router(router_mod.router)
    with TestClient(app) as c:
        # Full mode sees the FULL-only chemical.
        r = c.get("/public/kosha/msds/999999")
        assert r.status_code == 200
        assert r.json()["chem_id"] == "999999"
        # Full mode does NOT auto-see the preview-only chemical (unless it
        # is also in current_rows). In our store 001008 is only in
        # preview_rows, so FULL scope returns 404 for it.
        r2 = c.get("/public/kosha/msds/001008")
        assert r2.status_code == 404


# ---------------------------------------------------------------------------
# P12 · router off → 503 dormant behavior
# ---------------------------------------------------------------------------


def test_P12_router_off_is_dormant(dormant_client):
    r = dormant_client.get("/public/kosha/msds")
    assert r.status_code == 503
    body = r.json()
    assert body["detail"]["code"] == "MSDS_PUBLIC_DORMANT"


def test_P12b_router_unknown_mode_falls_back_to_off(monkeypatch, preview_store):
    monkeypatch.setenv(PUBLIC_MODE_ENV_VAR, "GARBAGE_VALUE")
    monkeypatch.setattr(router_mod, "get_store", lambda: preview_store)
    app = FastAPI()
    app.include_router(router_mod.router)
    with TestClient(app) as c:
        r = c.get("/public/kosha/msds")
        assert r.status_code == 503, "unknown mode → fail-closed off"


# ---------------------------------------------------------------------------
# Extras — manifest census + WO §22 exactness
# ---------------------------------------------------------------------------


def test_manifest_census_matches_wo_section_22():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["wo"] == "WO-CHEM-SEO-PREVIEW-LIVE-001"
    assert manifest["publication_scope"] == PUBLICATION_SCOPE_SEO_PREVIEW
    assert manifest["source"]["source_responses"] == 31961
    assert manifest["census"]["complete_chemicals"] == 1997
    assert manifest["census"]["preview_sections"] == 31952
    assert manifest["census"]["excluded_chemicals"] == 1
    assert manifest["census"]["excluded_chem_ids"] == ["432377"]
    assert manifest["census"]["unique_chemicals"] == 1998
    # 16*1997 = 31952
    assert manifest["census"]["preview_sections"] == \
        manifest["census"]["complete_chemicals"] * SEO_PREVIEW_REQUIRED_SECTION_COUNT
    # Deterministic self-hash: same length as SHA256.
    assert len(manifest["manifest_sha256"]) == 64
    assert len(manifest["source"]["responses_sha256"]) == 64
    # 1997 rows exactly.
    assert len(manifest["chemicals"]) == 1997


def test_manifest_chemicals_sorted_and_unique():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ids = [r["chem_id"] for r in manifest["chemicals"]]
    assert ids == sorted(ids), "chemicals must be sorted by chem_id"
    assert len(ids) == len(set(ids)), "no duplicate chem_ids"
    # Every row has exactly section_count=16 and a 64-char hash.
    for row in manifest["chemicals"]:
        assert row["section_count"] == SEO_PREVIEW_REQUIRED_SECTION_COUNT
        assert len(row["section_hashes_sha256"]) == 64


# ---------------------------------------------------------------------------
# Load-bearing fences: PRODUCTION_WRITE_ALLOWED and PRODUCTION_PUBLISH_ALLOWED
# both still False after WO-CHEM-SEO-PREVIEW-LIVE-001. This WO does not open
# the write path (WO §23).
# ---------------------------------------------------------------------------


def test_production_write_fence_still_closed():
    from services.kosha_msds import materialize_writer, publish as pub
    assert materialize_writer.PRODUCTION_WRITE_ALLOWED is False
    assert pub.PRODUCTION_PUBLISH_ALLOWED is False


# ---------------------------------------------------------------------------
# CHEM-10 preflight under SEO_PREVIEW scope: expected counts must be supplied
# from the manifest (not hard-coded).
# ---------------------------------------------------------------------------


def test_chem10_preflight_seo_preview_requires_explicit_counts():
    store = publish.MemoryPublishStore()
    with pytest.raises(ValueError):
        publish.preflight_publish(
            "snap-x",
            store=store,
            publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        )


def test_chem10_preflight_seo_preview_uses_manifest_counts():
    # Build a fixture snapshot that passes ALL preview gates.
    from services.kosha_msds.contract import (
        DETAIL_COMPLETE,
        ENUMERATION_FULL_OFFICIAL,
        SNAPSHOT_COMPLETED,
    )
    # 3 chemicals, 3*16 = 48 sections.
    snapshot_id = "snap-preview"
    snapshots = [{
        "id": snapshot_id,
        "status": SNAPSHOT_COMPLETED,
        "enumeration_mode": ENUMERATION_FULL_OFFICIAL,
        "publish_state": "NOT_PUBLISHED",
        "expected_count": 3,
        "discovered_count": 3,
        "metrics_json": {},
    }]
    snapshot_items = []
    sections = []
    for cid in ("A", "B", "C"):
        snapshot_items.append({
            "snapshot_id": snapshot_id,
            "chemical_id": cid,
            "detail_status": DETAIL_COMPLETE,
            "in_snapshot": True,
        })
        for n in range(1, 17):
            sections.append({
                "chemical_id": cid,
                "section_no": n,
                "section_hash": f"h-{cid}-{n}",
            })
    store = publish.MemoryPublishStore(
        snapshots=snapshots,
        snapshot_items=snapshot_items,
        sections=sections,
    )
    report = publish.preflight_publish(
        snapshot_id,
        store=store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        seo_preview_expected_chemical_count=3,
        seo_preview_expected_section_count=48,
    )
    assert report.eligible is True, f"expected eligible, got block_reasons={report.block_reasons}"


# ---------------------------------------------------------------------------
# Manifest builder tool: --check mode against the checked-in manifest.
# Verifies the SHA256 chain stays fresh against the source artifact.
# ---------------------------------------------------------------------------


def test_manifest_check_matches_source_when_artifact_present():
    """Skipped if the source artifact is not on this machine (CI runners
    typically won't have the 31,961-line jsonl). Locally we verify."""
    artifact = Path("/Users/taiwangsim/Desktop/tai-api-obj-chem/artifacts/chem04/official_v12/responses.jsonl")
    if not artifact.exists():
        pytest.skip("hydration artifact not available on this host")
    result = subprocess.run(
        [sys.executable, "-m", "tools.chem_seo_preview.build_manifest",
         "--responses-jsonl", str(artifact),
         "--check", str(MANIFEST_PATH)],
        cwd=REPO_ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert result.returncode == 0, f"manifest check failed: stdout={result.stdout} stderr={result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "MATCH"
    assert payload["complete_chemicals"] == 1997
