"""
services/projection_cleanup.py — Projection 품질 정제 (deterministic, stateless).

semantic inference / 의미 생성 없음 — 패턴 제거·fallback chain·dedup·정렬만.
"""

from __future__ import annotations

import copy
import os
import re
from typing import Any, Dict, List, Optional, Tuple

PROJECTION_VERSION = "v1.0.0"

ENABLE_PROJECTION_CLEANUP = os.environ.get("TAI_PROJECTION_CLEANUP", "true").lower() == "true"

CATEGORY_ORDER = {
    "선임": 0,
    "점검": 1,
    "조치": 2,
    "신고": 3,
    "보고": 4,
}

_TASK_CANDIDATE_RE = re.compile(
    r"\b[A-Z][A-Z0-9_]*_TASK_CANDIDATE(?:\s*:\s*[A-Z0-9_]+)?\b",
)
_TASK_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9_]*_TASK_[A-Z0-9_]+\b")
_FAMILY_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9_]*_FAMILY\b")
_ALLCAPS_SNAKE_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")

_FAMILY_LABEL_MAP = {
    "APPOINT_FAMILY": "선임",
    "REPORT_FAMILY": "신고",
    "NOTIFY_FAMILY": "보고",
    "INSTALL_FAMILY": "설치",
    "MEASURE_FAMILY": "측정",
    "INSPECT_FAMILY": "점검",
    "MANDATORY_FAMILY": "의무 이행",
    "PERMISSIVE_FAMILY": "허용 행위",
}

_last_cleanup_stats: Optional[Dict[str, Any]] = None


def get_last_cleanup_stats() -> Optional[Dict[str, Any]]:
    return copy.deepcopy(_last_cleanup_stats) if _last_cleanup_stats else None


def record_last_cleanup_stats(stats: Dict[str, Any], *, applicable_count: int = 0) -> None:
    global _last_cleanup_stats
    empty_summary = stats.get("empty_summary_count", 0)
    _last_cleanup_stats = {
        **stats,
        "applicable_count": applicable_count,
        "empty_summary_count": empty_summary,
    }


def cleanup_runtime_labels(text: str) -> str:
    if not text:
        return ""
    out = text
    for fam, label in _FAMILY_LABEL_MAP.items():
        out = out.replace(fam, label)
    out = _TASK_CANDIDATE_RE.sub("", out)
    out = _TASK_TOKEN_RE.sub("", out)
    out = _FAMILY_TOKEN_RE.sub("", out)
    # 남은 ALLCAPS runtime 토큰 제거 (한글/혼합 텍스트 보존)
    tokens = out.split()
    cleaned_tokens: List[str] = []
    for tok in tokens:
        if _ALLCAPS_SNAKE_RE.fullmatch(tok) and "_" in tok:
            mapped = _FAMILY_LABEL_MAP.get(tok)
            if mapped:
                cleaned_tokens.append(mapped)
            continue
        cleaned_tokens.append(tok)
    out = " ".join(cleaned_tokens)
    out = re.sub(r"\s+", " ", out).strip(" ·|")
    return out.strip()


def stabilize_summary(row: Dict[str, Any]) -> str:
    remarks = cleanup_runtime_labels((row.get("remarks") or "").strip())
    summary = cleanup_runtime_labels((row.get("obligation_summary") or "").strip())
    desc = cleanup_runtime_labels((row.get("description") or "").strip())
    law_name = (row.get("law_name") or "").strip()
    law_article = (row.get("law_article") or "").strip()

    if remarks and len(remarks) >= 5:
        return remarks[:100]
    if summary and len(summary) >= 5:
        return summary[:100]
    if desc and len(desc) >= 5:
        return desc[:80]
    if law_name and law_article:
        return f"{law_name} {law_article} 관련 의무"
    if law_name:
        return f"{law_name} 관련 의무"
    return "관련 법적 의무 확인 필요"


