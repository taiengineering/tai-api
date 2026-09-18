"""WO-CHEM-FULL-READINESS-004 — MSDS ops observability tests.

Read-only fixture tests for the ops collector. Verifies O1..O8:
production snapshot / hydration / full-readiness / dictionary
binding (v2 / v1 / offline) / public mode / no-mutation invariants.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from services.kosha_msds import ops, publish as pub, read
from services.kosha_msds.contract import (
    ENUMERATION_FULL_OFFICIAL,
    PUBLIC_MODE_ENV_VAR,
    PUBLIC_MODE_FULL,
    PUBLIC_MODE_OFF,
    PUBLIC_MODE_SEO_PREVIEW,
    PUBLISH_NOT_PUBLISHED,
    PUBLISH_PUBLISHED_FULL,
    PUBLISH_PUBLISHED_SEO_PREVIEW,
    SNAPSHOT_COMPLETED,
    SNAPSHOT_FAILED,
    SNAPSHOT_RUNNING,
)


PREVIEW_CHEM = 1_997
PREVIEW_SEC = PREVIEW_CHEM * 16   # 31,952
FULL_CHEM = 20_568
FULL_SEC = 329_088


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _snap(id: str, *, publish_state=PUBLISH_PUBLISHED_SEO_PREVIEW,
          status=SNAPSHOT_COMPLETED,
          expected=PREVIEW_CHEM, discovered=PREVIEW_CHEM,
          completed_at="2026-09-18T05:00:00Z") -> dict:
    return {
        "id": id, "source_id": "KOSHA_MSDS", "run_type": "FULL_SYNC",
        "status": status,
        "enumeration_mode": ENUMERATION_FULL_OFFICIAL,
        "publish_state": publish_state,
        "expected_count": expected,
        "discovered_count": discovered,
        "started_at": "2026-09-18T04:00:00Z",
        "completed_at": completed_at,
        "metrics_json": {
            "adapter_version": "CHEM05_V1",
            "materialize_plan_sha256": "plan-sem-sha",
            "responses_sha256": "resp-sha",
        },
    }


def _preview_publish_store() -> pub.MemoryPublishStore:
    """Preview-shaped store: 1 completed PUBLISHED_SEO_PREVIEW snap,
    with 1,997 membership rows and 31,952 (chem, sec) section rows."""
    snap = _snap("snap-preview")
    items = [
        {"snapshot_id": "snap-preview", "chemical_id": f"uu-{i:05d}",
         "detail_status": "COMPLETE", "in_snapshot": True}
        for i in range(PREVIEW_CHEM)
    ]
    sections = [
        {"chemical_id": f"uu-{i:05d}", "section_no": n,
         "section_hash": f"h-{i}-{n}", "result_code": "00"}
        for i in range(PREVIEW_CHEM) for n in range(1, 17)
    ]
    return pub.MemoryPublishStore(
        snapshots=[snap], snapshot_items=items, sections=sections,
    )


def _preview_read_store() -> read.MemoryMsdsReadStore:
    """FULL slice empty; preview slice = 1,997."""
    preview_rows = [
        {"id": f"uu-{i:05d}", "content_id": f"CHEM:uu-{i:05d}",
         "source_id": "KOSHA_MSDS", "source_key": f"P{i:05d}",
         "chem_id": f"P{i:05d}", "identity_status": "READY",
         "chemical_name_ko": f"화학{i}", "chemical_name_en": f"Chem{i}",
         "cas_no": None, "ke_no": None, "en_no": None, "un_no": None,
         "source_content_hash": f"sha-{i}",
         "source_dataset_url": "https://www.data.go.kr/data/15157612/openapi.do",
         "snapshot_id": "snap-preview"}
        for i in range(PREVIEW_CHEM)
    ]
    return read.MemoryMsdsReadStore(current_rows=[], preview_rows=preview_rows)


# ---------------------------------------------------------------------------
# O1 — production preview counts
# ---------------------------------------------------------------------------


def test_O1_preview_production_counts_reported():
    pub_store = _preview_publish_store()
    read_store = _preview_read_store()
    result = ops.collect_status(
        artifact_dir=None, live_base_url=None,
        publish_store=pub_store, read_store=read_store,
        env={},  # unset public mode → OFF
        http_get=lambda url, timeout=5.0: {},
    )
    prod = result["production_db"]
    pubn = result["publication"]
    assert prod["preview_current"] == PREVIEW_CHEM
    assert prod["full_current"] == 0
    assert prod["sections"] == PREVIEW_SEC
    # WO-CHEM-FULL-READINESS-004 PATCH-1 §A: chemicals reports the
    # authoritative row count in kosha_msds_chemicals (1,997 rows
    # currently, all in the preview publication).
    assert prod["chemicals"] == PREVIEW_CHEM
    assert pubn["preview_count"] == 1
    assert pubn["full_count"] == 0
    assert pubn["latest_preview_snapshot"]["id"] == "snap-preview"
    assert pubn["latest_full_snapshot"] is None


# ---------------------------------------------------------------------------
# O2 — hydration status against synthetic artifact
# ---------------------------------------------------------------------------


def test_O2_hydration_status_from_artifact(tmp_path):
    """Synthetic checkpoint + run_report + responses fragment models the
    real 31,961 / 297,127 state (frozen baseline of Batch-2 receipt)."""
    art = tmp_path / "official_v12"
    art.mkdir()

    # Small responses.jsonl covering 3 chemicals fully + 1 partial —
    # models the shape of the real 1,997/1 preview state deep-scan.
    payloads = []
    for i in range(1, 4):
        for n in range(1, 17):
            payloads.append({"chemId": f"COMP{i:03d}", "sectionNo": n})
    # 1 chemical with only 15/16 sections → INCOMPLETE
    for n in range(1, 16):
        payloads.append({"chemId": "INCP001", "sectionNo": n})
    (art / "responses.jsonl").write_text(
        "\n".join(json.dumps(p) for p in payloads) + "\n", encoding="utf-8",
    )

    (art / "checkpoint.json").write_text(json.dumps({
        "queue_sha256": "queue-sha",
        "queue_rows": 329_088,
        "next_queue_index": 31_961,
        "start_completed": 361,
        "new_success": 31_600,
        "new_official_empty": 0,
        "new_errors": 1,
        "http_requests": 31_601,
        "http_429": 1,
        "result_code_22": 0,
        "result_code_23": 0,
        "per_section_call_count": {},
        "last_completed_chemId": "432377",
        "last_completed_sectionNo": 9,
        "stop_reason": "QUOTA_LIMIT",
        "updated_at": "2026-09-18T00:28:09Z",
    }), encoding="utf-8")

    (art / "run_report.json").write_text(json.dumps({
        "WO": "WO-CHEM-04-OFFICIAL-HYDRATE-V12-001",
        "queue_sha256": "queue-sha",
        "queue_rows": 329_088,
        "total_completed": 31_961,
        "remaining": 297_127,
        "stop_reason": "QUOTA_LIMIT",
        "ended_at": "2026-09-18T00:28:09Z",
    }), encoding="utf-8")

    result = ops.collect_status(
        artifact_dir=str(art), live_base_url=None,
        publish_store=pub.MemoryPublishStore(),
        read_store=None, env={},
        http_get=lambda url, timeout=5.0: {},
    )
    h = result["hydration"]
    assert h["status"] == "OK"
    assert h["queue_total"] == 329_088
    assert h["completed"] == 31_961
    assert h["remaining"] == 297_127
    assert h["last_terminal_reason"] == "QUOTA_LIMIT"
    assert h["last_run_at"] == "2026-09-18T00:28:09Z"
    # Deep scan of the synthetic responses: 3 complete + 1 incomplete = 4 unique.
    assert h["unique_chemicals"] == 4
    assert h["complete_chemicals"] == 3
    assert h["incomplete_chemicals"] == 1
    # Next pending: after chemId=432377 sec=9 → sec=10.
    assert h["next_pending_chem_id"] == "432377"
    assert h["next_pending_section"] == 10
    # Byte-level responses SHA is reported.
    expected_sha = hashlib.sha256(
        (art / "responses.jsonl").read_bytes()
    ).hexdigest()
    assert h["responses_sha256"] == expected_sha


def test_O2b_artifact_missing_reports_status():
    result = ops.collect_status(
        artifact_dir="/does/not/exist", live_base_url=None,
        publish_store=pub.MemoryPublishStore(),
        env={}, http_get=lambda url, timeout=5.0: {},
    )
    assert result["hydration"]["status"] == "ARTIFACT_NOT_AVAILABLE"
    # Alert surfaced.
    codes = [a["code"] for a in result["alerts"]]
    assert ops.ALERT_HYDRATION_ARTIFACT_MISSING in codes


# ---------------------------------------------------------------------------
# O3 — FULL_READY=false with NO_FULL_CANDIDATE
# ---------------------------------------------------------------------------


def test_O3_full_readiness_no_full_candidate():
    """Preview snapshot exists but no COMPLETED / FULL_OFFICIAL /
    NOT_PUBLISHED candidate exists → NO_FULL_CANDIDATE."""
    pub_store = _preview_publish_store()
    result = ops.collect_status(
        artifact_dir=None, live_base_url=None,
        publish_store=pub_store, env={},
        http_get=lambda url, timeout=5.0: {},
    )
    fr = result["full_readiness"]
    assert fr["ready"] is False
    assert fr["reason"] == "NO_FULL_CANDIDATE"
    assert fr["snapshot_id"] is None


# ---------------------------------------------------------------------------
# O4 — search dictionary v2 binding
# ---------------------------------------------------------------------------


def test_O4_dictionary_v2_match():
    """Stub live GETs so /health returns the v2 snapshot id and
    /lookup returns 물질안전보건자료 for MSDS + SDS."""
    def _fake_get(url: str, timeout=5.0):
        if "/health" in url:
            return {"snapshot": "SEARCH-DICT-LEGPROD-2026-09-16",
                    "subjects": 471, "indexed_terms": 495}
        if "/lookup" in url:
            return {"items": [{"subject_type": "CHEM_TERM",
                                "subject_key": "물질안전보건자료",
                                "matched_term": url.split("q=")[1].split("&")[0]}]}
        return {}

    result = ops.collect_status(
        artifact_dir=None, live_base_url="https://api.example",
        publish_store=pub.MemoryPublishStore(), env={},
        http_get=_fake_get,
    )
    d = result["search_dictionary"]
    assert d["binding"] == ops.BINDING_V2_MATCH
    assert d["runtime_snapshot"] == "SEARCH-DICT-LEGPROD-2026-09-16"
    assert d["subjects"] == 471
    assert d["indexed_terms"] == 495
    assert d["chem_term_msds_matched"] is True
    assert d["chem_term_sds_matched"] is True
    # No V1_OR_OTHER alert.
    codes = [a["code"] for a in result["alerts"]]
    assert ops.ALERT_DICTIONARY_RUNTIME_NOT_V2 not in codes


# ---------------------------------------------------------------------------
# O5 — search dictionary v1 or other snapshot
# ---------------------------------------------------------------------------


def test_O5_dictionary_v1_or_other():
    def _fake_get(url: str, timeout=5.0):
        if "/health" in url:
            return {"snapshot": "SEARCH-DICT-SEED-V1-2026-01-01",
                    "subjects": 100, "indexed_terms": 100}
        if "/lookup" in url:
            return {"items": []}  # no CHEM_TERM in v1
        return {}

    result = ops.collect_status(
        artifact_dir=None, live_base_url="https://api.example",
        publish_store=pub.MemoryPublishStore(), env={},
        http_get=_fake_get,
    )
    d = result["search_dictionary"]
    assert d["binding"] == ops.BINDING_V1_OR_OTHER
    assert d["chem_term_msds_matched"] is False
    codes = [a["code"] for a in result["alerts"]]
    assert ops.ALERT_DICTIONARY_RUNTIME_NOT_V2 in codes


# ---------------------------------------------------------------------------
# O6 — live HTTP unavailable
# ---------------------------------------------------------------------------


def test_O6_live_http_unavailable_returns_unverified_network():
    def _raise(url: str, timeout=5.0):
        raise ConnectionError("simulated network failure")

    # CLI must not crash; just report UNVERIFIED_NETWORK.
    result = ops.collect_status(
        artifact_dir=None, live_base_url="https://api.example",
        publish_store=pub.MemoryPublishStore(), env={},
        http_get=_raise,
    )
    d = result["search_dictionary"]
    assert d["binding"] == ops.BINDING_UNVERIFIED_NETWORK
    assert "simulated network failure" in (d["error"] or "")
    assert d["runtime_snapshot"] is None
    # Absence of live-base-url also yields UNVERIFIED_NETWORK.
    result2 = ops.collect_status(
        artifact_dir=None, live_base_url=None,
        publish_store=pub.MemoryPublishStore(), env={},
    )
    assert result2["search_dictionary"]["binding"] == ops.BINDING_UNVERIFIED_NETWORK


# ---------------------------------------------------------------------------
# O7 — unknown public mode failsafe alert
# ---------------------------------------------------------------------------


def test_O7_unknown_public_mode_yields_failsafe_alert():
    result = ops.collect_status(
        artifact_dir=None, live_base_url=None,
        publish_store=pub.MemoryPublishStore(),
        env={PUBLIC_MODE_ENV_VAR: "garbage_mode_value"},
        http_get=lambda url, timeout=5.0: {},
    )
    pr = result["public_runtime"]
    assert pr["resolved_mode"] == PUBLIC_MODE_OFF
    assert pr["is_failsafe_off"] is True
    codes = [a["code"] for a in result["alerts"]]
    assert ops.ALERT_PUBLIC_MODE_FAILSAFE_OFF in codes


def test_O7b_full_mode_without_full_publication_yields_critical_alert():
    """Public mode=full but there's no PUBLISHED_FULL snapshot →
    CRITICAL alert (means router is serving from an empty FULL view)."""
    pub_store = _preview_publish_store()  # only PUBLISHED_SEO_PREVIEW
    result = ops.collect_status(
        artifact_dir=None, live_base_url=None,
        publish_store=pub_store,
        env={PUBLIC_MODE_ENV_VAR: PUBLIC_MODE_FULL},
        http_get=lambda url, timeout=5.0: {},
    )
    codes = [a["code"] for a in result["alerts"]]
    assert ops.ALERT_FULL_MODE_WITHOUT_FULL_PUBLICATION in codes
    critical = next(a for a in result["alerts"]
                    if a["code"] == ops.ALERT_FULL_MODE_WITHOUT_FULL_PUBLICATION)
    assert critical["severity"] == "CRIT"


# ---------------------------------------------------------------------------
# O8 — read-only invariant: no store mutation methods invoked
# ---------------------------------------------------------------------------


class _NoMutationPublishStore(pub.MemoryPublishStore):
    """Wraps MemoryPublishStore and traps every write method with a
    call counter that also fails the test if invoked."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.mutation_calls = 0

    def promote_to_published_full(self, snapshot_id):
        self.mutation_calls += 1
        pytest.fail(f"ops must not call promote_to_published_full({snapshot_id!r})")

    def demote_snapshot(self, snapshot_id):
        self.mutation_calls += 1
        pytest.fail(f"ops must not call demote_snapshot({snapshot_id!r})")

    def insert_snapshot(self, snapshot):
        self.mutation_calls += 1
        pytest.fail("ops must not call insert_snapshot")

    def insert_chemicals(self, rows):
        self.mutation_calls += 1
        pytest.fail("ops must not call insert_chemicals")

    def insert_sections(self, rows):
        self.mutation_calls += 1
        pytest.fail("ops must not call insert_sections")

    def insert_snapshot_items(self, rows):
        self.mutation_calls += 1
        pytest.fail("ops must not call insert_snapshot_items")

    def update_snapshot_status(self, snapshot_id, status):
        self.mutation_calls += 1
        pytest.fail("ops must not call update_snapshot_status")


