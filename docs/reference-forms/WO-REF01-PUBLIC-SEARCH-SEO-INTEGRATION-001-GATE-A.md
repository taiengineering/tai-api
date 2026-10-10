---
wo: WO-REF01-PUBLIC-SEARCH-SEO-INTEGRATION-001-GATE-A
date: 2026-10-11
status: GATE_A_COMPLETE
section: OBJ-REF-04 / OBJ-REF-09
publication: NOT_FOR_PUBLICATION
dependency: REF-05 + REF-08 (BLOCKED)
---

# Gate A 조사 결과 — 참고서식 공개 검색·SEO 통합

WO-REF01-PUBLIC-SEARCH-SEO-INTEGRATION-001 Gate A (READ-ONLY 조사).

---

## 1. 현재 Repo HEAD 및 관련 PR

| Repo | HEAD | Branch |
|------|------|--------|
| tai-api (WO 작업 브랜치) | `557fdfa50c90e4ee2c3ca49a17b0fa507eaa0b6e` | `docs/tai-reference-forms-charter-obj-20261008` |
| tai-www | `dc842ed3` | `perf/www-load-optimization-001` |

tai-api main: `83420943` (WO 브랜치가 main보다 4커밋 앞)
PR: #564 (OPEN — docs 브랜치, MERGE 금지)

---

## 2. WP별 재사용 가능 기존 코드

### WP-01 서식별 동적 상세페이지

| 역할 | 재사용 파일 | 비고 |
|------|---------|------|
| SSR 상세 라우트 패턴 | `src/pages/safety-guide/[id].astro` | on-demand SSR, 404 처리 |
| SSR 상세 라우트 패턴 2 | `src/pages/safety-search/legal/[id].astro` | 503 fallback 포함 |
| SEO 레이아웃 | `src/layouts/BaseLayout.astro` | title/description/canonical/jsonld |
| 연관검색어 | `src/components/seo/RelatedKeywords.astro` | props: items[], resolveHref |
| 인증 체크 | `src/lib/modules/auth.js` | 기존 TAI 토큰 검증 |
| 세션·redirect | `src/lib/session.js` | redirect= 쿼리 처리 |
| 비회원 모달 | 진단/결제 페이지 기존 패턴 참조 | 로그인·회원가입 CTA |

**신규 필요:**
- `src/pages/reference-form/[id].astro` — 서식 상세페이지
- `src/lib/server/referenceForm.js` — API fetcher (getReferenceFormById 등)
- 다운로드 모달 컴포넌트 (비회원 로그인/회원가입 안내)

### WP-02 SEO 연결

| 역할 | 재사용 파일 | 비고 |
|------|---------|------|
| SEO 레이아웃 | `src/layouts/BaseLayout.astro` | title, description, canonical, jsonld 전달 |
| SEO 정책 문서 | `docs/seo/OVERVIEW_seo-overhaul-2026-09.md` | v1.2 §7 N-1 rule 준수 |
| 중복 방지 CI | `scripts/seo-dupcheck.mjs` | PR마다 실행, PASS 필수 |
| DUPGUARD 계약 | `docs/seo/DUPGUARD.md` | 회귀 기준 |

**BaseLayout 핵심 SEO 파라미터:**
- `title` (필수, ≤60자), `description` (필수, 120-160자)
- `canonical` (자동 정규화: https, 슬래시 없음), `robots` (기본: index,follow)
- `jsonld` (object[]), `article` (publishedTime, modifiedTime, section, author)

**규칙 (WO-SEO-03c v1.2 §7):**
- N-1: `title === og:title`, `description === og:description`
- 미승인 서식: `robots="noindex,follow"` 적용
- 빈 title/description: 빌드 에러 발생 (빌드 게이트)

### WP-03 사이트맵

| 역할 | 재사용 파일 | 비고 |
|------|---------|------|
| sitemap_index 생성 | `workers/pages-live-worker.js` (line 881) | `handleSitemapIndex()` |
| 기존 사이트맵 등록 패턴 | 동 파일 line 903-916 | `sitemaps` 배열에 추가 |
| 사이트맵 페이지 패턴 | `src/pages/sitemap_guides.xml.js` | 정적 생성 패턴 |
| IndexNow 허용목록 | `scripts/lib/indexnow-sitemap.mjs` (line 10) | `ALLOWED_SITEMAPS` Set |

