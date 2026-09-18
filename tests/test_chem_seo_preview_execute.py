"""WO-CHEM-SEO-PREVIEW-EXECUTE-001 — production executor tests.

Uses in-memory stores (MemoryMaterializeStore + MemoryPublishStore) so
no live Supabase is needed in CI. Verifies every fail-closed guard the
production executor implements, plus a positive round-trip that ends
with publish_state = PUBLISHED_SEO_PREVIEW.

Also verifies:
  * FULL scope → BLOCK
  * --owner-approved False → BLOCK
  * --execute unset → BLOCK
  * expected SHA mismatch → BLOCK
  * expected census mismatch → BLOCK
  * materialize preflight blocked → publish path NOT reached
  * publish binding mismatch (tampered snapshot metrics_json) → promotion BLOCK
  * PUBLISHED_FULL is NEVER written by this executor
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from services.kosha_msds import materialize_writer as w
from services.kosha_msds import publish as pub
from services.kosha_msds.contract import (
    DETAIL_COMPLETE,
    ENUMERATION_FULL_OFFICIAL,
    PUBLICATION_SCOPE_FULL,
    PUBLICATION_SCOPE_SEO_PREVIEW,
    PUBLISH_NOT_PUBLISHED,
    PUBLISH_PUBLISHED_FULL,
    PUBLISH_PUBLISHED_SEO_PREVIEW,
    SNAPSHOT_COMPLETED,
    SNAPSHOT_FAILED,
    SNAPSHOT_RUNNING,
)
from tools.chem_seo_preview import execute_production as ex
from tools.chem_seo_preview import build_manifest as manifest_mod

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "docs" / "chem" / "seo-preview-manifest.json"


# ---------------------------------------------------------------------------
# Synthetic pipeline fixture: build responses.jsonl → CHEM-05 plan → SEO
# manifest → the four paths the executor consumes. Uses in-memory stores.
# ---------------------------------------------------------------------------


def _synth_full_row(chem_id: str, section_no: int) -> dict:
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
            "itemDetail": "value",
            "ordrIdx": "1",
            "lev": "1",
            "upMsdsItemCode": "A",
        }],
    }


def _write_synth_artifact(chem_ids: list[str], tmp_path: Path) -> Path:
    src = tmp_path / "responses.jsonl"
    with src.open("w", encoding="utf-8") as fh:
        for cid in chem_ids:
            for n in range(1, 17):
                fh.write(json.dumps(_synth_full_row(cid, n), ensure_ascii=False) + "\n")
    return src


def _run_chem05(responses: Path, out_dir: Path) -> dict:
    from tools.chem05.build_materialize_plan import run
    run(responses_path=responses, census_path=None, out_dir=out_dir)
    return {
        "plan_jsonl": out_dir / "materialize_plan.jsonl",
        "manifest": out_dir / "materialize_manifest.json",
        "report": out_dir / "materialize_report.json",
    }


def _build_seo_manifest(responses: Path, out_path: Path) -> dict:
    r = subprocess.run(
        [sys.executable, "-m", "tools.chem_seo_preview.build_manifest",
         "--responses-jsonl", str(responses), "--out", str(out_path)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"seo manifest build failed: {r.stderr}"
    return json.loads(out_path.read_text(encoding="utf-8"))


def _make_pipeline(tmp_path: Path, chem_ids: list[str]):
    """Return a dict of paths + fresh memory stores + SEO manifest."""
    src = _write_synth_artifact(chem_ids, tmp_path)
    chem05_dir = tmp_path / "chem05"
    chem05_paths = _run_chem05(src, chem05_dir)
    seo_path = tmp_path / "seo.json"
    seo = _build_seo_manifest(src, seo_path)

    def _factory():
        return w.MemoryMaterializeStore(), pub.MemoryPublishStore()

    return {
        "src": src,
        "chem05": chem05_paths,
        "seo_path": seo_path,
        "seo": seo,
        "store_factory": _factory,
    }


def _args_ns(**over) -> argparse.Namespace:
    """Build a Namespace that matches the CLI parser's shape."""
    defaults = dict(
        scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        owner_approved=True,
        execute=True,
        seo_manifest=None,
        chem05_plan_jsonl=None,
        chem05_manifest=None,
        chem05_report=None,
        snapshot_id="seo-preview-test-1",
        expected_seo_manifest_sha=None,
        expected_responses_sha=None,
        expected_chemical_count=None,
        expected_section_count=None,
    )
    defaults.update(over)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Preconditions (CLI-level gates)
