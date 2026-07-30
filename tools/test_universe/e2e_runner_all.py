#!/usr/bin/env python3
"""WO-E2E-BASELINE-001 — Full Baseline Runner (112 Profile).

profile_universe_v1.json 전수 실행 -> 라이브 엔진 -> Snapshot + 메타데이터 수집.
판정 없음. Golden 없음. 엔진/Rule 무수정. 사실(Fact)만 수집.

실행(사용자 PC / On-your-computer):
    cd ~/45cm-test && python3 e2e_runner_all.py
클라우드 세션은 프록시 403으로 차단됨(라이브 도달 불가).

산출:
    baseline_snapshot_set_v1.json   (전 Profile 메타 + 실패목록)
    snapshots_all/SNAP-XXXX-001.json (각 Snapshot 전문)

주의: 엔드포인트/일시정지는 환경변수로 조정 (TAI_API_BASE, RUN_PAUSE_S).
"""
import json, time, os, sys
from datetime import datetime, timezone
import urllib.request, urllib.error

API_BASE = os.getenv("TAI_API_BASE", "https://api.taieng.co.kr")
ENDPOINT = "/anonymous-diagnosis"
PAUSE_S = float(os.getenv("RUN_PAUSE_S", "0.5"))

SITE_KIND = {"MANUFACTURING": "manufacturing", "BUILDING": "building",
             "CONSTRUCTION": "construction", "SPECIAL_FACILITY": "other"}

def profile_to_request(p):
    c = p["layers"]["company"]
    return {"site_kind": SITE_KIND[p["sector"]], "scale": c["scale"],
            "workers": int(c["worker_count"]), "region": c["region"]}

def call_engine(payload, timeout=40):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_BASE + ENDPOINT, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "http": resp.status, "body": body,
                    "ms": round((time.perf_counter() - t0) * 1000)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "http": e.code, "body": None,
                "ms": round((time.perf_counter() - t0) * 1000), "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "http": None, "body": None,
                "ms": round((time.perf_counter() - t0) * 1000), "error": f"{type(e).__name__}: {e}"}

def extract_meta(body):
    if not isinstance(body, dict): return {}
    r = body.get("partialResult") or {}
    rules = r.get("rules_table") or []
    laws = set(r.get("law_badges") or [])
    evidence = sum(1 for x in rules
                   if (x.get("obligation_summary") or "").strip() and (x.get("law_name") or "").strip())
    s = r.get("summary") or {}
    return {
        "obligation_total": r.get("applicable_count") or s.get("total") or 0,
        "law_count": len(laws),
        "rule_count": len(rules),
        "evidence_count": evidence,
        "risk_level": r.get("risk_level"),
        "engine_version": r.get("engine_version"),
        "summary": s,
    }

def main():
    d = json.load(open("profile_universe_v1.json"))
    profiles = d["profiles"]
    targets = sys.argv[1:] or [p["profile_id"] for p in profiles]
    pmap = {p["profile_id"]: p for p in profiles}
    run_ts = datetime.now(timezone.utc).isoformat()
    os.makedirs("snapshots_all", exist_ok=True)
    records, failures = [], []
    total = len(targets)
    for i, pid in enumerate(targets, 1):
        p = pmap.get(pid)
        if not p:
            failures.append({"profile_id": pid, "reason": "not found in profile set"}); continue
        payload = profile_to_request(p)
        res = call_engine(payload)
        num = pid.split("-")[1]
        snap_id = f"SNAP-{num}-001"
        meta = extract_meta(res["body"]) if res["ok"] else {}
        pub = None
        if res["ok"] and isinstance(res["body"], dict):
            pub = res["body"].get("publicToken")
        snap = {
            "snapshot_id": snap_id, "profile_id": pid, "profile_version": "v1",
            "sector": p["sector"], "boundary": p.get("boundary", False),
            "boundary_note": p.get("boundary_note", ""),
            "engine_endpoint": API_BASE + ENDPOINT,
            "engine_version": meta.get("engine_version"),
            "public_token": pub, "run_at": run_ts,
            "request_payload": payload, "http_status": res["http"],
            "execution_duration_ms": res["ms"], "ok": res["ok"],
            "error": res.get("error"), "response": res["body"],
            "note": "WO-E2E-BASELINE-001 fact collection. No judgment. No Golden.",
        }
        json.dump(snap, open(f"snapshots_all/{snap_id}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        rec = {"snapshot_id": snap_id, "profile_id": pid, "sector": p["sector"],
               "boundary": p.get("boundary", False), "boundary_note": p.get("boundary_note", ""),
               "http_status": res["http"], "ok": res["ok"], "error": res.get("error"),
               "execution_duration_ms": res["ms"],
               "obligation_total": meta.get("obligation_total"),
               "law_count": meta.get("law_count"), "rule_count": meta.get("rule_count"),
               "evidence_count": meta.get("evidence_count"), "risk_level": meta.get("risk_level"),
               "engine_version": meta.get("engine_version"),
               "public_token": pub, "request_payload": payload}
        records.append(rec)
        if not res["ok"]:
            failures.append({"profile_id": pid, "http": res["http"], "error": res.get("error")})
        print(f"[{i}/{total}] {pid} {p['sector']:16} http={res['http']} "
              f"obl={meta.get('obligation_total')} risk={meta.get('risk_level')} {res['ms']}ms"
              + ("" if res["ok"] else f"  FAIL:{res.get('error')}"), flush=True)
        time.sleep(PAUSE_S)

    baseline = {
        "wo": "WO-E2E-BASELINE-001", "version": 1, "baseline": "baseline-snapshot-set-v1",
        "run_at": run_ts, "engine_expected": "v3.0-compiler-core-anonymous",
        "total_targets": total, "executed": len(records),
        "success": sum(1 for r in records if r["ok"]), "failures": failures,
        "records": records,
    }
    json.dump(baseline, open("baseline_snapshot_set_v1.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    ok = baseline["success"]
    print(f"\n=== BASELINE DONE === executed={len(records)}/{total} success={ok} failures={len(failures)}")
    print("output: baseline_snapshot_set_v1.json + snapshots_all/*.json")

if __name__ == "__main__":
    main()
