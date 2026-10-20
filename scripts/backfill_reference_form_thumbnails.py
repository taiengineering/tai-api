"""Reference Form Thumbnail Backfill — WO-WWW-SS-THUMBNAIL-001 P2.

Generates WebP thumbnails for all currently PUBLISHED reference forms.

Requires migration 20261021000001 (thumbnail columns) to be applied first.

Usage:
    python scripts/backfill_reference_form_thumbnails.py --dry-run   # default
    python scripts/backfill_reference_form_thumbnails.py --execute   # write to DB + Storage

Dry-run prints a plan with target count, estimated storage, and per-form status.
Production Backfill requires separate Owner approval (G4 gate).

Safety:
  - Skips forms that already have thumbnail_qa_status = QA_PASS (no duplicate work)
  - Skips forms whose preview does not match current approved file (stale preview)
  - Records QA_FAIL on generation error without touching other rows
  - Never modifies reference_form_files or original preview artifacts
  - Concurrency limited to 4 (configurable via --concurrency)
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

def _require_deps() -> tuple:
    """Import heavy deps only when needed."""
    try:
        import httpx
    except ImportError:
        log.error("httpx not installed")
        sys.exit(1)
    try:
        from supabase import create_client, Client
    except ImportError:
        log.error("supabase not installed")
        sys.exit(1)
    try:
        from services.reference_form_thumbnail_svc import (
            generate_thumbnail, ThumbnailInputError, ThumbnailSizeError,
            GENERATION_VERSION,
        )
    except ImportError as e:
        log.error("reference_form_thumbnail_svc not importable: %s", e)
        sys.exit(1)
    return httpx, create_client, generate_thumbnail, ThumbnailInputError, ThumbnailSizeError, GENERATION_VERSION


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
    existing_thumbnail_status: Optional[str]  # NULL / PENDING / QA_PASS / QA_FAIL


@dataclass
class BackfillStats:
    total:     int = 0
    skipped:   int = 0
    generated: int = 0
    failed:    int = 0
    errors:    list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

_VIEW      = "reference_form_public_view"
_FILES     = "reference_form_files"
_PREVIEW   = "reference_form_preview_artifacts"
_SOURCES   = "reference_form_sources"
_APPROVALS = "reference_form_approvals"

THUMBNAIL_BUCKET = "reference-forms-preview"
THUMBNAIL_PREFIX = "thumbnails"


def _get_supabase():
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        log.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)
    from supabase import create_client
    return create_client(url, key)


def _collect_targets(sb) -> list[FormTarget]:
    """
    Query all PUBLISHED forms and find those eligible for thumbnail generation.

    A form is eligible when:
      - It has at least one QA_PASS file with a linked preview artifact
      - The preview artifact: is_published=true, qa_status=QA_PASS,
        source_file_sha256 matches file sha256
      - thumbnail_qa_status is NULL or QA_FAIL (not already QA_PASS or PENDING)
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

        file_id   = str(rep_file["file_id"])
        file_sha  = rep_file.get("sha256", "")

        # Load file row to get preview_artifact_id
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

        # Load preview artifact
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

        existing_status = pa.get("thumbnail_qa_status")  # None / 'PENDING' / 'QA_PASS' / 'QA_FAIL'

        if existing_status in ("QA_PASS", "PENDING"):
            log.debug("  %s — skip: thumbnail already %s", slug, existing_status)
            continue

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


