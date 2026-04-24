#!/usr/bin/env python3
"""
TAI 전체 법령 auto-parse 로컬 실행 스크립트
============================================
사용법:
  export INTERNAL_API_SECRET='your-secret'
  python3 scripts/auto_parse_all.py

  # 백그라운드 실행
  nohup python3 scripts/auto_parse_all.py > parse_log.txt 2>&1 &
"""
import os, sys, json, time, requests
from datetime import datetime

API_URL = os.environ.get("TAI_API_URL", "https://api.taieng.co.kr")
SECRET = os.environ.get("INTERNAL_API_SECRET", "")
if not SECRET:
    print("export INTERNAL_API_SECRET='...' 필요"); sys.exit(1)

BASE = f"{API_URL}/law-rule-generator"
MAX_ARTICLES, THRESHOLD, DELAY = 80, 80, 1.5

def get_unparsed_laws():
    print("미파싱 법령 조회...")
    laws, page = [], 1
    while True:
        r = requests.get(f"{BASE}/laws", params={"page": page, "page_size": 100}, timeout=30)
        items = r.json().get("data", {}).get("items", [])
        if not items: break
        for i in items:
            if i.get("article_count", 0) > i.get("parsed_count", 0):
                laws.append({"law_id": i["id"], "law_name": i["law_name"], "unparsed": i["article_count"] - i["parsed_count"]})
        if len(items) < 100: break
        page += 1
    laws.sort(key=lambda x: x["unparsed"])
    print(f"  {len(laws)}개 법령, {sum(l['unparsed'] for l in laws)}개 조문")
    return laws

def parse_one(law_id):
    try:
        r = requests.post(f"{BASE}/auto-parse-and-approve", json={"secret": SECRET, "law_id": law_id, "max_articles": MAX_ARTICLES, "auto_approve_threshold": THRESHOLD}, timeout=300)
        d = r.json()
        if d.get("status") == "success":
            dd = d.get("data", {})
            return {"ok": True, "drafts": dd.get("drafts_created", 0), "approved": dd.get("auto_approved", 0)}
        return {"ok": False, "error": d.get("detail", "?")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}

def bulk_approve():
    print("\nbulk-approve...")
    total = 0
    for _ in range(5):
        r = requests.post(f"{BASE}/bulk-approve-unregistered", params={"secret": SECRET, "limit": 500}, timeout=120)
        d = r.json().get("data", {})
        ok, rem = d.get("ok", 0), d.get("remaining", 0)
        total += ok
        print(f"  +{ok}건, 잔여 {rem}")
        if rem == 0 or ok == 0: break
        time.sleep(2)
    return total

def main():
    start = time.time()
    laws = get_unparsed_laws()
    if not laws: print("완료"); return
    ok, fail, drafts, approved = 0, 0, 0, 0
    for i, law in enumerate(laws):
        elapsed = (time.time() - start) / 60
        eta = (elapsed / (i+1)) * (len(laws)-i-1) if i else 0
        print(f"[{i+1}/{len(laws)}] {law['law_name'][:30]}... ({law['unparsed']}조문) [{elapsed:.1f}분, ETA {eta:.0f}분]", end="", flush=True)
        r = parse_one(law["law_id"])
        if r["ok"]: ok += 1; drafts += r["drafts"]; approved += r["approved"]; print(f" -> 초안{r['drafts']} 승인{r['approved']}")
        else: fail += 1; print(f" -> X {r['error'][:40]}")
        time.sleep(DELAY)
    bulk = bulk_approve()
    print(f"\n=== 완료: {ok}/{len(laws)}법령, 초안{drafts}, 승인{approved}, master+{bulk}, 실패{fail}, {(time.time()-start)/60:.1f}분 ===")

if __name__ == "__main__": main()
