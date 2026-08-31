#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
expand_law_zip_attachments.py — ZIP 첨부파일 압축 해제 + 개별 PDF/HWP 업로드

배경 (2026-05-03):
    collect_law_attachments 실행 시 ZIP 파일 2건이 Supabase Storage 단일 PUT 50MB 한계 초과로 FAILED.
    - 환경유해인자공정시험기준.zip (61MB, 257개 시험법 PDF 묶음)
    - 대기오염공정시험기준.Zip (72MB, 비슷한 구조)
    
    환경부 공정시험기준은 분야별 시험법(ES No)을 PDF/HWP 개별 파일로 zip 묶어 배포하는 구조.
    압축 해제 → 개별 파일을 Storage 업로드하면 사이즈도 작아지고 의무 추출도 항목별로 가능.

대상:
    download_status='FAILED' AND attachment_title ILIKE '%.zip' AND download_error LIKE '%413%'
    또는 --attachment-id 로 특정 row 지정.

처리:
    1. zip 다운로드 (source_url)
    2. 메모리에서 압축 해제 (한글 파일명 cp437->cp949 디코드)
    3. 안의 .pdf / .hwp 파일을 개별 추출
    4. 각 파일:
       - Storage 업로드 (path: {master_id}/zip_{flSeq}/{idx:03d}.{ext})
       - law_attachment INSERT (parent_attachment_id 로 원본 zip 연결)
       - source_url 합성: {원본URL}#inner={idx:03d} (unique 보장)
    5. 원본 zip row → download_status='EXPANDED' 로 마킹 (이력 보존)

멱등성:
    이미 EXPANDED 인 zip 은 SKIP. --force 로 다시.
    같은 (version_id, source_url) 조합이 이미 SUCCESS 면 개별 파일도 SKIP.

실행:
    cd ~/dev/tai-api
    git pull origin main
    railway run python3 scripts/expand_law_zip_attachments.py [옵션]

옵션:
    --attachment-id UUID  : 특정 zip 첨부 row 만
    --dry-run             : 실제 업로드/INSERT 없이 매니페스트만
    --force               : 이미 EXPANDED 여도 다시 처리
    --max-file-mb 50      : 단일 파일 사이즈 한계 (기본 50MB, Storage 단일 PUT 한계)
