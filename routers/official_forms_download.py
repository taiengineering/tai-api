"""routers/official_forms_download.py — FORM647 공식서식 원본 다운로드 프록시

GET /official-forms/{ek}/{file_type}/download

인증:   Bearer JWT (get_current_user)
게이트: LEG form647_review.form_snapshots.source_gate='PASS' AND service_sot_gate='PASS'
        source_binary_snapshots.private_storage_path IS NOT NULL
현재:   service_sot_gate=BLOCKED DB CHECK 강제 → 모든 요청 404

설계 원칙:
- LEG 조회 실패 시 항상 fail-closed (허용 없음)
- storage_path는 LEG DB에서만 수신, 'form647/' prefix 강제 검증
- ek/file_type은 LEG DB 조회 파라미터로만 사용 (경로 조작 불가)
- run_id 연계로 동일 ingest의 form_snapshot·binary_snapshot만 연결
- 서비스 키·경로는 응답·에러 로그에 노출하지 않음

WO: WO-TAI-DOC-M004-FORM647-DOWNLOAD-API-003
"""
import logging
import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from db.supabase_client import get_supabase
from routers.auth import get_current_user

log = logging.getLogger("official_forms_download")

router = APIRouter(prefix="/official-forms", tags=["official-forms-download"])

_BUCKET = "form-originals"
_STORAGE_PATH_PREFIX = "form647/"
_CONTENT_TYPE = {
    "hwp": "application/x-hwp",
    "pdf": "application/pdf",
}

_leg_client = None


def _get_leg_client():
    global _leg_client
    if _leg_client is None:
        from supabase import create_client
        url = os.environ.get("LEG_SUPABASE_URL")
        key = os.environ.get("LEG_SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError(
                "LEG_SUPABASE_URL and LEG_SUPABASE_SERVICE_ROLE_KEY required"
            )
        _leg_client = create_client(url, key)
    return _leg_client


@router.get("/{ek}/{file_type}/download")
def download_official_form(
    ek: str,
    file_type: str,
    current: dict = Depends(get_current_user),
):
    if file_type not in _CONTENT_TYPE:
        raise HTTPException(status_code=404, detail="not found")

    try:
        leg = _get_leg_client()
    except RuntimeError:
        log.error("LEG client unavailable — fail-closed")
        raise HTTPException(status_code=503, detail="service unavailable")

    try:
        snap_rows = (
            leg.schema("form647_review")
            .table("form_snapshots")
            .select("run_id,source_gate,service_sot_gate")
            .eq("ek", ek)
            .limit(1)
            .execute()
        ).data or []
    except Exception as exc:
        log.error("LEG form_snapshots query failed — fail-closed err_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="service unavailable")

    if not snap_rows:
        raise HTTPException(status_code=404, detail="not found")
    snap = snap_rows[0]
    if snap.get("source_gate") != "PASS":
        raise HTTPException(status_code=404, detail="not found")
    if snap.get("service_sot_gate") != "PASS":
        raise HTTPException(status_code=404, detail="not found")

    run_id = snap["run_id"]

    try:
        binary_rows = (
            leg.schema("form647_review")
            .table("source_binary_snapshots")
            .select("private_storage_path")
            .eq("run_id", run_id)
            .eq("ek", ek)
            .eq("file_type", file_type)
            .limit(1)
            .execute()
        ).data or []
    except Exception as exc:
        log.error("LEG source_binary_snapshots query failed — fail-closed err_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="service unavailable")

    if not binary_rows:
        raise HTTPException(status_code=404, detail="not found")
    storage_path = binary_rows[0].get("private_storage_path") or ""
    if not storage_path:
        raise HTTPException(status_code=404, detail="not found")
    if not storage_path.startswith(_STORAGE_PATH_PREFIX):
        log.error("storage_path prefix violation — fail-closed")
        raise HTTPException(status_code=404, detail="not found")

    try:
        data = get_supabase().storage.from_(_BUCKET).download(storage_path)
    except Exception as exc:
        log.error("storage download failed err_type=%s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="storage unavailable") from exc

    filename = os.path.basename(storage_path)
    encoded_filename = quote(filename, safe="")
    return Response(
        content=data,
        media_type=_CONTENT_TYPE[file_type],
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )
