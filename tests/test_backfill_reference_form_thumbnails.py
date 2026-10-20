"""
WO-WWW-SS-THUMBNAIL-001 P3-R2 — Backfill script unit tests.

B1  Concurrent claim: only 1 of 2 simultaneous claims succeeds
B2  QA_PASS not overwritten by concurrent process
B3  Signed URL failure releases PENDING claim → QA_FAIL
B4  Download failure releases PENDING claim → QA_FAIL
B5  PENDING crash recovery: --reset-pending → NULL → re-claimable
B6  Storage success / DB failure → Storage rollback + QA_FAIL
B7  Dry-run before migration: survey-only, DB/Storage writes = 0
B8  Approval revocation during backfill → skipped
B9  Partial failure → non-zero exit code (sys.exit(2))
"""
from __future__ import annotations

import hashlib
import sys
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

def _import_backfill():
    from scripts.backfill_reference_form_thumbnails import (
        _atomic_claim,
        _release_claim,
        _reset_pending_claims,
        _process_one,
        _recheck_authority,
        _dry_run_pre_migration,
        FormTarget,
        THUMBNAIL_BUCKET,
        THUMBNAIL_PREFIX,
        _PREVIEW,
        _VIEW,
        _SOURCES,
        _APPROVALS,
        _FILES,
    )
    return {
        "_atomic_claim": _atomic_claim,
        "_release_claim": _release_claim,
        "_reset_pending_claims": _reset_pending_claims,
        "_process_one": _process_one,
        "_recheck_authority": _recheck_authority,
        "_dry_run_pre_migration": _dry_run_pre_migration,
        "FormTarget": FormTarget,
        "THUMBNAIL_BUCKET": THUMBNAIL_BUCKET,
        "THUMBNAIL_PREFIX": THUMBNAIL_PREFIX,
        "_PREVIEW": _PREVIEW,
    }


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_FORM_ID = "aaaa0000-0000-0000-0000-000000000001"
_SLUG    = "safety-training"
_FILE_ID = "bbbb0000-0000-0000-0000-000000000002"
_SHA256  = "abcdef1234567890" * 4
_PA_ID   = "cccc0000-0000-0000-0000-000000000003"

_PREVIEW_TABLE  = "reference_form_preview_artifacts"
_VIEW_TABLE     = "reference_form_public_view"
_SOURCES_TABLE  = "reference_form_sources"
_APPROVAL_TABLE = "reference_form_approvals"

WEBP_1PX = (
    b"RIFF$\x00\x00\x00WEBPVP8 "
    b"\x18\x00\x00\x000\x01\x00\x9d\x01*"
    b"\x01\x00\x01\x00\x02\x00\x34\x25\xa4\x00\x03p\x00\xfe\xfb\x94\x00\x00"
)
_WEBP_SHA = hashlib.sha256(WEBP_1PX).hexdigest()


def _make_target(**overrides):
    m = _import_backfill()
    defaults = dict(
        form_id=_FORM_ID,
        slug=_SLUG,
        file_id=_FILE_ID,
        file_sha256=_SHA256,
        preview_artifact_id=_PA_ID,
        preview_ref=f"storage://reference-forms-preview/previews/{_PA_ID}.png",
        source_file_sha256=_SHA256,
        existing_thumbnail_status=None,
    )
    defaults.update(overrides)
    return m["FormTarget"](**defaults)


