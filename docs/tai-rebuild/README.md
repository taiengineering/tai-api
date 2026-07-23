# TAI 마케팅 사이트 리빌드 · 작업 내역

- 대상 저장소: `taiengineering/tai-www` (Astro, Cloudflare Pages git 연결)
- 원본 정적 사이트: `taiengineering/taieng` 리포의 `nexas/` (Nexas 템플릿 기반 정적 HTML+jQuery+Bootstrap)
- 도메인: `taieng.co.kr`, `www.taieng.co.kr` (프로덕션), `old.taieng.co.kr` (구사이트 백업)
- 문서 갱신: 2026-07-23

---

## 1. 목적

1. 레거시 정적 사이트(Nexas)를 **Astro** 스택으로 재구축하되, **보여지는 페이지는 원본과 바이트 수준으로 동일**하게 유지.
2. 유지보수 편의를 위해 코드를 **3계층(데이터 / 도메인 / 프레젠테이션)** 으로 구조화.
3. 비개발자 "바이브코딩" 환경 → git 연동 필수(모든 변경은 GitHub `main` 커밋 → CF Pages 자동/수동 빌드).

핵심 원칙: 원본 CSS/JS 자산은 그대로 이관, 페이지 마크업·급소 로직(결제·본인확인 등)은 손대지 않고 **API 호출 경로만** 계층으로 정리.

---

## 2. 스택 · 인프라

- **Astro** static 빌드. `output:'static'`, `build.format:'preserve'` → 원본 파일 구조 유지(`/about.html` + `/mypage/index.html` 혼재).
- **Cloudflare Pages** 프로젝트 `tai-www` (계정 `3dba958d71a23e70e944193efe6d5be0`).
  - 빌드: `npm run build`, 출력 `dist`, `uses_functions:true`.
  - `functions/_api/[[path]].js` — KG이니시스 V023 도메인 일치용 same-origin `/_api` 프록시(결제·로그인 콜백).
  - `functions/_middleware.js` — `.fade` CSS 관련 보정.
- **백엔드 API**: `https://api.taieng.co.kr` (직접, CORS) + `/_api` 프록시(인증·결제 콜백).
- **공개 데이터(안전정보)**: Supabase REST(anon key), 프로젝트 `vwlahtguyggrhvslabax`.

배포 트리거: `POST /accounts/{acct}/pages/projects/tai-www/deployments` (API 커밋 즉시 반영용). CF는 빠른 연속 커밋을 합쳐 빌드하므로 최신 반영 확인 시 명시적 배포 트리거 사용.

---

## 3. 도메인 전환

- `taieng.co.kr` + `www` → `tai-www`(신규, functions 동작) 로 apex/www 바인딩.
- `old.taieng.co.kr` → 구사이트(`taieng-new` Pages 프로젝트, 원본 nexas 정적).
- DNS 레코드 편집은 guri 토큰 권한 밖(403) → 대시보드에서 사용자가 직접 수행.
- 검증: `taieng.co.kr/_api/public/pricing/all` 실 JSON 응답 확인.

---

## 4. 3계층 리팩터링 (증분 1~6)

계층 구조:
- **① 데이터 계층** `src/lib/` — 저수준 API/DB 접근 단일화.
- **② 도메인 계층** `src/lib/modules/` — 콘텐츠/기능 단위 래핑.
- **③ 프레젠테이션 계층** `src/pages/*.astro` — 도메인 모듈만 호출, 마크업/CSS/급소 무변경.

각 증분 공통 절차: 로컬 클린 빌드(50페이지) 통과 → GitHub `main`에 **byte-identical**(로컬 `git hash-object` == GitHub blob sha) 반영 → CF 배포 → guri-cf로 프로덕션 반영 확인.

