# 세션 로그 2026-04-21 (기획창 세션 5-6)

## 완료된 작업

### 1. KG이니시스 심사 차단 해제 (2건)
- **문제 #1**: taieng.co.kr 요금제 페이지 접근 불가 → `_redirects` v10 수정 (`fd4127d`)
  - 원인: `/home/` nav의 상대경로 `front-pages/pricing.html` → `/home/front-pages/pricing.html` → 파일 없음 → SPA 폴백
  - 수정: `/home/front-pages/*` → `/front-pages/*` 매핑 15개 + assets splat
- **문제 #2**: 로그인 후 요금제에서 로그아웃 상태 → `pricing.html` 전면 교체 (`15f8f3b`)
  - 수정: `login.html?next=pricing.html` 리디렉트 + nav auth 상태 JS + 로그아웃 함수

### 2. safe.taieng.co.kr 로그인 페이지 리디자인 (3차 수정)
- **1차** (`92959b9`): site/ 경로에 TAI Safe 브랜딩 패널 추가 (잘못된 경로)
- **2차** (`70c9fa9`): tadmin/ 경로로 이동, TAI Safe 브랜딩 + 안전관리자 태그
- **3차** (`e126005`): 소셜로그인 삭제 + 시간대별 인사 + 오늘의 한 마디 12개 로테이션
  - 배포 경로: `tadmin/full-version/html/horizontal-menu-template/auth-login-cover.html`

### 3. 서비스 계층 분리 개발 규칙 확정
- `docs/DEV_RULES_SERVICE_LAYER.md` 작성 (`a707869`, `5030151`)
- 5단계 분리 순서: 헬퍼분리 → 스키마분리 → 서비스분리 → 라우터슬림화 → 테스트작성
- 메모리 #14에 영구 반영

### 4. 법령엔진 서비스 계층 분리 완료
- 작업지시서: `docs/WORK_ORDER_LEGAL_ENGINE_REFACTOR.md` (`64ceecf`)
- Cursor에서 5단계 실행 → `87cd1da` 커밋 (main 직접 push)
- **Before**: `routers/legal_engine.py` 77KB 1개 파일
- **After**: 11개 파일 (router 5KB + services 8개 + schemas + tests 3개)
- Railway 배포 확인: `/health` healthy, law_engine ok

### 5. 전문가 페이지 완료 (세션 5 전반부)
- for-expert.html (허브), for-agency.html, for-repair.html, for-consultant.html
- 4페이지 공통 보완: TAI 정체성/출시시기/인센티브
- 별점→내부매칭점수 전환
- header.js v2.6.0 nav 변경

## 커밋 목록

| 커밋 | 레포 | 브랜치 | 설명 |
|---|---|---|---|
| `fd4127d` | tai-admin | main | _redirects v10 |
| `15f8f3b` | tai-admin | main | pricing.html 로그인 복귀 |
| `92959b9` | tai-admin | main | site/ auth-login-cover (잘못된 경로) |
| `70c9fa9` | tai-admin | main | tadmin/ auth-login-cover 브랜딩 |
| `e126005` | tai-admin | main | 로그인 시간대별인사+오늘의한마디 |
| `a707869` | tai-api | dev | DEV_RULES 초번 |
| `5030151` | tai-api | dev | DEV_RULES 5단계 확정 |
| `64ceecf` | tai-api | dev | 법령엔진 분리 작업지시서 |
| `87cd1da` | tai-api | main | 법령엔진 서비스 계층 분리 |
