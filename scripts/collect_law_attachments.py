#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collect_law_attachments.py — 첨부파일 본체 트랙 PDF/HWP 다운로드

목적:
    law.go.kr DRF API가 "공고/고시" 형태로 응답한 행정규칙은 본문이 첨부파일에만 있고
    XML <조문내용>은 비어있음. 이 케이스의 첨부파일을 다운로드 → Supabase Storage 보존
    → law_attachment 메타 저장. 이후 단계(텍스트 추출/의무 추출)의 전제 조건.

대상 (현재 DB 기준 116건):
    article_cnt <= 2 AND raw_xml에 <첨부파일링크> 존재 AND 아직 SUCCESS 첨부 없음
    예: 한국전기설비규정(KEC), 국가기술표준원 KS 표준 다수, KESCO 등

처리:
    1. 후보 master 목록 수집
    2. raw_xml에서 (첨부파일명, 첨부파일링크) 쌍 추출 (regex)
    3. PDF 우선, PDF 없으면 HWP fallback (둘 다 없으면 모든 형식)
    4. law.go.kr 다운로드 (HTTP/HTTPS, retry 3회, exponential backoff)
    5. Supabase Storage 업로드 (bucket: law-attachments, path: {master_id}/{filename})
    6. law_attachment INSERT/UPDATE (source_url 기반 upsert)

멱등성:
    같은 (version_id, source_url) 조합이 SUCCESS면 SKIP.
    --force 로 덮어쓰기, --retry-failed 로 FAILED 만 재시도.

실행:
    cd ~/dev/tai-api
    git pull origin main
    railway run python3 scripts/collect_law_attachments.py [옵션]

옵션:
    --limit N          : N건만 처리 (테스트)
    --master-id UUID   : 특정 master 만
    --dry-run          : 다운로드/업로드/INSERT 모두 안 하고 매니페스트만 출력
    --retry-failed     : download_status='FAILED' 인 첨부만 재시도
    --force            : 이미 SUCCESS여도 다시 다운로드
    --workers N        : 동시 다운로드 수 (기본 1, 로컬 IP 안전 고려)
    --include-hwp      : PDF 있어도 HWP까지 함께 다운로드 (기본은 PDF 우선)

환경변수:
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (Mac 로컬 .env 또는 railway run)

원칙:
    - 다운로드/업로드/DB 어느 단계에서 실패해도 다음 master 로 진행 (전체 중단 X)
    - FAILED 도 law_attachment 에 기록 (download_error) → 재시도 가능
    - 본 스크립트는 다운로드까지. 텍스트 추출/의무 추출은 별도 단계.
"""

import argparse
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# .env + 프록시 무력화 (Mac 로컬에서 railway run 패턴 호환)
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

# ── 정규식: <첨부파일명> + <첨부파일링크> 추출 (CDATA / 일반 텍스트 모두)
RE_ATTACH_NAME = re.compile(
    r'<첨부파일명>\s*(?:<!\[CDATA\[(.+?)\]\]>|([^<]+?))\s*</첨부파일명>',
    re.DOTALL,
)
RE_ATTACH_LINK = re.compile(
    r'<첨부파일링크>\s*([^\s<]+)\s*</첨부파일링크>',
    re.DOTALL,
)


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


def safe_filename(name: str) -> str:
    """파일시스템/Storage 안전한 이름. 한글 유지, 위험문자 _ 치환, 200byte 이내."""
    out = re.sub(r'[/\\:*?"<>|\x00-\x1f]', '_', name or "untitled")
    out = out.strip('. ')
    if not out:
        out = "untitled.bin"
    # 200 byte 이내
    enc = out.encode('utf-8')
    if len(enc) > 200:
        base, dot, ext = out.rpartition('.')
        if dot:
            keep = 200 - len(ext.encode('utf-8')) - 1
            base_enc = base.encode('utf-8')[:max(keep, 1)]
            out = base_enc.decode('utf-8', errors='ignore') + '.' + ext
        else:
            out = enc[:200].decode('utf-8', errors='ignore')
    return out


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


def upload_storage(master_id: str, filename: str, content: bytes, content_type: str = None) -> str:
    """Supabase Storage 업로드. 같은 path 있으면 update."""
    safe = safe_filename(filename)
    path = f"{master_id}/{safe}"

    # supabase-py upload는 file_options에 upsert 지원
    file_options = {"upsert": "true"}
    if content_type:
        file_options["content-type"] = content_type
    try:
        sb.storage.from_(BUCKET).upload(path, content, file_options=file_options)
    except Exception as e1:
        # 일부 버전은 upsert 안 먹어서 update fallback
        try:
            sb.storage.from_(BUCKET).update(path, content, file_options={"content-type": content_type or "application/octet-stream"})
        except Exception as e2:
            raise RuntimeError(f"storage upload failed: {e1} / update: {e2}")
    return path


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
                "status": "DRY_RUN", "format": detect_format(filename)
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

        # Step 2: Storage 업로드
        try:
            storage_path = upload_storage(master_id, filename, content, content_type)
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
                # SUCCESS가 이미 있으면 SKIP (전부 처리 완료된 것)
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
    print("collect_law_attachments — 첨부 본체 PDF/HWP 수집")
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

    # 미리보기 (처음 5건)
    print("  처음 5건 미리보기:")
    for m in candidates[:5]:
        pairs = extract_attachments(m["raw_xml"])
        targets = select_targets(pairs, include_hwp=args.include_hwp)
        print(f"    - {m['law_name'][:50]}: {len(pairs)}개 첨부 (선택 {len(targets)})")

    # 처리
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

    # 요약
    print("\n" + "=" * 72)
    print("요약")
    print("=" * 72)
    print(f"  처리 master: {len(candidates)}")
    print(f"  처리 파일:   {file_count}")
    for k in ("SUCCESS", "FAILED", "SKIPPED", "DRY_RUN"):
        if summary.get(k, 0):
            print(f"  {k:10}: {summary[k]}")

    # DB 상태 검증
    if not args.dry_run:
        print("\nDB 상태 검증 (law_attachment):")
        for s in ("SUCCESS", "FAILED", "PENDING", "DOWNLOADING", "SKIPPED"):
            cnt = sb.table("law_attachment").select("id", count="exact").eq(
                "download_status", s
            ).limit(1).execute()
            n = cnt.count or 0
            if n:
                print(f"  {s:12}: {n}")

    print("\n다음 단계 (이번 작업 완료 후):")
    print("  1) 다운로드 결과 검토 (Supabase Storage 'law-attachments' 버킷)")
    print("  2) FAILED 원인 분석 후 --retry-failed")
    print("  3) PDF/HWP 텍스트 추출 단계 (별도 스크립트)")
    print("  4) 의무 추출 (LLM, 4단계)")


if __name__ == "__main__":
    main()
