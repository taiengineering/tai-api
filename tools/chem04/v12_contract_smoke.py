"""WO-CHEM-04-API-V12-ALIGN-001 one-shot v1.2 contract smoke.

17 live requests total:
  * 1  × getChemList001  (searchCnd=0, searchWrd=벤젠)
  * 16 × getChemDetail{01..16}1  for chemId=000001

Hard cap = 25.  No retry on HTTP 429 or resultCode 22 — record and STOP.
Prints an evidence summary; no artifacts written outside stdout. Redacts
the service key so it never appears in logs or captured output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from services.kr_public_api import kr_get
from services.kosha_msds.contract import (
    BASE_URL,
    LIST_OPERATION,
    LIVE_SAMPLE_KEY_ENV,
    OFFICIAL_SPEC_DATE,
    OFFICIAL_SPEC_VERSION,
    RATE_LIMIT_DAILY_CODES,
    SOURCE_CONTRACT_VERSION,
    SUCCESS_RESULT_CODES,
    detail_operation,
)
from services.kosha_msds.parse import parse_list_xml, parse_section_xml

HARD_CAP = 25
LIST_SEARCH_CND = "0"          # 국문명
LIST_SEARCH_WRD = "벤젠"
DETAIL_CHEM_ID = "000001"      # official example


def _service_key() -> str:
    for name in LIVE_SAMPLE_KEY_ENV:
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    raise SystemExit("BLOCKED: service key not in env")


def _summarise_body(body: str, key: str) -> str:
    # Redaction: never let the raw service key hit stdout.
    if key and key in body:
        body = body.replace(key, "[REDACTED]")
    return body[:120].replace("\n", " ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v1.2 17-call smoke")
    args = parser.parse_args(argv)
    _ = args

    key = _service_key()
    calls = 0
    report: dict[str, Any] = {
        "WO": "WO-CHEM-04-API-V12-ALIGN-001",
        "spec_version": OFFICIAL_SPEC_VERSION,
        "spec_date": OFFICIAL_SPEC_DATE,
        "contract_version": SOURCE_CONTRACT_VERSION,
        "base_url": BASE_URL,
        "list_operation": LIST_OPERATION,
        "hard_cap": HARD_CAP,
    }
    rate_limited = False

    # ---- STEP 1: list ------------------------------------------------------
    list_url = f"{BASE_URL}/{LIST_OPERATION}"
    calls += 1
    status, body = kr_get(
        list_url,
        params={
            "serviceKey": key,
            "searchCnd": LIST_SEARCH_CND,
            "searchWrd": LIST_SEARCH_WRD,
            "numOfRows": "10",
            "pageNo": "1",
        },
        timeout=30,
    )
    list_info: dict[str, Any] = {
        "url_ends": list_url.split("/")[-1],
        "http": status,
    }
    try:
        parsed_list = parse_list_xml(body or "", require_success=False)
    except Exception as exc:
        list_info["parse_error"] = type(exc).__name__
        parsed_list = None

    if parsed_list is not None:
        list_info["result_code"] = parsed_list.result_code
        list_info["total_count"] = parsed_list.total_count
        list_info["items"] = len(parsed_list.items)
        list_info["parse"] = "PASS"
        if parsed_list.result_code in RATE_LIMIT_DAILY_CODES:
            rate_limited = True
        list_info["success"] = (
            status == 200
            and parsed_list.result_code in SUCCESS_RESULT_CODES
            and len(parsed_list.items) > 0
        )
    else:
        list_info["success"] = False

    list_info["body_preview"] = _summarise_body(body or "", key)
    report["list"] = list_info

    # ---- STEP 2: 16 details ------------------------------------------------
    detail_infos: list[dict[str, Any]] = []
    detail_success = 0
    for section in range(1, 17):
        if calls >= HARD_CAP:
            report["stop_reason"] = "HARD_CAP_HIT"
            break
        if rate_limited:
            report["stop_reason"] = "RATE_LIMIT"
            break

        op = detail_operation(section)
        url = f"{BASE_URL}/{op}"
        calls += 1
        d_status, d_body = kr_get(
            url,
            params={"serviceKey": key, "chemId": DETAIL_CHEM_ID},
            timeout=30,
        )
        info: dict[str, Any] = {
            "section": section,
            "operation": op,
            "http": d_status,
        }
        try:
            parsed = parse_section_xml(d_body or "", require_success=False)
            info["parse"] = "PASS"
            info["result_code"] = parsed.result_code
            info["items"] = len(parsed.items)
            if parsed.result_code in RATE_LIMIT_DAILY_CODES:
                rate_limited = True
            info["success"] = (
                d_status == 200 and parsed.result_code in SUCCESS_RESULT_CODES
            )
        except Exception as exc:
            info["parse"] = "FAIL"
            info["parse_error"] = type(exc).__name__
            info["success"] = False

        info["body_preview"] = _summarise_body(d_body or "", key)
        detail_infos.append(info)
        if info["success"]:
            detail_success += 1

    report["details_attempted"] = len(detail_infos)
    report["details_success"] = detail_success
    report["details"] = detail_infos
    report["calls_total"] = calls
    report["rate_limited"] = rate_limited
    report["under_hard_cap"] = calls <= HARD_CAP

    # Sanitize before printing.
    printable = json.dumps(report, ensure_ascii=False, indent=2)
    if key and key in printable:
        printable = printable.replace(key, "[REDACTED]")
    print(printable)
    ok = (
        list_info.get("success") is True
        and detail_success == 16
        and not rate_limited
        and calls <= HARD_CAP
    )
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
