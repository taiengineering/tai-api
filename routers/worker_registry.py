"""
작업자 명부 라우터 — v1.2.0

작업자 등록 (수동 + 파일 일괄), 목록 조회, 수정, 비활성화, 앱 초대 문자 발송

v1.2.0: 초대 발송을 기존 SMS 모듈(capabilities.sms.core)로 연결
v1.1.0: 초대 문자 실제 발송 시도 (종전 stub)

DB: worker_registry
endpoints:
  POST   /worker-registry                 수동 등록
  POST   /worker-registry/bulk-import     엑셀 일괄 등록
  GET    /worker-registry                 목록 조회
  GET    /worker-registry/template        엑셀 템플릿 다운로드
  PATCH  /worker-registry/{id}            수정
  DELETE /worker-registry/{id}            비활성화 (soft delete)
  POST   /worker-registry/{id}/invite     앱 초대 문자 발송
"""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import io
import os
import re
import logging
from db.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(prefix="/worker-registry", tags=["worker_registry"])

VERSION = "1.2.0"

# 초대 링크. 단축 도메인(w.taieng.co.kr)이 코드에 적혀 있었으나 프로젝트 어디에도
# 근거가 없어 실제 앱 주소를 쓴다. 환경변수로 바꿀 수 있게 둔다.
APP_INVITE_URL = os.getenv("APP_INVITE_URL", "https://safe.taieng.co.kr/app/")

