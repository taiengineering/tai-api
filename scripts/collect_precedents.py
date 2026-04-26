#!/usr/bin/env python3
"""
scripts/collect_precedents.py — 판례 수집 스크립트
================================================
master DB의 법령명 기준으로 법제처 API에서 판례 수집 → Railway API로 저장.

Mac에서 실행 (법제처 IP 등록 필요).
환경변수: INTERNAL_API_SECRET 1개만.

사용법:
  cd ~/Desktop/tai-engineering/tai-api
  export INTERNAL_API_SECRET=...
  python3 scripts/collect_precedents.py
  python3 scripts/collect_precedents.py --law "산업안전보건법"   # 특정 법령만
  python3 scripts/collect_precedents.py --dry-run              # 저장 안 함
"""
import os
import sys
import json
import time
import re
import argparse
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# ──── 설정 ────
LAW_OC = "taieng"
LAW_SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
LAW_DETAIL_URL = "http://www.law.go.kr/DRF/lawService.do"
API_URL = os.environ.get("TAI_API_URL", "https://api.taieng.co.kr")
INTERNAL_SECRET = os.environ.get("INTERNAL_API_SECRET", "")

# master에서 모법만 추출 (45개). 시행령/시행규칙/NFTC는 모법에 포함
PARENT_LAW_MAP = {
    "산업안전보건법": "산업안전보건법",
    "산업안전보건법 시행령": "산업안전보건법",
    "산업안전보건법 시행규칙": "산업안전보건법",
    "산업안전보건기준에 관한 규칙": "산업안전보건법",
    "중대재해 처벌 등에 관한 법률": "중대재해처벌법",
    "중대재해 처벌 등에 관한 법률 시행령": "중대재해처벌법",
    "위험물안전관리법": "위험물안전관리법",
    "고압가스 안전관리법": "고압가스안전관리법",
    "액화석유가스의 안전관리 및 사업법": "LPG안전관리법",
    "도시가스사업법": "도시가스사업법",
    "화학물질관리법": "화학물질관리법",
    "소방시설 설치 및 관리에 관한 법률": "소방시설법",
    "화재의 예방 및 안전관리에 관한 법률": "화재예방법",
    "승강기 안전관리법": "승강기안전관리법",
    "전기안전관리법": "전기안전관리법",
    "근로기준법": "근로기준법",
    "시설물의 안전 및 유지관리에 관한 특별법": "시설물안전법",
    "다중이용업소의 안전관리에 관한 특별법": "다중이용업소법",
    "소음㈱진동관리법": "소음진동관리법",
    "토양환경보전법": "토양환경보전법",
    "잔류성오염물질 관리법": "잔류성오염물질법",
    "악취방지법": "악취방지법",
    "재난 및 안전관리 기본법": "재난기본법",
    "파견근로자 보호 등에 관한 법률": "파견근로자법",
    "폐기물관리법": "폐기물관리법",
    "대기환경보전법": "대기환경보전법",
    "물환경보전법": "물환경보전법",
    "하수도법": "하수도법",
    "에너지이용 합리화법": "에너지이용합리화법",
    "건축법": "건축법",
    "건축물관리법": "건축물관리법",
    "주택법": "주택법",
    "소방기본법": "소방기본법",
    "소방시설공사업법": "소방시설공사업법",
    "건설산업기본법": "건설산업기본법",
    "건설기술 진흥법": "건설기술진흥법",
    "산업재해보상보험법": "산재보험법",
    "기계설비법": "기계설비법",
    "전기사업법": "전기사업법",
    "전기공사업법": "전기공사업법",
    "수도법": "수도법",
    "주차장법": "주차장법",
}


def parse_date(raw: str) -> str | None:
    """선고일자 변환: '2026.01.29' 또는 '20260129' → '2026-01-29'"""
    if not raw:
        return None
    raw = raw.strip()
    if "." in raw:
        parts = raw.split(".")
        if len(parts) == 3:
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return None


