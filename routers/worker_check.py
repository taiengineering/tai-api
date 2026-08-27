"""
작업자 현장 점검 제출 API — v1.5.0

v1.5.0 (2026-08-26, OBJ-01 KNOT-2 read cutover):
  [READ CUTOVER] GET /recent · GET /history 가 safety_inspections.status_code 직독 대신
        Effective Record 어댑터(fn_list_effective_inspection_records_by_inspector)를 소비한다.
        각 항목: id / inspection_date / inspection_status / result_summary / status_code(legacy alias).
        단일 RPC 로 inspector 유효 레코드 리스트를 받으므로 per-row Resolver N+1 = 0.
        POST /submit(writer) 는 불변 — 이 커밋은 read 경로만 바꿼다.
v1.4.1 (2026-08-17, Goal G-mswtdmi1-420f8c):
  [FIX] safety_inspections.assignment_id 의 FK 는 work_schedules(id) 를 참조한다(컬럼명과 대상 불일치).
        v1.4.0 이 work_assignments.id 를 그대로 넣어 FK 위반 → 500 → 앱이 "기기에 임시저장"으로 처리했다.
        (8/09 옇 제출은 assignment_id 가 없어 FK 검사를 타지 않아 성공했고, 새 앱은 assignment_id 를 보내 위반.)
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
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services import inspection_sets_svc as _iss
from services.inspection_record_resolver import (
    InspectionRecordError,
    list_effective_inspection_records_by_inspector,
)
from services.status_vocab import normalize_inspection_result_write
from services.worker_inspection_submission import (
    WorkerSubmissionError,
    submit_worker_inspection,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/worker-check", tags=["WorkerCheck"])

# result_summary(effective overall_result) → legacy status_code 별칭.
# result_summary 가 None 이면 inspection_status 를 status_code 로 쓴다(아래 _effective_worker_item).
_WORKER_STATUS_ALIAS = {"NORMAL": "COMPLETED", "ABNORMAL": "ISSUE", "HOLD": "HOLD"}


def _effective_worker_item(rec: dict) -> dict:
    """effective record → 워커 이력 항목 계약.

    id / inspection_date / inspection_status / result_summary / status_code(legacy alias).
    status_code 는 앱 구버전 호환용 별칭으로만 유도하며, effective 값을 재해석하지 않는다.
    """
    inspection_status = rec.get("inspection_status")
    result_summary = rec.get("overall_result")
    if result_summary is None:
        status_code = inspection_status
    else:
        status_code = _WORKER_STATUS_ALIAS.get(result_summary, result_summary)
    return {
        "id": rec.get("inspection_id"),
        "inspection_date": rec.get("inspection_date"),
        "inspection_status": inspection_status,
        "result_summary": result_summary,
        "status_code": status_code,
    }


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
    2. 일정 참조 해석 + parent work_schedules.factory_id companion (schedule-backed only)
    3. 참조 검증 후 원자적 생성 RPC(submit_worker_inspection) 1회 —
       base header(COMPLETED) + results + creation receipt 가 한 트랜잭션.
    """
    supabase = get_supabase()
    clean_phone = body.phone.replace("-", "").replace(" ", "")

    # submitted_at 은 필수 — 누락/공백을 서버 시각으로 대체하지 않는다(fail-closed 422).
    # submitted_at 은 오프라인 재전송 멱등의 정체성 앵커이므로, 서버 now 로 만들면
    # 동일 재전송이 매번 다른 submission_id 가 되어 replay 대신 409 로 변질된다.
    if not body.submitted_at:
        raise HTTPException(status_code=422, detail={"error": "WORKER_SUBMISSION_TIMESTAMP_INVALID"})

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

    # 2. 일정 참조 해석 (schedule-backed only).
    # safety_inspections.assignment_id 의 FK 는 work_schedules(id) 를 참조한다(컬럼명과 불일치, 별건).
    # body.assignment_id 는 work_assignments.id 이므로 schedule_id(work_schedules.id)로 변환한다.
    # body.schedule_id 가 오면 그것을 우선한다.
    schedule_ref = body.schedule_id
    if not schedule_ref and body.assignment_id:
        _wa = supabase.table("work_assignments").select("schedule_id").eq("id", body.assignment_id).limit(1).execute()
        if _wa.data:
            schedule_ref = _wa.data[0].get("schedule_id")

    # WP-04D: schedule-backed only. 신규 standalone(assignment_id NULL) 생성 금지 → fail-closed.
    if not schedule_ref:
        raise HTTPException(status_code=409, detail="일정 참조가 없어 점검을 생성할 수 없습니다.")

    # WP-04D: parent work_schedules 에서 factory_id companion 확보 (body.factory_id 신뢰 금지).
    # REV-2: work_schedules identity = (id, factory_id). id 는 factory 간 중복 가능하므로
    # limit(1) 로 임의 factory 를 고르지 않는다. 0→409(not-found), >1→409(AMBIGUOUS), 1→그 factory.
    # ambiguous 를 body.factory_id 로 disambiguate 하지 않는다(parent DB 사실로만 결정, fail-closed).
    _ws = supabase.table("work_schedules").select("id, factory_id").eq("id", schedule_ref).execute()
    _ws_rows = _ws.data or []
    if not _ws_rows:
        raise HTTPException(status_code=409, detail="일정을 찾을 수 없습니다.")
    if len(_ws_rows) > 1:
        raise HTTPException(status_code=409, detail={"error": "WORK_SCHEDULE_ID_AMBIGUOUS"})
    _parent_factory_id = _ws_rows[0].get("factory_id")
    if not _parent_factory_id:
        raise HTTPException(status_code=409, detail="일정의 factory_id를 확인할 수 없습니다.")

    # 3. 참조 검증(가공 차단): assignment_id 3홉으로 세트 항목만 참조로 인정하고,
    #    참조가 맞으면 item_name 을 서버 마스터 값으로 덮어씀(이름 위조 경로 제거).
    #    KNOT-3B: 직접 INSERT 대신 검증된 항목을 원자적 생성 RPC 로 넘긴다(base 직접 생성 없음).
    allowed: dict = {}
    set_id = _iss.resolve_set_id_for_assignment(body.assignment_id) if body.assignment_id else None
    if set_id:
        arows = supabase.table("inspection_set_items").select("id, item_name").eq("inspection_set_id", set_id).execute().data or []
        allowed = {r["id"]: r.get("item_name") for r in arows}

    items_payload = []
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
        items_payload.append({
            "inspection_set_item_id": ref,          # 검증 실패 시 None
            "name": name,
            "result_code": normalize_inspection_result_write(item.result),  # canonical NORMAL/ABNORMAL/HOLD
            "note": item.memo or item.note or "",
            "photo_urls": item.photo_urls or [],
        })

    # 4. 원자적 1회 생성: base header(COMPLETED) + results + creation receipt 가 한 트랜잭션.
    #    lifecycle 은 항상 COMPLETED; 결과 판정(NORMAL/ABNORMAL/HOLD)은 Resolver 가 결과에서 도출한다.
    #    submitted_at 은 위에서 필수 검증됨 → 클라이언트가 보낸 값을 그대로 전달(서버 now 대체 없음).
    #    같은 정체성 재전송은 receipt replay 로 멱등; invalid ISO 는 service 가 typed 에러로 막는다.
    try:
        _result = submit_worker_inspection(
            supabase,
            schedule_ref=str(schedule_ref),
            schedule_id=str(schedule_ref),
            factory_id=str(_parent_factory_id),
            inspector_id=inspector_id,
            phone=clean_phone,
            submitted_at=body.submitted_at,
            inspection_type=body.inspection_type,
            items=items_payload,
        )
    except WorkerSubmissionError as e:
        if e.code == "WORKER_SUBMISSION_TIMESTAMP_INVALID":
            raise HTTPException(status_code=422, detail={"error": e.code})
        if e.is_conflict:
            raise HTTPException(status_code=409, detail={"error": e.code})
        raise HTTPException(status_code=500, detail={"error": e.code})

    snap = _result.get("data") or {}
    inspection_id = snap.get("inspection_id")
    overall = snap.get("overall_result")
    # presentation alias 만 유도(NORMAL→COMPLETED, ABNORMAL→ISSUE, HOLD→HOLD); DB status_code 는 항상 COMPLETED.
    status_alias = _WORKER_STATUS_ALIAS.get(overall, overall)
    has_issue = overall == "ABNORMAL"

    if missing_ref or invalid_ref or unvalidated:
        log.warning(
            f"[WorkerCheck] 참조 미검증 inspection_id={inspection_id} "
            f"missing={missing_ref} invalid={invalid_ref} unvalidated={unvalidated}/{len(body.items)} "
            f"— 이름만 저장(가공 항목 소지)"
        )

    issue_items = [i.name for i in body.items if i.result == "bad"]
    log.info(
        f"[WorkerCheck] 저장 inspection_id={inspection_id} "
        f"issues={len(issue_items)} replayed={_result.get('replayed')}"
    )

    return {
        "status": "success",
        "message": "점검 결과가 저장됐습니다.",
        "data": {
            "inspection_id": inspection_id,
            "status": status_alias,
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
    """점검자의 최근 점검 이력 조회 (effective record 어댑터 경유)."""
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

    records = list_effective_inspection_records_by_inspector(inspector_id, limit, supabase)
    items = [_effective_worker_item(r) for r in records]
    return {"status": "success", "data": {"items": items}}


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

    KNOT-2: safety_inspections 직독 대신 effective record 어댑터를 소비한다.
    """
    supabase = get_supabase()
    inspector_id = _resolve_inspector_id(supabase, worker_id, phone)
    if not inspector_id:
        return {"status": "success", "data": {"items": []}}

    records = list_effective_inspection_records_by_inspector(inspector_id, limit, supabase)
    items = [_effective_worker_item(r) for r in records]
    return {"status": "success", "data": {"items": items}}
