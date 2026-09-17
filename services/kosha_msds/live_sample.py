"""OPTION C live sample comparator. No production writer. No key logging."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from services.kosha_msds.bootstrap import require_padded_chem_id
from services.kosha_msds.bootstrap_decision import (
    classify_pair,
    flatten_msds_xml,
    sample_manifest_hash,
)
from services.kosha_msds.client import section_token
from services.kosha_msds.contract import (
    ALLOWED_SECTIONS,
    BASE_URL,
    DETAIL_OPERATION_PREFIX,
    detail_operation,
    EXPECTED_OPTIONC_SAMPLE_SHA256,
    LIVE_SAMPLE_HARD_CAP,
    LIVE_SAMPLE_KEY_ENV,
    LIVE_SAMPLE_MAX_CALLS,
    LIVE_SAMPLE_RETRY_MAX,
    PREFLIGHT_CHEM_ID,
    PREFLIGHT_SECTION,
    RATE_LIMIT_DAILY_CODES,
)
from services.kosha_msds.content_audit import ContentAuditError, assert_secret_free
from services.kosha_msds.parse import KoshaMsdsParseError, parse_section_xml

GetFn = Callable[..., tuple[int, str]]
ProductionWriter = Callable[..., object]
LOGGER = logging.getLogger("chem04.live_sample")


class LiveSampleError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class QuotaStop(LiveSampleError):
    def __init__(self, http_429: int = 0, result_code_22: int = 0, message: str = "quota stop"):
        super().__init__("QUOTA_STOP", message)
        self.http_429 = http_429
        self.result_code_22 = result_code_22


class PreflightStop(LiveSampleError):
    def __init__(self, fetch_error: str):
        super().__init__("PREFLIGHT_FAIL", f"preflight {PREFLIGHT_CHEM_ID} Detail01 failed: {fetch_error}")
        self.fetch_error = fetch_error


def error_token_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        token = row.get("fetch_error")
        if token:
            counts[str(token)] = counts.get(str(token), 0) + 1
    return dict(sorted(counts.items()))


def classify_fetch_error_token(detail: str) -> str:
    token = (detail or "").strip() or "TRANSPORT"
    if token.startswith("HTTP_") or token.startswith("RESULT_"):
        return token
    if token in {"PARSE", "TIMEOUT", "TRANSPORT"}:
        return token
    lowered = token.lower()
    if "timeout" in lowered or "timed out" in lowered:
        return "TIMEOUT"
    return "TRANSPORT"


def live_sample_key() -> str:
    for name in LIVE_SAMPLE_KEY_ENV:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def detail_url(section_no: int) -> str:
    return f"{BASE_URL}/{detail_operation(section_no)}"


def sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def first_diff_position(left: str, right: str) -> Optional[int]:
    n = min(len(left), len(right))
    for i in range(n):
        if left[i] != right[i]:
            return i
    if len(left) != len(right):
        return n
    return None


def load_sample_rows(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["sample"] if isinstance(payload, dict) and "sample" in payload else payload
    return [{"chemId": require_padded_chem_id(r["chemId"]), "stratum": r["stratum"]} for r in rows]


def assert_manifest_sha(rows: list[dict], expected: str = EXPECTED_OPTIONC_SAMPLE_SHA256) -> str:
    actual = sample_manifest_hash(rows)
    if actual != expected:
        raise LiveSampleError("MANIFEST_MISMATCH", f"sample SHA {actual} != {expected}")
    return actual


def chemical_status(classes: list[str]) -> str:
    if any(c == "API_ERROR" for c in classes) or len(classes) < 16:
        return "UNVERIFIED"
    if any(c == "CONTENT_DIFFERENT" for c in classes):
        return "HAS_DIFFERENCE"
    if any(c in {"OFFICIAL_EMPTY", "SECONDARY_EMPTY", "SECONDARY_MISSING"} for c in classes):
        return "HAS_EMPTY_CONFLICT"
    if all(c in {"EXACT", "NORMALIZED_EQUAL"} for c in classes):
        return "ALL_MATCH"
    return "UNVERIFIED"


def comparison_metrics(rows: list[dict]) -> dict[str, object]:
    counts = {
        "EXACT": 0,
        "NORMALIZED_EQUAL": 0,
        "CONTENT_DIFFERENT": 0,
        "SECONDARY_MISSING": 0,
        "OFFICIAL_EMPTY": 0,
        "SECONDARY_EMPTY": 0,
        "API_ERROR": 0,
    }
    causes: dict[str, int] = {}
    for row in rows:
        code = row["class"]
        if code in counts:
            counts[code] += 1
        cause = row.get("possible_cause")
        if cause:
            causes[str(cause)] = causes.get(str(cause), 0) + 1
    comparable = counts["EXACT"] + counts["NORMALIZED_EQUAL"] + counts["CONTENT_DIFFERENT"]
    match = counts["EXACT"] + counts["NORMALIZED_EQUAL"]
    fidelity = round((match / comparable * 100.0), 2) if comparable else None
    successful = sum(1 for r in rows if r["class"] != "API_ERROR" and r.get("official_fetch") == "OK")
    by_chem: dict[str, list[str]] = {}
    for row in rows:
        by_chem.setdefault(row["chemId"], []).append(row["class"])
    chem_status = {cid: chemical_status(cls) for cid, cls in by_chem.items()}
    all_match = sum(1 for s in chem_status.values() if s == "ALL_MATCH")
    has_diff = sum(1 for s in chem_status.values() if s == "HAS_DIFFERENCE")
    empty_conflict = sum(1 for s in chem_status.values() if s == "HAS_EMPTY_CONFLICT")
    unverified = sum(1 for s in chem_status.values() if s == "UNVERIFIED")
    chem_n = len(chem_status)
    return {
        **counts,
        "comparable_sections": comparable,
        "section_fidelity_pct": fidelity,
        "successful_api_calls": successful,
        "chemical_ALL_MATCH": all_match,
        "chemical_HAS_DIFFERENCE": has_diff,
        "chemical_HAS_EMPTY_CONFLICT": empty_conflict,
        "chemical_UNVERIFIED": unverified,
        "chemical_all_match_pct": round((all_match / chem_n * 100.0), 2) if chem_n else None,
        "chemical_status": chem_status,
        "difference_causes": causes,
        "error_token_counts": error_token_counts(rows),
    }


def technical_option_c_gate(report: dict) -> str:
    if report.get("quota_stop") or report.get("secret_leak"):
        return "BLOCKED"
    preflight = report.get("preflight") or {}
    if isinstance(preflight, dict) and preflight.get("preflight") == "FAIL":
        return "BLOCKED"
    completed = int(report.get("sample_chemicals_completed") or 0)
    planned = int(report.get("planned_sections") or 0)
    rows_n = int(report.get("compared_sections") or 0)
    if completed < 16 or rows_n < planned:
        return "LOCAL_RUN_PENDING"
    if int(report.get("API_ERROR") or 0) and not int(report.get("comparable_sections") or 0):
        return "BLOCKED"
    return "PENDING_GPT"


def _quota_from_body(body: str) -> bool:
    try:
        parsed = parse_section_xml(body, require_success=False)
    except (KoshaMsdsParseError, Exception):
        return False
    return parsed.result_code in RATE_LIMIT_DAILY_CODES


def _is_retryable_timeout(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return "timeout" in name or "timed out" in text or "timeout" in text


def fetch_official_xml(
    *,
    chem_id: str,
    section_no: int,
    get_fn: GetFn,
    service_key: str,
    timeout_seconds: int = 30,
    http_counter: Optional[list[int]] = None,
    hard_cap: int = LIVE_SAMPLE_HARD_CAP,
) -> tuple[str, str]:
    """Return (status, xml_or_error). Retries timeout/5xx once. No 429 retry."""
    url = detail_url(section_no)
    params = {"chemId": chem_id, "serviceKey": service_key}
    last_status = 0
    last_body = ""
    LOGGER.info("section fetch chemId=%s sectionNo=%s", chem_id, section_no)
    for attempt in range(1, LIVE_SAMPLE_RETRY_MAX + 1):
        if http_counter is not None:
            if http_counter[0] >= hard_cap:
                raise LiveSampleError("CALL_CAP", f"HTTP calls {http_counter[0]} >= {hard_cap}")
            http_counter[0] += 1
        try:
            status, body = get_fn(url, params=params, timeout=timeout_seconds)
        except Exception as exc:
            if _is_retryable_timeout(exc) and attempt < LIVE_SAMPLE_RETRY_MAX:
                continue
            return "API_ERROR", "TIMEOUT" if _is_retryable_timeout(exc) else "TRANSPORT"
        last_status, last_body = status, body or ""
        if status == 429 or _quota_from_body(last_body):
            http_429 = 1 if status == 429 else 0
            rc22 = 1 if _quota_from_body(last_body) else 0
            raise QuotaStop(http_429=http_429, result_code_22=rc22)
        if status >= 500 and attempt < LIVE_SAMPLE_RETRY_MAX:
            continue
        if status != 200:
            return "API_ERROR", f"HTTP_{status}"
        try:
            parsed = parse_section_xml(last_body, require_success=False)
        except KoshaMsdsParseError:
            return "API_ERROR", "PARSE"
        if parsed.result_code in RATE_LIMIT_DAILY_CODES:
            raise QuotaStop(result_code_22=1)
        if parsed.result_code != "00":
            return "API_ERROR", f"RESULT_{parsed.result_code}"
        return "OK", last_body
    if last_status >= 500:
        return "API_ERROR", f"HTTP_{last_status}"
    return "API_ERROR", "TRANSPORT"


def run_preflight(
    *,
    get_fn: GetFn,
    service_key: str,
    http_counter: Optional[list[int]] = None,
    hard_cap: int = LIVE_SAMPLE_HARD_CAP,
) -> dict[str, object]:
    """One getChemDetail011 (v1.2 Detail 1) call for chemId 001008. Does not write the sample checkpoint."""
    payload: dict[str, object] = {
        "preflight": "FAIL",
        "chemId": PREFLIGHT_CHEM_ID,
        "sectionNo": PREFLIGHT_SECTION,
        "fetch_error": None,
        "official_fetch": "API_ERROR",
        "http_requests": 0,
    }
    counter = http_counter if http_counter is not None else [0]
    before = counter[0]
    try:
        status, detail = fetch_official_xml(
            chem_id=PREFLIGHT_CHEM_ID,
            section_no=PREFLIGHT_SECTION,
            get_fn=get_fn,
            service_key=service_key,
            http_counter=counter,
            hard_cap=hard_cap,
        )
    except QuotaStop as exc:
        token = "HTTP_429" if exc.http_429 else "RESULT_22"
        payload["fetch_error"] = token
        payload["official_fetch"] = "API_ERROR"
        payload["http_requests"] = counter[0] - before
        payload["quota_stop"] = True
        payload["HTTP_429"] = exc.http_429
        payload["resultCode_22"] = exc.result_code_22
        return payload
    payload["http_requests"] = counter[0] - before
    if status == "OK":
        payload["preflight"] = "OK"
        payload["official_fetch"] = "OK"
        payload["fetch_error"] = None
        return payload
    payload["fetch_error"] = classify_fetch_error_token(detail)
    return payload


def compare_section(secondary: Optional[str], official_xml: Optional[str], fetch_status: str) -> dict:
    if fetch_status != "OK":
        return {
            "class": "API_ERROR",
            "official_text": None,
            "possible_cause": None,
        }
    official_text = flatten_msds_xml(official_xml or "")
    code = classify_pair(secondary, official_text)
    cause = None
    if code == "CONTENT_DIFFERENT":
        cause = "UNKNOWN"
    return {"class": code, "official_text": official_text, "possible_cause": cause}


def read_checkpoint(path: Optional[Path]) -> dict:
    if path is None or not path.exists():
        return {"done": [], "attempted_calls": 0, "quota_stop": False, "http_requests": 0}
    return json.loads(path.read_text(encoding="utf-8"))


def write_checkpoint(path: Optional[Path], payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _checkpoint_payload(
    *,
    done: set[tuple[str, int]],
    attempted: int,
    rows: list[dict],
    quota_stop: bool,
    http_429: int,
    rc22: int,
    http_requests: int,
) -> dict:
    return {
        "done": [list(item) for item in sorted(done)],
        "attempted_calls": attempted,
        "quota_stop": quota_stop,
        "rows": rows,
        "http_429": http_429,
        "resultCode_22": rc22,
        "http_requests": http_requests,
    }


def run_live_sample(
    *,
    sample_rows: list[dict],
    secondary_by_chem: dict[str, dict[int, str]],
    get_fn: GetFn,
    service_key: str,
    max_calls: int = LIVE_SAMPLE_MAX_CALLS,
    max_chems: Optional[int] = None,
    checkpoint_path: Optional[Path] = None,
    raw_dir: Optional[Path] = None,
    normalized_dir: Optional[Path] = None,
    production_writer: Optional[ProductionWriter] = None,
    hard_cap: int = LIVE_SAMPLE_HARD_CAP,
    require_preflight: bool = False,
) -> dict[str, object]:
    if production_writer is not None:
        raise LiveSampleError("PRODUCTION_WRITER", "production writer is forbidden")
    if max_calls > hard_cap or max_calls > LIVE_SAMPLE_HARD_CAP:
        raise LiveSampleError("CALL_CAP", f"max_calls {max_calls} > {min(hard_cap, LIVE_SAMPLE_HARD_CAP)}")
    assert_manifest_sha(sample_rows)
    exec_rows = sample_rows[:max_chems] if max_chems is not None else sample_rows
    http_counter = [0]
    preflight = None
    preflight_http = 0
    if require_preflight:
        preflight = run_preflight(
            get_fn=get_fn,
            service_key=service_key,
            http_counter=http_counter,
            hard_cap=hard_cap,
        )
        if preflight.get("preflight") != "OK":
            report = {
                "WO": "WO-CHEM-04-OPTIONC-FETCH-DIAG-001",
                "sample_manifest_sha256": sample_manifest_hash(sample_rows),
                "sample_chemicals_selected": len(sample_rows),
                "sample_chemicals_attempted": 0,
                "sample_chemicals_completed": 0,
                "planned_sections": len(sample_rows) * 16,
                "compared_sections": 0,
                "quota_stop": bool(preflight.get("quota_stop")),
                "HTTP_429": int(preflight.get("HTTP_429") or 0),
                "resultCode_22": int(preflight.get("resultCode_22") or 0),
                "secret_leak": 0,
                "production_writer": None,
                "BOOTSTRAP_POLICY": "NOT DECIDED",
                "OPTION_B_auto_approve": "NO",
                "live_bulk_hydration": "NO",
                "production_ingest": "NO",
                "attempted_api_calls": 0,
                "http_requests": http_counter[0],
                "execution_success_pct": None,
                "preflight": preflight,
                "error_token_counts": (
                    {str(preflight.get("fetch_error")): 1} if preflight.get("fetch_error") else {}
                ),
                "EXACT": 0,
                "NORMALIZED_EQUAL": 0,
                "CONTENT_DIFFERENT": 0,
                "SECONDARY_MISSING": 0,
                "OFFICIAL_EMPTY": 0,
                "SECONDARY_EMPTY": 0,
                "API_ERROR": 0,
                "comparable_sections": 0,
                "section_fidelity_pct": None,
                "successful_api_calls": 0,
                "chemical_ALL_MATCH": 0,
                "chemical_HAS_DIFFERENCE": 0,
                "chemical_HAS_EMPTY_CONFLICT": 0,
                "chemical_UNVERIFIED": 0,
                "chemical_all_match_pct": None,
                "chemical_status": {},
                "difference_causes": {},
            }
            report["TECHNICAL_OPTION_C_GATE"] = technical_option_c_gate(report)
            return {"rows": [], "report": report, "attempted_calls": 0, "preflight": preflight}
    preflight_http = http_counter[0]
    cp = read_checkpoint(checkpoint_path)
    done = {(str(a), int(b)) for a, b in cp.get("done") or []}
    attempted = int(cp.get("attempted_calls") or 0)
    rows: list[dict] = list(cp.get("rows") or [])
    http_429 = int(cp.get("http_429") or 0)
    rc22 = int(cp.get("resultCode_22") or 0)
    http_counter = [int(cp.get("http_requests") or 0)]
    quota_stop = False
    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)
    if normalized_dir:
        normalized_dir.mkdir(parents=True, exist_ok=True)
    try:
        for item in exec_rows:
            chem_id = item["chemId"]
            for n in ALLOWED_SECTIONS:
                key = (chem_id, n)
                if key in done:
                    continue
                if attempted >= max_calls:
                    raise LiveSampleError("MAX_CALLS", f"attempted {attempted} >= {max_calls}")
                attempted += 1
                secondary = secondary_by_chem.get(chem_id, {}).get(n)
                try:
                    fetch_status, body = fetch_official_xml(
                        chem_id=chem_id,
                        section_no=n,
                        get_fn=get_fn,
                        service_key=service_key,
                        http_counter=http_counter,
                        hard_cap=hard_cap,
                    )
                except QuotaStop as exc:
                    quota_stop = True
                    http_429 += exc.http_429
                    rc22 += exc.result_code_22
                    raise
                compared = compare_section(secondary, body if fetch_status == "OK" else None, fetch_status)
                fetch_error = classify_fetch_error_token(body) if fetch_status != "OK" else None
                if fetch_status == "OK" and raw_dir:
                    assert_secret_free(body)
                    if service_key and service_key in body:
                        raise ContentAuditError("SECRET_LEAK", "raw xml")
                    (raw_dir / f"{chem_id}_{n:02d}.xml").write_text(body, encoding="utf-8")
                sec_text = secondary or ""
                off_text = compared.get("official_text") or ""
                row = {
                    "chemId": chem_id,
                    "sectionNo": n,
                    "class": compared["class"],
                    "secondary_sha256": sha256_text(sec_text) if secondary is not None else None,
                    "official_sha256": sha256_text(off_text) if compared["class"] != "API_ERROR" else None,
                    "secondary_length": len(sec_text) if secondary is not None else None,
                    "official_length": len(off_text) if compared["class"] != "API_ERROR" else None,
                    "first_diff_position": (
                        first_diff_position(sec_text, off_text)
                        if compared["class"] == "CONTENT_DIFFERENT"
                        else None
                    ),
                    "difference_type": "TEXT_MISMATCH" if compared["class"] == "CONTENT_DIFFERENT" else None,
                    "possible_cause": compared["possible_cause"],
                    "attempted_calls": 1,
                    "official_fetch": fetch_status,
                    "fetch_error": fetch_error,
                }
                if compared["class"] == "CONTENT_DIFFERENT":
                    row["diff_excerpt"] = {
                        "secondary": sec_text[:120],
                        "official": off_text[:120],
                    }
                if normalized_dir:
                    (normalized_dir / f"{chem_id}_{n:02d}.json").write_text(
                        json.dumps(
                            {
                                "chemId": chem_id,
                                "sectionNo": n,
                                "class": compared["class"],
                                "secondary_sha256": row["secondary_sha256"],
                                "official_sha256": row["official_sha256"],
                                "fetch_error": fetch_error,
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                rows.append(row)
                done.add(key)
                write_checkpoint(
                    checkpoint_path,
                    _checkpoint_payload(
                        done=done,
                        attempted=attempted,
                        rows=rows,
                        quota_stop=False,
                        http_429=http_429,
                        rc22=rc22,
                        http_requests=http_counter[0],
                    ),
                )
    except QuotaStop:
        quota_stop = True
        write_checkpoint(
            checkpoint_path,
            _checkpoint_payload(
                done=done,
                attempted=attempted,
                rows=rows,
                quota_stop=True,
                http_429=http_429,
                rc22=rc22,
                http_requests=http_counter[0],
            ),
        )
    metrics = comparison_metrics(rows)
    successful = int(metrics["successful_api_calls"])
    report = {
        "WO": "WO-CHEM-04-OPTIONC-LIVE-SAMPLE-001",
        "sample_manifest_sha256": sample_manifest_hash(sample_rows),
        "sample_chemicals_selected": len(sample_rows),
        "sample_chemicals_attempted": len({r["chemId"] for r in rows}),
        "sample_chemicals_completed": sum(
            1 for cid in {r["chemId"] for r in rows} if sum(1 for r in rows if r["chemId"] == cid) == 16
        ),
        "planned_sections": len(sample_rows) * 16,
        "compared_sections": len(rows),
        "quota_stop": quota_stop,
        "HTTP_429": http_429,
        "resultCode_22": rc22,
        "secret_leak": 0,
        "production_writer": None,
        "BOOTSTRAP_POLICY": "NOT DECIDED",
        "OPTION_B_auto_approve": "NO",
        "live_bulk_hydration": "NO",
        "production_ingest": "NO",
        "attempted_api_calls": attempted,
        "http_requests": http_counter[0],
        "execution_success_pct": round((successful / attempted * 100.0), 2) if attempted else None,
        "preflight": preflight,
        "preflight_http_requests": preflight_http,
        **metrics,
    }
    report["TECHNICAL_OPTION_C_GATE"] = technical_option_c_gate(report)
    return {"rows": rows, "report": report, "attempted_calls": attempted}


def scan_secret_free_dir(path: Path, extra_tokens: tuple[str, ...] = ()) -> None:
    if not path.exists():
        return
    for file in path.rglob("*"):
        if not file.is_file():
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        assert_secret_free(text)
        lowered = text.lower()
        if "servicekey=" in lowered and "servicekey=[redacted]" not in lowered:
            raise ContentAuditError("SECRET_LEAK", str(file))
        for token in extra_tokens:
            if token and token in text:
                raise ContentAuditError("SECRET_LEAK", str(file))