**현재 등록된 sitemap 자식 목록:**
`sitemap_marketing.xml`, `sitemap_knowledge.xml`, `sitemap_safetynews.xml`,
`sitemap_precedents.xml`, `sitemap_accidents.xml`, `sitemap_accidents_csi.xml`,
`sitemap_laws.xml`, `sitemap_guides.xml`, `sitemap_safety.xml`,
`sitemap_msds.xml`, `sitemap_legal_articles.xml`, `sitemap_hubs.xml`

**신규 필요:**
- `src/pages/sitemap_reference_forms.xml.js` (또는 worker 동적 생성)
- `workers/pages-live-worker.js` 수정: `sitemaps` 배열에 `/sitemap_reference_forms.xml` 추가
- IndexNow 허용목록 변경: **별도 Owner 승인 게이트 유지**

### WP-04 OpenSearch 및 통합검색

**tai-api 재사용 코드:**

| 역할 | 파일 | 비고 |
|------|------|------|
| 어댑터 프로토콜 | `services/shared_search/adapters/base.py` | DomainAdapter Protocol |
| SearchDocument 모델 | `services/shared_search/document.py` | 16개 필드 정의 |
| 계약 상수 | `services/shared_search/contract.py` | publication_status, visibility_scopes |
| production 레지스트리 | `services/shared_search/production_bindings.py` | `build_production_adapters()` |
| Incremental outbox | `services/shared_search/incremental.py` | `process_queue()`, `sync_object()` |
| 공개 검색 라우터 | `routers/public_safety_search.py` | object_type allowlist, sections |
| 공통 헬퍼 | `services/shared_search/adapters/_common.py` | `coerce_iso()`, `as_str_list()` 등 |

**tai-www 재사용 코드:**

| 역할 | 파일 | 비고 |
|------|------|------|
| 검색 그룹 정의 | `src/lib/server/safetySearch.js` (line 26-36) | `GROUP_DEFS` 배열 |
| 타입 허용목록 | 동 파일 (line 14-25) | `TYPE_ALLOWLIST` |
| 검색 화면 | `src/pages/safety-search.astro` | noindex,follow |

---

## 3. 신규 생성·변경 필요 파일 목록

### tai-api

| 파일 | 변경 유형 | 내용 |
|------|---------|------|
| `services/shared_search/adapters/reference_form.py` | 신규 | REFERENCE_FORM 도메인 어댑터 |
| `services/shared_search/adapters/__init__.py` | 수정 | ReferenceFormAdapter import 추가 |
| `services/shared_search/production_bindings.py` | 수정 | `_make_reference_form_adapter()` + 레지스트리 등록 |
| `routers/public_safety_search.py` | 수정 | `_PUBLIC_OBJECT_TYPES`, `_TYPE_MAP`, `_SECTION_TYPES` 3곳 |

### tai-www

| 파일 | 변경 유형 | 내용 |
|------|---------|------|
| `src/pages/reference-form/[id].astro` | 신규 | SSR 서식 상세페이지 |
| `src/lib/server/referenceForm.js` | 신규 | API fetcher (getReferenceFormById 등) |
| `src/pages/sitemap_reference_forms.xml.js` | 신규 | 서식 사이트맵 (또는 worker 수정) |
| `workers/pages-live-worker.js` | 수정 | `sitemaps` 배열에 서식 사이트맵 추가 |
| `src/lib/server/safetySearch.js` | 수정 | `GROUP_DEFS` + `TYPE_ALLOWLIST` 확장 |

### 비고
- `scripts/lib/indexnow-sitemap.mjs`: IndexNow 허용목록 — **Owner 별도 승인 후 수정**

---

## 4. CMS/Storage/OpenSearch 연동 계약

### 4.1 REF-05 CMS 스키마 (현재 BLOCKED)

WO 지정 8개 테이블 (물리 DDL 미확정):
```
reference_forms          — canonical ID, 대표명, 게시상태
reference_form_content   — SEO·작성법·FAQ·canonical URL
reference_form_files     — 1:N 포맷/버전/검수/해시
reference_form_sources   — 원본 기관·근거·이용권
reference_form_relations — 문서 관계/업무 흐름
reference_form_legacy_links — 기존 DB 원본 식별자
reference_form_aliases   — 유사 검색명
reference_form_events    — 리뷰/승인/발행 감사기록
```

### 4.2 Storage 계약

