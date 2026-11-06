"""WO-TAI-FORM647-PREVIEW-INTEGRATION-001 R1 — 파일럿 2종 프리뷰 생성 (안전 보정)

대상:
  ref-f647-17649099  Pilot A (PDF + OLE2 HWP)
  ref-f647-3033503   Pilot B (HWPX)

대표 파일 선택 기준:
  PDF 있으면 PDF 우선, 없으면 HWP (OLE2/HWPX)

dry-run(기본):
  PNG를 로컬 output/preview_spike/ 에만 저장. Storage/DB 변경 없음.

--execute:
  전체 사전검증(모든 서식) 완료 후에만 쓰기 시작.
  PNG → reference-forms-preview 버킷 업로드 (동일 파일이면 재사용, 다른 파일이면 중단)
  reference_form_preview_artifacts INSERT (동일 SHA256 artifact 있으면 재사용)
  reference_form_files.preview_artifact_id UPDATE (1건 검증)
  각 단계 실패 시 완료/미완료 상태 보고 후 프로세스 종료.

Storage 경로 규칙:
  previews/{form_id}/{file_id}.png  (reference-forms-preview 버킷, 전체 UUID)

사용법:
  GOTENBERG_URL=http://localhost:3500 python3 scripts/generate_pilot_form647_previews.py
  GOTENBERG_URL=http://localhost:3500 python3 scripts/generate_pilot_form647_previews.py --execute
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.supabase_client import get_supabase
from services.reference_form_preview_gen_svc import generate_preview, PreviewError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_SRC_BUCKET     = "reference-forms"
_PREVIEW_BUCKET = "reference-forms-preview"
_RUN_ID         = "form647-remediation-002-714df47a637e3e73"
_OUT_DIR        = Path(__file__).resolve().parent / "output" / "preview_spike"

_PILOT_FORMS = [
    {
        "slug":  "ref-f647-17649099",
        "files": [
            {
                "file_id":      "6a3b84b6-f67f-4c57-9d54-2c958f0391b3",
                "format":       "pdf",
                "storage_path": f"form647/{_RUN_ID}/pdf/17649099_licbyl.pdf",
                "sha256":       "62d6e4f7981ebd122f5233d42d7283a1b517c7429b034a3bb030a3fc6c136c74",
            },
            {
                "file_id":      "a30d44d1-1806-4d57-8f5f-83c30f89b738",
                "format":       "hwp",
                "storage_path": f"form647/{_RUN_ID}/hwp/17649099_licbyl.hwp",
                "sha256":       "d6771324ae18d35302eacfc97fd5e300ff3d4f1a29c876150035b9ecbdd94906",
            },
        ],
    },
    {
        "slug":  "ref-f647-3033503",
        "files": [
            {
                "file_id":      "a4b8ddca-1b4a-4cb6-9a65-8e938d20d43f",
                "format":       "hwp",
                "storage_path": f"form647/{_RUN_ID}/hwp/3033503_admbyl.hwp",
                "sha256":       "9c39355c0cebe4df1d50985c81835e01d70953e1a1f784496bf061c18811fc06",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _pick_representative(files: list[dict]) -> dict:
    """PDF 우선, 없으면 첫 번째 파일."""
    for f in files:
        if f["format"] == "pdf":
            return f
    return files[0]


def _preview_storage_path(form_id: str, file_id: str) -> str:
    return f"previews/{form_id}/{file_id}.png"


# ---------------------------------------------------------------------------
# 사전검증 (Pre-flight) — 쓰기 없음
# ---------------------------------------------------------------------------

def _preflight_all(sb, pilot_forms: list[dict]) -> list[dict]:
    """
    모든 파일럿 서식에 대해 사전검증을 실행한다.
    - Storage 다운로드 + SHA256 대조
    - PNG 생성 테스트
    한 건이라도 실패하면 RuntimeError를 발생시키고 쓰기를 시작하지 않는다.
    """
    results = []
    for pf in pilot_forms:
        log.info("[PREFLIGHT] %s", pf["slug"])
        r = _preflight_one(sb, pf)
        results.append(r)
        if r["error"]:
            raise RuntimeError(
                f"[PREFLIGHT FAIL] {pf['slug']}: {r['error']}\n"
                "  → 모든 파일럿 사전검증이 완료될 때까지 쓰기를 시작하지 않습니다."
            )
        log.info(
            "[PREFLIGHT OK] %s  form_id=%s  png=%dx%d px  source_format=%s",
            pf["slug"], r["form_id"],
            r["preview"].width_px, r["preview"].height_px,
            r["preview"].source_format,
        )
    return results


def _preflight_one(sb, pf: dict) -> dict:
    slug = pf["slug"]
    result: dict = {
        "slug": slug, "form_id": None, "rep": None,
        "preview": None, "storage_path": None, "error": None,
    }

    # 1. form_id 조회
    try:
        content_row = (
            sb.table("reference_form_content")
            .select("form_id")
            .eq("canonical_slug", slug)
            .limit(1)
            .execute()
        )
        if not content_row.data:
            result["error"] = "form_not_found_in_db"
            return result
        result["form_id"] = content_row.data[0]["form_id"]
    except Exception as exc:
        result["error"] = f"db_query_failed: {exc}"
        return result

    # 2. 대표 파일 선택 + Storage 다운로드
    rep = _pick_representative(pf["files"])
    result["rep"] = rep
    try:
        raw = sb.storage.from_(_SRC_BUCKET).download(rep["storage_path"])
    except Exception as exc:
        result["error"] = f"download_failed: {exc}"
        return result

    # 3. SHA256 대조
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != rep["sha256"]:
        result["error"] = f"sha256_mismatch: actual={actual_sha[:16]}…"
        return result

    # 4. PNG 생성 검증
    try:
        preview = generate_preview(raw)
    except PreviewError as exc:
        result["error"] = f"{exc.code}: {exc}"
        return result

    result["preview"] = preview
    result["storage_path"] = _preview_storage_path(result["form_id"], rep["file_id"])
    return result


# ---------------------------------------------------------------------------
# Storage — 멱등 업로드
# ---------------------------------------------------------------------------

def _storage_upload_or_reuse(sb, storage_path: str, png_bytes: bytes) -> str:
    """
    PNG를 업로드하거나 동일 파일이 이미 있으면 재사용한다.
    Returns 'UPLOADED' | 'REUSED'.
    경로에 다른 파일이 있으면 RuntimeError를 발생시킨다(덮어쓰기 금지).
    """
    try:
        existing = sb.storage.from_(_PREVIEW_BUCKET).download(storage_path)
        if hashlib.sha256(existing).hexdigest() == hashlib.sha256(png_bytes).hexdigest():
            log.info("[STORAGE] 동일 PNG 이미 존재 → REUSED: %s", storage_path)
            return "REUSED"
        raise RuntimeError(
            f"STORAGE_CONFLICT: 경로에 다른 PNG가 이미 존재합니다 — 덮어쓰기 금지: {storage_path}"
        )
    except RuntimeError:
        raise
    except Exception:
        pass  # 파일 미존재 → 업로드

    sb.storage.from_(_PREVIEW_BUCKET).upload(
        path=storage_path,
        file=png_bytes,
        file_options={"content-type": "image/png", "upsert": False},
    )
    log.info("[STORAGE] 업로드 완료: %s/%s", _PREVIEW_BUCKET, storage_path)
    return "UPLOADED"


# ---------------------------------------------------------------------------
# DB artifact — 멱등 INSERT
# ---------------------------------------------------------------------------

def _artifact_insert_or_reuse(
    sb, form_id: str, preview_ref: str, source_sha256: str
) -> tuple[str, str]:
    """
    동일 (form_id, source_sha256) artifact가 있으면 재사용,
    없으면 INSERT(qa_status=PENDING, is_published=false).
    Returns (artifact_id, action) — action='INSERTED'|'REUSED'.
    preview_ref 충돌 시 RuntimeError.
    """
    existing = (
        sb.table("reference_form_preview_artifacts")
        .select("id,preview_ref")
        .eq("form_id", form_id)
        .eq("source_file_sha256", source_sha256)
        .limit(1)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        if row["preview_ref"] == preview_ref:
            log.info("[ARTIFACT] 동일 artifact 이미 존재 → REUSED: id=%s", row["id"])
            return row["id"], "REUSED"
        raise RuntimeError(
            f"ARTIFACT_CONFLICT: 동일 form_id+SHA256에 다른 preview_ref가 등록되어 있습니다.\n"
            f"  existing: {row['preview_ref']}\n"
            f"  new:      {preview_ref}"
        )

    res = (
        sb.table("reference_form_preview_artifacts")
        .insert({
            "form_id":            form_id,
            "preview_ref":        preview_ref,
            "source_file_sha256": source_sha256,
            "is_published":       False,
            "qa_status":          "PENDING",
        })
        .execute()
    )
    artifact_id = res.data[0]["id"]
    log.info("[ARTIFACT] INSERT 완료: id=%s", artifact_id)
    return artifact_id, "INSERTED"


# ---------------------------------------------------------------------------
# DB file link — 멱등 UPDATE
# ---------------------------------------------------------------------------

def _link_artifact_to_file(sb, file_id: str, artifact_id: str) -> str:
    """
    reference_form_files.preview_artifact_id를 artifact_id로 연결한다.
    이미 같은 artifact가 연결되어 있으면 'ALREADY_LINKED' 반환.
    다른 artifact가 연결되어 있으면 RuntimeError(변경 금지).
    UPDATE 결과가 정확히 1건이 아니면 RuntimeError.
    Returns 'LINKED' | 'ALREADY_LINKED'.
    """
    current = (
        sb.table("reference_form_files")
        .select("id,preview_artifact_id")
        .eq("id", file_id)
        .limit(1)
        .execute()
    )
    if not current.data:
        raise RuntimeError(f"FILE_NOT_FOUND: file_id={file_id}")

    current_artifact_id = current.data[0].get("preview_artifact_id")

    if current_artifact_id == artifact_id:
        log.info("[LINK] 이미 연결됨 → ALREADY_LINKED: file_id=%s artifact_id=%s", file_id, artifact_id)
        return "ALREADY_LINKED"
    if current_artifact_id is not None:
        raise RuntimeError(
            f"FILE_CONFLICT: 파일이 이미 다른 artifact에 연결되어 있습니다.\n"
            f"  file_id:          {file_id}\n"
            f"  existing artifact: {current_artifact_id}\n"
            f"  new artifact:      {artifact_id}"
        )

    update_res = (
        sb.table("reference_form_files")
        .update({"preview_artifact_id": artifact_id})
        .eq("id", file_id)
        .execute()
    )
    if not update_res.data or len(update_res.data) != 1:
        raise RuntimeError(
            f"UPDATE_ROW_COUNT_ERROR: preview_artifact_id UPDATE가 "
            f"{len(update_res.data) if update_res.data else 0}건을 반환했습니다 "
            f"(기대 1건). file_id={file_id}"
        )
    log.info("[LINK] UPDATE 완료: file_id=%s → artifact_id=%s", file_id, artifact_id)
    return "LINKED"


# ---------------------------------------------------------------------------
# 단일 서식 처리
# ---------------------------------------------------------------------------

def _execute_one(sb, preflight: dict) -> dict:
    """
    사전검증을 통과한 단일 서식에 대해 Storage + DB 쓰기를 수행한다.
    실패 시 완료/미완료 단계를 steps에 기록하고 error를 반환한다.
    """
    slug         = preflight["slug"]
    form_id      = preflight["form_id"]
    rep          = preflight["rep"]
    preview      = preflight["preview"]
    storage_path = preflight["storage_path"]

    preview_ref = f"storage://{_PREVIEW_BUCKET}/{storage_path}"
    steps: dict[str, str] = {
        "storage": "PENDING",
        "artifact_insert": "PENDING",
        "file_link": "PENDING",
    }
    result = {
        "slug":           slug,
        "form_id":        form_id,
        "file_id":        rep["file_id"],
        "source_format":  preview.source_format,
        "png_size":       len(preview.png_bytes),
        "png_width":      preview.width_px,
        "png_height":     preview.height_px,
        "storage_path":   storage_path,
        "preview_ref":    preview_ref,
        "artifact_id":    None,
        "steps":          steps,
        "verdict":        "FAIL",
        "error":          None,
    }

    # Step 1: Storage
    try:
        storage_action = _storage_upload_or_reuse(sb, storage_path, preview.png_bytes)
        steps["storage"] = storage_action
    except Exception as exc:
        steps["storage"] = "FAIL"
        result["error"] = f"storage_failed: {exc}"
        return result

    # Step 2: Artifact INSERT
    try:
        artifact_id, artifact_action = _artifact_insert_or_reuse(
            sb, form_id, preview_ref, rep["sha256"]
        )
        result["artifact_id"] = artifact_id
        steps["artifact_insert"] = artifact_action
    except Exception as exc:
        steps["artifact_insert"] = "FAIL"
        result["error"] = f"artifact_failed: {exc}"
        return result

    # Step 3: File link UPDATE
    try:
        link_action = _link_artifact_to_file(sb, rep["file_id"], artifact_id)
        steps["file_link"] = link_action
    except Exception as exc:
        steps["file_link"] = "FAIL"
        result["error"] = f"file_link_failed: {exc}"
        return result

    result["verdict"] = "INSERTED"
    return result


def _process_dry_run(preflight: dict) -> dict:
    """DRY-RUN: 사전검증 결과를 그대로 반환. 쓰기 없음."""
    preview = preflight["preview"]
    return {
        "slug":           preflight["slug"],
        "form_id":        preflight["form_id"],
        "file_id":        preflight["rep"]["file_id"],
        "source_format":  preview.source_format,
        "png_size":       len(preview.png_bytes),
        "png_width":      preview.width_px,
        "png_height":     preview.height_px,
        "storage_path":   preflight["storage_path"],
        "preview_ref":    f"storage://{_PREVIEW_BUCKET}/{preflight['storage_path']}",
        "artifact_id":    None,
        "steps":          {},
        "verdict":        "DRY_PASS",
        "error":          None,
    }


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def run(dry_run: bool) -> int:
    """
    Returns 0 on full success, 1 on any failure.
    """
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    mode = "DRY-RUN" if dry_run else "EXECUTE"
    log.info("=== generate_pilot_form647_previews  mode=%s ===", mode)

    sb = get_supabase()

    # Phase 1: 모든 서식 사전검증 (쓰기 없음)
    log.info("--- Phase 1: 사전검증 (전체 %d건) ---", len(_PILOT_FORMS))
    try:
        preflights = _preflight_all(sb, _PILOT_FORMS)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1

    # 로컬 PNG 저장 (dry-run 포함 항상)
    for pf_data in preflights:
        out_name = f"{pf_data['slug'].replace('/', '_')}_preview.png"
        out_path = _OUT_DIR / out_name
        out_path.write_bytes(pf_data["preview"].png_bytes)
        log.info("[PNG] 로컬 저장: %s", out_path.name)

    if dry_run:
        results = [_process_dry_run(pf_data) for pf_data in preflights]
    else:
        # Phase 2: 쓰기 (사전검증 전체 통과 후)
        log.info("--- Phase 2: Storage + DB 쓰기 ---")
        results = []
        any_fail = False
        for pf_data in preflights:
            log.info("--- %s ---", pf_data["slug"])
            r = _execute_one(sb, pf_data)
            results.append(r)
            if r["verdict"] == "FAIL":
                any_fail = True
                log.error(
                    "[FAIL] %s  error=%s\n  완료 단계: %s\n  미완료 단계: %s",
                    r["slug"], r["error"],
                    {k: v for k, v in r["steps"].items() if v not in ("PENDING", "FAIL")},
                    {k: v for k, v in r["steps"].items() if v in ("PENDING", "FAIL")},
                )

    # 결과 출력
    print("\n" + "=" * 60)
    print(f"PILOT PREVIEW 결과 ({mode})")
    print("=" * 60)
    for r in results:
        ok = r["verdict"] in ("DRY_PASS", "INSERTED")
        status = "✓" if ok else "✗"
        print(f"\n{status} {r['slug']}")
        print(f"  form_id       : {r['form_id']}")
        print(f"  file_id       : {r['file_id']}")
        print(f"  source_format : {r['source_format']}")
        if r["png_width"]:
            print(f"  png           : {r['png_width']}×{r['png_height']} px, {r['png_size']:,} bytes")
        print(f"  preview_ref   : {r['preview_ref']}")
        if not dry_run and r.get("steps"):
            print(f"  steps         : {r['steps']}")
        print(f"  verdict       : {r['verdict']}")
        if r["error"]:
            print(f"  error         : {r['error']}")

    print(f"\nPNG 저장 위치: {_OUT_DIR}/")

    if dry_run:
        print("\n[dry-run 완료] --execute 로 Storage 업로드 및 DB 등록 실행 가능.")

    fail_count = sum(1 for r in results if r["verdict"] == "FAIL")
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute", action="store_true",
        help="Storage 업로드 및 DB 등록 실행 (기본: dry-run)"
    )
    args = parser.parse_args()
    sys.exit(run(dry_run=not args.execute))
