# 워크오더 — 모바일 Phase B (프론트엔드)

**작성일**: 2026-04-16  
**착수일**: 2026-04-17  
**대상 창**: 프론트엔드 세션 (tai-admin)  
**백엔드 연계**: `docs/workorder-2026-04-17-mobile-phase-b-backend.md`

---

## 1. 배경 및 의사결정

### 기획창 최종 결정 (2026-04-16)
- **옵션 B 확정**: 현재 `/app` PWA에 안전관리자/작업반장 기능을 통합 후 Google Play 출시
- **하나의 앱 + role 분기** 방식 (분리 앱 아님)
- **D-U-N-S 신청 완료** (2026-04-16, D&B 경유, 2~5영업일 대기)
- **iOS는 PWA 유지** (개인사업자 제약으로 Apple Organization 계정 불가 → 추후 법인 전환 시점에 App Store 추가)

### 현재 `/app` 진단 결과 (2026-04-16 기획창 실측)
- 경로: `tadmin/full-version/app/` (tai-admin repo)
- PWA 인프라 완비 (manifest.json, sw.js, firebase-messaging-sw.js, FCM 연동)
- 기존 페이지 21개 (작업자 중심)
- **문제**: index.html이 `_user.role` 분기 없음 (sector만 분기). 모든 role이 동일 UI 보고 있음
- **누락**: 안전관리자 UI(대시보드·PTW 승인), 작업반장 TBM 진행 모드

---

## 2. 역할 체계 (이번 Phase B에서 확정)

| role | 한글 | 핵심 업무 | 모바일 UI |
|---|---|---|---|
| `WORKER` | 작업자 | 점검 실행·신고·서명·QR출입 | 현재 `/app` UI 거의 그대로 |
| `FOREMAN` | 작업반장 | TBM 진행·PTW 작성·팀원 배치·작업중지 판단 | 확장 필요 |
| `SAFETY_MANAGER` | 안전관리자 | PTW 승인·대시보드·위험 모니터링·법령 대응 | **신규 구축 필요** |

> 백엔드는 `workers.role` 컬럼(enum)으로 관리. `/auth/verify-otp` 응답에 role 포함 필수 (백엔드 워크오더 참조).

---

## 3. 작업 범위

### 3-1. `index.html` role 분기 로직 추가

**파일**: `tadmin/full-version/app/index.html` (tai-admin repo)

현재 로그인 후 `initApp()` → 무조건 `home` 탭 표시.  
**변경**: `_user.role`에 따라 탭 구성과 홈 카드가 달라져야 함.

#### 구현 포인트

```javascript
// initApp 시작 시 role 기반 분기
function initApp(){
  showPage('pg-app');
  
  // role 기반 탭 구성 (기본값 WORKER)
  const role = _user.role || 'WORKER';
  buildTabsForRole(role);
  buildHomeForRole(role);
  
  loadActivities();
  loadTodayStats(role);
  registerFCM();
}

function buildTabsForRole(role) {
  // WORKER: 홈 / 점검 / 기록 / 내정보 (현행 유지)
  // FOREMAN: 홈 / TBM진행 / PTW작성 / 기록 / 내정보
  // SAFETY_MANAGER: 대시보드 / 승인 / 알림 / 통계 / 내정보
}
```

- 탭바 HTML은 role별로 다른 구조 렌더링
- 홈 카드(worker-card)도 role별로 내용 차등
- 기존 WORKER UI는 절대 손상시키지 않음 (fallback)

### 3-2. 신규 페이지 3개 (안전관리자용)

모두 `tadmin/full-version/app/` 디렉토리 아래 생성. 기존 index.html의 스타일 가이드 준수.

#### ① `admin-dashboard.html` — 안전관리자 대시보드

**핵심 데이터**:
- 미승인 PTW 건수 (카운트, 대형 숫자)
- 오늘 이상신고 건수
- 작업중지 발령 상태
- 날씨 위젯 (safety-dashboard.html FS-05 로직 재활용)
- 법령 D-3 알림 요약

**API 연계**: `GET /admin/dashboard-summary`

#### ② `admin-ptw-approval.html` — PTW 승인 목록

**UI 요구사항**:
- 카드 리스트 (PTW 1건 = 1카드)
- 각 카드에 작업자·작업내용·위험등급·요청시간 표시
- **스와이프 승인/반려** (우→승인, 좌→반려) + 버튼 병행
- 반려 시 사유 입력 bottom sheet

**API 연계**:
- `GET /work-requests?status=PENDING`
- `PATCH /work-requests/{id}/approve`
- `PATCH /work-requests/{id}/reject` (body: `{ reason }`)

#### ③ `admin-alerts.html` — 실시간 알림센터

- 미읽은 알림 상단 고정
- 카테고리 필터: PTW / 이상신고 / 긴급 / 법령
- 각 알림 클릭 시 해당 상세 페이지로 이동
- FCM 푸시와 연동 (Firebase Messaging 이미 구축됨)

### 3-3. 신규 페이지 2개 (작업반장용)

#### ④ `foreman-tbm-mode.html` — TBM 진행 모드

현재 `tbm.html`은 "개인 서명 페이지". 반장용 "진행 모드"는 별도.

**UI**:
- 상단: 오늘 작업 개요 (작업내용·장소·인원수)
- 안건 발표: 위험요소·보호구 체크리스트
- **출석 현황**: 작업자 리스트에서 참석/미참석 토글
- **서명 수집**: 작업자별 "서명 요청" 버튼 → 푸시로 작업자 앱 전송 → 수집 완료 카운트
- 하단: "TBM 완료 저장" (모든 참석자 서명 수집 후 활성화)