# 직종명 → WJT 코드 매핑 (업로드 시 직종명 ILIKE 매칭용)
JOB_TYPE_MAP = {
    "사무직":            "WJT001",
    "사무":              "WJT001",
    "사무직(일반)": "WJT001",
    "생산직":           "WJT002",
    "생산직(일반)": "WJT002",
    "생산":              "WJT002",
    "용접공":            "WJT003",
    "용접":              "WJT003",
    "철근공":            "WJT004",
    "철근":              "WJT004",
    "목공":              "WJT005",
    "목리":              "WJT005",
    "비계공":            "WJT006",
    "비계":              "WJT006",
    "전기공":            "WJT007",
    "전기":              "WJT007",
    "배관공":            "WJT008",
    "배관":              "WJT008",
    "도장공":            "WJT009",
    "도장":              "WJT009",
    "운전기사":          "WJT010",
    "운전":              "WJT010",
    "지게자 운전원":    "WJT011",
    "지게자":            "WJT011",
    "크레인 운전원":    "WJT012",
    "크레인":            "WJT012",
    "화학물질 취급":    "WJT013",
    "화학물질":          "WJT013",
    "화학":              "WJT013",
    "고소작업자":        "WJT014",
    "고소작업":          "WJT014",
    "고소":              "WJT014",
    "밀폐공간 작업자":    "WJT015",
    "밀폐공간":          "WJT015",
    "밀폐":              "WJT015",
    "관리감독자":        "WJT016",
    "관리감독":          "WJT016",
    "안전보건관리담당자":  "WJT017",
    "안전담당자":        "WJT017",
    "협력업체 작업자":  "WJT018",
    "협력업체":          "WJT018",
    "협력":              "WJT018",
    "일용직":            "WJT019",
    "일용":              "WJT019",
    "기타":              "WJT020",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_phone(phone: str) -> str:
    """010-1234-5678 → 01012345678"""
    return re.sub(r'[^0-9]', '', str(phone))


def _match_job_type(job_name: str) -> str:
    """직종명 → WJT 코드. 매핑 실패 시 WJT020(기타) 반환."""
    if not job_name:
        return "WJT020"
    job_name = job_name.strip()
    # 정확일치 먼저
    if job_name in JOB_TYPE_MAP:
        return JOB_TYPE_MAP[job_name]
    # 포함 매칭
    for key, code in JOB_TYPE_MAP.items():
        if key in job_name or job_name in key:
            return code
    return "WJT020"  # 기타


def _get_job_type_name(code: str) -> str:
    reverse = {v: k for k, v in JOB_TYPE_MAP.items()}
    return reverse.get(code, "기타")


# ============================================================
# 스키마
# ============================================================

class WorkerCreate(BaseModel):
    factory_id:      str
    name:            str
    phone:           str
    job_type_code:   str              # WJT001~WJT020
    contractor_name: Optional[str] = None
    department:      Optional[str] = None
    start_date:      Optional[str] = None
    birth_date:      Optional[str] = None
    id_number_last4: Optional[str] = None


class WorkerUpdate(BaseModel):
    name:            Optional[str] = None
    phone:           Optional[str] = None
    job_type_code:   Optional[str] = None
    contractor_name: Optional[str] = None
    department:      Optional[str] = None
    start_date:      Optional[str] = None
    end_date:        Optional[str] = None
    is_active:       Optional[bool] = None


# ============================================================
# GET /worker-registry/template  ← /{id} 앞에 선언
# ============================================================

@router.get("/template")
def download_template():
    """
    엑셀 템플릿 다운로드.
    openpyxl로 환경이 많지 않으면 CSV 방식으로 fallback.
    """
    try:
        import openpyxl
        wb = openpyxl.Workbook()

        # 시트 1: 데이터 입력
        ws = wb.active
        ws.title = "작업자명부"
        ws.append(["이름(필수)", "연락선(필수)", "직종(필수)", "소속업체", "입사일"])
        ws.append(["홍길동", "010-1234-5678", "용접공", "(\uc8fc)ABC건설", "2026-04-01"])

        # 시트 2: 직종 참고
        ws2 = wb.create_sheet(title="직종목록(참고)")
        ws2.append(["코드", "직종명"])
        for code, name in [
            ("WJT001","사무직"), ("WJT002","생산직(일반)"), ("WJT003","용접공"),
            ("WJT004","철근공"), ("WJT005","목공"), ("WJT006","비계공"),
            ("WJT007","전기공"), ("WJT008","배관공"), ("WJT009","도장공"),
            ("WJT010","운전기사"), ("WJT011","지게자 운전원"), ("WJT012","크레인 운전원"),
            ("WJT013","화학물질 취급"), ("WJT014","고소작업자"), ("WJT015","밀폐공간 작업자"),
            ("WJT016","관리감독자"), ("WJT017","안전보건관리담당자"), ("WJT018","협력업체 작업자"),
            ("WJT019","일용직"), ("WJT020","기타"),
        ]:
            ws2.append([code, name])

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=workers_template.xlsx"}
        )
    except ImportError:
        # openpyxl 미설치 시 CSV fallback
        csv_content = "이름(필수),연락선(필수),직종(필수),소속업체,입사일\n"
        csv_content += "홍길동,010-1234-5678,용접공,(\uc8fc)ABC건설,2026-04-01\n"
        buf = io.BytesIO(csv_content.encode("utf-8-sig"))
        return StreamingResponse(
            buf,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=workers_template.csv"}
        )


# ============================================================
# POST /worker-registry  수동 등록
# ============================================================

