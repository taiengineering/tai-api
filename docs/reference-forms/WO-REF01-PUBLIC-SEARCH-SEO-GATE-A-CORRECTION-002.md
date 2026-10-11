---
wo: WO-REF01-PUBLIC-SEARCH-SEO-GATE-A-CORRECTION-002
date: 2026-10-11
status: CORRECTION_COMPLETE
section: OBJ-REF-04 / OBJ-REF-09
publication: NOT_FOR_PUBLICATION
dependency: REF-05 + REF-08 (BLOCKED)
parent: WO-REF01-PUBLIC-SEARCH-SEO-INTEGRATION-001-GATE-A.md
---

# Gate A 교정 — 참고서식 공개 검색·SEO 통합

WO-REF01-PUBLIC-SEARCH-SEO-GATE-A-CORRECTION-002.

Gate A 문서의 실제 코드 불일치 8항 교정 + 구현 전 설계 계약 확정.

---

## 작업 1 — Repo 앵커 교정

### 실제 remote main SHA

| Repo | Remote main HEAD | 로컬 working 브랜치 HEAD |
|------|---------|---------|
| tai-api | `3a80af08f...` (fix(ext165) PATCH-A/B/C) | `59d88096e...` (docs/tai-reference-forms-charter-obj-20261008) |
| tai-www | `3fd8f6b1...` | `f3b2514f...` (local, 1 커밋 뒤처짐) |

**교정 내용:**
- Gate A 문서에서 tai-api "HEAD `589f8740`"는 로컬 비동기 main이며 remote main이 아님
- Gate A 문서에서 tai-www "HEAD `dc842ed3`"는 working 브랜치 HEAD이며 remote main이 아님
- Gate B 구현 착수 시 두 repo 모두 remote main 최신 기준으로 브랜치를 재고정해야 함
- WO 브랜치(`docs/tai-reference-forms-charter-obj-20261008`)는 tai-api remote main보다 앞서 있음 — docs 전용, code merge 대상 아님

---

## 작업 2 — Cloudflare SSR 라우팅 (CRITICAL)

### 확인된 사실

`workers/composite-entry.js` 구조:
- 특정 경로 명시적 매칭 → `astroPremiumWorker.fetch()` (Astro SSR)
- 나머지 모든 경로 → `existingLiveWorker.fetch()` (pages-live-worker.js, 정적/동적)

현행 Astro SSR 경로 등록 패턴:
```javascript
if (p === '/safety-guide' || p === '/sitemap_guides.xml') {
  return astroPremiumWorker.fetch(request, env, ctx);
}
if (/^\/safety-guide\/[^/]+$/.test(p)) {
  return astroPremiumWorker.fetch(request, env, ctx);
}
// ... safety-search, accident/csi, safety/equipment, safety/task, safety/law, safety/accident
```

`sitemap_guides.xml.js`의 `prerender = false` → 동적 SSR 엔드포인트이므로 composite-entry.js에 명시적 등록 필요.

### 결론 및 필요 변경

참고서식 상세페이지와 사이트맵이 `prerender=false` Astro SSR로 구현된다면:

| 대상 URL | composite-entry.js 추가 필요 |
|---------|--------------------------|
| `/reference-form/{id}` (정확 매칭) | `astroPremiumWorker.fetch()` 라우팅 추가 |
| `/reference-form/{id}/` (후행 슬래시) | `rewritePath` 후 `astroPremiumWorker.fetch()` |
| `/sitemap_reference_forms.xml` | `astroPremiumWorker.fetch()` 라우팅 추가 |

**Gate A 오류:** "신규 Astro 파일 생성만으로 라우팅 가능"하다고 묵시적으로 기술한 부분은 틀림. composite-entry.js 명시적 등록이 필수.

---

## 작업 3 — canonical URL 확정

### OBJ-REF-04 원기획 요구사항

- slug 충돌 검증 필요 (OBJ-REF-04 EXIT 조건: "slug collision tests")
- 파일 형식별 SEO 중복 페이지 생성 금지

