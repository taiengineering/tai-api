"""Phase 10B — Check→Quality Verification.

Check EvidenceReport를 Quality Evaluator에 넣었을 때
 READY / TRACE_REQUIRED / CORRECTION_REQUIRED가 타당하게 나오는지 검증.

검증 항목:
  V1: Check Complete + 조치 있음 → READY
  V2: Check Evidence 부족 → TRACE_REQUIRED
  V3: Claim 오류 / 구조 오류 → CORRECTION_REQUIRED
  V4: 중복 의무 → CORRECTION_REQUIRED
  V5: 동일 입력 → 동일 quality_status (결정론성)

실행 (라이브러리 필요 없음):
    python verification/phase10b_check_quality_verification.py
    —알는 데이터바이스 불필요
"""
from __future__ import annotations

import json
from typing import Any

from services.obligation_quality_evaluator import (
    CORRECTION_REQUIRED,
    READY,
    TRACE_REQUIRED,
    evaluate_quality,
)

# ──────────────────────────────────────────────────────────────
# 지원 함수
# ──────────────────────────────────────────────────────────────

_LAW_OK = {"law_name": "산업안전보건법", "article_no": "17"}


def _ob(**kw: Any) -> dict:
    return {"obligation_id": kw.pop("obligation_id", "OB-TEST"), **_LAW_OK, **kw}


def _report(
    claim_present: int = 0,
    ev_attached: int = 0,
    ev_not_attached: int = 0,
    ev_ref_missing: int = 0,
    claim_ref_missing: int = 0,
    claim_oos: int = 0,
    chain_complete: int = 0,
    chain_not_declared: int = 0,
    chain_broken: int = 0,
    chain_present: int = 0,
    obs_count: int = 1,
) -> dict:
    return {
        "report_id": "rpt_phase10b",
        "status_summary": {
            "claim": {
                "CLAIM_PRESENT": claim_present,
                "CLAIM_REF_MISSING": claim_ref_missing,
                "CLAIM_OUT_OF_SCOPE": claim_oos,
            },
            "evidence": {
                "EVIDENCE_ATTACHED": ev_attached,
                "EVIDENCE_NOT_ATTACHED": ev_not_attached,
                "EVIDENCE_REF_MISSING": ev_ref_missing,
            },
            "chain": {
                "EVIDENCE_CHAIN_COMPLETE": chain_complete,
                "EVIDENCE_CHAIN_NOT_DECLARED": chain_not_declared,
                "EVIDENCE_CHAIN_BROKEN": chain_broken,
                "EVIDENCE_CHAIN_PRESENT": chain_present,
            },
        },
        "observation_records": [{} for _ in range(obs_count)],
    }


def _check(item_id: str, description: str, ob: dict, report: dict,
           expected: str, *, duplicate: bool = False) -> dict:
    res = evaluate_quality(ob, report, duplicate=duplicate)
    passed = res["quality_status"] == expected
    return {
        "id": item_id,
        "description": description,
        "expected": expected,
        "actual": res["quality_status"],
        "reason": res["quality_reason"],
        "status": "PASS" if passed else "FAIL",
    }


# ──────────────────────────────────────────────────────────────
# 검증 항목
# ──────────────────────────────────────────────────────────────

