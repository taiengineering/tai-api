"""KOSHA MSDS identity census + OpenAPI detail hydration + incremental sync.

getChemList is a documented search list, not a global enumerator.
This runner hydrates a *known* chemId census (official seed) via Detail01–16.
It does not crawl chemList.do, guess identities, or apply production ingest.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional

from services.kosha_msds.client import FullDetail, KoshaMsdsClient
from services.kosha_msds.contract import (
    ALLOWED_SEARCH_CND,
    ALLOWED_SECTIONS,
    DETAIL_COMPLETE,
    DETAIL_EMPTY_BUT_VALID,
    DETAIL_INCOMPLETE,
    DIFF_CHANGED,
    DIFF_NEW,
    DIFF_UNCHANGED,
    OFFICIAL_SEED_SOURCES,
    REMOVED_CANDIDATE,
    TOTAL_COUNT_SEMANTICS,
    WORKING_PAGE_SIZE,
)
from services.kosha_msds.hash import source_content_hash
from services.kosha_msds.identity import ListCandidate, normalize_chem_id
from services.kosha_msds.snapshot import (
    SnapshotSpec,
    evaluate_publish_full,
    new_full_official_spec,
)
from services.public_data_sync.census import CensusDiff, CensusError, diff_identity_maps, validate_identity_census

SleepFn = Callable[[float], None]
TargetIds = list[str] | tuple[str, ...]


class KoshaMsdsSyncError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ListCensus:
    total_count: int
    page_count: int
    working_page_size: int
    chem_ids: tuple[str, ...]
    last_dates: Mapping[str, Optional[str]]
    rows: tuple[ListCandidate, ...]
    seed_source: Optional[str] = None
    total_count_semantics: str = TOTAL_COUNT_SEMANTICS

    @property
    def identity_map(self) -> dict[str, Optional[str]]:
        return dict(self.last_dates)


@dataclass
class SyncCheckpoint:
    census_ids: list[str] = field(default_factory=list)
    hydration_targets: list[str] = field(default_factory=list)
    completed_chem_ids: list[str] = field(default_factory=list)
    last_completed_chem_id: Optional[str] = None
    detail_calls: int = 0

    def remaining_targets(self) -> list[str]:
        done = set(self.completed_chem_ids)
        return [cid for cid in self.hydration_targets if cid not in done]


@dataclass
class HydrationRecord:
    chem_id: str
    detail: FullDetail
    source_content_hash: Optional[str]
    list_item: dict[str, Optional[str]]


@dataclass
class SyncPlan:
    diff: CensusDiff
    hydration_targets: tuple[str, ...]
    unchanged_detail_calls: int = 0
    detail_calls_planned: int = 0

    @property
    def labels(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for cid in self.diff.new:
            out[cid] = DIFF_NEW
        for cid in self.diff.changed:
            out[cid] = DIFF_CHANGED
        for cid in self.diff.unchanged:
            out[cid] = DIFF_UNCHANGED
        for cid in self.diff.removed:
            out[cid] = REMOVED_CANDIDATE
        return out


def is_documented_search(search_cnd: Optional[int], search_wrd: Optional[str]) -> bool:
    return search_cnd in ALLOWED_SEARCH_CND and bool((search_wrd or "").strip())


def assert_omitted_search_not_corpus(
    *,
    search_cnd: Optional[int],
    search_wrd: Optional[str],
    seed_source: Optional[str],
) -> None:
    """Omitted/blank getChemList is the documented search-only contract, not a dump-all."""
    official = seed_source in OFFICIAL_SEED_SOURCES
    if official:
        return
    if not is_documented_search(search_cnd, search_wrd):
        raise KoshaMsdsSyncError(
            "SEARCH_IS_NOT_CORPUS",
            "omitted/blank getChemList cannot be promoted to a full KOSHA corpus",
        )


def assert_official_seed_for_corpus(seed_source: Optional[str]) -> None:
    if seed_source not in OFFICIAL_SEED_SOURCES:
        raise KoshaMsdsSyncError(
            "INITIAL_FULL_SEED_BLOCKED",
            "full census requires an official chemId seed source",
        )


def collect_list_census(
    client: KoshaMsdsClient,
    *,
    num_of_rows: int = WORKING_PAGE_SIZE,
    search_cnd: Optional[int] = None,
    search_wrd: Optional[str] = None,
    require_corpus: bool = False,
    seed_source: Optional[str] = None,
    sleep_s: float = 0.0,
    sleep_fn: SleepFn = time.sleep,
) -> ListCensus:
    assert_omitted_search_not_corpus(
        search_cnd=search_cnd,
        search_wrd=search_wrd,
        seed_source=seed_source,
    )
    if require_corpus:
        assert_official_seed_for_corpus(seed_source)
        if is_documented_search(search_cnd, search_wrd):
            raise KoshaMsdsSyncError(
                "SEARCH_IS_NOT_CORPUS",
                "getChemList search totalCount is not a full KOSHA corpus",
            )
    first = client.list_page(
        page_no=1,
        num_of_rows=num_of_rows,
        search_cnd=search_cnd,
        search_wrd=search_wrd,
    )
    pages = [first]
    page_size = first.num_of_rows or num_of_rows
    if page_size < 1:
        raise KoshaMsdsSyncError("PAGE_SIZE_INVALID", "numOfRows from API is < 1")
    last_page = max(1, math.ceil(first.total_count / page_size)) if first.total_count else 1
    for page_no in range(2, last_page + 1):
        if sleep_s:
            sleep_fn(sleep_s)
        pages.append(
            client.list_page(
                page_no=page_no,
                num_of_rows=num_of_rows,
                search_cnd=search_cnd,
                search_wrd=search_wrd,
            )
        )
    rows: list[ListCandidate] = []
    for page in pages:
        rows.extend(page.candidates)
    try:
        chem_ids = validate_identity_census(
            [row.chem_id for row in rows],
            total_count=first.total_count,
        )
    except CensusError as exc:
        raise KoshaMsdsSyncError(exc.code, exc.message) from exc
    by_id = {row.chem_id: row for row in rows if row.chem_id}
    last_dates = {cid: by_id[cid].last_date for cid in chem_ids}
    semantics = (
        "OFFICIAL_SEED_CENSUS"
        if seed_source in OFFICIAL_SEED_SOURCES
        else TOTAL_COUNT_SEMANTICS
    )
    return ListCensus(
        total_count=first.total_count,
        page_count=len(pages),
        working_page_size=page_size,
        chem_ids=chem_ids,
        last_dates=last_dates,
        rows=tuple(rows),
        seed_source=seed_source,
        total_count_semantics=semantics,
    )


def plan_incremental(
    previous: Mapping[str, Optional[str]],
    current: Mapping[str, Optional[str]],
) -> SyncPlan:
    diff = diff_identity_maps(previous, current)
    targets = diff.hydration_identities
    return SyncPlan(
        diff=diff,
        hydration_targets=targets,
        unchanged_detail_calls=0,
        detail_calls_planned=len(targets) * len(ALLOWED_SECTIONS),
    )


def initial_sync_plan(current: Mapping[str, Optional[str]]) -> SyncPlan:
    return plan_incremental({}, current)


def _section_map(detail: FullDetail) -> dict[str, list[dict[str, Optional[str]]]]:
    return {key: list(section.items) for key, section in detail.sections.items()}


def hydrate_chem_id(
    client: KoshaMsdsClient,
    candidate: ListCandidate,
    *,
    previous_hash: Optional[str] = None,
) -> HydrationRecord:
    cid = normalize_chem_id(candidate.chem_id)
    if not cid:
        raise KoshaMsdsSyncError("CHEM_ID_REQUIRED", "hydration requires chemId")
    detail = client.get_full_detail(cid)
    digest = source_content_hash(cid, candidate.raw, _section_map(detail))
    if previous_hash and previous_hash == digest and detail.detail_status != DETAIL_INCOMPLETE:
        # identical payload; still return current record (idempotent upsert)
        pass
    return HydrationRecord(
        chem_id=cid,
        detail=detail,
        source_content_hash=digest,
        list_item=dict(candidate.raw),
    )


def run_hydration(
    client: KoshaMsdsClient,
    census: ListCensus,
    targets: TargetIds,
    checkpoint: SyncCheckpoint,
    *,
    sleep_s: float = 0.0,
    sleep_fn: SleepFn = time.sleep,
    fail_chem_id: Optional[str] = None,
) -> list[HydrationRecord]:
    by_id = {row.chem_id: row for row in census.rows if row.chem_id}
    checkpoint.census_ids = list(census.chem_ids)
    checkpoint.hydration_targets = list(targets)
    records: list[HydrationRecord] = []
    for cid in checkpoint.remaining_targets():
        if fail_chem_id and cid == fail_chem_id:
            raise KoshaMsdsSyncError("HYDRATION_INTERRUPTED", f"forced interrupt at {cid}")
        if sleep_s:
            sleep_fn(sleep_s)
        rec = hydrate_chem_id(client, by_id[cid])
        checkpoint.detail_calls += len(ALLOWED_SECTIONS)
        checkpoint.completed_chem_ids.append(cid)
        checkpoint.last_completed_chem_id = cid
        records.append(rec)
    return records


def chemical_detail_status(detail: FullDetail) -> str:
    if detail.detail_status == DETAIL_INCOMPLETE or detail.failed_sections:
        return DETAIL_INCOMPLETE
    statuses = [section.status for section in detail.sections.values()]
    if statuses and all(s == DETAIL_EMPTY_BUT_VALID for s in statuses):
        return DETAIL_EMPTY_BUT_VALID
    return DETAIL_COMPLETE


def incomplete_count(records: list[HydrationRecord]) -> int:
    return sum(1 for rec in records if chemical_detail_status(rec.detail) == DETAIL_INCOMPLETE)


def covered_detail_identities(records: list[HydrationRecord]) -> frozenset[str]:
    covered = set()
    for rec in records:
        if chemical_detail_status(rec.detail) in {DETAIL_COMPLETE, DETAIL_EMPTY_BUT_VALID}:
            covered.add(rec.chem_id)
    return frozenset(covered)


def detail_coverage_counts(
    census: ListCensus,
    records: list[HydrationRecord],
) -> tuple[int, int]:
    census_ids = set(census.chem_ids)
    covered = covered_detail_identities(records) & census_ids
    missing = census_ids - covered
    return len(covered), len(missing)


def publish_full_allowed(
    spec: SnapshotSpec,
    census: ListCensus,
    records: list[HydrationRecord],
    *,
    publish_state: str,
    incremental: bool = False,
) -> bool:
    """PUBLISHED_FULL only when every census chemId has COMPLETE/EMPTY_BUT_VALID detail.

    Incremental publish is fail-closed in this PR: no DB-backed prior coverage.
    """
    if incremental:
        return False
    census_ok = (
        len(census.chem_ids) == census.total_count
        and len(set(census.chem_ids)) == census.total_count
        and census.total_count > 0
    )
    covered_detail_count, missing_detail_count = detail_coverage_counts(census, records)
    promoted = SnapshotSpec(
        enumeration_mode=spec.enumeration_mode,
        status=spec.status if spec.status == "COMPLETED" else "COMPLETED",
        publish_state=publish_state,
        expected_count=census.total_count,
        run_type=spec.run_type,
    )
    return evaluate_publish_full(
        promoted,
        incomplete_count=incomplete_count(records),
        census_ok=census_ok,
        covered_detail_count=covered_detail_count,
        missing_detail_count=missing_detail_count,
        expected_count=census.total_count,
        incremental=False,
    )


def candidate_full_official_spec(census: ListCensus) -> SnapshotSpec:
    return new_full_official_spec(census.total_count, seed_source=census.seed_source or "")


def detail_calls_estimate(n: int) -> int:
    return n * len(ALLOWED_SECTIONS)
