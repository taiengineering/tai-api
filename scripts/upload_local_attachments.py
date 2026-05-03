#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
upload_local_attachments.py — 로컬 디렉토리의 PDF/HWP 일괄 업로드

사용 시나리오 (2026-05-03):
    Storage 단일 PUT 50MB 한계로 collect/expand 자동 처리가 실패한 zip 첨부를
    사용자가 Mac 에서 압축 해제한 뒤 직접 업로드.

    - 한글 파일명 → ASCII-safe Storage path 자동 변환
    - 디렉토리 재귀 탐색 (zip 안에 폴더 있는 경우 OK)
    - 원본 한글 파일명은 DB의 source_file_name + zip_inner_path 에 보존
    - macOS NFD → NFC 정규화

대상 master_id 예시:
    환경유해인자공정시험기준 → d2c6d65d-980b-4f2e-97e9-4ec8136119e6
    대기오염공정시험기준    → fdf75b2f-4012-41fe-8c4c-d59bf8941b40

처리:
    1. --source-dir 재귀 탐색 → .pdf / .hwp / .hwpx 수집
    2. NFC 정규화 + ES No 추출하여 자연 정렬 (가능 시)
    3. 각 파일:
       - Storage path: {master_id}/zip_{flseq}/{idx:03d}.{ext}  (parent zip 있으면)
                       또는 {master_id}/local_{idx:03d}.{ext}
       - law_attachment INSERT/UPDATE
       - source_url: {parent.source_url}#inner={idx:03d}  (unique 보장)
    4. parent zip row → EXPANDED 마킹

멱등성:
    같은 source_url + SUCCESS 면 SKIP. --force 로 덮어쓰기.

실행:
    cd ~/dev/tai-api
    git pull origin main

    # 환경유해인자
    railway run python3 scripts/upload_local_attachments.py \\
        --source-dir ~/Downloads/환경유해인자공정시험기준 \\
        --master-id d2c6d65d-980b-4f2e-97e9-4ec8136119e6 \\
        --parent-attachment-id d95e6f70-41b6-44d0-a9b2-1a9a8cc85d8e

    # 대기오염
    railway run python3 scripts/upload_local_attachments.py \\
        --source-dir ~/Downloads/대기오염공정시험기준 \\
        --master-id fdf75b2f-4012-41fe-8c4c-d59bf8941b40 \\
        --parent-attachment-id fef6458b-adf4-4d7b-a019-28d10a8f5599
