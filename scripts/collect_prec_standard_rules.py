#!/usr/bin/env python3
"""
scripts/collect_prec_standard_rules.py — 방향 3: 산안기준규칙 등 기준법령 조문별 직접 검색
================================================================
master에서 매칭 안 된 가장 큰 블록:
- 산업안전보건기준에 관한 규칙 (391건)
- 전기설비기술기준 (90건)
- 위험물안전관리법 (117건)

이 법령들은 참조조문(search=3)에서 조문 단위로 직접 검색.

사용법:
  export INTERNAL_API_SECRET=...
  python3 scripts/collect_prec_standard_rules.py
  python3 scripts/collect_prec_standard_rules.py --dry-run
"""
import os, sys, time, re, argparse, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

LAW_OC = "taieng"
LAW_SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
LAW_DETAIL_URL = "http://www.law.go.kr/DRF/lawService.do"
API_URL = os.environ.get("TAI_API_URL", "https://api.taieng.co.kr")
SECRET = os.environ.get("INTERNAL_API_SECRET", "")

# 대상 법령: master에 rule이 많지만 판례 매칭 0인 법령
TARGET_LAWS = [
    "산업안전보건기준에 관한 규칙",
    "전기설비기술기준",
    "위험물안전관리법",
    "승강기 안전관리법",
    "다중이용업소의 안전관리에 관한 특별법",
    "화학물질관리법",
    "고압가스 안전관리법",
    "액화석유가스의 안전관리 및 사업법",
]


def parse_date(raw):
    if not raw: return None
    raw = raw.strip()
    if "." in raw:
        p = raw.split(".")
        if len(p) == 3: return f"{p[0]}-{p[1].zfill(2)}-{p[2].zfill(2)}"
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return None


def get_rule_ids_for_law(law_name):
    """master에서 해당 법령의 조문별 rule_id 매핑"""
    try:
        resp = requests.get(f"{API_URL}/precedents/master-keys",
                           params={"secret": SECRET}, timeout=30)
        keys = resp.json().get("keys", [])
        result = {}
        for k in keys:
            if k["law_name"] == law_name:
                result[k["article_no"]] = k["rule_ids"]
        return result
    except: return {}


def search_prec(query, search_type=3, display=100):
    params = {"OC": LAW_OC, "target": "prec", "type": "XML",
              "query": query, "display": display, "search": search_type}
    try:
        resp = requests.get(LAW_SEARCH_URL, params=params, timeout=20)
        if resp.status_code != 200: return [], 0
        root = ET.fromstring(resp.text)
    except: return [], 0
    total_el = root.find("totalCnt")
    total = int(total_el.text) if total_el is not None and total_el.text else 0
    items = []
    for node in root.iter():
        seq_el = node.find("판례일련번호")
        if seq_el is None: continue
        item = {}
        for f in ["판례일련번호","사건명","사건번호","선고일자","법원명","사건종류명","판결유형"]:
            el = node.find(f)
            item[f] = el.text.strip() if el is not None and el.text else None
        items.append(item)
    return items, total


def fetch_detail(prec_seq):
    params = {"OC": LAW_OC, "target": "prec", "type": "XML", "ID": prec_seq}
    try:
        resp = requests.get(LAW_DETAIL_URL, params=params, timeout=20)
        if resp.status_code != 200: return {}
        root = ET.fromstring(resp.text)
    except: return {}
    d = {}
    for f in ["판시사항","판결요지","참조조문","참조판례","판례내용"]:
        el = root.find(f".//{f}")
        if el is not None and el.text: d[f] = el.text.strip()
    return d


def save_matched(payload, rule_ids):
    try:
        resp = requests.post(f"{API_URL}/precedents/save-matched",
            json={"secret": SECRET, "precedent": payload, "rule_ids": rule_ids}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return True, data.get("action","ok"), data.get("links_created",0)
        return False, resp.text[:100], 0
    except Exception as e:
        return False, str(e)[:100], 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not SECRET and not args.dry_run:
        print("[ERROR] export INTERNAL_API_SECRET=..."); sys.exit(1)

    total_saved = 0
    total_links = 0
    total_found = 0
    seen = set()

    for law_name in TARGET_LAWS:
        print(f"\n{'='*50}")
        print(f"법령: {law_name}")
        rule_map = get_rule_ids_for_law(law_name)
        if not rule_map:
            print(f"  master에 조문 없음, skip")
            continue
        print(f"  master 조문: {len(rule_map)}개")

        # 조문별 검색
        for article_no, rule_ids in sorted(rule_map.items(), key=lambda x: int(x[0])):
            query = f"{law_name} 제{article_no}조"
            items, total = search_prec(query, search_type=3)
            if total > 0:
                print(f"  제{article_no}조 → {total}건 (rule {len(rule_ids)}개)")
            total_found += len(items)

            for item in items:
                prec_seq = item.get("판례일련번호")
                case_number = item.get("사건번호")
                if not prec_seq: continue
                if not case_number:
                    case_number = f"PREC-{prec_seq}"
                already = prec_seq in seen
                seen.add(prec_seq)
                if args.dry_run:
                    if not already:
                        print(f"    {case_number} | {item.get('법원명','?')}")
                    continue
                detail = {} if already else fetch_detail(prec_seq)
                if not already: time.sleep(0.3)
                payload = {
                    "case_number": case_number,
                    "case_name": item.get("사건명"),
                    "court_name": item.get("법원명"),
                    "decision_date": parse_date(item.get("선고일자","")),
                    "case_type": item.get("사건종류명"),
                    "prec_seq": str(prec_seq),
                    "source": "law_go_kr",
                    "source_url": f"https://www.law.go.kr/precInfoP.do?precSeq={prec_seq}",
                    "is_active": True,
                }
                if detail:
                    s = detail.get("판결요지","")
                    if s: payload["summary"] = s[:3000]
                    ft = detail.get("판례내용","")
                    if ft: payload["full_text"] = ft
                    js = detail.get("판시사항","")
                    if js: payload["judicial_summary"] = js[:2000]
                    rl = detail.get("참조조문","")
                    if rl: payload["violation_laws_raw"] = rl
                    payload["keywords"] = [law_name]
                    payload["collected_at"] = datetime.now(timezone.utc).isoformat()
                ok, action, links = save_matched(payload, rule_ids)
                if ok:
                    if not already: total_saved += 1
                    total_links += links
            time.sleep(0.3)

    print(f"\n{'='*50}")
    print(f"수집 완료")
    print(f"  대상 법령: {len(TARGET_LAWS)}개")
    print(f"  검색 판례: {total_found}건")
    if not args.dry_run:
        print(f"  저장 판례: {total_saved}건")
        print(f"  rule 연결: {total_links}건")
    else:
        print("  (dry-run)")

if __name__ == "__main__":
    main()
