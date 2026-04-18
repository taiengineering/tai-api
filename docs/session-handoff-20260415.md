# TAI Fix 설계 세션 핸드오프 — 2026-04-15

**이전 대화 전체 트랜스크립트:** `/mnt/transcripts/` 디렉토리 참조

---

## 오늘 세션에서 확정된 사항

### 1. TAI Fix 입력부 — 대화형 (Claude API)

**핵심 설계:**
```
겉모습: "TAI 매칭 전문가와 상담"
실제: "구조화된 정보 수집기"
목적: "연결하기 버튼을 누르게 만드는 것"
```

**의도에 따라 질문이 완전히 다름:**
- REPAIR(수선): 설비/증상/긴급도/위치
- APPOINTMENT(선임): 업종/인원/상주비상주/위치  
- DIAGNOSIS(진단): 시설유형/진단목적/위치
- CONSULTING(컨설팅): 관련법령/업종/규모

**절대 규칙:** 해결책 제시 ❌, 법률 자문 ❌, 가격 안내 ❌ → 연결만 유도

**턴/비용 제한 (확정, system_codes FIX_CHAT_CONFIG 등록 완료):**

| 사용자 유형 | 최대 턴 | 예상 비용 | DB code |
|---|---|---|---|
| 비회원 | 3턴 | ~30원 | GUEST_MAX_TURNS |
| 회원 (SaaS 미구독) | 10턴 | ~150원 | MEMBER_MAX_TURNS |
| 회원 (SaaS 구독) | 12턴 | ~200원 | SUBSCRIBER_MAX_TURNS |

**두 사이트 전략:**
- new.taieng.co.kr (비회원): 3턴 체험 → 블러 결과 → "대화 저장됨, 가입 후 이어서" CTA
- safe.taieng.co.kr (회원): 전제조건 3가지(로그인+본인인증+시설주소) → 전체 대화 → 연결 요청
- SaaS 미구독자: 플랫폼 이용료 부과

### 2. 백엔드 완료 상태

| 항목 | main | dev | 상태 |
|---|---|---|---|
| routers/fix_chat.py v1.0.1 | ✅ | ✅ | 오타 수정 완료 |
| main.py v5.24.0 (fix_chat 등록) | ✅ | ❌ (v5.23.0) | main 배포됨 |
| fix_chat_sessions 테이블 | ✅ 2건 테스트 | — | 정상 |
| fix_chat_messages 테이블 | ✅ 12건 테스트 | — | 정상 |
| system_codes FIX_CHAT_CONFIG | ✅ 5건 | — | 등록됨 |

API 엔드포인트:
```
POST /fix/chat/start     — 세션 생성 (공개)
POST /fix/chat/message   — 메시지 전송 → Claude API (공개)
POST /fix/chat/complete  — 완료 → matching_requests 저장 (회원 인증)
```

### 3. 어드민 상담리스트 페이지

- `admin/full-version/html/horizontal-menu-template/fix-chat-list.html` — main 커밋 완료
- `menu-nav.js` — 매칭관리 최상단에 "상담리스트" 추가 완료
- 호출 API (백엔드 미구현): GET /fix/chat/admin/stats, GET /fix/chat/admin/sessions, GET /fix/chat/admin/sessions/{id}

### 4. 대시보드 미점검 현황 위젯 (ADD-04)

- `tadmin/full-version/html/horizontal-menu-template/index.html` — main 커밋 완료
- 통계: 전체 점검항목, 담당자 미배정, 체크항목 미설정, 기한 초과
- 문제 항목 최대 5건 리스트

### 5. 법령진단 가격 최종 확정

| 섹터 | 가격 |
|---|---|
| 소형건물 (<5,000㎡) | 99,000원 |
| 대형건물 (≥5,000㎡) | 249,000원 |
| 제조·산업 | 79,000/149,000/249,000원 |
| 건설현장 | 199,000원 |

