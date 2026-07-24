# TAI 마케팅 사이트 리빌드 · 작업 내역

- 대상 저장소: `taiengineering/tai-www` (Astro, Cloudflare Pages git 연결)
- 원본 정적 사이트: `taiengineering/taieng` 리포의 `nexas/` (Nexas 템플릿 기반 정적 HTML+jQuery+Bootstrap)
- 도메인: `taieng.co.kr`, `www.taieng.co.kr` (프로덕션), `old.taieng.co.kr` (구사이트 백업)
- 문서 갱신: 2026-07-24

---

## 1. 목적

1. 레거시 정적 사이트(Nexas)를 **Astro** 스택으로 재구축하되, **보여지는 페이지는 원본과 바이트 수준으로 동일**하게 유지.
2. 유지보수 편의를 위해 코드를 **3계층(데이터 / 도메인 / 프레젠테이션)** 으로 구조화.
3. 비개발자 "바이브코딩" 환경 → git 연동 필수(모든 변경은 GitHub `main` 커밋 → CF Pages 자동/수동 빌드).

핵심 원칙: 원본 CSS/JS 자산은 그대로 이관, 페이지 마크업·급소 로직(결제·본인확인 등)은 손대지 않고 **API 호출 경로만** 계층으로 정리.

---

## 2. 스택 · 인프라

- **Astro** static 빌드. `output:'static'`, `build.format:'preserve'`.
- **Cloudflare Pages** 프로젝트 `tai-www` (계정 `3dba958d71a23e70e944193efe6d5be0`).
  - 빌드 `npm run build`, 출력 `dist`, `uses_functions:true`.
  - `functions/_api/[[path]].js` — KG이니시스 V023 도메인 일치용 same-origin `/_api` 프록시.
- **백엔드 API**: `https://api.taieng.co.kr` + `/_api` 프록시.
- **공개 데이터(안전정보)**: Supabase REST(anon key), 프로젝트 `vwlahtguyggrhvslabax`.

배포 확인: `canonical_deployment == latest_deployment` 이고 `aliases`에 `taieng.co.kr` 포함이면 그 배포가 프로덕션.

---

## 3. 도메인 전환

- `taieng.co.kr` + `www` → `tai-www`(신규, functions 동작).
- `old.taieng.co.kr` → 구사이트(원본 nexas 정적).
- DNS 레코드는 대시보드에서 사용자가 직접(게이트웨이 권한 밖).

---

## 4. 3계층 리팩터링 (증분 1~6)

- **① 데이터 계층** `src/lib/` : `api.js`(api.taieng.co.kr+/_api), `sb.js`(Supabase REST + RPC), `session.js`(토큰/세션).
- **② 도메인 계층** `src/lib/modules/` : pricing, auth, identity, diagnosis, payment, `safety`(판례·사고사례·안전자료·법령안내), `mypage`(experts).
- **③ 프레젠테이션** `src/pages/*.astro` : 도메인 모듈만 호출, 마크업/CSS/급소 무변경.

증분: 1) 데이터/세션 2) 요금제 3) 인증 4) 법령진단 퍼널(이니시스) 5) 안전정보 8종 6) 마이페이지 전문가신청.
각 증분: 로컬 빌드(50p) → GitHub main byte-identical(blob sha) → CF 배포 → 라이브 확인.

---

## 5. 헤더 / 푸터

- 원본 `header.js`/`footer.js` 런타임 주입 방식 **현행 유지**(전 50페이지). `Header.astro`/`Footer.astro` 미사용 잔재는 삭제.
- Vue 아일랜드 컴포넌트화는 바이트 동일성·영향범위 이유로 보류. 세션 로직은 `session.js`가 이미 nav-auth와 동일 규칙 미러링.

---

## 6. 정리 · 점검 · 자산 복원

### 잔재 파일 삭제
- `src/components/Header.astro`, `Footer.astro` 제거(미사용).

### 전체 링크·경로 점검
- 51개 페이지, 내부 링크 1,720개 검사 → 아래 이슈 발견·조치.

### 이관 누락 자산 복원 (원본 `taieng/nexas/assets` 에서 byte-identical 복원)
- CSS: `diagnosis-modern.css`(free/paid-diagnosis 스타일 핵심), `fix-request-override.css`.
- 이미지: `matching-flow.svg`(fix-request), `tai-logo.png`(site-map).
- 배포 dist 포함 확인 완료.

---

## 7. 안전보건자료(kosha_safety_materials) 데이터 이슈 · 검색엔진

