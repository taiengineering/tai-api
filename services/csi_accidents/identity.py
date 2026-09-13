"""CSI identity: TAI content_id + fingerprint + version hash.

content_id is never a row hash, name+datetime, or case_no guess.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from services.csi_accidents.contract import (
    CONTENT_ID_PREFIX,
    DATASET_URL,
    FINGERPRINT_HEADERS,
    FINGERPRINT_VERSION,
    MISSING_SOURCE_VALUES,
    MISSING_TOKEN,
    NORM_ACCIDENT_MAJOR,
    NORM_ACCIDENT_TYPE,
    NORM_CAUSE_DETAIL,
    NORM_CAUSE_MAJOR,
    NORM_CAUSE_MID,
    NORM_CAUSE_MINOR,
    NORM_CONSTRUCTION,
    NORM_DEATH,
    NORM_INJURY,
    NORM_OBJECT_MAJOR,
    NORM_OBJECT_MINOR,
    NORM_OCCURRED,
    NORM_PROCESS_MAJOR,
    NORM_PROCESS_MINOR,
    NORM_SUMMARY,
    NORM_TITLE,
    NORM_WORK_PROCESS,
    OFFICIAL_HEADERS,
    SOURCE_ID,
)
from services.csi_accidents.parse import CsiSyncError, parse_int_or_none

KST = ZoneInfo("Asia/Seoul")
UuidFn = Callable[[], uuid.UUID]


def is_missing_source(value: str) -> bool:
    return value.strip() in MISSING_SOURCE_VALUES


def missing_to_null(value: str) -> Optional[str]:
    if is_missing_source(value):
        return None
    return value.strip()


def fingerprint_token(value: str) -> str:
    if is_missing_source(value):
        return MISSING_TOKEN
    return value.strip()


def _canonical_json(pairs: list[list[str]]) -> str:
    return json.dumps(pairs, ensure_ascii=False, separators=(",", ":"))


def source_content_hash(raw: dict[str, str]) -> str:
    pairs = [[h, raw.get(h, "")] for h in OFFICIAL_HEADERS]
    payload = _canonical_json(pairs)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def identity_fingerprint(raw: dict[str, str]) -> str:
    pairs = [[h, fingerprint_token(raw.get(h, ""))] for h in FINGERPRINT_HEADERS]
    digest = hashlib.sha256(_canonical_json(pairs).encode("utf-8")).hexdigest()
    return f"{FINGERPRINT_VERSION}:{digest}"


def new_content_id(uuid_fn: Optional[UuidFn] = None) -> str:
    fn = uuid_fn or uuid.uuid4
    return f"{CONTENT_ID_PREFIX}{fn()}"


def parse_occurred_at(raw: Optional[str]) -> Optional[str]:
    if raw is None or is_missing_source(raw):
        return None
    s = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=KST)
            return dt.isoformat()
        except ValueError:
            continue
    return None


@dataclass
class NormalizedAccident:
    row_number: int
    raw: dict[str, str]
    source_content_hash: str
    identity_fingerprint: str
    title: Optional[str]
    occurred_at: Optional[str]
    construction_type: Optional[str]
    process_major: Optional[str]
    process_minor: Optional[str]
    object_major: Optional[str]
    object_minor: Optional[str]
    work_process: Optional[str]
    accident_type_major: Optional[str]
    accident_type: Optional[str]
    cause_major: Optional[str]
    cause_mid: Optional[str]
    cause_minor: Optional[str]
    cause_detail: Optional[str]
    summary: Optional[str]
    death_count: Optional[int]
    injury_count: Optional[int]
    source_dataset_url: str = DATASET_URL
    source_item_url: Optional[str] = None
    source_id: str = SOURCE_ID
    source_key: Optional[str] = None


def normalize_row(raw: dict[str, str], row_number: int) -> NormalizedAccident:
    return NormalizedAccident(
        row_number=row_number,
        raw={h: raw.get(h, "") for h in OFFICIAL_HEADERS},
        source_content_hash=source_content_hash(raw),
        identity_fingerprint=identity_fingerprint(raw),
        title=missing_to_null(raw.get(NORM_TITLE, "")),
        occurred_at=parse_occurred_at(raw.get(NORM_OCCURRED, "")),
        construction_type=missing_to_null(raw.get(NORM_CONSTRUCTION, "")),
        process_major=missing_to_null(raw.get(NORM_PROCESS_MAJOR, "")),
        process_minor=missing_to_null(raw.get(NORM_PROCESS_MINOR, "")),
        object_major=missing_to_null(raw.get(NORM_OBJECT_MAJOR, "")),
        object_minor=missing_to_null(raw.get(NORM_OBJECT_MINOR, "")),
        work_process=missing_to_null(raw.get(NORM_WORK_PROCESS, "")),
        accident_type_major=missing_to_null(raw.get(NORM_ACCIDENT_MAJOR, "")),
        accident_type=missing_to_null(raw.get(NORM_ACCIDENT_TYPE, "")),
        cause_major=missing_to_null(raw.get(NORM_CAUSE_MAJOR, "")),
        cause_mid=missing_to_null(raw.get(NORM_CAUSE_MID, "")),
        cause_minor=missing_to_null(raw.get(NORM_CAUSE_MINOR, "")),
        cause_detail=missing_to_null(raw.get(NORM_CAUSE_DETAIL, "")),
        summary=missing_to_null(raw.get(NORM_SUMMARY, "")),
        death_count=parse_int_or_none(missing_to_null(raw.get(NORM_DEATH, ""))),
        injury_count=parse_int_or_none(missing_to_null(raw.get(NORM_INJURY, ""))),
    )


@dataclass
class CaseRecord:
    content_id: str
    identity_fingerprint: str
    identity_status: str
    source_content_hashes: set[str] = field(default_factory=set)


@dataclass
class ResolvedRow:
    row: NormalizedAccident
    content_id: str
    identity_status: str
    identity_reason: str
    match: str  # new | hash | fingerprint | hold_new


def _hash_index(cases: list[CaseRecord]) -> dict[str, set[str]]:
    idx: dict[str, set[str]] = defaultdict(set)
    for c in cases:
        for h in c.source_content_hashes:
            idx[h].add(c.content_id)
    return idx


def _fp_index(cases: list[CaseRecord]) -> dict[str, list[CaseRecord]]:
    idx: dict[str, list[CaseRecord]] = defaultdict(list)
    for c in cases:
        idx[c.identity_fingerprint].append(c)
    return idx


def resolve_identities(
    rows: list[NormalizedAccident],
    history: list[CaseRecord],
    *,
    uuid_fn: Optional[UuidFn] = None,
) -> tuple[list[ResolvedRow], dict]:
    """Match snapshot rows to TAI content_id. False merge is forbidden."""
    hash_idx = _hash_index(history)
    for digest, cids in hash_idx.items():
        if len(cids) > 1:
            raise CsiSyncError(
                "HASH_CASE_CONFLICT",
                f"source_content_hash maps to multiple cases: {digest}",
            )

    fp_idx = _fp_index(history)
    fp_counts = Counter(r.identity_fingerprint for r in rows)
    hold_fps: set[str] = set()
    for fp, n in fp_counts.items():
        if n > 1:
            hold_fps.add(fp)
    for fp, recs in fp_idx.items():
        if len({c.content_id for c in recs}) > 1:
            hold_fps.add(fp)

    seen_hash_to_cid: dict[str, str] = {}
    assigned: list[ResolvedRow] = []
    related_hold: set[str] = set()

    for row in rows:
        fp = row.identity_fingerprint
        digest = row.source_content_hash
        hist_cids = hash_idx.get(digest, set())
        if digest in seen_hash_to_cid:
            cid = seen_hash_to_cid[digest]
            match = "hash"
            reason = "EXACT_ROW_HASH"
        elif hist_cids:
            cid = next(iter(hist_cids))
            match = "hash"
            reason = "EXACT_ROW_HASH"
        elif fp in hold_fps:
            cid = new_content_id(uuid_fn)
            match = "hold_new"
            reason = (
                "SNAPSHOT_FINGERPRINT_COLLISION"
                if fp_counts[fp] > 1
                else "HISTORICAL_FINGERPRINT_AMBIGUOUS"
            )
            related_hold.update(c.content_id for c in fp_idx.get(fp, []))
            related_hold.add(cid)
        else:
            recs = fp_idx.get(fp, [])
            distinct = {c.content_id for c in recs}
            ready = [c for c in recs if c.identity_status == "READY"]
            ready_ids = {c.content_id for c in ready}
            if len(ready_ids) == 1 and len(distinct) == 1:
                cid = next(iter(ready_ids))
                match = "fingerprint"
                reason = "UNIQUE_HISTORICAL_FINGERPRINT"
            elif len(distinct) == 0:
                cid = new_content_id(uuid_fn)
                match = "new"
                reason = "UNIQUE_FINGERPRINT"
            elif len(distinct) == 1:
                cid = next(iter(distinct))
                match = "fingerprint"
                reason = "SINGLE_HISTORICAL_HOLD"
            else:
                raise CsiSyncError(
                    "FINGERPRINT_MERGE_FORBIDDEN",
                    f"refusing to auto-merge ambiguous fingerprint {fp}",
                )
        if fp in hold_fps:
            status = "HOLD"
            if reason == "EXACT_ROW_HASH":
                reason = "EXACT_ROW_HASH_IN_COLLISION"
            related_hold.add(cid)
            related_hold.update(c.content_id for c in fp_idx.get(fp, []))
        else:
            status = "READY"

        if digest in seen_hash_to_cid and seen_hash_to_cid[digest] != cid:
            raise CsiSyncError(
                "FINGERPRINT_MERGE_FORBIDDEN",
                "same hash resolved to different content_id",
            )
        seen_hash_to_cid[digest] = cid
        assigned.append(
            ResolvedRow(
                row=row,
                content_id=cid,
                identity_status=status,
                identity_reason=reason,
                match=match,
            )
        )

    collision_fps = sorted(fp for fp, n in fp_counts.items() if n > 1)
    hist_ambiguous = sorted(
        fp for fp, recs in fp_idx.items() if len({c.content_id for c in recs}) > 1
    )
    stats = {
        "collision_fingerprints": collision_fps,
        "historical_ambiguous_fingerprints": hist_ambiguous,
        "hold_content_ids": sorted(related_hold),
        "ready_rows": sum(1 for a in assigned if a.identity_status == "READY"),
        "hold_rows": sum(1 for a in assigned if a.identity_status == "HOLD"),
    }
    return assigned, stats
