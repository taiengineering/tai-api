# Fix Chat 대화 저장·복원 버그 수정 작업지시서

**작성일**: 2026-04-19
**우선순위**: 높음 (핵심 기능 미작동)
**관련 파일**:
- 백엔드: `routers/fix_chat.py` (v1.1.1)
- 프론트: `taiengineering/taieng/nexas/fix-request.html`
- DB: `fix_chat_sessions`, `fix_chat_messages`, `matching_requests`

---

## 버그 요약

fix-request 채팅 페이지에서:
1. 대화가 DB에 저장되지 않음
2. 새로고침/재방문 시 이전 대화가 출력되지 않음
3. 로그인 후에도 비회원 대화가 연결되지 않음

---

## 버그 상세 (5건)

### 🔒 B1: sendMessage() API 실패 시 더미 폴백 → DB 미저장

**현상**: 사용자가 메시지를 보내면 화면에는 응답이 나오지만 DB에는 아무것도 저장 안 됨

**원인**: `sendMessage()`의 try/catch 구조
```javascript
try {
  const res = await fetch(`${API}/fix/chat/message`, {...});
  // API 성공 시 정상 처리
} catch(e) {
  // API 실패 → 더미 응답 반환, DB에는 아무것도 안 씀
  const dummies = ['말씀해주신 상황을...', ...];
  appendExpertMsg(dummies[...]);
}
```

**증거**: DB에 16개 세션 존재, 최근 5개 모두 `current_turn=0`

**수정**: 
- catch 블록에서 더미 응답 제거
- API 실패 시 사용자에게 "일시적 오류" 메시지 표시 + 재시도 버튼
- 또는 메시지를 로컬에 큐잉하여 재전송

### 🔒 B2: Claude API 호출 실패 (백엔드)

**현상**: `/fix/chat/message` API가 502 반환

**원인 추정**: `ANTHROPIC_API_KEY` 환경변수가 Fly.io에 미설정 또는 만료

**확인 방법**:
```bash
fly secrets list -a tai-api-prod | grep ANTHROPIC
```

**수정**:
- ANTHROPIC_API_KEY가 없으면 → 백엔드에서 기본 응답 반환 (더미가 아닌 서버 측 폴백)
- fix_chat.py의 `_call_claude()`에서 KEY 없을 때 간단한 규칙 기반 응답 반환
- 메시지는 KEY 유무와 무관하게 항상 DB에 저장

### 🔒 B3: 새로고침 시 이전 메시지 미복원

**현상**: 페이지 새로고침 시 "이전 대화를 이어서 진행하겠습니다"만 출력, 실제 대화 내용은 안 보임

**원인**: `startChat()`에서 savedSession이 있으면 인사만 하고 return
```javascript
const savedSession = sessionStorage.getItem('fix_session_id');
if (savedSession) {
  sessionId = savedSession;
  appendExpertMsg('이전 대화를 이어서...');
  return; // ← 이전 메시지를 불러오는 API 호출 없음
}
```

**수정**:
- 저장된 session_id가 있으면 → API로 이전 메시지 목록 조회
- 조회된 메시지를 시간순으로 chatBody에 렌더링
- 필요 API: `GET /fix/chat/sessions/{session_id}/messages` (신규 추가)

### 🔒 B4: sessionStorage → localStorage 변경

**현상**: 브라우저 탭/창 닫으면 session_id 소멸 → 대화 영구 손실

**원인**: `sessionStorage` 사용 (탭 닫으면 삭제됨)

**수정**:
- `sessionStorage` → `localStorage`로 변경
- key: `tai_fix_session_id`
- 세션이 COMPLETED 상태이면 localStorage에서 삭제

### 🔒 B5: 비회원→회원 전환 시 세션 연결

**현상**: 비회원이 대화 후 회원가입/로그인해도 이전 대화에 접근 불가

**원인**: 
1. 비회원 세션의 `user_id`가 null
2. 로그인 후 세션을 사용자에게 연결하는 로직 없음
3. 사용자용 세션 조회 API가 없음 (admin API만 존재)

**수정 (백엔드)**:
- `POST /fix/chat/claim` — 로그인한 사용자가 세션 소유권 주장
  - 요청: `{ session_id: "xxx" }` + JWT 인증
  - 동작: `fix_chat_sessions.user_id = 현재 사용자 id` + `max_turns 업그레이드 (MEMBER=10)`
  - 조건: 해당 세션의 user_id가 null일 때만 허용
- `GET /fix/chat/my/sessions` — 내 세션 목록 조회
  - 응답: `[{id, status, intent, current_turn, created_at, preview}]`
- `GET /fix/chat/my/sessions/{session_id}/messages` — 내 세션 메시지 조회
  - 응답: `[{role, content, created_at}]`

**수정 (프론트)**:
- 로그인 성공 후 → localStorage에 session_id가 있으면 → `/fix/chat/claim` 호출
- claim 성공 → 이전 메시지 불러와서 화면에 렌더링
- turnBadge를 MEMBER 기준으로 업데이트 (10턴)

---

## 작업 순서

### Phase 1: 즉시 (DB 저장 보장)
1. B2: ANTHROPIC_API_KEY 확인 + 백엔드 폴백 추가
2. B1: 프론트 catch 블록 수정 → 더미 제거, 에러 표시
3. B4: sessionStorage → localStorage 변경

### Phase 2: 대화 복원
4. B3: 백엔드에 `GET /fix/chat/sessions/{id}/messages` 추가
5. B3: 프론트 startChat()에서 이전 메시지 로드

### Phase 3: 비회원→회원 연결
6. B5: 백엔드에 claim + my/sessions API 추가
7. B5: 프론트 로그인 후 claim 호출 + 대화 복원

---

## 테스트 시나리오

### T1: 기본 대화 저장
1. fix-request 페이지 열기
2. 메시지 3개 전송
3. DB 확인: fix_chat_sessions.current_turn = 3, fix_chat_messages 6개 (user 3 + assistant 3)

### T2: 새로고침 복원
1. T1 후 페이지 새로고침
2. 이전 대화 6개 메시지가 화면에 출력되는지 확인

### T3: 브라우저 닫기 복원
1. T1 후 브라우저 완전 종료 → 재실행
2. fix-request 접속 → 이전 대화 복원 확인

### T4: 비회원→회원 전환
1. 비회원으로 3턴 대화
2. 회원가입 → 로그인
3. fix-request 재접속 → 이전 대화 연결 + 잔여턴 7턴 표시

---

## 관련 기존 문서

- `docs/workorder-fix-chat-backend.md` — 원래 설계서 (백엔드)
- `docs/workorder-fix-chat-frontend.md` — 원래 설계서 (프론트)
- `docs/workorder-fix-provider-api.md` — 전체 매칭 플로우 확정

## 절대 규칙

- 🔒 기존 fix_chat.py의 admin API 3개 (stats, sessions, session detail)는 변경 금지
- 🔒 기존 채팅 UI (채팅 헤더, 버블, 타이핑 인디케이터, 입력바) DOM 구조 유지
- 🔒 3턴 제한 후 블러 결과카드 + CTA 로직 유지
- 🔒 from/type URL 파라미터 기반 인사 메시지 분기 유지
