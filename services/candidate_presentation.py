"""services/candidate_presentation.py

Candidate Presentation Layer

역할:
  LEG Engine이 생성한 Raw Candidate를
  사용자가 볼 수 있는 Grouped / Display 형태로 변환.

원칙:
  Rule 삭제 금지 / Candidate 삭제 금지
  Rule Merge 금지 / candidate_id 변경 금지
  허용: 그룹 생성, 집계 생성, 표시용 객체 생성
"""
from __future__ import annotations
from typing import Any, Dict, List

PRESENTATION_VERSION = "1.0.0"

# ── Priority Engine ──────────────────────────────────────────────────────
SOURCE_TYPE_PRIORITY: Dict[str, int] = {
    "APPOINT":   100,
    "DESIGNATE":  95,
    "INSPECT":    90,
    "VERIFY":     85,
    "TRAINING":   80,
    "REPORT":     70,
    "NOTIFY":     65,
    "RECORD":     60,
    "ACTION":     50,
    "MANAGE":     45,
    "EXECUTE":    40,
    "MEASURE":    35,
    "PRESERVE":   30,
    "INSTALL":    25,
}

def _priority_score(source_types: List[str]) -> int:
    if not source_types:
        return 0
    return max(SOURCE_TYPE_PRIORITY.get(st, 0) for st in source_types)

def _priority_label(score: int) -> str:
    if score >= 90:
        return "HIGH"
    if score >= 70:
        return "MEDIUM"
    if score >= 40:
        return "LOW"
    return "INFO"


# ── Group Engine ─────────────────────────────────────────────────────────
def group_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    (law_name, article_no) 기준 그룹화.

    Returns:
        [
          {
            "group_key": "전기안전관리법 시행규칙|제2조",
            "law_name": "...",
            "article_no": "...",
            "candidate_count": 21,
            "candidate_ids": [...],
            "condition_codes": [...],
            "source_types": [...],
            "evidence_chain": [...],
          },
          ...
        ]
    """
    groups: Dict[str, Dict[str, Any]] = {}

    for c in (candidates or []):
        law = (c.get("law_name") or "").strip()
        art = (c.get("article_no") or "").strip()
        key = f"{law}|{art}"

        if key not in groups:
            groups[key] = {
                "group_key":      key,
                "law_name":       law,
                "article_no":     art,
                "candidate_count": 0,
                "candidate_ids":  [],
                "condition_codes": set(),
                "source_types":   set(),
                "evidence_chain": [],
            }

        g = groups[key]
        g["candidate_count"] += 1

        cid = c.get("candidate_id")
        if cid:
            g["candidate_ids"].append(cid)

        cc = c.get("condition_code")
        if cc:
            g["condition_codes"].add(cc)

        st = c.get("source_type")
        if st:
            g["source_types"].add(st)

        for ev in (c.get("evidence_chain") or []):
            if ev not in g["evidence_chain"]:
                g["evidence_chain"].append(ev)

    result = []
    for g in groups.values():
        g["condition_codes"] = sorted(g["condition_codes"])
        g["source_types"]    = sorted(g["source_types"])
        result.append(g)

    result.sort(key=lambda x: (-_priority_score(x["source_types"]), -x["candidate_count"]))
    return result


# ── Display Candidate Builder ─────────────────────────────────────────────
def build_display_candidates(grouped_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Grouped Candidates → 사용자에게 보여줄 Display Candidate.

    Returns:
        [
          {
            "display_id":          "law_name|article_no",
            "law_name":            "...",
            "article_no":          "...",
            "candidate_count":     21,
            "evidence_count":      21,
            "source_types":        [...],
            "primary_source_type": "APPOINT",
            "priority_score":      100,
            "priority_label":      "HIGH",
          },
          ...
        ]
    """
    display = []
    for g in (grouped_candidates or []):
        source_types = g.get("source_types") or []
        score = _priority_score(source_types)
        primary = max(
            source_types,
            key=lambda s: SOURCE_TYPE_PRIORITY.get(s, 0),
            default="",
        )
        display.append({
            "display_id":          g["group_key"],
            "law_name":            g["law_name"],
            "article_no":          g["article_no"],
            "candidate_count":     g["candidate_count"],
            "evidence_count":      len(g.get("evidence_chain") or []),
            "source_types":        source_types,
            "primary_source_type": primary,
            "priority_score":      score,
            "priority_label":      _priority_label(score),
        })
    return display


# ── Metadata ──────────────────────────────────────────────────────────────
def _build_presentation_metadata(raw_count: int, group_count: int, display_count: int) -> Dict[str, Any]:
    reduction = round((raw_count - display_count) / raw_count * 100, 1) if raw_count > 0 else 0.0
    return {
        "raw_count":      raw_count,
        "group_count":    group_count,
        "display_count":  display_count,
        "reduction_rate": reduction,
        "version":        PRESENTATION_VERSION,
    }


# ── 통합 Entry Point ──────────────────────────────────────────────────────
def build_candidate_presentation(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Raw Candidates → Presentation Layer 전체 생성.

    Args:
        candidates: to_candidate_contract()["candidates"]

    Returns:
        {
            "grouped_candidates": [...],
            "display_candidates": [...],
            "metadata": {...},
        }
    """
    raw_count = len(candidates or [])
    grouped  = group_candidates(candidates)
    display  = build_display_candidates(grouped)
    return {
        "grouped_candidates": grouped,
        "display_candidates": display,
        "metadata": _build_presentation_metadata(raw_count, len(grouped), len(display)),
    }
