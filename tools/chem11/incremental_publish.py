"""WO-MSDS-INCREMENTAL-PUBLISH-001 — incremental KOSHA MSDS SEO preview publisher.

Publishes the v12 responses.jsonl artifact (4,647 complete chemicals) as a new
PUBLISHED_SEO_PREVIEW snapshot. The new snapshot unions the 1,997 already-published
chemicals with the 2,650 new complete chemicals, giving 4,647 total.

Pre-built frozen artifacts (SHA-pinned, gitignored):
    artifacts/chem04/official_v12/responses.jsonl    — source hydration artifact
    artifacts/chem_seo_preview_v12/                  — pre-built preview plan (use directly)
    docs/chem/seo-preview-manifest-v12.json          — SEO membership manifest (committed)

Safety fences (fail-closed):
    * DRY-RUN by default: preflight SELECT only; no DB writes.
    * --execute requires --owner-approved (GPT + Owner).
    * Four-way responses SHA binding verified before any DB connection:
        file SHA == FROZEN_RESPONSES_SHA == preview_manifest.responses_sha256
              == SEO manifest source.responses_sha256
    * Preview plan file SHA verified; frozen artifacts used directly as execution
      input (no re-build from source, no divergence between verified and executed plan).
    * preview manifest plan_semantic_sha256 verified against FROZEN_PREVIEW_PLAN_SEM.
    * preflight receives on_disk_responses_sha256 + on_disk_plan_file_sha256 so
      verify_manifest_binding() is NOT bypassed.
    * No DELETE, no TRUNCATE, no publish_state rollback.

CLI (dry-run):
    python -m tools.chem11.incremental_publish

CLI (execute, AFTER GPT + Owner approval):
    python -m tools.chem11.incremental_publish \\
        --execute --owner-approved \\
        --snapshot-id <uuid>

Frozen artifact bindings (WO §9 / PATCH-1):
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

# Source artifact path.
RESPONSES_PATH = Path("artifacts/chem04/official_v12/responses.jsonl")

# Frozen pre-built artifact paths (relative to repo root).
SEO_MANIFEST_PATH     = Path("docs/chem/seo-preview-manifest-v12.json")
PREVIEW_PLAN_JSONL    = Path("artifacts/chem_seo_preview_v12/preview_materialize_plan.jsonl")
PREVIEW_MANIFEST_JSON = Path("artifacts/chem_seo_preview_v12/preview_materialize_manifest.json")
PREVIEW_REPORT_JSON   = Path("artifacts/chem_seo_preview_v12/preview_materialize_report.json")

# Frozen SHA pins (WO §9 / PATCH-1).
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
    """Verify all frozen artifact SHAs and SHA binding chain. Raises on any mismatch.

    PATCH-1 binding chain (four-way responses SHA equality):
        actual file SHA
        == FROZEN_RESPONSES_SHA
        == preview_manifest.responses_sha256
        == SEO manifest source.responses_sha256

    Returns a dict with verified SHA values for downstream use.
    """
    # ── 1. Compute actual responses.jsonl SHA and four-way equality check.
    if not RESPONSES_PATH.exists():
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SHA_MISMATCH}: responses.jsonl not found: {RESPONSES_PATH}"
        )
    actual_responses_sha = _file_sha256(RESPONSES_PATH)
    if actual_responses_sha != FROZEN_RESPONSES_SHA:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SHA_MISMATCH}: responses.jsonl actual={actual_responses_sha!r} "
            f"frozen={FROZEN_RESPONSES_SHA!r}"
        )

    # ── 2. SEO manifest self-integrity (on-disk SHA field).
    if not SEO_MANIFEST_PATH.exists():
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SHA_MISMATCH}: SEO manifest not found: {SEO_MANIFEST_PATH}"
        )
    seo_manifest = json.loads(SEO_MANIFEST_PATH.read_text(encoding="utf-8"))
    seo_manifest_sha = seo_manifest.get("manifest_sha256")
    if seo_manifest_sha != FROZEN_SEO_MANIFEST_SHA:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SHA_MISMATCH}: seo_manifest actual={seo_manifest_sha!r} "
            f"frozen={FROZEN_SEO_MANIFEST_SHA!r}"
        )
    seo_responses_sha = (seo_manifest.get("source") or {}).get("responses_sha256")
    if seo_responses_sha != FROZEN_RESPONSES_SHA:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SHA_MISMATCH}: SEO manifest source.responses_sha256="
            f"{seo_responses_sha!r} != FROZEN_RESPONSES_SHA={FROZEN_RESPONSES_SHA!r}"
        )

    # ── 3. Preview plan JSONL file SHA.
    if not PREVIEW_PLAN_JSONL.exists():
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SHA_MISMATCH}: preview plan JSONL not found: {PREVIEW_PLAN_JSONL}"
        )
    actual_plan_file_sha = _file_sha256(PREVIEW_PLAN_JSONL)
    if actual_plan_file_sha != FROZEN_PREVIEW_PLAN_FILE:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SHA_MISMATCH}: preview_plan_file actual={actual_plan_file_sha!r} "
            f"frozen={FROZEN_PREVIEW_PLAN_FILE!r}"
        )

    # ── 4. Preview manifest: semantic SHA + responses SHA + census counts.
    if not PREVIEW_MANIFEST_JSON.exists():
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SHA_MISMATCH}: preview manifest not found: {PREVIEW_MANIFEST_JSON}"
        )
    preview_manifest = json.loads(PREVIEW_MANIFEST_JSON.read_text(encoding="utf-8"))

    sem_sha = preview_manifest.get("plan_semantic_sha256")
    if sem_sha != FROZEN_PREVIEW_PLAN_SEM:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SHA_MISMATCH}: preview_plan_semantic actual={sem_sha!r} "
            f"frozen={FROZEN_PREVIEW_PLAN_SEM!r}"
        )

    manifest_responses_sha = preview_manifest.get("responses_sha256")
    if manifest_responses_sha != FROZEN_RESPONSES_SHA:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SHA_MISMATCH}: preview_manifest.responses_sha256="
            f"{manifest_responses_sha!r} != FROZEN_RESPONSES_SHA={FROZEN_RESPONSES_SHA!r}"
        )

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

    return {
        "actual_responses_sha": actual_responses_sha,
        "actual_plan_file_sha": actual_plan_file_sha,
        "seo_manifest_sha": seo_manifest_sha,
        "preview_plan_semantic_sha": sem_sha,
        "chemicals": counts["chemicals"],
        "sections": counts["sections"],
    }


def _load_plan_inputs(*, actual_responses_sha: str, actual_plan_file_sha: str):
    """Load MaterializePlanInputs from the pre-built frozen preview artifacts.

    PATCH-1: uses materialize_writer.load_plan_inputs() directly against the
    pre-built PREVIEW_PLAN_JSONL / PREVIEW_MANIFEST_JSON / PREVIEW_REPORT_JSON.
    No re-invocation of build_preview_plan() — the verified file IS the input.
    """
    from services.kosha_msds import materialize_writer as w

    return w.load_plan_inputs(
        plan_jsonl=PREVIEW_PLAN_JSONL,
        manifest_json=PREVIEW_MANIFEST_JSON,
        report_json=PREVIEW_REPORT_JSON,
    )


def run_dry_run() -> dict:
    from services.kosha_msds import materialize_writer as w
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
    from services.kosha_msds.production_store import SupabaseMaterializeStore

    verified = _verify_frozen_artifacts()
    actual_responses_sha = verified["actual_responses_sha"]
    actual_plan_file_sha = verified["actual_plan_file_sha"]

    plan_inputs = _load_plan_inputs(
        actual_responses_sha=actual_responses_sha,
        actual_plan_file_sha=actual_plan_file_sha,
    )

    mat_store = SupabaseMaterializeStore()
    preloaded = w.preload_existing_state(plan_inputs, mat_store)
    preflight = w.preflight(
        plan_inputs,
        store=mat_store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        preloaded=preloaded,
        on_disk_responses_sha256=actual_responses_sha,
        on_disk_plan_file_sha256=actual_plan_file_sha,
    )

    if not preflight.can_execute:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_PREFLIGHT_FAIL}: {list(preflight.block_reasons)}"
        )

    return {
        "wo": WO_CODE,
        "mode": "DRY_RUN",
        "status": "PREFLIGHT_PASS",
        "binding": {
            "responses_sha256_actual": actual_responses_sha,
            "responses_sha256_frozen": FROZEN_RESPONSES_SHA,
            "responses_sha256_match": actual_responses_sha == FROZEN_RESPONSES_SHA,
            "preview_plan_file_sha_actual": actual_plan_file_sha,
            "preview_plan_file_sha_frozen": FROZEN_PREVIEW_PLAN_FILE,
            "preview_plan_file_sha_match": actual_plan_file_sha == FROZEN_PREVIEW_PLAN_FILE,
            "preview_plan_semantic_sha": verified["preview_plan_semantic_sha"],
            "seo_manifest_sha256": verified["seo_manifest_sha"],
        },
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

    verified = _verify_frozen_artifacts()
    actual_responses_sha = verified["actual_responses_sha"]
    actual_plan_file_sha = verified["actual_plan_file_sha"]
    seo_sha = verified["seo_manifest_sha"]

    plan_inputs = _load_plan_inputs(
        actual_responses_sha=actual_responses_sha,
        actual_plan_file_sha=actual_plan_file_sha,
    )
    snap_id = snapshot_id or str(_uuid_mod.uuid4())

    mat_store = SupabaseMaterializeStore()
    pub_store = SupabasePublishStore()

    preloaded = w.preload_existing_state(plan_inputs, mat_store)
    preflight = w.preflight(
        plan_inputs,
        store=mat_store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        preloaded=preloaded,
        on_disk_responses_sha256=actual_responses_sha,
        on_disk_plan_file_sha256=actual_plan_file_sha,
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

    snap_row = w.open_snapshot(
        snapshot_id=snap_id,
        manifest=plan_inputs.manifest,
        discovered_count=FROZEN_EXPECTED_CHEMICALS,
        expected_count=FROZEN_EXPECTED_CHEMICALS,
    )
    snap_row["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    metrics = dict(snap_row.get("metrics_json") or {})
    metrics.update({
        "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
        "seo_preview_manifest_sha256": seo_sha,
        "responses_sha256": actual_responses_sha,
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

    reread = mat_store.get_snapshot(snap_id)
    if not reread or reread.get("status") != SNAPSHOT_COMPLETED:
        raise IncrementalPublishError(
            f"BLOCKED {BLOCK_SNAPSHOT_VERIFY_FAIL}: post-materialize state={reread}"
        )

    publish_report = pub.preflight_publish(
        snap_id,
        store=pub_store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        seo_preview_expected_chemical_count=FROZEN_EXPECTED_CHEMICALS,
        seo_preview_expected_section_count=FROZEN_EXPECTED_SECTIONS,
        expected_materialize_binding={
            "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
            "seo_preview_manifest_sha256": seo_sha,
            "responses_sha256": actual_responses_sha,
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
        "binding": {
            "responses_sha256_actual": actual_responses_sha,
            "preview_plan_file_sha_actual": actual_plan_file_sha,
        },
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
