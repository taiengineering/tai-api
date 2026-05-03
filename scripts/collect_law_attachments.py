#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_law_attachments.py — 첨부파일 본체 트랙 PDF/HWP 다운로드  (v2: ASCII-safe Storage key)

목적:
    law.go.kr DRF API가 "공고/고시" 형태로 응답한 행정규칙은 본문이 첨부파일에만 있고
    XML <조문내용>은 비어있음. 이 케이스의 첨부파일을 다운로드 → Supabase Storage 보존
    → law_attachment 메타 저장. 이후 단계(텍스트 추출/의무 추출)의 전제 조건.

대상 (현재 DB 기준 116건):
    article_cnt <= 2 AND raw_xml에 <첨부파일링크> 존재 AND 아직 SUCCESS 첨부 없음
    예: 한국전기설비규정(KEC), 국가기술표준원 KS 표준 다수, KESCO 등

v2 변경 (2026-05-03):
    - Storage path를 ASCII-safe 로: {master_id}/{flSeq}.{ext}
    - 한글/공백/대괄호 포함 한글 파일명 → InvalidKey (Supabase Storage 거부) 해결
    - 원본 한글 파일명은 source_file_name + attachment_title 컬럼에 그대로 보존
    - content-type 명시 헤더 (pdf/hwp 자동 매핑)

처리:
    1. 후보 master 목록 수집
    2. raw_xml에서 (첨부파일명, 첨부파일링크) 쌍 추출 (regex)
    3. PDF 우선, PDF 없으면 HWP fallback (둘 다 없으면 모든 형식)
    4. law.go.kr 다운로드 (HTTP/HTTPS, retry 3회, exponential backoff)
    5. Supabase Storage 업로드 (bucket: law-attachments, path: {master_id}/{flSeq}.{ext})
    6. law_attachment INSERT/UPDATE (source_url 기반 upsert)

멱등성:
    같은 (version_id, source_url) 조합이 SUCCESS면 SKIP.
    --force 로 덮어쓰기, --retry-failed 로 FAILED 만 재시도.

실행:
    cd ~/dev/tai-api
    git pull origin main
    railway run python3 scripts/collect_law_attachments.py [옵션]