def search_precedents(keyword: str, display: int = 100, page: int = 1) -> tuple:
    """법제처 판례 목록 검색. returns (items, total_count)"""
    params = {
        "OC": LAW_OC,
        "target": "prec",
        "type": "XML",
        "query": keyword,
        "display": display,
        "page": page,
    }
    try:
        resp = requests.get(LAW_SEARCH_URL, params=params, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception as e:
        print(f"  [ERROR] 검색 실패 ({keyword}): {e}")
        return [], 0

    total_el = root.find("totalCnt")
    total = int(total_el.text) if total_el is not None and total_el.text else 0

    items = []
    for node in root.iter():
        seq_el = node.find("판례일련번호")
        if seq_el is None:
            continue
        item = {}
        for field in ["판례일련번호", "사건명", "사건번호", "선고일자",
                      "법원명", "사건종류명", "판결유형", "선고"]:
            el = node.find(field)
            item[field] = el.text.strip() if el is not None and el.text else None
        items.append(item)

    return items, total


def fetch_detail(prec_seq: str) -> dict:
    """판례 상세 조회"""
    params = {
        "OC": LAW_OC,
        "target": "prec",
        "type": "XML",
        "ID": prec_seq,
    }
    try:
        resp = requests.get(LAW_DETAIL_URL, params=params, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception as e:
        print(f"  [ERROR] 상세 조회 실패 ({prec_seq}): {e}")
        return {}

    detail = {}
    for field in ["판시사항", "판결요지", "참조조문", "참조판례", "판례내용"]:
        el = root.find(f".//{field}")
        if el is not None and el.text:
            detail[field] = el.text.strip()
    return detail


def build_save_payload(item: dict, detail: dict, search_law: str) -> dict:
    """법제처 응답 → DB 저장용 payload 변환"""
    prec_seq = item.get("판례일련번호", "")
    return {
        "case_number": item.get("사건번호"),
        "case_name": item.get("사건명"),
        "court_name": item.get("법원명"),
        "decision_date": parse_date(item.get("선고일자", "")),
        "case_type": item.get("사건종류명"),
        "prec_seq": prec_seq,
        "source": "law_go_kr",
        "source_url": f"https://www.law.go.kr/precInfoP.do?precSeq={prec_seq}" if prec_seq else None,
        "summary": (detail.get("판결요지") or "")[:3000],
        "full_text": detail.get("판례내용"),
        "judicial_summary": (detail.get("판시사항") or "")[:2000],
        "violation_laws_raw": detail.get("참조조문"),
        "keywords": [search_law],
        "collected_at": datetime.utcnow().isoformat(),
        "is_active": True,
    }


def save_to_api(payload: dict) -> bool:
    """단건 Railway API로 저장"""
    try:
        resp = requests.post(
            f"{API_URL}/precedents/save",
            json={"secret": INTERNAL_SECRET, "precedent": payload},
            timeout=15,
        )
        if resp.status_code == 200:
            return True
        else:
            print(f"  [WARN] 저장 실패 ({payload.get('case_number')}): {resp.status_code} {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"  [ERROR] API 호출 실패: {e}")
        return False


def get_master_law_names() -> list:
    """마스터 DB에서 고유 법령명 조회 → 모법 그룹핑"""
    try:
        resp = requests.get(
            f"{API_URL}/law-rule-generator/laws",
            params={"page_size": 100},
            timeout=15,
        )
        data = resp.json()
        laws = data.get("data", {}).get("items", [])
        names = set()
        for law in laws:
            name = law.get("law_name", "")
            # 모법으로 그룹핑
            parent = PARENT_LAW_MAP.get(name)
            if parent:
                names.add(parent)
            elif not any(kw in name for kw in ["시행령", "시행규칙", "NFTC", "NFPC", "고시", "기준", "기술기준", "통합고시"]):
                names.add(name)
        return sorted(names)
    except Exception as e:
        print(f"[ERROR] master 법령 조회 실패: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="TAI 판례 수집")
    parser.add_argument("--law", default="", help="특정 법령명만 검색")
    parser.add_argument("--dry-run", action="store_true", help="검색만 하고 저장 안 함")
    parser.add_argument("--max-per-law", type=int, default=100, help="법령당 최대 수집 건수")
    args = parser.parse_args()

    if not INTERNAL_SECRET and not args.dry_run:
        print("[ERROR] INTERNAL_API_SECRET 환경변수 필요")
        print("  export INTERNAL_API_SECRET=...")
        sys.exit(1)

    # 1. 검색 대상 법령 결정
    if args.law:
        law_names = [args.law]
    else:
        print("[1/4] master DB에서 모법 목록 조회...")
        law_names = get_master_law_names()
        print(f"  모법 {len(law_names)}개 확인")

    # 2. 법령별 판례 검색
    total_found = 0
    total_saved = 0
    total_skipped = 0
    errors = []

    print(f"\n[2/4] 판례 검색 시작 ({len(law_names)}개 법령)")
    for i, law_name in enumerate(law_names, 1):
        print(f"\n--- [{i}/{len(law_names)}] {law_name} ---")

        items, total = search_precedents(law_name, display=args.max_per_law)
        print(f"  검색 결과: {total}건 (반환 {len(items)}건)")
        total_found += total

        if not items:
            continue

        # 3. 각 판례 상세 조회 + 저장
        for j, item in enumerate(items, 1):
            prec_seq = item.get("판례일련번호")
            case_no = item.get("사건번호", "?")

            # 상세 조회
            detail = fetch_detail(prec_seq) if prec_seq else {}
            time.sleep(0.5)  # API 예의

            # payload 구성
            payload = build_save_payload(item, detail, law_name)

            if args.dry_run:
                has_summary = bool(detail.get("판결요지"))
                has_ref = bool(detail.get("참조조문"))
                print(f"  [{j}] {case_no} | {item.get('법원명', '?')} | "
                      f"요지={'O' if has_summary else 'X'} 참조조문={'O' if has_ref else 'X'}")
            else:
                ok = save_to_api(payload)
                if ok:
                    total_saved += 1
                    print(f"  [{j}] ✅ {case_no}")
                else:
                    total_skipped += 1

        time.sleep(1)  # 법령 간 대기

    # 4. 결과 요약
    print(f"\n{'='*50}")
    print(f"[4/4] 수집 완료")
    print(f"  검색 법령: {len(law_names)}개")
    print(f"  검색 판례: {total_found}건")
    if not args.dry_run:
        print(f"  저장 성공: {total_saved}건")
        print(f"  저장 실패: {total_skipped}건")
    else:
        print(f"  (dry-run 모드 — 저장 안 함)")


if __name__ == "__main__":
    main()