**API 연계**:
- `POST /tbm/sessions` (세션 시작)
- `POST /tbm/sessions/{id}/attendance` (출석 체크)
- `POST /tbm/sessions/{id}/request-signature` (서명 요청 푸시)
- `GET /tbm/sessions/{id}/status` (실시간 서명 현황)

#### ⑤ `foreman-ptw-create.html` — 반장용 PTW 작성

현재 `work_request.html`과의 차이점:
- 반장은 **팀원을 지정해서 PTW 발급** 가능
- 작업자 여러 명을 한 번에 할당
- 안전관리자에게 즉시 승인 요청 전송

### 3-4. 탭바 구성 매트릭스

| role | Tab 1 | Tab 2 | Tab 3 | Tab 4 | Tab 5 |
|---|---|---|---|---|---|
| WORKER | 🏠 홈 | ✅ 점검 | 📋 기록 | 👤 내정보 | — |
| FOREMAN | 🏠 홈 | 🎤 TBM진행 | 📋 PTW작성 | 📂 기록 | 👤 내정보 |
| SAFETY_MANAGER | 📊 대시보드 | ✓ 승인 | 🔔 알림 | 📈 통계 | 👤 내정보 |

---

## 4. 스타일 가이드 (기존 준수)

- 글꼴: `Noto Sans KR`
- 주요 색상: `--navy: #0d1b2a`, `--blue: #1565c0`, `--ok: #00875a`, `--bad: #de350b`, `--warn: #ff8b00`
- 모바일 우선, `viewport-fit=cover`, `user-scalable=no`
- 터치 영역 최소 44×44px (Apple HIG 기준)
- PWA `display: standalone` 유지 (TWA 필수)

---

## 5. 디자인 레퍼런스

- 지게차 UI (`tai_forklift_check_ui_html.html`) — 5초 체크 구조
- safety-dashboard.html (FS-05 날씨 위젯) — 대시보드 패턴
- construction-inspection-list.html — 65/35 레이아웃

---

## 6. 체크리스트 (개발 순서 권장)

### Day 1 (2026-04-17)
- [ ] 백엔드 `/auth/verify-otp` 응답에 role 필드 추가 확인 (백엔드 창과 연동)
- [ ] `index.html` 백업 생성 (`index-v1-worker-only.html.bak`)
- [ ] `index.html` role 분기 로직 추가 (`buildTabsForRole`, `buildHomeForRole`)
- [ ] WORKER role fallback 동작 검증 (기존 UI 무손상)

### Day 2
- [ ] `admin-dashboard.html` 신규 작성 (PTW 미승인·이상신고 카운트 + 날씨 위젯)
- [ ] `admin-ptw-approval.html` 신규 작성 (스와이프 승인/반려 UI)
- [ ] `admin-alerts.html` 신규 작성 (FCM 알림 연동)

### Day 3
- [ ] `foreman-tbm-mode.html` 신규 작성 (출석·서명 수집)
- [ ] `foreman-ptw-create.html` 신규 작성 (팀원 지정 PTW)
- [ ] 탭바 role별 차등 렌더링 검증

### Day 4
- [ ] E2E 테스트: 3개 role 각각 로그인 후 UI 확인
- [ ] PWA Lighthouse 90+ 재검증 (TWA 빌드 전제조건)
- [ ] Digital Asset Links 파일 배치 구조 준비 (`/.well-known/assetlinks.json`, SHA256은 D-U-N-S 수령 후)

---

## 7. 주의사항

1. **기존 WORKER UI는 절대 건드리지 말 것** — role 판별 실패 시 WORKER로 fallback되어야 함
2. **모든 커밋은 `dev` 브랜치에 push** (메모리 규칙: dev → PR → main)
3. `document.body` 직접 조작 금지, `_user.role` 기반 탭 분기는 명시적 함수로만
4. FCM 토큰 등록은 role 무관 공통 (기존 `registerFCM()` 재활용)
5. 작업자 앱 내 PTW 요청(`work_request.html`)은 유지 — 반장용 `foreman-ptw-create.html`과 별도
6. localStorage `tai_user`에 role 저장 시 암호화 불필요 (서버가 최종 권한 판별)

---

## 8. 백엔드 의존성

아래 항목은 백엔드 워크오더(docs/workorder-2026-04-17-mobile-phase-b-backend.md)에서 선행되어야 함:

- `workers.role` 컬럼 및 enum 제약
- `/auth/verify-otp` 응답 스키마에 `role` 추가
- `GET /admin/dashboard-summary`
- `GET /work-requests?status=PENDING`
- `PATCH /work-requests/{id}/approve`
- `PATCH /work-requests/{id}/reject`
- TBM 세션 API 5종

프론트 작업은 백엔드가 먼저 배포되어 있다는 가정 하에 진행. 동시 개발 시 API mock으로 선행 가능.

---

## 9. 완료 기준

- [ ] 3개 role 각각 고유 UI로 진입
- [ ] SAFETY_MANAGER가 모바일에서 PTW 승인/반려 가능
- [ ] FOREMAN이 모바일에서 TBM 진행·서명 수집 가능
- [ ] WORKER UI 무손상
- [ ] Lighthouse PWA 점수 90+ 유지
- [ ] FCM 푸시 3개 role 전부에서 동작

---

## 10. 후속 작업 (Phase B 완료 후)

1. 앱 아이콘 실파일 확인 (`tai-icon-192.png`, `tai-icon-512.png` 존재 여부)
2. Play Store용 피처 그래픽 1024×500 제작
3. 스크린샷 3개 role 각각 1장씩 촬영 (최소 2장, 권장 6장)
4. 법적 페이지 4종 배포 (taiengineering/taieng repo에 별도 워크오더)
5. D-U-N-S 수령 후 Google Play 조직 계정 생성 + Bubblewrap TWA 빌드
