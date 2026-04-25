"""
safe_db_update.py — DB UPDATE 타입 에러 방어
================================================
Sonnet이 반환한 patch에 타입 불일치 필드가 있으면,
해당 필드만 제거하고 나머지는 정상 저장.

v1.0.0 (2026-04-25): 최초 작성 — reparse 에러 방지
"""
from datetime import datetime, timezone
from typing import Any, Dict, Tuple
import logging

_logger = logging.getLogger("safe-db-update")


def safe_update_master(
    supabase,
    row_id: str,
    patch: Dict[str, Any],
    rule_id: str = "",
) -> Tuple[bool, int, int]:
    """master_building_legal_rules 안전 업데이트.

    1차: 전체 patch를 한 번에 UPDATE 시도
    2차: 실패 시 필드별 개별 UPDATE (채울 수 있는 건 채움)

    Returns:
        (any_saved, saved_count, failed_count)
    """
    if not patch:
        return False, 0, 0

    now_iso = datetime.now(timezone.utc).isoformat()
    patch["updated_at"] = now_iso

    # 1차: 전체 batch UPDATE
    try:
        supabase.table("master_building_legal_rules").update(
            patch
        ).eq("id", row_id).execute()
        return True, len(patch) - 1, 0  # -1 for updated_at
    except Exception as batch_err:
        _logger.info(
            f"[safe-update] {rule_id} batch 실패, 필드별 재시도: "
            f"{str(batch_err)[:80]}"
        )

    # 2차: 필드별 개별 UPDATE
    saved = 0
    failed = 0
    failed_fields = []

    for key, val in list(patch.items()):
        if key == "updated_at":
            continue
        try:
            supabase.table("master_building_legal_rules").update({
                key: val,
                "updated_at": now_iso,
            }).eq("id", row_id).execute()
            saved += 1
        except Exception as field_err:
            failed += 1
            failed_fields.append(key)
            _logger.warning(
                f"[safe-update] {rule_id}.{key} 타입에러 skip: "
                f"{str(field_err)[:60]}"
            )

    if failed_fields:
        _logger.info(
            f"[safe-update] {rule_id} 결과: {saved}건 저장, "
            f"{failed}건 skip ({', '.join(failed_fields)})"
        )

    return saved > 0, saved, failed
