"""Deterministic identity resolution. No fuzzy / LLM / embedding match."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from services.kosha_msds.bootstrap import BootstrapIdentity, normalize_name
from services.kosha_msds.contract import (
    MATCH_AMBIGUOUS,
    MATCH_CAS_EXACT,
    MATCH_COMPOUND_EXACT,
    MATCH_DIRECT_OFFICIAL_ID,
    MATCH_NAME_EXACT,
    MATCH_UNMATCHED,
)
from services.kosha_msds.current_index import OfficialCurrentRow


@dataclass(frozen=True)
class JoinRow:
    official: OfficialCurrentRow
    resolved_chem_id: Optional[str]
    present_in_secondary: bool
    secondary_chem_id: Optional[str]
    match_method: str

    def as_row(self) -> dict[str, object]:
        return {
            "official_name": self.official.official_name,
            "official_cas": self.official.official_cas,
            "official_revision_date": self.official.official_revision_date,
            "official_identifier_if_present": self.official.chem_id,
            "official_page": self.official.official_page,
            "resolved_chem_id": self.resolved_chem_id,
            "present_in_secondary": self.present_in_secondary,
            "secondary_chemId": self.secondary_chem_id,
            "match_method": self.match_method,
        }


def _index_unique(rows: list[BootstrapIdentity], key_fn) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        key = key_fn(row)
        if key:
            out[key].append(row.chem_id)
    return out


def _row(
    official: OfficialCurrentRow,
    *,
    resolved: Optional[str],
    present: bool,
    secondary: Optional[str],
    method: str,
) -> JoinRow:
    return JoinRow(
        official=official,
        resolved_chem_id=resolved,
        present_in_secondary=present,
        secondary_chem_id=secondary,
        match_method=method,
    )


def join_official_to_secondary(
    official_rows: list[OfficialCurrentRow],
    secondary_rows: list[BootstrapIdentity],
) -> list[JoinRow]:
    by_id = {row.chem_id: row for row in secondary_rows}
    by_cas = _index_unique(secondary_rows, lambda r: r.cas_no)
    by_name = _index_unique(secondary_rows, lambda r: normalize_name(r.name_ko))
    by_en = _index_unique(secondary_rows, lambda r: normalize_name(r.name_en))
    joined: list[JoinRow] = []
    for official in official_rows:
        if official.chem_id:
            present = official.chem_id in by_id
            joined.append(
                _row(
                    official,
                    resolved=official.chem_id,
                    present=present,
                    secondary=official.chem_id if present else None,
                    method=MATCH_DIRECT_OFFICIAL_ID,
                )
            )
            continue
        cas_hits = by_cas.get(official.official_cas or "", [])
        if official.official_cas and len(cas_hits) == 1:
            joined.append(
                _row(official, resolved=cas_hits[0], present=True, secondary=cas_hits[0], method=MATCH_CAS_EXACT)
            )
            continue
        if official.official_cas and len(cas_hits) > 1:
            joined.append(_row(official, resolved=None, present=False, secondary=None, method=MATCH_AMBIGUOUS))
            continue
        name_key = normalize_name(official.official_name)
        name_hits = by_name.get(name_key or "", [])
        if name_key and len(name_hits) == 1:
            joined.append(
                _row(official, resolved=name_hits[0], present=True, secondary=name_hits[0], method=MATCH_NAME_EXACT)
            )
            continue
        if name_key and len(name_hits) > 1:
            joined.append(_row(official, resolved=None, present=False, secondary=None, method=MATCH_AMBIGUOUS))
            continue
        en_hits = by_en.get(name_key or "", [])
        if name_key and len(en_hits) == 1:
            joined.append(
                _row(
                    official,
                    resolved=en_hits[0],
                    present=True,
                    secondary=en_hits[0],
                    method=MATCH_COMPOUND_EXACT,
                )
            )
            continue
        joined.append(_row(official, resolved=None, present=False, secondary=None, method=MATCH_UNMATCHED))
    return joined


def join_counts(rows: list[JoinRow]) -> dict[str, int]:
    counts = {
        MATCH_DIRECT_OFFICIAL_ID: 0,
        MATCH_CAS_EXACT: 0,
        MATCH_NAME_EXACT: 0,
        MATCH_COMPOUND_EXACT: 0,
        MATCH_UNMATCHED: 0,
        MATCH_AMBIGUOUS: 0,
    }
    resolved: set[str] = set()
    in_secondary: set[str] = set()
    present_n = 0
    official_only = 0
    for row in rows:
        counts[row.match_method] = counts.get(row.match_method, 0) + 1
        if row.resolved_chem_id:
            resolved.add(row.resolved_chem_id)
        if row.present_in_secondary:
            present_n += 1
            if row.secondary_chem_id:
                in_secondary.add(row.secondary_chem_id)
        elif row.match_method == MATCH_DIRECT_OFFICIAL_ID:
            official_only += 1
    total = len(rows)
    counts["resolved_unique_chemId"] = len(resolved)
    counts["mapped_unique_chemId"] = len(in_secondary)
    counts["present_in_secondary"] = present_n
    counts["official_only"] = official_only
    counts["official_current_total"] = total
    counts["direct_official_id_rate_x100"] = round((counts[MATCH_DIRECT_OFFICIAL_ID] / total * 100.0) if total else 0.0, 2)
    counts["secondary_overlap_x100"] = round((present_n / total * 100.0) if total else 0.0, 2)
    return counts
