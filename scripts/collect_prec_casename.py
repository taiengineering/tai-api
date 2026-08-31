#!/usr/bin/env python3
"""
scripts/collect_prec_casename.py — 방향 2: 사건명 검색(search=1)으로 추가 수집
================================================================
참조조문 검색에서 0건인 법령을 사건명 형태로 재검색.
법제처 사건명은 띄어쓰기 없이 붙여씁니다.

예: "위험물안전관리법위반", "승강기안전관리법위반"

사용법:
  export INTERNAL_API_SECRET=...
  python3 scripts/collect_prec_casename.py
  python3 scripts/collect_prec_casename.py --dry-run
"""
import os, sys, time, re, argparse, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from services.time import now_kst, serialize_external_utc

LAW_OC = "taieng"
LAW_SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
LAW_DETAIL_URL = "http://www.law.go.kr/DRF/lawService.do"
API_URL = os.environ.get("TAI_API_URL", "https://api.taieng.co.kr")
SECRET = os.environ.get("INTERNAL_API_SECRET", "")

# 사건명 검색어 → master 법령명 매핑
# 사건명은 띄어쓰기 없이 "법령명+위반" 형태
CASENAME_MAP = [
    {
        "search": "중대재해처벌",
        "master_law": "중대재해 처벌 등에 관한 법률",
    },
    {
        "search": "위험물안전관리법위반",
        "master_law": "위험물안전관리법",
    },
    {
        "search": "승강기안전관리법위반",
        "master_law": "승강기 안전관리법",
    },
    {
        "search": "다중이용업소",
        "master_law": "다중이용업소의 안전관리에 관한 특별법",
    },
    {
        "search": "전기안전관리법위반",
        "master_law": "전기안전관리법",
    },
    {
        "search": "화재예방법위반",
        "master_law": "화재의 예방 및 안전관리에 관한 법률",
    },
    {
        "search": "소방시설설치및관리",
        "master_law": "소방시설 설치 및 관리에 관한 법률",
    },
    {
        "search": "시설물의안전및유지관리",
        "master_law": "시설물의 안전 및 유지관리에 관한 특별법",
    },
    {
        "search": "기계설비법위반",
        "master_law": "기계설비법",
    },
    {
        "search": "전기사업법위반",
        "master_law": "전기사업법",
    },
    {
        "search": "전기공사업법위반",
        "master_law": "전기공사업법",
    },
    {
        "search": "주택법위반",
        "master_law": "주택법",
    },
    {
        "search": "건축물관리법위반",
        "master_law": "건축물관리법",
    },
    {
        "search": "재난안전법위반",
        "master_law": "재난 및 안전관리 기본법",
    },
    {
        "search": "파견근로자보호",
        "master_law": "파견근로자 보호 등에 관한 법률",
    },
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


def get_all_rule_ids_for_law(master_law):
    """master에서 해당 법령명의 모든 rule_id"""
    try:
        resp = requests.get(f"{API_URL}/precedents/master-keys",
                           params={"secret": SECRET}, timeout=30)
        keys = resp.json().get("keys", [])
        rule_ids = []
        for k in keys:
            if k["law_name"] == master_law:
                rule_ids.extend(k["rule_ids"])
        return list(set(rule_ids))
    except: return []


def search_prec(query, search_type=1, display=100):
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

    for entry in CASENAME_MAP:
        query = entry["search"]
        master_law = entry["master_law"]
        rule_ids = get_all_rule_ids_for_law(master_law)

        if not rule_ids:
            # master-keys에 없으면 범용 검색으로 폴백
            print(f"\n[{query}] master-keys에 '{master_law}' 없음, 범용 rule_id 사용")
            # 법령명으로 직접 master 검색
            try:
                resp = requests.get(f"{API_URL}/precedents/master-keys",
                                   params={"secret": SECRET}, timeout=30)
                all_keys = resp.json().get("keys", [])
                # master_law가 포함된 법령명 찾기
                for k in all_keys:
                    if master_law in k["law_name"] or k["law_name"] in master_law:
                        rule_ids.extend(k["rule_ids"])
                rule_ids = list(set(rule_ids))
            except: pass
            if not rule_ids:
                print(f"  rule_id도 없음, skip")
                continue

        items, total = search_prec(query, search_type=1)
        print(f"\n[{query}] → {total}건 (매칭 rule {len(rule_ids)}개)")
        total_found += len(items)

        for item in items:
            prec_seq = item.get("판례일련번호")
            case_number = item.get("사건번호")
            if not prec_seq: continue
            if not case_number: case_number = f"PREC-{prec_seq}"
            already = prec_seq in seen
            seen.add(prec_seq)
            if args.dry_run:
                if not already:
                    print(f"  {case_number} | {item.get('법원명','?')}")
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
                payload["keywords"] = [master_law]
                payload["collected_at"] = serialize_external_utc(now_kst())
            ok, action, links = save_matched(payload, rule_ids)
            if ok:
                if not already: total_saved += 1
                total_links += links
        time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"수집 완료")
    print(f"  검색 키워드: {len(CASENAME_MAP)}개")
    print(f"  검색 판례: {total_found}건")
    if not args.dry_run:
        print(f"  저장 판례: {total_saved}건")
        print(f"  rule 연결: {total_links}건")
    else:
        print("  (dry-run)")

if __name__ == "__main__":
    main()