| 항목 | 계약 |
|------|------|
| Storage 접근 | 비공개 bucket, public RLS 금지 |
| 다운로드 방식 | 방식 A/B 미결정 (WO-REF04-REF09-UI-SPECIFICATION-001 §6 참조) |
| 파일 URL | 브라우저에 Storage 직접 URL 전달 금지 (방식 A 채택 시) 또는 단기 Signed URL (방식 B) |
| 파일 공개 조건 | reference_form_files 검수 완료 + Owner 게시 승인 |

### 4.3 OpenSearch 연동 계약

| 항목 | 값 |
|------|-----|
| object_type | `REFERENCE_FORM` (충돌 없음 — 신규) |
| outbox 테이블 | `public.search_index_outbox` |
| publication_status | `PUBLISHED` (공개승인 후) / `HOLD` / `REMOVED` |
| visibility_scopes | `["PUBLIC", "SAAS", "PAID"]` (공개승인 후) |
| public_url | `/reference-form/{canonical_id}` |
| 색인 조건 | reference_forms.status = PUBLISHED + Owner 공개 승인 |
| 색인 삭제 조건 | status = REMOVED 또는 공개 취소 |
| Rebuild fence | `search_index_fence.rebuild_active` 체크 필수 |

**SearchDocument 필수 필드 (신규 어댑터):**

| 필드 | 값 |
|------|----|
| `object_type` | `"REFERENCE_FORM"` |
| `canonical_id` | reference_forms.id (uuid) |
| `source_id` | `"TAI_REFERENCE_FORMS"` |
| `title` | 서식 대표명 |
| `summary` | 서식 요약 (≤160자) |
| `search_text` | 서식명 + 작성법 요약 + FAQ + aliases |
| `aliases` | 유사 검색명 (reference_form_aliases) |
| `keywords` | 카테고리/업무/산업 태그 |
| `public_url` | `/reference-form/{id}` |
| `publication_status` | `PUBLISHED` |
| `visibility_scopes` | `["PUBLIC", "SAAS", "PAID"]` |
| `source_updated_at` | reference_form_events 최신 승인 시각 |

**금지 필드:** `company_id`, `factory_id`, `user_id`, API 키, applicability 필드, LLM 필드

---

## 5. URL·SEO·사이트맵 정합성 매트릭스

| 항목 | 계획 값 | 기존 패턴 준수 여부 |
|------|---------|--------------|
| canonical URL | `https://taieng.co.kr/reference-form/{id}` | ✓ (https, 슬래시 없음, 파라미터 없음) |
| sitemap URL | `/sitemap_reference_forms.xml` | ✓ (기존 명명 규칙 `sitemap_{name}.xml`) |
| sitemap_index 등록 | `workers/pages-live-worker.js` sitemaps 배열 | ✓ |
| lastmod | reference_form_events 최신 승인 시각 | ✓ (fake epoch 금지) |
| 공개 조건 | status=PUBLISHED + Owner 승인 | ✓ (기존 GUIDE/MATERIAL과 동일) |
| noindex 조건 | status≠PUBLISHED 또는 미승인 | ✓ BaseLayout robots="noindex,follow" |
| SEO title | 서식명 + 태그 조합, ≤60자 | ✓ (build guard 자동 적용) |
| SEO description | 서식 요약, 120-160자 | ✓ (build guard 자동 적용) |
| N-1 rule | title = og:title, description = og:description | ✓ BaseLayout 자동 적용 |
| dupcheck CI | `scripts/seo-dupcheck.mjs` | PR마다 통과 필수 |
| JSON-LD | Article + BreadcrumbList | ✓ (기존 legal/guide 패턴) |
| IndexNow 허용 | `ALLOWED_SITEMAPS` 추가 | ⚠ Owner 별도 승인 필요 |

---

## 6. OpenSearch 색인·삭제 테스트 매트릭스

| ID | 시나리오 | 예상 결과 |
|----|---------|---------|
| OS-01 | 서식 게시 승인 → `enqueue_search_index_sync()` 호출 | outbox PENDING 레코드 생성 |
| OS-02 | incremental processor 실행 → `object_reindex_payload()` 호출 | SearchDocument 색인 성공 |
| OS-03 | 동일 canonical_id 재색인 (내용 변경 없음) | content_hash 일치 → NOOP |
| OS-04 | 동일 canonical_id 재색인 (내용 변경) | 색인 갱신 성공 |
| OS-05 | 서식 공개 취소 → publication_status=REMOVED | OpenSearch 문서 삭제 |
| OS-06 | 서식 공개 취소 → visibility_scopes=[] | PUBLIC 검색에서 제외 |
| OS-07 | `search_index_fence.rebuild_active=true` 상태에서 enqueue | fence 차단 → PENDING 생성 안 됨 |
| OS-08 | 미승인 서식 (status≠PUBLISHED) → `iter_documents()` | 해당 row yield 안 됨 |
| OS-09 | `public/safety-search?q=서식명&type=reference-form` | REFERENCE_FORM 결과 반환 |
| OS-10 | `public/safety-search?q=서식명` (type=all) | REFERENCE_FORM 결과 포함 |
| OS-11 | 비공개 서식 (noindex) → 공개 검색 API | 결과 없음 (visibility_scopes에 PUBLIC 없음) |