def _make_sb(
    *,
    update_claim_data=None,   # data returned by _atomic_claim UPDATE
    release_data=None,
    authority_view=True,
    authority_sources=True,
    authority_approval=True,
):
    """
    Build a minimal Supabase mock.

    - Chaining: all .select/.update/.eq/.is_/.in_/.limit/.order return the chain.
    - execute() returns a result with .data = data_list based on table name.
    - update_claim_data: controls what _atomic_claim's UPDATE returns.
    """
    sb = MagicMock()

    # --- authority data ---
    _view_row = [{
        "id": _FORM_ID, "canonical_slug": _SLUG,
        "qa_pass_files": [{"file_id": _FILE_ID, "sha256": _SHA256, "has_preview": True}],
    }] if authority_view else []
    _src_rows = [{"source_name": "KOSHA", "rights_status": "CLEARED"}] if authority_sources else []
    _appr_row = [{
        "approved_file_hashes": [{"file_id": _FILE_ID, "sha256": _SHA256}]
    }] if authority_approval else []

    # claim UPDATE data — default: success (data=[{}])
    _claim_data = [{"id": _PA_ID}] if update_claim_data is None else update_claim_data

    # track call counts to differentiate NULL-claim vs QA_FAIL-claim
    _claim_call_count = {"n": 0}

    def _make_chain(data_list, is_update=False, claim_call_ref=None):
        chain = MagicMock()
        result = MagicMock()
        if is_update and claim_call_ref is not None:
            # First two update calls are atomic claims (NULL then QA_FAIL).
            # Return _claim_data for the first, [] for the second.
            def _exec():
                r = MagicMock()
                claim_call_ref["n"] += 1
                r.data = _claim_data if claim_call_ref["n"] == 1 else []
                return r
            chain.execute.side_effect = _exec
        else:
            result.data = data_list
            chain.execute.return_value = result
        for m in ("select", "update", "eq", "is_", "in_", "limit", "order"):
            getattr(chain, m).return_value = chain
        tbl = MagicMock()
        tbl.select.return_value = chain
        tbl.update.return_value = chain
        return tbl

    _data_map = {
        _VIEW_TABLE:     _view_row,
        _SOURCES_TABLE:  _src_rows,
        _APPROVAL_TABLE: _appr_row,
        _PREVIEW_TABLE:  [{"thumbnail_qa_status": None}],  # current status check
    }

    update_call_count = {"n": 0}

    def _side_effect(name):
        if name == _PREVIEW_TABLE:
            # First update call is atomic claim → use claim data
            return _make_chain(
                [],
                is_update=True,
                claim_call_ref=update_call_count,
            )
        return _make_chain(_data_map.get(name, []))

    sb.table.side_effect = _side_effect

    signed = MagicMock()
    signed.get = lambda k, default=None: (
        "https://storage.example.com/signed" if k in ("signedURL", "signedUrl") else default
    )
    sb.storage.from_.return_value.create_signed_url.return_value = signed
    sb.storage.from_.return_value.upload.return_value = MagicMock()
    sb.storage.from_.return_value.remove.return_value = MagicMock()

    return sb


def _make_generate_fn(bytes_=WEBP_1PX):
    from unittest.mock import MagicMock
    result = MagicMock()
    result.webp_bytes    = bytes_
    result.output_sha256 = hashlib.sha256(bytes_).hexdigest()
    result.byte_count    = len(bytes_)
    result.generation_version = "v1-pillow"
    generate_fn = MagicMock(return_value=result)
    return generate_fn


# ===========================================================================
# B1 — Concurrent claim: only 1 of 2 simultaneous claims succeeds
# ===========================================================================

def test_B1_concurrent_claim_only_one_succeeds():
    m = _import_backfill()

    # First atomic_claim call returns data (success), second returns empty (lost)
    call_count = {"n": 0}

    def _make_chain_for_preview():
        chain = MagicMock()
        for method in ("select", "update", "eq", "is_", "in_", "limit", "order"):
            getattr(chain, method).return_value = chain

        def _exec():
            r = MagicMock()
            call_count["n"] += 1
            r.data = [{"id": _PA_ID}] if call_count["n"] == 1 else []
            return r

        chain.execute.side_effect = _exec
        tbl = MagicMock()
        tbl.select.return_value = chain
        tbl.update.return_value = chain
        return tbl

    sb = MagicMock()
    sb.table.side_effect = lambda name: _make_chain_for_preview()

    # First claim: NULL → PENDING
    result1 = m["_atomic_claim"](sb, _PA_ID)
    # Second claim: NULL failed, QA_FAIL also fails → False
    result2 = m["_atomic_claim"](sb, _PA_ID)

    assert result1 is True,  "First claim should succeed"
    assert result2 is False, "Second concurrent claim should fail"


# ===========================================================================
# B2 — QA_PASS rows are not overwritten by concurrent claim
# ===========================================================================

