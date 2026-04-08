# 세션 작업내역 — 2026-04-08

## 1. worker-list.html 버그 수정 (tadmin)

**파일:** `tadmin/full-version/html/horizontal-menu-template/worker-list.html`

**발견된 버그:**
- `confirmModal` 함수 미정의 → 비활성화/일괄초대 버튼 클릭 시 JS 에러
- `if(!data||!data.data) return;` → API undefined 반환 시 스피너 무한 유지
- `showToast` 안전성 — 일부 경로에서 함수 없을 때 에러

**수정:**
- `confirmModal` 함수 직접 구현 (confirm-modal 모달 재사용)
- 스피너 유지 → 빈 상태 메시지 표시로 변경
- 전체 `showToast` 호출에 `typeof` 체크 추가

---

## 2. tai-safe.html 가격 표시 수정 (taieng.co.kr)

**파일:** `site/full-version/html/tai-safe.html`

**수정 내용:**
- 베이직 가격: `79,000원` → `₩79,000`
- 프리미엄 가격: `149,000월` → `₩149,000`
- 요금 안내 문구: `모든 요금제는 부가세 별도입니다.`로 통일

---

## 3. 레포 경로 정리 확인

| 도메인 | 레포 경로 | Cloudflare publish dir |
|--------|-----------|------------------------|
| taieng.co.kr | tai-admin / site/full-version | site/full-version |
| safe.taieng.co.kr | tai-admin / tadmin/full-version | tadmin/full-version |

- 이전 세션까지 `site/full-version/html/horizontal-menu-template/` 에 잘못 작업한 파일 존재 → 무효 (admin.taieng.co.kr용)
- tadmin 작업은 반드시 `tadmin/full-version/html/horizontal-menu-template/` 경로 사용

---

## 4. Railway API 재시작

- 세션 중 502 Bad Gateway 발생
- Railway 대시보드에서 tai-api 서비스 재시작 완료

---

## 5. Cloudflare 배포 이슈 (반복 패턴)

- taieng.co.kr / safe.taieng.co.kr 각각 **별도 Cloudflare Pages 프로젝트**
- GitHub push 후 자동 배포가 지연되는 경우 수동 재배포 필요
- 배포 후 CDN 캐시 잔존 시 → `Caching > Purge Everything` 필요
- tai-safe.html의 경우 캐시 삭제 후에도 구버전 서빙 → 파일 강제 재push로 해결

---

## PENDING

- Railway API 재시작 후 정상 복구 여부 최종 확인
- tai-safe.html 가격 표시 Cloudflare 반영 확인
- safe.taieng.co.kr 작업자관리 실제 로그인 후 동작 확인
