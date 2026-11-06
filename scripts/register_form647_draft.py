"""WO-TAI-FORM647-REFERENCE-CONTENT-PREP-002 — DRAFT 일괄 등록 스크립트

입력: scripts/output/form647_draft_registration.jsonl  (prepare_form647_reference_content.py 출력)
대상: deleted_from_law=False 인 항목만 처리 (579건)

기본값: dry-run (실제 INSERT 없음, 로그만 출력)
실제 실행: --execute (운영 DB INSERT — Owner 별도 승인 필요)

안전 장치:
  - canonical_slug LIKE 'ref-f647-%' 형식만 처리
  - 기존 슬러그 존재 시 SKIP (idempotent — 중복 실행 안전)
  - 기존 138종 (slug NOT LIKE 'ref-f647-%') 미접촉
  - deleted_from_law=True 항목 완전 제외

등록 테이블 순서 (형 의존성 순 — slug_registry 가 마지막 커밋 신호):
  1. reference_forms          — status=DRAFT, owner_approved=false
  2. reference_form_content   — canonical_slug, title, description, body_html
  3. reference_form_sources   — 출처, rights_status=REVIEW_REQUIRED
  4. reference_form_files     — 파일별 sha256, qa_status=PENDING (각 파일 단위)
  5. reference_form_slug_registry — 커밋 신호 (마지막, 완료 판정 기준)

부분 실패 복구:
  A. content 삽입 전 실패 → 이 실행 중 생성한 reference_forms 행 즉시 삭제 (고아 방지)
  B. content 삽입 후 실패 → 재실행 시 RESUME 경로: 누락 sources·파일 단위 보완 후 registry 등록

미등록 (공개 조건 미충족):
  - reference_form_approvals  — approval_status=PENDING 이므로 공개 뷰 미노출
  - reference_form_events     — 감사 로그 (등록 시 선택)

파일 저장소 주의:
  file_ref = storage://form-originals/... 형식
  현재 _ALLOWED_BUCKETS = {reference-forms, reference-forms-preview}
  → 표준 다운로드 엔드포인트는 form-originals 버킷 미지원
  → 파일 다운로드 활성화: reference-forms 버킷 이전 또는 _ALLOWED_BUCKETS 보완 필요 (별도 작업)

사용법:
  python3 scripts/register_form647_draft.py               # dry-run
  python3 scripts/register_form647_draft.py --execute     # 실제 실행 (Owner 승인 필요)
  python3 scripts/register_form647_draft.py --limit 5     # 처음 5건만 (검증용)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("form647_register")

_SLUG_PREFIX = "ref-f647-"
_JSONL_DEFAULT = Path(__file__).resolve().parent / "output" / "form647_draft_registration.jsonl"


# ---------------------------------------------------------------------------
# 로드
# ---------------------------------------------------------------------------

def load_drafts(jsonl_path: Path) -> list[dict]:
    if not jsonl_path.exists():
        sys.exit(f"ERROR: 입력 파일 없음 — {jsonl_path}\n"
                 "prepare_form647_reference_content.py 를 먼저 실행하세요.")
    rows = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# 안전 검사
# ---------------------------------------------------------------------------

def _assert_slug_safe(slug: str) -> None:
    if not slug.startswith(_SLUG_PREFIX):
        raise ValueError(f"슬러그가 '{_SLUG_PREFIX}' 로 시작하지 않음: {slug!r}")


def _registry_exists(sb, slug: str) -> bool:
    """slug 가 reference_form_slug_registry 에 존재하면 등록 완료로 판정."""
    try:
        res = (
            sb.table("reference_form_slug_registry")
            .select("slug")
            .eq("slug", slug)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception as exc:
        raise RuntimeError(f"레지스트리 확인 실패 ({slug}): {exc}") from exc


def _get_form_id_by_slug(sb, slug: str) -> str | None:
    """reference_form_content 에서 form_id 조회. 없으면 None."""
    try:
        res = (
            sb.table("reference_form_content")
            .select("form_id")
            .eq("canonical_slug", slug)
            .limit(1)
            .execute()
        )
        return res.data[0]["form_id"] if res.data else None
    except Exception as exc:
        raise RuntimeError(f"content form_id 조회 실패 ({slug}): {exc}") from exc


def _sources_exist(sb, form_id: str) -> bool:
    try:
        res = (
            sb.table("reference_form_sources")
            .select("id")
            .eq("form_id", form_id)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception as exc:
        raise RuntimeError(f"sources 확인 실패 ({form_id}): {exc}") from exc


def _get_registered_file_refs(sb, form_id: str) -> set[str]:
    """이미 등록된 file_ref 집합 반환 — 파일 단위 중복 방지용."""
    try:
        res = (
            sb.table("reference_form_files")
            .select("file_ref")
            .eq("form_id", form_id)
            .execute()
        )
        return {row["file_ref"] for row in (res.data or [])}
    except Exception as exc:
        raise RuntimeError(f"등록 파일 목록 조회 실패 ({form_id}): {exc}") from exc


# ---------------------------------------------------------------------------
# 등록 (단일 폼)
# ---------------------------------------------------------------------------

def _insert_reference_form(sb) -> str:
    """reference_forms 행 삽입 → form_id(UUID) 반환."""
    res = (
        sb.table("reference_forms")
        .insert({
            "status": "DRAFT",
            "owner_approved": False,
        })
        .execute()
    )
    if not res.data:
        raise RuntimeError("reference_forms INSERT 결과 없음")
    return res.data[0]["id"]


def _insert_content(sb, form_id: str, draft: dict) -> None:
    sb.table("reference_form_content").insert({
        "form_id": form_id,
        "lang": "ko",
        "canonical_slug": draft["canonical_slug"],
        "title": draft["title"],
        "description": draft.get("description", ""),
        "body_html": draft.get("body_html", ""),
    }).execute()


def _insert_slug_registry(sb, form_id: str, slug: str) -> None:
    sb.table("reference_form_slug_registry").insert({
        "slug": slug,
        "form_id": form_id,
        "slug_status": "CANONICAL",
    }).execute()


def _insert_source(sb, form_id: str, draft: dict) -> None:
    sb.table("reference_form_sources").insert({
        "form_id": form_id,
        "source_name": draft["source_name"],
        "source_url": draft.get("source_url") or None,
        "rights_status": "REVIEW_REQUIRED",
        "is_active": True,
    }).execute()


def _file_ref(draft: dict, file_type: str) -> str:
    """storage://form-originals/... 형식으로 file_ref 생성.
    참고: 표준 다운로드는 form-originals 버킷 미지원 — 버킷 이전 후 갱신 필요.
    """
    file_info = next((f for f in draft["files"] if f["file_type"] == file_type), None)
    if file_info is None:
        raise ValueError(f"파일 정보 없음: ek={draft['ek']} type={file_type}")
    return f"storage://form-originals/{file_info['storage_path']}"


def _insert_files(sb, form_id: str, draft: dict) -> None:
    for file_info in draft["files"]:
        file_ref = f"storage://form-originals/{file_info['storage_path']}"
        sb.table("reference_form_files").insert({
            "form_id": form_id,
            "file_ref": file_ref,
            "sha256": file_info["sha256"],
            "qa_status": "PENDING",
            "is_active": True,
        }).execute()


def _insert_files_missing(sb, form_id: str, draft: dict) -> None:
    """누락된 파일만 삽입 — 파일 단위 중복 방지 (RESUME 경로 전용)."""
    existing_refs = _get_registered_file_refs(sb, form_id)
    for file_info in draft["files"]:
        file_ref = f"storage://form-originals/{file_info['storage_path']}"
        if file_ref in existing_refs:
            continue
        sb.table("reference_form_files").insert({
            "form_id": form_id,
            "file_ref": file_ref,
            "sha256": file_info["sha256"],
            "qa_status": "PENDING",
            "is_active": True,
        }).execute()


def register_one(sb, draft: dict, dry_run: bool) -> str:
    """단일 폼을 등록한다.

    반환값: 'INSERTED' | 'RESUMED' | 'SKIPPED' | 'ERROR:...'

    완료 판정: reference_form_slug_registry 행 존재 여부 (마지막 삽입 = 커밋 신호).
    삽입 순서: reference_forms → content → sources → files → slug_registry(커밋).

    부분 실패 복구:
      A. content 삽입 전 실패: 이 실행에서 생성한 reference_forms 행 즉시 삭제
         → 재실행 시 고아 없는 깨끗한 신규 등록
      B. content 삽입 후 실패: 기존 form_id 로 누락 steps만 보완
         (sources 없으면 삽입, 파일은 미등록 file_ref 단위로 보완)
         → 재실행 시 RESUME 경로 처리
    """
    slug = draft["canonical_slug"]
    _assert_slug_safe(slug)

    # 완료 여부 = 레지스트리 존재 (마지막 커밋 신호)
    if _registry_exists(sb, slug):
        return "SKIPPED"

    if dry_run:
        file_types = [f["file_type"] for f in draft["files"]]
        log.info(
            "[DRY] 등록 예정: %s | %s | 파일=%s",
            slug, draft["title"][:40], file_types,
        )
        return "DRY"

    # RESUME: content 존재 + registry 미존재 → 누락 steps 보완
    existing_form_id = _get_form_id_by_slug(sb, slug)
    if existing_form_id:
        try:
            log.warning("[RESUME] 부분 실패 복구: %s (form_id=%s)", slug, existing_form_id)
            if not _sources_exist(sb, existing_form_id):
                _insert_source(sb, existing_form_id, draft)
            _insert_files_missing(sb, existing_form_id, draft)
            _insert_slug_registry(sb, existing_form_id, slug)
            return "RESUMED"
        except Exception as exc:
            return f"ERROR:{exc}"

    # 신규 등록
    form_id = _insert_reference_form(sb)
    after_content = False
    try:
        _insert_content(sb, form_id, draft)
        after_content = True
        _insert_source(sb, form_id, draft)
        _insert_files(sb, form_id, draft)
        _insert_slug_registry(sb, form_id, slug)  # ← 커밋 신호: 항상 마지막
        return "INSERTED"
    except Exception as exc:
        if not after_content:
            # content 미등록: 이 실행에서 생성한 reference_forms 행 정리 (고아 방지)
            try:
                sb.table("reference_forms").delete().eq("id", form_id).execute()
            except Exception as cleanup_exc:
                log.warning(
                    "[ORPHAN] reference_forms 고아 행 삭제 실패 (form_id=%s): %s",
                    form_id, cleanup_exc,
                )
        # after_content=True 인 경우: 재실행 시 RESUME 경로가 처리
        return f"ERROR:{exc}"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="FORM647 DRAFT 일괄 등록")
    parser.add_argument(
        "--jsonl",
        type=Path,
        default=_JSONL_DEFAULT,
        help="입력 JSONL 파일 경로",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="실제 DB INSERT 실행 (기본: dry-run)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="처리 건수 제한 (0=전체, 검증용)",
    )
    args = parser.parse_args()

    dry_run = not args.execute

    if dry_run:
        log.info("=== DRY-RUN 모드 (실제 INSERT 없음) ===")
        log.info("실제 실행: --execute 플래그 추가")
    else:
        log.warning("=== EXECUTE 모드 — 운영 DB INSERT 실행 ===")

    # 입력 로드
    all_drafts = load_drafts(args.jsonl)

    # 삭제 서식 제외 + slug 형식 검증
    eligible = [
        d for d in all_drafts
        if not d["flags"]["deleted_from_law"]
        and d["canonical_slug"].startswith(_SLUG_PREFIX)
    ]
    log.info("전체 %d건 → 등록 후보 %d건 (삭제 서식 %d건 제외)",
             len(all_drafts), len(eligible), len(all_drafts) - len(eligible))

    if args.limit > 0:
        eligible = eligible[:args.limit]
        log.info("--limit %d 적용: %d건만 처리", args.limit, len(eligible))

    if not dry_run:
        # 운영 DB 연결
        try:
            from db.supabase_client import get_supabase
            sb = get_supabase()
        except Exception as exc:
            sys.exit(f"ERROR: Supabase 연결 실패 — {exc}")
    else:
        # dry-run: 슬러그 존재 확인만 하려면 연결 필요 (--check-existing 없이는 스킵)
        sb = None

    counts = {"DRY": 0, "INSERTED": 0, "RESUMED": 0, "SKIPPED": 0, "ERROR": 0}

    for i, draft in enumerate(eligible, 1):
        slug = draft["canonical_slug"]
        if dry_run:
            # dry-run: DB 연결 없이 로그만
            file_types = [f["file_type"] for f in draft["files"]]
            log.info(
                "[DRY %d/%d] %s | %s | 파일=%s",
                i, len(eligible), slug, draft["title"][:40], file_types,
            )
            counts["DRY"] += 1
        else:
            outcome = register_one(sb, draft, dry_run=False)
            if outcome == "INSERTED":
                log.info("[OK   %d/%d] %s — %s", i, len(eligible), slug, draft["title"][:40])
                counts["INSERTED"] += 1
            elif outcome == "RESUMED":
                log.warning("[RSUM %d/%d] %s — 부분 실패 복구 완료", i, len(eligible), slug)
                counts["RESUMED"] += 1
            elif outcome == "SKIPPED":
                log.info("[SKIP %d/%d] %s — 이미 존재", i, len(eligible), slug)
                counts["SKIPPED"] += 1
            else:
                log.error("[ERR  %d/%d] %s — %s", i, len(eligible), slug, outcome)
                counts["ERROR"] += 1

    # 결과 요약
    print("\n=== 완료 ===")
    if dry_run:
        print(f"DRY-RUN: {counts['DRY']}건 처리 예정")
        print("실제 등록: --execute 플래그 추가")
    else:
        print(f"INSERTED: {counts['INSERTED']}건")
        print(f"RESUMED:  {counts['RESUMED']}건 (부분 실패 복구)")
        print(f"SKIPPED:  {counts['SKIPPED']}건 (이미 완료)")
        print(f"ERROR:    {counts['ERROR']}건")
        if counts["ERROR"] > 0:
            print("⚠ 오류 발생 — 로그를 확인하고 오류 항목을 개별 점검하세요.")

    print()
    print("=== 등록 후 남은 작업 ===")
    print("1. rights_status REVIEW_REQUIRED → CLEARED: 출처 권리 검토 완료 후")
    print("2. qa_status PENDING → QA_PASS: 파일 품질 검토 완료 후")
    print("3. owner_approved=true: Owner 승인 후")
    print("4. status DRAFT → PUBLISHED: 승인 완료 후")
    print("5. reference_form_approvals 등록: PUBLISHED 전환 시 필요")
    print("6. 파일 저장소 이전: form-originals → reference-forms 버킷 (다운로드 활성화)")


if __name__ == "__main__":
    main()
