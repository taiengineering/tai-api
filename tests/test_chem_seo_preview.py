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
# P4 (PATCH-1) · duplicate (chem_id, section_no) → builder fails non-zero,
# no manifest file written. Synthetic responses.jsonl with a real duplicate
# row proves the fail-closed contract (WO §21 P4 + PATCH-B).
# ---------------------------------------------------------------------------


def _write_synth_responses(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _synth_row(chem_id: str, section_no: int, *, result_code: str = "00",
               authoritative: bool = True) -> dict:
    return {
        "chemId": chem_id,
        "sectionNo": section_no,
        "authoritative_verified": authoritative,
        "result_code": result_code,
        "items": [{"msdsItemCode": f"C{section_no:02d}", "itemDetail": "x"}],
    }


def test_P4_duplicate_pair_fails_builder_non_zero(tmp_path):
    """A real synthetic artifact with (chem A, section 1) duplicated must
    cause `build_manifest` CLI to exit non-zero and NOT write output."""
    rows = [_synth_row("A00001", n) for n in range(1, 17)]
    # Inject a real duplicate: (A00001, 1) appears TWICE.
    rows.append(_synth_row("A00001", 1))
    src = tmp_path / "responses.jsonl"
    out = tmp_path / "manifest.json"
    _write_synth_responses(src, rows)
    r = subprocess.run(
        [sys.executable, "-m", "tools.chem_seo_preview.build_manifest",
         "--responses-jsonl", str(src), "--out", str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert r.returncode != 0, f"builder should fail-closed on duplicate: {r.stdout} {r.stderr}"
    assert not out.exists(), "manifest file must NOT be written on failure"
    # Message must name the duplicate condition so operators can diagnose.
    combined = r.stdout + r.stderr
    assert "duplicate" in combined.lower() or "DUPLICATE" in combined


def test_P4b_source_contract_failure_fails_builder(tmp_path):
    """authoritative_verified == false must cause fail-closed exit."""
    rows = [_synth_row("A00001", n) for n in range(1, 17)]
    rows.append(_synth_row("B00002", 1, authoritative=False))   # contract failure
    src = tmp_path / "responses.jsonl"
    out = tmp_path / "manifest.json"
    _write_synth_responses(src, rows)
    r = subprocess.run(
        [sys.executable, "-m", "tools.chem_seo_preview.build_manifest",
         "--responses-jsonl", str(src), "--out", str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert r.returncode != 0, "builder must fail-closed on source contract failure"
    assert not out.exists(), "manifest file must NOT be written on failure"


def test_P4c_bad_result_code_fails_builder(tmp_path):
    """result_code outside SUCCESS set must cause fail-closed exit."""
    rows = [_synth_row("A00001", n) for n in range(1, 17)]
    rows.append(_synth_row("B00002", 1, result_code="99"))
    src = tmp_path / "responses.jsonl"
    out = tmp_path / "manifest.json"
    _write_synth_responses(src, rows)
    r = subprocess.run(
        [sys.executable, "-m", "tools.chem_seo_preview.build_manifest",
         "--responses-jsonl", str(src), "--out", str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert r.returncode != 0, "builder must fail-closed on non-success result_code"
    assert not out.exists()


def test_P4d_clean_synthetic_artifact_builds_successfully(tmp_path):
    """Positive control: a clean synthetic 2-chemical artifact yields a
    complete manifest with the expected census (duplicate_pairs=0,
    source_contract_failures=0). Proves the fail-closed path fires only
    on real violations."""
    rows = [_synth_row("A00001", n) for n in range(1, 17)]
    rows += [_synth_row("B00002", n) for n in range(1, 17)]
    src = tmp_path / "responses.jsonl"
    out = tmp_path / "manifest.json"
    _write_synth_responses(src, rows)
    r = subprocess.run(
        [sys.executable, "-m", "tools.chem_seo_preview.build_manifest",
         "--responses-jsonl", str(src), "--out", str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert r.returncode == 0, r.stderr
    assert out.exists()
    manifest = json.loads(out.read_text(encoding="utf-8"))
    assert manifest["census"]["complete_chemicals"] == 2
    assert manifest["census"]["preview_sections"] == 32
    assert manifest["census"]["duplicate_pairs"] == 0
    assert manifest["census"]["source_contract_failures"] == 0
    assert manifest["generator_version"] == "2"


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
    assert read._view_for_scope(PUBLICATION_SCOPE_SEO_PREVIEW) == "kosha_msds_seo_preview_display"

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
    # PATCH-1: frozen corpus must show zero duplicates and zero contract failures.
    assert manifest["census"]["duplicate_pairs"] == 0
    assert manifest["census"]["source_contract_failures"] == 0
    # PATCH-1: generator bumped from 1 → 2 (semantic change: fail-closed).
    assert manifest["generator_version"] == "2"
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


# ---------------------------------------------------------------------------
# PATCH-A · SEO manifest → preview materialize plan bridge integration tests.
#
# End-to-end chain: build_manifest → build_preview_plan → materialize_writer.preflight
# must yield can_execute=True and the snapshot metrics_json must carry the
# seo_preview_manifest_sha256 binding CHEM-10 will later verify.
# ---------------------------------------------------------------------------


from services.kosha_msds import materialize_writer, materialize as chem05_lib
from tools.chem_seo_preview import build_preview_plan as bridge_mod


def _run_chem05_plan(responses_path: Path, out_dir: Path) -> dict:
    """Run CHEM-05 build_materialize_plan.run() against a synthetic
    responses.jsonl. Returns the paths to the three CHEM-05 artifacts."""
    from tools.chem05.build_materialize_plan import run as chem05_run
    chem05_run(responses_path=responses_path, census_path=None, out_dir=out_dir)
    return {
        "plan_jsonl": out_dir / "materialize_plan.jsonl",
        "manifest": out_dir / "materialize_manifest.json",
        "report": out_dir / "materialize_report.json",
    }


def _synth_full_row(chem_id: str, section_no: int, *, items_extra: str = "") -> dict:
    """Full contract row that CHEM-05's build_plan accepts as an
    authoritative section. Matches services.kosha_msds.materialize
    REQUIRED_SOURCE = 'KOSHA_OFFICIAL' + KOSHA_MSDS_OPENAPI_V1_2 + spec 1.2."""
    return {
        "chemId": chem_id,
        "sectionNo": section_no,
        "authoritative_verified": True,
        "result_code": "00",
        "result_msg": "NORMAL SERVICE.",
        "fetched_at": "2026-09-18T00:00:00Z",
        "source": "KOSHA_OFFICIAL",
        "official_spec_date": "2026-09-16",
        "official_spec_version": "1.2",
        "operation": f"getChemDetail{section_no:02d}1",
        "source_contract_version": "KOSHA_MSDS_OPENAPI_V1_2",
        "status": "OK",
        "items": [{
            "msdsItemCode": f"C{section_no:02d}",
            "msdsItemNameKor": f"항목{section_no}",
            "itemDetail": f"value{items_extra}",
            "ordrIdx": "1",
            "lev": "1",
            "upMsdsItemCode": "A",
        }],
    }


def _synth_full_artifact(chem_ids: list[str], tmp_path: Path,
                          include_partial_chem: str | None = None) -> Path:
    """Write a synthetic responses.jsonl with N chemicals × 16 sections
    each, optionally including one partial chemical (sections 1..9)."""
    src = tmp_path / "responses.jsonl"
    with src.open("w", encoding="utf-8") as fh:
        for cid in chem_ids:
            for n in range(1, 17):
                fh.write(json.dumps(_synth_full_row(cid, n), ensure_ascii=False) + "\n")
        if include_partial_chem:
            for n in range(1, 10):
                fh.write(json.dumps(_synth_full_row(include_partial_chem, n), ensure_ascii=False) + "\n")
    return src


def _run_seo_manifest_build(responses_path: Path, out_path: Path) -> dict:
    r = subprocess.run(
        [sys.executable, "-m", "tools.chem_seo_preview.build_manifest",
         "--responses-jsonl", str(responses_path), "--out", str(out_path)],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    if r.returncode != 0:
        pytest.fail(f"synthetic manifest build failed: {r.stderr}")
    return json.loads(out_path.read_text(encoding="utf-8"))


def test_bridge_positive_manifest_plan_preflight_can_execute(tmp_path):
    """POSITIVE PATH: synthetic 3-complete + 1-partial responses
    → CHEM-05 plan (partial=INCOMPLETE, complete=COMPLETE, execute_eligible=False)
    → SEO manifest (3 preview chemicals, excluded=partial)
    → bridge preview plan (3 chemicals × 16, execute_eligible=True)
    → materialize_writer.preflight(publication_scope=SEO_PREVIEW).can_execute == True
    → snapshot.metrics_json carries seo_preview_manifest_sha256.
    """
    src = _synth_full_artifact(["A00001", "A00002", "A00003"], tmp_path,
                                include_partial_chem="P99999")
    chem05_dir = tmp_path / "chem05"
    chem05_paths = _run_chem05_plan(src, chem05_dir)
    seo_manifest_path = tmp_path / "seo-manifest.json"
    seo = _run_seo_manifest_build(src, seo_manifest_path)
    assert seo["census"]["complete_chemicals"] == 3
    assert seo["census"]["excluded_chem_ids"] == ["P99999"]

    built = bridge_mod.build_preview_plan(
        chem05_plan_jsonl=chem05_paths["plan_jsonl"],
        chem05_manifest_json=chem05_paths["manifest"],
        chem05_report_json=chem05_paths["report"],
        seo_manifest_json=seo_manifest_path,
    )
    assert built["manifest"]["execute_eligible"] is True
    assert built["manifest"]["counts"]["chemicals"] == 3
    assert built["manifest"]["counts"]["sections"] == 48
    metrics = built["manifest"]["snapshot"]["metrics_json"]
    assert metrics["publication_scope"] == PUBLICATION_SCOPE_SEO_PREVIEW
    assert metrics["seo_preview_manifest_sha256"] == seo["manifest_sha256"]
    assert metrics["responses_sha256"] == seo["source"]["responses_sha256"]

    # Write to disk so we can round-trip through load_plan_inputs.
    out_dir = tmp_path / "preview_out"
    manifest_disk = bridge_mod.write_preview_plan_artifacts(built, out_dir)
    plan_path = out_dir / "preview_materialize_plan.jsonl"
    inputs = materialize_writer.load_plan_inputs(
        plan_jsonl=plan_path,
        manifest_json=out_dir / "preview_materialize_manifest.json",
        report_json=out_dir / "preview_materialize_report.json",
    )
    report = materialize_writer.preflight(
        inputs, store=materialize_writer.MemoryMaterializeStore(),
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    assert report.can_execute is True, f"preflight blocked: {list(report.block_reasons)}"
    # The preview snapshot's metrics_json must carry the seo manifest SHA
    # exactly, so CHEM-10's expected_materialize_binding will match.
    assert manifest_disk["snapshot"]["metrics_json"]["seo_preview_manifest_sha256"] \
        == seo["manifest_sha256"]


def test_bridge_negative_seo_manifest_tampered_manifest_sha_integrity(tmp_path):
    """SEO manifest with an intact structure but a tampered manifest_sha256
    field must fail-closed at the integrity check."""
    src = _synth_full_artifact(["A00001", "A00002"], tmp_path)
    chem05_dir = tmp_path / "chem05"
    chem05_paths = _run_chem05_plan(src, chem05_dir)
    seo_manifest_path = tmp_path / "seo.json"
    _run_seo_manifest_build(src, seo_manifest_path)
    tampered = json.loads(seo_manifest_path.read_text(encoding="utf-8"))
    tampered["manifest_sha256"] = "0" * 64   # blatantly wrong
    seo_manifest_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        bridge_mod.build_preview_plan(
            chem05_plan_jsonl=chem05_paths["plan_jsonl"],
            chem05_manifest_json=chem05_paths["manifest"],
            chem05_report_json=chem05_paths["report"],
            seo_manifest_json=seo_manifest_path,
        )
    assert "MANIFEST_SHA_INTEGRITY_FAILURE" in str(exc.value)


def test_bridge_negative_responses_sha_mismatch(tmp_path):
    """CHEM-05 manifest.responses_sha256 ≠ SEO manifest → BLOCK."""
    src = _synth_full_artifact(["A00001", "A00002"], tmp_path)
    chem05_dir = tmp_path / "chem05"
    chem05_paths = _run_chem05_plan(src, chem05_dir)
    seo_manifest_path = tmp_path / "seo.json"
    _run_seo_manifest_build(src, seo_manifest_path)

    # Tamper CHEM-05 manifest's responses_sha256 (and its own manifest_sha256
    # so the file at least parses).
    tampered = json.loads(chem05_paths["manifest"].read_text(encoding="utf-8"))
    tampered["responses_sha256"] = "deadbeef" * 8
    chem05_paths["manifest"].write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        bridge_mod.build_preview_plan(
            chem05_plan_jsonl=chem05_paths["plan_jsonl"],
            chem05_manifest_json=chem05_paths["manifest"],
            chem05_report_json=chem05_paths["report"],
            seo_manifest_json=seo_manifest_path,
        )
    assert "RESPONSES_SHA_MISMATCH" in str(exc.value)


def test_bridge_negative_membership_missing_from_plan(tmp_path):
    """SEO manifest lists chem_id X but CHEM-05 plan does not include X."""
    # Build artifact + SEO manifest with chem A + B.
    src = _synth_full_artifact(["A00001", "B00002"], tmp_path)
    chem05_dir = tmp_path / "chem05"
    chem05_paths = _run_chem05_plan(src, chem05_dir)
    seo_manifest_path = tmp_path / "seo.json"
    _run_seo_manifest_build(src, seo_manifest_path)

    # Now delete chem A from CHEM-05 plan JSONL to simulate a producer disagreement.
    # CHEM-05 writes JSONL with compact separators (no space after colon), so the
    # match string must also be compact.
    lines = chem05_paths["plan_jsonl"].read_text(encoding="utf-8").splitlines()
    filtered = [ln for ln in lines if '"chem_id":"A00001"' not in ln]
    assert len(filtered) < len(lines), "sanity: at least one line filtered"
    chem05_paths["plan_jsonl"].write_text("\n".join(filtered) + "\n", encoding="utf-8")
    # PATCH-2: keep the manifest's plan_file_sha256 in sync with the new JSONL
    # so PATCH-2's SOURCE_PLAN_FILE_SHA_MISMATCH guard doesn't intercept first —
    # this test targets the deeper MANIFEST_MEMBER_NOT_IN_PLAN reason.
    from tools.chem_seo_preview.build_preview_plan import _file_sha256 as _sha
    m = json.loads(chem05_paths["manifest"].read_text(encoding="utf-8"))
    m["plan_file_sha256"] = _sha(chem05_paths["plan_jsonl"])
    chem05_paths["manifest"].write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        bridge_mod.build_preview_plan(
            chem05_plan_jsonl=chem05_paths["plan_jsonl"],
            chem05_manifest_json=chem05_paths["manifest"],
            chem05_report_json=chem05_paths["report"],
            seo_manifest_json=seo_manifest_path,
        )
    assert "MANIFEST_MEMBER_NOT_IN_PLAN" in str(exc.value)


def test_bridge_negative_one_section_missing(tmp_path):
    """CHEM-05 plan bundle for a preview member is missing section 16.

    We tamper the CHEM-05 plan JSONL directly to drop section 16 from chem
    A00001, keeping the SEO manifest unchanged (which still expects 16
    sections). Bridge must fail-closed.
    """
    src = _synth_full_artifact(["A00001", "B00002"], tmp_path)
    chem05_dir = tmp_path / "chem05"
    chem05_paths = _run_chem05_plan(src, chem05_dir)
    seo_manifest_path = tmp_path / "seo.json"
    _run_seo_manifest_build(src, seo_manifest_path)

    # Drop section 16 from chem A00001 in the CHEM-05 plan JSONL. Use compact
    # separators to match CHEM-05's own writer.
    rewritten = []
    for line in chem05_paths["plan_jsonl"].read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        if obj.get("chem_id") == "A00001":
            obj["sections"] = [s for s in obj["sections"] if s.get("section_no") != 16]
        rewritten.append(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")))
    chem05_paths["plan_jsonl"].write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    # PATCH-2: sync manifest.plan_file_sha256 to the new JSONL so PATCH-2's
    # SOURCE_PLAN_FILE_SHA_MISMATCH guard doesn't intercept first — this test
    # targets the deeper MEMBER_INCOMPLETE_SECTIONS/MEMBER_HASH_MISMATCH reason.
    from tools.chem_seo_preview.build_preview_plan import _file_sha256 as _sha
    m = json.loads(chem05_paths["manifest"].read_text(encoding="utf-8"))
    m["plan_file_sha256"] = _sha(chem05_paths["plan_jsonl"])
    chem05_paths["manifest"].write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        bridge_mod.build_preview_plan(
            chem05_plan_jsonl=chem05_paths["plan_jsonl"],
            chem05_manifest_json=chem05_paths["manifest"],
            chem05_report_json=chem05_paths["report"],
            seo_manifest_json=seo_manifest_path,
        )
    reason_str = str(exc.value)
    # Either the section-count check or the hash check fires depending on
    # which producer noticed first; both are fail-closed exits.
    assert (
        "MEMBER_INCOMPLETE_SECTIONS" in reason_str
        or "MEMBER_HASH_MISMATCH" in reason_str
    ), reason_str


def test_bridge_chem10_binding_flows_through_to_preflight(tmp_path):
    """Prove the end-to-end binding: the preview snapshot's
    metrics_json.seo_preview_manifest_sha256 (set by the bridge) is exactly
    what CHEM-10's expected_materialize_binding will verify at production
    time. This test simulates the CHEM-10 handshake using MemoryPublishStore.
    """
    src = _synth_full_artifact(["A00001", "A00002"], tmp_path)
    chem05_dir = tmp_path / "chem05"
    chem05_paths = _run_chem05_plan(src, chem05_dir)
    seo_manifest_path = tmp_path / "seo.json"
    seo = _run_seo_manifest_build(src, seo_manifest_path)
    built = bridge_mod.build_preview_plan(
        chem05_plan_jsonl=chem05_paths["plan_jsonl"],
        chem05_manifest_json=chem05_paths["manifest"],
        chem05_report_json=chem05_paths["report"],
        seo_manifest_json=seo_manifest_path,
    )

    # Simulate a future CHEM-08 having materialized the preview plan:
    # a snapshot row exists with the bridge's metrics_json copied verbatim.
    snapshot_id = "snap-preview"
    snapshot_row = {
        "id": snapshot_id,
        "status": SNAPSHOT_COMPLETED,
        "enumeration_mode": ENUMERATION_FULL_OFFICIAL,
        "publish_state": "NOT_PUBLISHED",
        "expected_count": 2,
        "discovered_count": 2,
        "metrics_json": built["manifest"]["snapshot"]["metrics_json"],
    }
    snapshot_items = []
    sections = []
    from services.kosha_msds.contract import DETAIL_COMPLETE as DC
    for cid in ("A00001", "A00002"):
        snapshot_items.append({
            "snapshot_id": snapshot_id, "chemical_id": cid,
            "detail_status": DC, "in_snapshot": True,
        })
        for n in range(1, 17):
            sections.append({"chemical_id": cid, "section_no": n})
    store = publish.MemoryPublishStore(
        snapshots=[snapshot_row], snapshot_items=snapshot_items, sections=sections,
    )
    # Verify CHEM-10 accepts this snapshot under SEO_PREVIEW scope with the
    # correct manifest binding, and rejects it under a tampered binding.
    report_ok = publish.preflight_publish(
        snapshot_id, store=store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        seo_preview_expected_chemical_count=2,
        seo_preview_expected_section_count=32,
        expected_materialize_binding={
            "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
            "seo_preview_manifest_sha256": seo["manifest_sha256"],
            "responses_sha256": seo["source"]["responses_sha256"],
        },
    )
    assert report_ok.eligible is True, f"blocked: {list(report_ok.block_reasons)}"

    report_bad = publish.preflight_publish(
        snapshot_id, store=store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        seo_preview_expected_chemical_count=2,
        seo_preview_expected_section_count=32,
        expected_materialize_binding={
            "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
            "seo_preview_manifest_sha256": "0" * 64,   # tampered
            "responses_sha256": seo["source"]["responses_sha256"],
        },
    )
    assert report_bad.eligible is False
    assert "MATERIALIZE_BINDING_MISMATCH" in report_bad.block_reasons


# ---------------------------------------------------------------------------
# PATCH-2 · Source-plan file integrity guard.
#
# If the CHEM-05 plan JSONL is tampered on disk without updating its
# accompanying manifest, the bridge must fail-closed at
# SOURCE_PLAN_FILE_SHA_MISMATCH — not silently trust the JSONL and only
# catch violations for chem_ids that happen to appear in the SEO manifest.
# ---------------------------------------------------------------------------


def test_patch2_tampered_chem05_plan_jsonl_fails_source_sha(tmp_path):
    """Tamper one chemical row in the CHEM-05 plan JSONL (leave the manifest
    untouched). The bridge must raise SOURCE_PLAN_FILE_SHA_MISMATCH and
    write NO output files."""
    src = _synth_full_artifact(["A00001", "B00002"], tmp_path)
    chem05_dir = tmp_path / "chem05"
    chem05_paths = _run_chem05_plan(src, chem05_dir)
    seo_manifest_path = tmp_path / "seo.json"
    _run_seo_manifest_build(src, seo_manifest_path)

    # Sanity: a clean bridge run succeeds against these inputs.
    clean = bridge_mod.build_preview_plan(
        chem05_plan_jsonl=chem05_paths["plan_jsonl"],
        chem05_manifest_json=chem05_paths["manifest"],
        chem05_report_json=chem05_paths["report"],
        seo_manifest_json=seo_manifest_path,
    )
    assert clean["manifest"]["execute_eligible"] is True

    # Tamper chem A's chemical_name_ko field in the JSONL bytes without
    # touching the manifest. This changes the file SHA but not (necessarily)
    # any hash the manifest already recorded.
    plan_lines = chem05_paths["plan_jsonl"].read_text(encoding="utf-8").splitlines()
    tampered = []
    for line in plan_lines:
        obj = json.loads(line)
        if obj.get("chem_id") == "A00001":
            obj["chemical_name_ko"] = "TAMPERED"
        tampered.append(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":")))
    chem05_paths["plan_jsonl"].write_text("\n".join(tampered) + "\n", encoding="utf-8")

    out_dir = tmp_path / "preview_out"
    with pytest.raises(SystemExit) as exc:
        built = bridge_mod.build_preview_plan(
            chem05_plan_jsonl=chem05_paths["plan_jsonl"],
            chem05_manifest_json=chem05_paths["manifest"],
            chem05_report_json=chem05_paths["report"],
            seo_manifest_json=seo_manifest_path,
        )
        # Should NEVER reach the write step.
        bridge_mod.write_preview_plan_artifacts(built, out_dir)
    assert "SOURCE_PLAN_FILE_SHA_MISMATCH" in str(exc.value)
    # Fail-closed contract: no artifacts written.
    assert not out_dir.exists() or not any(out_dir.iterdir())


def test_patch2_tampered_chem05_semantic_sha_fails_semantic_check(tmp_path):
    """Tamper the CHEM-05 report's plan_sha256 so it disagrees with the
    manifest's plan_semantic_sha256. Bridge must fail-closed at
    SOURCE_PLAN_SEMANTIC_SHA_MISMATCH."""
    src = _synth_full_artifact(["A00001", "B00002"], tmp_path)
    chem05_dir = tmp_path / "chem05"
    chem05_paths = _run_chem05_plan(src, chem05_dir)
    seo_manifest_path = tmp_path / "seo.json"
    _run_seo_manifest_build(src, seo_manifest_path)

    report = json.loads(chem05_paths["report"].read_text(encoding="utf-8"))
    report["plan_sha256"] = "deadbeef" * 8   # deliberate disagreement
    chem05_paths["report"].write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        bridge_mod.build_preview_plan(
            chem05_plan_jsonl=chem05_paths["plan_jsonl"],
            chem05_manifest_json=chem05_paths["manifest"],
            chem05_report_json=chem05_paths["report"],
            seo_manifest_json=seo_manifest_path,
        )
    assert "SOURCE_PLAN_SEMANTIC_SHA_MISMATCH" in str(exc.value)


def test_patch2_positive_path_still_passes_after_new_guards(tmp_path):
    """Regression: adding the PATCH-2 guards must not break the clean chain."""
    src = _synth_full_artifact(["A00001", "A00002", "A00003"], tmp_path)
    chem05_dir = tmp_path / "chem05"
    chem05_paths = _run_chem05_plan(src, chem05_dir)
    seo_manifest_path = tmp_path / "seo.json"
    _run_seo_manifest_build(src, seo_manifest_path)
    built = bridge_mod.build_preview_plan(
        chem05_plan_jsonl=chem05_paths["plan_jsonl"],
        chem05_manifest_json=chem05_paths["manifest"],
        chem05_report_json=chem05_paths["report"],
        seo_manifest_json=seo_manifest_path,
    )
    assert built["manifest"]["execute_eligible"] is True
    assert built["manifest"]["counts"]["chemicals"] == 3
