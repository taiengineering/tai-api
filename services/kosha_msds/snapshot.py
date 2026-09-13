"""PROBE-only snapshot rules. FULL_OFFICIAL / global current are CHEM-03+."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from services.kosha_msds.contract import (
    CHEM02_ALLOWED_ENUMERATION,
    CHEM04_ALLOWED_ENUMERATION,
    ENUMERATION_FULL_OFFICIAL,
    ENUMERATION_PROBE,
    PUBLISH_NOT_PUBLISHED,
    PUBLISH_PUBLISHED_FULL,
    SNAPSHOT_COMPLETED,
    SNAPSHOT_RUNNING,
    SOURCE_CONTRACT_VERSION,
    SOURCE_ID,
)


class KoshaMsdsSnapshotError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SnapshotSpec:
    enumeration_mode: str
    status: str
    publish_state: str = PUBLISH_NOT_PUBLISHED
    expected_count: Optional[int] = None
    source_id: str = SOURCE_ID
    source_contract_version: str = SOURCE_CONTRACT_VERSION
    run_type: str = "MANUAL_PROBE"


def validate_enumeration_mode(mode: str, *, chem02: bool = True) -> str:
    if chem02 and mode not in CHEM02_ALLOWED_ENUMERATION:
        raise KoshaMsdsSnapshotError(
            "ENUMERATION_FORBIDDEN",
            f"CHEM-02 allows only {sorted(CHEM02_ALLOWED_ENUMERATION)}; got {mode}",
        )
    if mode == ENUMERATION_FULL_OFFICIAL and chem02:
        raise KoshaMsdsSnapshotError(
            "FULL_OFFICIAL_BLOCKED",
            "FULL_OFFICIAL is forbidden before corpus enumeration gate",
        )
    if not chem02 and mode not in CHEM04_ALLOWED_ENUMERATION:
        raise KoshaMsdsSnapshotError(
            "ENUMERATION_FORBIDDEN",
            f"CHEM-04 allows only {sorted(CHEM04_ALLOWED_ENUMERATION)}; got {mode}",
        )
    return mode


def can_publish_global_current(spec: SnapshotSpec) -> bool:
    return (
        spec.status == SNAPSHOT_COMPLETED
        and spec.enumeration_mode == ENUMERATION_FULL_OFFICIAL
        and spec.publish_state == PUBLISH_PUBLISHED_FULL
    )


def assert_probe_not_full(spec: SnapshotSpec) -> None:
    validate_enumeration_mode(spec.enumeration_mode, chem02=True)
    if spec.enumeration_mode == ENUMERATION_PROBE and spec.publish_state == PUBLISH_PUBLISHED_FULL:
        raise KoshaMsdsSnapshotError(
            "PROBE_CANNOT_PUBLISH_FULL",
            "PROBE snapshot cannot become PUBLISHED_FULL",
        )
    if spec.expected_count is not None:
        raise KoshaMsdsSnapshotError(
            "EXPECTED_COUNT_FORBIDDEN",
            "CHEM-02 must not set expected_count from unofficial web totals",
        )


def new_probe_spec() -> SnapshotSpec:
    spec = SnapshotSpec(
        enumeration_mode=ENUMERATION_PROBE,
        status="RUNNING",
        publish_state=PUBLISH_NOT_PUBLISHED,
        expected_count=None,
    )
    assert_probe_not_full(spec)
    return spec


def new_full_official_spec(expected_count: int, *, run_type: str = "FULL_SYNC") -> SnapshotSpec:
    """CHEM-04 candidate snapshot. Does not publish. expected_count must be API totalCount."""
    validate_enumeration_mode(ENUMERATION_FULL_OFFICIAL, chem02=False)
    if expected_count <= 0:
        raise KoshaMsdsSnapshotError(
            "FULL_LIST_BLOCKED",
            "FULL_OFFICIAL expected_count must be API totalCount > 0",
        )
    return SnapshotSpec(
        enumeration_mode=ENUMERATION_FULL_OFFICIAL,
        status=SNAPSHOT_RUNNING,
        publish_state=PUBLISH_NOT_PUBLISHED,
        expected_count=expected_count,
        run_type=run_type,
    )


def evaluate_publish_full(
    spec: SnapshotSpec,
    *,
    incomplete_count: int,
    census_ok: bool,
) -> bool:
    """PUBLISHED_FULL is allowed only after census+detail gates. This WO does not promote."""
    return (
        spec.enumeration_mode == ENUMERATION_FULL_OFFICIAL
        and spec.status == SNAPSHOT_COMPLETED
        and spec.publish_state == PUBLISH_PUBLISHED_FULL
        and census_ok
        and incomplete_count == 0
        and can_publish_global_current(spec)
    )
