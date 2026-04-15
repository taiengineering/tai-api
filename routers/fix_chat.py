# routers/fix_chat.py — TAI Fix 대화형 입력부 API
# v1.0.1 (2026-04-15): 오타 수정 (말씀/어느/걱정/혹시/존댓말)
# v1.0.0 (2026-04-15): 신규
#   POST /fix/chat/start    — 대화 세션 생성 (인증 불필요)
#   POST /fix/chat/message  — 메시지 전송 → Claude API → 응답 (인증 불필요)
#   POST /fix/chat/complete — 대화 완료 → matching_requests 저장 (회원 인증 필수)
import os
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Depends
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
  상대방의 첫 말에서 의도를 파악합니다.
  의도: REPAIR(수선) / APPOINTMENT(선임) / DIAGNOSIS(진단) / CONSULTING(컨설팅)
  의도가 불명확하면 한 번만 더 물어봅니다.

2단계 — 의도별 정보 수집 (3~5턴)
  파악된 의도에 맞는 필수 정보만 질문합니다.
  한 턴에 질문은 최대 2개까지만.
  상대방이 "모르겠다"고 하면 넘어갑니다.

3단계 — 정리 + 연결 제안 (마지막 턴)
  수집된 정보를 정리하여 보여주고,
  "전문 업체 연결을 도와드릴까요?"로 마무리합니다.

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
   ❌ "분전반을 차단하고 절연저항을 측정하세요"
   ✅ "전기안전 전문 업체의 현장 점검이 필요한 상황입니다"

2. 법률 자문을 하지 않는다.
   "전문가를 통해 확인하시는 게 정확합니다"로 넘긴다.

3. 가격을 말하지 않는다.

4. 주제를 벗어나면 부드럽게 돌린다.
   "저는 산업안전 분야 매칭 전문가라 그 부분은 도움드리기 어렵습니다.
    혹시 시설 관련해서 도움이 필요하신 부분이 있으신가요?"

5. 필수 정보가 모이면 즉시 연결 제안한다.

6. 공감하되 길지 않게. "걱정되시겠습니다" 한 줄이면 충분.

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
- 전문가답되 딱딱하지 않게
- 이모지 최소 사용 (📋 정리할 때만)
"""


class StartBody(BaseModel):
    user_type: str


class MessageBody(BaseModel):
    session_id: str
    message: str


class CompleteBody(BaseModel):
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


async def _call_claude(messages: list) -> tuple[str, int]:
    if not ANTHROPIC_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY 미설정")

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
        raise HTTPException(status_code=502, detail="Claude API 호출 실패")

    data   = resp.json()
    reply  = data["content"][0]["text"]
    tokens = data.get("usage", {}).get("output_tokens", 0)
    return reply, tokens


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

    reply, out_tokens = await _call_claude(history)
    new_turn = current_turn + 1

    sb.table("fix_chat_messages").insert([
        {"session_id": body.session_id, "role": "user",      "content": body.message},
        {"session_id": body.session_id, "role": "assistant", "content": reply, "token_count": out_tokens},
    ]).execute()

    is_last = (new_turn >= max_turns)
    sb.table("fix_chat_sessions").update({
        "current_turn": new_turn,
        "status": "COMPLETED" if is_last else "ACTIVE",
    }).eq("id", body.session_id).execute()

    return {
        "reply":           reply,
        "turn_number":     new_turn,
        "remaining_turns": max(0, max_turns - new_turn),
        "is_last_turn":    is_last,
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


def _parse_intent(text: str) -> str:
    t = text.upper()
    if "REPAIR" in t or "수선" in t or "수리" in t: return "REPAIR"
    if "APPOINTMENT" in t or "선임" in t or "대행" in t: return "APPOINTMENT"
    if "DIAGNOSIS" in t or "진단" in t or "검사" in t: return "DIAGNOSIS"
    if "CONSULTING" in t or "컨설팅" in t or "법령" in t: return "CONSULTING"
    return "REPAIR"
