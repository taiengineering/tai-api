#!/usr/bin/env python3
"""
scripts/collect_precedents_matched.py — master 기반 판례 수집
================================================================
master_building_legal_rules의 (법령명 + 조문번호)를 검색 키로
법제처 판례 API에서 참조조문 검색 → 결과 즉시 rule_id 연결.

수집 = 매칭. 매칭 안 되는 판례는 저장 안 함.

사용법:
  cd ~/Desktop/tai-engineering/tai-api
  export INTERNAL_API_SECRET=...
  python3 scripts/collect_precedents_matched.py --dry-run
  python3 scripts/collect_precedents_matched.py
  python3 scripts/collect_precedents_matched.py --limit 10
"""
import os
import sys
import time
import re
import argparse
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from services.time import now_kst, serialize_external_utc

LAW_OC = "taieng"
LAW_SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
LAW_DETAIL_URL = "http://www.law.go.kr/DRF/lawService.do"
API_URL = os.environ.get("TAI_API_URL", "https://api.taieng.co.kr")
INTERNAL_SECRET = os.environ.get("INTERNAL_API_SECRET", "")


def parse_date(raw):
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


def get_master_keys():
    try:
        resp = requests.get(
            f"{API_URL}/precedents/master-keys",
            params={"secret": INTERNAL_SECRET},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("keys", [])
    except Exception as e:
        print(f"[ERROR] master-keys 조회 실패: {e}")
        return []


def search_by_ref(query, display=100):
    params = {
        "OC": LAW_OC, "target": "prec", "type": "XML",
        "query": query, "display": display, "search": 3,
    }
    try:
        resp = requests.get(LAW_SEARCH_URL, params=params, timeout=20)
        if resp.status_code != 200:
            return [], 0
        root = ET.fromstring(resp.text)
    except Exception as e:
        print(f"  [ERROR] 검색 실패: {e}")
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
                      "법원명", "사건종류명", "판결유형"]:
            el = node.find(field)
            item[field] = el.text.strip() if el is not None and el.text else None
        items.append(item)
    return items, total


def fetch_detail(prec_seq):
    params = {"OC": LAW_OC, "target": "prec", "type": "XML", "ID": prec_seq}
    try:
        resp = requests.get(LAW_DETAIL_URL, params=params, timeout=20)
        if resp.status_code != 200:
            return {}
        root = ET.fromstring(resp.text)
    except Exception:
        return {}
    detail = {}
    for field in ["판시사항", "판결요지", "참조조문", "참조판례", "판례내용"]:
        el = root.find(f".//{field}")
        if el is not None and el.text:
            detail[field] = el.text.strip()
    return detail


def save_matched(payload, rule_ids):
    try:
        resp = requests.post(
            f"{API_URL}/precedents/save-matched",
            json={"secret": INTERNAL_SECRET, "precedent": payload, "rule_ids": rule_ids},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            return True, data.get("action", "ok"), data.get("links_created", 0)
        else:
            return False, resp.text[:100], 0
    except Exception as e:
        return False, str(e)[:100], 0


def main():
    parser = argparse.ArgumentParser(description="master 기반 판례 수집")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if not INTERNAL_SECRET:
        print("[ERROR] export INTERNAL_API_SECRET=... 필요")
        sys.exit(1)

    print("[1/3] master 검색 키 조회...")
    keys = get_master_keys()
    if not keys:
        print("[ERROR] 검색 키 없음")
        return
    if args.limit:
        keys = keys[:args.limit]
    print(f"  검색 키: {len(keys)}개")

    print(f"\n[2/3] 법제처 참조조문 검색 시작")
    total_found = 0
    total_saved = 0
    total_links = 0
    total_skipped = 0
    seen_seqs = set()

    for i, key in enumerate(keys, 1):
        query = key["search_query"]
        rule_ids = key["rule_ids"]
        rule_count = key["rule_count"]

        items, total = search_by_ref(query)
        if total > 0:
            print(f"[{i}/{len(keys)}] {query} → {total}건 (rule {rule_count}개)")
        total_found += len(items)

        if not items:
            continue

        for item in items:
            prec_seq = item.get("판례일련번호")
            case_number = item.get("사건번호")

            # prec_seq 또는 case_number 없으면 skip
            if not prec_seq:
                continue
            if not case_number:
                # case_number가 없으면 사건명에서 추출 시도, 안 되면 prec_seq 사용
                case_name = item.get("사건명", "")
                m = re.search(r"(\d{2,4}[가-힣]+\d+)", case_name)
                case_number = m.group(1) if m else f"PREC-{prec_seq}"

            already_saved = prec_seq in seen_seqs
            seen_seqs.add(prec_seq)

            if args.dry_run:
                if not already_saved:
                    print(f"  {case_number} | {item.get('법원명', '?')} | → rule {rule_count}개")
                continue

            detail = {}
            if not already_saved:
                detail = fetch_detail(prec_seq)
                time.sleep(0.3)

            payload = {
                "case_number": case_number,
                "case_name": item.get("사건명"),
                "court_name": item.get("법원명"),
                "decision_date": parse_date(item.get("선고일자", "")),
                "case_type": item.get("사건종류명"),
                "prec_seq": str(prec_seq),
                "source": "law_go_kr",
                "source_url": f"https://www.law.go.kr/precInfoP.do?precSeq={prec_seq}",
                "is_active": True,
            }

            # 상세 데이터 (새 판례만)
            if detail:
                summary = detail.get("판결요지", "")
                if summary:
                    payload["summary"] = summary[:3000]
                full_text = detail.get("판례내용", "")
                if full_text:
                    payload["full_text"] = full_text
                judicial = detail.get("판시사항", "")
                if judicial:
                    payload["judicial_summary"] = judicial[:2000]
                ref_laws = detail.get("참조조문", "")
                if ref_laws:
                    payload["violation_laws_raw"] = ref_laws
                payload["keywords"] = [key["law_name"]]
                payload["collected_at"] = serialize_external_utc(now_kst())

            ok, action, links = save_matched(payload, rule_ids)
            if ok:
                if not already_saved:
                    total_saved += 1
                total_links += links
            else:
                total_skipped += 1
                if not already_saved:
                    print(f"  [WARN] {case_number}: {action}")

        time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"[3/3] 수집 완료")
    print(f"  검색 키: {len(keys)}개")
    print(f"  검색 판례: {total_found}건")
    if not args.dry_run:
        print(f"  저장 판례: {total_saved}건")
        print(f"  rule 연결: {total_links}건")
        print(f"  skip/실패: {total_skipped}건")
    else:
        print(f"  (dry-run 모드)")


if __name__ == "__main__":
    main()