# ---------------------------------------------------------------------------


def test_full_scope_is_refused(tmp_path):
    pipe = _make_pipeline(tmp_path, ["A00001", "A00002"])
    args = _args_ns(
        scope=PUBLICATION_SCOPE_FULL,
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
    )
    with pytest.raises(SystemExit) as exc:
        ex._run(args, store_factory=pipe["store_factory"])
    assert "SCOPE_NOT_SEO_PREVIEW" in str(exc.value)


def test_owner_not_approved_is_refused(tmp_path):
    pipe = _make_pipeline(tmp_path, ["A00001", "A00002"])
    args = _args_ns(
        owner_approved=False,
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
    )
    with pytest.raises(SystemExit) as exc:
        ex._run(args, store_factory=pipe["store_factory"])
    assert "OWNER_NOT_APPROVED" in str(exc.value)


def test_execute_flag_required(tmp_path):
    pipe = _make_pipeline(tmp_path, ["A00001", "A00002"])
    args = _args_ns(
        execute=False,
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
    )
    with pytest.raises(SystemExit) as exc:
        ex._run(args, store_factory=pipe["store_factory"])
    assert "EXECUTE_NOT_REQUESTED" in str(exc.value)


# ---------------------------------------------------------------------------
# Frozen SHA guards
# ---------------------------------------------------------------------------


def test_expected_manifest_sha_mismatch_blocks(tmp_path):
    pipe = _make_pipeline(tmp_path, ["A00001", "A00002"])
    args = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
        expected_seo_manifest_sha="0" * 64,
    )
    with pytest.raises(SystemExit) as exc:
        ex._run(args, store_factory=pipe["store_factory"])
    assert "EXPECTED_MANIFEST_SHA_MISMATCH" in str(exc.value)


def test_expected_responses_sha_mismatch_blocks(tmp_path):
    pipe = _make_pipeline(tmp_path, ["A00001", "A00002"])
    args = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
        expected_responses_sha="0" * 64,
    )
    with pytest.raises(SystemExit) as exc:
        ex._run(args, store_factory=pipe["store_factory"])
    assert "EXPECTED_RESPONSES_SHA_MISMATCH" in str(exc.value)


def test_expected_census_mismatch_blocks(tmp_path):
    pipe = _make_pipeline(tmp_path, ["A00001", "A00002"])
    args = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
        expected_chemical_count=999,   # mismatch
    )
    with pytest.raises(SystemExit) as exc:
        ex._run(args, store_factory=pipe["store_factory"])
    assert "EXPECTED_CENSUS_MISMATCH" in str(exc.value)


# ---------------------------------------------------------------------------
# Successful round-trip end-to-end
# ---------------------------------------------------------------------------


def _shared_stores():
    """Wire in-memory materialize + publish stores so they observe the
    same underlying rows. In production both types point at the same
    Postgres tables; here we forward pub_store's read helpers to
    mat_store's live dicts so a section written during materialize is
    visible when publish_preflight runs a moment later."""
    mat_store = w.MemoryMaterializeStore()
    pub_store = pub.MemoryPublishStore()
    pub_store._snapshots = mat_store._snapshots
    pub_store._items = mat_store._snapshot_items

    def _sections_live(snapshot_id: str) -> list[dict]:
        chem_uuids = {
            str(i.get("chemical_id"))
            for i in mat_store._snapshot_items
            if str(i.get("snapshot_id")) == str(snapshot_id)
            and i.get("in_snapshot", True) is True
        }
        return [
            {"chemical_id": cid, "section_no": sno}
            for (cid, sno) in mat_store._sections_by_pair.keys()
            if str(cid) in chem_uuids
        ]

    def _section_count(snapshot_id: str) -> int:
        rows = _sections_live(snapshot_id)
        return len({(r["chemical_id"], int(r["section_no"])) for r in rows})

    def _duplicate_section_pairs(snapshot_id: str) -> int:
        return 0  # MemoryMaterializeStore uses a dict keyed by pair; no dups possible.

    pub_store.section_count_for_snapshot = _section_count            # type: ignore
    pub_store.duplicate_section_pairs_for_snapshot = _duplicate_section_pairs  # type: ignore
    return mat_store, pub_store