def test_B2_qa_pass_not_overwritten():
    m = _import_backfill()

    # Simulate: all UPDATE attempts return [] (QA_PASS row can't be claimed)
    chain = MagicMock()
    result = MagicMock()
    result.data = []  # QA_PASS doesn't match NULL or QA_FAIL conditions
    chain.execute.return_value = result
    for method in ("select", "update", "eq", "is_", "in_", "limit", "order"):
        getattr(chain, method).return_value = chain
    tbl = MagicMock()
    tbl.update.return_value = chain

    sb = MagicMock()
    sb.table.return_value = tbl

    claimed = m["_atomic_claim"](sb, _PA_ID)
    assert claimed is False, "QA_PASS row should not be claimable"


# ===========================================================================
# B3 — Signed URL failure releases PENDING claim → QA_FAIL
# ===========================================================================

def test_B3_signed_url_failure_releases_claim():
    """Patch _atomic_claim and _release_claim directly to verify release is called."""
    m = _import_backfill()

    with (
        patch("scripts.backfill_reference_form_thumbnails._atomic_claim", return_value=True),
        patch("scripts.backfill_reference_form_thumbnails._recheck_authority", return_value=None),
        patch("scripts.backfill_reference_form_thumbnails._release_claim") as mock_release,
    ):
        sb = MagicMock()
        sb.storage.from_.return_value.create_signed_url.side_effect = Exception("storage down")

        result = m["_process_one"](sb, _make_target(), MagicMock(), dry_run=False)

    assert result.startswith("failed:signed_url"), f"Got: {result}"
    mock_release.assert_called_once_with(sb, _PA_ID)


# ===========================================================================
# B4 — Download failure releases PENDING claim → QA_FAIL
# ===========================================================================

def test_B4_download_failure_releases_claim():
    """Patch _atomic_claim and _release_claim directly to verify release is called."""
    m = _import_backfill()

    with (
        patch("scripts.backfill_reference_form_thumbnails._atomic_claim", return_value=True),
        patch("scripts.backfill_reference_form_thumbnails._recheck_authority", return_value=None),
        patch("scripts.backfill_reference_form_thumbnails._release_claim") as mock_release,
    ):
        signed = MagicMock()
        signed.get = lambda k, d=None: "https://example.com/signed" if k in ("signedURL", "signedUrl") else d

        sb = MagicMock()
        sb.storage.from_.return_value.create_signed_url.return_value = signed

        with patch("httpx.get", side_effect=Exception("network error")):
            result = m["_process_one"](sb, _make_target(), MagicMock(), dry_run=False)

    assert result.startswith("failed:download"), f"Got: {result}"
    mock_release.assert_called_once_with(sb, _PA_ID)


# ===========================================================================
# B5 — Crash recovery: --reset-pending moves PENDING → NULL
# ===========================================================================

def test_B5_reset_pending_enables_retry():
    m = _import_backfill()

    reset_data = [{"id": _PA_ID, "thumbnail_qa_status": "PENDING"}]

    chain = MagicMock()
    res = MagicMock()
    res.data = reset_data
    chain.execute.return_value = res
    for method in ("select", "update", "eq", "is_", "in_", "limit", "order"):
        getattr(chain, method).return_value = chain
    tbl = MagicMock()
    tbl.update.return_value = chain

    sb = MagicMock()
    sb.table.return_value = tbl

    count = m["_reset_pending_claims"](sb)
    assert count == len(reset_data), f"Should reset {len(reset_data)} PENDING rows, got {count}"


# ===========================================================================
# B6 — Storage success / DB failure → Storage rollback + QA_FAIL
# ===========================================================================