### 7-1. 목록이 안 뜨던 원인 (해결)
- 증상: `safety-news`(안전보건자료) 목록이 "표시할 자료가 없습니다"(상단 통계 숫자는 정상).
- 원인: **원본·리빌드 공통**으로 목록 쿼리가 `select=id,title,url,category,sector&order=collected_at.desc` 였는데,
  실제 테이블에 **`sector` 컬럼이 없음** → PostgREST 400. (별도 검색엔진을 쓴 게 아니라, 원본도 동일한 직접 테이블 조회였음.)
- **실제 컬럼**: `id, title, product_type, industry, accident_type, url, raw_json, collected_at, category, industry_category`
  - `category` = 자료유형(EDUCATION/CASE_STUDY/GUIDE/…)
  - `industry_category` = 업종(CONSTRUCTION/MANUFACTURING/SERVICE/COMMON) ← 프론트의 "sector"
  - `collected_at` = 수집시각(최신순 정렬 기준, 존재함)
- 수정(`safety.js materials.list`): 직접 조회를 `select=id,title,url,category,sector:industry_category,collected_at`(별칭) + `order=collected_at.desc` + 업종 필터 `industry_category=eq.` 로 교정.
  - 부수 효과: 이전엔 업종 배지가 전부 "공통"으로 잘못 표시되고 업종 필터가 400이던 것도 함께 정상화.

### 7-2. 검색엔진 (Postgres 네이티브 · pg_trgm) — 방식 A 채택
- 프론트: `materials.list` 가 **`search_safety_materials()` RPC 우선 호출 → 없으면 7-1 직접 조회로 폴백**. (`sb.js` 에 `sbRpc()` 추가)
- DB: `docs/tai-rebuild/search-safety-materials.sql` — **Supabase 대시보드 SQL Editor 에서 1회 실행** 필요(게이트웨이엔 해당 DB DDL 권한 없음).
  - `pg_trgm` 확장 + 제목 GIN 트라이그램 인덱스(+ 필터/정렬 인덱스)
  - `search_safety_materials(q, cat, sec, page_no, page_size)` : 한글 부분검색 + 유사도 랭킹 + 필터 + 페이지네이션 + total_count
  - anon 실행권한 + `notify pgrst,'reload schema'`
- 적용 전에도 폴백(제목 부분일치)으로 정상 동작. 적용 시 **관련도순 검색**으로 향상.

---

## 8. 핵심 파일 맵 (tai-www)

```
src/lib/
  api.js       ① api.taieng.co.kr + /_api 통합 클라이언트
  sb.js        ① Supabase REST + RPC(sbRpc) 클라이언트
  session.js   ① 토큰/세션 localStorage 캡슐화
  modules/
    auth.js identity.js pricing.js diagnosis.js payment.js
    safety.js   ② 판례·사고사례·안전보건자료(검색 RPC)·법령안내
    mypage.js   ② experts(전문가 신청)
  render/pricingCards.js
functions/_api/[[path]].js   결제·로그인 프록시(이니시스 도메인 일치)
public/assets/               원본 CSS/JS/img (바이트 동일 이관)
src/pages/*.astro            프레젠테이션(도메인 모듈만 호출)
```

원본 정적 사이트 전체: `taiengineering/taieng` 리포 `nexas/`.

---

## 9. 남은 작업 / QA

### 이어서 할 작업
1. **검색엔진 활성화**: `docs/tai-rebuild/search-safety-materials.sql` 을 Supabase SQL Editor 에서 실행(사용자/백엔드). 실행 전에도 사이트는 폴백으로 정상.
2. **site-map 죽은 링크 정리**: `site-map`이 리빌드에 없는 5개 페이지 참조 — `provider-register.html`, `service/appointment.html`, `service/consulting.html`, `service/education.html`, `service/repair.html`. (링크 제거 or 페이지 이관 결정 필요.)

### 오픈 전 실거래 QA (자동 검증 불가 — 사용자 직접)
- KG이니시스 **결제**, 휴대폰 **본인확인**, 전문가 신청 **서류 업로드**(전문가 서비스 준비중이라 급하지 않음).

### 참고 (운영 팁)
- github 쓰기: `github_put_file`(플레인텍스트)이 간헐 타임아웃/오류응답 → 실패해도 커밋된 경우 많음. 바이너리/대용량은 `github_api` Contents PUT(base64, 개행 제거). **어느 방식이든 blob sha 대조로 byte-identical 검증** 권장.
- 게이트웨이 응답의 `path`/`commit` 이 엉뚱하게 나오는 표시 오류가 있으므로, 반영 여부는 항상 git tree blob sha 로 재확인.
