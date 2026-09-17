"""WO-CHEM-04-OFFICIAL-HYDRATE-V12-001 resumable KOSHA MSDS v1.2 hydration.

Reads the frozen AUTHORITATIVE_VERIFY queue (329,088 rows), calls the
official v1.2 Detail endpoints one by one under the current DEVELOPMENT
account, saves each successful section to a gitignored local artifact,
and STOPs on the first real quota signal (HTTP 429, resultCode 22/23),
an auth/contract error, an error budget breach, or the 40,000-request
safety cap. Fully resumable: re-runs skip any (chemId, sectionNo)
already recorded in responses.jsonl.

Zero production DB write. Zero customer publication. Service key is
read from env only and never serialized.

CLI:
  python -m tools.chem04.official_hydrate_v12 \
      --queue artifacts/chem04/content/queues/hydration_queue.jsonl \
      --resume \
      --hard-cap 40000 \
      --workers 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from services.kr_public_api import kr_get
from services.kosha_msds.client import (
    KoshaMsdsClient,
    KoshaMsdsClientError,
    KoshaMsdsTransportError,
)
from services.kosha_msds.contract import (
    ALLOWED_SECTIONS,
    LIVE_SAMPLE_KEY_ENV,
    OFFICIAL_SPEC_DATE,
    OFFICIAL_SPEC_VERSION,
    SOURCE_CONTRACT_VERSION,
    detail_operation,
)

WO_ID = "WO-CHEM-04-OFFICIAL-HYDRATE-V12-001"

DEFAULT_QUEUE = Path("artifacts/chem04/content/queues/hydration_queue.jsonl")
DEFAULT_OUT = Path("artifacts/chem04/official_v12")
EXPECTED_QUEUE_SHA256 = "7eba2dca2e183bab2c09f6260874cf8b5380ccb6d2f4bec61dfd193c881085d9"
EXPECTED_QUEUE_ROWS = 329088

DEFAULT_HARD_CAP = 40000
CONSECUTIVE_ERROR_BUDGET = 10

STOP_QUOTA = "QUOTA_LIMIT"
STOP_CONTRACT_AUTH = "CONTRACT_OR_AUTH_ERROR"
STOP_SAFETY_CAP = "SAFETY_CAP_REACHED"
STOP_ERROR_BUDGET = "ERROR_BUDGET_EXCEEDED"
STOP_QUEUE_COMPLETE = "QUEUE_COMPLETE"
STOP_QUEUE_GUARD = "QUEUE_GUARD_FAILED"
STOP_UNEXPECTED = "UNEXPECTED_FATAL_ERROR"

AUTH_ERROR_MSG_MARKERS = (
    "gateway 인증실패",
    "service key not registered",
    "invalid service key",
    "no_openapi_service_error",
    "service access denied",
    "not registered",
)


# ---------------------------------------------------------------------------
# Env / key
# ---------------------------------------------------------------------------


def _service_key() -> str:
    for name in LIVE_SAMPLE_KEY_ENV:
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    raise SystemExit("BLOCKED: service key not in env")


# ---------------------------------------------------------------------------
# Queue guard
# ---------------------------------------------------------------------------


def _queue_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_queue(path: Path, expect_rows: int, expect_sha: Optional[str]) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"BLOCKED: queue missing {path}")
    sha = _queue_sha256(path)
    rows: list[dict] = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    if expect_rows and len(rows) != expect_rows:
        raise SystemExit(f"BLOCKED: queue rows {len(rows)} != {expect_rows}")
    if expect_sha and sha != expect_sha:
        raise SystemExit(f"BLOCKED: queue sha {sha} != {expect_sha}")
    pairs = {(r["chemId"], r["sectionNo"]) for r in rows}
    if len(pairs) != len(rows):
        raise SystemExit("BLOCKED: queue has duplicate (chemId, sectionNo)")
    for r in rows:
        if int(r["sectionNo"]) not in ALLOWED_SECTIONS:
            raise SystemExit(
                f"BLOCKED: queue has invalid sectionNo {r['sectionNo']} for {r['chemId']}"
            )
    return rows


# ---------------------------------------------------------------------------
# Resume state — read every existing response
# ---------------------------------------------------------------------------


def _load_completed_pairs(responses_path: Path) -> set[tuple[str, int]]:
    if not responses_path.exists():
        return set()
    done: set[tuple[str, int]] = set()
    with responses_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            done.add((str(r["chemId"]), int(r["sectionNo"])))
    return done


# ---------------------------------------------------------------------------
# Secret / redaction guards
# ---------------------------------------------------------------------------


def _redact(text: str, key: str) -> str:
    if not text:
        return text
    out = text.replace(key, "[REDACTED]") if key else text
    return re.sub(r"serviceKey=[^&\s\"']+", "serviceKey=[REDACTED]", out)


def _is_auth_error(msg: str) -> bool:
    m = (msg or "").lower()
    return any(marker in m for marker in AUTH_ERROR_MSG_MARKERS)


def _canonical_json_sha256(payload: dict) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _new_client(key: str) -> KoshaMsdsClient:
    return KoshaMsdsClient(
        get_fn=kr_get,
        service_key=key,
        timeout_seconds=30,
        max_attempts=3,
    )


def _append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def _write_checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _scan_secret_free(paths: Iterable[Path], key: str) -> None:
    for p in paths:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if key and key in text:
            raise SystemExit(f"BLOCKED: raw key leaked into {p}")
        if "serviceKey=" in text and "[REDACTED]" not in text:
            raise SystemExit(f"BLOCKED: serviceKey= present in {p}")


def _classify_error_msg(msg: str) -> str:
    m = (msg or "").lower()
    if any(k in m for k in ("timeout", "timed out")):
        return "TIMEOUT"
    if "http 5" in m:
        return "HTTP_5XX"
    if "http 4" in m:
        return "HTTP_4XX"
    return "TRANSPORT"


def run(
    *,
    queue_path: Path = DEFAULT_QUEUE,
    out_dir: Path = DEFAULT_OUT,
    hard_cap: int = DEFAULT_HARD_CAP,
    resume: bool = True,
    expect_rows: int = EXPECTED_QUEUE_ROWS,
    expect_sha: Optional[str] = EXPECTED_QUEUE_SHA256,
    client_factory=None,
    started_at: Optional[str] = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    responses_path = out_dir / "responses.jsonl"
    errors_path = out_dir / "errors.jsonl"
    checkpoint_path = out_dir / "checkpoint.json"
    report_path = out_dir / "run_report.json"

    queue_rows = _load_queue(queue_path, expect_rows, expect_sha)
    queue_sha = _queue_sha256(queue_path)

    done_pairs = _load_completed_pairs(responses_path) if resume else set()
    start_completed = len(done_pairs)

    key = _service_key()
    client = (client_factory or _new_client)(key)

    per_section_calls: dict[int, int] = {n: 0 for n in ALLOWED_SECTIONS}
    http_requests = 0
    new_success = 0
    new_official_empty = 0
    new_errors = 0
    http_429 = 0
    rc22 = 0
    rc23 = 0
    consecutive_errors = 0
    stop_reason: Optional[str] = None
    first_quota_op: Optional[str] = None
    first_quota_chem: Optional[str] = None
    last_completed_chem: Optional[str] = None
    last_completed_section: Optional[int] = None
    started_at = started_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    next_index = 0

    def _emit_checkpoint():
        _write_checkpoint(
            checkpoint_path,
            {
                "queue_sha256": queue_sha,
                "queue_rows": len(queue_rows),
                "next_queue_index": next_index,
                "start_completed": start_completed,
                "new_success": new_success,
                "new_official_empty": new_official_empty,
                "new_errors": new_errors,
                "http_requests": http_requests,
                "http_429": http_429,
                "result_code_22": rc22,
                "result_code_23": rc23,
                "per_section_call_count": {str(k): v for k, v in per_section_calls.items()},
                "last_completed_chemId": last_completed_chem,
                "last_completed_sectionNo": last_completed_section,
                "stop_reason": stop_reason,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

    try:
        for idx, row in enumerate(queue_rows):
            next_index = idx
            chem = str(row["chemId"])
            section = int(row["sectionNo"])
            if (chem, section) in done_pairs:
                continue
            if http_requests >= hard_cap:
                stop_reason = STOP_SAFETY_CAP
                break
            operation = detail_operation(section)
            http_requests += 1
            per_section_calls[section] += 1
            try:
                fetched = client.get_detail_section(chem, section)
            except KoshaMsdsTransportError as exc:
                msg = _redact(str(exc), key)
                _append_jsonl(
                    errors_path,
                    {
                        "chemId": chem,
                        "sectionNo": section,
                        "operation": operation,
                        "code": "TRANSPORT",
                        "http_status": exc.http_status,
                        "message": msg[:400],
                        "class": _classify_error_msg(msg),
                        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    },
                )
                new_errors += 1
                if exc.http_status == 429:
                    http_429 += 1
                    first_quota_op = operation
                    first_quota_chem = chem
                    stop_reason = STOP_QUOTA
                    break
                consecutive_errors += 1
                if consecutive_errors >= CONSECUTIVE_ERROR_BUDGET:
                    stop_reason = STOP_ERROR_BUDGET
                    break
                continue
            except KoshaMsdsClientError as exc:
                # RATE_LIMIT and auth/contract errors are terminal; everything
                # else counts against the consecutive-error budget.
                msg = _redact(exc.message, key)
                _append_jsonl(
                    errors_path,
                    {
                        "chemId": chem,
                        "sectionNo": section,
                        "operation": operation,
                        "code": exc.code,
                        "message": msg[:400],
                        "class": _classify_error_msg(msg),
                        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    },
                )
                new_errors += 1
                if exc.code == "RATE_LIMIT":
                    # Distinguish rc22 vs rc23 based on the message envelope if
                    # possible; fall back to rc22 for a "daily" flavor.
                    if "23" in msg or "second" in msg.lower():
                        rc23 += 1
                    else:
                        rc22 += 1
                    first_quota_op = operation
                    first_quota_chem = chem
                    stop_reason = STOP_QUOTA
                    break
                if _is_auth_error(msg) or exc.code == "SERVICE_KEY_MISSING":
                    stop_reason = STOP_CONTRACT_AUTH
                    break
                consecutive_errors += 1
                if consecutive_errors >= CONSECUTIVE_ERROR_BUDGET:
                    stop_reason = STOP_ERROR_BUDGET
                    break
                continue
            # Successful fetch (parse succeeded, resultCode 00).
            consecutive_errors = 0
            is_empty = not fetched.items
            payload = {
                "chemId": chem,
                "sectionNo": section,
                "operation": operation,
                "source": "KOSHA_OFFICIAL",
                "source_contract_version": SOURCE_CONTRACT_VERSION,
                "official_spec_version": OFFICIAL_SPEC_VERSION,
                "official_spec_date": OFFICIAL_SPEC_DATE,
                "result_code": fetched.result_code,
                "result_msg": _redact(fetched.result_msg or "", key)[:200],
                "status": "OFFICIAL_EMPTY" if is_empty else fetched.status,
                "items": fetched.items,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "authoritative_verified": True,
            }
            _append_jsonl(responses_path, payload)
            done_pairs.add((chem, section))
            last_completed_chem = chem
            last_completed_section = section
            if is_empty:
                new_official_empty += 1
            else:
                new_success += 1
            if (new_success + new_official_empty + new_errors) % 200 == 0:
                _emit_checkpoint()
        else:
            stop_reason = STOP_QUEUE_COMPLETE
            next_index = len(queue_rows)
    except KeyboardInterrupt:
        stop_reason = stop_reason or "KEYBOARD_INTERRUPT"
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover
        stop_reason = STOP_UNEXPECTED
        _append_jsonl(
            errors_path,
            {
                "code": "FATAL",
                "message": _redact(str(exc), key)[:400],
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

    _emit_checkpoint()

    ended_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    total_completed = start_completed + new_success + new_official_empty
    remaining = len(queue_rows) - total_completed
    report = {
        "WO": WO_ID,
        "queue_path": str(queue_path),
        "queue_sha256": queue_sha,
        "queue_rows": len(queue_rows),
        "start_completed": start_completed,
        "new_success": new_success,
        "new_official_empty": new_official_empty,
        "new_errors": new_errors,
        "total_completed": total_completed,
        "remaining": remaining,
        "http_requests": http_requests,
        "http_429": http_429,
        "result_code_22": rc22,
        "result_code_23": rc23,
        "per_section_calls": {str(k): v for k, v in per_section_calls.items()},
        "first_quota_hit_operation": first_quota_op,
        "first_quota_hit_chemId": first_quota_chem,
        "stop_reason": stop_reason,
        "hard_cap": hard_cap,
        "workers": 1,
        "started_at": started_at,
        "ended_at": ended_at,
    }
    _write_checkpoint(report_path, report)

    _scan_secret_free([responses_path, errors_path, checkpoint_path, report_path], key)

    report["responses_sha256"] = _file_sha256(responses_path)
    report["errors_sha256"] = _file_sha256(errors_path)
    report["checkpoint_sha256"] = _canonical_json_sha256(
        json.loads(checkpoint_path.read_text(encoding="utf-8"))
    )
    report["run_report_canonical_sha256"] = _canonical_json_sha256(
        {k: v for k, v in report.items() if k != "run_report_canonical_sha256"}
    )
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} runner")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--hard-cap", type=int, default=DEFAULT_HARD_CAP)
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--expect-queue-sha",
        default=EXPECTED_QUEUE_SHA256,
        help="Expected queue SHA256; disable with empty string to bypass (tests only)",
    )
    parser.add_argument(
        "--expect-queue-rows",
        type=int,
        default=EXPECTED_QUEUE_ROWS,
    )
    args = parser.parse_args(argv)

    if args.workers != 1:
        raise SystemExit("BLOCKED: this WO enforces workers=1")

    result = run(
        queue_path=Path(args.queue),
        out_dir=Path(args.out_dir),
        hard_cap=args.hard_cap,
        resume=args.resume,
        expect_rows=args.expect_queue_rows,
        expect_sha=args.expect_queue_sha or None,
    )
    # Print report without ever exposing the key.
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