def test_B6_storage_success_db_failure_rollback():
    """DB update raises → Storage remove is called + _release_claim."""
    m = _import_backfill()

    storage_remove_calls = []

    with (
        patch("scripts.backfill_reference_form_thumbnails._atomic_claim", return_value=True),
        patch("scripts.backfill_reference_form_thumbnails._recheck_authority", return_value=None),
        patch("scripts.backfill_reference_form_thumbnails._release_claim") as mock_release,
    ):
        signed = MagicMock()
        signed.get = lambda k, d=None: "https://example.com/signed" if k in ("signedURL", "signedUrl") else d

        def _track_remove(paths):
            storage_remove_calls.extend(paths)
            return MagicMock()

        sb = MagicMock()
        sb.storage.from_.return_value.create_signed_url.return_value = signed
        sb.storage.from_.return_value.upload.return_value = MagicMock()
        sb.storage.from_.return_value.remove.side_effect = _track_remove

        # DB update fails
        db_chain = MagicMock()
        db_chain.eq.return_value = db_chain
        db_chain.execute.side_effect = Exception("DB write failed")
        sb.table.return_value.update.return_value = db_chain

        generate_fn = _make_generate_fn()

        with patch("httpx.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, content=b"PNG_PREVIEW",
                headers={}, raise_for_status=lambda: None,
            )
            result = m["_process_one"](sb, target=_make_target(), generate_fn=generate_fn, dry_run=False)

    assert result.startswith("failed:db_update"), f"Got: {result}"
    assert len(storage_remove_calls) >= 1, "Storage file should be rolled back on DB failure"
    mock_release.assert_called_once_with(sb, _PA_ID)


# ===========================================================================
# B7 — Dry-run before migration: read-only survey, no DB/Storage writes
# ===========================================================================

def test_B7_dry_run_pre_migration_no_writes():
    m = _import_backfill()

    write_calls = []

    def _make_chain(data):
        chain = MagicMock()
        res = MagicMock()
        res.data = data if isinstance(data, list) else [data]
        chain.execute.return_value = res

        def _track_write(*a, **kw):
            write_calls.append(True)
            return chain

        chain.update.side_effect = _track_write
        for method in ("select", "eq", "is_", "in_", "limit", "order"):
            getattr(chain, method).return_value = chain
        tbl = MagicMock()
        tbl.select.return_value = chain
        tbl.update.side_effect = _track_write
        return tbl

    sb = MagicMock()
    sb.table.side_effect = lambda name: _make_chain([
        {"id": _FORM_ID, "canonical_slug": _SLUG,
         "qa_pass_files": [{"file_id": _FILE_ID, "sha256": _SHA256, "has_preview": True}]}
    ] if name == _VIEW_TABLE else [])

    m["_dry_run_pre_migration"](sb)

    assert len(write_calls) == 0, "Pre-migration dry-run must make zero DB writes"
    assert sb.storage.from_.call_count == 0, "Pre-migration dry-run must make zero Storage calls"


# ===========================================================================
# B8 — Approval revocation causes backfill skip
# ===========================================================================

def test_B8_approval_revocation_skips_form():
    m = _import_backfill()

    def _make_chain(data):
        chain = MagicMock()
        res = MagicMock()
        res.data = data if isinstance(data, list) else [data]
        chain.execute.return_value = res
        for method in ("select", "update", "eq", "is_", "in_", "limit", "order"):
            getattr(chain, method).return_value = chain
        tbl = MagicMock()
        tbl.select.return_value = chain
        tbl.update.return_value = chain
        return tbl

    sb = MagicMock()
    sb.table.side_effect = lambda name: _make_chain(
        [{"id": _FORM_ID, "qa_pass_files": [{"file_id": _FILE_ID, "sha256": _SHA256, "has_preview": True}]}]
        if name == _VIEW_TABLE
        else [{"source_name": "KOSHA", "rights_status": "CLEARED"}]
        if name == _SOURCES_TABLE
        else []  # approval returns empty → no current approval
    )

    target = _make_target()
    auth_err = m["_recheck_authority"](sb, target)

    assert auth_err == "no_current_approval", f"Expected approval revocation, got: {auth_err}"


# ===========================================================================
# B9 — Partial failure → sys.exit(2)
# ===========================================================================

def test_B9_partial_failure_exits_nonzero():
    """main() must call sys.exit(2) when any form fails."""
    import importlib
    import scripts.backfill_reference_form_thumbnails as mod

    def _mock_collect(sb):
        return [_make_target()]

    def _mock_process(sb, target, generate_fn, dry_run):
        return "failed:generate:test error"

    with (
        patch.object(mod, "_get_supabase", return_value=MagicMock()),
        patch.object(mod, "_check_migration_applied", return_value=True),
        patch.object(mod, "_collect_targets", _mock_collect),
        patch.object(mod, "_process_one", _mock_process),
        patch("sys.argv", ["backfill", "--execute"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        mod.main()

    assert exc_info.value.code == 2, f"Expected exit code 2, got {exc_info.value.code}"
