#!/usr/bin/env python3
"""WO-E2E-RUNNER-001 — Minimal E2E Runner.

Profile -> Compiler Input(AnonymousDiagnosisCreate) -> Live Engine(POST /anonymous-diagnosis) -> Snapshot.
엔진/Rule/Profile 무수정. Golden/Diff/Regression 없음. 라이브 API 클라이언트만.

실행: python3 e2e_runner.py            (기본 대표 4건: PF-0001 PF-0019 PF-0028 PF-0037)
      python3 e2e_runner.py PF-0005 …  (특정 Profile 지정)

주의: 클라우드 Cowork 세션에서는 아웃바운드 프록시가 POST를 403 차단한다.
      라이브 호출은 'On your computer' 모드(사용자 실제 네트워크)에서 실행할 것.
      입력 profile_universe_v1.json 이 같은 디렉토리에 있어야 한다.
"""
import json, time, sys, os
from datetime import datetime, timezone
import urllib.request, urllib.error
from services.time import now_kst, serialize_external_utc

API_BASE = "https://api.taieng.co.kr"
ENDPOINT = "/anonymous-diagnosis"
ENGINE_VERSION_HINT = "compiler-core (api.taieng.co.kr)"

# Profile.sector -> AnonymousDiagnosisCreate.site_kind (실측 계약: routers/anonymous_diagnosis.py SECTOR_BY_KIND 역방향)
SITE_KIND = {
    "MANUFACTURING": "manufacturing",
    "BUILDING": "building",
    "CONSTRUCTION": "construction",
    "SPECIAL_FACILITY": "other",
}

def profile_to_request(p):
    c = p["layers"]["company"]
    return {
        "site_kind": SITE_KIND[p["sector"]],
        "scale": c["scale"],
        "workers": int(c["worker_count"]),
        "region": c["region"],
    }

def call_engine(payload, timeout=30):
    url = API_BASE + ENDPOINT
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return {"ok": True, "http_status": resp.status, "body": json.loads(body),
                    "elapsed_s": round(time.perf_counter() - t0, 3)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "http_status": e.code, "body": e.read().decode("utf-8", "replace")[:1000],
                "elapsed_s": round(time.perf_counter() - t0, 3), "error": "HTTPError"}
    except Exception as e:
        return {"ok": False, "http_status": None, "body": None,
                "elapsed_s": round(time.perf_counter() - t0, 3), "error": f"{type(e).__name__}: {e}"}

def make_snapshot(p, payload, result, run_ts):
    body = result.get("body") if result["ok"] else None
    pub_token = body.get("publicToken") if isinstance(body, dict) else None
    partial = body.get("partialResult") if isinstance(body, dict) else None
    engine_ver = None
    if isinstance(partial, dict):
        engine_ver = partial.get("engine_version")
    snap_id = f"SNAP-{p['profile_id'].split('-')[1]}-001"
    return {
        "snapshot_id": snap_id,
        "profile_id": p["profile_id"],
        "profile_version": "v1",
        "sector": p["sector"],
        "engine_endpoint": API_BASE + ENDPOINT,
        "engine_version": engine_ver or ENGINE_VERSION_HINT,
        "public_token": pub_token,
        "run_at": run_ts,
        "request_payload": payload,
        "http_status": result["http_status"],
        "elapsed_s": result["elapsed_s"],
        "ok": result["ok"],
        "error": result.get("error"),
        "response": body,
        "note": "WO-E2E-RUNNER-001 test run (live). Golden/Diff not evaluated.",
    }

def main():
    d = json.load(open("profile_universe_v1.json"))
    profiles = {p["profile_id"]: p for p in d["profiles"]}
    targets = sys.argv[1:] or ["PF-0001", "PF-0019", "PF-0028", "PF-0037"]
    run_ts = serialize_external_utc(now_kst())
    log = []
    os.makedirs("snapshots", exist_ok=True)
    for pid in targets:
        p = profiles.get(pid)
        if not p:
            log.append({"profile_id": pid, "step": "read", "result": "FAIL", "detail": "not found"})
            continue
        log.append({"profile_id": pid, "step": "read", "result": "OK", "sector": p["sector"]})
        payload = profile_to_request(p)
        log.append({"profile_id": pid, "step": "compiler_input", "result": "OK", "payload": payload})
        res = call_engine(payload)
        step_res = "OK" if res["ok"] else "FAIL"
        log.append({"profile_id": pid, "step": "engine", "result": step_res,
                    "http_status": res["http_status"], "elapsed_s": res["elapsed_s"],
                    "error": res.get("error")})
        snap = make_snapshot(p, payload, res, run_ts)
        path = f"snapshots/{snap['snapshot_id']}.json"
        json.dump(snap, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        log.append({"profile_id": pid, "step": "snapshot", "result": "OK",
                    "snapshot_id": snap["snapshot_id"], "public_token": snap["public_token"], "path": path})
    json.dump({"wo": "WO-E2E-RUNNER-001", "run_at": run_ts, "targets": targets, "log": log},
              open("snapshots/run_log.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    oks = sum(1 for e in log if e["step"] == "engine" and e["result"] == "OK")
    print(f"RUN {run_ts} | targets={len(targets)} | engine_OK={oks}")
    for e in log:
        if e["step"] in ("engine", "snapshot"):
            print(json.dumps(e, ensure_ascii=False))

if __name__ == "__main__":
    main()
