# 세션 로그 — 2026-04-28 (기획창)

## 1. Supabase 서울 이전 마무리 (#58)

### 프론트엔드 Supabase URL+키 교체 (tai-admin, 3커밋)
| 파일 | 변경 | 커밋 |
|---|---|---|
| admin/config.js | URL + sb_publishable key | c2e09db |
| tadmin/config.js | URL + sb_publishable key | c2e09db |
| supabase-config.js | URL + JWT anon key | c2e09db |
| auto-qa-dashboard.html | 인라인 SB_URL+SB_KEY | c44a303 |
| diagram-gallery.html | 폴백 URL | b8f810c |

### Edge Function Secrets 6개 — 대표 수동 완료

### Storage 파일 51개 이전 (Chrome JS)
| 버킷 | 파일 수 | 결과 |
|---|---|---|
| diagrams | 28 | ✅ |
| site-assets | 17 | ✅ |
| app | 4 | ✅ |
| proposals | 2 | ✅ |
| **합계** | **51** | **51/51 성공** |

diagram_templates.public_url 25건 신 프로젝트 URL로 PATCH 갱신 완료.

### 기존 프로젝트 IPv4 비활성화 — 대표 수동 완료

### Claude Supabase MCP 프로젝트 ID 교체 — 대표 수동 완료

---

## 2. 작업자 웹앱 라우팅 시도 → 원복 (tai-admin #5)

### 시도한 작업
- auth-login-cover.html에 role 분기 추가 (014/022 → worker-home)
- auth-guard.js에 작업자 화이트리스트 추가
- worker-home.html, schedule-review.html, tbm-list.html, notification-list.html 복사/생성
- worker-home.html에 로그아웃 버튼 추가

### 발생한 문제
1. 하단 탭바 링크 페이지(schedule-review, tbm-list, notification-list)가 tadmin 경로에 없어 404 발생
2. auth-guard가 작업자를 worker- 패턴 외 페이지에서 되돌려보냄
3. 복사된 페이지들이 원본 site/ 경로의 기존 디자인/기능과 달라진 상태

### 원복 조치 (b27c59b)
- auth-login-cover.html → b6334c0 상태로 원복 (원본 APP_ONLY_ROLES, 원본 리다이렉트)
- auth-guard.js → b6334c0 상태로 원복 (토큰 유무만 확인)
- 추가된 파일(worker-home, schedule-review, tbm-list, notification-list)은 레포에 남아있으나 어디에서도 링크하지 않음

### 교훈
- tadmin(SaaS)과 site(앱)은 별도 도메인/경로이므로 단순 복사로는 동작하지 않음
- 작업자 웹앱 라우팅은 site/ 경로의 기존 구조를 충분히 파악한 후 별도 세션에서 설계부터 접근해야 함

---

## 3. 기타
- 작업자 테스트 계정 비밀번호 리셋: worker@tai.com / Tai1234!
- 구 프로젝트에 잘못 배포된 copy-storage Edge Function 삭제 필요

---

## 이슈 처리
| 이슈 | 레포 | 상태 |
|---|---|---|
| #58 Supabase 서울 이전 | tai-api | ✅ 완료 (삭제만 1주 후) |
| #5 작업자 라우팅 | tai-admin | ❌ closed → 원복됨, 재설계 필요 |