def collapse_duplicates(rules_table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_ids: set = set()
    seen_keys: set = set()
    result: List[Dict[str, Any]] = []

    for row in rules_table:
        rid = str(row.get("rule_id") or "")
        if rid and rid in seen_ids:
            continue

        key: Tuple[str, str, str] = (
            (row.get("law_name") or "").strip(),
            (row.get("law_article") or "").strip(),
            (row.get("obligation_summary") or "").strip()[:50],
        )
        if key != ("", "", "") and key in seen_keys:
            continue

        if rid:
            seen_ids.add(rid)
        if key != ("", "", ""):
            seen_keys.add(key)
        result.append(row)

    return result


def stable_sort(rules_table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def sort_key(row: Dict[str, Any]):
        cat = CATEGORY_ORDER.get(row.get("category", ""), 99)
        law = row.get("law_name", "")
        article = row.get("law_article", "")
        article_num = 0
        m = re.search(r"(\d+)", article or "")
        if m:
            article_num = int(m.group(1))
        rid = row.get("rule_id", "")
        return (cat, law, article_num, rid)

    return sorted(rules_table, key=sort_key)


def reduce_article_flood(
    rules_table: List[Dict[str, Any]],
    max_per_article: int = 5,
) -> List[Dict[str, Any]]:
    article_counts: Dict[str, int] = {}
    result: List[Dict[str, Any]] = []

    for row in rules_table:
        key = f"{row.get('law_name', '')}|{row.get('law_article', '')}"
        count = article_counts.get(key, 0)
        article_counts[key] = count + 1

        if count < max_per_article:
            result.append(row)
        else:
            overflow_row = {**row, "_overflow": True}
            result.append(overflow_row)

    return result


def cleanup_projection(rules_table: List[Dict[str, Any]]) -> Dict[str, Any]:
    """rules_table in-place 정제 후 stats 반환."""
    input_count = len(rules_table)
    summaries_stabilized = 0
    labels_cleaned = 0
    empty_summary_count = 0

    for row in rules_table:
        original = (row.get("obligation_summary") or "").strip()
        if not original:
            empty_summary_count += 1
        stabilized = stabilize_summary(row)
        if stabilized != original:
            row["obligation_summary"] = stabilized
            summaries_stabilized += 1
        elif len(stabilized) > 100:
            row["obligation_summary"] = stabilized[:100]
            summaries_stabilized += 1

        for field in ("description", "remarks"):
            val = row.get(field, "")
            if not isinstance(val, str):
                continue
            cleaned = cleanup_runtime_labels(val)
            if cleaned != val:
                row[field] = cleaned
                labels_cleaned += 1

    before_dedup = len(rules_table)
    rules_table[:] = collapse_duplicates(rules_table)
    duplicates_removed = before_dedup - len(rules_table)

    rules_table[:] = stable_sort(rules_table)
    rules_table[:] = reduce_article_flood(rules_table)

    overflow_count = sum(1 for r in rules_table if r.get("_overflow"))
    output_count = len([r for r in rules_table if not r.get("_overflow")])

    stats = {
        "input_count": input_count,
        "output_count": output_count,
        "duplicates_removed": duplicates_removed,
        "summaries_stabilized": summaries_stabilized,
        "labels_cleaned": labels_cleaned,
        "overflow_count": overflow_count,
        "empty_summary_count": empty_summary_count,
    }
    return {"rules_table": rules_table, "stats": stats}


def apply_rules_table_cleanup(
    rules_table: List[Dict[str, Any]],
    *,
    enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """legal_step1_builder 연결용. disabled 시 no-op stats."""
    if enabled is None:
        enabled = ENABLE_PROJECTION_CLEANUP
    if not enabled or not rules_table:
        stats = {
            "input_count": len(rules_table),
            "output_count": len(rules_table),
            "duplicates_removed": 0,
            "summaries_stabilized": 0,
            "labels_cleaned": 0,
            "overflow_count": 0,
            "empty_summary_count": sum(
                1 for r in rules_table if not (r.get("obligation_summary") or "").strip()
            ),
            "skipped": True,
        }
        record_last_cleanup_stats(stats, applicable_count=len(rules_table))
        return stats

    result = cleanup_projection(rules_table)
    stats = result["stats"]
    record_last_cleanup_stats(stats, applicable_count=stats["output_count"])
    return stats