def test_O8_read_only_guard_never_mutates_store():
    snap = _snap("snap-preview")
    items = [{"snapshot_id": "snap-preview", "chemical_id": "uu-01",
              "detail_status": "COMPLETE", "in_snapshot": True}]
    sections = [{"chemical_id": "uu-01", "section_no": n, "section_hash": f"h-{n}"}
                for n in range(1, 17)]
    guarded = _NoMutationPublishStore(
        snapshots=[snap], snapshot_items=items, sections=sections,
    )
    result = ops.collect_status(
        artifact_dir=None, live_base_url=None,
        publish_store=guarded, env={},
        http_get=lambda url, timeout=5.0: {},
    )
    # No pytest.fail was raised → guaranteed 0 mutation calls.
    assert guarded.mutation_calls == 0
    # And the status was still assembled.
    assert result["publication"]["preview_count"] == 1


# ---------------------------------------------------------------------------
# Extra: CLI wiring
# ---------------------------------------------------------------------------


def test_cli_smoke_no_db_no_live_url(capsys, monkeypatch):
    """The CLI should run cleanly with --no-db and no --live-base-url,
    printing a JSON payload and exiting 0. Simulates the developer
    scenario where they just want a shape check."""
    monkeypatch.delenv(PUBLIC_MODE_ENV_VAR, raising=False)
    from tools.chem_ops import status as cli
    rc = cli.main([
        "--no-db", "--no-deep-scan",
        "--artifact-dir", "/does/not/exist",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "hydration" in parsed
    assert "production_db" in parsed
    assert "publication" in parsed
    assert "public_runtime" in parsed
    assert "search_dictionary" in parsed
    assert "full_readiness" in parsed
    assert "alerts" in parsed
    # No live-base-url → UNVERIFIED_NETWORK.
    assert parsed["search_dictionary"]["binding"] == ops.BINDING_UNVERIFIED_NETWORK


# ---------------------------------------------------------------------------
# PATCH-1 §A/§B/§F — Supabase-shaped production path
# ---------------------------------------------------------------------------


class _FakeProductionPublishStore:
    """Publish store that mimics the SupabasePublishStore interface but
    has NONE of the memory-only `_snapshots` / `_items` / `_sections`
    attributes. This is the shape ops.py hits in production.
    """

    def __init__(self, *, counts: dict, snapshots: list[dict]):
        self._counts = counts
        self._snapshots_data = snapshots  # only for latest_published_snapshot resolution
        self.mutation_calls = 0

    # -- census methods (matches SupabasePublishStore contract) --
    def count_chemicals(self):
        return self._counts.get("chemicals", 0)

    def count_sections(self):
        return self._counts.get("sections", 0)

    def count_snapshots(self):
        return self._counts.get("snapshots", 0)

    def count_snapshot_items(self):
        return self._counts.get("snapshot_items", 0)

    def count_snapshots_by_status(self, status):
        key = {SNAPSHOT_RUNNING: "running",
               SNAPSHOT_COMPLETED: "completed",
               SNAPSHOT_FAILED: "failed"}.get(status, status)
        return self._counts.get(key, 0)

    def count_snapshots_by_publish_state(self, state):
        key = {PUBLISH_PUBLISHED_SEO_PREVIEW: "preview_publish",
               PUBLISH_PUBLISHED_FULL: "full_publish",
               PUBLISH_NOT_PUBLISHED: "not_published"}.get(state, state)
        return self._counts.get(key, 0)

    def find_full_candidate(self):
        for s in self._snapshots_data:
            if (s.get("status") == SNAPSHOT_COMPLETED
                    and s.get("enumeration_mode") == ENUMERATION_FULL_OFFICIAL
                    and s.get("publish_state") == PUBLISH_NOT_PUBLISHED):
                return dict(s)
        return None

    def get_snapshot(self, snapshot_id):
        for s in self._snapshots_data:
            if str(s.get("id")) == str(snapshot_id):
                return dict(s)
        return None

    def latest_published_snapshot(self, *, publication_scope):
        from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
        want = (PUBLISH_PUBLISHED_SEO_PREVIEW
                if publication_scope == PUBLICATION_SCOPE_SEO_PREVIEW
                else PUBLISH_PUBLISHED_FULL)
        candidates = [
            s for s in self._snapshots_data if s.get("publish_state") == want
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda s: (s.get("completed_at") or "",
                           s.get("started_at") or ""), reverse=True,
        )
        return dict(candidates[0])

    # Any mutation is a bug — this is a status observer, not a writer.
    def _fail(self, *a, **kw):
        self.mutation_calls += 1
        pytest.fail("ops must never invoke a mutation method")

    insert_snapshot = _fail
    update_snapshot_status = _fail
    promote_to_state = _fail
    promote_to_published_full = _fail
    demote_snapshot = _fail

    # For publish-preflight fallbacks (only reached when a real
    # candidate exists and is_full_ready is invoked).
    def snapshot_items(self, snapshot_id):
        return []  # empty on this fake — preflight will BLOCK, that's fine

    def section_count_for_snapshot(self, snapshot_id):
        return 0

    def duplicate_section_pairs_for_snapshot(self, snapshot_id):
        return 0


class _FakeProductionReadStore:
    """Read store shape mimicking SupabaseMsdsReadStore. No _current /
    _preview lists — only the census method."""

    def __init__(self, *, preview_current: int, full_current: int):
        self._preview_current = preview_current
        self._full_current = full_current

    def count_current(self, *, scope):
        from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
        return (self._preview_current
                if scope == PUBLICATION_SCOPE_SEO_PREVIEW
                else self._full_current)


def _production_baseline_stores():
    """WO baseline: chemicals=1997, sections=31952, snapshots=2,
    snapshot_items=1997, preview_current=1997, full_current=0,
    running=0, failed=1, preview_publish=1, full_publish=0."""
    snapshots = [
        # PUBLISHED_SEO_PREVIEW (the live one).
        {"id": "snap-preview-live",
         "status": SNAPSHOT_COMPLETED,
         "enumeration_mode": ENUMERATION_FULL_OFFICIAL,
         "publish_state": PUBLISH_PUBLISHED_SEO_PREVIEW,
         "expected_count": 1997, "discovered_count": 1997,
         "completed_at": "2026-09-18T05:00:00Z",
         "started_at": "2026-09-18T04:00:00Z"},
        # A prior FAILED snapshot — this is what P4 must surface.
        {"id": "snap-failed-1",
         "status": SNAPSHOT_FAILED,
         "enumeration_mode": ENUMERATION_FULL_OFFICIAL,
         "publish_state": PUBLISH_NOT_PUBLISHED,
         "expected_count": 1997, "discovered_count": 1500,
         "completed_at": None,
         "started_at": "2026-09-15T02:00:00Z"},
    ]
    counts = {
        "chemicals": 1997, "sections": 31952,
        "snapshots": 2, "snapshot_items": 1997,
        "running": 0, "failed": 1, "completed": 1,
        "preview_publish": 1, "full_publish": 0,
    }
    publish_store = _FakeProductionPublishStore(
        counts=counts, snapshots=snapshots,
    )
    read_store = _FakeProductionReadStore(
        preview_current=1997, full_current=0,
    )
    return publish_store, read_store


def test_F_supabase_shape_production_counts_correct():
    """Fake Supabase-shaped stores (no _snapshots / _items / _sections
    / _current / _preview attributes) still yield the WO's live
    baseline counts. Proves the CLI reports real numbers in production.
    """
    pub_store, read_store = _production_baseline_stores()
    result = ops.collect_status(
        artifact_dir=None, live_base_url=None,
        publish_store=pub_store, read_store=read_store,
        env={}, http_get=lambda url, timeout=5.0: {},
    )
    prod = result["production_db"]
    assert prod["chemicals"] == 1997
    assert prod["sections"] == 31952
    assert prod["snapshots"] == 2
    assert prod["snapshot_items"] == 1997
    assert prod["preview_current"] == 1997
    assert prod["full_current"] == 0
    assert prod["running_snapshots"] == 0
    assert prod["failed_snapshots"] == 1
    pubn = result["publication"]
    assert pubn["preview_count"] == 1
    assert pubn["full_count"] == 0
    assert (pubn["latest_preview_snapshot"] or {}).get("id") == "snap-preview-live"
    assert pubn["latest_full_snapshot"] is None
    # And the FAILED snapshot is now surfaced as an alert.
    codes = [a["code"] for a in result["alerts"]]
    assert ops.ALERT_FAILED_SNAPSHOT_PRESENT in codes
    # No mutation reached the store.
    assert pub_store.mutation_calls == 0


def test_F_supabase_shape_full_candidate_discovery_works():
    """A production-shaped store that has a valid FULL candidate
    surfaces it and lets `is_full_ready` decide. No _snapshots peek."""
    snapshots = [
        {"id": "snap-full-candidate",
         "status": SNAPSHOT_COMPLETED,
         "enumeration_mode": ENUMERATION_FULL_OFFICIAL,
         "publish_state": PUBLISH_NOT_PUBLISHED,
         "expected_count": ops.EXPECTED_CHEMICAL_COUNT,
         "discovered_count": ops.EXPECTED_CHEMICAL_COUNT,
         "completed_at": "2026-10-01T02:00:00Z",
         "started_at": "2026-10-01T01:00:00Z"},
    ]
    counts = {"chemicals": ops.EXPECTED_CHEMICAL_COUNT,
              "sections": ops.EXPECTED_QUEUE_ROWS,
              "snapshots": 1, "snapshot_items": ops.EXPECTED_CHEMICAL_COUNT}
    pub_store = _FakeProductionPublishStore(
        counts=counts, snapshots=snapshots,
    )
    result = ops.collect_status(
        artifact_dir=None, live_base_url=None,
        publish_store=pub_store,
        env={}, http_get=lambda url, timeout=5.0: {},
    )
    fr = result["full_readiness"]
    # A candidate was found — reason is NOT NO_FULL_CANDIDATE anymore.
    assert fr["reason"] != "NO_FULL_CANDIDATE"
    assert fr["snapshot_id"] == "snap-full-candidate"
    # is_full_ready delegates to preflight_publish; with the fake
    # store returning zero snapshot_items / sections, it BLOCKS.
    # (That's the correct behavior — the FAKE has no membership,
    # so eligibility fails. The point of this test is proving
    # candidate discovery reaches the eligibility gate.)
    assert fr["ready"] is False
    assert fr["reason"] == "PREFLIGHT_BLOCKED"


def test_F_supabase_shape_no_candidate_reports_no_full_candidate():
    """No COMPLETED / FULL_OFFICIAL / NOT_PUBLISHED snapshot exists
    → reason = NO_FULL_CANDIDATE (not an error)."""
    pub_store, read_store = _production_baseline_stores()
    result = ops.collect_status(
        artifact_dir=None, live_base_url=None,
        publish_store=pub_store, read_store=read_store,
        env={}, http_get=lambda url, timeout=5.0: {},
    )
    fr = result["full_readiness"]
    assert fr["ready"] is False
    assert fr["reason"] == "NO_FULL_CANDIDATE"
    assert fr["snapshot_id"] is None


# ---------------------------------------------------------------------------
# PATCH-1 §C — /search-dict envelope unwrap
# ---------------------------------------------------------------------------


def test_C_search_dict_wrapped_envelope_v2_match():
    """Live router response uses {status:success, data:{...}} envelope.
    ops.py's collector must unwrap and NOT return runtime_snapshot=None.
    """
    def _wrapped_get(url: str, timeout=5.0):
        if "/health" in url:
            return {
                "status": "success",
                "data": {
                    "snapshot": "SEARCH-DICT-LEGPROD-2026-09-16",
                    "subjects": 471,
                    "indexed_terms": 486,
                },
            }
        if "/lookup" in url:
            return {
                "status": "success",
                "data": {
                    "items": [{
                        "subject_type": "CHEM_TERM",
                        "subject_key": "물질안전보건자료",
                        "matched_term": url.split("q=")[1].split("&")[0],
                    }],
                },
            }
        return {"status": "success", "data": {}}

    result = ops.collect_status(
        artifact_dir=None, live_base_url="https://api.example",
        publish_store=pub.MemoryPublishStore(), env={},
        http_get=_wrapped_get,
    )
    d = result["search_dictionary"]
    assert d["binding"] == ops.BINDING_V2_MATCH
    assert d["runtime_snapshot"] == "SEARCH-DICT-LEGPROD-2026-09-16"
    assert d["subjects"] == 471
    assert d["indexed_terms"] == 486
    assert d["chem_term_msds_matched"] is True
    assert d["chem_term_sds_matched"] is True


def test_C_search_dict_raw_shape_still_works():
    """Injected test doubles can also return raw (unwrapped) payloads.
    Both shapes must map to the same collected result. This preserves
    the O4 test's original fixture semantics."""
    def _raw_get(url: str, timeout=5.0):
        if "/health" in url:
            return {"snapshot": "SEARCH-DICT-LEGPROD-2026-09-16",
                    "subjects": 471, "indexed_terms": 495}
        if "/lookup" in url:
            return {"items": [{"subject_type": "CHEM_TERM",
                                "subject_key": "물질안전보건자료",
                                "matched_term": url.split("q=")[1].split("&")[0]}]}
        return {}

    result = ops.collect_status(
        artifact_dir=None, live_base_url="https://api.example",
        publish_store=pub.MemoryPublishStore(), env={},
        http_get=_raw_get,
    )
    assert result["search_dictionary"]["binding"] == ops.BINDING_V2_MATCH


# ---------------------------------------------------------------------------
# PATCH-1 §D — hydration next_pending across the section=16 boundary
# ---------------------------------------------------------------------------


def test_D_next_pending_at_section_16_boundary_via_queue(tmp_path, monkeypatch):
    """When last_completed_section == 16, the runner's own
    `next_queue_index` (checkpoint) points to the next chemId in the
    queue file — that's the authoritative next pending."""
    # Build a tiny queue file at the runner-owned canonical path.
    queue_dir = tmp_path / "artifacts/chem04/content/queues"
    queue_dir.mkdir(parents=True)
    queue_path = queue_dir / "hydration_queue.jsonl"
    # Rows 0-15: chemA sections 1..16; rows 16-31: chemB sections 1..16.
    rows = ([{"chemId": "chemA", "sectionNo": n} for n in range(1, 17)]
            + [{"chemId": "chemB", "sectionNo": n} for n in range(1, 17)])
    queue_path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8",
    )
    # Point ops.py at this tmp_path as its CWD-relative resolution root.
    monkeypatch.chdir(tmp_path)

    # Synthetic checkpoint: runner just finished chemA's section 16
    # (last_completed pair). next_queue_index=16 → first pending is
    # chemB / section 1.
    art = tmp_path / "artifacts/chem04/official_v12"
    art.mkdir(parents=True)
    (art / "checkpoint.json").write_text(json.dumps({
        "queue_sha256": "queue-sha", "queue_rows": 32,
        "next_queue_index": 16,
        "start_completed": 0, "new_success": 16,
        "new_official_empty": 0, "new_errors": 0,
        "last_completed_chemId": "chemA",
        "last_completed_sectionNo": 16,
        "stop_reason": None,
        "updated_at": "2026-09-18T01:00:00Z",
    }), encoding="utf-8")
    (art / "run_report.json").write_text(json.dumps({
        "total_completed": 16, "remaining": 16,
        "stop_reason": None, "ended_at": "2026-09-18T01:00:00Z",
    }), encoding="utf-8")

    result = ops.collect_status(
        artifact_dir=str(art), live_base_url=None,
        publish_store=pub.MemoryPublishStore(), env={},
        http_get=lambda url, timeout=5.0: {},
    )
    h = result["hydration"]
    assert h["next_pending_chem_id"] == "chemB"
    assert h["next_pending_section"] == 1


def test_D_next_pending_current_baseline_still_432377_10(tmp_path):
    """With last_completed=chemId 432377 / sec 9 and no queue file
    present, the checkpoint-arithmetic fallback still resolves to
    432377 / sec 10 — the current preview baseline."""
    art = tmp_path / "art"
    art.mkdir()
    (art / "checkpoint.json").write_text(json.dumps({
        "queue_sha256": "queue-sha", "queue_rows": 329088,
        "next_queue_index": 31961,
        "start_completed": 361, "new_success": 31600,
        "new_official_empty": 0, "new_errors": 1,
        "last_completed_chemId": "432377",
        "last_completed_sectionNo": 9,
        "stop_reason": "QUOTA_LIMIT",
        "updated_at": "2026-09-18T00:28:09Z",
    }), encoding="utf-8")
    (art / "run_report.json").write_text(json.dumps({
        "total_completed": 31961, "remaining": 297127,
        "stop_reason": "QUOTA_LIMIT",
        "ended_at": "2026-09-18T00:28:09Z",
    }), encoding="utf-8")
    result = ops.collect_status(
        artifact_dir=str(art), live_base_url=None,
        publish_store=pub.MemoryPublishStore(), env={},
        http_get=lambda url, timeout=5.0: {},
    )
    h = result["hydration"]
    assert h["next_pending_chem_id"] == "432377"
    assert h["next_pending_section"] == 10


# ---------------------------------------------------------------------------
# PATCH-1 §E — RUNNING alert renamed to _PRESENT
# ---------------------------------------------------------------------------


def test_E_running_alert_renamed():
    """The alert code is RUNNING_SNAPSHOT_PRESENT — no time-threshold
    judgement implied. The old STALE constant is gone."""
    assert not hasattr(ops, "ALERT_RUNNING_SNAPSHOT_STALE")
    assert ops.ALERT_RUNNING_SNAPSHOT_PRESENT == "RUNNING_SNAPSHOT_PRESENT"

    # And a store with a RUNNING snapshot triggers the new alert.
    snapshots = [
        {"id": "snap-running",
         "status": SNAPSHOT_RUNNING,
         "enumeration_mode": ENUMERATION_FULL_OFFICIAL,
         "publish_state": PUBLISH_NOT_PUBLISHED,
         "started_at": "2026-09-18T00:00:00Z"},
    ]
    pub_store = _FakeProductionPublishStore(
        counts={"running": 1, "failed": 0, "chemicals": 0, "sections": 0,
                "snapshots": 1, "snapshot_items": 0},
        snapshots=snapshots,
    )
    result = ops.collect_status(
        artifact_dir=None, live_base_url=None,
        publish_store=pub_store, env={},
        http_get=lambda url, timeout=5.0: {},
    )
    codes = [a["code"] for a in result["alerts"]]
    assert ops.ALERT_RUNNING_SNAPSHOT_PRESENT in codes


# ---------------------------------------------------------------------------
# Original safety check (guard against docstring false positives)
# ---------------------------------------------------------------------------


def test_no_new_engine_no_kosha_safety_materials_coupling():
    """ops.py must not fork the search / publish / hydration engines,
    and must not depend on the kosha_safety_materials domain. Checks
    are against import statements, not docstring mentions."""
    src = Path(ops.__file__).read_text(encoding="utf-8")
    # Composer only — never re-implements the eligibility check.
    assert "def is_full_ready" not in src
    # No safety-materials domain dependency in imports.
    for banned in ("from services.kosha_safety_materials",
                   "import services.kosha_safety_materials"):
        assert banned not in src
    # No hydration API — uses artifacts only (grep for actual imports,
    # not docstring context).
    for banned in ("from tools.chem04.official_hydrate_v12",
                   "import tools.chem04.official_hydrate_v12"):
        assert banned not in src
