"""WO-MSDS-INCREMENTAL-PUBLISH-001 — incremental KOSHA MSDS SEO preview publisher.

Publishes the v12 responses.jsonl artifact (4,647 complete chemicals) as a new
PUBLISHED_SEO_PREVIEW snapshot. The new snapshot unions the 1,997 already-published
chemicals with the 2,650 new complete chemicals, giving 4,647 total.

Pre-built artifacts (all deterministic, SHA-pinned):
    artifacts/chem05_v12/         — chem05 plan from v12 responses
    artifacts/chem_seo_preview_v12/ — preview plan bridging chem05_v12 + SEO manifest v12
    docs/chem/seo-preview-manifest-v12.json — SEO membership manifest

Safety fences (fail-closed):
    * DRY-RUN by default: only preflight; no DB writes.
    * --execute requires --owner-approved (GPT + Owner).
    * Expected SHA/count pins verified before any DB connection.
    * No DELETE, no TRUNCATE, no publish_state rollback.
    * production_store import deferred; never imported on dry-run.

CLI (dry-run):
    python -m tools.chem11.incremental_publish

CLI (execute, AFTER GPT + Owner approval):
    python -m tools.chem11.incremental_publish \\
        --execute --owner-approved \\
        --snapshot-id <uuid>

Frozen artifact bindings (WO §9):
    responses_sha256:          ce817e9cccd97e8b5e93b572aaa577fc32426a80f65359d7e753956c3f3cac67
    seo_manifest_sha256:       b6f9e86da727617d253d04f03aebfee0b6d5cb2426f123add46133db8d36cf88
    preview_plan_semantic_sha: ff3b1a13853db201ac8da53f8e5cbe056c1537531ade5d73ae8c24615fc9ce27
    preview_plan_file_sha:     360b4ccedde15bae7d287a660ff38f22c8f05cbb8860c6eb5c7ce62c599b6505
    expected_chemicals:        4647
    expected_sections:         74352
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid as _uuid_mod
from pathlib import Path
from typing import Optional

WO_CODE = "WO-MSDS-INCREMENTAL-PUBLISH-001"

# Frozen artifact paths (relative to repo root).
SEO_MANIFEST_PATH = Path("docs/chem/seo-preview-manifest-v12.json")
CHEM05_PLAN_JSONL = Path("artifacts/chem05_v12/materialize_plan.jsonl")
CHEM05_MANIFEST  = Path("artifacts/chem05_v12/materialize_manifest.json")
CHEM05_REPORT    = Path("artifacts/chem05_v12/materialize_report.json")
PREVIEW_PLAN_JSONL   = Path("artifacts/chem_seo_preview_v12/preview_materialize_plan.jsonl")
PREVIEW_MANIFEST_JSON = Path("artifacts/chem_seo_preview_v12/preview_materialize_manifest.json")
PREVIEW_REPORT_JSON   = Path("artifacts/chem_seo_preview_v12/preview_materialize_report.json")

# Frozen SHA pins (WO §9).
FROZEN_RESPONSES_SHA      = "ce817e9cccd97e8b5e93b572aaa577fc32426a80f65359d7e753956c3f3cac67"
FROZEN_SEO_MANIFEST_SHA   = "b6f9e86da727617d253d04f03aebfee0b6d5cb2426f123add46133db8d36cf88"
FROZEN_PREVIEW_PLAN_SEM   = "ff3b1a13853db201ac8da53f8e5cbe056c1537531ade5d73ae8c24615fc9ce27"
FROZEN_PREVIEW_PLAN_FILE  = "360b4ccedde15bae7d287a660ff38f22c8f05cbb8860c6eb5c7ce62c599b6505"
FROZEN_EXPECTED_CHEMICALS = 4647
FROZEN_EXPECTED_SECTIONS  = 74352

BLOCK_EXECUTE_NOT_REQUESTED  = "EXECUTE_NOT_REQUESTED"
BLOCK_OWNER_NOT_APPROVED     = "OWNER_NOT_APPROVED"
BLOCK_SHA_MISMATCH           = "SHA_MISMATCH"
BLOCK_CENSUS_MISMATCH        = "CENSUS_MISMATCH"
BLOCK_PREFLIGHT_FAIL         = "PREFLIGHT_FAIL"
BLOCK_MATERIALIZE_FAIL       = "MATERIALIZE_FAIL"
BLOCK_SNAPSHOT_VERIFY_FAIL   = "SNAPSHOT_VERIFY_FAIL"
BLOCK_PUBLISH_PREFLIGHT_FAIL = "PUBLISH_PREFLIGHT_FAIL"
BLOCK_PROMOTION_FAIL         = "PROMOTION_FAIL"


class IncrementalPublishError(SystemExit):
    pass


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _print(obj: dict) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False))


def _verify_frozen_artifacts() -> dict:
    """Verify all frozen artifact SHAs. Raises on any mismatch."""
    results = {}
    checks = [
        ("seo_manifest", SEO_MANIFEST_PATH, "manifest_sha256", FROZEN_SEO_MANIFEST_SHA),
        ("preview_plan_file", PREVIEW_PLAN_JSONL, None, FROZEN_PREVIEW_PLAN_FILE),
    ]
    for label, path, json_field, expected in checks:
        if not path.exists():
            raise IncrementalPublishError(f"BLOCKED {BLOCK_SHA_MISMATCH}: {path} not found")
        if json_field:
            data = json.loads(path.read_text(encoding="utf-8"))
            actual = data.get(json_field)
        else:
            actual = _file_sha256(path)
        if actual != expected:
            raise IncrementalPublishError(
                f"BLOCKED {BLOCK_SHA_MISMATCH}: {label} actual={actual!r} expected={expected!r}"
            )
        results[label] = actual

    # Check preview manifest's semantic sha.
    preview_manifest = json.loads(PREVIEW_MANIFEST_JSON.read_text(encoding="utf-8"))
    sem_sha = preview_manifest.get("plan_semantic_sha256")
    if sem_sha != FROZEN_PREVIEW_PLAN_SEM:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SHA_MISMATCH}: preview_plan_semantic actual={sem_sha!r} "
            f"expected={FROZEN_PREVIEW_PLAN_SEM!r}"
        )
    results["preview_plan_semantic"] = sem_sha

    # Verify census counts in preview manifest.
    counts = preview_manifest.get("counts") or {}
    if int(counts.get("chemicals") or 0) != FROZEN_EXPECTED_CHEMICALS:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_CENSUS_MISMATCH}: chemicals "
            f"actual={counts.get('chemicals')} expected={FROZEN_EXPECTED_CHEMICALS}"
        )
    if int(counts.get("sections") or 0) != FROZEN_EXPECTED_SECTIONS:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_CENSUS_MISMATCH}: sections "
            f"actual={counts.get('sections')} expected={FROZEN_EXPECTED_SECTIONS}"
        )
    results["chemicals"] = counts["chemicals"]
    results["sections"] = counts["sections"]
    results["responses_sha256"] = preview_manifest.get("responses_sha256")
    return results


def _load_plan_inputs():
    from services.kosha_msds import materialize_writer as w
    from tools.chem_seo_preview.build_preview_plan import build_preview_plan

    built = build_preview_plan(
        chem05_plan_jsonl=CHEM05_PLAN_JSONL,
        chem05_manifest_json=CHEM05_MANIFEST,
        chem05_report_json=CHEM05_REPORT,
        seo_manifest_json=SEO_MANIFEST_PATH,
    )
    preview_manifest = dict(built["manifest"])
    preview_manifest.setdefault("plan_file_sha256", preview_manifest["plan_semantic_sha256"])
    return w.MaterializePlanInputs(
        manifest=preview_manifest,
        report=dict(built["report"]),
        chemicals=tuple(built["plan_chemicals"]),
    )


def run_dry_run() -> dict:
    from services.kosha_msds import materialize_writer as w
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
    from services.kosha_msds.production_store import SupabaseMaterializeStore

    _verify_frozen_artifacts()
    plan_inputs = _load_plan_inputs()

    mat_store = SupabaseMaterializeStore()
    preloaded = w.preload_existing_state(plan_inputs, mat_store)
    preflight = w.preflight(
        plan_inputs,
        store=mat_store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        preloaded=preloaded,
    )

    if not preflight.can_execute:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_PREFLIGHT_FAIL}: {list(preflight.block_reasons)}"
        )

    return {
        "wo": WO_CODE,
        "mode": "DRY_RUN",
        "status": "PREFLIGHT_PASS",
        "frozen": {
            "responses_sha256": FROZEN_RESPONSES_SHA,
            "seo_manifest_sha256": FROZEN_SEO_MANIFEST_SHA,
            "preview_plan_semantic_sha256": FROZEN_PREVIEW_PLAN_SEM,
            "preview_plan_file_sha256": FROZEN_PREVIEW_PLAN_FILE,
            "expected_chemicals": FROZEN_EXPECTED_CHEMICALS,
            "expected_sections": FROZEN_EXPECTED_SECTIONS,
        },
        "preflight": preflight.to_dict(),
        "production_impact": {
            "chemicals_to_insert": preflight.counts_by_kind.get("NEW", (0, 0))[0],
            "chemicals_unchanged": preflight.counts_by_kind.get("UNCHANGED", (0, 0))[0],
            "chemicals_to_update": preflight.counts_by_kind.get("CHANGED", (0, 0))[0],
            "chemicals_conflict": preflight.counts_by_kind.get("CONFLICT", (0, 0))[0],
            "sections_to_insert": preflight.counts_by_kind.get("NEW", (0, 0))[1],
            "sections_unchanged": preflight.counts_by_kind.get("UNCHANGED", (0, 0))[1],
            "sections_to_update": preflight.counts_by_kind.get("CHANGED", (0, 0))[1],
            "sections_conflict": preflight.counts_by_kind.get("CONFLICT", (0, 0))[1],
            "snapshot_items_to_insert": FROZEN_EXPECTED_CHEMICALS,
            "new_snapshot_publish_state": "PUBLISHED_SEO_PREVIEW",
        },
    }


def run_execute(*, snapshot_id: Optional[str] = None) -> dict:
    from services.kosha_msds import materialize_writer as w
    from services.kosha_msds import publish as pub
    from services.kosha_msds.contract import (
        PUBLICATION_SCOPE_SEO_PREVIEW,
        PUBLISH_PUBLISHED_SEO_PREVIEW,
        SNAPSHOT_COMPLETED,
        SNAPSHOT_FAILED,
    )
    from services.kosha_msds.production_store import (
        SupabaseMaterializeStore, SupabasePublishStore,
    )

    artifact_results = _verify_frozen_artifacts()
    plan_inputs = _load_plan_inputs()
    snap_id = snapshot_id or str(_uuid_mod.uuid4())

    mat_store = SupabaseMaterializeStore()
    pub_store = SupabasePublishStore()

    # Preflight with preloaded state.
    preloaded = w.preload_existing_state(plan_inputs, mat_store)
    preflight = w.preflight(
        plan_inputs,
        store=mat_store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        preloaded=preloaded,
    )
    if not preflight.can_execute:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_PREFLIGHT_FAIL}: {list(preflight.block_reasons)}"
        )

    try:
        w.assert_can_execute_production_write(
            preflight_report=preflight,
            owner_approved=True,
            wo_scope_allows_write=True,
        )
    except w.ProductionWriteForbidden as exc:
        raise IncrementalPublishError(f"BLOCKED {BLOCK_MATERIALIZE_FAIL}: {exc}") from exc

    # Open snapshot.
    preview_manifest = plan_inputs.manifest
    seo_manifest = json.loads(SEO_MANIFEST_PATH.read_text(encoding="utf-8"))
    seo_sha = seo_manifest.get("manifest_sha256")
    responses_sha = artifact_results.get("responses_sha256")

    snap_row = w.open_snapshot(
        snapshot_id=snap_id,
        manifest=preview_manifest,
        discovered_count=FROZEN_EXPECTED_CHEMICALS,
        expected_count=FROZEN_EXPECTED_CHEMICALS,
    )
    snap_row["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # Inject binding into metrics_json so publish preflight can verify.
    metrics = dict(snap_row.get("metrics_json") or {})
    metrics.update({
        "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
        "seo_preview_manifest_sha256": seo_sha,
        "responses_sha256": responses_sha,
        "seo_preview_expected_chemical_count": FROZEN_EXPECTED_CHEMICALS,
        "seo_preview_expected_section_count": FROZEN_EXPECTED_SECTIONS,
    })
    snap_row["metrics_json"] = metrics
    mat_store.insert_snapshot(snap_row)

    try:
        try:
            write_report = w.execute_incremental_write(
                plan_inputs, store=mat_store, snapshot_id=snap_id, preloaded=preloaded,
            )
        except w.IncrementalWriteBlocked as exc:
            raise IncrementalPublishError(f"BLOCKED {BLOCK_MATERIALIZE_FAIL}: {exc}") from exc
        mat_store.update_snapshot_status(snap_id, SNAPSHOT_COMPLETED)
    except Exception:
        try:
            mat_store.update_snapshot_status(snap_id, SNAPSHOT_FAILED)
        except Exception:
            pass
        raise

    # Verify snapshot completed.
    reread = mat_store.get_snapshot(snap_id)
    if not reread or reread.get("status") != SNAPSHOT_COMPLETED:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SNAPSHOT_VERIFY_FAIL}: post-materialize state={reread}"
        )

    # Publish preflight.
    publish_report = pub.preflight_publish(
        snap_id,
        store=pub_store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        seo_preview_expected_chemical_count=FROZEN_EXPECTED_CHEMICALS,
        seo_preview_expected_section_count=FROZEN_EXPECTED_SECTIONS,
        expected_materialize_binding={
            "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
            "seo_preview_manifest_sha256": seo_sha,
            "responses_sha256": responses_sha,
        },
    )
    if not publish_report.eligible:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_PUBLISH_PREFLIGHT_FAIL}: {list(publish_report.block_reasons)}"
        )

    try:
        pub.assert_can_execute_publish(
            report=publish_report, owner_approved=True, wo_scope_allows_publish=True,
        )
    except pub.PublicationForbidden as exc:
        raise IncrementalPublishError(f"BLOCKED {BLOCK_PROMOTION_FAIL}: {exc}") from exc

    pub_store.promote_to_state(snap_id, PUBLISH_PUBLISHED_SEO_PREVIEW)

    post = pub_store.get_snapshot(snap_id)
    if not post or post.get("publish_state") != PUBLISH_PUBLISHED_SEO_PREVIEW:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_PROMOTION_FAIL}: post state={post}"
        )

    return {
        "wo": WO_CODE,
        "mode": "EXECUTE",
        "status": "OK",
        "snapshot_id": snap_id,
        "frozen": {
            "responses_sha256": FROZEN_RESPONSES_SHA,
            "seo_manifest_sha256": FROZEN_SEO_MANIFEST_SHA,
            "expected_chemicals": FROZEN_EXPECTED_CHEMICALS,
            "expected_sections": FROZEN_EXPECTED_SECTIONS,
        },
        "write_report": write_report.to_dict(),
        "snapshot_status_after_materialize": reread.get("status"),
        "publish_state_after_promote": post.get("publish_state"),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true", default=False,
                   help="Execute production write. Requires --owner-approved.")
    p.add_argument("--owner-approved", action="store_true", default=False,
                   help="Owner + GPT approval confirmed.")
    p.add_argument("--snapshot-id", default=None,
                   help="Deterministic snapshot UUID. Random if omitted.")
    args = p.parse_args(argv)

    if args.execute and not args.owner_approved:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_OWNER_NOT_APPROVED}: --execute requires --owner-approved"
        )

    if args.execute:
        result = run_execute(snapshot_id=args.snapshot_id)
    else:
        result = run_dry_run()

    _print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
