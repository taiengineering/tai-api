# routers/fix_chat.py — TAI Fix 대화형 입력부 API
# v1.2.0 (2026-04-19): B1~B5 버그 수정
#   B2: _call_claude() KEY 없었 때 규칙 기반 폴백, 메시지 항상 DB 저장
#   B3: GET /fix/chat/sessions/{id}/messages 신규 — 이전 메시지 복원
#   B5: POST /fix/chat/claim 신규 — 비회원 세션 소유권 주장
#   B5: GET /fix/chat/my/sessions 신규 — 내 세션 목록
# v1.1.1 (2026-04-15): admin/stats 응답에 프론트 호환 편의 필드 추가
# v1.1.0 (2026-04-15): 어드민 API 3개 추가 (stats, sessions, session detail)
# v1.0.1 (2026-04-15): 오타 수정
# v1.0.0 (2026-04-15): 신규
import os
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from db.database import get_supabase
from routers.auth import get_current_user

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/fix/chat", tags=["TAI Fix 대화"])

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL  = "claude-sonnet-4-20250514"
MAX_TOKENS    = 500

SYSTEM_PROMPT = """당신은 TAI 산업안전 매칭 전문가입니다.
이름은 "TAI 전문가"입니다.

당신의 역할은 상대방의 상황을 정확히 파악하고,
적합한 전문 업체를 연결하기 위한 정보를 수집하는 것입니다.

# 대화 흐름

1단계 — 의도 파악 (1~2턴)
  의도: REPAIR(수선) / APPOINTMENT(선임) / DIAGNOSIS(진단) / CONSULTING(컨설팅)
  의도가 불명확하면 한 번만 더 물어보다.

2단계 — 의도별 정보 수집 (3~5턴)
  한 턴에 질문은 최대 2개까지만.
  "모르곊다"고 하면 넘어간다.

3단계 — 정리 + 연결 제안 (마지막 턴)
  수집된 정보를 정리하여 보여주고,
  "전문 업체 연결을 도와드릴까요?"로 마무리한다.

# 의도별 수집 항목

[REPAIR — 수선/수리]
  필수: 어떤 설비/부위, 증상, 긴급도, 현장 위치
  선택: 설비 연식, 수리 이력, 희망 일정

[APPOINTMENT — 선임/대행]
  필수: 업종, 근로자 수, 상주/비상주, 현장 위치
  선택: 현재 선임 여부, 시설 규모, 특수 위험요소

[DIAGNOSIS — 진단/검사]
  필수: 시설 유형, 진단 목적, 현장 위치
  선택: 연면적, 준공연도, 이전 진단 이력

[CONSULTING — 컨설팅/법령]
  필수: 관련 법령/제도, 업종, 규모
  선택: 현재 관리 체계, 지적사항 이력

# 절대 규칙

1. 해결책을 제시하지 않는다.
2. 법률 자문을 하지 않는다.
3. 가격을 말하지 않는다.
4. 주제를 벗어나면 부드럽게 돌린다.
5. 필수 정보가 모이면 즐시 연결 제안한다.

# 마지막 턴 형식

📋 상황 정리
• 의도: {REPAIR/APPOINTMENT/DIAGNOSIS/CONSULTING}
• 시설: {시설유형} ({위치})
• 상황: {요약}
• 긴급도: {높음/보통/여유}

이 상황에 적합한 전문 업체를 매칭해드릴 수 있습니다.
위 정보로 업체 매칭을 진행할까요?

# 응답 스타일

- 존댓말 사용
- 간결하게 (한 턴 최대 3~4문장)
- 전문가답되 딱딩하지 않게
- 이모지 최소 사용 (📋 정리할 때만)
"""

# 규칙 기반 폴백 응답 (ANTHROPIC_KEY 없을 때)
_FALLBACK_REPLIES = [
    "말씀해주신 상황을 파악하고 있습니다. 어떤 시설/설비에서 발생한 문제인가요? 현장 위치도 알려주시면 더 정확한 업체를 연결해드릴 수 있습니다.",
    "기본적인 상황 파악이 되었습니다. 얼마나 긴급한 상황인가요? (높음/보통/여유) 히망하시는 일정이 있으시면 알려주세요.",
    "평소 안전 관리를 위해 노력하시는 분이시군요. 지금까지 말씀해주신 정보를 바탕으로 적합한 전문 업체를 매칭해드릴 수 있습니다. 매칭을 진행할까요?",
]