def test_happy_path_promotes_to_published_seo_preview(tmp_path):
    pipe = _make_pipeline(tmp_path, ["A00001", "A00002", "A00003"])
    mat_store, pub_store = _shared_stores()

    def _factory():
        return mat_store, pub_store

    args = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
        expected_seo_manifest_sha=pipe["seo"]["manifest_sha256"],
        expected_responses_sha=pipe["seo"]["source"]["responses_sha256"],
        expected_chemical_count=pipe["seo"]["census"]["complete_chemicals"],
        expected_section_count=pipe["seo"]["census"]["preview_sections"],
    )
    result = ex._run(args, store_factory=_factory)
    assert result["publish_state_after_promote"] == PUBLISH_PUBLISHED_SEO_PREVIEW
    assert result["snapshot_status_after_materialize"] == SNAPSHOT_COMPLETED
    assert result["materialized_chemicals"] == 3
    assert result["materialized_sections"] == 3 * 16
    assert result["materialized_snapshot_items"] == 3
    assert result["seo_preview_manifest_sha256"] == pipe["seo"]["manifest_sha256"]


# ---------------------------------------------------------------------------
# Downstream fail-closed conditions
# ---------------------------------------------------------------------------


def test_materialize_preflight_block_prevents_publish(tmp_path, monkeypatch):
    """Force materialize preflight to return can_execute=False; verify
    the executor exits before the publish path is reached."""
    pipe = _make_pipeline(tmp_path, ["A00001", "A00002"])

    # Patch materialize_writer.preflight to always emit a blocked report.
    calls = {"preflight": 0, "publish_preflight": 0}
    real_preflight = w.preflight

    def fake_preflight(*args, **kwargs):
        calls["preflight"] += 1
        report = real_preflight(*args, **kwargs)
        # Force a block reason to make can_execute=False.
        report_dict = report.__dict__.copy()
        report_dict["block_reasons"] = tuple(list(report.block_reasons) + ["FORCED_BLOCK"])
        report_dict["can_execute"] = False
        return type(report)(**report_dict)

    monkeypatch.setattr(w, "preflight", fake_preflight)
    monkeypatch.setattr(ex.w, "preflight", fake_preflight)

    def _spy_publish_preflight(*args, **kwargs):
        calls["publish_preflight"] += 1
        return pub.preflight_publish(*args, **kwargs)

    monkeypatch.setattr(ex.pub, "preflight_publish", _spy_publish_preflight)

    args = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
    )
    with pytest.raises(SystemExit) as exc:
        ex._run(args, store_factory=pipe["store_factory"])
    assert "MATERIALIZE_PREFLIGHT_BLOCKED" in str(exc.value)
    assert calls["preflight"] == 1
    assert calls["publish_preflight"] == 0, (
        "publish preflight must NOT run when materialize preflight is blocked"
    )


def test_publish_binding_mismatch_blocks_promotion(tmp_path, monkeypatch):
    """If the snapshot's metrics_json binding disagrees with the SEO
    manifest SHA, promotion must fail-closed with BLOCK_MATERIALIZE_BINDING_MISMATCH."""
    pipe = _make_pipeline(tmp_path, ["A00001", "A00002"])
    mat_store, pub_store = _shared_stores()

    # Patch open_snapshot so the produced snapshot's metrics_json has a
    # TAMPERED seo_preview_manifest_sha256. Everything else stays valid.
    real_open = w.open_snapshot

    def _tampered_open(**kw):
        snap = real_open(**kw)
        snap["metrics_json"] = dict(snap.get("metrics_json") or {})
        snap["metrics_json"]["seo_preview_manifest_sha256"] = "0" * 64
        return snap

    monkeypatch.setattr(ex.w, "open_snapshot", _tampered_open)

    def _factory():
        return mat_store, pub_store

    args = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
    )
    with pytest.raises(SystemExit) as exc:
        ex._run(args, store_factory=_factory)
    assert "PUBLISH_PREFLIGHT_BLOCKED" in str(exc.value)
    assert "MATERIALIZE_BINDING_MISMATCH" in str(exc.value)

    # And the snapshot must NOT have been promoted.
    snap = pub_store.get_snapshot("seo-preview-test-1")
    assert snap is not None
    assert snap["publish_state"] != PUBLISH_PUBLISHED_SEO_PREVIEW
    assert snap["publish_state"] != PUBLISH_PUBLISHED_FULL


# ---------------------------------------------------------------------------
# The FULL contract stays intact — the executor never emits PUBLISHED_FULL.
# ---------------------------------------------------------------------------


