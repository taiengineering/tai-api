# TAI Fix 대화형 입력부 — 프론트엔드 작업지시서

**작성일:** 2026-04-15
**방식:** 단계별 진행

---

## 배경

TAI Fix 입력부를 대화형 UI로 구현.
2개 사이트에 각각 다른 버전:
- new.taieng.co.kr — 비회원 체험 (3턴 → 블러 → 가입 유도)
- safe.taieng.co.kr — 회원 전용 (7~10턴 → 매칭 연결)

## 단계 1: new.taieng.co.kr 대화 UI (비회원용)

**프롬프트:**
```
nexas/fix-request.html을 전면 교체합니다.

현재: 정적 폼 (카드 선택 + textarea)
변경: 대화형 채팅 UI

화면 구성:

상단 헤더:
  TAI Fix 로고
  "산업안전 전문가 매칭"

채팅 영역:
  왼쪽 정렬: TAI 전문가 메시지 (프로필 아이콘 + 말풍선)
  오른쪽 정렬: 사용자 메시지 (말풍선)
  하단: 입력창 + 전송 버튼

동작:
1. 페이지 로드 시 POST /fix/chat/start { user_type: 'GUEST' } 호출
2. greeting_message를 첫 메시지로 표시
3. 사용자 입력 → POST /fix/chat/message { session_id, message }
4. 응답의 reply를 채팅에 추가
5. 입력 중 로딩 표시 ("TAI 전문가가 입력 중...")

3턴 후 (is_last_turn=true):
  채팅 영역 아래에 결과 요약 카드 표시
  일부 정보는 블러 처리:
    ✅ 의도: 수선 (공개)
    ✅ 증상 요약 (공개)
    🔒 관련 법령 (블러 — 흐릿하게 보이지만 읽을 수 없음)
    🔒 과태료 정보 (블러)
    🔒 매칭 가능 업체 (블러)
  CTA 카드:
    "대화 내용이 저장되어 있습니다."
    "회원가입 후 바로 전문 업체 매칭이 시작됩니다."
    [무료 회원가입 후 전체 결과 보기] 버튼

UI 스타일:
  기존 nexas 템플릿의 헤더/푸터 유지
  채팅 영역은 카카오톡/라인 스타일
  TAI 전문가 아이콘: 파란색 원형 아바타 "T"
  말풍선: 라운드 코너, 연한 배경색
  입력창: 하단 고정, textarea + 전송 버튼

세션 데이터를 sessionStorage에 저장:
  sessionStorage.setItem('fix_session_id', session_id)
  → 회원가입 후 이어받기용

main 브랜치 커밋.
이 단계에서는 fix-request.html만 교체.
```

**완료 조건:** 비회원 대화 UI + 3턴 제한 + 블러 결과 + CTA

---

## 단계 2: safe.taieng.co.kr 대화 UI (회원용)

**프롬프트:**
```
tadmin 리포에 fix-chat.html을 새로 생성합니다.
경로: tadmin/full-version/html/horizontal-menu-template/fix-chat.html

기존 tadmin 페이지와 동일한 레이아웃 (헤더/메뉴/푸터).

화면 구성:

전제조건 체크 (페이지 로드 시):
  1. 로그인 여부 → 미로그인 시 로그인 페이지로
  2. 본인인증 여부 → 미인증 시 본인인증 안내 모달
  3. 시설 등록 여부 → 미등록 시 시설 등록 안내

전제조건 충족 후:
  채팅 영역 (fix-request.html과 동일한 채팅 UI)
  단, user_type: localStorage의 contract_level에 따라:
    level > 0 → 'SUBSCRIBER' (10턴)
    level == 0 → 'MEMBER' (7턴)

이어받기 기능:
  페이지 로드 시 sessionStorage.getItem('fix_session_id') 확인
  있으면 → "이전 대화를 이어서 진행하시겠습니까?" 모달
  → 예 → 기존 세션의 메시지 로드하여 채팅에 표시
  → 아니요 → 새 세션 시작

대화 완료 시 (is_last_turn=true):
  블러 없이 전체 결과 표시
  [전문 업체 연결 요청하기] 버튼
  → POST /fix/chat/complete { session_id } 호출
  → 성공 시 "요청이 접수되었습니다" 완료 화면

SaaS 미구독자:
  완료 시 플랫폼 이용료 안내 모달
  "TAI Fix 연결 서비스 이용료: 별도 안내"
  → 결제 후 complete 진행 (결제 로직은 TODO)

main 브랜치 커밋.
이 단계에서는 fix-chat.html만 생성.
```

**완료 조건:** 회원 대화 UI + 전제조건 체크 + 이어받기 + 연결 요청

---

## 단계 3: 메뉴 등록

**프롬프트:**
```
menu-tadmin.js에 TAI Fix 대화 메뉴를 추가합니다.

모든 섹터에서 표시:
  메뉴 그룹: "연결 서비스"
  메뉴 항목: "전문가 매칭" → fix-chat.html

이 단계에서는 menu-tadmin.js만 수정.
```

**완료 조건:** 사이드바에 메뉴 표시

---

## 단계 4: 통합 테스트

**프롬프트:**
```
양쪽 사이트에서 테스트.

테스트 1: 비회원 (new.taieng.co.kr/fix-request.html)
  → 대화 시작 → 3턴 대화 → 블러 결과 → CTA 버튼 확인

테스트 2: 회원 (safe.taieng.co.kr/fix-chat.html)
  → 로그인 상태에서 진입 → 대화 → 연결 요청

테스트 3: 이어받기
  → new에서 3턴 대화 → 회원가입(가정) → safe에서 이어받기 모달

테스트 4: 의도별 대화
  수선: "분전반에서 냄새가 나요"
  선임: "안전관리자를 어떻게 구하죠"
  진단: "건물 안전진단을 받고 싶어요"
  컨설팅: "중대재해법 대응을 어떻게 해야 하나요"
```

**완료 조건:** 4가지 시나리오 정상 동작

---

## 참고: API 엔드포인트

```
POST /fix/chat/start
  요청: { user_type: 'GUEST' | 'MEMBER' | 'SUBSCRIBER' }
  응답: { session_id, max_turns, greeting_message }

POST /fix/chat/message
  요청: { session_id, message }
  응답: { reply, turn_number, remaining_turns, is_last_turn }

POST /fix/chat/complete (회원 전용)
  요청: { session_id }
  응답: { request_id, summary }
```

## 참고: 채팅 UI 디자인 가이드

```
전문가 아바타: 파란 원형 "T" 아이콘 (#378add)
전문가 말풍선: 연한 회색 배경, 왼쪽 정렬
사용자 말풍선: 파란 배경 흰 글씨, 오른쪽 정렬
타이핑 인디케이터: "TAI 전문가가 입력 중..." + 점 애니메이션
입력창: 하단 고정, 라운드 코너, placeholder "상황을 편하게 말씀해주세요"
전송: 파란 화살표 아이콘 버튼
```
