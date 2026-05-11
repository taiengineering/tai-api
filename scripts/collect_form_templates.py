"""
TAI 법정서식 HWP 수집기
─────────────────────────
1) form_templates 테이블에서 hwp_url 조회
2) 법제처에서 HWP 파일 다운로드
3) Supabase form-originals 버킷에 업로드
4) form_templates.original_storage_path 업데이트

실행 (tai-api 폴더에서):
  railway run python3 scripts/collect_form_templates.py --dry-run   # 다운로드만 테스트
  railway run python3 scripts/collect_form_templates.py             # 실제 실행
"""

import os
import sys
import time
import requests
from pathlib import Path

# ─── 설정 (Railway 환경변수 자동 주입) ───
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
BUCKET = "form-originals"
DOWNLOAD_DIR = Path("./form_originals_hwp")
DRY_RUN = "--dry-run" in sys.argv

if not SUPABASE_URL or not SUPABASE_KEY:
    if not DRY_RUN:
        print("ERROR: Railway 환경변수가 없습니다.")
        print("  railway run python3 scripts/collect_form_templates.py")
        sys.exit(1)

HEADERS_SB = {
    "apikey": SUPABASE_KEY or "",
    "Authorization": f"Bearer {SUPABASE_KEY or ''}",
}

HEADERS_DL = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) TAI-Collector/1.0",
    "Accept": "application/octet-stream, */*",
}


def fetch_form_templates():
    url = f"{SUPABASE_URL}/rest/v1/form_templates"
    params = {
        "select": "id,form_code,form_name,hwp_url,original_storage_path",
        "hwp_url": "not.is.null",
        "order": "form_code.asc",
    }
    resp = requests.get(url, headers={**HEADERS_SB, "Prefer": "return=representation"}, params=params)
    resp.raise_for_status()
    return resp.json()


def download_hwp(hwp_url, save_path):
    try:
        resp = requests.get(hwp_url, headers=HEADERS_DL, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        size = len(resp.content)
        if size < 1024:
            try:
                text = resp.content[:200].decode("utf-8", errors="ignore")
                if "<html" in text.lower():
                    print(f"    ✗ HTML 응답 — HWP 아님. 스킵.")
                    return False
            except Exception:
                pass
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(resp.content)
        print(f"    ✓ 다운로드: {size:,} bytes → {save_path.name}")
        return True
    except requests.RequestException as e:
        print(f"    ✗ 다운로드 실패: {e}")
        return False


def upload_to_storage(local_path, storage_path):
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}"
    with open(local_path, "rb") as f:
        data = f.read()
    resp = requests.post(url, headers={**HEADERS_SB, "Content-Type": "application/x-hwp", "x-upsert": "true"}, data=data)
    if resp.status_code in (200, 201):
        print(f"    ✓ 업로드: {BUCKET}/{storage_path}")
        return True
    print(f"    ✗ 업로드 실패 ({resp.status_code}): {resp.text[:200]}")
    return False


def update_db(record_id, storage_path):
    url = f"{SUPABASE_URL}/rest/v1/form_templates"
    resp = requests.patch(
        url, params={"id": f"eq.{record_id}"},
        headers={**HEADERS_SB, "Content-Type": "application/json", "Prefer": "return=minimal"},
        json={"original_storage_path": storage_path},
    )
    if resp.status_code in (200, 204):
        print(f"    ✓ DB: original_storage_path = {storage_path}")
        return True
    print(f"    ✗ DB 실패 ({resp.status_code}): {resp.text[:200]}")
    return False


def main():
    print("=" * 60)
    print("  TAI 법정서식 HWP 수집기")
    print("=" * 60)
    if DRY_RUN:
        print("  [DRY RUN] 다운로드만, 업로드/DB 안 함\n")
    else:
        print(f"  버킷: {BUCKET} | Supabase: {SUPABASE_URL}\n")

    print("[1/4] form_templates 조회...")
    templates = fetch_form_templates()
    print(f"  → {len(templates)}건\n")

    todo = [t for t in templates if not t.get("original_storage_path")]
    skip = len(templates) - len(todo)
    if skip:
        print(f"  ℹ 이미 완료: {skip}건 스킵")
    print(f"  → 처리 대상: {len(todo)}건\n")

    s = {"dl_ok": 0, "dl_fail": 0, "up_ok": 0, "up_fail": 0, "db_ok": 0, "db_fail": 0}

    for i, t in enumerate(todo, 1):
        fc, fn, url, rid = t["form_code"], t["form_name"], t["hwp_url"], t["id"]
        print(f"[{i}/{len(todo)}] {fc}: {fn}")

        local = DOWNLOAD_DIR / f"{fc}.hwp"
        if not download_hwp(url, local):
            s["dl_fail"] += 1; print(); continue
        s["dl_ok"] += 1

        if DRY_RUN:
            print("    [DRY RUN] 스킵\n"); continue

        sp = f"{fc}/{fc}.hwp"
        if not upload_to_storage(local, sp):
            s["up_fail"] += 1; print(); continue
        s["up_ok"] += 1

        if update_db(rid, sp):
            s["db_ok"] += 1
        else:
            s["db_fail"] += 1

        time.sleep(1)
        print()

    print("=" * 60)
    print(f"  다운로드: {s['dl_ok']} 성공 / {s['dl_fail']} 실패")
    if not DRY_RUN:
        print(f"  업로드:   {s['up_ok']} 성공 / {s['up_fail']} 실패")
        print(f"  DB:       {s['db_ok']} 성공 / {s['db_fail']} 실패")
    print(f"  로컬:     {DOWNLOAD_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