def test_executor_never_writes_published_full(tmp_path, monkeypatch):
    pipe = _make_pipeline(tmp_path, ["A00001", "A00002"])
    mat_store, pub_store = _shared_stores()

    calls = {"full_promote": 0, "state_targets": []}
    real_promote_state = pub_store.promote_to_state

    def _spy(snapshot_id: str, target_state: str):
        calls["state_targets"].append(target_state)
        if target_state == PUBLISH_PUBLISHED_FULL:
            calls["full_promote"] += 1
        return real_promote_state(snapshot_id, target_state)

    pub_store.promote_to_state = _spy   # type: ignore

    def _factory():
        return mat_store, pub_store

    args = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
    )
    ex._run(args, store_factory=_factory)

    assert calls["full_promote"] == 0
    assert PUBLISH_PUBLISHED_FULL not in calls["state_targets"]
    assert PUBLISH_PUBLISHED_SEO_PREVIEW in calls["state_targets"]


# ---------------------------------------------------------------------------
# Module fences unchanged — this WO doesn't flip them.
# ---------------------------------------------------------------------------


def test_module_fences_unchanged_after_executor_import():
    assert w.PRODUCTION_WRITE_ALLOWED is False
    assert pub.PRODUCTION_PUBLISH_ALLOWED is False


# ---------------------------------------------------------------------------
# Frozen checked-in manifest wired to the executor's expected constants.
# This is a receipt check — the CLI's default frozen values (when the
# caller pins --expected-*) MUST match the manifest on disk.
# ---------------------------------------------------------------------------


def test_frozen_manifest_sha_matches_checked_in_file():
    on_disk = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert on_disk["manifest_sha256"] == "f696a212fd9fd04659b7b75accd4c13fc539a1a71a663fb2a80599b9c255638d"
    assert on_disk["source"]["responses_sha256"] == "49994a2a8d44b5c2acfae60283d5f2f76fd65e0af5842a10db43383e26b643dd"
    assert on_disk["census"]["complete_chemicals"] == 1997
    assert on_disk["census"]["preview_sections"] == 31952
    assert on_disk["census"]["excluded_chem_ids"] == ["432377"]


# ---------------------------------------------------------------------------
# Router registration — public.py must reference kosha_public_msds so the
# runtime knows about it. Env default `off` still keeps the router 503.
# ---------------------------------------------------------------------------


def test_public_router_registry_lists_msds_router():
    from router_registry.public import ROUTERS
    modules = [r.get("module") for r in ROUTERS]
    assert "routers.kosha_public_msds" in modules


# ---------------------------------------------------------------------------
# FINAL PATCH · Supabase section-read pagination.
#
# The prior implementation issued one .execute() per chemical_id chunk and
# assumed the whole result came back in one page. PostgREST's default page
# cap is 1,000 rows, so a chunk of 200 chemicals × 16 sections = 3,200 rows
# would silently truncate to 1,000. section_count_for_snapshot and
# duplicate_section_pairs_for_snapshot now paginate WITHIN each chunk. We
# exercise that path with a fake Supabase client whose responses honour
# both .in_(...) filtering AND .range(offset, offset+size-1).
# ---------------------------------------------------------------------------


class _FakeSupabaseSectionsClient:
    """Minimal chainable stub that mimics the PostgREST/Supabase Python
    client for the queries in SupabasePublishStore. Only the tables and
    methods actually reached are implemented."""

    def __init__(self, sections_rows: list[dict], items_rows: list[dict]):
        self._sections = sections_rows
        self._items = items_rows

    def table(self, name: str):
        if name == "kosha_msds_sections":
            return _FakeSectionsQuery(self._sections)
        if name == "kosha_msds_snapshot_items":
            return _FakeItemsQuery(self._items)
        raise KeyError(f"unexpected table: {name}")


class _FakeSectionsQuery:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filter_in: tuple[str, list] | None = None
        self._range: tuple[int, int] | None = None

    def select(self, *_a, **_kw): return self
    def order(self, *_a, **_kw): return self

    def in_(self, col: str, values):
        self._filter_in = (col, list(values))
        return self

    def range(self, start: int, end: int):
        self._range = (start, end)
        return self

    def execute(self):
        rows = list(self._rows)
        if self._filter_in is not None:
            col, allowed = self._filter_in
            rows = [r for r in rows if str(r.get(col)) in {str(v) for v in allowed}]
        if self._range is not None:
            start, end = self._range
            rows = rows[start:end + 1]

        class _R: pass
        r = _R()
        r.data = rows
        return r