@router.post("")
def create_worker(body: WorkerCreate):
    supabase = get_supabase()

    if not body.name.strip():
        raise HTTPException(status_code=422, detail="이름은 필수입니다.")

    phone = _normalize_phone(body.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="연락선은 필수입니다.")

    # factory → company_id 조회
    fac = supabase.table("factories").select("company_id").eq(
        "id", body.factory_id
    ).single().execute()
    if not fac.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    company_id = fac.data["company_id"]

    # job_type_name 자동 세팅
    job_names = {
        "WJT001":"사무직","WJT002":"생산직(일반)","WJT003":"용접공",
        "WJT004":"철근공","WJT005":"목공","WJT006":"비계공",
        "WJT007":"전기공","WJT008":"배관공","WJT009":"도장공",
        "WJT010":"운전기사","WJT011":"지게자 운전원","WJT012":"크레인 운전원",
        "WJT013":"화학물질 취급","WJT014":"고소작업자","WJT015":"밀폐공간 작업자",
        "WJT016":"관리감독자","WJT017":"안전보건관리담당자","WJT018":"협력업체 작업자",
        "WJT019":"일용직","WJT020":"기타"
    }
    job_type_name = job_names.get(body.job_type_code, "기타")

    now = _now_iso()
    data = {
        "factory_id":      body.factory_id,
        "company_id":      company_id,
        "name":            body.name.strip(),
        "phone":           phone,
        "job_type_code":   body.job_type_code,
        "job_type_name":   job_type_name,
        "is_active":       True,
        "status_code":     "ACTIVE",
        "app_installed":   False,
        "created_at":      now,
        "updated_at":      now,
    }
    if body.contractor_name: data["contractor_name"] = body.contractor_name
    if body.department:      data["department"]      = body.department
    if body.start_date:      data["start_date"]      = body.start_date
    if body.birth_date:      data["birth_date"]      = body.birth_date
    if body.id_number_last4: data["id_number_last4"] = body.id_number_last4

    res = supabase.table("worker_registry").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="작업자 등록 실패")

    return {"status": "success", "message": f"작업자 '{body.name}' 등록 완료", "data": res.data[0]}


# ============================================================
# POST /worker-registry/bulk-import  엑셀 일괄 등록
# ============================================================

@router.post("/bulk-import")
async def bulk_import_workers(
    factory_id: str = Form(...),
    file: UploadFile = File(...),
):
    """
    엑셀 / CSV 파일로 작업자 일괄 등록.
    켇럼: 이름(필수) | 연락선(필수) | 직종(필수) | 소속업체 | 입사일
    - 직종명 → WJT 코드 자동 매핑 (실패 시 WJT020)
    - 중복 전화번호 → 업데이트
    """
    supabase = get_supabase()

    # factory → company_id
    fac = supabase.table("factories").select("company_id").eq(
        "id", factory_id
    ).single().execute()
    if not fac.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    company_id = fac.data["company_id"]

    content   = await file.read()
    filename  = file.filename or ""
    rows: list[dict] = []

    try:
        if filename.endswith(".csv"):
            import csv
            text    = content.decode("utf-8-sig")
            reader  = csv.DictReader(io.StringIO(text))
            for r in reader:
                rows.append(r)
        else:
            # xlsx / xls — pandas + openpyxl
            import pandas as pd
            df = pd.read_excel(io.BytesIO(content), sheet_name=0, dtype=str)
            df = df.fillna("")
            rows = df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"파일 파싱 실패: {e}")

    if not rows:
        raise HTTPException(status_code=422, detail="파일에 데이터가 없습니다.")

    # 콼럼명 정규화 함수
    def _col(row: dict, *keys: str) -> str:
        for k in keys:
            if k in row and str(row[k]).strip():
                return str(row[k]).strip()
        return ""

    created, updated, failed = 0, 0, []
    now = _now_iso()

    job_names_map = {
        "WJT001":"사무직","WJT002":"생산직(일반)","WJT003":"용접공",
        "WJT004":"철근공","WJT005":"목공","WJT006":"비계공",
        "WJT007":"전기공","WJT008":"배관공","WJT009":"도장공",
        "WJT010":"운전기사","WJT011":"지게자 운전원","WJT012":"크레인 운전원",
        "WJT013":"화학물질 취급","WJT014":"고소작업자","WJT015":"밀폐공간 작업자",
        "WJT016":"관리감독자","WJT017":"안전보건관리담당자","WJT018":"협력업체 작업자",
        "WJT019":"일용직","WJT020":"기타"
    }
    mapping_failed = []  # 직종 매핑 실패 항목

    for idx, row in enumerate(rows, start=2):  # 1행 = 헤더
        name     = _col(row, "이름", "이름(필수)", "name")
        phone_raw = _col(row, "연락선", "연락선(필수)", "phone", "휴대폰")
        job_name = _col(row, "직종", "직종(필수)", "job_type", "직종명")
        contractor = _col(row, "소속업체", "contractor")
        start_date = _col(row, "입사일", "start_date")

        if not name or not phone_raw:
            failed.append({"row": idx, "reason": "이름/연락선 누락"})
            continue

        phone = _normalize_phone(phone_raw)
        if len(phone) < 10:
            failed.append({"row": idx, "name": name, "reason": "연락선 형식 오류"})
            continue

        job_type_code = _match_job_type(job_name)
        job_type_name_val = job_names_map.get(job_type_code, "기타")
        if job_type_code == "WJT020" and job_name and job_name not in ("기타", ""):
            mapping_failed.append({"row": idx, "name": name, "job_name": job_name})

        record = {
            "factory_id":    factory_id,
            "company_id":    company_id,
            "name":          name,
            "phone":         phone,
            "job_type_code": job_type_code,
            "job_type_name": job_type_name_val,
            "is_active":     True,
            "status_code":   "ACTIVE",
            "app_installed": False,
            "updated_at":    now,
        }
        if contractor:  record["contractor_name"] = contractor
        if start_date:  record["start_date"]      = start_date

        try:
            # 중복 여부 확인 (factory_id + phone)
            dup = supabase.table("worker_registry").select("id").eq(
                "factory_id", factory_id
            ).eq("phone", phone).limit(1).execute()

            if dup.data:
                # 업데이트
                supabase.table("worker_registry").update(record).eq(
                    "id", dup.data[0]["id"]
                ).execute()
                updated += 1
            else:
                record["created_at"] = now
                supabase.table("worker_registry").insert(record).execute()
                created += 1
        except Exception as e:
            failed.append({"row": idx, "name": name, "reason": str(e)})

    return {
        "status":  "success",
        "message": f"등록 {created}건, 수정 {updated}건, 실패 {len(failed)}건",
        "data": {
            "created":        created,
            "updated":        updated,
            "failed":         failed,
            "mapping_failed": mapping_failed,  # 직종 매핑 실패 목록
        }
    }


