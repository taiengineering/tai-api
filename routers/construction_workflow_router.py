import io
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from db.supabase_client import get_supabase
from schemas.construction import (
    CorrectivePatch,
    EntryPatch,
    InspectionCreate,
    InspectionPatch,
    ProcessCreate,
    ProcessPatch,
    PtwPatch,
    SafetyManagerBody,
    WorkCreate,
    WorkPatch,
    WorkerCreate,
    WorkerPatch,
)
from services.construction_helpers import calc_safety_manager
from services.construction_status_svc import (
    build_corrective_update_payload,
    build_entry_update_payload,
    build_ptw_update_payload,
)
from services.construction_svc import (
    create_record,
    get_record_or_none,
    normalize_date_fields,
    prepare_inspection_payload,
    run_list_query,
    send_fcm_inspection_alert,
    soft_delete_record,
    update_record,
)

router = APIRouter(tags=["건설안전"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_JOB_CODE_TO_NAME = {
    "WJT001": "사무직", "WJT002": "생산직(일반)", "WJT003": "용접공",
    "WJT004": "철근공", "WJT005": "목공", "WJT006": "비계공",
    "WJT007": "전기공", "WJT008": "배관공", "WJT009": "도장공",
    "WJT010": "운전기사", "WJT011": "지게차 운전원", "WJT012": "크레인 운전원",
    "WJT013": "화학물질 취급", "WJT014": "고소작업자", "WJT015": "밀폐공간 작업자",
    "WJT016": "관리감독자", "WJT017": "안전보건관리담당자", "WJT018": "협력업체 작업자",
    "WJT019": "일용직", "WJT020": "기타",
}
_JOB_NAME_TO_CODE = {
    "사무직": "WJT001", "사무": "WJT001", "생산직": "WJT002", "생산": "WJT002",
    "용접공": "WJT003", "용접": "WJT003", "철근공": "WJT004", "철근": "WJT004",
    "타설공": "WJT004", "목공": "WJT005", "형틀목공": "WJT005", "비계공": "WJT006",
    "비계": "WJT006", "전기공": "WJT007", "전기": "WJT007", "배관공": "WJT008",
    "설비공": "WJT008", "배관": "WJT008", "도장공": "WJT009", "도장": "WJT009",
    "운전기사": "WJT010", "굴착기운전": "WJT010", "크레인 운전원": "WJT012",
    "관리감독자": "WJT016", "현장소장": "WJT016", "안전보건관리담당자": "WJT017",
    "안전관리자": "WJT017", "협력업체 작업자": "WJT018", "신호수": "WJT018",
    "일용직": "WJT019", "기타": "WJT020",
}
_EMP_TYPE_MAP = {
    "직접": "DIRECT", "직영": "DIRECT", "정규": "DIRECT",
    "하도급": "SUBCON", "협력": "SUBCON", "하청": "SUBCON",
    "원청": "PRIMARY", "원청직영": "PRIMARY",
}


def _match_job_code(job_name: str) -> str:
    if not job_name:
        return "WJT020"
    s = job_name.strip()
    if s in _JOB_NAME_TO_CODE:
        return _JOB_NAME_TO_CODE[s]
    for k, v in _JOB_NAME_TO_CODE.items():
        if k in s or s in k:
            return v
    return "WJT020"


def _resolve_group_id_site(supabase, site_id: str, dept_name: str, team_name: str, group_name: str):
    """건설 org: construction_site_id → departments → teams → groups 로 group_id 해석. 실패 시 None."""
    if not group_name:
        return None
    dept_id = None
    if dept_name:
        d = supabase.table("departments").select("id").eq("construction_site_id", site_id).eq("department_name", dept_name).limit(1).execute()
        dept_id = d.data[0]["id"] if d.data else None
    team_id = None
    if team_name:
        tq = supabase.table("teams").select("id").eq("team_name", team_name)
        if dept_id:
            tq = tq.eq("department_id", dept_id)
        t = tq.limit(1).execute()
        team_id = t.data[0]["id"] if t.data else None
    gq = supabase.table("groups").select("id, team_id").eq("group_name", group_name)
    if team_id:
        gq = gq.eq("team_id", team_id)
    g = gq.execute()
    rows = g.data or []
    if not rows:
        return None
    return rows[0]["id"]


def _validate_uuid(value: str) -> str:
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        raise HTTPException(status_code=400, detail="유효하지 않은 ID 형식입니다.")


def _alias_inspection_row(row: dict) -> dict:
    """화면 계약 호환(LEDGER §62 표시분): DB 컬럼명에 화면이 읽는 별칭을 병기(원본 유지).
    목록은 item.inspection_datetime 을, 상세는 defect_details·corrective_due 를 읽어
    값이 있어도 '-'/created_at 으로 떨어지던 것을 해소한다.
    ※ inspector_name(이름) 은 inspector_id(uuid)에서 채울 수 없어 여기서 다루지 않는다(결정 대기)."""
    if not isinstance(row, dict):
        return row
    if row.get("inspection_datetime") is None and row.get("inspection_date") is not None:
        row["inspection_datetime"] = row.get("inspection_date")
    if row.get("defect_details") is None and row.get("defect_items") is not None:
        row["defect_details"] = row.get("defect_items")
    if row.get("corrective_due") is None and row.get("corrective_deadline") is not None:
        row["corrective_due"] = row.get("corrective_deadline")
    return row


def _ptw_number(site_id: str, supabase) -> str:
    year = datetime.now().year
    res = supabase.table("construction_works").select("id", count="exact").eq("site_id", site_id).execute()
    seq = (res.count or 0) + 1
    return f"CS-{year}-{seq:05d}"


@router.get("/sites/{site_id}/processes")
async def list_processes(
    site_id: str,
    status_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = run_list_query(
            supabase,
            "construction_site_processes",
            {"site_id": site_id, "is_active": True, "status_code": status_code},
            page,
            size,
            ["sort_order", "created_at"],
        )
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/processes")
async def create_process(site_id: str, body: ProcessCreate):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        data = normalize_date_fields(data, ("planned_start", "planned_end"))
        created = create_record(supabase, "construction_site_processes", data, _now_iso, "등록 실패")
        return {"status": "success", "data": created}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/processes/{process_id}")
async def get_process(process_id: str):
    supabase = get_supabase()
    row = get_record_or_none(supabase, "construction_site_processes", process_id)
    if not row:
        raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.patch("/processes/{process_id}")
async def update_process(process_id: str, body: ProcessPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        data = normalize_date_fields(data, ("planned_start", "planned_end", "actual_start", "actual_end"))
        updated = update_record(supabase, "construction_site_processes", process_id, data, _now_iso)
        if not updated:
            raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
        return {"status": "success", "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/processes/{process_id}")
async def delete_process(process_id: str):
    supabase = get_supabase()
    deleted = soft_delete_record(supabase, "construction_site_processes", process_id, _now_iso)
    if not deleted:
        raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.get("/sites/{site_id}/works")
async def list_works(
    site_id: str,
    status_code: Optional[str] = Query(None),
    ptw_status: Optional[str] = Query(None),
    work_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = run_list_query(
            supabase,
            "construction_works",
            {"site_id": site_id, "is_active": True, "status_code": status_code, "ptw_status": ptw_status, "work_date": work_date},
            page,
            size,
            [("work_date", True), ("created_at", True)],
        )
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/works")
async def create_work(site_id: str, body: WorkCreate):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        data = normalize_date_fields(data, ("work_date",))
        data["ptw_number"] = _ptw_number(site_id, supabase)
        data["ptw_status"] = "DRAFT"
        created = create_record(supabase, "construction_works", data, _now_iso, "등록 실패")
        return {"status": "success", "data": created}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/works/{work_id}")
async def get_work(work_id: str):
    supabase = get_supabase()
    row = get_record_or_none(supabase, "construction_works", work_id)
    if not row:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.patch("/works/{work_id}")
async def update_work(work_id: str, body: WorkPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        data = normalize_date_fields(data, ("work_date",))
        updated = update_record(supabase, "construction_works", work_id, data, _now_iso)
        if not updated:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        return {"status": "success", "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/works/{work_id}/ptw")
async def update_ptw(work_id: str, body: PtwPatch):
    supabase = get_supabase()
    try:
        data = build_ptw_update_payload(body, _now_iso)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    res = supabase.table("construction_works").update(data).eq("id", work_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.delete("/works/{work_id}")
async def delete_work(work_id: str):
    supabase = get_supabase()
    deleted = soft_delete_record(supabase, "construction_works", work_id, _now_iso)
    if not deleted:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.get("/sites/{site_id}/workers")
async def list_workers(
    site_id: str,
    worker_type: Optional[str] = Query(None),
    entry_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("construction_workers").select(
            "*, worker_registry(name, phone, job_type_code, job_type_name, contractor_name, start_date, memo)",
            count="exact",
        ).eq("site_id", site_id).eq("is_active", True)
        if worker_type:
            q = q.eq("worker_type", worker_type)
        if entry_status:
            q = q.eq("entry_status", entry_status)
        if search:
            q = q.ilike("worker_name", f"%{search}%")
        res = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
        items = res.data or []
        # 화면이 바로 읽도록 명부값을 평탄화(원본 embed 객체도 유지)
        for it in items:
            reg = it.get("worker_registry") or {}
            it["job_type_code"] = reg.get("job_type_code")
            it["job_type_name"] = reg.get("job_type_name")
            it["contractor_name"] = reg.get("contractor_name")
            it["start_date"] = reg.get("start_date")
            it["registry_name"] = reg.get("name")
            it["registry_memo"] = reg.get("memo")
        return {"status": "success", "data": {"items": items, "total": res.count or 0, "page": page, "size": size}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _iso_date(v) -> Optional[str]:
    """date 객체면 ISO 문자열로, 그 외(str/None)는 그대로."""
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


@router.post("/sites/{site_id}/workers")
async def create_worker(site_id: str, body: WorkerCreate):
    """건설 작업자 등록 — 통합 명부(worker_registry) + 현장배치(construction_workers) 동시 생성.

    LEDGER §19: 종전에는 construction_workers 에만 직접 써서 화면 8필드가 버려지고, org
    (부서·팀·그룹)·리더 체계에서 이탈했다. 실측상 org 배정·리더는 worker_registry.id 를
    기준점으로 하고(worker_group·groups.lead_worker_id·teams.lead_worker_id FK),
    construction_workers 는 worker_registry_id 로 명부와 연결된다(기존 데이터 전원 연결·
    worker_registry.factory_id=NULL·company 스코프). 그 선례대로:
      1) worker_registry 명부 생성(factory_id=NULL, company 스코프) — org·리더 편입 가능
      2) construction_workers 현장배치 생성(worker_registry_id 연결 + 건설 특화: 고용형태·
         안전교육·출입상태)
    실패 시 명부 고아를 남기지 않도록 보상 삭제한다.
    """
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()

    name = (body.worker_name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="이름은 필수입니다.")

    # site → company_id (worker_registry 는 factory_id 없이 company 스코프로 담는다)
    site = supabase.table("construction_sites").select("company_id").eq("id", site_id).single().execute()
    if not site.data:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
    company_id = site.data.get("company_id")

    phone = re.sub(r"[^0-9]", "", body.phone or "") or None
    job_label = (body.job_type or "").strip() or "미지정"
    job_name = _JOB_CODE_TO_NAME.get(job_label, job_label)  # 코드면 직종명, 아니면(미지정/자유텍스트) 그대로
    contractor = (body.company_name or "").strip() or None
    memo = (body.memo or "").strip() or None
    hire = _iso_date(body.hire_date)
    now = _now_iso()

    # 1) 통합 명부(worker_registry) — factory_id=NULL, company 스코프 (실측 선례)
    reg_payload = {
        "company_id":      company_id,
        "factory_id":      None,
        "name":            name,
        "phone":           phone,
        "job_type_code":   job_label,
        "job_type_name":   job_name,
        "contractor_name": contractor,
        "start_date":      hire,
        "memo":            memo,
        "is_active":       True,
        "status_code":     "ACTIVE",
        "created_at":      now,
        "updated_at":      now,
    }
    reg_payload = {k: v for k, v in reg_payload.items() if v is not None}
    try:
        reg = supabase.table("worker_registry").insert(reg_payload).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작업자 명부 등록 실패: {e}")
    if not reg.data:
        raise HTTPException(status_code=500, detail="작업자 명부 등록 실패")
    worker_registry_id = reg.data[0]["id"]

    # 2) 현장배치(construction_workers) — 명부 연결 + 건설 특화(고용형태·안전교육·출입)
    edu_hours = int(body.safety_training_hours) if body.safety_training_hours is not None else None
    cw_payload = {
        "site_id":            site_id,
        "worker_registry_id": worker_registry_id,
        "worker_name":        name,
        "worker_phone":       phone,
        "worker_type":        body.worker_type,
        "join_date":          hire,
        "safety_edu_date":    _iso_date(body.safety_training_date),
        "safety_edu_hours":   edu_hours,
        "entry_status":       body.entry_status,
        "notes":              memo,
        "is_active":          True,
        "created_at":         now,
        "updated_at":         now,
    }
    cw_payload = {k: v for k, v in cw_payload.items() if v is not None}
    try:
        res = supabase.table("construction_workers").insert(cw_payload).execute()
        if not res.data:
            raise Exception("현장 배치 저장 결과가 비어 있습니다.")
    except Exception as e:
        # 보상: 명부 고아 방지
        try:
            supabase.table("worker_registry").delete().eq("id", worker_registry_id).execute()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"현장 배치 등록 실패: {e}")

    return {"status": "success", "data": res.data[0]}


class SiteQrBody(BaseModel):
    qr_code: Optional[str] = None   # 미지정 시 site_id 를 그대로 QR 값으로 사용


@router.post("/sites/{site_id}/qr")
async def issue_site_qr(site_id: str, body: SiteQrBody):
    """현장 출입 QR 발급(등록). 이미 발급된 현장이면 기존 행을 갱신(재발급).
    QR 내용은 기본적으로 site_id(UUID) 그대로 — 앱 qr_scan.html 이 이 값을 site_id 로 파싱한다."""
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()

    site = supabase.table("construction_sites").select("id, site_name").eq("id", site_id).single().execute()
    if not site.data:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")

    qr_code = (body.qr_code or "").strip() or site_id
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # 같은 현장에 이미 발급된 QR 있으면 갱신, 없으면 신규
    exist = supabase.table("qr_entities").select("id").eq("site_id", site_id).eq("tag_type", "SITE").limit(1).execute()
    if exist.data:
        qid = exist.data[0]["id"]
        supabase.table("qr_entities").update({
            "qr_code": qr_code, "status_code": "ACTIVE",
        }).eq("id", qid).execute()
    else:
        ins = supabase.table("qr_entities").insert({
            "site_id": site_id, "qr_code": qr_code, "tag_type": "SITE",
            "status_code": "ACTIVE", "issued_at": now_naive,
        }).execute()
        qid = ins.data[0]["id"] if ins.data else None

    return {
        "status": "success",
        "data": {"id": qid, "site_id": site_id, "qr_code": qr_code,
                 "site_name": site.data.get("site_name")},
    }


@router.get("/sites/{site_id}/qr")
async def get_site_qr(site_id: str):
    """현장에 발급된 QR 조회(없으면 data=null). 화면이 발급 여부·재출력에 쓴다."""
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    res = supabase.table("qr_entities").select("id, qr_code, status_code, issued_at") \
        .eq("site_id", site_id).eq("tag_type", "SITE").limit(1).execute()
    return {"status": "success", "data": (res.data[0] if res.data else None)}


@router.post("/sites/{site_id}/workers/bulk-import")
async def bulk_import_construction_workers(
    site_id: str,
    file: UploadFile = File(...),
):
    """건설 작업자 엑셀 일괄 등록 — 행마다 worker_registry(명부) + construction_workers(배치) 생성.
    컬럼: 이름(필수)|연락처(필수)|직종(필수)|소속업체|입사일|부서|팀|그룹|고용형태(선택)"""
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    site = supabase.table("construction_sites").select("company_id").eq("id", site_id).single().execute()
    if not site.data:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
    company_id = site.data.get("company_id")
    content = await file.read()
    filename = file.filename or ""
    rows: list = []
    try:
        if filename.endswith(".csv"):
            import csv
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            rows = list(reader)
        else:
            import pandas as pd
            df = pd.read_excel(io.BytesIO(content), sheet_name=0, dtype=str).fillna("")
            rows = df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"파일 파싱 실패: {e}")
    if not rows:
        raise HTTPException(status_code=422, detail="파일에 데이터가 없습니다.")
    def _col(row: dict, *keys: str) -> str:
        for k in keys:
            if k in row and str(row[k]).strip():
                return str(row[k]).strip()
        return ""
    created, updated, failed, mapping_failed, org_failed = 0, 0, [], [], []
    now = _now_iso()
    for idx, row in enumerate(rows, start=2):
        name = _col(row, "이름", "이름(필수)", "name")
        phone_raw = _col(row, "연락처", "연락처(필수)", "phone")
        job_name = _col(row, "직종", "직종(필수)", "job_type")
        contractor = _col(row, "소속업체", "contractor") or None
        start_date = _col(row, "입사일", "start_date") or None
        dept_name = _col(row, "부서", "department")
        team_name = _col(row, "팀", "team")
        group_name = _col(row, "그룹", "조", "group")
        emp_raw = _col(row, "고용형태", "worker_type")
        if not name or not phone_raw:
            failed.append({"row": idx, "reason": "이름/연락처 누락"})
            continue
        phone = re.sub(r"[^0-9]", "", phone_raw)
        if len(phone) < 10:
            failed.append({"row": idx, "name": name, "reason": "연락처 형식 오류"})
            continue
        job_code = _match_job_code(job_name)
        job_type_name = _JOB_CODE_TO_NAME.get(job_code, "기타")
        if job_code == "WJT020" and job_name and job_name not in ("기타", ""):
            mapping_failed.append({"row": idx, "name": name, "job_name": job_name})
        worker_type = _EMP_TYPE_MAP.get(emp_raw, "DIRECT")
        try:
            # 중복: 같은 현장에 같은 연락처 → 배치 update
            dup = supabase.table("construction_workers").select("id, worker_registry_id").eq("site_id", site_id).eq("worker_phone", phone).eq("is_active", True).limit(1).execute()
            if dup.data:
                cw_id = dup.data[0]["id"]
                reg_id = dup.data[0]["worker_registry_id"]
                supabase.table("worker_registry").update({
                    "name": name, "job_type_code": job_code, "job_type_name": job_type_name,
                    "contractor_name": contractor, "start_date": start_date, "updated_at": now,
                }).eq("id", reg_id).execute()
                supabase.table("construction_workers").update({
                    "worker_name": name, "worker_type": worker_type, "updated_at": now,
                }).eq("id", cw_id).execute()
                worker_registry_id = reg_id
                updated += 1
            else:
                reg_payload = {
                    "company_id": company_id, "factory_id": None, "name": name, "phone": phone,
                    "job_type_code": job_code, "job_type_name": job_type_name,
                    "contractor_name": contractor, "start_date": start_date,
                    "is_active": True, "status_code": "ACTIVE", "created_at": now, "updated_at": now,
                }
                reg_payload = {k: v for k, v in reg_payload.items() if v is not None}
                reg = supabase.table("worker_registry").insert(reg_payload).execute()
                worker_registry_id = reg.data[0]["id"]
                cw_payload = {
                    "site_id": site_id, "worker_registry_id": worker_registry_id,
                    "worker_name": name, "worker_phone": phone, "worker_type": worker_type,
                    "join_date": start_date, "is_active": True, "created_at": now, "updated_at": now,
                }
                cw_payload = {k: v for k, v in cw_payload.items() if v is not None}
                supabase.table("construction_workers").insert(cw_payload).execute()
                created += 1
            # org 배정 (site 기반 그룹 해석)
            if worker_registry_id and group_name:
                gid = _resolve_group_id_site(supabase, site_id, dept_name, team_name, group_name)
                if gid:
                    supabase.table("worker_group").delete().eq("worker_id", worker_registry_id).execute()
                    supabase.table("worker_group").insert({"worker_id": worker_registry_id, "group_id": gid, "is_lead": False}).execute()
                else:
                    org_failed.append({"row": idx, "name": name, "group": group_name})
        except Exception as e:
            failed.append({"row": idx, "name": name, "reason": str(e)})
    return {
        "status": "success",
        "message": f"등록 {created}건, 수정 {updated}건, 실패 {len(failed)}건",
        "data": {"created": created, "updated": updated, "failed": failed,
                 "mapping_failed": mapping_failed, "org_failed": org_failed},
    }


@router.get("/workers/{worker_id}")
async def get_worker(worker_id: str):
    supabase = get_supabase()
    row = get_record_or_none(supabase, "construction_workers", worker_id)
    if not row:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.patch("/workers/{worker_id}")
async def update_worker(worker_id: str, body: WorkerPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        data = normalize_date_fields(data, ("join_date", "leave_date", "health_check_date", "safety_edu_date"))
        updated = update_record(supabase, "construction_workers", worker_id, data, _now_iso)
        if not updated:
            raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
        return {"status": "success", "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/workers/{worker_id}/entry")
async def update_entry(worker_id: str, body: EntryPatch):
    supabase = get_supabase()
    try:
        data = build_entry_update_payload(body, _now_iso)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    res = supabase.table("construction_workers").update(data).eq("id", worker_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.delete("/workers/{worker_id}")
async def delete_worker(worker_id: str):
    supabase = get_supabase()
    deleted = soft_delete_record(supabase, "construction_workers", worker_id, _now_iso)
    if not deleted:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.get("/sites/{site_id}/inspections")
async def list_inspections(
    site_id: str,
    inspection_type: Optional[str] = Query(None),
    overall_result: Optional[str] = Query(None),
    corrective_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = run_list_query(
            supabase,
            "construction_inspections",
            {
                "site_id": site_id,
                "is_active": True,
                "inspection_type": inspection_type,
                "overall_result": overall_result,
                "corrective_status": corrective_status,
            },
            page,
            size,
            [("inspection_date", True)],
        )
        data["items"] = [_alias_inspection_row(r) for r in data.get("items", [])]
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/inspections")
async def create_inspection(site_id: str, body: InspectionCreate):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = prepare_inspection_payload(body.model_dump(exclude_none=True), _now_iso)
        data["site_id"] = site_id
        res = supabase.table("construction_inspections").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        inspection = res.data[0]
        if data.get("overall_result") in ("FAIL", "ISSUE") and data.get("defect_count", 0) > 0:
            await send_fcm_inspection_alert(supabase, site_id=site_id, inspection_id=inspection["id"], defect_count=data.get("defect_count", 1))
        return {"status": "success", "data": _alias_inspection_row(inspection)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inspections/{inspection_id}")
async def get_inspection(inspection_id: str):
    supabase = get_supabase()
    row = get_record_or_none(supabase, "construction_inspections", inspection_id)
    if not row:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "data": _alias_inspection_row(row)}


@router.patch("/inspections/{inspection_id}")
async def update_inspection(inspection_id: str, body: InspectionPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        data = normalize_date_fields(data, ("corrective_deadline",))
        updated = update_record(supabase, "construction_inspections", inspection_id, data, _now_iso)
        if not updated:
            raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
        return {"status": "success", "data": _alias_inspection_row(updated)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/inspections/{inspection_id}/corrective")
async def update_corrective(inspection_id: str, body: CorrectivePatch):
    supabase = get_supabase()
    try:
        data = build_corrective_update_payload(body, _now_iso)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    res = supabase.table("construction_inspections").update(data).eq("id", inspection_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "data": _alias_inspection_row(res.data[0])}


@router.delete("/inspections/{inspection_id}")
async def delete_inspection(inspection_id: str):
    supabase = get_supabase()
    deleted = soft_delete_record(supabase, "construction_inspections", inspection_id, _now_iso)
    if not deleted:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.post("/engine/safety-manager")
async def engine_safety_manager(body: SafetyManagerBody):
    return {"status": "success", "data": calc_safety_manager(body.site_type, body.contract_amount, body.total_workers)}