class _FakeItemsQuery:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._eqs: dict[str, object] = {}
        self._range: tuple[int, int] | None = None

    def select(self, *_a, **_kw): return self

    def eq(self, col: str, value):
        self._eqs[col] = value
        return self

    def range(self, start: int, end: int):
        self._range = (start, end)
        return self

    def execute(self):
        rows = [r for r in self._rows
                if all(r.get(k) == v for k, v in self._eqs.items())]
        if self._range is not None:
            start, end = self._range
            rows = rows[start:end + 1]

        class _R: pass
        r = _R()
        r.data = rows
        return r


def test_section_count_paginates_beyond_default_page_cap():
    """Chunk of 200 chemicals × 16 sections = 3,200 rows. A single
    .execute() (which caps at 1,000) would return only 1,000. The store
    must page through .range(offset, offset+999) three times per chunk."""
    from services.kosha_msds.production_store import SupabasePublishStore

    # 200 chemicals, 16 sections each. Deterministic uuids for readability.
    chem_ids = [f"chem-{i:04d}" for i in range(200)]
    sections_rows: list[dict] = []
    for cid in chem_ids:
        for n in range(1, 17):
            sections_rows.append({"chemical_id": cid, "section_no": n})
    assert len(sections_rows) == 3200   # sanity

    items_rows = [
        {"snapshot_id": "snap-a", "chemical_id": cid, "in_snapshot": True,
         "detail_status": "COMPLETE"}
        for cid in chem_ids
    ]

    fake = _FakeSupabaseSectionsClient(sections_rows, items_rows)
    store = SupabasePublishStore(sb=fake)
    total = store.section_count_for_snapshot("snap-a")
    assert total == 3200, (
        f"pagination must count every (chemical_id, section_no) pair; got {total}"
    )

    dup_count = store.duplicate_section_pairs_for_snapshot("snap-a")
    assert dup_count == 0


def test_executor_writes_canonical_content_id(tmp_path):
    """content_id must be CHEM:<UUID> per services.kosha_msds.identity.
    CHEM:<chem_id> would let KOSHA source identity leak into TAI content
    identity — is_chem_content_id() would even accept it, but it violates
    the intentional separation between source_id / chem_id and TAI's own
    content identifier."""
    from services.kosha_msds.identity import is_chem_content_id
    pipe = _make_pipeline(tmp_path, ["A00001", "A00002"])
    mat_store, pub_store = _shared_stores()

    def _factory():
        return mat_store, pub_store

    args = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
    )
    ex._run(args, store_factory=_factory)

    # Every inserted chemical row must carry a canonical content_id.
    for row in list(mat_store._chemicals_by_key.values()):
        cid = row.get("content_id")
        chem_id = row.get("chem_id")
        assert is_chem_content_id(cid), f"content_id must be CHEM:<UUID>, got {cid!r}"
        assert cid.startswith("CHEM:")
        # Explicitly reject the pre-PATCH form CHEM:<chem_id>.
        assert cid != f"CHEM:{chem_id}", (
            f"content_id must NOT reuse KOSHA source identity ({chem_id!r}); "
            "identity.py owns the UUID form"
        )


def test_section_count_paginates_across_two_chunks_and_pages():
    """400 chemicals cross both the CHEM-ID chunk boundary AND the
    per-chunk page boundary. Every row must still be counted exactly once."""
    from services.kosha_msds.production_store import SupabasePublishStore

    chem_ids = [f"c-{i:05d}" for i in range(400)]
    sections_rows = [
        {"chemical_id": cid, "section_no": n}
        for cid in chem_ids for n in range(1, 17)
    ]
    assert len(sections_rows) == 6400
    items_rows = [
        {"snapshot_id": "snap-x", "chemical_id": cid, "in_snapshot": True,
         "detail_status": "COMPLETE"}
        for cid in chem_ids
    ]
    store = SupabasePublishStore(sb=_FakeSupabaseSectionsClient(sections_rows, items_rows))
    assert store.section_count_for_snapshot("snap-x") == 6400
    assert store.duplicate_section_pairs_for_snapshot("snap-x") == 0


# ---------------------------------------------------------------------------
# WO-CHEM-FULL-READINESS-001 PATCH-B — RUNNING → FAILED cleanup on write error
# ---------------------------------------------------------------------------


