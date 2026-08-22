"""
작업자 현장 점검 제출 API — v1.5.0

v1.5.0 (2026-08-23, WP-PARTITION-02C):
  [ADD] safety_inspections INSERT 시 factory_id 전파.
        work_schedules 가 PARTITION BY HASH(factory_id) 로 전환되면
        PK 가 (id, factory_id) 가 되고 safety_inspections FK 도
        (assignment_id, factory_id) 복합키 + MATCH FULL + pair CHECK 가 된다.
        → 기존 work_assignments 조회에 factory_id 를 함께 취득(추가 SELECT 없음).
          body.schedule_id 직접 경로처럼 factory 를 얻지 못한 경우에만
          work_schedules 에서 보완 조회한다.
        assignment 이 없는 제출(구버전 앱)은 둘 다 NULL 로 저장되어
        pair CHECK 를 정상 통과한다.
        ※ 이 변경은 파티션 적용 DB 를 전제로 한다. DB migration 과 동일
          maintenance window 에서 배포해야 한다(구 schema 와 호환 안 됨).

v1.4.1 (2026-08-17, Goal G-mswtdmi1-420f8c):
  [FIX] safety_inspections.assignment_id 의 FK 는 work_schedules(id) 를 참조한다(컬럼명과 대상 불일치).
        v1.4.0 이 work_assignments.id 를 그대로 넣어 FK 위반 → 500 → 앱이 "기기에 임시저장"으로 처리했다.
        (8/09 옛 제출은 assignment_id 가 없어 FK 검사를 타지 않아 성공했고, 새 앱은 assignment_id 를 보내 위반.)
        → assignment_id(work_assignments.id)를 schedule_id(work_schedules.id)로 변환해 저장한다.
        [별건] 컬럼명 assignment_id 인데 FK 는 work_schedules — 명명/설계 정합(FK 를 work_assignments 로 옆길지)은 기획 결정.
v1.4.0 (2026-08-17, Goal G-mswtdmi1-420f8c):
  [FIX] 참조 검증을 assignment_id 3홉(work_assignments→work_schedules→inspection_set_id)으로 교체.
        safety_inspections.assignment_id 저장.
v1.3.0 (2026-08-17, Goal G-mswtdmi1-420f8c — 검토 ①ㄴ·②·⑤):
  [FIX] 제출된 inspection_set_item_id 를 검증한다 — 이 점검 세트의 항목만 참조로 인정.
        아닌 참조는 버리고 경고(가공 차단은 FK/검증 문제이지 수용만으로는 안 된다).
  [FIX] 참조가 맞으면 item_name 을 서버 마스터 값으로 덮어쓴다 — 이름 위조 경로 제거.
  [FIX] 경고 로그에서 phone 제거(inspection_id 로 추적).
v1.2.0 (2026-08-17): items[].inspection_set_item_id 수용·저장.
v1.1.0 (2026-04-24): Authorization(Optional)·photo_urls·worker_id/factory_id/schedule_id/inspection_type.

API:
  POST /worker-check/submit   점검 결과 저장
  GET  /worker-check/recent   최근 점검 이력 조회
  GET  /worker-check/history  점검 이력 조회 (앱 이력 화면)
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services import inspection_sets_svc as _iss
from services.status_vocab import normalize_inspection_result_write

log = logging.getLogger(__name__)
router = APIRouter(prefix="/worker-check", tags=["WorkerCheck"])


def _optional_auth(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Authorization이 있으면 검증, 없으면 None 반환."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    try:
        ur = supabase.auth.get_user(token)
        if not ur or not ur.user:
            raise HTTPException(status_code=401, detail={"error": "AUTH_EXPIRED"})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "AUTH_EXPIRED"})
    res = supabase.table("users").select("*").eq("auth_id", str(ur.user.id)).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return res.data[0]


class CheckItem(BaseModel):
    name: str
    result: str            # ok | bad | hold
    memo: Optional[str] = None
    note: Optional[str] = None       # 구버전 호환
    photo_urls: Optional[List[str]] = None
    inspection_set_item_id: Optional[str] = None  # v1.2.0 — 항목 참조(가공 항목 차단)


class CheckSubmitBody(BaseModel):
    phone: str             # 점검자 전화번호
    worker_id: Optional[str] = None
    factory_id: Optional[str] = None
    schedule_id: Optional[str] = None
    assignment_id: Optional[str] = None
    inspection_type: Optional[str] = None  # BEFORE_WORK | BEFORE_WORK_CON
    asset_name: Optional[str] = None       # 설비명
    items: List[CheckItem]
    factory_name: Optional[str] = None
    submitted_at: Optional[str] = None


@router.post("/submit")
def submit_check(
    body: CheckSubmitBody,
    current_user: Optional[dict] = Depends(_optional_auth),
):
    """
    작업자 점검 제출.
    1. users 테이블에서 전화번호로 inspector_id 조회
    2. safety_inspections 점검 세션 생성
    3. 참조 검증 후 safety_inspection_results 항목별 결과 저장
    """
    supabase = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    clean_phone = body.phone.replace("-", "").replace(" ", "")

    # 1. 점검자 ID 조회 (users 또는 worker_registry)
    inspector_id = None
    u = supabase.table("users").select("id, name").eq("phone", clean_phone).limit(1).execute()
    if not u.data:
        fmt = f"{clean_phone[:3]}-{clean_phone[3:7]}-{clean_phone[7:]}"
        u = supabase.table("users").select("id, name").eq("phone", fmt).limit(1).execute()
    if u.data:
        inspector_id = u.data[0]["id"]
        inspector_name = u.data[0].get("name", "")
    else:
        w = supabase.table("worker_registry").select("id, name").eq("phone", clean_phone).limit(1).execute()
        if w.data:
            inspector_id = w.data[0]["id"]
            inspector_name = w.data[0].get("name", "")
        else:
            inspector_name = clean_phone

    # 2. safety_inspections 점검 세션 생성
    has_issue = any(item.result == "bad" for item in body.items)
    has_hold = any((item.result or "").lower() == "hold" for item in body.items)
    status_code = "ISSUE" if has_issue else ("HOLD" if has_hold else "COMPLETED")

    # safety_inspections.assignment_id 의 FK 는 work_schedules(id) 를 참조한다(컬럼명과 불일치, 별건).
    # body.assignment_id 는 work_assignments.id 이므로 그대로 넣으면 FK 위반(500)이다.
    # → schedule_id(work_schedules.id)로 변환해 저장한다. body.schedule_id 가 오면 그것을 우선한다.
    schedule_ref = body.schedule_id
    factory_ref = None
    if not schedule_ref and body.assignment_id:
        # v1.5.0(WP-PARTITION-02C): 기존 조회에 factory_id 를 함께 취득(추가 SELECT 없음)
        _wa = supabase.table("work_assignments").select("schedule_id, factory_id") \
            .eq("id", body.assignment_id).limit(1).execute()
        if _wa.data:
            schedule_ref = _wa.data[0].get("schedule_id")
            factory_ref = _wa.data[0].get("factory_id")

    # v1.5.0: schedule 을 참조하는데 factory 를 아직 못 얻은 경우에만 parent 에서 보완.
    #   · body.schedule_id 직접 전달 경로
    #   · work_assignments.factory_id 가 비어 있는 경우
    if schedule_ref and not factory_ref:
        _ws = supabase.table("work_schedules").select("factory_id") \
            .eq("id", schedule_ref).limit(1).execute()
        factory_ref = _ws.data[0].get("factory_id") if _ws.data else None

    # v1.5.0: pair CHECK — (assignment_id IS NULL) = (factory_id IS NULL)
    #   schedule 을 참조하는데 factory 를 모르면 저장하지 않는다(무결성 우회 차단).
    if schedule_ref and not factory_ref:
        raise HTTPException(status_code=409, detail="일정의 사업장 정보를 확인할 수 없습니다")

    ins_res = supabase.table("safety_inspections").insert({
        "inspector_id": inspector_id,
        "inspection_date": now,
        "status_code": status_code,
        "assignment_id": schedule_ref,
        "factory_id": factory_ref,
    }).execute()

    if not ins_res.data:
        raise HTTPException(status_code=500, detail="점검 세션 생성 실패")

    inspection_id = ins_res.data[0]["id"]

    # 3. 참조 검증(가공 차단): assignment_id 3홉으로 세트 항목만 참조로 인정하고,
    #    참조가 맞으면 item_name 을 서버 마스터 값으로 덮어썼(이름 위조 경로 제거).
    allowed: dict = {}
    set_id = _iss.resolve_set_id_for_assignment(body.assignment_id) if body.assignment_id else None
    if set_id:
        arows = supabase.table("inspection_set_items").select("id, item_name").eq("inspection_set_id", set_id).execute().data or []
        allowed = {r["id"]: r.get("item_name") for r in arows}

    result_rows = []
    missing_ref = 0      # 참조 없음(구버전 앱)
    invalid_ref = 0      # 이 점검 세트의 항목이 아님 → 참조 버림
    unvalidated = 0      # assignment_id 없어 검증 불가 → 참조 유지
    for item in body.items:
        ref = item.inspection_set_item_id
        name = item.name
        if ref and set_id:
            if ref in allowed:
                name = allowed[ref] or item.name   # ② 이름을 서버 마스터로
            else:
                ref = None                          # ①ㄴ 이 점검의 항목이 아님
                invalid_ref += 1
        elif ref:
            unvalidated += 1
        else:
            missing_ref += 1
        row_data = {
            "inspection_id": inspection_id,
            "item_name": name,
            "result_code": normalize_inspection_result_write(item.result),
            "value_text": item.result,
            "note": item.memo or item.note or "",
            "checked_at": now,
        }
        if ref:
            row_data["inspection_set_item_id"] = ref
        if item.photo_urls:
            row_data["photo_urls"] = item.photo_urls
        result_rows.append(row_data)

    if result_rows:
        supabase.table("safety_inspection_results").insert(result_rows).execute()

    if missing_ref or invalid_ref or unvalidated:
        log.warning(
            f"[WorkerCheck] 참조 미검증 inspection_id={inspection_id} "
            f"missing={missing_ref} invalid={invalid_ref} unvalidated={unvalidated}/{len(body.items)} "
            f"— 이름만 저장(가공 항목 소지)"
        )

    issue_items = [i.name for i in body.items if i.result == "bad"]
    log.info(f"[WorkerCheck] 저장 inspection_id={inspection_id} issues={len(issue_items)}")

    return {
        "status": "success",
        "message": "점검 결과가 저장됐습니다.",
        "data": {
            "inspection_id": inspection_id,
            "status": status_code,
            "has_issue": has_issue,
            "issue_items": issue_items,
            "inspector": inspector_name,
            "total_items": len(body.items),
        }
    }


def _resolve_inspector_id(supabase, worker_id: Optional[str], phone: Optional[str]) -> Optional[str]:
    """worker_id(=users.id) 우선, 없으면 phone 으로 users→worker_registry 순 조회."""
    if worker_id:
        return worker_id
    if not phone:
        return None
    clean = phone.replace("-", "").replace(" ", "")
    if not clean:
        return None
    u = supabase.table("users").select("id").eq("phone", clean).limit(1).execute()
    if not u.data and len(clean) == 11:
        u = supabase.table("users").select("id").eq("phone", f"{clean[:3]}-{clean[3:7]}-{clean[7:]}").limit(1).execute()
    if u.data:
        return u.data[0]["id"]
    w = supabase.table("worker_registry").select("id").eq("phone", clean).limit(1).execute()
    if w.data:
        return w.data[0]["id"]
    return None


@router.get("/recent")
def get_recent_checks(phone: str, limit: int = 5):
    """점검자의 최근 점검 이력 조회"""
    supabase = get_supabase()
    clean = phone.replace("-", "").replace(" ", "")

    inspector_id = None
    u = supabase.table("users").select("id").eq("phone", clean).limit(1).execute()
    if not u.data:
        u = supabase.table("users").select("id").eq("phone", f"{clean[:3]}-{clean[3:7]}-{clean[7:]}").limit(1).execute()
    if u.data:
        inspector_id = u.data[0]["id"]

    if not inspector_id:
        return {"status": "success", "data": {"items": []}}

    res = supabase.table("safety_inspections") \
        .select("id, inspection_date, status_code") \
        .eq("inspector_id", inspector_id) \
        .order("inspection_date", desc=True) \
        .limit(limit).execute()

    return {"status": "success", "data": {"items": res.data or []}}


@router.get("/history")
def get_check_history(
    worker_id: Optional[str] = None,
    phone: Optional[str] = None,
    limit: int = 50,
):
    """점검자의 점검 이력 조회 (앱 이력 화면). worker_id(=users.id) 우선, 없으면 phone.

    앱 이력 화면이 GET /worker-check/history?worker_id=&phone= 로 호출한다.
    이 라우트가 없으면 항상 실패했고, 앱이 오류를 삼켜 '빈 이력'과 구분되지 않았다(결함 76).
    점검자를 못 찾으면 빈 목록을 돌려준다(정상 응답). 조회 자체 실패는 예외로 전파한다.
    """
    supabase = get_supabase()
    inspector_id = _resolve_inspector_id(supabase, worker_id, phone)
    if not inspector_id:
        return {"status": "success", "data": {"items": []}}

    res = supabase.table("safety_inspections") \
        .select("id, inspection_date, status_code") \
        .eq("inspector_id", inspector_id) \
        .order("inspection_date", desc=True) \
        .limit(limit).execute()

    return {"status": "success", "data": {"items": res.data or []}}