### 방식 비교

| 방식 | 예시 | 장점 | 단점 |
|------|------|------|------|
| UUID 기반 | `/reference-form/a1b2c3d4-...` | 충돌 없음, CMS 직결 | 불가독성, SEO 키워드 부재 |
| slug 기반 | `/reference-form/kosha-c002-safety-check` | 가독성, SEO 키워드 | 슬러그 유일성 관리 필요, 변경 시 301 필요 |

### 결정 제안 (GPT Owner 승인 필요)

**권장: slug 기반** `/reference-form/{canonical_slug}`

근거:
- SEO 검색의도 일치 (서식 이름 포함)
- OBJ-REF-04에서 slug collision tests 명시
- 기존 `/safety-guide/[id]`(UUID) vs `/knowledge/[slug]`(slug) — 콘텐츠 유형에 따라 혼용 중

**slug 관리 계약:**
- `reference_form_content.canonical_slug` 필드 (unique constraint)
- 슬러그 변경 시 구 URL → 301 redirect 필수 (이전 Google 색인 보호)
- REF-05 CMS DDL에 `canonical_slug TEXT UNIQUE NOT NULL` 포함 필요

**4-way 일치 필수:**

```
SearchDocument.public_url    = /reference-form/{canonical_slug}
상세페이지 <link rel="canonical"> = https://taieng.co.kr/reference-form/{canonical_slug}
sitemap_reference_forms.xml <loc> = https://taieng.co.kr/reference-form/{canonical_slug}
내부 링크(검색결과 카드 href)    = /reference-form/{canonical_slug}
```

---

## 작업 4 — OpenSearch 갱신 이벤트 설계

Gate A 누락: "누가 outbox 이벤트를 등록하는가"가 미정의였음.

### 상태 전이별 이벤트 생산자

| 상태 전이 | 트리거 | outbox 등록 책임 | reason |
|---------|------|------|------|
| 최초 공개 승인 | `reference_forms.status` → `PUBLISHED` | tai-api CMS 서비스 | `"REFERENCE_FORM_PUBLISHED"` |
| 콘텐츠 수정 승인 | `reference_form_content` 변경 + 승인 | tai-api CMS 서비스 | `"REFERENCE_FORM_CONTENT_UPDATED"` |
| 파일 버전 변경 | `reference_form_files` 신규/수정 승인 | tai-api CMS 서비스 | `"REFERENCE_FORM_FILE_UPDATED"` |
| SEO 정보 수정 | title/description/slug 변경 승인 | tai-api CMS 서비스 | `"REFERENCE_FORM_SEO_UPDATED"` |
| 공개 취소 | `reference_forms.status` → `HOLD` | tai-api CMS 서비스 | `"REFERENCE_FORM_UNPUBLISHED"` |
| 게시 삭제 | `reference_forms.status` → `REMOVED` | tai-api CMS 서비스 | `"REFERENCE_FORM_DELETED"` |

### 신뢰성 계약

```
enqueue_search_index_sync(
  domain_name = "REFERENCE_FORM",
  object_type = "REFERENCE_FORM",
  canonical_id = {slug or uuid},
  event_key    = "REFERENCE_FORM:{canonical_id}:{reason}",
  reason       = {reason 위 표}
)
```

- CMS 상태 변경과 `enqueue_search_index_sync()` 호출은 **동일 트랜잭션** 또는 **동일 API 요청 내** 순차 실행
- enqueue 실패 시 CMS 상태 변경 롤백 또는 dead-letter 처리
- `event_key` UNIQUE constraint가 중복 등록 방지 (ON CONFLICT IGNORE)

---

## 작업 5 — Fence 및 테스트 매트릭스 교정

### 실제 fence 동작 (코드 기반)

