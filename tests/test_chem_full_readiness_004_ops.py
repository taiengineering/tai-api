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
    # read_store._current is an empty list under preview-only publication
    # → chemicals in the FULL slice = 0. (Not None because the read
    # store exists; None would mean "no read store supplied".)
    assert prod["chemicals"] == 0
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