"""

import argparse
import hashlib
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

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

# ── 정규식: <첨부파일명> + <첨부파일링크>
RE_ATTACH_NAME = re.compile(
    r'<첨부파일명>\s*(?:<!\[CDATA\[(.+?)\]\]>|([^<]+?))\s*</첨부파일명>',
    re.DOTALL,
)
RE_ATTACH_LINK = re.compile(
    r'<첨부파일링크>\s*([^\s<]+)\s*</첨부파일링크>',
    re.DOTALL,
)

# 포맷별 content-type
CONTENT_TYPE_MAP = {
    'pdf': 'application/pdf',
    'hwp': 'application/x-hwp',
    'doc': 'application/octet-stream',
    'other': 'application/octet-stream',
}


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def extract_attachments(raw_xml: str):
    """raw_xml에서 (filename, url) 쌍 추출. 등장 순서로 1:1 짝지음."""
    names = []
    for m in RE_ATTACH_NAME.finditer(raw_xml):
        n = (m.group(1) or m.group(2) or "").strip()
        names.append(n)

    links = []
    for m in RE_ATTACH_LINK.finditer(raw_xml):
        u = m.group(1).strip().replace('\n', '').replace('\r', '')
        links.append(u)

    pairs = []
    for i, link in enumerate(links):
        name = names[i] if i < len(names) else f"unknown_{i}.bin"
        pairs.append((name, link))
    return pairs


def detect_format(filename: str) -> str:
    fn = (filename or "").lower()
    if fn.endswith('.pdf'):
        return 'pdf'
    if fn.endswith('.hwp') or fn.endswith('.hwpx'):
        return 'hwp'
    if fn.endswith('.docx') or fn.endswith('.doc'):
        return 'doc'
    return 'other'


def select_targets(pairs, include_hwp: bool = False):
    """PDF 우선. PDF 없으면 HWP. include_hwp=True 면 PDF+HWP 모두."""
    pdf_pairs = [(n, u) for n, u in pairs if detect_format(n) == 'pdf']
    hwp_pairs = [(n, u) for n, u in pairs if detect_format(n) == 'hwp']
    other_pairs = [(n, u) for n, u in pairs if detect_format(n) not in ('pdf', 'hwp')]

    if include_hwp:
        if pdf_pairs and hwp_pairs:
            return pdf_pairs + hwp_pairs
        return pdf_pairs or hwp_pairs or other_pairs

    if pdf_pairs:
        return pdf_pairs
    if hwp_pairs:
        return hwp_pairs
    return other_pairs or pairs


def build_storage_path(master_id: str, filename: str, source_url: str) -> str:
    """ASCII-safe Storage key 생성. 형식: {master_id}/{flSeq}.{ext}

    Supabase Storage(S3-호환)는 한글/공백/대괄호 등을 InvalidKey 로 거부함.
    →  master_id (UUID, ASCII safe) + flSeq (URL의 숫자 ID) + 확장자만 사용.
    원본 파일명은 DB의 source_file_name 컬럼에 보존되므로 식별 가능.
    """
    fmt = detect_format(filename)
    ext_map = {'pdf': 'pdf', 'hwp': 'hwp', 'doc': 'doc', 'other': 'bin'}
    ext = ext_map.get(fmt, 'bin')

    m = re.search(r'flSeq=(\d+)', source_url)
    if m:
        seq = m.group(1)
    else:
        seq = hashlib.md5(source_url.encode('utf-8')).hexdigest()[:12]

    return f"{master_id}/{seq}.{ext}"


def download_file(url: str, timeout: int = 60, max_retry: int = 3):
    """첨부파일 다운로드. (bytes, content_type) 반환 또는 raise."""
    last_err = None
    for attempt in range(max_retry):
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 TAI-Engineering-Bot',
                    'Accept': '*/*',
                },
            )
            resp.raise_for_status()
            content = resp.content
            if not content or len(content) < 100:
                raise RuntimeError(f"empty or too-small content ({len(content)} bytes)")
            return content, resp.headers.get('Content-Type', '')
        except Exception as e:
            last_err = e
            if attempt < max_retry - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"download failed after {max_retry} retries: {last_err}")


def upload_storage(storage_path: str, filename: str, content: bytes) -> str:
    """Supabase Storage 업로드. content-type은 파일명에서 자동 매핑.

    storage_path는 build_storage_path()로 ASCII-safe하게 미리 생성된 값.
    """
    fmt = detect_format(filename)
    content_type = CONTENT_TYPE_MAP.get(fmt, 'application/octet-stream')

    file_options = {
        "content-type": content_type,
        "upsert": "true",
    }
    try:
        sb.storage.from_(BUCKET).upload(storage_path, content, file_options=file_options)
    except Exception as e1:
        # 일부 supabase-py 버전은 upsert 옵션 안 먹음 → update fallback
        try:
            sb.storage.from_(BUCKET).update(
                storage_path, content,
                file_options={"content-type": content_type},
            )
        except Exception as e2:
            raise RuntimeError(f"storage upload failed: {e1} / update fallback: {e2}")
    return storage_path


def upsert_attachment_row(version_id: str, source_url: str, payload: dict):
    """(law_version_id, source_url) 기반 select-then-insert/update."""
    existing = sb.table("law_attachment").select("id").eq(
        "law_version_id", version_id
    ).eq("source_url", source_url).limit(1).execute()

    if existing.data:
        att_id = existing.data[0]["id"]
        sb.table("law_attachment").update(payload).eq("id", att_id).execute()
        return att_id
    else:
        full = {"law_version_id": version_id, "source_url": source_url, **payload}
        result = sb.table("law_attachment").insert(full).execute()
        return result.data[0]["id"] if result.data else None


# ────────────────────────────────────────────────────────────────
# 처리 단위
# ────────────────────────────────────────────────────────────────

def process_one(master: dict, args) -> dict:
    """한 master 처리. 첨부 N개 다운로드+업로드+DB INSERT."""
    master_id = master["id"]
    version_id = master["current_version_id"]
    law_name = master.get("law_name", "")
    raw_xml = master.get("raw_xml") or ""

    pairs = extract_attachments(raw_xml)
    if not pairs:
        return {
            "master_id": master_id, "law_name": law_name,
            "files": [{"status": "SKIPPED", "reason": "no <첨부파일링크> in raw_xml"}],
        }

    targets = select_targets(pairs, include_hwp=args.include_hwp)
    files_result = []

    for filename, url in targets:
        if not url.startswith('http'):
            url = ('http://law.go.kr' + url) if url.startswith('/') else ('http://' + url)

        # 멱등성
        if not args.force:
            existing = sb.table("law_attachment").select("download_status").eq(
                "law_version_id", version_id
            ).eq("source_url", url).limit(1).execute()
            if existing.data:
                cur_status = existing.data[0].get("download_status")
                if cur_status == "SUCCESS":
                    files_result.append({
                        "filename": filename, "url": url,
                        "status": "SKIPPED", "reason": "already SUCCESS"
                    })
                    continue
                if args.retry_failed and cur_status != "FAILED":
                    files_result.append({
                        "filename": filename, "url": url,
                        "status": "SKIPPED", "reason": f"--retry-failed: cur={cur_status}"
                    })
                    continue

        if args.dry_run:
            files_result.append({
                "filename": filename, "url": url,
                "status": "DRY_RUN", "format": detect_format(filename),
                "would_path": build_storage_path(master_id, filename, url),
            })
            continue

        fmt = detect_format(filename)
        meta_base = {
            "attachment_type_code": "ATTACHMENT_BODY",
            "attachment_title": filename[:500],
            "source_file_name": filename[:500],
            "file_format": fmt,
            "storage_bucket": BUCKET,
        }

        # Step 1: 다운로드
        try:
            content, content_type = download_file(url)
        except Exception as e:
            try:
                upsert_attachment_row(version_id, url, {
                    **meta_base,
                    "download_status": "FAILED",
                    "download_error": str(e)[:500],
                })
            except Exception:
                pass
            files_result.append({
                "filename": filename, "url": url,
                "status": "FAILED", "reason": f"download: {str(e)[:120]}"
            })
            continue

        # Step 2: Storage 업로드 (ASCII-safe path)
        storage_path = build_storage_path(master_id, filename, url)
        try:
            upload_storage(storage_path, filename, content)
        except Exception as e:
            try:
                upsert_attachment_row(version_id, url, {
                    **meta_base,
                    "file_size_bytes": len(content),
                    "download_status": "FAILED",
                    "download_error": f"storage: {str(e)[:400]}",
                })
            except Exception:
                pass
            files_result.append({
                "filename": filename, "url": url,
                "status": "FAILED", "reason": f"storage: {str(e)[:120]}"
            })
            continue

        # Step 3: DB upsert (SUCCESS)
        try:
            upsert_attachment_row(version_id, url, {
                **meta_base,
                "file_size_bytes": len(content),
                "download_status": "SUCCESS",
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "storage_path": storage_path,
                "download_error": None,
            })
        except Exception as e:
            files_result.append({
                "filename": filename, "url": url,
                "status": "FAILED", "reason": f"db: {str(e)[:120]}",
                "size": len(content), "path": storage_path
            })
            continue

        files_result.append({
            "filename": filename, "url": url,
            "status": "SUCCESS", "size": len(content), "path": storage_path,
            "format": fmt,
        })

    return {
        "master_id": master_id, "law_name": law_name,
        "files": files_result,
    }


# ────────────────────────────────────────────────────────────────
# 후보 수집
# ────────────────────────────────────────────────────────────────

def collect_candidates(args):
    """대상 master 목록 + raw_xml 까지 prefetch."""
    if args.master_id:
        m_resp = sb.table("law_master").select(
            "id,law_name,current_version_id,is_active"
        ).eq("id", args.master_id).limit(1).execute()
        masters = m_resp.data or []
    else:
        m_resp = sb.table("law_master").select(
            "id,law_name,current_version_id,is_active"
        ).eq("is_active", True).execute()
        masters = m_resp.data or []

    candidates = []
    print(f"  전체 master(active): {len(masters)}건. 필터링...")

    for i, m in enumerate(masters, 1):
        vid = m.get("current_version_id")
        if not vid:
            continue

        # article 수
        cnt = sb.table("law_article").select("id", count="exact").eq(
            "law_version_id", vid
        ).limit(1).execute()
        article_cnt = cnt.count or 0
        if article_cnt > 2 and not args.master_id:
            continue

        # raw_xml
        raw_resp = sb.table("law_content_raw").select("raw_xml").eq(
            "law_version_id", vid
        ).limit(1).execute()
        raw_xml = (raw_resp.data[0].get("raw_xml") if raw_resp.data else "") or ""
        if "<첨부파일링크>" not in raw_xml and not args.master_id:
            continue

        # 이미 처리된 첨부 상태
        if not args.force and not args.master_id:
            success_cnt = sb.table("law_attachment").select("id", count="exact").eq(
                "law_version_id", vid
            ).eq("download_status", "SUCCESS").limit(1).execute()
            failed_cnt = sb.table("law_attachment").select("id", count="exact").eq(
                "law_version_id", vid
            ).eq("download_status", "FAILED").limit(1).execute()

            if args.retry_failed:
                if (failed_cnt.count or 0) == 0:
                    continue
            else:
                if (success_cnt.count or 0) > 0 and (failed_cnt.count or 0) == 0:
                    continue

        candidates.append({**m, "raw_xml": raw_xml, "article_cnt": article_cnt})

        if i % 50 == 0:
            print(f"    {i}/{len(masters)} 검사. 후보 누적: {len(candidates)}")

    return candidates


# ────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--master-id", type=str, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--include-hwp", action="store_true",
                    help="PDF 있어도 HWP 까지 함께 (기본: PDF 우선/HWP fallback)")
    args = ap.parse_args()

    print("=" * 72)
    print("collect_law_attachments v2 — 첨부 본체 PDF/HWP 수집 (ASCII-safe key)")
    print("=" * 72)
    print(f"옵션: limit={args.limit} dry_run={args.dry_run} retry_failed={args.retry_failed} "
          f"force={args.force} workers={args.workers} include_hwp={args.include_hwp}")

    print("\nStep 1. 후보 수집")
    candidates = collect_candidates(args)
    if args.limit:
        candidates = candidates[:args.limit]
    print(f"  최종 처리 후보: {len(candidates)}건")

    if not candidates:
        print("처리 대상 없음. 종료.")
        return

    print("  처음 5건 미리보기:")
    for m in candidates[:5]:
        pairs = extract_attachments(m["raw_xml"])
        targets = select_targets(pairs, include_hwp=args.include_hwp)
        print(f"    - {m['law_name'][:50]}: {len(pairs)}개 첨부 (선택 {len(targets)})")

    print(f"\nStep 2. 처리 시작 (workers={args.workers})")
    summary = {"SUCCESS": 0, "FAILED": 0, "SKIPPED": 0, "DRY_RUN": 0}
    file_count = 0

    if args.workers <= 1:
        for i, m in enumerate(candidates, 1):
            try:
                result = process_one(m, args)
            except Exception as e:
                print(f"  [{i}/{len(candidates)}] EXCEPTION {m['law_name'][:40]}: {e}")
                summary["FAILED"] = summary.get("FAILED", 0) + 1
                continue
            files = result.get("files", [])
            ok = sum(1 for f in files if f.get("status") == "SUCCESS")
            fail = sum(1 for f in files if f.get("status") == "FAILED")
            skip = sum(1 for f in files if f.get("status") == "SKIPPED")
            dry = sum(1 for f in files if f.get("status") == "DRY_RUN")
            for f in files:
                summary[f.get("status", "FAILED")] = summary.get(f.get("status", "FAILED"), 0) + 1
                file_count += 1
            print(f"  [{i:3}/{len(candidates)}] {m['law_name'][:45]:45} "
                  f"ok={ok} fail={fail} skip={skip} dry={dry}")
            for f in files:
                if f.get("status") == "FAILED":
                    print(f"      FAIL: {f.get('filename', '?')[:50]} | {f.get('reason', '')[:80]}")
                elif f.get("status") == "SUCCESS":
                    print(f"      OK:   {f.get('path', '?')} ({f.get('size', 0)} bytes)")
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(process_one, m, args): m for m in candidates}
            for i, fut in enumerate(as_completed(futs), 1):
                m = futs[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    print(f"  [{i}/{len(candidates)}] EXCEPTION {m['law_name'][:40]}: {e}")
                    summary["FAILED"] = summary.get("FAILED", 0) + 1
                    continue
                files = result.get("files", [])
                ok = sum(1 for f in files if f.get("status") == "SUCCESS")
                fail = sum(1 for f in files if f.get("status") == "FAILED")
                for f in files:
                    summary[f.get("status", "FAILED")] = summary.get(f.get("status", "FAILED"), 0) + 1
                    file_count += 1
                print(f"  [{i:3}/{len(candidates)}] {m['law_name'][:45]:45} ok={ok} fail={fail}")

    print("\n" + "=" * 72)
    print("요약")
    print("=" * 72)
    print(f"  처리 master: {len(candidates)}")
    print(f"  처리 파일:   {file_count}")
    for k in ("SUCCESS", "FAILED", "SKIPPED", "DRY_RUN"):
        if summary.get(k, 0):
            print(f"  {k:10}: {summary[k]}")

    if not args.dry_run:
        print("\nDB 상태 검증 (law_attachment):")
        for s in ("SUCCESS", "FAILED", "PENDING", "DOWNLOADING", "SKIPPED"):
            cnt = sb.table("law_attachment").select("id", count="exact").eq(
                "download_status", s
            ).limit(1).execute()
            n = cnt.count or 0
            if n:
                print(f"  {s:12}: {n}")

    print("\n다음 단계:")
    print("  1) Supabase Storage 'law-attachments' 버킷에서 파일 확인")
    print("  2) FAILED 원인 분석 후 --retry-failed")
    print("  3) PDF/HWP 텍스트 추출 단계 (별도 스크립트)")


if __name__ == "__main__":
    main()