"""

import argparse
import hashlib
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
for _k in ("OUTBOUND_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)

from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or os.environ.get("SUPABASE_SERVICE_KEY")
)
if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL / SUPABASE_(SERVICE_ROLE_)KEY env required", file=sys.stderr)
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET = "law-attachments"

CONTENT_TYPE_MAP = {
    'pdf': 'application/pdf',
    'hwp': 'application/x-hwp',
    'hwpx': 'application/x-hwp',
    'doc': 'application/octet-stream',
    'docx': 'application/octet-stream',
    'other': 'application/octet-stream',
}

# ES NNNNN.x 형식 (ES 12000.a, ES 01000 등) 추출 → 자연 정렬용
ES_NO_RE = re.compile(r'ES\s*(\d{4,5})\.?([0-9a-z]*)', re.IGNORECASE)


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def detect_format(filename: str) -> str:
    fn = (filename or "").lower()
    if fn.endswith('.pdf'):
        return 'pdf'
    if fn.endswith('.hwp'):
        return 'hwp'
    if fn.endswith('.hwpx'):
        return 'hwpx'
    if fn.endswith('.docx'):
        return 'docx'
    if fn.endswith('.doc'):
        return 'doc'
    return 'other'


def normalize_filename(name: str) -> str:
    """macOS NFD 한글 → NFC 정규화."""
    if not name:
        return name
    return unicodedata.normalize('NFC', name)


def extract_es_no(name: str):
    """파일명에서 ES No 추출. 정렬 키 생성."""
    m = ES_NO_RE.search(name or "")
    if not m:
        return None
    num = int(m.group(1))
    sub = (m.group(2) or "").lower()
    return (num, sub)


def extract_flseq(url: str) -> str:
    if not url:
        return None
    m = re.search(r'flSeq=(\d+)', url)
    if m:
        return m.group(1)
    return hashlib.md5(url.encode('utf-8')).hexdigest()[:12]


def upload_storage(storage_path: str, fmt: str, content: bytes):
    content_type = CONTENT_TYPE_MAP.get(fmt, 'application/octet-stream')
    file_options = {"content-type": content_type, "upsert": "true"}
    try:
        sb.storage.from_(BUCKET).upload(storage_path, content, file_options=file_options)
    except Exception as e1:
        try:
            sb.storage.from_(BUCKET).update(
                storage_path, content,
                file_options={"content-type": content_type},
            )
        except Exception as e2:
            raise RuntimeError(f"storage upload failed: {e1} / update fallback: {e2}")
    return storage_path


def upsert_attachment_row(version_id: str, source_url: str, payload: dict):
    existing = sb.table("law_attachment").select("id").eq(
        "law_version_id", version_id
    ).eq("source_url", source_url).limit(1).execute()
    if existing.data:
        att_id = existing.data[0]["id"]
        sb.table("law_attachment").update(payload).eq("id", att_id).execute()
        return att_id
    full = {"law_version_id": version_id, "source_url": source_url, **payload}
    result = sb.table("law_attachment").insert(full).execute()
    return result.data[0]["id"] if result.data else None


def get_version_id(master_id: str) -> str:
    resp = sb.table("law_master").select("current_version_id,law_name").eq(
        "id", master_id
    ).limit(1).execute()
    if not resp.data:
        return None, None
    return resp.data[0].get("current_version_id"), resp.data[0].get("law_name")


def get_parent_attachment(parent_id: str):
    if not parent_id:
        return None
    resp = sb.table("law_attachment").select("*").eq("id", parent_id).limit(1).execute()
    return resp.data[0] if resp.data else None


# ────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-dir", type=str, required=True, help="압축 해제된 디렉토리")
    ap.add_argument("--master-id", type=str, required=True, help="대상 law_master.id")
    ap.add_argument("--parent-attachment-id", type=str, default=None,
                    help="zip 원본 첨부 row id (있으면 source_url 합성 + EXPANDED 마킹)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-file-mb", type=int, default=50)
    ap.add_argument("--include-other", action="store_true",
                    help=".pdf/.hwp/.hwpx 외 다른 확장자도")
    args = ap.parse_args()

    print("=" * 72)
    print("upload_local_attachments — 로컬 PDF/HWP 일괄 업로드")
    print("=" * 72)

    # 사전 검증
    source_dir = Path(args.source_dir).expanduser().resolve()
    if not source_dir.is_dir():
        print(f"ERROR: source-dir 가 디렉토리가 아님: {source_dir}", file=sys.stderr)
        sys.exit(1)

    version_id, law_name = get_version_id(args.master_id)
    if not version_id:
        print(f"ERROR: master_id 의 current_version_id 못 찾음: {args.master_id}", file=sys.stderr)
        sys.exit(1)
    print(f"  master_id = {args.master_id}")
    print(f"  law_name  = {law_name}")
    print(f"  version_id= {version_id}")
    print(f"  source_dir= {source_dir}")

    parent = get_parent_attachment(args.parent_attachment_id) if args.parent_attachment_id else None
    if args.parent_attachment_id and not parent:
        print(f"ERROR: parent_attachment_id 못 찾음: {args.parent_attachment_id}", file=sys.stderr)
        sys.exit(1)

    parent_source_url = parent.get("source_url") if parent else None
    parent_id = parent.get("id") if parent else None
    flseq = extract_flseq(parent_source_url) if parent_source_url else None

    if parent:
        print(f"  parent zip: {parent.get('attachment_title', '?')[:60]}")
        print(f"  parent source_url: {parent_source_url}")
        print(f"  flSeq: {flseq}")

    # ─── Step 1. 파일 수집 ────────────────────────────────────────
    print(f"\nStep 1. 파일 재귀 탐색 ({source_dir})")
    allowed_exts = {'pdf', 'hwp', 'hwpx'}
    if args.include_other:
        allowed_exts |= {'doc', 'docx'}

    found = []
    for path in source_dir.rglob('*'):
        if not path.is_file():
            continue
        # macOS .DS_Store, __MACOSX 등 무시
        if path.name.startswith('.') or '__MACOSX' in path.parts:
            continue
        rel = path.relative_to(source_dir)
        rel_str = unicodedata.normalize('NFC', str(rel))
        original_name = unicodedata.normalize('NFC', path.name)
        fmt = detect_format(original_name)
        if fmt not in allowed_exts:
            continue
        found.append({
            "path": path,
            "rel_path": rel_str,
            "name": original_name,
            "fmt": fmt,
            "size": path.stat().st_size,
        })

    if not found:
        print("  탐색 결과 PDF/HWP 없음. 종료.")
        return

    # ES No 자연 정렬
    found.sort(key=lambda f: (extract_es_no(f["name"]) or (99999, ""), f["rel_path"]))

    print(f"  파일: {len(found)}개")
    print(f"  포맷별: " + ", ".join(
        f"{k}={sum(1 for f in found if f['fmt'] == k)}"
        for k in sorted({f['fmt'] for f in found})
    ))
    total_mb = sum(f["size"] for f in found) / 1024 / 1024
    print(f"  합계: {total_mb:.1f} MB")
    print(f"  처음 5건:")
    for f in found[:5]:
        print(f"    [{f['fmt']:4}] {f['rel_path'][:70]:70} {f['size']:>10,} bytes")

    # ─── Step 2. 처리 ────────────────────────────────────────────
    print(f"\nStep 2. 업로드 시작 (dry_run={args.dry_run}, force={args.force})")
    max_size = args.max_file_mb * 1024 * 1024
    summary = {"SUCCESS": 0, "FAILED": 0, "SKIPPED": 0, "DRY_RUN": 0}
    failed_details = []

    for idx, f in enumerate(found, 1):
        # source_url 합성
        if parent_source_url:
            inner_source_url = f"{parent_source_url}#inner={idx:03d}"
        else:
            safe_rel = re.sub(r'[^\w\-./]', '_', f['rel_path'])
            inner_source_url = f"local://{args.master_id}/{idx:03d}-{safe_rel}"

        # 멱등성
        if not args.force:
            ex = sb.table("law_attachment").select("download_status").eq(
                "law_version_id", version_id
            ).eq("source_url", inner_source_url).limit(1).execute()
            if ex.data and ex.data[0].get("download_status") == "SUCCESS":
                summary["SKIPPED"] += 1
                continue

        # 크기 체크
        if f["size"] > max_size:
            summary["FAILED"] += 1
            failed_details.append((f["rel_path"], f"size {f['size']} > limit {max_size}"))
            try:
                upsert_attachment_row(version_id, inner_source_url, {
                    "attachment_type_code": "ZIP_INNER" if parent else "LOCAL",
                    "attachment_title": f["name"][:500],
                    "source_file_name": f["name"][:500],
                    "file_format": f["fmt"],
                    "file_size_bytes": f["size"],
                    "download_status": "FAILED",
                    "download_error": f"file > {args.max_file_mb}MB limit",
                    "storage_bucket": BUCKET,
                    "parent_attachment_id": parent_id,
                    "zip_inner_path": f["rel_path"][:500],
                })
            except Exception:
                pass
            print(f"  [{idx:3}/{len(found)}] FAIL: {f['rel_path'][:60]} (size limit)")
            continue

        if args.dry_run:
            summary["DRY_RUN"] += 1
            if idx <= 5 or idx % 50 == 0:
                print(f"  [{idx:3}/{len(found)}] DRY: {f['rel_path'][:60]}")
            continue

        # Storage path
        if flseq:
            storage_path = f"{args.master_id}/zip_{flseq}/{idx:03d}.{f['fmt']}"
        else:
            storage_path = f"{args.master_id}/local_{idx:03d}.{f['fmt']}"

        # 파일 읽기
        try:
            content = f["path"].read_bytes()
        except Exception as e:
            summary["FAILED"] += 1
            failed_details.append((f["rel_path"], f"read: {e}"))
            print(f"  [{idx:3}/{len(found)}] FAIL: {f['rel_path'][:60]} (read: {e})")
            continue

        # Storage 업로드
        try:
            upload_storage(storage_path, f["fmt"], content)
        except Exception as e:
            summary["FAILED"] += 1
            failed_details.append((f["rel_path"], f"storage: {e}"))
            try:
                upsert_attachment_row(version_id, inner_source_url, {
                    "attachment_type_code": "ZIP_INNER" if parent else "LOCAL",
                    "attachment_title": f["name"][:500],
                    "source_file_name": f["name"][:500],
                    "file_format": f["fmt"],
                    "file_size_bytes": f["size"],
                    "download_status": "FAILED",
                    "download_error": f"storage: {str(e)[:400]}",
                    "storage_bucket": BUCKET,
                    "parent_attachment_id": parent_id,
                    "zip_inner_path": f["rel_path"][:500],
                })
            except Exception:
                pass
            print(f"  [{idx:3}/{len(found)}] FAIL: {f['rel_path'][:60]} (storage: {str(e)[:60]})")
            continue

        # DB upsert (SUCCESS)
        try:
            upsert_attachment_row(version_id, inner_source_url, {
                "attachment_type_code": "ZIP_INNER" if parent else "LOCAL",
                "attachment_title": f["name"][:500],
                "source_file_name": f["name"][:500],
                "file_format": f["fmt"],
                "file_size_bytes": f["size"],
                "download_status": "SUCCESS",
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "storage_path": storage_path,
                "download_error": None,
                "storage_bucket": BUCKET,
                "parent_attachment_id": parent_id,
                "zip_inner_path": f["rel_path"][:500],
            })
            summary["SUCCESS"] += 1
            if idx <= 5 or idx % 25 == 0 or idx == len(found):
                print(f"  [{idx:3}/{len(found)}] OK: {storage_path} ({f['size']:,} bytes) "
                      f"<- {f['rel_path'][:50]}")
        except Exception as e:
            summary["FAILED"] += 1
            failed_details.append((f["rel_path"], f"db: {e}"))
            print(f"  [{idx:3}/{len(found)}] FAIL: {f['rel_path'][:60]} (db: {str(e)[:60]})")

    # ─── Step 3. parent zip → EXPANDED ─────────────────────────────
    if parent_id and not args.dry_run and summary["SUCCESS"] > 0:
        try:
            sb.table("law_attachment").update({
                "download_status": "EXPANDED",
                "download_error": None,
                "attachment_type_code": "ZIP_PARENT",
            }).eq("id", parent_id).execute()
            print(f"\n  parent zip {parent_id} → EXPANDED 마킹")
        except Exception as e:
            print(f"  WARN: parent EXPANDED 마킹 실패: {e}")

    # ─── 요약 ───────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("요약")
    print("=" * 72)
    for k in ("SUCCESS", "FAILED", "SKIPPED", "DRY_RUN"):
        if summary.get(k, 0):
            print(f"  {k:10}: {summary[k]}")

    if failed_details:
        print(f"\n  FAILED 상세 (처음 10건):")
        for name, err in failed_details[:10]:
            print(f"    - {name[:60]} | {err[:80]}")
        if len(failed_details) > 10:
            print(f"    ... 그 외 {len(failed_details)-10}건")

    if not args.dry_run:
        print("\nDB 상태 검증 (이 master 의 law_attachment):")
        for s in ("SUCCESS", "FAILED", "EXPANDED", "PENDING"):
            cnt = sb.table("law_attachment").select(
                "id", count="exact"
            ).eq("law_version_id", version_id).eq(
                "download_status", s
            ).limit(1).execute()
            n = cnt.count or 0
            if n:
                print(f"  {s:12}: {n}")


if __name__ == "__main__":
    main()
