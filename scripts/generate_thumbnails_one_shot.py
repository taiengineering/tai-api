"""Reference Form Thumbnail Generator — WO-WWW-SS-THUMBNAIL-001.

One-shot script: generates 320px WebP thumbnails from existing approved
Preview PNGs and uploads them to Storage at thumbnails/{form_id}.webp.

No new DB columns are created.  The thumbnail's existence at the predictable
Storage path is the only state.

Usage:
    python scripts/generate_thumbnails_one_shot.py --dry-run   # default
    python scripts/generate_thumbnails_one_shot.py --execute   # write to Storage

--dry-run  Queries published forms and shows which would be processed.
           No Storage reads or writes.
--execute  Downloads each Preview PNG, generates WebP, uploads to Storage.
           Requires Owner G4 approval before running on production.

Safety:
  - Re-verifies PUBLISHED + CLEARED + approval binding before each form
  - upsert=false: skips forms whose thumbnail already exists in Storage
  - Logs each result; exits with code 2 on partial failure
  - Never modifies DB tables
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("thumbnail_generator")


# ---------------------------------------------------------------------------
# Deps
# ---------------------------------------------------------------------------

def _require_deps() -> None:
    for pkg in ("httpx", "supabase"):
        try:
            __import__(pkg)
        except ImportError:
            log.error("%s not installed", pkg)
            sys.exit(1)
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail  # noqa
    except ImportError as e:
        log.error("reference_form_thumbnail_svc not importable: %s", e)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class FormTarget:
    form_id: str
    slug: str
    file_id: str
    file_sha256: str
    preview_ref: str       # storage://reference-forms-preview/...
    thumb_path: str        # thumbnails/{form_id}.webp


@dataclass
class Stats:
    total:     int = 0
    generated: int = 0
    skipped:   int = 0
    failed:    int = 0
    errors:    list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VIEW      = "reference_form_public_view"
_FILES     = "reference_form_files"
_PREVIEW   = "reference_form_preview_artifacts"
_SOURCES   = "reference_form_sources"
_APPROVALS = "reference_form_approvals"
BUCKET     = "reference-forms-preview"


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


# ---------------------------------------------------------------------------
# Target collection
# ---------------------------------------------------------------------------

def _collect_targets(sb) -> list[FormTarget]:
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
            continue

        file_id  = str(rep_file["file_id"])
        file_sha = rep_file.get("sha256", "")

        try:
            fr = (
                sb.table(_FILES)
                .select("id,form_id,sha256,preview_artifact_id,is_active,qa_status")
                .eq("id", file_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            log.warning("  %s — skip: file query error: %s", slug, exc)
            continue

        if not fr.data:
            continue
        file_row = fr.data[0]
        if not file_row.get("is_active") or file_row.get("qa_status") != "QA_PASS":
            continue
        if file_row.get("sha256") != file_sha:
            continue

        pa_id = file_row.get("preview_artifact_id")
        if not pa_id:
            continue

        try:
            par = (
                sb.table(_PREVIEW)
                .select("form_id,preview_ref,source_file_sha256,is_published,qa_status")
                .eq("id", str(pa_id))
                .limit(1)
                .execute()
            )
        except Exception as exc:
            log.warning("  %s — skip: preview query error: %s", slug, exc)
            continue

        if not par.data:
            continue
        pa = par.data[0]
        if not pa.get("is_published") or pa.get("qa_status") != "QA_PASS":
            continue
        if pa.get("source_file_sha256") != file_sha:
            continue

        preview_ref = pa.get("preview_ref", "")
        if not preview_ref or not preview_ref.startswith("storage://"):
            continue

        targets.append(FormTarget(
            form_id=form_id,
            slug=slug,
            file_id=file_id,
            file_sha256=file_sha,
            preview_ref=preview_ref,
            thumb_path=f"thumbnails/{form_id}-{file_sha[:16]}.webp",
        ))

    return targets


# ---------------------------------------------------------------------------
# Per-form processing
# ---------------------------------------------------------------------------

def _recheck_authority(sb, target: FormTarget) -> Optional[str]:
    """Returns None on pass, error reason string on fail."""
    try:
        vr = sb.table(_VIEW).select("id").eq("id", target.form_id).limit(1).execute()
        if not vr.data:
            return "form_unpublished"
    except Exception as exc:
        return f"view_error:{exc}"

    try:
        sr = (
            sb.table(_SOURCES)
            .select("rights_status")
            .eq("form_id", target.form_id)
            .eq("is_active", True)
            .execute()
        )
        sources = sr.data or []
        if not sources or any(s.get("rights_status") != "CLEARED" for s in sources):
            return "sources_not_cleared"
    except Exception as exc:
        return f"sources_error:{exc}"

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
        if not ar.data:
            return "no_current_approval"
        hashes = ar.data[0].get("approved_file_hashes") or []
        match = next(
            (h for h in hashes
             if str(h.get("file_id")) == target.file_id
             and h.get("sha256") == target.file_sha256),
            None,
        )
        if not match:
            return "approval_binding_failed"
    except Exception as exc:
        return f"approval_error:{exc}"

    return None


def _parse_preview_path(preview_ref: str) -> str:
    rest = preview_ref[len("storage://"):]
    slash = rest.find("/")
    bucket = rest[:slash]
    path   = rest[slash + 1:]
    if bucket != BUCKET:
        raise ValueError(f"Unexpected bucket {bucket!r}")
    if ".." in path.split("/"):
        raise ValueError(f"Path traversal in {path!r}")
    return path


def _process_one(sb, target: FormTarget, generate_fn) -> str:
    import httpx

    auth_err = _recheck_authority(sb, target)
    if auth_err:
        log.info("  %s — skip (authority): %s", target.slug, auth_err)
        return f"skipped:{auth_err}"

    # Parse preview storage path
    try:
        preview_path = _parse_preview_path(target.preview_ref)
    except ValueError as exc:
        return f"failed:bad_preview_ref:{exc}"

    # Signed URL for preview
    try:
        signed = sb.storage.from_(BUCKET).create_signed_url(preview_path, expires_in=120)
        signed_url = signed.get("signedURL") or signed.get("signedUrl") or ""
        if not signed_url:
            raise ValueError("empty signed URL")
    except Exception as exc:
        return f"failed:signed_url:{exc}"

    # Download preview PNG
    try:
        r = httpx.get(signed_url, follow_redirects=True, timeout=60)
        r.raise_for_status()
        preview_bytes = r.content
    except Exception as exc:
        return f"failed:download:{exc}"

    # Generate WebP
    try:
        result = generate_fn(preview_bytes)
    except Exception as exc:
        return f"failed:generate:{exc}"

    # Upload to Storage — upsert=false (skip if already exists)
    try:
        sb.storage.from_(BUCKET).upload(
            path=target.thumb_path,
            file=result.webp_bytes,
            file_options={"content-type": "image/webp", "upsert": "false"},
        )
    except Exception as exc:
        err_str = str(exc).lower()
        if "already exists" in err_str or "duplicate" in err_str or "409" in err_str:
            log.info("  %s — skip: thumbnail already exists in Storage", target.slug)
            return "skipped:already_exists"
        return f"failed:upload:{exc}"

    log.info("  OK %s — %d B WebP sha256=%s…",
             target.slug, result.byte_count, result.output_sha256[:12])
    return "generated"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-shot thumbnail generator for reference forms"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run", dest="mode", action="store_const", const="dry_run", default="dry_run",
        help="Show eligible forms only — no writes (default)"
    )
    mode_group.add_argument(
        "--execute", dest="mode", action="store_const", const="execute",
        help="Generate and upload thumbnails (requires Owner G4 approval)"
    )
    args = parser.parse_args()

    _require_deps()
    from services.reference_form_thumbnail_svc import generate_thumbnail, GENERATION_VERSION

    sb = _get_supabase()
    targets = _collect_targets(sb)

    if args.mode == "dry_run":
        log.info("=== Thumbnail Generator DRY-RUN === eligible=%d version=%s",
                 len(targets), GENERATION_VERSION)
        for t in targets:
            log.info("  %s  form_id=%s", t.slug, t.form_id)
        log.info("Re-run with --execute to generate (requires Owner G4 approval).")
        return

    # --- execute ---
    stats = Stats(total=len(targets))
    log.info("=== Thumbnail Generator EXECUTE === targets=%d version=%s",
             len(targets), GENERATION_VERSION)

    if not targets:
        log.info("No eligible forms found.")
        return

    for t in targets:
        outcome = _process_one(sb, t, generate_thumbnail)
        if outcome == "generated":
            stats.generated += 1
        elif outcome.startswith("skipped:"):
            stats.skipped += 1
        elif outcome.startswith("failed:"):
            stats.failed += 1
            stats.errors.append((t.slug, outcome))
            log.warning("  FAIL %s — %s", t.slug, outcome)
        else:
            stats.skipped += 1

    log.info("=== Done: generated=%d skipped=%d failed=%d ===",
             stats.generated, stats.skipped, stats.failed)
    if stats.errors:
        for slug, reason in stats.errors:
            log.warning("  %s: %s", slug, reason)

    if stats.failed:
        sys.exit(2)


if __name__ == "__main__":
    main()