`search_index_fence` 체크 지점:
1. Python `process_queue()` — fence 활성이면 claim 건너뜀 (`{"claimed": 0, "fence_active": True}`)
2. SQL `complete_search_index_event` — fence 활성이면 `RETURN FALSE` (쓰기 거부)
3. **`enqueue_search_index_sync`는 fence를 체크하지 않음** — enqueue 자체는 항상 성공

### OS-07 교정

**이전 (잘못된 예상 결과):**
> `enqueue_search_index_sync()` 호출 → PENDING 레코드 생성 안 됨

**교정된 예상 결과:**
> `enqueue_search_index_sync()` 호출 → PENDING 레코드 **생성됨**
> `process_queue()` → fence 활성 → 처리 건너뜀 (`fence_active: True`)
> OpenSearch 쓰기 → 차단됨 (fence 해제 후 다음 실행에서 처리)

### 교정된 OpenSearch 테스트 매트릭스

| ID | 시나리오 | 예상 결과 (교정) |
|----|---------|---------|
| OS-01 | 서식 공개 승인 → enqueue | outbox PENDING 생성 |
| OS-02 | incremental processor 실행 → object_reindex_payload | SearchDocument 색인 성공 |
| OS-03 | 동일 canonical_id 재색인 (내용 변경 없음) | content_hash 일치 → NOOP |
| OS-04 | 동일 canonical_id 재색인 (내용 변경) | 색인 갱신 성공 |
| OS-05 | 서식 공개 취소 (status=REMOVED) → enqueue | outbox PENDING 생성; 처리 후 OpenSearch 문서 삭제 |
| OS-06 | 서식 공개 취소 후 `/public/safety-search` 조회 | REFERENCE_FORM 결과 없음 (visibility_scopes에 PUBLIC 없음) |
| OS-07 | `search_index_fence.rebuild_active=true` + enqueue | PENDING **생성됨**; `process_queue()` fence 감지 → 처리 건너뜀; OpenSearch 쓰기 차단됨 |
| OS-08 | 미승인 서식 → `iter_documents()` | 해당 row yield 안 됨 |
| OS-09 | `?q=서식명&type=reference-form` | REFERENCE_FORM 결과 반환 |
| OS-10 | `?q=서식명` (type=all) | REFERENCE_FORM 포함 |
| OS-11 | 비공개 서식 공개 검색 | 결과 없음 (PUBLIC scope 없음) |
| OS-12 | 공개 취소 후 상세페이지 접근 | 404 또는 noindex 응답 |
| OS-13 | 공개 취소 후 사이트맵 확인 | URL 포함 안 됨 |
| OS-14 | 공개 취소 후 다운로드 시도 | 접근 거부 |
| OS-15 | stale 캐시 무효화 (CF Cache) | 공개 취소 후 TTL 내 stale 반환 가능 → CF 캐시 무효화 정책 필요 |

---

## 작업 6 — 검색결과 출력

### safety-search.astro 범용 렌더러 확인

`src/pages/safety-search.astro` 동작:
- `GROUP_DEFS`를 `Map`으로 변환: `new Map(GROUP_DEFS.filter(d => d.objectType).map(d => [d.objectType, d.label]))`
- 결과 카드는 `object_type` → label 매핑으로 섹션 제목 결정
- 결과 항목은 `public_url`, `title`, `summary` 범용 필드 사용

**결론:** `GROUP_DEFS`에 `REFERENCE_FORM` 추가 + `TYPE_ALLOWLIST`에 `'reference-form'` 추가만으로 카드 렌더링 가능성 높음.

### 검증 필요 항목 (E2E)

| 항목 | 검증 방법 |
|------|---------|
| '참고서식' 섹션 레이블 표시 | `type=all` 검색 결과 화면 |
| 제목·요약 카드 출력 | REFERENCE_FORM 결과 포함 검색어로 확인 |
| `public_url` 링크 (`/reference-form/{slug}`) | 카드 클릭 → 상세페이지 이동 |
| `type=reference-form` 단독 검색 | 타입 필터 동작 |
| 더보기·페이지 이동 | 10건 초과 결과 |
| 공개 취소 후 결과 제거 | 취소 서식 검색어 → 결과 없음 |

