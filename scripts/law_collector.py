#!/usr/bin/env python3
"""
TAI 법령 수집 스크립트

사용법:
    python scripts/law_collector.py --sector BUILDING
    python scripts/law_collector.py --sector MANUFACTURING
    python scripts/law_collector.py --sector CONSTRUCTION
    python scripts/law_collector.py --sector ALL

흐름:
    1. 법제처 Open API → 법령 조문 원문 수집
    2. OpenAI GPT-4o → 구조화 JSON 룰로 변환
    3. output/ 폴더에 JSON + CSV 저장
    4. 완료 후 파일을 백엔드 창에 전달마

필요 패키지:
    pip install requests openai python-dotenv
"""

import os
import sys
import json
import time
import csv
import argparse
import requests
from pathlib import Path
from datetime import date

try:
    from openai import OpenAI
except ImportError:
    print("[ERROR] openai 패키지 필요: pip install openai")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ══════════════════════════════
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LAW_OC = "taieng"  # 법제처 Open API 아이디 (인증키 불필요)
OUTPUT_DIR = Path("scripts/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════
# 수집 대상 정의
# MST: 법령 일련번호 (법제처 API에서 확인한 값)
# ══════════════════════════════
COLLECTION_TARGETS = {
    "BUILDING": [
        {
            "mst": "276853",
            "law_name": "화재의 예방 및 안전관리에 관한 법률",
            "articles": ["24", "25", "26"],  # 소방안전관리자 선임
            "sector": "BUILDING",
            "stage": 1,
            "rule_prefix": "FIRE-BLDG",
        },
        {
            "mst": "276853",
            "law_name": "화재의 예방 및 안전관리에 관한 법률 시행령",
            "articles": ["22", "23", "24"],
            "sector": "BUILDING",
            "stage": 1,
            "rule_prefix": "FIRE-BLDG",
        },
        {
            "mst": "302927",  # 전기안전관리법
            "law_name": "전기안전관리법",
            "articles": ["22", "23", "24"],
            "sector": "BUILDING",
            "stage": 1,
            "rule_prefix": "ELEC-BLDG",
        },
    ],
    "MANUFACTURING": [
        {
            "mst": "276853",  # 산업안전보건법 (관련 MST 재확인 필요)
            "law_name": "산업안전보건법",
            "articles": ["17", "18", "19"],  # 안전관리자/보건관리자
            "sector": "MANUFACTURING",
            "stage": 1,
            "rule_prefix": "OSH-MFG",
        },
        {
            "mst": "276853",
            "law_name": "산업안전보건법 시행령",
            "articles": ["16", "17", "18", "19", "20"],  # 별표3 기준
            "sector": "MANUFACTURING",
            "stage": 1,
            "rule_prefix": "OSH-MFG",
        },
        {
            "mst": "276853",
            "law_name": "위험물안전관리법",
            "articles": ["15", "16"],
            "sector": "MANUFACTURING",
            "stage": 1,
            "rule_prefix": "HAZMAT-MFG",
        },
        {
            "mst": "276853",
            "law_name": "고압가스안전관리법",
            "articles": ["15"],
            "sector": "MANUFACTURING",
            "stage": 1,
            "rule_prefix": "HPGAS-MFG",
        },
    ],
    "CONSTRUCTION": [
        {
            "mst": "276853",
            "law_name": "산업안전보건법",
            "articles": ["42", "67", "72", "73"],  # 유해위험방지계획서/안전관리비
            "sector": "CONSTRUCTION",
            "stage": 1,
            "rule_prefix": "CONST",
        },
        {
            "mst": "276853",
            "law_name": "산업안전보건법 시행령",
            "articles": ["52", "53"],  # 별표5 건설업 안전관리자
            "sector": "CONSTRUCTION",
            "stage": 1,
            "rule_prefix": "CONST",
        },
    ],
    "EQUIPMENT": [
        {
            "mst": "276853",
            "law_name": "산업안전보건법",
            "articles": ["93", "94", "95"],  # 유해위험기계기구
            "sector": "MANUFACTURING",
            "stage": 3,
            "rule_prefix": "EQUIP",
        },
    ],
}

SYSTEM_PROMPT = """당신은 TAI Engineering의 산업안전 법령 데이터 변환 전문 AI입니다.

## 역할
공공 API에서 수집한 법령 원문을 분석하여
TAI DB의 master_building_legal_rules 테이블에 적재할 구조화된 JSON 룰로 변환합니다.

## 핵심 원칙
1. 반드시 입력된 법령 원문 텍스트만 기반으로 변환 (기억 사용 금지)
2. 법령 조문번호 반드시 포함 (예: 산안법 제17조 제1항)
3. 수치 기준 없이 성립하는 룰는 threshold 항목에 null 입력
4. 출력은 순수 JSON 배열만 (코드블록/설명/서문 일체 금지)
5. 원문에 없는 내용 절대 추가 안 함
6. 처볈 조항은 원문에 명시된 경우만 포함

## 출력 JSON 형식
[
  {
    "rule_id": "{rule_prefix}-NNN",
    "sector": "{sector}",
    "stage": {stage},
    "rule_name": "판정 룰 이름",
    "rule_type": "APPOINTMENT|OBLIGATION|INSPECTION|REPORT|APPROVAL",
    "law_name": "실제 법령명",
    "law_article": "제 X조 제 Y항",
    "condition_field": "해당하는 입력필드명 또는 null",
    "condition_operator": ">= | <= | == | IN | NOT_IN | ==true 또는 null",
    "condition_value": "값 또는 null",
    "condition_unit": "단위 또는 null",
    "threshold_field": "두번째 조건필드 또는 null",
    "threshold_operator": "두번째 연산자 또는 null",
    "threshold_value": "두번째 값 또는 null",
    "threshold_unit": "두번째 단위 또는 null",
    "obligation": "해야 할 의무 요약",
    "qualification": "자격 요건 또는 null",
    "penalty": "위반 시 결과 또는 null"
  }
]

## 섹터별 코드 참조
- BUILDING: condition_field 예시 — building_use_category, gross_floor_area, above_ground_floors, worker_count, electric_capacity_kw
- MANUFACTURING: condition_field 예시 — ksic_lv1_code, worker_count, has_hazardous_material, has_high_pressure_gas, has_chemical_substance
- CONSTRUCTION: condition_field 예시 — contract_amount, worker_count, construction_type
"""


def fetch_law_article(mst: str, article_no: str) -> str:
    """법제처 Open API로 특정 조문 원문 가져오기"""
    url = f"https://www.law.go.kr/DRF/lawService.do"
    params = {
        "OC": LAW_OC,
        "target": "law",
        "MST": mst,
        "type": "JSON",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # 조문 데이터 파싱
        law_data = data.get("법령", {})
        articles = law_data.get("조문", {}).get("조문단위", [])
        if isinstance(articles, dict):
            articles = [articles]
        result_texts = []
        for art in articles:
            art_no = art.get("조문번호", "")
            if str(art_no).lstrip("0") == str(article_no).lstrip("0"):
                title = art.get("조문제목", "")
                content_list = art.get("조문내용", [])
                if isinstance(content_list, dict):
                    content_list = [content_list]
                texts = [f"제{art_no}조 {title}"]
                for c in content_list:
                    texts.append(c.get("조문내용텍스트", "") if isinstance(c, dict) else str(c))
                result_texts.append("\n".join(texts))
        return "\n\n".join(result_texts) if result_texts else ""
    except Exception as e:
        print(f"  [WARN] 조문 수집 실패 (MST={mst}, 조문={article_no}): {e}")
        return ""


def search_law_mst(law_name: str) -> str:
    """법령명으로 MST 조회"""
    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {"OC": LAW_OC, "target": "law", "type": "JSON", "query": law_name, "display": 1}
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        laws = data.get("LawSearch", {}).get("law", [])
        if isinstance(laws, dict):
            laws = [laws]
        if laws:
            return laws[0].get("법령일련번호", "")
    except Exception as e:
        print(f"  [WARN] MST 조회 실패 ({law_name}): {e}")
    return ""


def convert_to_rules(
    raw_text: str, target: dict, rule_counter: int, client: OpenAI
) -> list:
    """원문 텍스트를 GPT로 JSON 룰로 변환"""
    if not raw_text.strip():
        return []

    user_msg = f"""아래는 [{target['law_name']}] 원문입니다.
---원문 시작---
{raw_text}
---원문 끝---

위 원문을 분석하여 [{target['sector']}] 섹터 단계 {target['stage']}의
판정 룰를 JSON으로 변환하세요.

rule_id 형식: {target['rule_prefix']}-{rule_counter:03d} 부터 순차 부여
JSON 배열만 출력. 설명/서문 없이."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=4000,
        )
        content = resp.choices[0].message.content.strip()
        # JSON 마크늤다운 제거
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("```", 1)[0]
        rules = json.loads(content)
        if isinstance(rules, dict):
            rules = [rules]
        return rules
    except Exception as e:
        print(f"  [WARN] GPT 변환 실패: {e}")
        return []


def save_results(rules: list, sector: str):
    """결과 JSON + CSV 저장"""
    today = date.today().strftime("%Y%m%d")

    # JSON 저장
    json_path = OUTPUT_DIR / f"rules_{sector.lower()}_{today}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    print(f"  [SAVED] JSON: {json_path} ({len(rules)}개 룰)")

    # CSV 저장 (마스터 테이블 컬럼 매핑)
    csv_path = OUTPUT_DIR / f"rules_{sector.lower()}_{today}.csv"
    fieldnames = [
        "rule_id", "sector", "stage", "rule_name", "rule_type",
        "law_name", "law_article",
        "condition_field", "condition_operator", "condition_value", "condition_unit",
        "threshold_field", "threshold_operator", "threshold_value", "threshold_unit",
        "obligation", "qualification", "penalty",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rules)
    print(f"  [SAVED] CSV: {csv_path}")
    return json_path, csv_path


def collect_sector(sector: str, client: OpenAI):
    """섹터 수집 실행"""
    targets = COLLECTION_TARGETS.get(sector, [])
    if not targets:
        print(f"[ERROR] 알 수 없는 sector: {sector}")
        return

    all_rules = []
    rule_counter = 1

    print(f"\n[START] {sector} 섹터 수집 시작")
    print(f"  대상 법령: {len(targets)}개")

    for target in targets:
        law_name = target["law_name"]
        mst = target["mst"]

        # MST 자동 조회 (mst가 placeholder인 경우)
        if not mst or mst == "276853":
            print(f"  → MST 조회 중: {law_name}")
            mst = search_law_mst(law_name)
            if mst:
                print(f"    MST 확인: {mst}")
            else:
                print(f"    [SKIP] MST 조회 실패")
                continue
            time.sleep(0.5)

        for article_no in target["articles"]:
            print(f"  → {law_name} 제{article_no}조 원문 수집...")
            raw_text = fetch_law_article(mst, article_no)

            if not raw_text:
                print(f"    [SKIP] 원문 없음")
                time.sleep(0.5)
                continue

            print(f"    원문 수집됨 ({len(raw_text)}자) → GPT 변환 중...")
            rules = convert_to_rules(raw_text, target, rule_counter, client)
            all_rules.extend(rules)
            rule_counter += len(rules) + 1
            print(f"    {len(rules)}개 룰 생성")
            time.sleep(1)  # API 레이트 제한

    print(f"\n[DONE] {sector}: 총 {len(all_rules)}개 룰 수집")
    if all_rules:
        save_results(all_rules, sector)
    return all_rules


def main():
    parser = argparse.ArgumentParser(description="TAI 법령 수집 스크립트")
    parser.add_argument(
        "--sector",
        choices=["BUILDING", "MANUFACTURING", "CONSTRUCTION", "EQUIPMENT", "ALL"],
        default="BUILDING",
        help="수집할 섹터 (default: BUILDING)",
    )
    args = parser.parse_args()

    if not OPENAI_API_KEY:
        print("[ERROR] OPENAI_API_KEY 환경변수 필요")
        print("  export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    client = OpenAI(api_key=OPENAI_API_KEY)

    if args.sector == "ALL":
        sectors = ["BUILDING", "MANUFACTURING", "CONSTRUCTION", "EQUIPMENT"]
    else:
        sectors = [args.sector]

    total_rules = []
    for sector in sectors:
        rules = collect_sector(sector, client)
        if rules:
            total_rules.extend(rules)

    print(f"\n[COMPLETE] 전체 {len(total_rules)}개 룰 수집 완료")
    print(f"[OUTPUT]  scripts/output/ 폴더 확인")
    print(f"[NEXT]    수집된 CSV를 백엔드 창에 전달하여 DB 적재")


if __name__ == "__main__":
    main()