def run_verification() -> list[dict]:
    items: list[dict] = []

    # V1: Check Complete + 조치 있음 → READY
    items.append(_check(
        "V1a", "CLAIM_PRESENT + EVIDENCE_ATTACHED + CHAIN_COMPLETE → READY",
        _ob(obligation_id="OB-V1a"),
        _report(claim_present=1, ev_attached=1, chain_complete=1),
        READY,
    ))
    items.append(_check(
        "V1b", "CLAIM_PRESENT + EVIDENCE_REF_RESOLVED + CHAIN_COMPLETE → READY",
        _ob(obligation_id="OB-V1b"),
        _report(claim_present=1, ev_attached=0, chain_complete=1),
        READY,
    ))

    # V2: Check Evidence 부족 → TRACE_REQUIRED
    items.append(_check(
        "V2a", "EVIDENCE_NOT_ATTACHED → TRACE_REQUIRED (EVIDENCE_INSUFFICIENT)",
        _ob(obligation_id="OB-V2a"),
        _report(claim_present=1, ev_not_attached=1, chain_complete=1),
        TRACE_REQUIRED,
    ))
    items.append(_check(
        "V2b", "CHAIN_NOT_DECLARED → TRACE_REQUIRED (ACTION_INSUFFICIENT, 조치 미연결)",
        _ob(obligation_id="OB-V2b"),
        _report(claim_present=1, ev_attached=1, chain_not_declared=1),
        TRACE_REQUIRED,
    ))
    items.append(_check(
        "V2c", "CHAIN_BROKEN → TRACE_REQUIRED (ACTION_INSUFFICIENT)",
        _ob(obligation_id="OB-V2c"),
        _report(claim_present=1, ev_attached=1, chain_broken=1),
        TRACE_REQUIRED,
    ))
    items.append(_check(
        "V2d", "관측로그 없음(빈 리포트) → TRACE_REQUIRED (EVIDENCE_INSUFFICIENT)",
        _ob(obligation_id="OB-V2d"),
        _report(claim_present=0, obs_count=0),
        TRACE_REQUIRED,
    ))

    # V3: Claim 오류 / 구조 오류 → CORRECTION_REQUIRED
    items.append(_check(
        "V3a", "CLAIM_REF_MISSING → CORRECTION_REQUIRED (CLAIM_ERROR)",
        _ob(obligation_id="OB-V3a"),
        _report(claim_ref_missing=1, ev_attached=1, chain_complete=1),
        CORRECTION_REQUIRED,
    ))
    items.append(_check(
        "V3b", "리포트 말형 (status_summary 누락) → CORRECTION_REQUIRED (DATA_ERROR)",
        _ob(obligation_id="OB-V3b"),
        {"observation_records": []},  # status_summary 없음
        CORRECTION_REQUIRED,
    ))
    items.append(_check(
        "V3c", "리포트 None → CORRECTION_REQUIRED (DATA_ERROR)",
        _ob(obligation_id="OB-V3c"),
        None,
        CORRECTION_REQUIRED,
    ))
    items.append(_check(
        "V3d", "법령 연결 누락 → CORRECTION_REQUIRED (LAW_LINK_ERROR)",
        {"obligation_id": "OB-V3d"},  # law_name/article_no 없음
        _report(claim_present=1, ev_attached=1, chain_complete=1),
        CORRECTION_REQUIRED,
    ))

    # V4: 중복 의무 → CORRECTION_REQUIRED
    items.append(_check(
        "V4a", "duplicate=True → CORRECTION_REQUIRED (DUPLICATE_OBLIGATION)",
        _ob(obligation_id="OB-V4a"),
        _report(claim_present=1, ev_attached=1, chain_complete=1),
        CORRECTION_REQUIRED,
        duplicate=True,
    ))

    # V5: 결정론성
    ob_v5 = _ob(obligation_id="OB-V5")
    rep_v5 = _report(claim_present=1, ev_attached=1, chain_complete=1)
    r1 = evaluate_quality(ob_v5, rep_v5)
    r2 = evaluate_quality(ob_v5, rep_v5)
    items.append({
        "id": "V5",
        "description": "동일 입력 → 동일 quality_status (결정론성)",
        "run1": r1, "run2": r2,
        "status": "PASS" if r1 == r2 else "FAIL",
    })

    return items


def main() -> None:
    items = run_verification()
    all_passed = all(item["status"] == "PASS" for item in items)
    report = {
        "phase": "10B",
        "total": len(items),
        "passed": sum(1 for i in items if i["status"] == "PASS"),
        "failed": sum(1 for i in items if i["status"] == "FAIL"),
        "all_passed": all_passed,
        "status": "VERIFIED" if all_passed else "FAILED",
        "items": items,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
