"""Common binary storage size policy — PATCH-5B-SIZE-POLICY.

Single SoT for KOSHA source GET and R2 GET/readback.
"""
from __future__ import annotations

MAX_BINARY_BYTES = 64 * 1024 * 1024
OVERSIZE_REASON = "SOURCE_ASSET_OVERSIZE_POLICY"


def parsed_file_size(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def is_metadata_oversize(value) -> bool:
    """Trusted positive metadata only. NULL/0 are not pre-network oversize."""
    n = parsed_file_size(value)
    return n is not None and n > MAX_BINARY_BYTES


def oversize_observed(*, file_size, file_name, extra: dict | None = None) -> list[dict]:
    row = {
        "file_size": file_size,
        "max_binary_bytes": MAX_BINARY_BYTES,
        "file_name": file_name,
    }
    if extra:
        row.update(extra)
    return [row]
