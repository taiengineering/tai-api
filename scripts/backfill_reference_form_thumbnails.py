"""Reference Form Thumbnail Backfill — WO-WWW-SS-THUMBNAIL-001 P2.

Generates WebP thumbnails for all currently PUBLISHED reference forms.

Requires migration 20261021000001 (thumbnail columns) to be applied first
for --execute.  --dry-run works without the migration (shows a read-only survey).

Usage:
    python scripts/backfill_reference_form_thumbnails.py --dry-run   # default
    python scripts/backfill_reference_form_thumbnails.py --execute   # write to DB + Storage
    python scripts/backfill_reference_form_thumbnails.py --reset-pending --pa-id <PA_ID>

Production Backfill requires separate Owner approval (G4 gate).

Concurrency model:
  Designed for a single operator run.  Concurrent execution is safe but each run
  competes for an atomic PENDING claim — only the winner proceeds per form.

Claim lifecycle:
  NULL / QA_FAIL → (atomic claim) → PENDING → QA_PASS  (success)
                                            → QA_FAIL   (failure, via _release_claim)
  After a process crash, PENDING rows remain.  Use --reset-pending --pa-id <PA_ID>
  to move specific stuck rows back to NULL before retrying.
  (Run --dry-run first — it logs pa_id for every PENDING row.)

Safety:
  - Detects missing migration columns before --execute
  - Atomic DB claim prevents duplicate processing across concurrent runs
  - Hash-based Storage path (input_sha256[:16]) enables idempotent re-upload:
    on conflict, existing object is re-used only if SHA256 matches
  - QA_PASS update guarded by thumbnail_qa_status=PENDING to prevent
    overwriting another process's completed result (FIX-01)
  - All failure paths release PENDING back to QA_FAIL (retry-safe)
    EXCEPT ownership-lost path — to avoid corrupting a concurrent claim
  - Rolls back Storage upload on DB update failure
  - Never modifies reference_form_files or original preview artifacts
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("thumbnail_backfill")

# ---------------------------------------------------------------------------
# Imports (deferred to allow --dry-run without all deps installed)
# ---------------------------------------------------------------------------

def _require_deps() -> None:
    for pkg, name in (("httpx", "httpx"), ("supabase", "supabase")):
        try:
            __import__(pkg)
        except ImportError:
            log.error("%s not installed", name)
            sys.exit(1)
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail  # noqa
    except ImportError as e:
        log.error("reference_form_thumbnail_svc not importable: %s", e)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FormTarget:
    form_id: str
    slug: str
    file_id: str
    file_sha256: str
    preview_artifact_id: str
    preview_ref: str
    source_file_sha256: str
    existing_thumbnail_status: Optional[str]  # None / PENDING / QA_PASS / QA_FAIL


@dataclass
class BackfillStats:
    total:     int = 0
    skipped:   int = 0
    generated: int = 0
    failed:    int = 0
    errors:    list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Table / bucket constants
# ---------------------------------------------------------------------------

_VIEW      = "reference_form_public_view"
_FILES     = "reference_form_files"
_PREVIEW   = "reference_form_preview_artifacts"
_SOURCES   = "reference_form_sources"
_APPROVALS = "reference_form_approvals"

THUMBNAIL_BUCKET = "reference-forms-preview"
THUMBNAIL_PREFIX = "thumbnails"


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------

def _get_supabase():
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        log.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)
    from supabase import create_client
    return create_client(url, key)


def _check_migration_applied(sb) -> bool:
    """Return True if migration 20261021000001 thumbnail columns exist."""
    try:
        sb.table(_PREVIEW).select("thumbnail_qa_status").limit(1).execute()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Atomic claim / release helpers
# ---------------------------------------------------------------------------

def _atomic_claim(sb, pa_id: str) -> bool:
    """
    Atomically transition thumbnail_qa_status NULL→PENDING or QA_FAIL→PENDING.

    Uses two separate conditional UPDATEs.  PostgreSQL row-level locking
    ensures that if two processes run simultaneously, at most one succeeds
    per transition: the first UPDATE that wins the lock changes the status,
    the second finds no matching row and returns data=[].

    Returns True if this call successfully claimed the row.
    """
    # Claim from NULL (never processed)
    try:
        res = (
            sb.table(_PREVIEW)
            .update({"thumbnail_qa_status": "PENDING"})
            .eq("id", pa_id)
            .is_("thumbnail_qa_status", "null")
            .execute()
        )
        if res.data:
            return True
    except Exception:
        pass

    # Claim from QA_FAIL (retry after previous failure)
    try:
        res = (
            sb.table(_PREVIEW)
            .update({"thumbnail_qa_status": "PENDING"})
            .eq("id", pa_id)
            .eq("thumbnail_qa_status", "QA_FAIL")
            .execute()
        )
        if res.data:
            return True
    except Exception:
        pass

    return False


def _release_claim(sb, pa_id: str) -> None:
    """
    Release a PENDING claim back to QA_FAIL on failure.
    Only transitions from PENDING — will not touch QA_PASS rows.
    """
    try:
        sb.table(_PREVIEW).update({"thumbnail_qa_status": "QA_FAIL"}).eq(
            "id", pa_id
        ).eq("thumbnail_qa_status", "PENDING").execute()
    except Exception as exc:
        log.error("Claim release failed for pa_id=%s: %s", pa_id, exc)


def _reset_pending_claims(sb, pa_ids: list[str]) -> int:
    """
    Crash recovery: reset the specified PENDING preview artifacts back to NULL.

    Requires an explicit list of preview artifact IDs — unrestricted bulk reset
    is prohibited because another process may currently hold a PENDING claim.

    Returns the count of rows reset.
    Run --dry-run first to obtain the pa_id for stuck PENDING rows.
    """
    if not pa_ids:
        log.error(
            "reset_pending_claims requires at least one pa_id; "
            "unrestricted bulk reset is prohibited. "
            "Run --dry-run to identify stuck PENDING rows and their pa_ids."
        )
        return 0
    try:
        res = (
            sb.table(_PREVIEW)
            .update({"thumbnail_qa_status": None})
            .eq("thumbnail_qa_status", "PENDING")
            .in_("id", pa_ids)
            .execute()
        )
        return len(res.data or [])
    except Exception as exc:
        log.error("reset_pending failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Target collection
# ---------------------------------------------------------------------------

def _collect_targets(sb) -> list[FormTarget]:
    """
    Query all PUBLISHED forms and find those eligible for thumbnail generation.

    Eligible when:
      - QA_PASS file with has_preview=True and a linked preview artifact
      - Preview: is_published=true, qa_status=QA_PASS, source_file_sha256 matches
      - thumbnail_qa_status is NOT QA_PASS (NULL, QA_FAIL, and PENDING are eligible)
        PENDING is included so crashed runs can be re-claimed after --reset-pending.
    """
    log.info("Querying published forms …")
    try:
        view_res = sb.table(_VIEW).select("id,canonical_slug,qa_pass_files").execute()
    except Exception as exc:
        log.error("View query failed: %s", exc)
        sys.exit(1)

    rows = view_res.data or []
    log.info("  %d published forms found", len(rows))

    targets: list[FormTarget] = []

    for row in rows:
        form_id = str(row["id"])
        slug    = str(row.get("canonical_slug", ""))
        qa_files = row.get("qa_pass_files") or []

        rep_file = next((f for f in qa_files if f.get("has_preview") is True), None)
        if not rep_file:
            log.debug("  %s — skip: no file with has_preview", slug)
            continue

        file_id  = str(rep_file["file_id"])
        file_sha = rep_file.get("sha256", "")

        try:
            fr = (
                sb.table(_FILES)
                .select("id,sha256,preview_artifact_id,is_active,qa_status")
                .eq("id", file_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            log.warning("  %s — skip: file query error: %s", slug, exc)
            continue

        if not fr.data:
            log.debug("  %s — skip: file row not found", slug)
            continue

        file_row = fr.data[0]
        if not file_row.get("is_active") or file_row.get("qa_status") != "QA_PASS":
            log.debug("  %s — skip: file not active/QA_PASS", slug)
            continue
        if file_row.get("sha256") != file_sha:
            log.debug("  %s — skip: file sha256 mismatch", slug)
            continue

        pa_id = file_row.get("preview_artifact_id")
        if not pa_id:
            log.debug("  %s — skip: no preview_artifact_id", slug)
            continue

        try:
            par = (
                sb.table(_PREVIEW)
                .select(
                    "form_id,preview_ref,source_file_sha256,is_published,qa_status,"
                    "thumbnail_qa_status"
                )
                .eq("id", str(pa_id))
                .limit(1)
                .execute()
            )
        except Exception as exc:
            log.warning("  %s — skip: preview artifact query error: %s", slug, exc)
            continue

        if not par.data:
            log.debug("  %s — skip: preview artifact not found", slug)
            continue

        pa = par.data[0]
        if not pa.get("is_published") or pa.get("qa_status") != "QA_PASS":
            log.debug("  %s — skip: preview not published/QA_PASS", slug)
            continue
        if pa.get("source_file_sha256") != file_sha:
            log.debug("  %s — skip: preview source_file_sha256 mismatch", slug)
            continue

        existing_status = pa.get("thumbnail_qa_status")

        if existing_status == "QA_PASS":
            log.debug("  %s — skip: thumbnail already QA_PASS", slug)
            continue
        # PENDING and QA_FAIL are eligible:
        # - QA_FAIL: previous attempt failed → retry
        # - PENDING: previous process may have crashed → retry after --reset-pending

        preview_ref = pa.get("preview_ref", "")
        if not preview_ref:
            log.debug("  %s — skip: no preview_ref", slug)
            continue

        targets.append(FormTarget(
            form_id=form_id,
            slug=slug,
            file_id=file_id,
            file_sha256=file_sha,
            preview_artifact_id=str(pa_id),
            preview_ref=preview_ref,
            source_file_sha256=pa["source_file_sha256"],
            existing_thumbnail_status=existing_status,
        ))

    return targets


def _dry_run_pre_migration(sb) -> None:
    """
    Read-only survey of eligible forms when migration is not yet applied.
    Queries only columns that exist before migration 20261021000001.
    """
    log.info("--- Pre-migration dry-run survey (read-only) ---")
    log.info("Migration 20261021000001 not applied — thumbnail columns unavailable.")
    log.info("Showing form eligibility based on existing preview data.")

    try:
        view_res = sb.table(_VIEW).select("id,canonical_slug,qa_pass_files").execute()
    except Exception as exc:
        log.error("View query failed: %s", exc)
        return

    rows = view_res.data or []
    total = len(rows)
    eligible = 0

    for row in rows:
        slug    = str(row.get("canonical_slug", ""))
        qa_files = row.get("qa_pass_files") or []
        has_preview = any(f.get("has_preview") is True for f in qa_files)
        if has_preview:
            eligible += 1
            log.info("  eligible: %s", slug)

    log.info("--- Survey complete: total=%d eligible_with_preview=%d ---", total, eligible)
    log.info("Apply migration 20261021000001 then re-run with --dry-run or --execute.")


# ---------------------------------------------------------------------------
# Authority recheck
# ---------------------------------------------------------------------------

def _parse_storage_ref(raw_ref: str, expected_bucket: str) -> str:
    prefix = "storage://"
    if not raw_ref.startswith(prefix):
        raise ValueError(f"Bad storage ref: {raw_ref!r}")
    rest = raw_ref[len(prefix):]
    slash_idx = rest.find("/")
    if slash_idx < 1:
        raise ValueError(f"Bad storage ref (no path): {raw_ref!r}")
    bucket = rest[:slash_idx]
    path   = rest[slash_idx + 1:]
    if bucket != expected_bucket:
        raise ValueError(f"Bucket mismatch: expected {expected_bucket!r}, got {bucket!r}")
    if not path or ".." in path.split("/"):
        raise ValueError(f"Invalid path: {path!r}")
    return path


def _recheck_authority(sb, target: FormTarget) -> Optional[str]:
    """
    Re-verify PUBLISHED + CLEARED + approval binding immediately before processing.
    Returns None if all gates pass, or an error reason string.
    """
    try:
        vr = (
            sb.table(_VIEW)
            .select("id,qa_pass_files")
            .eq("id", target.form_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        return f"precheck_view_error:{exc}"
    if not vr.data:
        return "form_unpublished"

    try:
        sr = (
            sb.table(_SOURCES)
            .select("source_name,rights_status")
            .eq("form_id", target.form_id)
            .eq("is_active", True)
            .execute()
        )
    except Exception as exc:
        return f"precheck_sources_error:{exc}"
    sources = sr.data or []
    if not sources:
        return "no_active_sources"
    if any(s.get("rights_status") != "CLEARED" for s in sources):
        return "sources_not_cleared"

    try:
        ar = (
            sb.table(_APPROVALS)
            .select("approved_file_hashes")
            .eq("form_id", target.form_id)
            .eq("is_current", True)
            .eq("approval_status", "APPROVED")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        return f"precheck_approval_error:{exc}"
    if not ar.data:
        return "no_current_approval"
    hashes = ar.data[0].get("approved_file_hashes") or []
    match = next(
        (h for h in hashes
         if str(h.get("file_id")) == target.file_id and h.get("sha256") == target.file_sha256),
        None,
    )
    if not match:
        return "approval_binding_failed"

    return None


# ---------------------------------------------------------------------------
# Process one form
# ---------------------------------------------------------------------------

def _process_one(sb, target: FormTarget, generate_fn, dry_run: bool) -> str:
    """
    Process one form.
    Returns 'generated', 'dry_run', 'skipped:<reason>', or 'failed:<reason>'.

    In execute mode:
      1. Re-verify authority (PUBLISHED / CLEARED / approval).
      2. Atomic claim: NULL or QA_FAIL → PENDING.
         If claim fails another process owns it → 'skipped:claim_lost'.
      3. Download preview PNG, generate WebP.
      4. Upload to Storage using hash-based path for idempotency.
         On upload conflict, verify existing object SHA256 — reuse if match,
         fail with 'upload_conflict' if mismatch.
      5. DB update with thumbnail_qa_status=PENDING guard (FIX-01).
         If update returns no rows (ownership lost), roll back Storage without
         calling _release_claim (row may be claimed by another process).
      6. On any other failure: release claim (PENDING → QA_FAIL) for retry-safety.
    """
    import httpx

    # Step 1: authority recheck (both modes)
    auth_err = _recheck_authority(sb, target)
    if auth_err:
        log.info("  %s — skip (authority): %s", target.slug, auth_err)
        return f"skipped:{auth_err}"

    # Dry-run: no DB/Storage writes
    if dry_run:
        try:
            _parse_storage_ref(target.preview_ref, THUMBNAIL_BUCKET)
        except ValueError as exc:
            return f"skipped:bad_preview_ref:{exc}"
        log.info("  [DRY-RUN] %s — eligible (existing_status=%s)",
                 target.slug, target.existing_thumbnail_status)
        return "dry_run"

    # Step 2: atomic claim (execute mode only)
    if not _atomic_claim(sb, target.preview_artifact_id):
        log.info("  %s — skip: claim_lost (already claimed by another process)", target.slug)
        return "skipped:claim_lost"

    # Helper: release claim on any failure from here on.
    def _fail(reason: str) -> str:
        _release_claim(sb, target.preview_artifact_id)
        return f"failed:{reason}"

    # Step 3: parse storage ref
    try:
        preview_path = _parse_storage_ref(target.preview_ref, THUMBNAIL_BUCKET)
    except ValueError as exc:
        return _fail(f"bad_preview_ref:{exc}")

    # Step 4: get signed URL for preview
    try:
        signed = sb.storage.from_(THUMBNAIL_BUCKET).create_signed_url(
            preview_path, expires_in=120
        )
        signed_url = signed.get("signedURL") or signed.get("signedUrl") or ""
        if not signed_url:
            raise ValueError("empty signed URL")
    except Exception as exc:
        return _fail(f"signed_url:{exc}")

    # Step 5: download preview
    try:
        r = httpx.get(signed_url, follow_redirects=True, timeout=60)
        r.raise_for_status()
        preview_bytes = r.content
    except Exception as exc:
        return _fail(f"download:{exc}")

    input_sha256 = hashlib.sha256(preview_bytes).hexdigest()

    # Step 6: generate WebP
    try:
        result = generate_fn(preview_bytes)
    except Exception as exc:
        return _fail(f"generate:{exc}")

    # Step 7: upload to Storage — hash-based path for idempotency; no upsert.
    # Same input + same generation version → same path → safe to detect duplicates.
    thumb_storage_path = f"{THUMBNAIL_PREFIX}/{target.form_id}-{input_sha256[:16]}.webp"
    try:
        sb.storage.from_(THUMBNAIL_BUCKET).upload(
            path=thumb_storage_path,
            file=result.webp_bytes,
            file_options={"content-type": "image/webp", "upsert": "false"},
        )
    except Exception as upload_exc:
        # Upload failed — check whether an identical object already exists.
        # This can occur when a previous run uploaded but the DB update failed
        # before Storage rollback executed.
        log.debug("  %s — upload failed (%s); checking for existing object",
                  target.slug, upload_exc)
        try:
            check_signed = sb.storage.from_(THUMBNAIL_BUCKET).create_signed_url(
                thumb_storage_path, expires_in=60
            )
            check_url = (
                check_signed.get("signedURL") or check_signed.get("signedUrl") or ""
            )
            if not check_url:
                return _fail(f"upload:{upload_exc}")
            check_r = httpx.get(check_url, follow_redirects=True, timeout=30)
            check_r.raise_for_status()
            existing_sha256 = hashlib.sha256(check_r.content).hexdigest()
            if existing_sha256 != result.output_sha256:
                log.error(
                    "  %s — upload conflict: existing object SHA256 mismatch "
                    "(expected=%s… got=%s…)",
                    target.slug, result.output_sha256[:12], existing_sha256[:12],
                )
                return _fail("upload_conflict")
            log.info(
                "  %s — reusing existing Storage object (SHA256 match)", target.slug
            )
        except Exception as check_exc:
            return _fail(f"upload:{upload_exc} conflict_check_failed:{check_exc}")

    # Step 8: DB update — guarded by thumbnail_qa_status=PENDING (FIX-01).
    # If the row is no longer PENDING (ownership lost), roll back Storage without
    # calling _release_claim — the row may be claimed by another process.
    thumbnail_ref = f"storage://{THUMBNAIL_BUCKET}/{thumb_storage_path}"
    try:
        db_res = (
            sb.table(_PREVIEW)
            .update({
                "thumbnail_ref":                thumbnail_ref,
                "thumbnail_sha256":             result.output_sha256,
                "thumbnail_input_sha256":       input_sha256,
                "thumbnail_generation_version": result.generation_version,
                "thumbnail_qa_status":          "QA_PASS",
                "thumbnail_bytes":              result.byte_count,
            })
            .eq("id", target.preview_artifact_id)
            .eq("thumbnail_qa_status", "PENDING")
            .execute()
        )
    except Exception as exc:
        try:
            sb.storage.from_(THUMBNAIL_BUCKET).remove([thumb_storage_path])
            log.warning("  %s — rolled back Storage after DB failure", target.slug)
        except Exception as rm_exc:
            log.error("  %s — Storage rollback failed (orphan file %s): %s",
                      target.slug, thumb_storage_path, rm_exc)
        return _fail(f"db_update:{exc}")

    if not db_res.data:
        # Row is no longer PENDING — ownership was lost after we uploaded.
        # Do NOT call _release_claim: the row may be PENDING under another
        # process's ownership, and releasing it would corrupt that claim.
        try:
            sb.storage.from_(THUMBNAIL_BUCKET).remove([thumb_storage_path])
            log.warning("  %s — rolled back Storage after ownership loss", target.slug)
        except Exception as rm_exc:
            log.error("  %s — Storage rollback failed (orphan file %s): %s",
                      target.slug, thumb_storage_path, rm_exc)
        log.warning(
            "  %s — ownership lost: thumbnail_qa_status is no longer PENDING "
            "(concurrent --reset-pending or claim race).",
            target.slug,
        )
        return "failed:db_update_ownership_lost"

    log.info("  OK %s — %d B WebP (sha256=%s…)",
             target.slug, result.byte_count, result.output_sha256[:12])
    return "generated"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill WebP thumbnails for reference forms"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run", dest="mode", action="store_const", const="dry_run", default="dry_run",
        help="Print plan only — no writes (default; works before migration)"
    )
    mode_group.add_argument(
        "--execute", dest="mode", action="store_const", const="execute",
        help="Generate and store thumbnails (requires migration + Owner G4)"
    )
    mode_group.add_argument(
        "--reset-pending", dest="mode", action="store_const", const="reset_pending",
        help="Crash recovery: reset stuck PENDING rows back to NULL (requires --pa-id)"
    )
    parser.add_argument(
        "--pa-id", dest="pa_ids", action="append", metavar="PA_ID",
        help=(
            "Preview artifact ID to target (repeatable). "
            "Required for --reset-pending. "
            "Obtain from --dry-run output (pa_id= field on PENDING rows)."
        ),
    )
    args = parser.parse_args()

    _require_deps()
    sb = _get_supabase()

    # --- reset-pending mode ---
    if args.mode == "reset_pending":
        if not args.pa_ids:
            log.error(
                "--reset-pending requires at least one --pa-id PA_ID argument to "
                "scope the reset. Run --dry-run first to identify stuck PENDING rows "
                "and their pa_ids."
            )
            sys.exit(1)
        n = _reset_pending_claims(sb, pa_ids=args.pa_ids)
        log.info(
            "Reset %d PENDING row(s) to NULL for %d pa_id(s). "
            "Re-run with --execute to retry.",
            n, len(args.pa_ids),
        )
        return

    from services.reference_form_thumbnail_svc import generate_thumbnail, GENERATION_VERSION

    migration_ok = _check_migration_applied(sb)

    # --- dry-run mode ---
    if args.mode == "dry_run":
        if not migration_ok:
            _dry_run_pre_migration(sb)
            return
        targets = _collect_targets(sb)
        pending_stuck = sum(1 for t in targets if t.existing_thumbnail_status == "PENDING")
        log.info("=== Thumbnail Backfill DRY-RUN === eligible=%d version=%s",
                 len(targets), GENERATION_VERSION)
        for t in targets:
            if t.existing_thumbnail_status == "PENDING":
                log.info("  %s  status=PENDING  pa_id=%s  [use --reset-pending --pa-id %s]",
                         t.slug, t.preview_artifact_id, t.preview_artifact_id)
            else:
                log.info("  %s  status=%s  pa_id=%s",
                         t.slug, t.existing_thumbnail_status, t.preview_artifact_id)
        if pending_stuck:
            log.warning(
                "  %d PENDING row(s) detected. To recover after a crash: "
                "--reset-pending --pa-id <PA_ID> (one --pa-id per stuck row)",
                pending_stuck,
            )
        log.info("Re-run with --execute to generate (requires Owner G4 approval).")
        return

    # --- execute mode ---
    if not migration_ok:
        log.error(
            "Migration 20261021000001 not applied — thumbnail columns missing. "
            "Apply the migration first."
        )
        sys.exit(1)

    targets = _collect_targets(sb)
    stats = BackfillStats(total=len(targets))

    log.info("=== Thumbnail Backfill EXECUTE === targets=%d version=%s",
             len(targets), GENERATION_VERSION)

    if not targets:
        log.info("No eligible forms found — nothing to do.")
        return

    for t in targets:
        result = _process_one(sb, t, generate_thumbnail, dry_run=False)
        if result == "generated":
            stats.generated += 1
        elif result.startswith("skipped:"):
            stats.skipped += 1
        elif result.startswith("failed:"):
            stats.failed += 1
            stats.errors.append((t.slug, result))
            log.warning("  FAIL %s — %s", t.slug, result)
        else:
            stats.skipped += 1

    log.info("=== Backfill complete: generated=%d skipped=%d failed=%d ===",
             stats.generated, stats.skipped, stats.failed)
    if stats.errors:
        log.warning("Failures:")
        for slug, reason in stats.errors:
            log.warning("  %s: %s", slug, reason)

    if stats.failed:
        sys.exit(2)  # partial failure — non-zero exit code


if __name__ == "__main__":
    main()
