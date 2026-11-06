"""WO-TAI-FORM647-FILE-RELEASE-PILOT-001-R2 — 파일럿 file_ref DB 업데이트

복사 완료된 3개 파일의 reference_form_files.file_ref를
  storage://form-originals/...  →  storage://reference-forms/...
로 갱신한다.

전제 조건:
  - pilot_form647_file_copy.py --execute 로 3개 파일이 reference-forms 버킷에 복사 완료
  - PILOT_STORAGE_COPY_VERIFIED = Owner 확인 완료

검증 절차 (업데이트 전):
  1. reference-forms 버킷에서 파일 다운로드
  2. SHA256 재계산 → DB 등록값과 대조 (BLOCK-SHA: 불일치 시 해당 파일 중단)

대상 (고정):
  file_id  6a3b84b6-f67f-4c57-9d54-2c958f0391b3  (Pilot A PDF)
  file_id  a30d44d1-1806-4d57-8f5f-83c30f89b738  (Pilot A HWP)
  file_id  a4b8ddca-1b4a-4cb6-9a65-8e938d20d43f  (Pilot B HWP)

사용법:
  python scripts/update_pilot_file_ref.py           # dry-run (기본)
  python scripts/update_pilot_file_ref.py --execute
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.supabase_client import get_supabase

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 대상 (고정 — pilot_form647_file_copy.py --execute 결과와 일치해야 함)
# ---------------------------------------------------------------------------

_RUN_ID = "form647-remediation-002-714df47a637e3e73"
_DST_BUCKET = "reference-forms"

_PILOT_UPDATES = [
    {
        "label":    "Pilot A PDF",
        "file_id":  "6a3b84b6-f67f-4c57-9d54-2c958f0391b3",
        "file_ref_before": f"storage://form-originals/form647/{_RUN_ID}/pdf/17649099_licbyl.pdf",
        "file_ref_after":  f"storage://reference-forms/form647/{_RUN_ID}/pdf/17649099_licbyl.pdf",
        "storage_path":    f"form647/{_RUN_ID}/pdf/17649099_licbyl.pdf",
        "registered_sha256": "62d6e4f7981ebd122f5233d42d7283a1b517c7429b034a3bb030a3fc6c136c74",
    },
    {
        "label":    "Pilot A HWP",
        "file_id":  "a30d44d1-1806-4d57-8f5f-83c30f89b738",
        "file_ref_before": f"storage://form-originals/form647/{_RUN_ID}/hwp/17649099_licbyl.hwp",
        "file_ref_after":  f"storage://reference-forms/form647/{_RUN_ID}/hwp/17649099_licbyl.hwp",
        "storage_path":    f"form647/{_RUN_ID}/hwp/17649099_licbyl.hwp",
        "registered_sha256": "d6771324ae18d35302eacfc97fd5e300ff3d4f1a29c876150035b9ecbdd94906",
    },
    {
        "label":    "Pilot B HWP",
        "file_id":  "a4b8ddca-1b4a-4cb6-9a65-8e938d20d43f",
        "file_ref_before": f"storage://form-originals/form647/{_RUN_ID}/hwp/3033503_admbyl.hwp",
        "file_ref_after":  f"storage://reference-forms/form647/{_RUN_ID}/hwp/3033503_admbyl.hwp",
        "storage_path":    f"form647/{_RUN_ID}/hwp/3033503_admbyl.hwp",
        "registered_sha256": "9c39355c0cebe4df1d50985c81835e01d70953e1a1f784496bf061c18811fc06",
    },
]


# ---------------------------------------------------------------------------
# 검증
# ---------------------------------------------------------------------------

def _verify_in_dst(sb, entry: dict) -> tuple[bool, str, int | None]:
    """reference-forms 버킷에서 파일을 다운로드하고 SHA256을 확인한다.
    반환: (sha256_match, actual_sha256_or_error, size_bytes_or_None)
    """
    try:
        raw = sb.storage.from_(_DST_BUCKET).download(entry["storage_path"])
    except Exception as exc:
        return False, f"DOWNLOAD_ERROR:{exc}", None

    size = len(raw)
    actual = hashlib.sha256(raw).hexdigest()
    return actual == entry["registered_sha256"], actual, size


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def run(dry_run: bool) -> None:
    sb = get_supabase()
    mode = "DRY-RUN" if dry_run else "EXECUTE"
    log.info("=== update_pilot_file_ref  mode=%s ===", mode)

    updated = skipped = errors = 0

    for entry in _PILOT_UPDATES:
        label   = entry["label"]
        file_id = entry["file_id"]

        # 1. reference-forms 버킷 SHA256 재확인
        sha_match, actual_sha, size = _verify_in_dst(sb, entry)

        if not sha_match:
            log.error("[BLOCK-SHA] %s  file_id=%s  actual=%s  registered=%s  size=%s",
                      label, file_id, actual_sha, entry["registered_sha256"], size)
            errors += 1
            continue

        log.info("[SHA-OK] %s  size=%d bytes  sha256=%s",
                 label, size, actual_sha[:16] + "...")

        if dry_run:
            log.info("[DRY] %s  file_id=%s", label, file_id)
            log.info("        before: %s", entry["file_ref_before"])
            log.info("        after : %s", entry["file_ref_after"])
            updated += 1
            continue

        # 2. DB 업데이트
        try:
            sb.table("reference_form_files") \
              .update({"file_ref": entry["file_ref_after"]}) \
              .eq("id", file_id) \
              .execute()
            log.info("[OK] %s  file_id=%s  →  %s", label, file_id, entry["file_ref_after"])
            updated += 1
        except Exception as exc:
            log.error("[ERR] %s  file_id=%s  —  %s", label, file_id, exc)
            errors += 1

    log.info("=== 완료: updated=%d  skipped=%d  errors=%d  dry_run=%s ===",
             updated, skipped, errors, dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="실제 DB 업데이트 (기본: dry-run)")
    args = parser.parse_args()
    run(dry_run=not args.execute)