class StartBody(BaseModel):
    user_type: str


class MessageBody(BaseModel):
    session_id: str
    message: str


class CompleteBody(BaseModel):
    session_id: str


class ClaimBody(BaseModel):
    session_id: str


USER_TYPE_MAX_TURNS = {
    "GUEST":      3,
    "MEMBER":     10,
    "SUBSCRIBER": 12,
}

GREETING = "안녕하세요. TAI 매칭 전문가입니다. 어떤 상황인지 편하게 말씀해주세요."

GUEST_LIMIT_MSG = (
    "상황이 어느 정도 파악되었습니다.\n"
    "전문 업체 매칭을 위해 회원가입이 필요합니다.\n\n"
    "지금까지 대화 내용은 저장되어 있으며,\n"
    "회원가입 후 바로 이어서 진행하실 수 있습니다."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _call_claude(messages: list, turn_index: int = 0) -> tuple:
    """
    Claude API 호출. KEY 없으면 규칙 기반 폴백 응답 반환.
    어떤 경우든 (reply, tokens) 로 돌려줌 — 메시지는 항상 DB에 저장됨.
    """
    # B2 수정: KEY 없으면 폴백 응답 (502 에러 리턴 안 함)
    if not ANTHROPIC_KEY:
        log.warning("[FIX_CHAT] ANTHROPIC_API_KEY 미설정 — 규칙 기반 폴백 응답")
        idx = min(turn_index, len(_FALLBACK_REPLIES) - 1)
        return _FALLBACK_REPLIES[idx], 0

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json={
                    "model":      CLAUDE_MODEL,
                    "max_tokens": MAX_TOKENS,
                    "system":     SYSTEM_PROMPT,
                    "messages":   messages,
                },
            )

        if resp.status_code != 200:
            log.error(f"[FIX_CHAT] Claude API 오류 {resp.status_code}: {resp.text[:300]}")
            # B2 수정: API 오류 시에도 폴백 응답 (메시지 DB 저장 보장)
            idx = min(turn_index, len(_FALLBACK_REPLIES) - 1)
            return _FALLBACK_REPLIES[idx], 0

        data   = resp.json()
        reply  = data["content"][0]["text"]
        tokens = data.get("usage", {}).get("output_tokens", 0)
        return reply, tokens

    except Exception as e:
        log.error(f"[FIX_CHAT] Claude API 예외: {e}")
        idx = min(turn_index, len(_FALLBACK_REPLIES) - 1)
        return _FALLBACK_REPLIES[idx], 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 API (인증 불필요)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/start")
