"""Local secondary MSDS content audit. No production writer. No live OpenAPI."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Callable, Iterable, Optional

from services.kosha_msds.bootstrap import BootstrapSeedError, require_padded_chem_id
from services.kosha_msds.contract import (
    ALLOWED_SECTIONS,
    CONTENT_SECONDARY_COMPLETE,
    CONTENT_SECONDARY_EMPTY_VALID,
    CONTENT_SECONDARY_INVALID,
    CONTENT_SECONDARY_MISSING,
    CONTENT_SECONDARY_PARTIAL,
    DETAIL01_OBSERVED_DAILY_STOP,
    FRESHNESS_CURRENT_CHANGED,
    FRESHNESS_CURRENT_MATCH,
    FRESHNESS_DATE_UNKNOWN,
    REASON_OFFICIAL_ONLY,
    REASON_REVISION_CHANGED,
    REASON_REVISION_UNKNOWN,
    REASON_SECONDARY_COMPLETE_CANDIDATE,
    REASON_SECONDARY_EMPTY_VALID,
    REASON_SECONDARY_INVALID_SECTION,
    REASON_SECONDARY_MISSING_SECTION,
    SECONDARY_CONTENT_PRODUCTION_INGEST,
    SECTION_EMPTY,
    SECTION_INVALID,
    SECTION_MISSING,
    SECTION_PRESENT,
)
from services.kosha_msds.current_index import OfficialCurrentRow
from services.time import now_kst, serialize_external_utc

ProductionWriter = Callable[..., object]
CANONICAL_META_KEYS = frozenset({"written_at", "created_at", "timestamp", "executor_started_at"})
SOURCE_DATE_KEYS = ("lastDate", "last_date", "source_date")
SOURCE_REVISION_KEYS = ("revision", "lastDate", "last_date")
SECRET_MARKERS = ("servicekey=", "eyj", "authorization: bearer")


class ContentAuditError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def first_observed_text(raw: dict, keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def observe_record_fields(raw: dict) -> dict[str, object]:
    section_keys: list[str] = []
    sections = raw.get("sections")
    if isinstance(sections, list):
        for item in sections:
            if isinstance(item, dict):
                section_keys = sorted(item.keys())
                break
    return {
        "top_keys": sorted(raw.keys()),
        "section_keys": section_keys,
        "sections_is_list": isinstance(sections, list),
        "section_count_raw": len(sections) if isinstance(sections, list) else 0,
    }


def classify_section_payload(item: Optional[dict]) -> str:
    if item is None:
        return SECTION_MISSING
    if not isinstance(item, dict) or item.get("_invalid"):
        return SECTION_INVALID
    texts: list[str] = []
    for key in ("text_ko", "textKo", "braille"):
        value = item.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            return SECTION_INVALID
        if value.strip():
            texts.append(value.strip())
    return SECTION_PRESENT if texts else SECTION_EMPTY


def parse_section_map(raw_sections: object) -> dict[int, dict]:
    if raw_sections is None:
        return {}
    if not isinstance(raw_sections, list):
        raise ContentAuditError("SECTIONS_NOT_LIST", "sections is not a list")
    by_no: dict[int, dict] = {}
    for item in raw_sections:
        if not isinstance(item, dict):
            raise ContentAuditError("SECTION_NOT_OBJECT", "section is not an object")
        raw_no = item.get("section_no") if item.get("section_no") is not None else item.get("sectionNo")
        try:
            n = int(raw_no)
        except (TypeError, ValueError):
            raise ContentAuditError("SECTION_NO_INVALID", f"section_no={raw_no}") from None
        if n not in ALLOWED_SECTIONS:
            raise ContentAuditError("SECTION_NO_UNKNOWN", f"section_no={n}")
        if n in by_no:
            raise ContentAuditError("SECTION_DUPLICATE", f"duplicate section_no={n}")
        by_no[n] = item
    return by_no


def statuses_from_map(by_no: dict[int, dict]) -> dict[int, str]:
    return {n: classify_section_payload(by_no.get(n)) for n in ALLOWED_SECTIONS}


def content_status_from_sections(statuses: dict[int, str]) -> str:
    present = sum(1 for s in statuses.values() if s == SECTION_PRESENT)
    empty = sum(1 for s in statuses.values() if s == SECTION_EMPTY)
    missing = sum(1 for s in statuses.values() if s == SECTION_MISSING)
    invalid = sum(1 for s in statuses.values() if s == SECTION_INVALID)
    if invalid:
        return CONTENT_SECONDARY_INVALID
    if missing == 16:
        return CONTENT_SECONDARY_MISSING
    if missing == 0 and present == 0 and empty == 16:
        return CONTENT_SECONDARY_EMPTY_VALID
    if missing == 0:
        return CONTENT_SECONDARY_COMPLETE
    return CONTENT_SECONDARY_PARTIAL


def canonical_content_hash(chem_id: str, by_no: dict[int, dict], statuses: dict[int, str]) -> str:
    payload = {
        "chemId": chem_id,
        "sections": [
            {
                "section_no": n,
                "status": statuses[n],
                "text_ko": (
                    by_no[n].get("text_ko")
                    if n in by_no and isinstance(by_no[n].get("text_ko"), str)
                    else (by_no[n].get("textKo") if n in by_no and isinstance(by_no[n].get("textKo"), str) else None)
                ),
                "title": (by_no[n].get("title") if n in by_no else None),
            }
            for n in ALLOWED_SECTIONS
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_hash(payload: dict) -> str:
    cleaned = {key: value for key, value in payload.items() if key not in CANONICAL_META_KEYS}
    text = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def index_row_from_raw(raw: dict, *, source_revision: str) -> dict[str, object]:
    chem_id = require_padded_chem_id(raw.get("chem_id") or raw.get("chemId"))
    by_no = parse_section_map(raw.get("sections"))
    statuses = statuses_from_map(by_no)
    status = content_status_from_sections(statuses)
    row: dict[str, object] = {
        "chemId": chem_id,
        "secondary_present": True,
        "section_count": sum(1 for s in statuses.values() if s in {SECTION_PRESENT, SECTION_EMPTY}),
        "source_revision_if_present": first_observed_text(raw, SOURCE_REVISION_KEYS),
        "source_date_if_present": first_observed_text(raw, SOURCE_DATE_KEYS),
        "source_dataset_revision": source_revision,
        "content_hash": canonical_content_hash(chem_id, by_no, statuses),
        "content_status": status,
        "production_content": SECONDARY_CONTENT_PRODUCTION_INGEST,
    }
    for n in ALLOWED_SECTIONS:
        row[f"section{n:02d}_present"] = statuses[n]
    return row


def _write_checkpoint(path: Optional[Path], consumed: int, rows: int, invalid: int) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source_lines_consumed": consumed, "rows": rows, "invalid_chem_id": invalid}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_checkpoint(path: Optional[Path]) -> dict[str, int]:
    if path is None or not path.exists():
        return {"source_lines_consumed": 0, "rows": 0, "invalid_chem_id": 0}
    rec = json.loads(path.read_text(encoding="utf-8"))
    return {
        "source_lines_consumed": int(rec.get("source_lines_consumed") or 0),
        "rows": int(rec.get("rows") or 0),
        "invalid_chem_id": int(rec.get("invalid_chem_id") or 0),
    }


def stream_secondary_index(
    source_lines: Iterable[str],
    dest: Path,
    *,
    source_revision: str,
    max_rows: Optional[int] = None,
    resume_skip: int = 0,
    checkpoint_path: Optional[Path] = None,
    checkpoint_every: int = 500,
    production_writer: Optional[ProductionWriter] = None,
) -> dict[str, object]:
    del production_writer
    dest.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    prior_written = 0
    if resume_skip and dest.exists():
        with dest.open(encoding="utf-8") as existing:
            for line in existing:
                if line.strip():
                    seen.add(json.loads(line)["chemId"])
                    prior_written += 1
    written = 0
    invalid = 0
    consumed = 0
    observed: Optional[dict[str, object]] = None
    mode = "a" if resume_skip else "w"
    with dest.open(mode, encoding="utf-8") as out:
        for i, line in enumerate(source_lines, start=1):
            consumed = i
            if i <= resume_skip:
                continue
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if observed is None:
                observed = observe_record_fields(rec)
            try:
                row = index_row_from_raw(rec, source_revision=source_revision)
            except BootstrapSeedError:
                invalid += 1
                if max_rows is not None and (written + invalid) >= max_rows:
                    break
                continue
            cid = str(row["chemId"])
            if cid in seen:
                raise ContentAuditError("DUPLICATE_CHEM_ID", f"duplicate chemId={cid}")
            seen.add(cid)
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
            if checkpoint_path is not None and written % checkpoint_every == 0:
                out.flush()
                _write_checkpoint(checkpoint_path, consumed, prior_written + written, invalid)
            if max_rows is not None and (written + invalid) >= max_rows:
                break
    _write_checkpoint(checkpoint_path, consumed, prior_written + written, invalid)
    return {
        "rows": written,
        "rows_total": prior_written + written,
        "invalid_chem_id": invalid,
        "source_lines_consumed": consumed,
        "artifact_path": str(dest),
        "observed_schema": observed,
        "production_content": SECONDARY_CONTENT_PRODUCTION_INGEST,
    }


def stream_index_from_path(
    source: Path,
    dest: Path,
    *,
    source_revision: str,
    max_rows: Optional[int] = None,
    checkpoint_path: Optional[Path] = None,
    resume: bool = False,
    production_writer: Optional[ProductionWriter] = None,
) -> dict[str, object]:
    skip = read_checkpoint(checkpoint_path)["source_lines_consumed"] if resume else 0
    with source.open(encoding="utf-8") as fh:
        return stream_secondary_index(
            fh,
            dest,
            source_revision=source_revision,
            max_rows=max_rows,
            resume_skip=skip,
            checkpoint_path=checkpoint_path,
            production_writer=production_writer,
        )


def load_index_rows(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            cid = rec["chemId"]
            if cid in out:
                raise ContentAuditError("DUPLICATE_CHEM_ID", f"duplicate chemId={cid}")
            out[cid] = rec
    return out


def freshness(official_rev: Optional[str], secondary_rev: Optional[str]) -> str:
    if not official_rev or not secondary_rev:
        return FRESHNESS_DATE_UNKNOWN
    if official_rev == secondary_rev:
        return FRESHNESS_CURRENT_MATCH
    return FRESHNESS_CURRENT_CHANGED


def coverage_row(official: OfficialCurrentRow, secondary: Optional[dict]) -> dict[str, object]:
    if not official.chem_id:
        raise ContentAuditError("OFFICIAL_CHEM_ID_NULL", "official chemId is null")
    statuses = {n: SECTION_MISSING for n in ALLOWED_SECTIONS}
    if secondary:
        for n in ALLOWED_SECTIONS:
            statuses[n] = secondary.get(f"section{n:02d}_present") or SECTION_MISSING
        status = secondary.get("content_status") or CONTENT_SECONDARY_PARTIAL
        present = True
    else:
        status = CONTENT_SECONDARY_MISSING
        present = False
    counts = {SECTION_PRESENT: 0, SECTION_EMPTY: 0, SECTION_MISSING: 0, SECTION_INVALID: 0}
    for s in statuses.values():
        counts[s] = counts.get(s, 0) + 1
    secondary_date = (secondary or {}).get("source_date_if_present")
    fresh = freshness(official.official_revision_date, secondary_date if isinstance(secondary_date, str) else None)
    if status == CONTENT_SECONDARY_MISSING:
        needs_api, reason = True, REASON_OFFICIAL_ONLY
    elif status == CONTENT_SECONDARY_INVALID:
        needs_api, reason = True, REASON_SECONDARY_INVALID_SECTION
    elif status == CONTENT_SECONDARY_PARTIAL:
        needs_api, reason = True, REASON_SECONDARY_MISSING_SECTION
    elif status == CONTENT_SECONDARY_EMPTY_VALID:
        needs_api, reason = True, REASON_SECONDARY_EMPTY_VALID
    elif fresh == FRESHNESS_CURRENT_CHANGED:
        needs_api, reason = True, REASON_REVISION_CHANGED
    elif fresh == FRESHNESS_DATE_UNKNOWN:
        needs_api, reason = "unknown", REASON_REVISION_UNKNOWN
    else:
        needs_api, reason = False, REASON_SECONDARY_COMPLETE_CANDIDATE
    row: dict[str, object] = {
        "chemId": official.chem_id,
        "official_current": True,
        "secondary_present": present,
        "sections_present_count": counts[SECTION_PRESENT],
        "sections_empty_count": counts[SECTION_EMPTY],
        "sections_missing_count": counts[SECTION_MISSING],
        "sections_invalid_count": counts[SECTION_INVALID],
        "content_status": status,
        "freshness": fresh,
        "needs_api": needs_api,
        "reason": reason,
        "official_revision": official.official_revision_date,
        "secondary_revision": secondary_date,
        "production_content": SECONDARY_CONTENT_PRODUCTION_INGEST,
        "match_method": "CHEMID_EXACT",
    }
    for n in ALLOWED_SECTIONS:
        row[f"section{n:02d}_present"] = statuses[n]
    return row


def join_coverage(official_rows: list[OfficialCurrentRow], index: dict[str, dict]) -> list[dict]:
    return [coverage_row(official, index.get(official.chem_id) if official.chem_id else None) for official in official_rows]


def _q(chem_id, section_no, reason, row, sec_status, *, priority: int) -> dict:
    return {
        "chemId": chem_id,
        "sectionNo": section_no,
        "reason": reason,
        "priority": priority,
        "secondary_present": row["secondary_present"],
        "secondary_section_status": sec_status,
        "official_revision": row.get("official_revision"),
        "secondary_revision": row.get("secondary_revision"),
    }


def delta_queue_rows(coverage: Iterable[dict]) -> list[dict]:
    queue: list[dict] = []
    for row in coverage:
        status = row["content_status"]
        chem_id = row["chemId"]
        if status == CONTENT_SECONDARY_MISSING:
            for n in ALLOWED_SECTIONS:
                queue.append(_q(chem_id, n, REASON_OFFICIAL_ONLY, row, SECTION_MISSING, priority=1))
            continue
        if status == CONTENT_SECONDARY_EMPTY_VALID:
            for n in ALLOWED_SECTIONS:
                queue.append(_q(chem_id, n, REASON_SECONDARY_EMPTY_VALID, row, SECTION_EMPTY, priority=2))
            continue
        if row["reason"] == REASON_REVISION_CHANGED:
            for n in ALLOWED_SECTIONS:
                queue.append(
                    _q(chem_id, n, REASON_REVISION_CHANGED, row, row[f"section{n:02d}_present"], priority=3)
                )
            continue
        if row["reason"] == REASON_REVISION_UNKNOWN and status == CONTENT_SECONDARY_COMPLETE:
            continue
        if row["reason"] == REASON_SECONDARY_COMPLETE_CANDIDATE:
            continue
        for n in ALLOWED_SECTIONS:
            sec = row[f"section{n:02d}_present"]
            if sec == SECTION_MISSING:
                queue.append(_q(chem_id, n, REASON_SECONDARY_MISSING_SECTION, row, sec, priority=4))
            elif sec == SECTION_INVALID:
                queue.append(_q(chem_id, n, REASON_SECONDARY_INVALID_SECTION, row, sec, priority=2))
    queue.sort(key=lambda r: (r["priority"], r["chemId"], r["sectionNo"]))
    return queue


def endpoint_counts(queue: list[dict]) -> dict[int, int]:
    counts = {n: 0 for n in ALLOWED_SECTIONS}
    for row in queue:
        counts[int(row["sectionNo"])] += 1
    return counts


def coverage_metrics(coverage: list[dict], queue: list[dict]) -> dict[str, object]:
    official_n = len(coverage)
    strict = official_n * len(ALLOWED_SECTIONS)
    delta = len(queue)
    reduction = strict - delta
    pct = round((reduction / strict * 100.0), 2) if strict else 0.0
    delta_ep = endpoint_counts(queue)

    def n_status(code: str) -> int:
        return sum(1 for r in coverage if r["content_status"] == code)

    def n_fresh(code: str) -> int:
        return sum(1 for r in coverage if r["freshness"] == code)

    metrics: dict[str, object] = {
        "official_current": official_n,
        "official_in_secondary": sum(1 for r in coverage if r["secondary_present"]),
        CONTENT_SECONDARY_COMPLETE: n_status(CONTENT_SECONDARY_COMPLETE),
        CONTENT_SECONDARY_PARTIAL: n_status(CONTENT_SECONDARY_PARTIAL),
        CONTENT_SECONDARY_EMPTY_VALID: n_status(CONTENT_SECONDARY_EMPTY_VALID),
        CONTENT_SECONDARY_INVALID: n_status(CONTENT_SECONDARY_INVALID),
        CONTENT_SECONDARY_MISSING: n_status(CONTENT_SECONDARY_MISSING),
        "revision_match": n_fresh(FRESHNESS_CURRENT_MATCH),
        "revision_changed": n_fresh(FRESHNESS_CURRENT_CHANGED),
        "revision_unknown": n_fresh(FRESHNESS_DATE_UNKNOWN),
        "STRICT_API_CALLS": strict,
        "DELTA_API_CALLS": delta,
        "API_CALL_REDUCTION": reduction,
        "API_CALL_REDUCTION_PCT": pct,
        "live_bulk_api_calls": 0,
        "production_ingest": "NO",
        "production_content_publication": SECONDARY_CONTENT_PRODUCTION_INGEST,
        "FULL_DETAIL_HYDRATION": "NOT STARTED",
    }
    for n in ALLOWED_SECTIONS:
        metrics[f"DETAIL{n:02d}_strict"] = official_n
        metrics[f"DETAIL{n:02d}_delta"] = delta_ep[n]
    return metrics


def quota_scenarios(delta_calls: int, strict_calls: int, delta_by_endpoint: dict[int, int]) -> dict[str, object]:
    daily = DETAIL01_OBSERVED_DAILY_STOP
    return {
        "observed_detail01_daily_stop": daily,
        "quota_status": "OBSERVED_NOT_PER_ENDPOINT_FACT",
        "if_1000_per_day_global": {
            "strict_days": math.ceil(strict_calls / daily) if daily else None,
            "delta_days": math.ceil(delta_calls / daily) if daily and delta_calls else 0,
        },
        "if_1000_per_day_per_endpoint": {
            "strict_days": math.ceil((strict_calls / len(ALLOWED_SECTIONS)) / daily) if daily else None,
            "delta_days": max((math.ceil(n / daily) for n in delta_by_endpoint.values()), default=0),
        },
        "note": "Detail01 HTTP 429 after ~1000/day was observed once. Not a per-endpoint fact.",
    }


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    n = 0
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    tmp.replace(path)
    return n


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body.setdefault("written_at", serialize_external_utc(now_kst()))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def assert_secret_free(text: str) -> None:
    lowered = text.lower()
    for token in SECRET_MARKERS:
        if token in lowered:
            raise ContentAuditError("SECRET_LEAK", token)


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n