### 증분1 — 데이터/세션 계층
- `src/lib/api.js` — 통합 API 클라이언트(`auth·pricing·posts·diagnosis·lookup·identity·payments`, 이후 `experts` 추가). `request()`가 `err.data`에 원응답 부착.
- `src/lib/session.js` — 토큰/세션 localStorage 캡슐화. 키: `tai_session`, `access_token` 등(header.js·nav-auth.js와 동일 규칙 미러링).

### 증분2 — 요금제 도메인 파일럿
- `src/lib/modules/pricing.js` + `src/lib/render/pricingCards.js`.
- 요금제/서비스 페이지 결제·요금 표시를 도메인 경유로.

### 증분3 — 인증 계층
- `src/lib/modules/auth.js`, `src/lib/modules/identity.js`.
- `identity-verify.astro` 등 KG이니시스 본인확인 요청/결과 흐름을 모듈로(팝업·postMessage 로직 무변경).

### 증분4 — 법령진단 퍼널 (보수적)
- `src/lib/modules/diagnosis.js`, `payment.js`.
- 페이지: `free-diagnosis`, `free-diagnosis-result`, `paid-diagnosis`, `paid-diagnosis-detail`, `paid-diagnosis-result`.
- **급소 무변경**: `INIStdPay.pay()`, 히든 결제폼, returnUrl/closeUrl(`/_api`), 청약철회 동의(전자상거래법 §17②), 본인확인 팝업. API 호출만 모듈 경유.
- 번들 `<script>` + `import`, 인라인 onclick 유지 위해 `Object.assign(window,{...})`.

### 증분5 — 안전정보 데이터 계층
- **①** `src/lib/sb.js` — Supabase REST base URL/anon key/헤더 단일화, `content-range` 총계 파싱, 단건 조회.
- **②** `src/lib/modules/safety.js` — `precedents`(판례), `accidentsDomestic`/`accidentsConstruction`(사고사례), `materials`(안전보건자료), `lawRevisions`(개정법령) + 공용 헬퍼(`esc`/`escAttr`/라벨맵).
- **③** 8개 페이지 리팩터링(목록/상세): 판례검색·판례상세, 사고사례·상세, 안전보건자료·상세, 개정법령·상세.
  - 그동안 8개 페이지가 각자 하드코딩하던 Supabase base/anon key를 데이터 계층 한 곳으로 통합.
  - 렌더링·필터·페이지네이션·onclick·마크업 무변경. 안전자료 상세의 "빈 결과→safety-post-detail 리다이렉트, 오류→throw" 분기도 보존.

### 증분6 — 마이페이지
- 조사 결과 마이페이지의 실제 백엔드 호출은 **전문가 신청(expert-application) 한 곳뿐**. 나머지는 localStorage mock(`tai-mypage-state.js`, "추후 GET /me로 교체" 주석). `mypage/index`의 `/experts/status`는 주석 처리된 비활성 코드.
- **①** `api.experts`(upload-url·attach·apply·status) auth POST 추가.
- **②** `src/lib/modules/mypage.js` — experts 래퍼(오류 `detail || message` 정규화로 기존 동작 보존).
- **③** `expert-application` 변환 — 3개 API 호출만 모듈 경유. **서명 URL PUT 업로드·사업자 매트릭스·사업자번호 검증·서류 설정·submit 순서 무변경**. 드래그&드롭 포함 인라인 핸들러 14개 `window` 노출.

---

## 5. 헤더 / 푸터 (현행 유지 결정)

- 현재 헤더/푸터는 **원본 `header.js`/`footer.js`가 런타임에 `#tai-header`/`#tai-footer`로 주입**(전 50페이지). `nav-auth.js`가 로그인 상태 스왑.
- `src/components/Header.astro`/`Footer.astro`는 초기 clean-rebuild 잔재로 **어디에서도 import 안 됨** → 삭제(빌드/화면 영향 0).
- "Vue 아일랜드 컴포넌트화"는 전 페이지 최대 영향·바이트 동일성 리스크로 **보류**. `session.js`가 이미 nav-auth와 동일 키·규칙을 미러링해 세션 로직은 계층으로서 정리된 상태.

