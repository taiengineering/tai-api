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
    secondary_chem_id: Optional[str]
    match_method: str

    def as_row(self) -> dict[str, object]:
        return {
            "official_name": self.official.official_name,
            "official_cas": self.official.official_cas,
            "official_revision_date": self.official.official_revision_date,
            "official_identifier_if_present": self.official.chem_id,
            "official_page": self.official.official_page,
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
            joined.append(
                JoinRow(
                    official=official,
                    secondary_chem_id=official.chem_id if official.chem_id in by_id else official.chem_id,
                    match_method=MATCH_DIRECT_OFFICIAL_ID,
                )
            )
            continue
        cas_hits = by_cas.get(official.official_cas or "", [])
        if official.official_cas and len(cas_hits) == 1:
            joined.append(JoinRow(official, cas_hits[0], MATCH_CAS_EXACT))
            continue
        if official.official_cas and len(cas_hits) > 1:
            joined.append(JoinRow(official, None, MATCH_AMBIGUOUS))
            continue
        name_key = normalize_name(official.official_name)
        name_hits = by_name.get(name_key or "", [])
        if name_key and len(name_hits) == 1:
            joined.append(JoinRow(official, name_hits[0], MATCH_NAME_EXACT))
            continue
        if name_key and len(name_hits) > 1:
            joined.append(JoinRow(official, None, MATCH_AMBIGUOUS))
            continue
        en_hits = by_en.get(name_key or "", [])
        if name_key and len(en_hits) == 1:
            joined.append(JoinRow(official, en_hits[0], MATCH_COMPOUND_EXACT))
            continue
        joined.append(JoinRow(official, None, MATCH_UNMATCHED))
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
    mapped: set[str] = set()
    for row in rows:
        counts[row.match_method] = counts.get(row.match_method, 0) + 1
        if row.secondary_chem_id and row.match_method != MATCH_AMBIGUOUS:
            mapped.add(row.secondary_chem_id)
        if row.match_method == MATCH_DIRECT_OFFICIAL_ID and row.official.chem_id:
            mapped.add(row.official.chem_id)
    unique = len(mapped)
    total = len(rows)
    coverage = (unique / total * 100.0) if total else 0.0
    counts["mapped_unique_chemId"] = unique
    counts["official_current_total"] = total
    counts["mapping_coverage_x100"] = round(coverage, 2)
    return counts