# ============================================================
# GET /worker-registry  목록 조회
# ============================================================

@router.get("")
def get_workers(
    factory_id:    Optional[str]  = Query(None),
    company_id:    Optional[str]  = Query(None),
    job_type_code: Optional[str]  = Query(None),
    is_active:     Optional[bool] = Query(None),
    keyword:       Optional[str]  = Query(None, description="이름/연락선/소속업체 통합 검색"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    query = supabase.table("worker_registry").select(
        "id, factory_id, company_id, name, phone, job_type_code, job_type_name, "
        "contractor_name, department, start_date, end_date, "
        "app_installed, invite_sent_at, is_active, status_code, created_at",
        count="exact"
    )
    if factory_id:    query = query.eq("factory_id",    factory_id)
    if company_id:    query = query.eq("company_id",    company_id)
    if job_type_code: query = query.eq("job_type_code", job_type_code)
    if is_active is not None: query = query.eq("is_active", is_active)
    if keyword:       query = query.or_(
        f"name.ilike.%{keyword}%,phone.ilike.%{keyword}%,contractor_name.ilike.%{keyword}%"
    )

    offset = (page - 1) * size
    res = query.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0

    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        }
    }


# ============================================================
# PATCH /worker-registry/{id}  수정
# ============================================================

@router.patch("/{worker_id}")
def update_worker(worker_id: str, body: WorkerUpdate):
    supabase = get_supabase()
    chk = supabase.table("worker_registry").select("id").eq(
        "id", worker_id
    ).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if "phone" in update_data:
        update_data["phone"] = _normalize_phone(update_data["phone"])
    update_data["updated_at"] = _now_iso()

    res = supabase.table("worker_registry").update(update_data).eq(
        "id", worker_id
    ).execute()
    return {"status": "success", "message": "작업자 정보가 수정됐습니다.", "data": res.data[0] if res.data else {}}


# ============================================================
# DELETE /worker-registry/{id}  비활성화
# ============================================================

@router.delete("/{worker_id}")
def delete_worker(worker_id: str):
    supabase = get_supabase()
    chk = supabase.table("worker_registry").select("id").eq(
        "id", worker_id
    ).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    supabase.table("worker_registry").update({
        "is_active":   False,
        "status_code": "INACTIVE",
        "updated_at":  _now_iso(),
    }).eq("id", worker_id).execute()
    return {"status": "success", "message": "작업자가 비활성화됐습니다."}