---

## 작업 7 — SEO/사이트맵 QA 교정

### seo-meta-lint.mjs 실제 강제 기준 (코드 검증)

| 필드 | 강제 기준 (HARD FAIL) | 권장 범위 |
|------|------|------|
| title | > 60자 → FAIL | 30-60자 |
| description | > 170자 → FAIL | 120-160자 |
| description | < 30자 (비카드) → FAIL | — |

**교정:** BaseLayout이 "description 120~160자를 자동 강제"한다는 기술은 틀림.
- BaseLayout: `title`, `description` 미제공 시 빌드 에러 (빈값 방지만)
- seo-meta-lint: 30~170자 범위 강제 (HARD FAIL); 120~160자는 권장 범위

### sitemap 처리 방식

| 사이트맵 | 생성 방식 | composite-entry.js 등록 |
|---------|---------|------|
| `sitemap_guides.xml` | Astro SSR (`prerender=false`) | 필요 (line 21 등록됨) |
| `sitemap_knowledge.xml` 외 기존 | pages-live-worker.js 정적 생성 | 불필요 |
| `sitemap_reference_forms.xml` | Astro SSR (`prerender=false`) **권장** | **필요** (신규 추가) |

### SEO 검증 체계

| 검증 수단 | 대상 | 한계 |
|---------|------|------|
| `seo-dupcheck.mjs` | `dist/**/*.html` (빌드 산출물) | 동적 SSR URL 미포함 |
| `seo-meta-lint.mjs` | 동일 | 동적 SSR URL 미포함 |
| 동적 SSR QA | 실행 응답 직접 확인 | CI 자동화 별도 필요 |

**신규 동적 SSR URL(`/reference-form/{id}`)은 정적 dupcheck 외에 실행 응답 검사 필요.**

### 미승인 콘텐츠 게이트

| 항목 | 미승인 처리 |
|------|---------|
| 상세페이지 robots | `noindex,follow` 적용 |
| 사이트맵 포함 여부 | 제외 (status=PUBLISHED 조건) |
| OpenSearch 색인 | visibility_scopes=[] (PUBLIC 없음) |
| IndexNow 제출 | ALLOWED_SITEMAPS 추가 — **Owner 별도 승인** |

---

## 작업 8 — 의존성 상태 유지

| 항목 | 상태 |
|------|------|
| REF-05 CMS DDL/RLS/Storage | BLOCKED |
| REF-08 파일·콘텐츠 QA | BLOCKED |
| 다운로드 방식 A/B 결정 | OWNER DECISION REQUIRED |
| Gate B 코드 구현 | BLOCKED (REF-05+08 해소 전) |

---

## 제출 요약

| 항목 | 값 |
|------|-----|
| 원격 HEAD (WO 브랜치) | 이 커밋 push 후 확인 |
| tai-api remote main | `3a80af08...` |
| tai-www remote main | `3fd8f6b1...` |
| 변경 파일 | Gate A 교정 문서 1개 신규 |

### 확정 canonical URL 계약 (GPT 승인 대기)

제안: `/reference-form/{canonical_slug}`

4-way 일치 대상: SearchDocument.public_url / canonical / sitemap loc / 검색 카드 href

### 핵심 교정 사항 3가지

1. **composite-entry.js 변경 필수** — `/reference-form/{id}`, `/sitemap_reference_forms.xml` 명시적 등록 없이 SSR 라우팅 불가
2. **OS-07 수정** — fence 활성 시 enqueue 성공 (PENDING 생성됨), 처리 단계에서 차단
3. **SEO 길이 강제 기준** — title ≤60, description 30~170 (HARD FAIL); 120~160은 권장

NEXT_GATE: GPT_REF01_PUBLIC_SEARCH_SEO_DESIGN_VERIFY_R2