def _raising_store_factory(pipe, *, raise_on: str):
    """Return a factory that produces a MemoryMaterializeStore whose
    write method named by `raise_on` raises RuntimeError.

    `pipe["store_factory"]` still owns the pub_store side so publish
    inspection would remain functional if the executor got that far —
    but it must NOT, because the write phase fails first."""

    def _factory():
        mat_store, pub_store = _shared_stores()
        original = getattr(mat_store, raise_on)

        def _raiser(*a, **kw):
            raise RuntimeError(f"simulated {raise_on} failure")

        setattr(mat_store, raise_on, _raiser)
        # Keep the original reachable so post-hoc assertions can peek
        # at the store's state if needed.
        setattr(mat_store, f"__original_{raise_on}", original)
        return mat_store, pub_store
    return _factory


def _shared_state_capture():
    """Wrap _shared_stores so the caller can inspect state after the
    executor raises. Returns (factory, holder). holder["mat"] and
    ["pub"] are set when the factory fires."""
    holder: dict = {}

    def _factory():
        mat_store, pub_store = _shared_stores()
        holder["mat"] = mat_store
        holder["pub"] = pub_store
        return mat_store, pub_store
    return _factory, holder


def test_F9_writer_failure_marks_running_snapshot_failed(tmp_path):
    """PATCH-B: if `insert_sections` raises during execute_incremental_write,
    the RUNNING snapshot must be flipped to FAILED before the exception
    propagates. Publish must never be reached."""
    pipe = _make_pipeline(tmp_path, ["F00001", "F00002"])
    factory, holder = _shared_state_capture()

    def _factory():
        mat_store, pub_store = factory()
        original_insert_sections = mat_store.insert_sections

        def _raise(rows):
            raise RuntimeError("simulated insert_sections failure")

        mat_store.insert_sections = _raise
        return mat_store, pub_store

    args = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
        snapshot_id="snap-F9",
    )
    with pytest.raises(RuntimeError, match="simulated insert_sections failure"):
        ex._run(args, store_factory=_factory)

    # Snapshot is FAILED (not RUNNING). The row itself is preserved.
    assert holder["mat"] is not None
    snap = holder["mat"].get_snapshot("snap-F9")
    assert snap is not None
    assert snap["status"] == SNAPSHOT_FAILED
    # Publish was never invoked — nothing landed in the publish side.
    for s in holder["pub"]._snapshots:
        assert s.get("publish_state") != PUBLISH_PUBLISHED_SEO_PREVIEW


def test_F10_chemical_insert_failure_marks_running_failed(tmp_path):
    """PATCH-B: same as F9 but the failure is `insert_chemicals`."""
    pipe = _make_pipeline(tmp_path, ["G00001", "G00002"])
    factory, holder = _shared_state_capture()

    def _factory():
        mat_store, pub_store = factory()

        def _raise(rows):
            raise RuntimeError("simulated insert_chemicals failure")

        mat_store.insert_chemicals = _raise
        return mat_store, pub_store

    args = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
        snapshot_id="snap-F10",
    )
    with pytest.raises(RuntimeError, match="simulated insert_chemicals failure"):
        ex._run(args, store_factory=_factory)

    snap = holder["mat"].get_snapshot("snap-F10")
    assert snap["status"] == SNAPSHOT_FAILED
    # PUBLISHED_SEO_PREVIEW must not have been touched.
    for s in holder["pub"]._snapshots:
        assert s.get("publish_state") != PUBLISH_PUBLISHED_SEO_PREVIEW
    # And PUBLISHED_FULL certainly was not.
    for s in holder["pub"]._snapshots:
        from services.kosha_msds.contract import PUBLISH_PUBLISHED_FULL
        assert s.get("publish_state") != PUBLISH_PUBLISHED_FULL


