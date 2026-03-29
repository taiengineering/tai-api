#!/usr/bin/env python3
"""
TAI 법령 룰 DB 적재 스크립트

사용법:
    python scripts/law_db_insert.py --file scripts/output/rules_building_20260329.json
    python scripts/law_db_insert.py --file scripts/output/rules_manufacturing_20260329.json
    python scripts/law_db_insert.py --all   # output/ 폴더 전체

주의:
    - 중복 rule_id 는 SKIP (기존 데이터 보호)
    - DB 연결: SUPABASE_URL + SUPABASE_KEY 환경변수
"""

import os
import sys
import json
import argparse
from pathlib import Path

try:
    from supabase import create_client
except ImportError:
    print("[ERROR] supabase 패키지 필요: pip install supabase")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# JSON 키 → DB 컴럼 매핑
FIELD_MAP = {
    "rule_id":           "rule_code",
    "rule_name":         "rule_name",
    "rule_type":         "rule_type",
    "law_name":          "law_name",
    "law_article":       "law_article",
    "condition_field":   "condition_1_field",
    "condition_operator":"condition_1_operator",
    "condition_value":   "condition_1_value",
    "condition_unit":    "condition_1_unit",
    "threshold_field":   "condition_2_field",
    "threshold_operator":"condition_2_operator",
    "threshold_value":   "condition_2_value",
    "threshold_unit":    "condition_2_unit",
    "sector":            "sector",
    "stage":             "diagnosis_stage",
    "obligation":        "obligation_summary",
    "penalty":           "penalty_summary",
}


def load_rules(file_path: str) -> list:
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def map_rule(rule: dict) -> dict:
    """JSON 키를 DB 컴럼명으로 변환"""
    row = {}
    for json_key, db_col in FIELD_MAP.items():
        val = rule.get(json_key)
        if val is not None:
            row[db_col] = val
    row["is_active"] = True
    return row


def insert_rules(rules: list, supabase):
    inserted = 0
    skipped = 0
    errors = 0

    for rule in rules:
        row = map_rule(rule)
        rule_code = row.get("rule_code", "")

        if not rule_code:
            print(f"  [SKIP] rule_code 없음: {rule}")
            skipped += 1
            continue

        # 중복 체크
        existing = supabase.table("master_building_legal_rules").select("id") \
            .eq("rule_code", rule_code).execute()
        if existing.data:
            print(f"  [SKIP] 중복: {rule_code}")
            skipped += 1
            continue

        try:
            supabase.table("master_building_legal_rules").insert(row).execute()
            print(f"  [OK]   삽입: {rule_code} | {row.get('rule_name', '')[:30]}")
            inserted += 1
        except Exception as e:
            print(f"  [ERR]  삽입 실패 {rule_code}: {e}")
            errors += 1

    return inserted, skipped, errors


def main():
    parser = argparse.ArgumentParser(description="TAI 법령 룰 DB 적재")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="적재할 JSON 파일 경로")
    group.add_argument("--all", action="store_true", help="output/ 전체 적재")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERROR] SUPABASE_URL 및 SUPABASE_KEY 환경변수 필요")
        sys.exit(1)

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    files = []
    if args.all:
        files = list(Path("scripts/output").glob("rules_*.json"))
        print(f"[INFO] {len(files)}개 JSON 파일 발견")
    else:
        files = [Path(args.file)]

    total_inserted = total_skipped = total_errors = 0

    for f in files:
        print(f"\n[FILE] {f.name}")
        rules = load_rules(str(f))
        print(f"  룰 수: {len(rules)}개")
        ins, skip, err = insert_rules(rules, supabase)
        total_inserted += ins
        total_skipped += skip
        total_errors += err

    print(f"\n[COMPLETE]")
    print(f"  삽입: {total_inserted}개")
    print(f"  스킵: {total_skipped}개")
    print(f"  오류: {total_errors}개")


if __name__ == "__main__":
    main()
