"""Raw CSI CSV retention policy. This PR does not write R2."""
from __future__ import annotations

from services.csi_accidents.contract import DATASET_ID
from services.kosha_safety_materials.storage.r2_store import ALLOWED_BUCKET

# Existing production R2 bucket is KOSHA-originals only (key prefix kosha/).
EXISTING_OFFICIAL_BUCKET = ALLOWED_BUCKET
REUSE_EXISTING_BUCKET = False
REUSE_REASON = (
    "tai-kosha-originals is hardcoded for KOSHA binaries (kosha/... keys, "
    "DELETE forbidden). CSI CSV is a different official source; do not mix."
)
POLICY = "IMMUTABLE_PRIVATE_RETENTION"
OVERWRITE = False
DELETE = False
R2_WRITES_OPEN = False


def proposed_object_key(effective_date: str, file_sha256: str, filename: str) -> str:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"csi/{DATASET_ID}/{effective_date}/{file_sha256}/{safe_name}"


def storage_report() -> dict:
    return {
        "policy": POLICY,
        "private": True,
        "overwrite": OVERWRITE,
        "delete": DELETE,
        "r2_writes_open": R2_WRITES_OPEN,
        "existing_bucket": EXISTING_OFFICIAL_BUCKET,
        "reuse_existing_bucket": REUSE_EXISTING_BUCKET,
        "reuse_reason": REUSE_REASON,
        "proposed_key_pattern": "csi/{dataset_id}/{effective_date}/{sha256}/{filename}",
        "new_bucket_this_pr": False,
    }
