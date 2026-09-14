"""Identity census validation and previous/current diff.

Generic over string identities and optional change tokens.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence


class CensusError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CensusDiff:
    new: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]
    removed: tuple[str, ...]

    @property
    def hydration_identities(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.new) | set(self.changed)))


def validate_identity_census(identities: Sequence[Optional[str]], *, total_count: int) -> tuple[str, ...]:
    if total_count < 0:
        raise CensusError("TOTAL_COUNT_INVALID", "totalCount must be >= 0")
    normalized: list[str] = []
    missing = 0
    for raw in identities:
        value = (raw or "").strip()
        if not value:
            missing += 1
            continue
        normalized.append(value)
    if missing:
        raise CensusError("MISSING_IDENTITY", f"missing identity count={missing}")
    unique = set(normalized)
    if len(unique) != len(normalized):
        raise CensusError(
            "DUPLICATE_IDENTITY",
            f"duplicate identity count={len(normalized) - len(unique)}",
        )
    if len(normalized) != total_count:
        raise CensusError(
            "COUNT_MISMATCH",
            f"collected={len(normalized)} totalCount={total_count}",
        )
    return tuple(normalized)


def diff_identity_maps(
    previous: Mapping[str, Optional[str]],
    current: Mapping[str, Optional[str]],
) -> CensusDiff:
    prev_keys = set(previous)
    curr_keys = set(current)
    new = tuple(sorted(curr_keys - prev_keys))
    removed = tuple(sorted(prev_keys - curr_keys))
    changed: list[str] = []
    unchanged: list[str] = []
    for key in sorted(prev_keys & curr_keys):
        if previous[key] != current[key]:
            changed.append(key)
        else:
            unchanged.append(key)
    return CensusDiff(
        new=new,
        changed=tuple(changed),
        unchanged=tuple(unchanged),
        removed=removed,
    )