DB: price_diagnosis_report (BUILDING_V2, BUILDING_LARGE_V2, INDUSTRY_V2, CONSTRUCTION_V2)
DB: diagnosis_input_fields 111건

---

## 작업지시서 위치

| 문서 | 경로 | 상태 |
|---|---|---|
| Fix 시스템 프롬프트 v2 | tai-api/docs/tai-fix-chat-system-prompt.md | ✅ 확정 |
| Fix 대화형 백엔드 | tai-api/docs/workorder-fix-chat-backend.md | ✅ 완료 |
| Fix 대화형 프론트 | tai-api/docs/workorder-fix-chat-frontend.md | ⬜ PENDING |
| Fix 업체등록 백엔드 | tai-api/docs/workorder-fix-provider-api.md | ✅ 완료 |
| 법령진단 입력 백엔드 | tai-api/docs/workorder-diagnosis-input-backend.md | ✅ 완료 |
| 법령진단 입력 프론트 | taieng/nexas/docs/workorder-diagnosis-input-frontend.md | ✅ 완료 |

---

## PENDING 작업 (우선순위)

### 🔴 즉시
1. **Fix 프론트엔드 — new.taieng.co.kr 채팅 UI** (fix-request.html 교체)
   - 작업지시서: workorder-fix-chat-frontend.md 단계 1
   - 현재 fix-request.html은 정적 폼 → 채팅 UI로 전면 교체
   
2. **Fix 프론트엔드 — safe.taieng.co.kr 채팅 UI** (fix-chat.html 신규)
   - 작업지시서: workorder-fix-chat-frontend.md 단계 2
   - 전제조건 체크(로그인+본인인증+시설주소) + 이어받기

3. **어드민 상담리스트 백엔드 API** (3개 엔드포인트)
   - GET /fix/chat/admin/stats
   - GET /fix/chat/admin/sessions (필터/페이징)
   - GET /fix/chat/admin/sessions/{id} (상세+메시지)

### 🟡 다음
4. **작업일정 목록 필터 버그** — DB 268건 있는데 safe에서 "일치하는 일정 없음" 표시
5. **pricing.html 고도화** — 과금구조 기획서 반영
6. **SMS 실발송** — MessageMi + 고정IP

### 🟢 후순위
7. TAI Fix 매칭→견적→계약→보증금→연락처 파이프라인
8. 건설 모듈 (데이터 0건)
9. main.py 리팩토링 (라우터 그룹화)

---

## TAI Safe 사용자 여정 테스트 결과 (04-15)

**좋은 점:** 대시보드 핵심 정보, 점검앵커 4조건 체크, 법령진단 18건/3건 판정, 시설목록

**문제점:**
1. 작업일정 목록 비어있음 (필터 버그)
2. 점검앵커 8건 전부 잠김 (담당자 미지정)
3. 회원가입→결제→진단→점검세팅 온보딩 흐름 없음
4. 빈 화면에 "시작하기" 안내 필요

---

## 오늘 변경된 파일 목록

**tai-api (main):**
- routers/fix_chat.py — v1.0.1 (오타 수정)
- main.py — v5.24.0 (fix_chat 등록)

**tai-api (dev):**
- docs/tai-fix-chat-system-prompt.md — v2
- docs/workorder-fix-chat-backend.md
- docs/workorder-fix-chat-frontend.md
- docs/session-handoff-20260415.md (이 파일)

**tai-admin (main):**
- tadmin/.../index.html — ADD-04 미점검 위젯
- admin/.../fix-chat-list.html — 상담리스트 페이지
- admin/.../menu-nav.js — 상담리스트 메뉴 추가

**Supabase:**
- fix_chat_sessions 테이블 생성
- fix_chat_messages 테이블 생성
- system_codes FIX_CHAT_CONFIG 5건 등록
- system_codes CONTRACT_STATUS 8건 등록
- system_codes DEPOSIT_CONFIG 4건 등록