def start_chat(body: StartBody):
    """새 대화 세션 생성 — 인증 불필요 (비회원/회원 모두)"""
    user_type = body.user_type.upper()
    if user_type not in USER_TYPE_MAX_TURNS:
        raise HTTPException(status_code=400, detail=f"user_type은 {list(USER_TYPE_MAX_TURNS.keys())} 중 하나여야 합니다")

    sb  = get_supabase()
    res = sb.table("fix_chat_sessions").insert({
        "user_type": user_type,
        "max_turns": USER_TYPE_MAX_TURNS[user_type],
        "status":    "ACTIVE",
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="세션 생성 실패")

    return {
        "session_id":       res.data[0]["id"],
        "max_turns":        USER_TYPE_MAX_TURNS[user_type],
        "greeting_message": GREETING,
    }


@router.post("/message")
async def send_message(body: MessageBody):
    """사용자 메시지 → Claude API → 응답 — 인증 불필요"""
    sb = get_supabase()

    sess_res = sb.table("fix_chat_sessions").select("*").eq("id", body.session_id).limit(1).execute()
    if not sess_res.data:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    sess         = sess_res.data[0]
    current_turn = sess["current_turn"]
    max_turns    = sess["max_turns"]

    if sess["status"] != "ACTIVE":
        raise HTTPException(status_code=400, detail=f"종료된 세션입니다 (status={sess['status']})")

    if current_turn >= max_turns:
        if sess["user_type"] == "GUEST":
            return {"reply": GUEST_LIMIT_MSG, "turn_number": current_turn,
                    "remaining_turns": 0, "is_last_turn": True, "is_guest_limit": True}
        raise HTTPException(status_code=400, detail="최대 턴 수를 초과했습니다")

    msgs_res = sb.table("fix_chat_messages").select("role, content").eq(
        "session_id", body.session_id).order("id").execute()
    history  = [{"role": m["role"], "content": m["content"]} for m in (msgs_res.data or [])]
    history.append({"role": "user", "content": body.message})

    # B2 수정: _call_claude가 예외 없이 (reply, tokens) 를 로드리 줌
    reply, out_tokens = await _call_claude(history, turn_index=current_turn)
    new_turn = current_turn + 1

    # 메시지 DB 저장 — 항상 실행
    sb.table("fix_chat_messages").insert([
        {"session_id": body.session_id, "role": "user",      "content": body.message},
        {"session_id": body.session_id, "role": "assistant", "content": reply, "token_count": out_tokens},
    ]).execute()

    is_last = (new_turn >= max_turns)
    update_data = {"current_turn": new_turn}
    if is_last:
        update_data["status"] = "COMPLETED"
    if not sess.get("intent") and new_turn >= 1:
        parsed = _parse_intent(reply)
        if parsed:
            update_data["intent"] = parsed

    sb.table("fix_chat_sessions").update(update_data).eq("id", body.session_id).execute()

    return {
        "reply":           reply,
        "turn_number":     new_turn,
        "remaining_turns": max(0, max_turns - new_turn),
        "is_last_turn":    is_last,
    }


@router.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    """
    B3 수정: 이전 메시지 복원 — 인증 불필요 (비회원 접근 허용)
    새로고침 시 프론트에서 이전 대화를 화면에 다시 렌더링하기 위해 사용
    """
    sb = get_supabase()

    sess_res = sb.table("fix_chat_sessions").select(
        "id, status, user_type, current_turn, max_turns, intent"
    ).eq("id", session_id).limit(1).execute()

    if not sess_res.data:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    sess = sess_res.data[0]

    msgs_res = sb.table("fix_chat_messages").select(
        "id, role, content, created_at"
    ).eq("session_id", session_id).order("id").execute()

    messages = msgs_res.data or []

    return {
        "session_id":      session_id,
        "status":          sess["status"],
        "user_type":       sess["user_type"],
        "current_turn":    sess["current_turn"],
        "max_turns":       sess["max_turns"],
        "remaining_turns": max(0, sess["max_turns"] - sess["current_turn"]),
        "intent":          sess.get("intent"),
        "messages":        messages,
    }


@router.post("/claim")
def claim_session(body: ClaimBody, current_user: dict = Depends(get_current_user)):
    """
    B5 수정: 비회원 세션 소유권 주장 — 회원 인증 필수
    로그인 후 localStorage의 session_id로 이 API를 호출하면:
    - user_id 연결
    - GUEST → MEMBER로 업그레이드 (max_turns 10으로 확대)
    """
    sb = get_supabase()

    sess_res = sb.table("fix_chat_sessions").select("*").eq("id", body.session_id).limit(1).execute()
    if not sess_res.data:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    sess = sess_res.data[0]

    # 이미 다른 사용자에 연결된 세션이면 거부
    if sess.get("user_id") and sess["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="다른 사용자의 세션입니다")

    # 이미 내 세션이면 누멡승리
    if sess.get("user_id") == current_user["id"]:
        return {
            "status":      "already_claimed",
            "session_id":  body.session_id,
            "user_type":   sess["user_type"],
            "max_turns":   sess["max_turns"],
            "current_turn": sess["current_turn"],
        }

    # 업그레이드: GUEST → MEMBER, max_turns 10으로 확장
    new_user_type = "MEMBER" if sess["user_type"] == "GUEST" else sess["user_type"]
    new_max_turns = USER_TYPE_MAX_TURNS.get(new_user_type, sess["max_turns"])

    # COMPLETED된 세션이면 ACTIVE로 재활성화 (어렵리는 대화 가능하도록)
    new_status = "ACTIVE" if sess["status"] == "COMPLETED" and sess["user_type"] == "GUEST" else sess["status"]

    update = {
        "user_id":   current_user["id"],
        "user_type": new_user_type,
        "max_turns": new_max_turns,
        "status":    new_status,
    }
    sb.table("fix_chat_sessions").update(update).eq("id", body.session_id).execute()

    return {
        "status":       "claimed",
        "session_id":   body.session_id,
        "user_type":    new_user_type,
        "max_turns":    new_max_turns,
        "current_turn": sess["current_turn"],
        "remaining_turns": max(0, new_max_turns - sess["current_turn"]),
    }


@router.get("/my/sessions")
def my_sessions(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """
    B5 수정: 내 세션 목록 — 회원 인증 필수
    로그인한 사용자의 쿇대화 세션 목록 반환
    """
    sb = get_supabase()

    offset = (page - 1) * size
    res = sb.table("fix_chat_sessions").select(
        "id, status, user_type, intent, current_turn, max_turns, created_at",
        count="exact"
    ).eq("user_id", current_user["id"]).order(
        "created_at", desc=True
    ).range(offset, offset + size - 1).execute()

    items = res.data or []
    total = res.count if res.count is not None else len(items)

    # 첫 메시지 미리보기 추가
    for it in items:
        msg_res = sb.table("fix_chat_messages").select("content").eq(
            "session_id", it["id"]
        ).eq("role", "user").order("id").limit(1).execute()
        it["preview"] = msg_res.data[0]["content"][:60] if msg_res.data else ""
        it["remaining_turns"] = max(0, it["max_turns"] - it["current_turn"])

    return {
        "items":       items,
        "total":       total,
        "page":        page,
        "size":        size,
        "total_pages": max(1, (total + size - 1) // size),
    }


@router.post("/complete")
def complete_chat(body: CompleteBody, current_user: dict = Depends(get_current_user)):
    """대화 완료 → matching_requests 저장 — 회원 인증 필수"""
    sb = get_supabase()

    sess_res = sb.table("fix_chat_sessions").select("*").eq("id", body.session_id).limit(1).execute()
    if not sess_res.data:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    sess = sess_res.data[0]
    if sess.get("request_id"):
        raise HTTPException(status_code=409, detail="이미 완료된 세션입니다")

    msgs_res = sb.table("fix_chat_messages").select("role, content").eq(
        "session_id", body.session_id).order("id").execute()
    messages = msgs_res.data or []
    if not messages:
        raise HTTPException(status_code=400, detail="대화 내용이 없습니다")

    last_assistant = next((m["content"] for m in reversed(messages) if m["role"] == "assistant"), "")
    intent    = sess.get("intent") or _parse_intent(last_assistant)
    full_text = "\n".join(f"[{m['role']}] {m['content']}" for m in messages)
    user_msgs = [m["content"] for m in messages if m["role"] == "user"]
    title     = user_msgs[0][:50] if user_msgs else "매칭 신청"

    now = _now()
    req_res = sb.table("matching_requests").insert({
        "user_id":        current_user["id"],
        "expert_type":    intent or "REPAIR",
        "title":          title,
        "description":    full_text,
        "source":         "FIX_CHAT",
        "status":         "RECEIVED",
        "status_history": [{"status": "RECEIVED", "at": now, "by": current_user["id"]}],
        "created_at":     now,
        "updated_at":     now,
    }).execute()

    if not req_res.data:
        raise HTTPException(status_code=500, detail="매칭 신청 저장 실패")

    request_id = req_res.data[0]["id"]
    sb.table("fix_chat_sessions").update({
        "request_id": request_id, "status": "COMPLETED", "user_id": current_user["id"],
    }).eq("id", body.session_id).execute()

    return {"status": "success", "request_id": request_id, "summary": last_assistant[:500]}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 어드민 API — 권한은 헤더가드 PLATFORM_AUDIT_VIEW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/admin/stats")
def admin_stats(current_user: dict = Depends(get_current_user)):
    """상담 통계 — 전체/상태별/의도별/오늘/토큰"""
    sb = get_supabase()

    all_res = sb.table("fix_chat_sessions").select(
        "id, status, user_type, intent, current_turn, request_id, created_at"
    ).execute()
    rows = all_res.data or []
    total = len(rows)

    by_status = {}
    for r in rows:
        s = r.get("status") or "UNKNOWN"
        by_status[s] = by_status.get(s, 0) + 1

    by_intent = {}
    for r in rows:
        i = r.get("intent") or "UNKNOWN"
        by_intent[i] = by_intent.get(i, 0) + 1

    by_user_type = {}
    for r in rows:
        ut = r.get("user_type") or "UNKNOWN"
        by_user_type[ut] = by_user_type.get(ut, 0) + 1

    today_str   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_count = sum(1 for r in rows if (r.get("created_at") or "")[:10] == today_str)
    total_turns = sum(r.get("current_turn", 0) for r in rows)

    token_res    = sb.table("fix_chat_messages").select("token_count").not_.is_("token_count", "null").execute()
    total_tokens = sum(m.get("token_count", 0) for m in (token_res.data or []))
    connected    = sum(1 for r in rows if r.get("request_id"))

    return {
        "total":           total,
        "active":          by_status.get("ACTIVE", 0),
        "completed":       connected,
        "guest":           by_user_type.get("GUEST", 0),
        "total_sessions":  total,
        "today_sessions":  today_count,
        "total_turns":     total_turns,
        "total_tokens":    total_tokens,
        "connected":       connected,
        "by_status":       by_status,
        "by_intent":       by_intent,
        "by_user_type":    by_user_type,
    }


@router.get("/admin/sessions")
def admin_sessions(
    status:    Optional[str] = Query(None),
    user_type: Optional[str] = Query(None),
    intent:    Optional[str] = Query(None),
    page:      int           = Query(1, ge=1),
    size:      int           = Query(20, ge=1, le=100),
    current_user: dict       = Depends(get_current_user),
):
    """상담 세션 목록 — 필터/페이징"""
    sb = get_supabase()

    q = sb.table("fix_chat_sessions").select(
        "id, user_id, user_type, status, intent, current_turn, max_turns, request_id, created_at",
        count="exact"
    )
    if status:    q = q.eq("status",    status.upper())
    if user_type: q = q.eq("user_type", user_type.upper())
    if intent:    q = q.eq("intent",    intent.upper())

    offset = (page - 1) * size
    q = q.order("created_at", desc=True).range(offset, offset + size - 1)
    res = q.execute()
    items       = res.data or []
    total_count = res.count if res.count is not None else len(items)

    session_ids = [it["id"] for it in items]
    previews    = {}
    if session_ids:
        for sid in session_ids:
            msg_res = sb.table("fix_chat_messages").select("content").eq(
                "session_id", sid).eq("role", "user").order("id").limit(1).execute()
            if msg_res.data:
                previews[sid] = msg_res.data[0]["content"][:80]
    for it in items:
        it["preview"] = previews.get(it["id"], "")

    return {
        "items":       items,
        "total":       total_count,
        "page":        page,
        "size":        size,
        "total_pages": max(1, (total_count + size - 1) // size),
    }


@router.get("/admin/sessions/{session_id}")
def admin_session_detail(session_id: str, current_user: dict = Depends(get_current_user)):
    """상담 세션 상세 + 전체 메시지"""
    sb = get_supabase()

    sess_res = sb.table("fix_chat_sessions").select("*").eq("id", session_id).limit(1).execute()
    if not sess_res.data:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    session  = sess_res.data[0]
    msgs_res = sb.table("fix_chat_messages").select(
        "id, role, content, token_count, created_at"
    ).eq("session_id", session_id).order("id").execute()
    messages     = msgs_res.data or []
    total_tokens = sum(m.get("token_count", 0) for m in messages if m.get("token_count"))

    matching_request = None
    if session.get("request_id"):
        mr_res = sb.table("matching_requests").select(
            "id, expert_type, title, status, created_at"
        ).eq("id", session["request_id"]).limit(1).execute()
        if mr_res.data:
            matching_request = mr_res.data[0]

    return {
        "session":          session,
        "messages":         messages,
        "message_count":    len(messages),
        "total_tokens":     total_tokens,
        "matching_request": matching_request,
    }


def _parse_intent(text: str) -> str:
    t = text.upper()
    if "REPAIR"      in t or "수선" in t or "수리" in t: return "REPAIR"
    if "APPOINTMENT" in t or "선임" in t or "대행" in t: return "APPOINTMENT"
    if "DIAGNOSIS"   in t or "진단" in t or "검사" in t: return "DIAGNOSIS"
    if "CONSULTING"  in t or "컨설팅" in t or "법령" in t: return "CONSULTING"
    return "REPAIR"
