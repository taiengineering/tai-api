"""WO-TAI-FORM647-PREVIEW-INTEGRATION-001 — 파일럿 2종 프리뷰 생성

대상:
  ref-f647-17649099  Pilot A (PDF + OLE2 HWP)
  ref-f647-3033503   Pilot B (HWPX)

대표 파일 선택 기준:
  PDF 있으면 PDF 우선, 없으면 HWP (OLE2/HWPX)

dry-run(기본):
  PNG를 로컬 output/preview_spike/ 에만 저장. Storage/DB 변경 없음.

--execute:
  PNG → reference-forms-preview 버킷 업로드
  reference_form_preview_artifacts INSERT
  reference_form_files.preview_artifact_id UPDATE
  (Owner 별도 승인 필요)

Storage 경로 규칙:
  previews/{form_id}/{file_id[:8]}.png  (reference-forms-preview 버킷)

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

# 파일럿 2종 — form_id, 파일 목록 (PDF 우선 정렬)
_PILOT_FORMS = [
    {
        "slug":    "ref-f647-17649099",
        "files": [
            {
                "file_id":    "6a3b84b6-f67f-4c57-9d54-2c958f0391b3",
                "format":     "pdf",
                "storage_path": f"form647/{_RUN_ID}/pdf/17649099_licbyl.pdf",
                "sha256":     "62d6e4f7981ebd122f5233d42d7283a1b517c7429b034a3bb030a3fc6c136c74",
            },
            {
                "file_id":    "a30d44d1-1806-4d57-8f5f-83c30f89b738",
                "format":     "hwp",
                "storage_path": f"form647/{_RUN_ID}/hwp/17649099_licbyl.hwp",
                "sha256":     "d6771324ae18d35302eacfc97fd5e300ff3d4f1a29c876150035b9ecbdd94906",
            },
        ],
    },
    {
        "slug":    "ref-f647-3033503",
        "files": [
            {
                "file_id":    "a4b8ddca-1b4a-4cb6-9a65-8e938d20d43f",
                "format":     "hwp",
                "storage_path": f"form647/{_RUN_ID}/hwp/3033503_admbyl.hwp",
                "sha256":     "9c39355c0cebe4df1d50985c81835e01d70953e1a1f784496bf061c18811fc06",
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
# 단일 서식 처리
# ---------------------------------------------------------------------------

def process_form(sb, pf: dict, dry_run: bool) -> dict:
    slug = pf["slug"]
    result = {
        "slug":           slug,
        "form_id":        None,
        "file_id":        None,
        "source_format":  None,
        "png_size":       None,
        "png_width":      None,
        "png_height":     None,
        "storage_path":   None,
        "preview_ref":    None,
        "out_png":        None,
        "verdict":        "FAIL",
        "error":          None,
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
            result["error"] = "form_not_found"
            return result
        form_id = content_row.data[0]["form_id"]
        result["form_id"] = form_id
    except Exception as exc:
        result["error"] = f"db_query_failed: {exc}"
        return result

    # 2. 대표 파일 선택
    rep = _pick_representative(pf["files"])
    result["file_id"] = rep["file_id"]
    log.info("[%s] 대표 파일: %s (%s)", slug, rep["format"], rep["storage_path"].split("/")[-1])

    # 3. 버킷에서 다운로드
    try:
        raw = sb.storage.from_(_SRC_BUCKET).download(rep["storage_path"])
    except Exception as exc:
        result["error"] = f"download_failed: {exc}"
        return result

    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != rep["sha256"]:
        result["error"] = f"sha256_mismatch: actual={actual_sha[:16]}"
        return result

    # 4. 프리뷰 생성
    try:
        preview = generate_preview(raw)
    except PreviewError as exc:
        result["error"] = f"{exc.code}: {exc}"
        return result

    result["source_format"] = preview.source_format
    result["png_size"]      = len(preview.png_bytes)
    result["png_width"]     = preview.width_px
    result["png_height"]    = preview.height_px

    # 5. 로컬 PNG 저장 (dry-run 포함 항상)
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_name = f"{slug.replace('/', '_')}_preview.png"
    out_path = _OUT_DIR / out_name
    out_path.write_bytes(preview.png_bytes)
    result["out_png"] = str(out_path)

    storage_path = _preview_storage_path(form_id, rep["file_id"])
    preview_ref  = f"storage://{_PREVIEW_BUCKET}/{storage_path}"
    result["storage_path"] = storage_path
    result["preview_ref"]  = preview_ref

    log.info("[%s] PNG %dx%d px, %d bytes → %s",
             slug, preview.width_px, preview.height_px,
             len(preview.png_bytes), out_name)

    if dry_run:
        result["verdict"] = "DRY_PASS"
        log.info("[DRY] %s  storage→ %s", slug, storage_path)
        return result

    # ── EXECUTE 경로 ────────────────────────────────────────────────────────

    # 6. Storage 업로드
    try:
        sb.storage.from_(_PREVIEW_BUCKET).upload(
            path=storage_path,
            file=preview.png_bytes,
            file_options={"content-type": "image/png", "upsert": False},
        )
        log.info("[OK] Storage upload: %s/%s", _PREVIEW_BUCKET, storage_path)
    except Exception as exc:
        result["error"] = f"storage_upload_failed: {exc}"
        return result

    # 7. reference_form_preview_artifacts INSERT
    try:
        art_res = (
            sb.table("reference_form_preview_artifacts")
            .insert({
                "form_id":           form_id,
                "preview_ref":       preview_ref,
                "source_file_sha256": rep["sha256"],
                "is_published":      False,
                "qa_status":         "PENDING",
            })
            .execute()
        )
        artifact_id = art_res.data[0]["id"]
        log.info("[OK] preview_artifact INSERT id=%s", artifact_id)
    except Exception as exc:
        result["error"] = f"artifact_insert_failed: {exc}"
        return result

    # 8. reference_form_files.preview_artifact_id UPDATE
    try:
        sb.table("reference_form_files") \
          .update({"preview_artifact_id": artifact_id}) \
          .eq("id", rep["file_id"]) \
          .execute()
        log.info("[OK] file preview_artifact_id → %s (file_id=%s)", artifact_id, rep["file_id"])
    except Exception as exc:
        result["error"] = f"file_update_failed: {exc}"
        return result

    result["verdict"] = "INSERTED"
    return result


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def run(dry_run: bool) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    mode = "DRY-RUN" if dry_run else "EXECUTE"
    log.info("=== generate_pilot_form647_previews  mode=%s ===", mode)

    sb = get_supabase()
    results = []

    for pf in _PILOT_FORMS:
        log.info("\n--- %s ---", pf["slug"])
        r = process_form(sb, pf, dry_run)
        results.append(r)

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
        print(f"  local_png     : {Path(r['out_png']).name if r['out_png'] else '-'}")
        print(f"  verdict       : {r['verdict']}")
        if r["error"]:
            print(f"  error         : {r['error']}")

    print(f"\nPNG 저장 위치: {_OUT_DIR}/")

    if dry_run:
        print("\n[dry-run 완료] --execute 로 Storage 업로드 및 DB 등록 실행 가능.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true",
                        help="Storage 업로드 및 DB 등록 실행 (기본: dry-run)")
    args = parser.parse_args()
    run(dry_run=not args.execute)