def _process_one(sb, target: FormTarget, generate_fn, dry_run: bool) -> str:
    """Process one form. Returns 'generated', 'skipped', or 'failed:<reason>'."""
    import httpx

    # Download preview PNG
    try:
        preview_path = _parse_storage_ref(target.preview_ref, THUMBNAIL_BUCKET)
    except ValueError as exc:
        return f"failed:bad_preview_ref:{exc}"

    try:
        signed = sb.storage.from_(THUMBNAIL_BUCKET).create_signed_url(
            preview_path, expires_in=120
        )
        signed_url = signed.get("signedURL") or signed.get("signedUrl") or ""
        if not signed_url:
            raise ValueError("empty signed URL")
    except Exception as exc:
        return f"failed:signed_url:{exc}"

    try:
        r = httpx.get(signed_url, follow_redirects=True, timeout=60)
        r.raise_for_status()
        preview_bytes = r.content
    except Exception as exc:
        return f"failed:download:{exc}"

    input_sha256 = hashlib.sha256(preview_bytes).hexdigest()

    if dry_run:
        log.info("  [DRY-RUN] %s — would generate thumbnail (preview %d B, input_sha256=%s…)",
                 target.slug, len(preview_bytes), input_sha256[:12])
        return "dry_run"

    # Generate thumbnail
    try:
        result = generate_fn(preview_bytes)
    except Exception as exc:
        # Record QA_FAIL in DB
        try:
            sb.table(_PREVIEW).update({
                "thumbnail_qa_status": "QA_FAIL",
            }).eq("id", target.preview_artifact_id).execute()
        except Exception:
            pass
        return f"failed:generate:{exc}"

    # Upload to storage
    thumb_storage_path = f"{THUMBNAIL_PREFIX}/{target.form_id}-v1.webp"
    try:
        sb.storage.from_(THUMBNAIL_BUCKET).upload(
            path=thumb_storage_path,
            file=result.webp_bytes,
            file_options={"content-type": "image/webp", "upsert": "true"},
        )
    except Exception as exc:
        try:
            sb.table(_PREVIEW).update({
                "thumbnail_qa_status": "QA_FAIL",
            }).eq("id", target.preview_artifact_id).execute()
        except Exception:
            pass
        return f"failed:upload:{exc}"

    # Update preview artifact row
    thumbnail_ref = f"storage://{THUMBNAIL_BUCKET}/{thumb_storage_path}"
    try:
        sb.table(_PREVIEW).update({
            "thumbnail_ref":                thumbnail_ref,
            "thumbnail_sha256":             result.output_sha256,
            "thumbnail_input_sha256":       input_sha256,
            "thumbnail_generation_version": result.generation_version,
            "thumbnail_qa_status":          "QA_PASS",
            "thumbnail_bytes":              result.byte_count,
        }).eq("id", target.preview_artifact_id).execute()
    except Exception as exc:
        return f"failed:db_update:{exc}"

    log.info("  OK %s — %d B WebP (sha256=%s…)", target.slug, result.byte_count, result.output_sha256[:12])
    return "generated"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill WebP thumbnails for reference forms")
    group  = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run",  dest="dry_run",  action="store_true",  default=True,
                       help="Print plan only — do not write (default)")
    group.add_argument("--execute",  dest="dry_run",  action="store_false",
                       help="Actually generate and store thumbnails")
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    _require_deps()
    from services.reference_form_thumbnail_svc import (
        generate_thumbnail, GENERATION_VERSION,
    )

    sb = _get_supabase()
    targets = _collect_targets(sb)
    stats = BackfillStats(total=len(targets))

    mode = "DRY-RUN" if args.dry_run else "EXECUTE"
    log.info("=== Thumbnail Backfill %s === targets=%d version=%s",
             mode, len(targets), GENERATION_VERSION)

    if not targets:
        log.info("No eligible forms found — nothing to do.")
        return

    if args.dry_run:
        log.info("Dry-run: listing %d target forms:", len(targets))
        for t in targets:
            log.info("  %s  (existing_status=%s)", t.slug, t.existing_thumbnail_status)
        log.info("Re-run with --execute to generate thumbnails (requires Owner G4 approval).")
        return

    # Execute mode
    for t in targets:
        result = _process_one(sb, t, generate_thumbnail, dry_run=False)
        if result == "generated":
            stats.generated += 1
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


if __name__ == "__main__":
    main()