"""

import argparse
import hashlib
import io
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from services.time import now_kst, serialize_external_utc

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
for _k in ("OUTBOUND_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)

import requests
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
    'doc': 'application/octet-stream',
    'other': 'application/octet-stream',
}


def detect_format(filename: str) -> str:
    fn = (filename or "").lower()
    if fn.endswith('.pdf'):
        return 'pdf'
    if fn.endswith('.hwp') or fn.endswith('.hwpx'):
        return 'hwp'
    if fn.endswith('.docx') or fn.endswith('.doc'):
        return 'doc'
    return 'other'


def decode_zip_filename(name_bytes_or_str):
    """zip 안의 한글 파일명 디코드.

    Windows에서 만든 한국어 zip은 cp437로 디코드된 상태로 들어옴 → cp949로 재해석.
    UTF-8 zip (EFS marker 있는 것) 은 Python zipfile이 자동 UTF-8 디코드.
    """
    if isinstance(name_bytes_or_str, bytes):
        for enc in ('utf-8', 'cp949', 'euc-kr'):
            try:
                return name_bytes_or_str.decode(enc)
            except UnicodeDecodeError:
                continue
        return name_bytes_or_str.decode('utf-8', errors='replace')

    s = name_bytes_or_str
    # cp437로 잘못 디코드된 경우 (Windows zip + EFS 없는 경우의 일반 케이스)
    try:
        re_decoded = s.encode('cp437').decode('cp949')
        # 한글이 나타나면 재해석 결과가 정답
        if any('\uac00' <= ch <= '\ud7af' for ch in re_decoded):
            return re_decoded
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return s


def download_zip(url: str, timeout: int = 120, max_retry: int = 3):
    """zip 다운로드. (bytes, content_type) 반환."""
    last_err = None
    for attempt in range(max_retry):
        try:
            resp = requests.get(
                url, timeout=timeout, allow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 TAI-Engineering-Bot', 'Accept': '*/*'},
            )
            resp.raise_for_status()
            content = resp.content
            if not content or len(content) < 100:
                raise RuntimeError(f"empty or too-small content ({len(content)} bytes)")
            return content, resp.headers.get('Content-Type', '')
        except Exception as e:
            last_err = e
            if attempt < max_retry - 1:
                import time
                time.sleep(2 ** attempt)
    raise RuntimeError(f"zip download failed after {max_retry} retries: {last_err}")


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


def extract_flseq(url: str) -> str:
    m = re.search(r'flSeq=(\d+)', url)
    if m:
        return m.group(1)
    return hashlib.md5(url.encode('utf-8')).hexdigest()[:12]


def collect_zip_targets(args):
    """대상 zip 첨부 row 수집."""
    if args.attachment_id:
        resp = sb.table("law_attachment").select("*").eq("id", args.attachment_id).limit(1).execute()
        return resp.data or []

    # FAILED + 413 + zip
    resp = sb.table("law_attachment").select("*").eq(
        "download_status", "FAILED"
    ).execute()
    rows = resp.data or []
    targets = []
    for r in rows:
        title = (r.get("attachment_title") or "").lower()
        err = (r.get("download_error") or "")
        if title.endswith(".zip") and ("413" in err or "Payload too large" in err):
            targets.append(r)
    return targets


def get_master_id_from_version(version_id: str) -> str:
    resp = sb.table("law_version").select("law_id").eq("id", version_id).limit(1).execute()
    if not resp.data:
        return None
    return resp.data[0].get("law_id")


def process_zip(zip_row: dict, args):
    """한 zip 첨부를 압축 해제 → 개별 업로드 + DB INSERT."""
    zip_id = zip_row["id"]
    version_id = zip_row["law_version_id"]
    source_url = zip_row["source_url"]
    zip_title = zip_row.get("attachment_title", "?.zip")

    master_id = get_master_id_from_version(version_id)
    if not master_id:
        return {"status": "FAILED", "reason": "master_id not found"}

    flseq = extract_flseq(source_url)

    # 멱등성: 이미 EXPANDED면 SKIP (단 --force는 통과)
    if not args.force and zip_row.get("download_status") == "EXPANDED":
        return {"status": "SKIPPED", "reason": "already EXPANDED"}

    # 1. zip 다운로드
    print(f"  [download] {zip_title} ({source_url})")
    try:
        content, _ = download_zip(source_url)
    except Exception as e:
        return {"status": "FAILED", "reason": f"download: {e}"}
    print(f"    OK {len(content):,} bytes")

    # 2. 압축 해제
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as e:
        return {"status": "FAILED", "reason": f"bad zip: {e}"}

    inner_files = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        # 한글 파일명 디코드
        try:
            raw_name = info.filename
            decoded = decode_zip_filename(raw_name)
        except Exception:
            decoded = info.filename

        fmt = detect_format(decoded)
        if fmt not in ('pdf', 'hwp', 'doc'):
            continue
        inner_files.append((info, decoded, fmt))

    if not inner_files:
        return {"status": "FAILED", "reason": "no PDF/HWP inside zip"}

    print(f"    압축 안 PDF/HWP: {len(inner_files)}개")

    # 3. 각 파일 처리
    max_size = args.max_file_mb * 1024 * 1024
    success_count = 0
    failed_count = 0
    skipped_count = 0
    failed_details = []

    for idx, (info, decoded_name, fmt) in enumerate(inner_files, 1):
        inner_path = decoded_name  # zip 안 원본 경로
        inner_source_url = f"{source_url}#inner={idx:03d}"

        # 멱등성
        if not args.force:
            ex = sb.table("law_attachment").select("download_status").eq(
                "law_version_id", version_id
            ).eq("source_url", inner_source_url).limit(1).execute()
            if ex.data and ex.data[0].get("download_status") == "SUCCESS":
                skipped_count += 1
                continue

        if args.dry_run:
            print(f"    [{idx:03d}/{len(inner_files)}] {decoded_name[:60]} (DRY_RUN)")
            continue

        try:
            file_content = zf.read(info)
        except Exception as e:
            failed_count += 1
            failed_details.append((decoded_name, f"zip read: {e}"))
            continue

        if len(file_content) > max_size:
            failed_count += 1
            failed_details.append((decoded_name, f"size {len(file_content)} > limit {max_size}"))
            # 사이즈 초과는 별도 FAILED row 작성
            try:
                upsert_attachment_row(version_id, inner_source_url, {
                    "attachment_type_code": "ZIP_INNER",
                    "attachment_title": decoded_name[:500],
                    "source_file_name": decoded_name[:500],
                    "file_format": fmt,
                    "file_size_bytes": len(file_content),
                    "download_status": "FAILED",
                    "download_error": f"inner file > {args.max_file_mb}MB limit",
                    "storage_bucket": BUCKET,
                    "parent_attachment_id": zip_id,
                    "zip_inner_path": inner_path[:500],
                })
            except Exception:
                pass
            continue

        storage_path = f"{master_id}/zip_{flseq}/{idx:03d}.{fmt}"

        # Storage 업로드
        try:
            upload_storage(storage_path, fmt, file_content)
        except Exception as e:
            failed_count += 1
            failed_details.append((decoded_name, f"storage: {e}"))
            try:
                upsert_attachment_row(version_id, inner_source_url, {
                    "attachment_type_code": "ZIP_INNER",
                    "attachment_title": decoded_name[:500],
                    "source_file_name": decoded_name[:500],
                    "file_format": fmt,
                    "file_size_bytes": len(file_content),
                    "download_status": "FAILED",
                    "download_error": f"storage: {str(e)[:400]}",
                    "storage_bucket": BUCKET,
                    "parent_attachment_id": zip_id,
                    "zip_inner_path": inner_path[:500],
                })
            except Exception:
                pass
            continue

        # DB upsert (SUCCESS)
        try:
            upsert_attachment_row(version_id, inner_source_url, {
                "attachment_type_code": "ZIP_INNER",
                "attachment_title": decoded_name[:500],
                "source_file_name": decoded_name[:500],
                "file_format": fmt,
                "file_size_bytes": len(file_content),
                "download_status": "SUCCESS",
                "downloaded_at": serialize_external_utc(now_kst()),
                "storage_path": storage_path,
                "download_error": None,
                "storage_bucket": BUCKET,
                "parent_attachment_id": zip_id,
                "zip_inner_path": inner_path[:500],
            })
            success_count += 1
        except Exception as e:
            failed_count += 1
            failed_details.append((decoded_name, f"db: {e}"))
            continue

        if idx % 50 == 0:
            print(f"    진행 {idx}/{len(inner_files)}: ok={success_count} fail={failed_count}")

    # 4. 원본 zip row → EXPANDED 로 마킹
    if not args.dry_run and success_count > 0:
        try:
            sb.table("law_attachment").update({
                "download_status": "EXPANDED",
                "download_error": None,
                "attachment_type_code": "ZIP_PARENT",
            }).eq("id", zip_id).execute()
        except Exception as e:
            print(f"    WARN: failed to mark EXPANDED: {e}")

    return {
        "status": "OK",
        "total_inner": len(inner_files),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "failed_details": failed_details,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attachment-id", type=str, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-file-mb", type=int, default=50)
    args = ap.parse_args()

    print("=" * 72)
    print("expand_law_zip_attachments — zip 압축 해제 + 개별 파일 업로드")
    print("=" * 72)
    print(f"옵션: attachment_id={args.attachment_id} dry_run={args.dry_run} "
          f"force={args.force} max_file_mb={args.max_file_mb}")

    print("\nStep 1. 대상 zip 수집")
    targets = collect_zip_targets(args)
    print(f"  대상 zip: {len(targets)}건")
    if not targets:
        print("처리 대상 없음. 종료.")
        return
    for t in targets:
        print(f"    - id={t['id']} title={t.get('attachment_title', '?')[:60]} "
              f"size={t.get('file_size_bytes') or '?'}")

    print(f"\nStep 2. 처리 시작")
    grand_total = {"success": 0, "failed": 0, "skipped": 0}
    for i, t in enumerate(targets, 1):
        print(f"\n  [{i}/{len(targets)}] {t.get('attachment_title', '?')[:50]}")
        result = process_zip(t, args)
        if result.get("status") in ("FAILED", "SKIPPED"):
            print(f"    {result['status']}: {result.get('reason', '')}")
            continue
        print(f"    완료: 안 파일 {result['total_inner']}개 / "
              f"ok={result['success']} fail={result['failed']} skip={result['skipped']}")
        grand_total["success"] += result["success"]
        grand_total["failed"] += result["failed"]
        grand_total["skipped"] += result["skipped"]
        if result.get("failed_details"):
            for name, err in result["failed_details"][:5]:
                print(f"      FAIL: {name[:50]} | {err[:80]}")

    print("\n" + "=" * 72)
    print("요약")
    print("=" * 72)
    print(f"  처리 zip: {len(targets)}")
    print(f"  내부 파일: ok={grand_total['success']} fail={grand_total['failed']} skip={grand_total['skipped']}")

    if not args.dry_run:
        print("\nDB 상태 검증 (law_attachment):")
        for s in ("SUCCESS", "FAILED", "PENDING", "DOWNLOADING", "SKIPPED", "EXPANDED"):
            cnt = sb.table("law_attachment").select("id", count="exact").eq(
                "download_status", s
            ).limit(1).execute()
            n = cnt.count or 0
            if n:
                print(f"  {s:12}: {n}")


if __name__ == "__main__":
    main()
