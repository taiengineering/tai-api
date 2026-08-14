"""
관리자 통합 인박스 — inquiries 목록·수정·직접 등록

Doc: docs/inbox-system/PHASE4_INQUIRY_LIST.md

[2026-07-29 P2-5] 답변(status=ANSWERED + answer) 저장 시 고객에게 실제 발송 연동.
  메일 우선(email 있으면), 없으면 SMS 안내. notify_svc 위임. 발송 실패는 저장 결과에
  영향을 주지 않고 응답의 notify 필드에 상태만 담는다(베스트에포트).

[트랙 A 마감] 고객응대 taxonomy 표시용 label 을 응답에 additive projection.
  값/label SoT 는 services/support_taxonomy.py 하나다. 여기서는 그 label 함수만 호출해
  type_label/subtype_label/resolution_axis_label 3개를 응답 row 에 덧붙인다(DB 컬럼 아님).
  분류/추론/LLM/저장은 하지 않는다 — 값은 트랙 B 분류기가 채운다(현재 전부 NULL → label None).
  GET items · POST/PATCH 반환 row 에 동일 helper(support_taxonomy.project_labels)를 재사용한다(중복 구현 금지).

[리스트/검색 개편] GET /admin/inquiries 에 taxonomy 필터(type_code / resolution_axis)를 additive 로 추가.
  - 값 '__none__' 이면 IS NULL(미분류) 필터. 그 외엔 support_taxonomy 로 유효성 검사 후 eq 필터.
  - 유효하지 않은 값은 400. 기존 필터/정렬/계약 무변경(추가만).
  - sort_key 에 type_code / resolution_axis 추가(리스트 컬럼 정렬 대응).
  - GET /admin/inquiries/taxonomy-options: 필터 드롭다운 선택지(문의유형/처리방식)를 SoT 에서 내려준다
    (프론트가 label 을 재정의하지 않도록 — SoT 단일 유지). taxonomy_snapshot() 재사용, 신규 로직 없음.
    라우터 순서: 고정 경로이므로 동적 경로(/{inquiry_id}) 앞에 둔다.

[인증 경계 보정 — 마감] 이 라우터는 public.py(인증 불필요 그룹)에 등록되고 그룹 등록/미들웨어가
  인증을 강제하지 않으므로, 인증은 이 파일에서 직접 보장해야 한다. 기존 _require_bearer 는
  'Bearer ' 접두사 문자열만 확인해(JWT/role 검증 없음) 사실상 무인증이었다 → 취약(INSECURE).
  보정: repo 공통 auth SoT(routers.auth.get_current_user, Supabase 토큰 실검증)를 재사용하고
  admin role(system_codes role '001' 최고관리자)만 통과시키는 얇은 의존성 require_admin 을 둔다.
  - 신규 인증 프레임워크/JWT 파서 만들지 않음(기존 helper 재사용).
  - /admin/inquiries 전체(GET 목록·taxonomy-options·POST·PATCH)에 동일 admin 경계 적용.
  - 기대 계약: 무토큰/무효 토큰 → 401(get_current_user), 일반 회원 → 403, 최고관리자 → 200.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.support_taxonomy import project_labels, is_valid_type, is_valid_axis, taxonomy_snapshot

router = APIRouter(prefix="/admin/inquiries", tags=["관리 - 통합 인박스"])

# admin 경계 = 시스템 전체 관리자(system_codes role '001' 최고관리자).
# 회사/사업장 관리자('002')는 super-admin 콘솔 대상이 아니므로 포함하지 않는다(최소 권한).
ADMIN_ROLE_CODES = {"001"}

INQUIRY_CATEGORIES = {
    "consult",
    "safety",
    "electric",
    "risk",
    "csia",
    "saas",
    "repair",
    "edu",
    "partner",
    "other",
}
FEEDBACK_CATEGORIES = {
    "fb_feature",
    "fb_bug",
    "fb_ux",
    "fb_idea",
    "fb_praise",
}

SORT_KEYS = {
    "created_at", "no", "category", "title", "name", "status", "assigned", "source",
    "inquiry_type", "type_code", "resolution_axis",
}

# 미분류(NULL) 필터를 요청하는 특수 토큰(클라이언트 → 서버 약속값).
NONE_FILTER_TOKEN = "__none__"


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """admin 경계 의존성. get_current_user(토큰 실검증) 통과 후 role 이 admin 인지 확인.

    - 무토큰/무효/만료 토큰 → get_current_user 가 401.
    - 유효 토큰이지만 admin(role '001') 아님 → 403.
    - admin → current_user 반환.
    role 확인만 추가한다(신규 인증 체계 없음). super-admin 콘솔 전용 경계.
    """
    role = str(current_user.get("role_code") or "").strip()
    if role not in ADMIN_ROLE_CODES:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return current_user


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _notify_answer(row: Dict[str, Any], answer: str) -> Dict[str, Any]:
    """답변 등록 시 고객 실발송(베스트에포트). 메일 우선, 없으면 SMS 안내."""
    email = (row.get("email") or "").strip()
    phone = (row.get("phone") or "").strip()
    name = row.get("name") or "고객"
    title = row.get("title") or "문의"
    try:
        from services import notify_svc
        if email:
            subject = f"[TAI] 문의 답변 안내 - {title}"
            text = (
                f"안녕하세요, {name}님.\n\n"
                f"문의해 주신 내용에 대한 답변입니다.\n\n"
                f"{answer}\n\n"
                f"감사합니다.\nTAI Engineering"
            )
            r = notify_svc.send("MAIL", target=email, subject=subject, message=text, actor_id="admin")
            return {"channel": "MAIL", "status": r.get("status"), "provider": r.get("provider"), "error": r.get("error")}
        if phone:
            r = notify_svc.send(
                "SMS", target=phone,
                message="[TAI] 문의에 답변이 등록되었습니다. 확인 부탁드립니다.",
                actor_id="admin",
            )
            return {"channel": "SMS", "status": r.get("status"), "provider": r.get("provider"), "error": r.get("error")}
        return {"channel": None, "status": "skipped", "error": "수신 연락처 없음"}
    except Exception as e:  # noqa: BLE001
        return {"channel": None, "status": "failed", "error": str(e)}


def _next_inquiry_no(supabase) -> str:
    utc = datetime.now(timezone.utc)
    day = utc.strftime("%Y%m%d")
    prefix = f"TAI-INQ-{day}-"
    start = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    res = (
        supabase.table("inquiries")
        .select("id", count="exact")
        .gte("created_at", start.isoformat())
        .execute()
    )
    n = (res.count or 0) + 1
    return f"{prefix}{n:04d}"


def _safe_or_pattern(q: str) -> Optional[str]:
    s = (q or "").strip()[:120]
    for ch in "*,%()":
        s = s.replace(ch, " ")
    s = s.strip()
    return s if s else None


class InquiryCreateBody(BaseModel):
    inquiry_type: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    title: Optional[str] = None
    content: str = Field(..., min_length=1)
    name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_member: bool = False


class InquiryPatchBody(BaseModel):
    answer: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned: Optional[str] = None


def _validate_category(inquiry_type: str, category: str) -> None:
    cat = (category or "").strip()
    it = (inquiry_type or "").strip().upper()
    if it == "INQUIRY" and cat not in INQUIRY_CATEGORIES:
        raise HTTPException(status_code=400, detail="INQUIRY 유형에 맞지 않는 category 입니다.")
    if it == "FEEDBACK" and cat not in FEEDBACK_CATEGORIES:
        raise HTTPException(status_code=400, detail="FEEDBACK 유형에 맞지 않는 category 입니다.")
    if it not in ("INQUIRY", "FEEDBACK"):
        raise HTTPException(status_code=400, detail="inquiry_type은 INQUIRY 또는 FEEDBACK 이어야 합니다.")


@router.get("")
def admin_list_inquiries(
    _admin: dict = Depends(require_admin),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    source: Optional[str] = Query(None, description="direct | marketing | safe"),
    inquiry_type: Optional[str] = Query(None, description="INQUIRY | FEEDBACK"),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    type_code: Optional[str] = Query(None, description="T1~T7 | __none__(미분류)"),
    resolution_axis: Optional[str] = Query(None, description="KNOWLEDGE|INVESTIGATION|HANDOFF | __none__(미분류)"),
    is_member: Optional[str] = Query(None, description="1=회원, 0=비회원"),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    q: Optional[str] = Query(None, description="통합검색"),
    sort_key: str = Query("created_at"),
    sort_dir: str = Query("desc"),
):
    if sort_dir not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="sort_dir은 asc 또는 desc 여야 합니다.")
    if sort_key not in SORT_KEYS:
        raise HTTPException(status_code=400, detail="지원하지 않는 sort_key 입니다.")
    supabase = get_supabase()
    offset = (page - 1) * size
    desc = sort_dir == "desc"

    query = supabase.table("inquiries").select("*", count="exact")

    if source:
        query = query.eq("source", source.strip())
    if inquiry_type:
        query = query.eq("inquiry_type", inquiry_type.strip().upper())
    if category:
        query = query.eq("category", category.strip())
    if status:
        query = query.eq("status", status.strip())

    # taxonomy 필터(additive). '__none__' → IS NULL(미분류). 그 외엔 SoT 유효성 검사 후 eq.
    if type_code:
        tc = type_code.strip()
        if tc == NONE_FILTER_TOKEN:
            query = query.is_("type_code", "null")
        elif is_valid_type(tc):
            query = query.eq("type_code", tc)
        else:
            raise HTTPException(status_code=400, detail="지원하지 않는 type_code 입니다.")
    if resolution_axis:
        ax = resolution_axis.strip()
        if ax == NONE_FILTER_TOKEN:
            query = query.is_("resolution_axis", "null")
        elif is_valid_axis(ax):
            query = query.eq("resolution_axis", ax)
        else:
            raise HTTPException(status_code=400, detail="지원하지 않는 resolution_axis 입니다.")

    if is_member == "1":
        query = query.eq("is_member", True)
    elif is_member == "0":
        query = query.eq("is_member", False)

    if from_date:
        query = query.gte("created_at", f"{from_date.strip()}T00:00:00+00:00")
    if to_date:
        query = query.lt("created_at", f"{to_date.strip()}T23:59:59.999999+00:00")

    if q and q.strip():
        pat = _safe_or_pattern(q)
        if pat:
            query = query.or_(
                f"name.ilike.*{pat}*,company.ilike.*{pat}*,title.ilike.*{pat}*,"
                f"content.ilike.*{pat}*,email.ilike.*{pat}*,phone.ilike.*{pat}*"
            )

    try:
        res = query.order(sort_key, desc=desc).range(offset, offset + size - 1).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"조회 실패: {e!s}") from e

    # 표시용 taxonomy label 을 additive projection(SoT=support_taxonomy). 값 없으면 label None.
    items = [project_labels(r) for r in (res.data or [])]

    return {
        "status": "success",
        "data": {
            "items": items,
            "total": res.count or 0,
            "page": page,
            "size": size,
        },
    }


@router.get("/taxonomy-options")
def admin_inquiry_taxonomy_options(
    _admin: dict = Depends(require_admin),
):
    """문의 필터 드롭다운 선택지(문의유형 T1~T7 / 처리방식 3종)를 SoT 에서 내려준다.

    프론트가 label 을 재정의하지 않도록(SoT 단일 유지) taxonomy_snapshot() 의 types/resolution_axes 만 반환.
    subtype 은 필터 대상이 아니므로 내려주지 않는다(현 개편 범위: 문의유형 + 처리방식).
    admin 경계는 /admin/inquiries 목록과 동일(require_admin) — DB 조회 없음, 상수 스냅샷.
    """
    snap = taxonomy_snapshot()
    return {
        "status": "success",
        "data": {
            "types": snap.get("types", []),
            "resolution_axes": snap.get("resolution_axes", []),
        },
    }


@router.post("")
def admin_create_inquiry(
    body: InquiryCreateBody,
    _admin: dict = Depends(require_admin),
):
    it = body.inquiry_type.strip().upper()
    _validate_category(it, body.category)

    supabase = get_supabase()
    no = _next_inquiry_no(supabase)
    title = (body.title or "").strip() or None
    row: Dict[str, Any] = {
        "no": no,
        "source": "direct",
        "inquiry_type": it,
        "category": body.category.strip(),
        "title": title,
        "content": body.content.strip(),
        "name": (body.name or "").strip() or None,
        "company": (body.company or "").strip() or None,
        "phone": (body.phone or "").strip() or None,
        "email": (body.email or "").strip() or None,
        "is_member": bool(body.is_member),
        "status": "RECEIVED",
        "priority": "NORMAL",
    }
    try:
        res = supabase.table("inquiries").insert(row).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"등록 실패: {e!s}") from e
    if not res.data:
        raise HTTPException(status_code=500, detail="등록 후 데이터를 확인할 수 없습니다.")
    # 목록과 동일한 label projection 재사용(프론트 캐시 upsert 시 표시 일관성).
    return {"status": "success", "data": project_labels(res.data[0])}


@router.patch("/{inquiry_id}")
def admin_patch_inquiry(
    inquiry_id: UUID,
    body: InquiryPatchBody,
    _admin: dict = Depends(require_admin),
):
    raw = body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)
    patch: Dict[str, Any] = {k: v for k, v in raw.items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")

    st = patch.get("status")
    ans = patch.get("answer")
    is_answer_event = st == "ANSWERED" and ans and str(ans).strip()
    if is_answer_event:
        patch["replied_at"] = _now_iso()

    supabase = get_supabase()
    try:
        res = supabase.table("inquiries").update(patch).eq("id", str(inquiry_id)).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"저장 실패: {e!s}") from e
    if not res.data:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")

    row = res.data[0]
    # [P2-5] 답변 등록 시 고객 실발송(베스트에포트). 발송 실패해도 저장은 성공 처리.
    notify_result = _notify_answer(row, str(ans).strip()) if is_answer_event else None
    # 프론트가 PATCH 응답 row 를 캐시에 upsert 하므로, 목록과 동일 label projection 을 붙여 표시 일관성 유지.
    return {"status": "success", "data": project_labels(row), "notify": notify_result}
