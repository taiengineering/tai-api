#!/usr/bin/env python3
"""
scripts/migrate_result_data_v2026_04.py

BE-06: factory_diagnosis_results 백필 스크립트

동작:
  1. 현재 'legacy' 버전인 레코드에 업그레이드 가능한 코드를 수동 매핑
  2. 신규 INSERT 시에는 DiagnosisResultV202604 모델로 검증 후 저장

이 스크립트는 자동 실행하지 않는 참조/수동 실행용입니다.
실제 데이터 수정은 Supabase MCP나 직접 SQL로 처리하세요.

진단 엔진 v2026.04 전환은 legal_engine.py개선 후 별도 커밋 예정.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any

# ── 레거시 코어 키 매핑하여 v2026.04 형식으로 변환 ──────────────────────────

RISK_LEVEL_DEFAULT = "MEDIUM"


def _severity_from_counts(crit: int, high: int, med: int, low: int) -> str:
    if crit > 0: return "CRITICAL"
    if high > 0: return "HIGH"
    if med  > 0: return "MEDIUM"
    return "LOW"


def _map_obligation(raw: dict, idx: int) -> dict:
    """legacy obligation dict → v2026.04 obligation"""
    risk = (
        raw.get("risk_level") or
        raw.get("priority") or
        RISK_LEVEL_DEFAULT
    ).upper()
    if risk not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        risk = RISK_LEVEL_DEFAULT

    penalty_krw = None
    if raw.get("penalty_amount"):
        try: penalty_krw = int(raw["penalty_amount"])
        except (TypeError, ValueError): pass

    return {
        "id":       raw.get("rule_id") or raw.get("id") or f"OB-{idx:04d}",
        "law_ref":  raw.get("law_name") or raw.get("law_ref"),
        "title":    raw.get("obligation_summary") or raw.get("title") or raw.get("name") or "",
        "due":      None,
        "penalty":  {"krw": penalty_krw, "criminal": None, "type": None},
        "risk_level": risk,
        "is_retroactive": None,
        "evidence":  [],
        "action_url": None,
    }


def _map_warning(raw: Any) -> dict | None:
    """legacy warning item → v2026.04 warning"""
    if isinstance(raw, str):
        return {"code": "LEGACY", "message": raw, "level": "INFO"}
    if isinstance(raw, dict):
        return {
            "code":    raw.get("code") or "LEGACY",
            "message": raw.get("message") or raw.get("text") or str(raw),
            "level":   (raw.get("level") or raw.get("severity") or "INFO").upper(),
        }
    return None


def upgrade_to_v202604(record: dict) -> dict:
    """
    legacy result_data 하나를 v2026.04 형식으로 변환.

    리턴: 새 result_data dict (schema_version='2026.04' 포함)
    """
    if record.get("schema_version") == "2026.04":
        return record  # 이미 업그레이드됨

    sector = (
        record.get("sector") or
        record.get("sector_groups", [""])[0] if isinstance(record.get("sector_groups"), list) else ""
    ) or "BUILDING"

    # 감지 수학
    diagnosis_stage = record.get("step") or record.get("stage") or 1
    tier = (
        record.get("tier") or
        ("PAID" if (diagnosis_stage or 1) >= 2 else "FREE")
    )

    # obligations 수집 (여러 legacy 키 통합)
    legacy_obls: list[dict] = []
    for src_key in (
        "obligations", "key_obligations",
        "inspection_required", "action_required",
        "appointment_required", "report_required",
    ):
        raw_list = record.get(src_key) or []
        if isinstance(raw_list, list):
            for item in raw_list:
                if isinstance(item, dict):
                    legacy_obls.append(item)

    obligations = [_map_obligation(o, i) for i, o in enumerate(legacy_obls)]

    # risk_summary 보정
    risk_raw = record.get("risk_summary") or {}
    risk_summary = {
        "critical": int(risk_raw.get("critical") or risk_raw.get("CRITICAL") or 0),
        "high":     int(risk_raw.get("high") or risk_raw.get("HIGH") or 0),
        "medium":   int(risk_raw.get("medium") or risk_raw.get("MEDIUM") or 0),
        "low":      int(risk_raw.get("low") or risk_raw.get("LOW") or 0),
    }

    # warnings 통합 (쿠 4개의 키 병합)
    raw_warnings: list = []
    for w_key in ("warnings", "urgent_action_items", "construction_specific_tips", "edge_case_warning"):
        items = record.get(w_key) or []
        if isinstance(items, list):
            raw_warnings.extend(items)
    warnings = [w for item in raw_warnings if (w := _map_warning(item)) is not None]

    # headline
    headline_msg = record.get("headline_message") or (
        (record.get("summary") or {}).get("headline") if isinstance(record.get("summary"), dict) else None
    )
    crit, high, med, low = (
        risk_summary["critical"], risk_summary["high"],
        risk_summary["medium"], risk_summary["low"],
    )
    headline = {
        "summary": headline_msg or f"적용된 의무 {len(obligations)}건 발견",
        "severity": _severity_from_counts(crit, high, med, low),
    }

    rule_total = (
        record.get("rule_count_total") or
        record.get("total_rules_checked") or
        record.get("applicable_count") or
        record.get("rule_count") or
        len(obligations)
    )

    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "schema_version":    "2026.04",
        "tier":              tier,
        "sector":            sector,
        "generated_at":      record.get("evaluated_at") or now_iso,
        "valid_until":       None,
        "headline":          headline,
        "applicable_laws":   record.get("applicable_laws") or [],
        "obligations":       obligations,
        "risk_summary":      risk_summary,
        "warnings":          warnings,
        "inspection_schedule": None,
        "exposure":          None,
        "next_actions":      [],
        "roi":               None,
        "rule_count_total":  int(rule_total or 0),
        "rule_count_shown":  len(obligations),
        # 레거시 키 보존 (엔진 청욨이렬, legal_engine개선 시 제거)
        "_legacy_keys": list(record.keys()),
    }


if __name__ == "__main__":
    # 로컈 단위테스트
    legacy_sample = {
        "step": 1, "sector": "BUILDING", "tier": "FREE",
        "evaluated_at": "2026-04-16T00:00:00+00:00",
        "applicable_count": 34,
        "obligations": [
            {"rule_id": "B001", "obligation_summary": "소방시설 점검", "risk_level": "HIGH",
             "law_name": "소방시설 설치유지 관리법"},
        ],
        "risk_summary": {"high": 1, "medium": 0, "low": 0, "critical": 0},
        "warnings": ["의용쉽 3년 경과 다가옴"],
    }
    upgraded = upgrade_to_v202604(legacy_sample)
    print(json.dumps(upgraded, ensure_ascii=False, indent=2))
    print(f"\n✔ schema_version: {upgraded['schema_version']}")
    print(f"✔ obligations: {len(upgraded['obligations'])}건")
    print(f"✔ warnings merged: {len(upgraded['warnings'])}건")