---

## 6. 정리 · 점검

### 잔재 파일 삭제
- `src/components/Header.astro` (커밋 29e4ef6d), `src/components/Footer.astro` (커밋 6cfb226a) 제거.

### 전체 링크·경로 점검
- 51개 페이지, 내부 링크 1,720개 검사 → 대부분 정상, 아래 이슈 발견.

### 🔴 페이지 전용 CSS 이관 누락 → **복원 완료**
원본 `nexas/assets/css`에 있으나 tai-www로 이관 누락됐던 CSS를 **원본에서 byte-identical 복원**:
- `diagnosis-modern.css` (29,064B, blob `22b91563…`) — free/paid-diagnosis 스타일 핵심. free-diagnosis는 인라인 스타일 0개라 이 파일에 전적 의존이었음. (커밋 4f069b2)
- `fix-request-override.css` (419B) — fix-request. (커밋 f631da3e)
- 배포 `29d92c00`(커밋 4f069b2) dist에 두 CSS 포함 확인, 프로덕션 반영 완료.

---

## 7. 핵심 파일 맵 (tai-www)

```
src/lib/
  api.js              ① 통합 API 클라이언트(api.taieng.co.kr + /_api)
  sb.js               ① Supabase REST 클라이언트(안전정보)
  session.js          ① 토큰/세션 localStorage 캡슐화
  modules/
    auth.js  identity.js  pricing.js  diagnosis.js  payment.js
    safety.js           ② 판례·사고사례·안전보건자료·개정법령
    mypage.js           ② experts(전문가 신청)
  render/pricingCards.js
functions/
  _api/[[path]].js      결제·로그인 프록시(이니시스 도메인 일치)
  _middleware.js
public/assets/          원본 CSS/JS/img (바이트 동일 이관)
src/pages/*.astro       프레젠테이션(도메인 모듈만 호출)
```

원본 정적 사이트 전체: `taiengineering/taieng` 리포 `nexas/` (필요 시 누락 자산은 여기서 복원).

---

## 8. 남은 작업 / QA

### 이어서 할 작업
1. **누락 이미지 복원**(원본 `nexas/assets/img`에 존재, 이관 누락):
   - `matching-flow.svg` (10,644B, blob `3c98c41d…`) → `public/assets/img/matching-flow.svg` (fix-request 다이어그램)
   - `tai-logo.png` (72,355B, blob `eff1fe45…`) → `public/assets/img/tai-logo.png` (site-map 로고)
   - PNG는 바이너리 → base64로 Contents API PUT 방식 복원 후 blob sha 대조.
2. **site-map 죽은 링크 정리**: `site-map.astro`가 리빌드에 없는 5개 페이지 참조 — `provider-register.html`, `service/appointment.html`, `service/consulting.html`, `service/education.html`, `service/repair.html`. (원본에는 존재했으나 리빌드에서 의도적 미이관으로 추정 → 링크 제거 또는 페이지 이관 결정 필요.)

### 오픈 전 실거래 QA (자동 검증 불가 — 사용자 직접)
- KG이니시스 **결제**(유료 진단 결제창 → 승인 → 결과)
- 휴대폰 **본인확인** 팝업(무료 진단 시작 / identity-verify)
- 전문가 신청 **서류 업로드**(서명 URL PUT) — 단, 전문가 서비스 준비중이라 급하지 않음
- free-diagnosis / fix-request **스타일 육안 확인**(CSS 복원 반영 후)

### 참고
- github 쓰기: `github_put_file`(플레인텍스트)이 간헐 타임아웃 → 실패해도 커밋된 경우 많음. 바이너리/대용량은 `github_api` Contents API PUT(base64, 개행 제거) 사용. 어느 방식이든 **blob sha 대조로 byte-identical 검증** 권장.
- 배포 확인: `canonical_deployment == latest_deployment` 이고 `aliases`에 `taieng.co.kr` 포함이면 해당 배포가 프로덕션.