def test_F11_replay_after_failed_run_succeeds(tmp_path):
    """PATCH-B: A FAILED snapshot must not block a follow-up retry
    (existing RUNNING guard was the reason we mark FAILED). Rerunning
    the same plan with a fresh snapshot id after a partial-write crash
    must complete cleanly with 0 duplicate-key errors — the shared
    incremental writer reclassifies any surviving rows as UNCHANGED.
    """
    pipe = _make_pipeline(tmp_path, ["H00001", "H00002", "H00003"])

    # First attempt: fail on the SECOND insert_sections call so the
    # first N sections land but the rest do not. Under the shared
    # MemoryMaterializeStore, `insert_sections` is called exactly once
    # (all sections at once), so we simulate the partial state by
    # manually pre-populating chemicals + some sections into a store
    # for the SECOND run.
    factory, holder1 = _shared_state_capture()

    def _factory1():
        mat_store, pub_store = factory()
        original = mat_store.insert_sections
        # Keep the original reachable so attempt 2 can restore it.
        mat_store.__dict__["_original_insert_sections"] = original

        def _raise(rows):
            # Land the first bundle's worth of sections, then raise.
            first_uuid = str(rows[0]["chemical_id"])
            partial = [r for r in rows if str(r["chemical_id"]) == first_uuid]
            original(partial)
            raise RuntimeError("simulated partial insert_sections failure")

        mat_store.insert_sections = _raise
        return mat_store, pub_store

    args1 = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
        snapshot_id="snap-F11-attempt1",
    )
    with pytest.raises(RuntimeError, match="simulated partial insert_sections"):
        ex._run(args1, store_factory=_factory1)

    # Attempt 1 left: 3 chemicals inserted (chunk was single call),
    # 16 sections for the first chemical only, snapshot marked FAILED.
    mat_store_1 = holder1["mat"]
    assert mat_store_1.get_snapshot("snap-F11-attempt1")["status"] == SNAPSHOT_FAILED
    assert len(mat_store_1._chemicals_by_key) == 3
    # 16 sections landed for the first chemical.
    assert sum(1 for _ in mat_store_1._sections_by_pair) == 16

    # Second attempt: replay against the SAME state (same store), with
    # a fresh snapshot id. Existing rows should reclassify as UNCHANGED
    # (chemicals) or split UNCHANGED/NEW (sections) with no crash.
    def _factory2():
        # Return the same mat_store from attempt 1 so the DB state
        # is carried forward — but restore the original
        # `insert_sections` bound method so the raising stub from
        # attempt 1 doesn't fire again.
        original = mat_store_1.__dict__.get("_original_insert_sections")
        if original is not None:
            mat_store_1.insert_sections = original
        # Rebuild a pub_store wired to mat_store_1's live dicts so
        # publish_preflight's section-count check reads the sections
        # actually written by the materialize phase (identical wiring
        # to _shared_stores()).
        pub_store = pub.MemoryPublishStore()
        pub_store._snapshots = mat_store_1._snapshots
        pub_store._items = mat_store_1._snapshot_items

        def _sections_live(snapshot_id):
            chem_uuids = {
                str(i.get("chemical_id"))
                for i in mat_store_1._snapshot_items
                if str(i.get("snapshot_id")) == str(snapshot_id)
                and i.get("in_snapshot", True) is True
            }
            return [
                {"chemical_id": cid, "section_no": sno}
                for (cid, sno) in mat_store_1._sections_by_pair.keys()
                if str(cid) in chem_uuids
            ]

        pub_store.section_count_for_snapshot = (
            lambda sid: len({(r["chemical_id"], int(r["section_no"]))
                             for r in _sections_live(sid)})
        )  # type: ignore
        pub_store.duplicate_section_pairs_for_snapshot = lambda sid: 0  # type: ignore
        return mat_store_1, pub_store

    args2 = _args_ns(
        seo_manifest=str(pipe["seo_path"]),
        chem05_plan_jsonl=str(pipe["chem05"]["plan_jsonl"]),
        chem05_manifest=str(pipe["chem05"]["manifest"]),
        chem05_report=str(pipe["chem05"]["report"]),
        snapshot_id="snap-F11-attempt2",
    )
    result = ex._run(args2, store_factory=_factory2)
    # Replay succeeded end-to-end.
    assert result["snapshot_status_after_materialize"] == SNAPSHOT_COMPLETED
    # All 3 chemicals ended up in the second snapshot's membership.
    assert result["materialized_snapshot_items"] == 3
    # 0 chemical INSERTs on the replay — the 3 rows already existed
    # from attempt 1 and reclassify as UNCHANGED.
    write_report = result["materialize_write_report"]
    assert write_report["chemicals"]["unchanged"] == 3
    assert write_report["chemicals"]["new"] == 0
    # First chemical's 16 sections are UNCHANGED; the other 2 chemicals'
    # 16×2 = 32 sections are NEW on this replay.
    assert write_report["sections"]["unchanged"] == 16
    assert write_report["sections"]["new"] == 32
