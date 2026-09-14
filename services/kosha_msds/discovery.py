"""CHEM-04 PATCH-3: empirical getChemDetail01 chemId discovery.

This is DETAIL01_ID_DISCOVERY / EMPIRICAL_API_CENSUS.
It is not a documented enumeration API and must not be called FULL_OFFICIAL.

ERROR is never coerced to ABSENT. Production writers are never invoked.
Detail02~16 hydration is out of scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from services.kosha_msds.client import Detail01Raw, KoshaMsdsClient, redact_secret
from services.kosha_msds.contract import (
    DISCOVERY_ABSENT,
    DISCOVERY_DISCOVERED,
    DISCOVERY_METHOD,
    DISCOVERY_RANGE_END,
    DISCOVERY_RANGE_START,
    DISCOVERY_STAGES,
    DISCOVERY_TAIL_BLOCK,
    DISCOVERY_UNKNOWN,
    DISCOVERY_WORKERS_MAX,
    DISCOVERY_WORKERS_START,
    EMPIRICAL_API_CENSUS,
    INITIAL_SEED_CANDIDATE_BLOCKED,
    INITIAL_SEED_CANDIDATE_CONDITIONAL,
    INITIAL_SEED_CANDIDATE_PASS,
    QUOTA_MESSAGE_MARKERS,
    RATE_LIMIT_DAILY_CODES,
    RATE_LIMIT_SECOND_CODES,
    SUCCESS_RESULT_CODES,
)
from services.kosha_msds.identity import format_numeric_chem_id
from services.kosha_msds.parse import KoshaMsdsParseError, parse_section_xml

TAIL_EXTEND = "EXTEND_NEXT_BLOCK"
TAIL_UPPER_BOUND_PASS = "UPPER_BOUND_CANDIDATE_PASS"
DEFAULT_ARTIFACT_DIR = Path("artifacts/chem04")

ProductionWriter = Callable[..., object]


class KoshaMsdsDiscoveryError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clamp_workers(n: int) -> int:
    if type(n) is not int or n < 1:
        return DISCOVERY_WORKERS_START
    return min(n, DISCOVERY_WORKERS_MAX)


def is_quota_or_rate(
    *,
    http_status: Optional[int],
    result_code: Optional[str],
    result_msg: Optional[str],
    error_text: Optional[str],
) -> bool:
    if http_status == 429:
        return True
    if result_code in RATE_LIMIT_DAILY_CODES | RATE_LIMIT_SECOND_CODES:
        return True
    blob = " ".join(part for part in (result_msg, error_text) if part).lower()
    return any(marker in blob for marker in QUOTA_MESSAGE_MARKERS)


def classify_detail01(raw: Detail01Raw, *, secret: str = "") -> "ProbeRecord":
    cid = raw.chem_id
    probed_at = utc_now()
    msg = redact_secret(raw.error_text or "", secret)
    if raw.error_code or raw.body is None or raw.http_status != 200:
        http_status = raw.http_status
        quota = is_quota_or_rate(
            http_status=http_status,
            result_code=None,
            result_msg=None,
            error_text=raw.error_text,
        )
        return ProbeRecord(
            chem_id=cid,
            status=DISCOVERY_UNKNOWN,
            http_status=http_status,
            result_code=None,
            result_msg=msg,
            error_code=raw.error_code or "TRANSPORT",
            quota_or_rate=quota,
            probed_at=probed_at,
            elapsed_ms=raw.elapsed_ms,
        )
    try:
        parsed = parse_section_xml(raw.body, require_success=False)
    except KoshaMsdsParseError as exc:
        return ProbeRecord(
            chem_id=cid,
            status=DISCOVERY_UNKNOWN,
            http_status=raw.http_status,
            result_code=None,
            result_msg=redact_secret(exc.message, secret),
            error_code=exc.code,
            quota_or_rate=False,
            probed_at=probed_at,
            elapsed_ms=raw.elapsed_ms,
        )
    quota = is_quota_or_rate(
        http_status=raw.http_status,
        result_code=parsed.result_code,
        result_msg=parsed.result_msg,
        error_text=None,
    )
    if quota or parsed.result_code not in SUCCESS_RESULT_CODES:
        return ProbeRecord(
            chem_id=cid,
            status=DISCOVERY_UNKNOWN,
            http_status=raw.http_status,
            result_code=parsed.result_code,
            result_msg=redact_secret(parsed.result_msg, secret),
            error_code="RESULT_CODE" if not quota else "RATE_LIMIT",
            quota_or_rate=quota,
            probed_at=probed_at,
            elapsed_ms=raw.elapsed_ms,
        )
    status = DISCOVERY_ABSENT if parsed.empty_but_valid else DISCOVERY_DISCOVERED
    return ProbeRecord(
        chem_id=cid,
        status=status,
        http_status=raw.http_status,
        result_code=parsed.result_code,
        result_msg=redact_secret(parsed.result_msg, secret),
        error_code=None,
        quota_or_rate=False,
        probed_at=probed_at,
        elapsed_ms=raw.elapsed_ms,
    )


@dataclass(frozen=True)
class ProbeRecord:
    chem_id: str
    status: str
    http_status: Optional[int]
    result_code: Optional[str]
    result_msg: Optional[str]
    error_code: Optional[str]
    quota_or_rate: bool
    probed_at: str
    elapsed_ms: float = 0.0

    def as_artifact_row(self) -> dict[str, object]:
        return {
            "chemId": self.chem_id,
            "status": self.status,
            "http_status": self.http_status,
            "result_code": self.result_code,
            "result_msg": self.result_msg,
            "error_code": self.error_code,
            "quota_or_rate": self.quota_or_rate,
            "probed_at": self.probed_at,
        }


def range_complete(*, candidate_count: int, discovered: int, absent: int, unknown: int) -> bool:
    return unknown == 0 and discovered + absent == candidate_count


def evaluate_tail_block(*, discovered_count: int, block_size: int = DISCOVERY_TAIL_BLOCK) -> str:
    if block_size != DISCOVERY_TAIL_BLOCK:
        raise KoshaMsdsDiscoveryError("TAIL_BLOCK_INVALID", "tail block must be 10000")
    if discovered_count > 0:
        return TAIL_EXTEND
    return TAIL_UPPER_BOUND_PASS


def initial_seed_candidate_status(
    *,
    range_complete_ok: bool,
    unknown: int,
    trailing_zero: bool,
    checkpoint_ok: bool,
    artifact_hash: Optional[str],
    quota_stop: bool,
) -> str:
    if quota_stop and not (range_complete_ok and trailing_zero and unknown == 0):
        return INITIAL_SEED_CANDIDATE_BLOCKED
    if range_complete_ok and unknown == 0 and trailing_zero and checkpoint_ok and artifact_hash:
        return INITIAL_SEED_CANDIDATE_PASS
    if range_complete_ok and unknown == 0 and checkpoint_ok and artifact_hash and not trailing_zero:
        return INITIAL_SEED_CANDIDATE_CONDITIONAL
    return INITIAL_SEED_CANDIDATE_BLOCKED


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_latest_rows(path: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    if not path.exists():
        return latest
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            cid = row.get("chemId")
            if cid:
                latest[str(cid)] = row
    return latest


def pending_numeric_ids(start: int, end: int, latest: dict[str, dict]) -> list[int]:
    pending: list[int] = []
    for n in range(start, end + 1):
        cid = format_numeric_chem_id(n)
        status = (latest.get(cid) or {}).get("status")
        if status in {DISCOVERY_DISCOVERED, DISCOVERY_ABSENT}:
            continue
        pending.append(n)
    return pending


def prefix_watermark(start: int, end: int, latest: dict[str, dict]) -> Optional[str]:
    last: Optional[str] = None
    for n in range(start, end + 1):
        cid = format_numeric_chem_id(n)
        status = (latest.get(cid) or {}).get("status")
        if status not in {DISCOVERY_DISCOVERED, DISCOVERY_ABSENT}:
            break
        last = cid
    return last


def count_status(latest: dict[str, dict], start: int, end: int) -> tuple[int, int, int]:
    discovered = absent = unknown = 0
    for n in range(start, end + 1):
        status = (latest.get(format_numeric_chem_id(n)) or {}).get("status")
        if status == DISCOVERY_DISCOVERED:
            discovered += 1
        elif status == DISCOVERY_ABSENT:
            absent += 1
        elif status == DISCOVERY_UNKNOWN:
            unknown += 1
    return discovered, absent, unknown


def discovered_ids_in_range(latest: dict[str, dict], start: int, end: int) -> list[str]:
    out: list[str] = []
    for n in range(start, end + 1):
        cid = format_numeric_chem_id(n)
        if (latest.get(cid) or {}).get("status") == DISCOVERY_DISCOVERED:
            out.append(cid)
    return out


def highest_1000_block_hit_count(latest: dict[str, dict], start: int, end: int) -> int:
    best = 0
    block_start = start
    while block_start <= end:
        block_end = min(block_start + 999, end)
        hits = 0
        for n in range(block_start, block_end + 1):
            if (latest.get(format_numeric_chem_id(n)) or {}).get("status") == DISCOVERY_DISCOVERED:
                hits += 1
        if hits > best:
            best = hits
        block_start += 1000
    return best


@dataclass
class DiscoveryCheckpoint:
    last_scanned_id: Optional[str] = None
    discovered_count: int = 0
    absent_count: int = 0
    unknown_ids: list[str] = field(default_factory=list)
    started_at: str = ""
    updated_at: str = ""
    range_start: int = DISCOVERY_RANGE_START
    range_end: int = DISCOVERY_RANGE_END
    quota_stop: bool = False
    calls_attempted: int = 0
    http_429: int = 0
    result_code_22: int = 0
    other_api_errors: int = 0
    workers: int = DISCOVERY_WORKERS_START
    discovery_method: str = DISCOVERY_METHOD
    census_status: str = EMPIRICAL_API_CENSUS
    artifact_path: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "last_scanned_id": self.last_scanned_id,
            "discovered_count": self.discovered_count,
            "absent_count": self.absent_count,
            "unknown_ids": list(self.unknown_ids),
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "range_start": self.range_start,
            "range_end": self.range_end,
            "quota_stop": self.quota_stop,
            "calls_attempted": self.calls_attempted,
            "http_429": self.http_429,
            "result_code_22": self.result_code_22,
            "other_api_errors": self.other_api_errors,
            "workers": self.workers,
            "discovery_method": self.discovery_method,
            "census_status": self.census_status,
            "artifact_path": self.artifact_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiscoveryCheckpoint":
        known = {k: data[k] for k in cls().to_dict() if k in data}
        return cls(**known)


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


class DiscoveryStore:
    def __init__(self, artifact_path: Path, checkpoint_path: Path, *, secret: str = ""):
        self.artifact_path = artifact_path
        self.checkpoint_path = checkpoint_path
        self.secret = secret
        self.lock = threading.Lock()
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        self.latest = load_latest_rows(artifact_path)
        if checkpoint_path.exists():
            self.checkpoint = DiscoveryCheckpoint.from_dict(
                json.loads(checkpoint_path.read_text(encoding="utf-8"))
            )
        else:
            self.checkpoint = DiscoveryCheckpoint(
                started_at=utc_now(),
                updated_at=utc_now(),
                artifact_path=str(artifact_path),
            )
        if not self.checkpoint.started_at:
            self.checkpoint.started_at = utc_now()
        self.checkpoint.artifact_path = str(artifact_path)
        self._refresh_counts(self.checkpoint.range_start, self.checkpoint.range_end)

    def _refresh_counts(self, start: int, end: int) -> None:
        discovered, absent, unknown = count_status(self.latest, start, end)
        self.checkpoint.discovered_count = discovered
        self.checkpoint.absent_count = absent
        self.checkpoint.unknown_ids = [
            format_numeric_chem_id(n)
            for n in range(start, end + 1)
            if (self.latest.get(format_numeric_chem_id(n)) or {}).get("status") == DISCOVERY_UNKNOWN
        ]
        self.checkpoint.last_scanned_id = prefix_watermark(start, end, self.latest)
        self.checkpoint.range_start = start
        self.checkpoint.range_end = end
        self.checkpoint.updated_at = utc_now()

    def record(self, probe: ProbeRecord, *, range_start: int, range_end: int) -> ProbeRecord:
        with self.lock:
            row = probe.as_artifact_row()
            blob = json.dumps(row, ensure_ascii=False)
            if self.secret and self.secret in blob:
                row = json.loads(redact_secret(blob, self.secret))
            previous = self.latest.get(probe.chem_id) or {}
            if previous.get("status") == DISCOVERY_DISCOVERED and probe.status == DISCOVERY_DISCOVERED:
                # Identity set: the same chemId cannot be discovered twice.
                self.latest[probe.chem_id] = {**previous, "probed_at": probe.probed_at}
            else:
                self.latest[probe.chem_id] = row
                with self.artifact_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fh.flush()
            self.checkpoint.calls_attempted += 1
            if probe.http_status == 429:
                self.checkpoint.http_429 += 1
            if probe.result_code == "22":
                self.checkpoint.result_code_22 += 1
            if probe.status == DISCOVERY_UNKNOWN and not probe.quota_or_rate:
                self.checkpoint.other_api_errors += 1
            if probe.quota_or_rate:
                self.checkpoint.quota_stop = True
            self._refresh_counts(range_start, range_end)
            write_json_atomic(self.checkpoint_path, self.checkpoint.to_dict())
            return probe


@dataclass
class StageReport:
    start_id: int
    end_id: int
    calls: int
    discovered: int
    absent: int
    unknown: int
    quota_errors: int
    http_errors: int
    timeout_count: int
    latency_ms_avg: float
    workers: int
    quota_stop: bool


@dataclass
class CensusSummary:
    discovery_method: str
    census_status: str
    scan_range_completed: str
    calls_attempted: int
    discovered: int
    absent: int
    unknown: int
    max_discovered_chemid: Optional[str]
    min_discovered_chemid: Optional[str]
    highest_1000_block_hit_count: int
    tail_zero_discovery_run: int
    quota_errors: int
    http_429: int
    result_code_22: int
    other_api_errors: int
    effective_calls_per_sec: float
    portal_1000_day_hard_limit_observed: str
    durable_checkpoint: str
    artifact_path: str
    artifact_sha256: Optional[str]
    artifact_bytes: int
    artifact_rows: int
    initial_seed_candidate: str
    quota_stop: bool
    stages: list[StageReport] = field(default_factory=list)

    def secret_free_text(self) -> str:
        lines = [
            f"DETAIL01_ID_DISCOVERY = {self.discovery_method}",
            f"EMPIRICAL_API_CENSUS = {self.census_status}",
            f"scan range completed = {self.scan_range_completed}",
            f"calls attempted = {self.calls_attempted}",
            f"DISCOVERED = {self.discovered}",
            f"ABSENT = {self.absent}",
            f"UNKNOWN = {self.unknown}",
            f"MAX_DISCOVERED_CHEMID = {self.max_discovered_chemid or '-'}",
            f"MIN_DISCOVERED_CHEMID = {self.min_discovered_chemid or '-'}",
            f"highest 1000-id block hit count = {self.highest_1000_block_hit_count}",
            f"tail zero-discovery run = {self.tail_zero_discovery_run}",
            f"quota errors = {self.quota_errors}",
            f"HTTP 429 = {self.http_429}",
            f"resultCode 22 = {self.result_code_22}",
            f"other API errors = {self.other_api_errors}",
            f"effective calls/sec = {self.effective_calls_per_sec:.4f}",
            f"PORTAL 1000/day HARD LIMIT OBSERVED = {self.portal_1000_day_hard_limit_observed}",
            f"durable checkpoint = {self.durable_checkpoint}",
            f"artifact path = {self.artifact_path}",
            f"artifact SHA256 = {self.artifact_sha256 or '-'}",
            f"INITIAL_SEED_CANDIDATE = {self.initial_seed_candidate}",
        ]
        return "\n".join(lines)


def probe_one(client: KoshaMsdsClient, chem_id: str) -> ProbeRecord:
    raw = client.fetch_detail01_raw(chem_id)
    return classify_detail01(raw, secret=client.service_key or "")


def scan_chem_ids(
    client: KoshaMsdsClient,
    numeric_ids: list[int],
    store: DiscoveryStore,
    *,
    range_start: int,
    range_end: int,
    workers: int = DISCOVERY_WORKERS_START,
    production_writer: Optional[ProductionWriter] = None,
    log_progress: bool = False,
) -> list[ProbeRecord]:
    """Probe Detail01 for the given numeric chemIds. production_writer is never called."""
    del production_writer  # PATCH-3 forbids production ingest; tests assert this is unused.
    workers = clamp_workers(workers)
    stop = threading.Event()
    records: list[ProbeRecord] = []
    done = 0

    def emit(msg: str) -> None:
        if log_progress:
            print(msg, flush=True)

    def work(n: int) -> ProbeRecord:
        if stop.is_set():
            cid = format_numeric_chem_id(n)
            return ProbeRecord(
                chem_id=cid,
                status=DISCOVERY_UNKNOWN,
                http_status=None,
                result_code=None,
                result_msg="stopped before call",
                error_code="STOPPED",
                quota_or_rate=False,
                probed_at=utc_now(),
            )
        cid = format_numeric_chem_id(n)
        probe = probe_one(client, cid)
        stored = store.record(probe, range_start=range_start, range_end=range_end)
        if stored.quota_or_rate:
            stop.set()
        return stored

    if workers == 1:
        for n in numeric_ids:
            if stop.is_set():
                break
            rec = work(n)
            records.append(rec)
            done += 1
            if done % 100 == 0 or rec.quota_or_rate:
                emit(
                    f"PROGRESS scanned={done}/{len(numeric_ids)} "
                    f"last={rec.chem_id} status={rec.status} "
                    f"quota_stop={store.checkpoint.quota_stop}"
                )
        return records

    pending = iter(numeric_ids)
    in_flight: dict = {}

    def submit_one(pool: ThreadPoolExecutor) -> None:
        if stop.is_set():
            return
        try:
            n = next(pending)
        except StopIteration:
            return
        in_flight[pool.submit(work, n)] = n

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in range(min(workers, len(numeric_ids))):
            submit_one(pool)
        while in_flight:
            fut = next(as_completed(list(in_flight)))
            in_flight.pop(fut, None)
            rec = fut.result()
            records.append(rec)
            done += 1
            if done % 100 == 0 or rec.quota_or_rate:
                emit(
                    f"PROGRESS scanned={done}/{len(numeric_ids)} "
                    f"last={rec.chem_id} status={rec.status} "
                    f"quota_stop={store.checkpoint.quota_stop}"
                )
            if not stop.is_set():
                submit_one(pool)
    return records


def _stage_metrics(records: list[ProbeRecord], start: int, end: int, workers: int) -> StageReport:
    calls = len(records)
    discovered = sum(1 for r in records if r.status == DISCOVERY_DISCOVERED)
    absent = sum(1 for r in records if r.status == DISCOVERY_ABSENT)
    unknown = sum(1 for r in records if r.status == DISCOVERY_UNKNOWN)
    quota_errors = sum(1 for r in records if r.quota_or_rate)
    http_errors = sum(1 for r in records if r.http_status is not None and r.http_status >= 500)
    timeout_count = sum(
        1
        for r in records
        if r.error_code == "TRANSPORT" and r.http_status in {None, 0}
    )
    latencies = [r.elapsed_ms for r in records if r.elapsed_ms]
    return StageReport(
        start_id=start,
        end_id=end,
        calls=calls,
        discovered=discovered,
        absent=absent,
        unknown=unknown,
        quota_errors=quota_errors,
        http_errors=http_errors,
        timeout_count=timeout_count,
        latency_ms_avg=(sum(latencies) / len(latencies)) if latencies else 0.0,
        workers=workers,
        quota_stop=quota_errors > 0,
    )


def run_empirical_census(
    client: KoshaMsdsClient,
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    range_start: int = DISCOVERY_RANGE_START,
    range_end: int = DISCOVERY_RANGE_END,
    stages: tuple[tuple[int, int], ...] = DISCOVERY_STAGES,
    workers: int = DISCOVERY_WORKERS_START,
    tail: bool = True,
    production_writer: Optional[ProductionWriter] = None,
    checkpoint_path: Optional[Path] = None,
    artifact_path: Optional[Path] = None,
    log_progress: bool = False,
) -> CensusSummary:
    if production_writer is not None:
        # Accepted so tests can prove it is never invoked.
        production_writer = production_writer
    started = time.perf_counter()
    workers = clamp_workers(workers)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    checkpoint = checkpoint_path or (artifact_dir / "checkpoint.json")
    if artifact_path is not None:
        artifact = artifact_path
    elif checkpoint.exists():
        prev = json.loads(checkpoint.read_text(encoding="utf-8"))
        prev_artifact = Path(str(prev.get("artifact_path") or ""))
        artifact = prev_artifact if prev_artifact.name else (artifact_dir / f"chem_id_census_{stamp}.jsonl")
    else:
        artifact = artifact_dir / f"chem_id_census_{stamp}.jsonl"
    store = DiscoveryStore(artifact, checkpoint, secret=client.service_key or "")
    store.checkpoint.workers = workers
    store.checkpoint.range_start = range_start
    store.checkpoint.range_end = range_end
    stage_reports: list[StageReport] = []
    clipped_stages = []
    for start, end in stages:
        if end < range_start or start > range_end:
            continue
        clipped_stages.append((max(start, range_start), min(end, range_end)))
    if not clipped_stages:
        clipped_stages = [(range_start, range_end)]

    for start, end in clipped_stages:
        pending = pending_numeric_ids(start, end, store.latest)
        records = scan_chem_ids(
            client,
            pending,
            store,
            range_start=range_start,
            range_end=range_end,
            workers=workers,
            production_writer=None,
            log_progress=log_progress,
        )
        report = _stage_metrics(records, start, end, workers)
        stage_reports.append(report)
        if log_progress:
            print(
                f"STAGE {format_numeric_chem_id(start)}-{format_numeric_chem_id(end)} "
                f"calls={report.calls} DISCOVERED={report.discovered} "
                f"ABSENT={report.absent} UNKNOWN={report.unknown} "
                f"quota={report.quota_errors} http_5xx={report.http_errors} "
                f"timeouts={report.timeout_count} "
                f"latency_ms_avg={report.latency_ms_avg:.1f} workers={report.workers}",
                flush=True,
            )
        if store.checkpoint.quota_stop:
            break
        timeout_rate = (report.timeout_count / report.calls) if report.calls else 0.0
        if report.calls > 0 and timeout_rate < 0.05 and report.http_errors == 0:
            workers = clamp_workers(min(workers + 2, DISCOVERY_WORKERS_MAX))
            store.checkpoint.workers = workers

    tail_zero = 0
    scanned_end = range_end
    if tail and not store.checkpoint.quota_stop:
        tail_start = range_end + 1
        while True:
            tail_end = tail_start + DISCOVERY_TAIL_BLOCK - 1
            pending = pending_numeric_ids(tail_start, tail_end, store.latest)
            records = scan_chem_ids(
                client,
                pending,
                store,
                range_start=range_start,
                range_end=tail_end,
                workers=workers,
                production_writer=None,
                log_progress=log_progress,
            )
            stage_reports.append(_stage_metrics(records, tail_start, tail_end, workers))
            scanned_end = tail_end
            store.checkpoint.range_end = tail_end
            hits = len(discovered_ids_in_range(store.latest, tail_start, tail_end))
            if log_progress:
                print(
                    f"TAIL {format_numeric_chem_id(tail_start)}-{format_numeric_chem_id(tail_end)} "
                    f"DISCOVERED={hits} quota_stop={store.checkpoint.quota_stop}",
                    flush=True,
                )
            if store.checkpoint.quota_stop:
                break
            if evaluate_tail_block(discovered_count=hits) == TAIL_UPPER_BOUND_PASS:
                tail_zero = DISCOVERY_TAIL_BLOCK
                break
            tail_start = tail_end + 1

    latest = store.latest
    watermark = store.checkpoint.last_scanned_id or format_numeric_chem_id(range_start)
    if store.checkpoint.quota_stop:
        scanned_end_label = watermark
    else:
        scanned_end_label = format_numeric_chem_id(scanned_end)
    discovered_list = discovered_ids_in_range(latest, range_start, scanned_end)
    discovered, absent, unknown = count_status(latest, range_start, scanned_end)
    candidate_count = scanned_end - range_start + 1
    complete = range_complete(
        candidate_count=candidate_count,
        discovered=discovered,
        absent=absent,
        unknown=unknown,
    )
    elapsed = max(time.perf_counter() - started, 0.001)
    artifact_exists = artifact.exists()
    digest = sha256_file(artifact) if artifact_exists else None
    quota_errors = store.checkpoint.http_429 + store.checkpoint.result_code_22
    hard_limit = "YES" if store.checkpoint.quota_stop and quota_errors > 0 else "NO"
    seed_status = initial_seed_candidate_status(
        range_complete_ok=complete,
        unknown=unknown,
        trailing_zero=tail_zero == DISCOVERY_TAIL_BLOCK,
        checkpoint_ok=checkpoint.exists(),
        artifact_hash=digest,
        quota_stop=store.checkpoint.quota_stop,
    )
    row_count = sum(1 for line in artifact.read_text(encoding="utf-8").splitlines() if line.strip()) if artifact_exists else 0
    return CensusSummary(
        discovery_method=DISCOVERY_METHOD,
        census_status=EMPIRICAL_API_CENSUS,
        scan_range_completed=f"{format_numeric_chem_id(range_start)} ~ {scanned_end_label}",
        calls_attempted=store.checkpoint.calls_attempted,
        discovered=discovered,
        absent=absent,
        unknown=unknown,
        max_discovered_chemid=discovered_list[-1] if discovered_list else None,
        min_discovered_chemid=discovered_list[0] if discovered_list else None,
        highest_1000_block_hit_count=highest_1000_block_hit_count(latest, range_start, scanned_end),
        tail_zero_discovery_run=tail_zero,
        quota_errors=quota_errors,
        http_429=store.checkpoint.http_429,
        result_code_22=store.checkpoint.result_code_22,
        other_api_errors=store.checkpoint.other_api_errors,
        effective_calls_per_sec=store.checkpoint.calls_attempted / elapsed,
        portal_1000_day_hard_limit_observed=hard_limit,
        durable_checkpoint="PASS" if checkpoint.exists() else "FAIL",
        artifact_path=str(artifact),
        artifact_sha256=digest,
        artifact_bytes=artifact.stat().st_size if artifact_exists else 0,
        artifact_rows=row_count,
        initial_seed_candidate=seed_status,
        quota_stop=store.checkpoint.quota_stop,
        stages=stage_reports,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KOSHA Detail01 empirical chemId census")
    parser.add_argument("--start", type=int, default=DISCOVERY_RANGE_START)
    parser.add_argument("--end", type=int, default=DISCOVERY_RANGE_END)
    parser.add_argument("--workers", type=int, default=DISCOVERY_WORKERS_START)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--no-tail", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    client = KoshaMsdsClient(max_attempts=1, timeout_seconds=20)
    summary = run_empirical_census(
        client,
        artifact_dir=Path(args.artifact_dir),
        range_start=args.start,
        range_end=args.end,
        workers=args.workers,
        tail=not args.no_tail,
        production_writer=None,
        log_progress=True,
    )
    print(summary.secret_free_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
