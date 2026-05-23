#!/usr/bin/env python3
"""Step 2: projection sample anomaly 자동 탐지 + before/after 리포트.

Usage:
  python3 scripts/detect_projection_anomalies.py
  python3 scripts/detect_projection_anomalies.py --all-samples   # include stale sample_* dirs
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLES_ROOT = ROOT / "docs" / "projection_samples"


def load_samples(samples_dir: Path, *, use_manifest_only: bool = True) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    if not samples_dir.is_dir():
        return samples

    names: List[str] = []
    manifest_path = samples_dir / "manifest.json"
    if use_manifest_only and manifest_path.is_file():
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        names = [s.get("sample") for s in (manifest.get("samples") or []) if s.get("sample")]
    if not names:
        names = sorted(
            d.name for d in samples_dir.iterdir() if d.is_dir() and d.name.startswith("sample_")
        )

    for name in names:
        d = samples_dir / name
        if not d.is_dir():
            continue
        rules_path = d / "03_rules_table.json"
        before_path = d / "03_rules_table_before_cleanup.json"
        if not rules_path.is_file():
            continue
        with open(rules_path, encoding="utf-8") as f:
            rules_table = json.load(f)
        before = None
        if before_path.is_file():
            with open(before_path, encoding="utf-8") as f:
                before = json.load(f)
        meta = {}
        meta_path = d / "meta.json"
        if meta_path.is_file():
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        samples.append(
            {
                "name": d.name,
                "rules_table": rules_table,
                "rules_table_before": before,
                "meta": meta,
            }
        )
    return samples


def detect_anomalies(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    anomalies: List[Dict[str, Any]] = []

    for sample in samples:
        name = sample["name"]
        rules_table = sample["rules_table"]

        seen_rule_ids: Dict[str, int] = {}
        for i, row in enumerate(rules_table):
            rid = row.get("rule_id")
            if rid:
                if rid in seen_rule_ids:
                    anomalies.append(
                        {
                            "type": "DUPLICATE_RULE",
                            "severity": "HIGH",
                            "sample": name,
                            "row_index": i,
                            "rule_id": rid,
                            "first_index": seen_rule_ids[rid],
                        }
                    )
                else:
                    seen_rule_ids[rid] = i

            if not (row.get("obligation_summary") or "").strip():
                anomalies.append(
                    {
                        "type": "EMPTY_SUMMARY",
                        "severity": "HIGH",
                        "sample": name,
                        "row_index": i,
                        "rule_id": row.get("rule_id"),
                        "description": (row.get("description") or "")[:100],
                    }
                )

            for field in ("obligation_summary", "description", "remarks"):
                val = row.get(field, "") or ""
                if "_TASK_CANDIDATE" in val or "_TASK_" in val:
                    anomalies.append(
                        {
                            "type": "RUNTIME_LABEL_EXPOSED",
                            "severity": "HIGH",
                            "sample": name,
                            "row_index": i,
                            "field": field,
                            "value": val[:200],
                        }
                    )

            summary = row.get("obligation_summary", "") or ""
            if len(summary) > 100:
                anomalies.append(
                    {
                        "type": "SUMMARY_TOO_LONG",
                        "severity": "MEDIUM",
                        "sample": name,
                        "row_index": i,
                        "length": len(summary),
                        "value": summary[:200],
                    }
                )
            if 0 < len(summary.strip()) < 5:
                anomalies.append(
                    {
                        "type": "SUMMARY_TOO_SHORT",
                        "severity": "MEDIUM",
                        "sample": name,
                        "row_index": i,
                        "value": summary,
                    }
                )

            if not (row.get("law_name") or "").strip():
                anomalies.append(
                    {
                        "type": "EMPTY_LAW_NAME",
                        "severity": "HIGH",
                        "sample": name,
                        "row_index": i,
                    }
                )

            penalty = row.get("penalty_summary", "") or ""
            if "확인 필요" in penalty or "부과 가능" in penalty:
                anomalies.append(
                    {
                        "type": "PENALTY_FALLBACK",
                        "severity": "LOW",
                        "sample": name,
                        "row_index": i,
                        "value": penalty,
                    }
                )

        article_counts: Dict[str, List[int]] = {}
        for i, row in enumerate(rules_table):
            key = f"{row.get('law_name', '')}|{row.get('law_article', '')}"
            article_counts.setdefault(key, []).append(i)
        for key, indices in article_counts.items():
            visible = [i for i in indices if not rules_table[i].get("_overflow")]
            if len(visible) > 3:
                anomalies.append(
                    {
                        "type": "ARTICLE_FLOOD",
                        "severity": "MEDIUM",
                        "sample": name,
                        "article": key,
                        "count": len(visible),
                        "row_indices": visible,
                    }
                )

    return anomalies


def build_before_after_report(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    report: List[Dict[str, Any]] = []
    for sample in samples:
        before = sample.get("rules_table_before")
        after = sample["rules_table"]
        if before is None:
            continue
        report.append(
            {
                "sample": sample["name"],
                "before_count": len(before),
                "after_count": len(after),
                "after_visible_count": len([r for r in after if not r.get("_overflow")]),
                "delta": len(before) - len(after),
            }
        )
    return report


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Detect projection anomalies")
    parser.add_argument(
        "--all-samples",
        action="store_true",
        help="Scan all sample_* dirs (default: manifest.json only)",
    )
    args = parser.parse_args()

    samples = load_samples(SAMPLES_ROOT, use_manifest_only=not args.all_samples)
    if not samples:
        print(f"No samples in {SAMPLES_ROOT} — run collect_projection_samples.py first")
        return 1

    anomalies = detect_anomalies(samples)
    before_after = build_before_after_report(samples)

    by_type: Dict[str, int] = {}
    for a in anomalies:
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1

    catalog = {
        "sample_count": len(samples),
        "anomaly_count": len(anomalies),
        "by_type": by_type,
        "anomalies": anomalies,
    }
    catalog_path = SAMPLES_ROOT / "anomaly_catalog.json"
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    report_path = SAMPLES_ROOT / "before_after_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"samples": before_after, "totals": catalog["by_type"]}, f, ensure_ascii=False, indent=2)

    print(json.dumps({"sample_count": len(samples), "anomaly_count": len(anomalies), "by_type": by_type}, ensure_ascii=False, indent=2))
    print(f"Wrote {catalog_path}")
    print(f"Wrote {report_path}")

    high = [a for a in anomalies if a.get("severity") == "HIGH"]
    if high:
        print(f"\nWARN: {len(high)} HIGH severity anomalies remain")
        return 1
    print("\nOK: no HIGH severity anomalies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
