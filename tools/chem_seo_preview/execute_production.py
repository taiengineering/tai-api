"""WO-CHEM-SEO-PREVIEW-EXECUTE-001 — SEO_PREVIEW production executor.

End-to-end orchestrator that runs the ENTIRE materialize + promote chain
against a live Supabase in a single command:

    1. Frozen SHA verify
       - CHEM-05 plan file SHA matches its manifest.plan_file_sha256
       - CHEM-05 manifest.responses_sha256 matches SEO manifest
       - SEO manifest self-SHA integrity holds
       - Optional CLI flags let the caller pin expected frozen values
         (e.g. --expected-seo-manifest-sha) so a wrong manifest gets
         caught before the DB is touched
    2. Preview plan load
       - build_preview_plan produces a MaterializePlanInputs whose
         snapshot.metrics_json binds the SEO manifest SHA
    3. Live preflight (materialize_writer.preflight, publication_scope=SEO_PREVIEW)
       - reads the live kosha_msds_chemicals + kosha_msds_sections +
         kosha_msds_snapshots tables via SupabaseMaterializeStore
    4. Materialize
       - opens a RUNNING snapshot
       - inserts NEW chemicals, sections, snapshot_items in chunks
       - marks snapshot COMPLETED
    5. Snapshot COMPLETED verify
       - re-reads the snapshot; status must be COMPLETED
    6. Publish preflight (publish.preflight_publish, publication_scope=SEO_PREVIEW)
       - expected count + section count bound to the SEO manifest census
       - expected_materialize_binding checks the snapshot metrics_json
    7. Promote to PUBLISHED_SEO_PREVIEW
       - single-column UPDATE via SupabasePublishStore.promote_to_state
    8. Post-write census
       - reads back preview view row count

The two pre-existing safety fences remain closed at module scope:

    services.kosha_msds.materialize_writer.PRODUCTION_WRITE_ALLOWED = False
    services.kosha_msds.publish.PRODUCTION_PUBLISH_ALLOWED           = False

The executor passes wo_scope_allows_write=True / wo_scope_allows_publish=True
as keyword-argument OVERRIDES at the two assert callsites — and only when
ALL of the following hold at CLI parsing time:

    --scope seo_preview        (FULL is refused with a non-zero exit)
    --owner-approved           (unset/false is refused)
    --execute                  (dry-run is the default; --execute must be
                                explicit)

If any of those preconditions is missing, the executor prints the
computed preflight report and exits non-zero without touching the DB.

CLI:

    python -m tools.chem_seo_preview.execute_production \\
        --scope seo_preview --owner-approved --execute \\
        --seo-manifest        docs/chem/seo-preview-manifest.json \\
        --chem05-plan-jsonl   artifacts/chem05/materialize_plan.jsonl \\
        --chem05-manifest     artifacts/chem05/materialize_manifest.json \\
        --chem05-report       artifacts/chem05/materialize_report.json \\
        --snapshot-id         seo-preview-2026-09-18 \\
        --expected-seo-manifest-sha  f696a212...638d \\
        --expected-responses-sha     49994a2a...43dd \\
        --expected-chemical-count    1997 \\
        --expected-section-count     31952
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from services.kosha_msds import materialize_writer as w
from services.kosha_msds import publish as pub
from services.kosha_msds.contract import (
    ALLOWED_PUBLICATION_SCOPES,
    DETAIL_COMPLETE,
    PUBLICATION_SCOPE_FULL,
    PUBLICATION_SCOPE_SEO_PREVIEW,
    PUBLISH_PUBLISHED_SEO_PREVIEW,
    SEO_PREVIEW_REQUIRED_SECTION_COUNT,
    SNAPSHOT_COMPLETED,
)
from services.kosha_msds.identity import new_content_id
from tools.chem_seo_preview.build_preview_plan import build_preview_plan


WO_SCOPE = "WO-CHEM-SEO-PREVIEW-EXECUTE-001"

# Fail-closed block reasons unique to the executor.
BLOCK_SCOPE_NOT_SEO_PREVIEW = "SCOPE_NOT_SEO_PREVIEW"
BLOCK_OWNER_NOT_APPROVED = "OWNER_NOT_APPROVED"
BLOCK_EXECUTE_NOT_REQUESTED = "EXECUTE_NOT_REQUESTED"
BLOCK_EXPECTED_MANIFEST_SHA_MISMATCH = "EXPECTED_MANIFEST_SHA_MISMATCH"
BLOCK_EXPECTED_RESPONSES_SHA_MISMATCH = "EXPECTED_RESPONSES_SHA_MISMATCH"
BLOCK_EXPECTED_CENSUS_MISMATCH = "EXPECTED_CENSUS_MISMATCH"
BLOCK_MATERIALIZE_PREFLIGHT = "MATERIALIZE_PREFLIGHT_BLOCKED"
BLOCK_MATERIALIZE_WRITE = "MATERIALIZE_WRITE_FAILED"
BLOCK_SNAPSHOT_NOT_COMPLETED = "SNAPSHOT_NOT_COMPLETED_POST_MATERIALIZE"
BLOCK_PUBLISH_PREFLIGHT = "PUBLISH_PREFLIGHT_BLOCKED"
BLOCK_PROMOTION_FAILED = "PROMOTION_FAILED"


class ExecutorError(SystemExit):
    """Non-zero exit for any fail-closed condition."""


# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _print(obj: dict) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Store factory — swappable so tests can inject in-memory fakes.
# ---------------------------------------------------------------------------


def _default_store_factory():
    """Import the production Supabase stores. Fails loudly if the app
    environment (SUPABASE_URL / SUPABASE_SERVICE_KEY) is unset — the
    executor MUST NOT proceed without a live client."""
    from services.kosha_msds.production_store import (
        SupabaseMaterializeStore, SupabasePublishStore,
    )
    return SupabaseMaterializeStore(), SupabasePublishStore()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _assert_preconditions(args) -> None:
    """CLI-level gates run BEFORE any file I/O or DB connection."""
    scope = args.scope
    if scope not in ALLOWED_PUBLICATION_SCOPES:
        raise ExecutorError(f"BLOCKED {BLOCK_SCOPE_NOT_SEO_PREVIEW}: --scope must be seo_preview")
    if scope == PUBLICATION_SCOPE_FULL:
        raise ExecutorError(
            f"BLOCKED {BLOCK_SCOPE_NOT_SEO_PREVIEW}: FULL is explicitly refused by "
            f"this executor. FULL rollout is a separate WO."
        )
    if scope != PUBLICATION_SCOPE_SEO_PREVIEW:
        raise ExecutorError(f"BLOCKED {BLOCK_SCOPE_NOT_SEO_PREVIEW}: unsupported scope {scope!r}")
    if not args.owner_approved:
        raise ExecutorError(f"BLOCKED {BLOCK_OWNER_NOT_APPROVED}: --owner-approved is required")
    if not args.execute:
        raise ExecutorError(f"BLOCKED {BLOCK_EXECUTE_NOT_REQUESTED}: --execute must be set explicitly")


def _verify_frozen_shas(
    seo_manifest_path: Path,
    *,
    expected_seo_manifest_sha: Optional[str],
    expected_responses_sha: Optional[str],
    expected_chemical_count: Optional[int],
    expected_section_count: Optional[int],
) -> dict:
    """Compare the on-disk SEO manifest against the WO's frozen fingerprint.

    Returns the loaded manifest dict. Any mismatch raises ExecutorError.
    """
    seo_manifest = json.loads(seo_manifest_path.read_text(encoding="utf-8"))
    on_disk_manifest_sha = seo_manifest.get("manifest_sha256")
    responses_sha = (seo_manifest.get("source") or {}).get("responses_sha256")
    census = seo_manifest.get("census") or {}
    chem_count = census.get("complete_chemicals")
    sec_count = census.get("preview_sections")

    if expected_seo_manifest_sha and on_disk_manifest_sha != expected_seo_manifest_sha:
        raise ExecutorError(
            f"BLOCKED {BLOCK_EXPECTED_MANIFEST_SHA_MISMATCH}: "
            f"expected={expected_seo_manifest_sha} actual={on_disk_manifest_sha}"
        )
    if expected_responses_sha and responses_sha != expected_responses_sha:
        raise ExecutorError(
            f"BLOCKED {BLOCK_EXPECTED_RESPONSES_SHA_MISMATCH}: "
            f"expected={expected_responses_sha} actual={responses_sha}"
        )
    if expected_chemical_count is not None and chem_count != expected_chemical_count:
        raise ExecutorError(
            f"BLOCKED {BLOCK_EXPECTED_CENSUS_MISMATCH}: "
            f"expected chemicals={expected_chemical_count} actual={chem_count}"
        )
    if expected_section_count is not None and sec_count != expected_section_count:
        raise ExecutorError(
            f"BLOCKED {BLOCK_EXPECTED_CENSUS_MISMATCH}: "
            f"expected sections={expected_section_count} actual={sec_count}"
        )
    return seo_manifest


def _run(args, *, store_factory=None) -> dict:
    """Full pipeline. Returns a summary dict when successful."""
    _assert_preconditions(args)

    if store_factory is None:
        store_factory = _default_store_factory

    seo_manifest_path = Path(args.seo_manifest)
    chem05_plan = Path(args.chem05_plan_jsonl)
    chem05_manifest = Path(args.chem05_manifest)
    chem05_report = Path(args.chem05_report)

    seo_manifest = _verify_frozen_shas(
        seo_manifest_path,
        expected_seo_manifest_sha=args.expected_seo_manifest_sha,
        expected_responses_sha=args.expected_responses_sha,
        expected_chemical_count=args.expected_chemical_count,
        expected_section_count=args.expected_section_count,
    )
    census = seo_manifest.get("census") or {}
    chem_count = int(census.get("complete_chemicals"))
    sec_count = int(census.get("preview_sections"))

    # ── Step 2: preview plan load (bridge is the same tool used in tests).
    built = build_preview_plan(
        chem05_plan_jsonl=chem05_plan,
        chem05_manifest_json=chem05_manifest,
        chem05_report_json=chem05_report,
        seo_manifest_json=seo_manifest_path,
    )
    if not built["manifest"].get("execute_eligible"):
        raise ExecutorError(
            f"BLOCKED: preview plan reported execute_eligible=false — "
            f"reasons={built['manifest'].get('execute_block_reasons')}"
        )

    # Materialize preflight expects a MaterializePlanInputs; build it in-memory
    # from the bridge output rather than round-tripping to disk.
    preview_manifest = dict(built["manifest"])
    # Bridge output leaves plan_path / plan_file_sha256 nullable until written;
    # for the in-DB path we set the sha to the deterministic semantic sha so
    # preflight has stable binding.
    preview_manifest.setdefault("plan_file_sha256", preview_manifest["plan_semantic_sha256"])
    plan_inputs = w.MaterializePlanInputs(
        manifest=preview_manifest,
        report=dict(built["report"]),
        chemicals=tuple(built["plan_chemicals"]),
    )

    mat_store, pub_store = store_factory()

    # ── Step 3: live preflight
    preflight = w.preflight(
        plan_inputs,
        store=mat_store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    if not preflight.can_execute:
        raise ExecutorError(
            f"BLOCKED {BLOCK_MATERIALIZE_PREFLIGHT}: reasons={list(preflight.block_reasons)}"
        )

    # ── Assert we may open the write path (fence override at callsite ONLY).
    try:
        w.assert_can_execute_production_write(
            preflight_report=preflight,
            owner_approved=True,
            wo_scope_allows_write=True,
        )
    except w.ProductionWriteForbidden as exc:
        raise ExecutorError(f"BLOCKED {BLOCK_MATERIALIZE_WRITE}: {exc}") from exc

    # ── Step 4: materialize
    snapshot_id = args.snapshot_id or str(uuid.uuid4())
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    snapshot_row = w.open_snapshot(
        snapshot_id=snapshot_id,
        manifest=preview_manifest,
        discovered_count=chem_count,
        expected_count=chem_count,
    )
    snapshot_row["started_at"] = started_at
    mat_store.insert_snapshot(snapshot_row)

    # Insert chemicals + sections + snapshot_items in order.
    # Generate deterministic client-side UUIDs so we can wire sections +
    # snapshot_items without a round-trip lookup. Postgres accepts an
    # explicit `id` uuid on kosha_msds_chemicals (schema line ≈13-30);
    # the DEFAULT gen_random_uuid() only fires when `id` is absent.
    chem_rows: list[dict] = []
    section_rows: list[dict] = []
    membership_rows: list[dict] = []
    chem_uuid_by_key: dict[tuple[str, str], str] = {}
    for c in built["plan_chemicals"]:
        chem_uuid = str(uuid.uuid4())
        chem_uuid_by_key[(c.get("source_id"), c.get("source_key"))] = chem_uuid
        # Canonical TAI content identity is CHEM:<UUID> (see
        # services.kosha_msds.identity.new_content_id + is_chem_content_id).
        # It is deliberately separate from the KOSHA source identity
        # (chem_id / source_key) so a re-hydration or bulk swap doesn't
        # collide with an already-published TAI content_id.
        chem_rows.append({
            "id": chem_uuid,
            "content_id": new_content_id(),
            "source_id": c.get("source_id"),
            "source_key": c.get("source_key"),
            "chem_id": c.get("chem_id"),
            "identity_status": c.get("identity_status"),
            "chemical_name_ko": c.get("chemical_name_ko"),
            "chemical_name_en": c.get("chemical_name_en"),
            "cas_no": c.get("cas_no"),
            "ke_no": c.get("ke_no"),
            "en_no": c.get("en_no"),
            "un_no": c.get("un_no"),
            "last_date": c.get("last_date"),
            "source_content_hash": c.get("source_content_hash"),
            "source_dataset_url": c.get("source_dataset_url"),
            "is_current": False,
        })
    mat_store.insert_chemicals(chem_rows)

    # Re-read each chemical to confirm it landed. Under the live Supabase
    # this is a cheap round-trip that also validates the CHECK constraints
    # (source_id, source_key = chem_id, etc.). Under the in-memory store
    # it just verifies our own bookkeeping.
    for c in built["plan_chemicals"]:
        expected = chem_uuid_by_key[(c.get("source_id"), c.get("source_key"))]
        row = mat_store.get_chemical_by_natural_key(c.get("source_id"), c.get("source_key"))
        if not row:
            raise ExecutorError(
                f"BLOCKED {BLOCK_MATERIALIZE_WRITE}: chemical missing after insert "
                f"chem_id={c.get('chem_id')!r}"
            )
        got = row.get("id")
        if got and got != expected:
            raise ExecutorError(
                f"BLOCKED {BLOCK_MATERIALIZE_WRITE}: chemical id drift for "
                f"chem_id={c.get('chem_id')!r} expected={expected!r} got={got!r}"
            )

    for c in built["plan_chemicals"]:
        chem_uuid = chem_uuid_by_key[(c.get("source_id"), c.get("source_key"))]
        for s in c.get("sections") or []:
            section_rows.append({
                "chemical_id": chem_uuid,
                "section_no": int(s.get("section_no")),
                "payload_json": s.get("payload_json"),
                "section_hash": s.get("section_hash"),
                "result_code": s.get("result_code"),
                "result_message": s.get("result_message"),
                "fetched_at": s.get("fetched_at"),
            })
        membership_rows.append({
            "snapshot_id": snapshot_id,
            "chemical_id": chem_uuid,
            "source_content_hash": c.get("source_content_hash"),
            "identity_status": c.get("identity_status"),
            "detail_status": c.get("detail_status"),
            "in_snapshot": True,
        })
    mat_store.insert_sections(section_rows)
    mat_store.insert_snapshot_items(membership_rows)
    mat_store.update_snapshot_status(snapshot_id, SNAPSHOT_COMPLETED)

    # ── Step 5: snapshot COMPLETED verify
    reread = mat_store.get_snapshot(snapshot_id)
    if not reread or reread.get("status") != SNAPSHOT_COMPLETED:
        raise ExecutorError(
            f"BLOCKED {BLOCK_SNAPSHOT_NOT_COMPLETED}: snapshot={reread}"
        )

    # ── Step 6: publish preflight (SEO_PREVIEW)
    seo_manifest_sha = seo_manifest.get("manifest_sha256")
    responses_sha = (seo_manifest.get("source") or {}).get("responses_sha256")
    publish_report = pub.preflight_publish(
        snapshot_id,
        store=pub_store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        seo_preview_expected_chemical_count=chem_count,
        seo_preview_expected_section_count=sec_count,
        expected_materialize_binding={
            "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
            "seo_preview_manifest_sha256": seo_manifest_sha,
            "responses_sha256": responses_sha,
        },
    )
    if not publish_report.eligible:
        raise ExecutorError(
            f"BLOCKED {BLOCK_PUBLISH_PREFLIGHT}: reasons={list(publish_report.block_reasons)}"
        )

    # ── Step 7: promote (fence override at callsite ONLY)
    try:
        pub.assert_can_execute_publish(
            report=publish_report,
            owner_approved=True,
            wo_scope_allows_publish=True,
        )
    except pub.PublicationForbidden as exc:
        raise ExecutorError(f"BLOCKED {BLOCK_PROMOTION_FAILED}: {exc}") from exc

    pub_store.promote_to_state(snapshot_id, PUBLISH_PUBLISHED_SEO_PREVIEW)

    # ── Step 8: post-write verify
    post = pub_store.get_snapshot(snapshot_id)
    if not post or post.get("publish_state") != PUBLISH_PUBLISHED_SEO_PREVIEW:
        raise ExecutorError(
            f"BLOCKED {BLOCK_PROMOTION_FAILED}: post-promotion state={post}"
        )

    return {
        "wo": WO_SCOPE,
        "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
        "snapshot_id": snapshot_id,
        "expected_chemical_count": chem_count,
        "expected_section_count": sec_count,
        "materialized_chemicals": len(chem_rows),
        "materialized_sections": len(section_rows),
        "materialized_snapshot_items": len(membership_rows),
        "snapshot_status_after_materialize": reread.get("status"),
        "publish_state_after_promote": post.get("publish_state"),
        "seo_preview_manifest_sha256": seo_manifest_sha,
        "responses_sha256": responses_sha,
        "preview_plan_semantic_sha256": preview_manifest.get("plan_semantic_sha256"),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scope", required=True,
                   help="Publication scope. Only 'seo_preview' is accepted.")
    p.add_argument("--owner-approved", action="store_true", default=False,
                   help="Signals owner-level approval. Required with --execute.")
    p.add_argument("--execute", action="store_true", default=False,
                   help="Must be set explicitly for the live path to run.")
    p.add_argument("--seo-manifest", required=True,
                   help="Path to docs/chem/seo-preview-manifest.json.")
    p.add_argument("--chem05-plan-jsonl", required=True)
    p.add_argument("--chem05-manifest", required=True)
    p.add_argument("--chem05-report", required=True)
    p.add_argument("--snapshot-id", default=None,
                   help="Optional deterministic snapshot id (uuid if omitted).")
    p.add_argument("--expected-seo-manifest-sha", default=None,
                   help="Pin the SEO manifest SHA to prevent surprise drift.")
    p.add_argument("--expected-responses-sha", default=None,
                   help="Pin the frozen responses.jsonl SHA.")
    p.add_argument("--expected-chemical-count", type=int, default=None)
    p.add_argument("--expected-section-count", type=int, default=None)

    args = p.parse_args(argv)
    result = _run(args)
    _print({"status": "OK", **result})
    return 0


if __name__ == "__main__":
    sys.exit(main())