---

## 7. 통합검색 E2E 테스트 계획

**순방향 (공개 → 검색 노출):**

```
fixture: approved_reference_form (status=PUBLISHED, visibility=[PUBLIC])
→ SearchDocument 생성 확인 (object_type=REFERENCE_FORM)
→ OpenSearch 색인 확인 (canonical_id 조회)
→ /public/safety-search?q={title} 반환에 REFERENCE_FORM 포함
→ 검색 화면 GROUP_DEFS["reference-form"] 카드 렌더링
→ 카드 클릭 → /reference-form/{id} 상세페이지 이동
→ 상세페이지 SSR 렌더링 확인 (title/description/canonical)
→ 사이트맵에 URL 포함 확인 (sitemap_reference_forms.xml)
→ 비회원 다운로드 클릭 → 로그인 모달 표시
→ 회원 다운로드 클릭 → 서버 인증 → 파일 다운로드
```

**역방향 (공개 취소 → 검색 제거):**

```
fixture: 상기 fixture의 공개 취소 (status=REMOVED)
→ SearchDocument publication_status=REMOVED 또는 삭제
→ OpenSearch 문서 제거 확인
→ 사이트맵에서 URL 제외 확인
→ /public/safety-search?q={title} → 결과 없음
→ /reference-form/{id} → 404 또는 noindex 응답
→ 파일 다운로드 → 404 또는 접근 거부
```

**격리 원칙:**
- 결정론적 fixture 사용 (운영 데이터 참조 금지)
- 운영 OpenSearch 재색인 금지 (Owner 승인 전)
- 운영 DB write 금지

---

## 8. 의존성 및 BLOCKED 목록

| ID | 항목 | 상태 | 차단 이유 |
|----|------|------|---------|
| DEP-01 | REF-05 CMS 스키마 (8개 테이블 DDL) | BLOCKED | Owner 승인 + 기존 API 충돌 검토 미완 |
| DEP-02 | REF-08 콘텐츠 팩토리 QA | BLOCKED | REF-05 선행 필요 |
| DEP-03 | reference_form_files Storage bucket | BLOCKED | REF-05 선행 필요 |
| DEP-04 | 다운로드 방식 A/B 결정 | PENDING | Owner + GPT 설계 결정 필요 |
| DEP-05 | IndexNow 허용목록 추가 | PENDING | 별도 Owner 승인 |
| DEP-06 | 운영 OpenSearch 색인 활성화 | PENDING | Gate C (GPT 독립검증 + Owner 승인) |
| DEP-07 | 운영 배포·공개 색인 | PENDING | Gate C |

**Gate B 착수 조건 (코드 구현 허용):**
1. REF-05 CMS 스키마 Owner 승인 + DDL 적용
2. REF-08 파일 생산 및 QA 완료
3. 다운로드 방식 A/B 결정

**Gate B에서 구현 가능한 항목 (개발 브랜치, 격리 테스트):**
- 도메인 어댑터 `REFERENCE_FORM` (tai-api)
- 공개 검색 라우터 확장 (tai-api)
- SSR 상세페이지 `/reference-form/[id].astro` (tai-www)
- 검색 프론트엔드 `GROUP_DEFS` / `TYPE_ALLOWLIST` 확장 (tai-www)
- 사이트맵 생성 (tai-www)

---

## 9. 현재 충돌·위험 없음 확인

| 항목 | 확인 결과 |
|------|---------|
| `REFERENCE_FORM` object_type 충돌 | 없음 — 신규 추가 안전 |
| `참고서식` / `reference-form` tai-www 기존 코드 | 없음 — 신규 추가 안전 |
| `/reference-form/` URL 경로 충돌 | 없음 |
| `sitemap_reference_forms.xml` 충돌 | 없음 |

NEXT_GATE: `GPT_REF01_PUBLIC_SEARCH_SEO_DESIGN_VERIFY`
