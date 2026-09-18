"""OBJ-CHEM-05 authoritative KOSHA MSDS materialize adapter (pure logic).

Reads hydration runner artifacts (responses.jsonl) plus optional census,
produces a canonical materialize plan whose targets are the EXISTING
public.kosha_msds_* tables. No DB I/O in this module. No new schema. No
new engine. No new hash algorithm - hashes reuse
`services.kosha_msds.hash`.

Provenance the runner artifact carries but the DB catalog does not have
as columns is folded into the snapshot's metrics_json rather than added
as new columns (WO §4):

    official_spec_version   ->   snapshot.metrics_json.official_spec_version
    official_spec_date      ->   snapshot.metrics_json.official_spec_date
    authoritative_verified  ->   admission gate (records failing it are rejected)
    ingest_batch_id         ->   snapshot.id (per-run natural key)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from services.kosha_msds.contract import (
    ALLOWED_SECTIONS,
    DATASET_URL,
    DETAIL_COMPLETE,
    DETAIL_EMPTY_BUT_VALID,
    DETAIL_INCOMPLETE,
    ENUMERATION_FULL_OFFICIAL,
    IDENTITY_HOLD,
    IDENTITY_READY,
    OFFICIAL_SPEC_DATE,
    OFFICIAL_SPEC_VERSION,
    PUBLISH_NOT_PUBLISHED,
    PUBLISH_PUBLISHED_FULL,
    SNAPSHOT_RUNNING,
    SOURCE_CONTRACT_VERSION,
    SOURCE_ID,
)
from services.kosha_msds.hash import section_hash, source_content_hash
from services.kosha_msds.identity import identity_status_for_chem_id
from services.kosha_msds.parse import canonical_section_items, normalize_optional

# ---------------------------------------------------------------------------
# Frozen expectations for the KOSHA official corpus.
# Aligned with tools/chem04/official_hydrate_v12.py:53 (EXPECTED_QUEUE_ROWS).
# ---------------------------------------------------------------------------
FULL_OFFICIAL_CHEMICAL_COUNT = 20568
FULL_OFFICIAL_SECTION_COUNT = 329088

# ---------------------------------------------------------------------------
# Source contract admission gate (WO §6).
# Records failing any of these are rejected. This is deliberately strict:
# the runner already ONLY writes response records when HTTP 200 + rc 00 +
# parse OK, so any failure here is either artifact tampering or a bug.
# ---------------------------------------------------------------------------
REQUIRED_SOURCE = "KOSHA_OFFICIAL"
REQUIRED_SOURCE_CONTRACT_VERSION = SOURCE_CONTRACT_VERSION
REQUIRED_OFFICIAL_SPEC_VERSION = OFFICIAL_SPEC_VERSION
REQUIRED_OFFICIAL_SPEC_DATE = OFFICIAL_SPEC_DATE
REQUIRED_AUTHORITATIVE_VERIFIED = True
REQUIRED_RESULT_CODE = "00"

# ---------------------------------------------------------------------------
# Execute-eligibility block reason vocabulary (WO §15).
# ---------------------------------------------------------------------------
BLOCK_FULL_OFFICIAL_CORPUS_INCOMPLETE = "FULL_OFFICIAL_CORPUS_INCOMPLETE"
BLOCK_SOURCE_CONTRACT_FAIL = "SOURCE_CONTRACT_FAIL"
BLOCK_DUPLICATE_PAIRS = "DUPLICATE_PAIRS"
BLOCK_MISSING_SECTIONS = "MISSING_SECTIONS"
BLOCK_INCOMPLETE_CHEMICALS = "INCOMPLETE_CHEMICALS"

ADAPTER_VERSION = "CHEM05_V1"


@dataclass(frozen=True)
class ContractFailure:
    chem_id: Optional[str]
    section_no: Optional[int]
    code: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "chem_id": self.chem_id,
            "section_no": self.section_no,
            "code": self.code,
            "detail": self.detail,
        }


def check_source_contract(record: Mapping[str, Any]) -> Optional[ContractFailure]:
    """Return None if the record passes admission; ContractFailure otherwise.

    The runner's own contract (see tools/chem04/official_hydrate_v12.py
    lines 375-389) writes each of these fields on every success record.
    Anything else in the artifact is rejected.
    """
    chem_id = record.get("chemId")
    section_no_raw = record.get("sectionNo")
    try:
        section_no = int(section_no_raw) if section_no_raw is not None else None
    except (TypeError, ValueError):
        section_no = None

    if not isinstance(chem_id, str) or not chem_id:
        return ContractFailure(
            chem_id=None,
            section_no=section_no,
            code="MISSING_CHEM_ID",
            detail="chemId absent or non-string",
        )
    if section_no is None or section_no not in ALLOWED_SECTIONS:
        return ContractFailure(
            chem_id=chem_id,
            section_no=section_no,
            code="SECTION_OUT_OF_RANGE",
            detail=f"sectionNo={section_no_raw!r} not in 1..16",
        )
    if record.get("source") != REQUIRED_SOURCE:
        return ContractFailure(
            chem_id, section_no, "SOURCE_MISMATCH",
            f"source={record.get('source')!r}",
        )
    if record.get("source_contract_version") != REQUIRED_SOURCE_CONTRACT_VERSION:
        return ContractFailure(
            chem_id, section_no, "SOURCE_CONTRACT_VERSION_MISMATCH",
            f"got={record.get('source_contract_version')!r}",
        )
    if record.get("official_spec_version") != REQUIRED_OFFICIAL_SPEC_VERSION:
        return ContractFailure(
            chem_id, section_no, "OFFICIAL_SPEC_VERSION_MISMATCH",
            f"got={record.get('official_spec_version')!r}",
        )
    if record.get("official_spec_date") != REQUIRED_OFFICIAL_SPEC_DATE:
        return ContractFailure(
            chem_id, section_no, "OFFICIAL_SPEC_DATE_MISMATCH",
            f"got={record.get('official_spec_date')!r}",
        )
    if record.get("authoritative_verified") is not REQUIRED_AUTHORITATIVE_VERIFIED:
        return ContractFailure(
            chem_id, section_no, "AUTHORITATIVE_VERIFIED_MISMATCH",
            f"got={record.get('authoritative_verified')!r}",
        )
    if record.get("result_code") != REQUIRED_RESULT_CODE:
        return ContractFailure(
            chem_id, section_no, "RESULT_CODE_MISMATCH",
            f"got={record.get('result_code')!r}",
        )
    return None


@dataclass(frozen=True)
class SectionRow:
    """Projection for public.kosha_msds_sections.

    Fields not in the DB (item_count, result_message) are convenience
    fields for the plan; only section_no / payload_json / section_hash /
    result_code / result_message / fetched_at map to columns.
    """
    section_no: int
    payload_json: list           # canonical items array (list of dicts)
    section_hash: str
    result_code: str
    result_message: Optional[str]
    fetched_at: str
    item_count: int

    def to_dict(self) -> dict:
        return {
            "section_no": self.section_no,
            "section_hash": self.section_hash,
            "result_code": self.result_code,
            "result_message": self.result_message,
            "fetched_at": self.fetched_at,
            "item_count": self.item_count,
            "payload_json": self.payload_json,
        }


@dataclass(frozen=True)
class ChemicalBundle:
    """All rows the plan will insert for one chemId.

    Maps to one row in kosha_msds_chemicals + up to 16 rows in
    kosha_msds_sections + one snapshot_items membership row.
    """
    chem_id: str
    source_id: str
    source_key: str
    identity_status: str
    identity_reason: Optional[str]
    chemical_name_ko: Optional[str]
    chemical_name_en: Optional[str]
    cas_no: Optional[str]
    ke_no: Optional[str]
    en_no: Optional[str]
    un_no: Optional[str]
    last_date: Optional[str]
    source_content_hash: str
    source_dataset_url: str
    detail_status: str
    sections: tuple  # tuple[SectionRow, ...]

    def to_dict(self) -> dict:
        return {
            "chem_id": self.chem_id,
            "source_id": self.source_id,
            "source_key": self.source_key,
            "identity_status": self.identity_status,
            "identity_reason": self.identity_reason,
            "chemical_name_ko": self.chemical_name_ko,
            "chemical_name_en": self.chemical_name_en,
            "cas_no": self.cas_no,
            "ke_no": self.ke_no,
            "en_no": self.en_no,
            "un_no": self.un_no,
            "last_date": self.last_date,
            "source_content_hash": self.source_content_hash,
            "source_dataset_url": self.source_dataset_url,
            "detail_status": self.detail_status,
            "sections": [s.to_dict() for s in self.sections],
        }


@dataclass
class SnapshotCandidate:
    run_type: str
    enumeration_mode: str
    status: str
    publish_state: str
    source_contract_version: str
    expected_count: int
    discovered_count: int
    metrics_json: dict

    def to_dict(self) -> dict:
        return {
            "run_type": self.run_type,
            "enumeration_mode": self.enumeration_mode,
            "status": self.status,
            "publish_state": self.publish_state,
            "source_contract_version": self.source_contract_version,
            "expected_count": self.expected_count,
            "discovered_count": self.discovered_count,
            "metrics_json": dict(self.metrics_json),
        }


@dataclass
class MaterializePlan:
    chemicals: tuple  # tuple[ChemicalBundle, ...]
    snapshot: SnapshotCandidate
    contract_failures: tuple  # tuple[ContractFailure, ...]
    duplicate_pairs: tuple    # tuple[tuple[str, int], ...]
    plan_sha256: str
    execute_eligible: bool
    execute_block_reasons: tuple
    counts: dict

    def to_report(self) -> dict:
        return {
            "counts": dict(self.counts),
            "plan_sha256": self.plan_sha256,
            "execute_eligible": self.execute_eligible,
            "execute_block_reasons": list(self.execute_block_reasons),
            "snapshot": self.snapshot.to_dict(),
            "contract_failures_head": [
                f.to_dict() for f in self.contract_failures[:10]
            ],
            "duplicate_pairs_head": [
                {"chem_id": cp[0], "section_no": cp[1]}
                for cp in self.duplicate_pairs[:10]
            ],
        }


def _semantic_plan_json(chemicals: Iterable[ChemicalBundle]) -> str:
    """Deterministic JSON of the plan's semantic content.

    Excludes fetched_at, result_message, item_count, payload_json (full
    content is already covered by section_hash). This is what
    plan_sha256 hashes.
    """
    rows = []
    for c in sorted(chemicals, key=lambda x: x.chem_id):
        rows.append({
            "chem_id": c.chem_id,
            "source_content_hash": c.source_content_hash,
            "identity_status": c.identity_status,
            "detail_status": c.detail_status,
            "sections": [
                {"section_no": s.section_no, "section_hash": s.section_hash,
                 "result_code": s.result_code, "item_count": s.item_count}
                for s in sorted(c.sections, key=lambda s: s.section_no)
            ],
        })
    return json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_plan(
    *,
    artifact_records: Iterable[Mapping[str, Any]],
    census: Optional[Mapping[str, Mapping[str, Any]]] = None,
    artifact_responses_sha256: Optional[str] = None,
    adapter_version: str = ADAPTER_VERSION,
) -> MaterializePlan:
    """Build a materialize plan from hydration artifact records.

    artifact_records:
        Iterable of dicts as written by
        tools/chem04/official_hydrate_v12.py to responses.jsonl.
    census:
        Optional mapping keyed by chem_id -> dict with additional
        identity fields (chemical_name_ko, chemical_name_en, cas_no,
        ke_no, en_no, un_no, last_date). If absent, the chemical row's
        attributes are left null. Never fetches live data.
    artifact_responses_sha256:
        SHA256 of the responses.jsonl file the plan was built from.
        Recorded in snapshot.metrics_json for provenance; not used by
        the adapter otherwise.
    """
    if census is None:
        census = {}

    seen_pairs: dict[tuple[str, int], Mapping[str, Any]] = {}
    duplicates: list[tuple[str, int]] = []
    failures: list[ContractFailure] = []
    sections_by_chem: dict[str, dict[int, Mapping[str, Any]]] = {}
    total_records = 0

    for record in artifact_records:
        total_records += 1
        failure = check_source_contract(record)
        if failure is not None:
            failures.append(failure)
            continue
        chem_id = record["chemId"]
        section_no = int(record["sectionNo"])
        key = (chem_id, section_no)
        if key in seen_pairs:
            duplicates.append(key)
            continue
        seen_pairs[key] = record
        sections_by_chem.setdefault(chem_id, {})[section_no] = record

    chemicals: list[ChemicalBundle] = []
    for chem_id in sorted(sections_by_chem.keys()):
        section_map = sections_by_chem[chem_id]
        section_rows: list[SectionRow] = []

        for n in sorted(section_map.keys()):
            rec = section_map[n]
            raw_items = list(rec.get("items") or [])
            canonical = canonical_section_items(raw_items)
            section_rows.append(SectionRow(
                section_no=n,
                payload_json=canonical,
                section_hash=section_hash(raw_items),
                result_code=str(rec.get("result_code")),
                result_message=normalize_optional(rec.get("result_msg")),
                fetched_at=str(rec.get("fetched_at") or ""),
                item_count=len(canonical),
            ))

        census_row = dict(census.get(chem_id) or {})
        # source_content_hash: give the runtime helper the same shape it
        # was designed for (chem_id + list_item + sections dict keyed
        # "01".."16").
        list_item = {
            "chemId": chem_id,
            "chemNameKor": census_row.get("chemical_name_ko"),
            "casNo": census_row.get("cas_no"),
            "keNo": census_row.get("ke_no"),
            "enNo": census_row.get("en_no"),
            "unNo": census_row.get("un_no"),
            "lastDate": census_row.get("last_date"),
            "openYn": census_row.get("open_yn"),
            "koshaConfirm": census_row.get("kosha_confirm"),
        }
        sections_for_hash = {
            f"{n:02d}": list((section_map.get(n) or {}).get("items") or [])
            for n in ALLOWED_SECTIONS
        }
        content_hash = source_content_hash(chem_id, list_item, sections_for_hash)

        present = set(section_map.keys())
        missing = set(ALLOWED_SECTIONS) - present
        if missing:
            detail_status = DETAIL_INCOMPLETE
        else:
            any_content = any(
                len(section_map[n].get("items") or []) > 0 for n in ALLOWED_SECTIONS
            )
            detail_status = DETAIL_COMPLETE if any_content else DETAIL_EMPTY_BUT_VALID

        identity_status = identity_status_for_chem_id(chem_id)
        chemicals.append(ChemicalBundle(
            chem_id=chem_id,
            source_id=SOURCE_ID,
            source_key=chem_id,
            identity_status=identity_status,
            identity_reason=None if identity_status == IDENTITY_READY else "missing chemId",
            chemical_name_ko=normalize_optional(census_row.get("chemical_name_ko")),
            chemical_name_en=normalize_optional(census_row.get("chemical_name_en")),
            cas_no=normalize_optional(census_row.get("cas_no")),
            ke_no=normalize_optional(census_row.get("ke_no")),
            en_no=normalize_optional(census_row.get("en_no")),
            un_no=normalize_optional(census_row.get("un_no")),
            last_date=normalize_optional(census_row.get("last_date")),
            source_content_hash=content_hash,
            source_dataset_url=DATASET_URL,
            detail_status=detail_status,
            sections=tuple(section_rows),
        ))

    plan_sha = hashlib.sha256(
        _semantic_plan_json(chemicals).encode("utf-8")
    ).hexdigest()

    unique_pairs = len(seen_pairs)
    unique_chemids = len(sections_by_chem)
    complete = sum(1 for c in chemicals if c.detail_status == DETAIL_COMPLETE)
    incomplete = sum(1 for c in chemicals if c.detail_status == DETAIL_INCOMPLETE)
    empty_but_valid = sum(1 for c in chemicals if c.detail_status == DETAIL_EMPTY_BUT_VALID)
    missing_sections = FULL_OFFICIAL_SECTION_COUNT - unique_pairs
    if missing_sections < 0:
        missing_sections = 0  # more sections than expected -> caught by corpus-incomplete

    reasons: list[str] = []
    if failures:
        reasons.append(BLOCK_SOURCE_CONTRACT_FAIL)
    if duplicates:
        reasons.append(BLOCK_DUPLICATE_PAIRS)
    if incomplete > 0:
        reasons.append(BLOCK_INCOMPLETE_CHEMICALS)
    if (unique_chemids != FULL_OFFICIAL_CHEMICAL_COUNT
            or unique_pairs != FULL_OFFICIAL_SECTION_COUNT):
        reasons.append(BLOCK_FULL_OFFICIAL_CORPUS_INCOMPLETE)
    if missing_sections > 0 and BLOCK_FULL_OFFICIAL_CORPUS_INCOMPLETE not in reasons:
        reasons.append(BLOCK_MISSING_SECTIONS)

    execute_eligible = len(reasons) == 0

    snapshot = SnapshotCandidate(
        run_type="FULL_SYNC",
        enumeration_mode=ENUMERATION_FULL_OFFICIAL,
        status=SNAPSHOT_RUNNING,
        publish_state=PUBLISH_NOT_PUBLISHED,
        source_contract_version=SOURCE_CONTRACT_VERSION,
        expected_count=FULL_OFFICIAL_CHEMICAL_COUNT,
        discovered_count=unique_chemids,
        metrics_json={
            "official_spec_version": REQUIRED_OFFICIAL_SPEC_VERSION,
            "official_spec_date": REQUIRED_OFFICIAL_SPEC_DATE,
            "source": REQUIRED_SOURCE,
            "queue_expected_sections": FULL_OFFICIAL_SECTION_COUNT,
            "chemical_expected_count": FULL_OFFICIAL_CHEMICAL_COUNT,
            "artifact_responses_sha256": artifact_responses_sha256,
            "materialize_plan_sha256": plan_sha,
            "adapter_version": adapter_version,
        },
    )

    counts = {
        "artifact_records": total_records,
        "unique_pairs": unique_pairs,
        "unique_chemids": unique_chemids,
        "complete_chemicals": complete,
        "incomplete_chemicals": incomplete,
        "empty_but_valid_chemicals": empty_but_valid,
        "duplicate_pairs": len(duplicates),
        "source_contract_failures": len(failures),
        "missing_sections": missing_sections,
        "expected_chemical_count": FULL_OFFICIAL_CHEMICAL_COUNT,
        "expected_section_count": FULL_OFFICIAL_SECTION_COUNT,
    }

    return MaterializePlan(
        chemicals=tuple(chemicals),
        snapshot=snapshot,
        contract_failures=tuple(failures),
        duplicate_pairs=tuple(duplicates),
        plan_sha256=plan_sha,
        execute_eligible=execute_eligible,
        execute_block_reasons=tuple(reasons),
        counts=counts,
    )


def block_execute_if_not_eligible(plan: MaterializePlan) -> None:
    """Raise if the plan is not execute-eligible. Called before any DB write.

    A --execute invocation must call this before opening any DB
    connection. If eligibility drifts back to False after re-planning,
    we abort without touching the DB.
    """
    if plan.execute_eligible:
        return
    reasons = ", ".join(plan.execute_block_reasons) or "UNKNOWN"
    raise ExecuteBlocked(reasons, plan)


class ExecuteBlocked(Exception):
    def __init__(self, reasons: str, plan: MaterializePlan):
        super().__init__(f"execute blocked: {reasons}")
        self.reasons = reasons
        self.plan = plan


def assert_no_publish_full(snapshot: SnapshotCandidate) -> None:
    """Fail-closed guard. This adapter never emits PUBLISHED_FULL (WO §31)."""
    if snapshot.publish_state == PUBLISH_PUBLISHED_FULL:
        raise ValueError(
            "publish_state=PUBLISHED_FULL is a separate future WO; the adapter "
            "never emits PUBLISHED_FULL from a dry-run plan."
        )