# ============================================================
# POST /worker-registry/{id}/invite  앱 초대 문자 발송
#
# v1.2.0: 기존 SMS 모듈을 직접 호출한다.
#   SMS 는 capabilities/sms/core.py 로 이미 모듈화되어 있고 routers/messaging.py
#   가 그것을 쓴다. Supabase Edge Function(서울) 경유이며 retry·timeout 이 내장돼
#   있다. 초대 발송도 같은 모듈을 쓴다.
#
#   v1.1.0 은 services/notification_engine/adapters/sms.py 를 불렀으나, 그 어댑터는
#   api.messagemi.com 을 직접 호출하는데 그 도메인이 존재하지 않아 DNS 해석에
#   실패했다(NameResolutionError).
#
#   종전(v1.0.0)에는 메시지 문자열을 print 로 출력하고 invite_sent_at 만 갱신했다.
#   그럼에도 응답은 "초대 문자가 발송됐습니다" 였기에, 관리자 화면에서는 성공으로
#   보이지만 실제로는 아무것도 나가지 않았다.
# ============================================================

def _build_invite_message(name: str) -> str:
    """초대 문안.

    URL 을 앞쪽에 두어 이름이 길어도 링크가 온전하게 남도록 한다 —
    링크가 깨지면 초대의 목적 자체가 사라진다.
    길이 제한은 신경 쓰지 않는다. core.detect_msg_type() 이 90바이트 초과 시
    LMS 로 판별한다.
    """
    suffix = f"\n{name}님" if name else ""
    return f"[TAI Safe] 안전점검 앱 설치\n{APP_INVITE_URL}{suffix}"


@router.post("/{worker_id}/invite")
async def send_invite(worker_id: str):
    """작업자에게 앱 초대 문자를 발송한다."""
    supabase = get_supabase()
    chk = supabase.table("worker_registry").select(
        "id, name, phone"
    ).eq("id", worker_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")

    worker = chk.data[0]
    phone  = _normalize_phone(worker.get("phone") or "")
    if not phone:
        raise HTTPException(status_code=422, detail="연락처가 없어 초대를 보낼 수 없습니다.")

    invite_msg = _build_invite_message(worker.get("name") or "")

    try:
        from capabilities.sms.core import send_sms
        result = await send_sms(phone, invite_msg, title="TAI Safe")
    except Exception as e:
        log.error(f"[invite] SMS 발송 예외 worker_id={worker_id} phone={phone}: {e}")
        raise HTTPException(status_code=502, detail=f"문자 발송에 실패했습니다. ({str(e)[:150]})")

    if not result.get("success"):
        # 발송에 실패했으면 invite_sent_at 을 남기지 않는다. 기록이 남으면
        # 관리자가 이미 보냈다고 판단해 재발송하지 않는다.
        # code·raw 를 함께 남긴다 — 발신번호 미등록·잔액 부족 등을 구분해야 한다.
        err = f"code={result.get('code')} {str(result.get('raw'))[:150]}"
        log.error(f"[invite] 발송 실패 worker_id={worker_id} phone={phone}: {err}")
        raise HTTPException(status_code=502, detail=f"문자 발송에 실패했습니다. ({err})")

    now = _now_iso()
    supabase.table("worker_registry").update({
        "invite_sent_at": now,
        "updated_at":     now,
    }).eq("id", worker_id).execute()

    log.info(f"[invite] 발송 성공 worker_id={worker_id} phone={phone} mode={result.get('mode')}")

    return {
        "status":  "success",
        "message": f"초대 문자가 발송됐습니다. ({worker['phone']})",
        "data": {
            "worker_id":      worker_id,
            "name":           worker["name"],
            "phone":          worker["phone"],
            "invite_sent_at": now,
            "message":        invite_msg,
            "mode":           result.get("mode"),
        }
    }
