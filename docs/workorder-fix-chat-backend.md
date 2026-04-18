# TAI Fix 대화형 입력부 — 백엔드 작업지시서

**작성일:** 2026-04-15
**방식:** 단계별 진행

---

## 배경

TAI Fix 입력부를 Claude API 기반 대화형으로 구현.
시스템 프롬프트: `docs/tai-fix-chat-system-prompt.md` 참고.

## 단계 1: 대화 세션 API 생성

**프롬프트:**
```
routers/fix_chat.py 파일을 새로 만들어주세요.
prefix: /fix/chat

엔드포인트 3개:

1. POST /fix/chat/start
   - 새 대화 세션 생성
   - 요청: { user_type: 'GUEST' | 'MEMBER' | 'SUBSCRIBER' }
   - 응답: { session_id, max_turns, greeting_message }
   - user_type별 max_turns: GUEST=3, MEMBER=7, SUBSCRIBER=10
   - session_id는 UUID
   - greeting_message: "안녕하세요. TAI 매칭 전문가입니다. 어떤 상황인지 편하게 말씀해주세요."
   - DB: fix_chat_sessions 테이블에 저장

2. POST /fix/chat/message
   - 사용자 메시지 전송 → Claude API 호출 → 응답 반환
   - 요청: { session_id, message }
   - 로직:
     a. fix_chat_sessions에서 세션 조회
     b. 현재 턴수 확인 → max_turns 초과 시 거부
     c. fix_chat_messages에서 이전 대화 내역 조회
     d. Claude API 호출 (system prompt + 대화 내역 + 새 메시지)
     e. 응답을 fix_chat_messages에 저장
     f. 턴수 증가
   - 응답: { reply, turn_number, remaining_turns, is_last_turn }
   - is_last_turn=true면 응답에 연결 CTA 포함

3. POST /fix/chat/complete
   - 대화 완료 → matching_requests에 저장
   - 요청: { session_id }
   - 로직:
     a. fix_chat_messages에서 전체 대화 조회
     b. 마지막 턴의 📋 정리 내용 파싱
     c. matching_requests에 INSERT
   - 응답: { request_id, summary }
   - 비회원은 이 엔드포인트 호출 불가 (회원만)

Claude API 호출:
  model: claude-sonnet-4-20250514
  max_tokens: 500 (응답 토큰 제한)
  system prompt: docs/tai-fix-chat-system-prompt.md의 System Prompt 섹션
  환경변수: ANTHROPIC_API_KEY (Fly.io에 등록 필요)

인증:
  /fix/chat/start — 인증 없이 가능 (비회원도)
  /fix/chat/message — 인증 없이 가능 (session_id로 제어)
  /fix/chat/complete — 회원 인증 필수

branch: dev에 push_files.
이 단계에서는 이 파일만 만듭니다.
```

**완료 조건:** fix_chat.py dev 커밋

---

## 단계 2: DB 테이블 생성

**프롬프트:**
```
Supabase MCP로 테이블 2개를 생성해주세요.

fix_chat_sessions:
  id UUID PK DEFAULT gen_random_uuid()
  user_id UUID (nullable — 비회원은 NULL)
  user_type VARCHAR(20) NOT NULL — GUEST / MEMBER / SUBSCRIBER
  max_turns INT NOT NULL
  current_turn INT DEFAULT 0
  intent VARCHAR(20) — REPAIR / APPOINTMENT / DIAGNOSIS / CONSULTING (대화 중 파악)
  collected_data JSONB DEFAULT '{}' — 수집된 정보
  status VARCHAR(20) DEFAULT 'ACTIVE' — ACTIVE / COMPLETED / EXPIRED
  request_id UUID (nullable — complete 시 연결)
  created_at TIMESTAMPTZ DEFAULT now()
  expires_at TIMESTAMPTZ DEFAULT (now() + interval '24 hours')

fix_chat_messages:
  id SERIAL PK
  session_id UUID FK(fix_chat_sessions) ON DELETE CASCADE
  role VARCHAR(10) NOT NULL — user / assistant
  content TEXT NOT NULL
  token_count INT
  created_at TIMESTAMPTZ DEFAULT now()

apply_migration 사용.
```

**완료 조건:** 테이블 2개 생성 완료

---

## 단계 3: main.py 라우터 등록

**프롬프트:**
```
main.py에 fix_chat 라우터 추가.

from routers import fix_chat
app.include_router(fix_chat.router)

공개 엔드포인트 그룹에 등록.
branch: dev.
```

**완료 조건:** main.py 커밋

---

## 단계 4: ANTHROPIC_API_KEY 확인

**프롬프트:**
```
Fly.io에 ANTHROPIC_API_KEY 환경변수가 등록되어 있는지 확인.
없으면 등록 방법 안내.

테스트:
curl -X POST https://api.taieng.co.kr/fix/chat/start \
  -H 'Content-Type: application/json' \
  -d '{"user_type": "GUEST"}'

→ session_id가 반환되는지 확인.
```

**완료 조건:** API 동작 확인

---

## 단계 5: 대화 테스트

**프롬프트:**
```
Supabase MCP로 테스트.

1. 세션 생성 확인
   SELECT * FROM fix_chat_sessions ORDER BY created_at DESC LIMIT 1;

2. 메시지 저장 확인
   SELECT * FROM fix_chat_messages WHERE session_id = '...' ORDER BY id;

3. 턴 제한 확인
   GUEST 세션에서 4번째 메시지 전송 시 거부되는지

4. 의도 분류 확인
   "분전반에서 냄새" → intent = REPAIR
   "안전관리자 구해야" → intent = APPOINTMENT
```

**완료 조건:** 의도 분류 + 턴 제한 + 대화 저장 정상
