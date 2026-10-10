---
wo: WO-REF01-GATE-A-R2-FINAL-CONTRACT-003
date: 2026-10-11
status: CONTRACT_READY
section: OBJ-REF-04 / OBJ-REF-09
publication: NOT_FOR_PUBLICATION
dependency: REF-05 + REF-08 (BLOCKED)
parent: WO-REF01-PUBLIC-SEARCH-SEO-GATE-A-CORRECTION-002.md
---

# Gate A R2 — 최종 계약 (Canonical Identity · Outbox · 원자성 · 공개취소)

WO-REF01-GATE-A-R2-FINAL-CONTRACT-003.

GPT R2 HOLD 결함 3건 + HIGH 2건 교정. DOCS ONLY.

---

## 1. Canonical Identity 확정

### 역할별 식별자

| 역할 | 값 | 불변 여부 |
|------|-----|------|
| SearchDocument.canonical_id | `reference_forms.id` (UUID) | 불변 |
| OpenSearch `_id` | `REFERENCE_FORM::{reference_forms.id}` | 불변 |
| 공개 URL | `/reference-form/{canonical_slug}` | 변경 시 301 |
| SEO `<link rel="canonical">` | `https://taieng.co.kr/reference-form/{canonical_slug}` | slug 기준 |
| sitemap `<loc>` | 동일 절대 URL | slug 기준 |
| SearchDocument.public_url | `/reference-form/{canonical_slug}` | slug 기준 |
| 검색 결과 카드 href | 동일 | slug 기준 |

**4-way URL 정합 계약:** `SearchDocument.public_url`, canonical href, sitemap loc, 카드 href는 모두 동일한 절대·상대 경로를 가리켜야 한다. 상대/절대 혼용 방지를 위해 sitemap은 절대 URL, 내부 href는 상대 URL 사용.

### slug 관리

- `reference_form_content.canonical_slug TEXT UNIQUE NOT NULL` — REF-05 DDL에 포함 필요
- 슬러그 변경 시 변경 전 slug → 새 slug로 301 redirect (Google 색인 보호)
- 이전 slug 재사용 및 충돌 방지: `reference_form_slug_history` 테이블 또는 `UNIQUE` 인덱스로 전 slug 보존 — REF-05 설계 포함
- slug 변경 이벤트 → SearchDocument.public_url 갱신 → OpenSearch 재색인 필수

### OpenSearch ID 교정

Gate A Correction-002에서 `canonical_id = {slug or uuid}` 로 열어 두었던 부분 확정:
- **`canonical_id` = UUID (불변)** — slug 변경이 기존 색인을 고아(orphan)로 남기는 문제 해소
- OpenSearch에서 `GET /reference-form/_doc/REFERENCE_FORM::{uuid}` 로 항상 동일 문서 접근

---

## 2. Outbox 이벤트 키 설계

### 기존 코드 패턴 조사 결과

| 서비스 | event_key 패턴 | 비고 |
|--------|------|------|
| kosha_guide_sync | `guide_snapshot:{snapshot_id}:{gid}` | 배치 실행 당 고유 snapshot_id |
| kosha_safety_material_sync | `safety_material_snapshot:{snapshot_id}:{mid}` | 동일 |
| safe_help_svc (KNOWLEDGE) | `knowledge:{doc_id}:{reason}:{uuid4()}` | 매 호출마다 uuid4() 생성 |
| opensearch_reconcile | `reconcile:{reconcile_run_id}:{domain}:{cid}` | 실행 당 고유 run_id |
| csi_accidents/store | `csi_snapshot:{snapshot_id}:{cid}` | 동일 |

**ON CONFLICT (event_key) DO NOTHING** — 동일 키 재등록은 무시(idempotent).

### REFERENCE_FORM 이벤트 키 계약

`safe_help_svc.py` (KNOWLEDGE) 패턴 채택:

```python
# reference_form_events.id = UUID (CMS 변경 이벤트 고유 식별자)
event_key = f"reference_form:{canonical_id}:{cms_event_id}"
```

`cms_event_id` = `reference_form_events.id` (UUID, 변경 이벤트마다 신규 생성)

**결과:**
| 시나리오 | 동작 |
|---------|------|
| 최초 변경 → enqueue | 고유 event_key → PENDING 생성 |
| 동일 변경 이벤트 재시도 | 동일 event_key → ON CONFLICT DO NOTHING (중복 방지) |
| 동일 서식 두 번째 수정 | 새 `cms_event_id` → 새 event_key → 별도 PENDING 생성 |
| slug만 변경 | 새 cms_event_id → 새 event_key → OpenSearch public_url 갱신 |

**Gate A Correction-002 오류:** `{canonical_id}:{reason}` 패턴은 같은 서식의 반복 수정 시 두 번째 이벤트가 `DO NOTHING`으로 누락됨 → 폐기.

---

## 3. CMS-Outbox 원자성

### 기존 패턴 검토

- `kosha_guide_sync`, `kosha_safety_material_sync`, `csi_accidents/store`: 배치 실행 후 RPC 호출. 트랜잭션 없음 (배치 실패 허용, 다음 실행에서 재처리).
- `safe_help_svc.py` (KNOWLEDGE): 동일 API 요청 내 순차 실행. PostgreSQL 트랜잭션 없음.

### REFERENCE_FORM 요구사항

CMS 상태 변경(게시 승인)과 outbox INSERT가 동일 PostgreSQL 트랜잭션 내 성공 또는 실패해야 함.

**Gate A Correction-002 오류:** "동일 API 요청 내 순차 실행"을 원자성 보증으로 허용 → 폐기. CMS 저장 성공 + outbox 등록 실패 시 영구 불일치 가능.

### 설계 방식 선택 (REF-05 DDL 설계 시 결정)

| 방식 | 설명 | 주의사항 |
|------|------|---------|
| **A (권장): DB trigger** | `reference_forms.status` 변경 또는 `reference_form_events` INSERT 시 AFTER 트리거로 `enqueue_search_index_sync()` 자동 호출 | 트리거 내 RPC 가능 여부 Supabase 제약 확인 필요 |
| **B: Stored Procedure (RPC)** | 단일 DB 함수가 CMS UPDATE + outbox INSERT를 동일 트랜잭션으로 래핑 | `SECURITY INVOKER` 권한 설계 필요 |
| **C: Client-side transaction** | PostgREST transaction API or Supabase 클라이언트 트랜잭션 | 클라이언트 트랜잭션 보장 여부 검증 필요 |

**방식 A 또는 B를 REF-05 DDL 설계에서 확정한다.** 방식 C는 클라이언트 보장이 약하므로 기본 선택에서 제외.

공통 금지사항: `service_role` 키 클라이언트 노출. RLS + RPC EXECUTE 권한은 REF-05에서 명시.

---

## 4. 증분색인 스케줄러 상태

### 마이그레이션 코드 기반 확인

```sql
-- 20260920_shared_search_incremental_outbox.sql line 245:
-- "Incremental indexing scheduler jobs (INACTIVE — activation is separate)"
INSERT INTO public.cron_job_master (..., is_active, ...)
VALUES ('shared_search_incremental', ..., false, ...)
ON CONFLICT (job_code) DO NOTHING;
```

마이그레이션 등록 시 `is_active = false` (비활성). `ON CONFLICT DO NOTHING`이므로 기존 row가 있으면 변경 없음.

### 운영 현재 활성 상태

| 항목 | 확인 결과 |
|------|---------|
| 마이그레이션 초기 등록 상태 | `is_active = false` (비활성) |
| 운영 DB 현재 is_active 값 | **UNVERIFIED** (READ-ONLY DB 쿼리 필요, 환경 접근 불가) |
| `cron_schedule_config.is_enabled` 현재 값 | **UNVERIFIED** |
| 최근 outbox 처리 이력 | **UNVERIFIED** |

**GPT 우려 근거 확인됨:** 마이그레이션이 비활성으로 등록하므로, 별도 활성화 조치가 없으면 운영에서 증분색인이 실행되지 않는다. 실제 운영 상태는 DB 쿼리 없이 코드만으로 판정 불가.

**Gate B 착수 전 확인 필요:** 운영 DB `SELECT is_active FROM cron_job_master WHERE job_code='shared_search_incremental'` 결과.

---

## 5. 공개 취소 Fail-Closed

`noindex` 단독 적용으로는 파일·미리보기 접근을 차단할 수 없다. 공개 취소 시 모든 레이어에서 동시 처리 필요.

### 공개 취소 전파 매트릭스

| 레이어 | 처리 방법 | 근거 |
|--------|---------|------|
| OpenSearch | tombstone (publication_status=REMOVED, visibility_scopes=[]) | 검색 결과 즉시 제거 |
| 사이트맵 | `status=PUBLISHED` 조건 → 자동 제외 | sitemap_reference_forms.xml 재생성 |
| SEO | `robots="noindex,follow"` 또는 404 반환 | 검색엔진 색인 방지 |
| 상세페이지 | status 확인 → 404 또는 noindex 렌더 | 직접 접근 차단 |
| 미리보기 | Storage ACL 또는 API 게이트 — 상태 확인 후 거부 | noindex만으로 불충분 |
| 파일 다운로드 | API 게이트 — 게시 승인 상태 확인 후 거부 | 인증 외 승인 상태도 검증 |
| CF 캐시 | TTL 내 stale 가능 → CF Cache Purge 또는 짧은 TTL 정책 필요 | 즉시 차단 보장 불가 |
| 이전 slug URL | 301 → 새 URL 또는 404 (취소 시) | slug 이력 레코드 활용 |
| 구버전 파일 | Storage ACL + API 게이트에서 version 상태 확인 | 버전 우회 방지 |

**핵심 계약:** 미리보기와 파일은 Storage 공개 URL 직접 접근이 아닌 API 게이트를 통해 제공해야 공개 취소가 즉시 반영된다. (= `WO-REF04-REF09-UI-SPECIFICATION-001 §6` 방식 A 선택 시 자동 보장)

---

## 6. SEO 정합화

### BaseLayout vs seo-meta-lint 기준 구분

| 검증 수단 | 강제 기준 | 권장 범위 |
|---------|---------|---------|
| BaseLayout (빌드 에러) | `title` 또는 `description` 미제공 시 Error | — |
| `seo-meta-lint.mjs` (HARD FAIL) | title > 60자, description > 170자 또는 < 30자 | — |
| SEO 정책 권장 | — | title 30-60자, description 120-160자 |

120~160자는 권장 범위이며 빌드 또는 lint의 강제 기준이 아님.

### 동적 SSR URL SEO 검증

`seo-dupcheck.mjs`와 `seo-meta-lint.mjs`는 `dist/**/*.html` 정적 빌드 산출물만 검사.
신규 `/reference-form/{id}` (prerender=false)는 포함되지 않음.

| 검증 방법 | 대상 |
|---------|------|
| 정적 dupcheck | `dist/*.html` — 기존 방식 |
| 동적 SSR QA | 서버 실행 후 HTTP 응답 직접 확인 (별도 자동화 필요) |

### 4-way URL 정규화

```
SearchDocument.public_url  = /reference-form/{slug}           (상대)
<link rel="canonical">     = https://taieng.co.kr/reference-form/{slug}  (절대)
sitemap <loc>             = https://taieng.co.kr/reference-form/{slug}  (절대)
카드 href                  = /reference-form/{slug}           (상대)
```

### 사이트맵 Worker 분류 교정

| 사이트맵 | 생성 방식 |
|---------|---------|
| `sitemap_guides.xml` | Astro SSR (prerender=false) + composite-entry.js 등록 |
| `sitemap_knowledge.xml`, `sitemap_safetynews.xml` 등 | pages-live-worker.js 동적 처리 |
| `sitemap_reference_forms.xml` | Astro SSR (prerender=false) 권장 + composite-entry.js 등록 필요 |

Gate A 문서에서 "기존 사이트맵 = 정적 생성"으로 일반화한 표현 교정. 일부는 Worker 동적 처리.

---

## 7. 교정된 E2E 테스트 매트릭스 (전체)

### OpenSearch 색인 (OS-)

| ID | 시나리오 | 예상 결과 |
|----|---------|---------|
| OS-01 | 서식 공개 승인 → enqueue (cms_event_id A) | outbox PENDING 생성, event_key=`reference_form:{id}:{A}` |
| OS-02 | incremental processor 실행 | SearchDocument 색인 성공 |
| OS-03 | 동일 cms_event_id 재전달 (재시도) | ON CONFLICT DO NOTHING, 중복 없음 |
| OS-04 | 동일 서식 두 번째 수정 (cms_event_id B) | 별도 event_key=`reference_form:{id}:{B}` → 별도 PENDING |
| OS-05 | 공개 취소 → enqueue (cms_event_id C) | PENDING 생성, processor 후 OpenSearch tombstone |
| OS-06 | 공개 취소 후 `/public/safety-search` 조회 | REFERENCE_FORM 결과 없음 |
| OS-07 | fence 활성 + enqueue 호출 | PENDING 생성됨 (enqueue fence 미체크), processor 차단 |
| OS-08 | fence 해제 후 processor 실행 | 대기 PENDING 이벤트 처리, 색인 갱신 |
| OS-09 | 미승인 서식 → `iter_documents()` | yield 안 됨 |
| OS-10 | `?q=서식명&type=reference-form` | REFERENCE_FORM 결과 반환 |
| OS-11 | `?q=서식명` (type=all) | REFERENCE_FORM 포함 |
| OS-12 | 비공개 서식 공개 검색 | 결과 없음 (PUBLIC scope 없음) |

### 공개 취소 (UNPUB-)

| ID | 시나리오 | 예상 결과 |
|----|---------|---------|
| UNPUB-01 | 공개 취소 후 검색 | 결과 없음 |
| UNPUB-02 | 공개 취소 후 상세페이지 접근 | 404 또는 noindex 응답 |
| UNPUB-03 | 공개 취소 후 사이트맵 | URL 포함 안 됨 |
| UNPUB-04 | 공개 취소 후 파일 다운로드 | 게시 상태 확인 → 거부 |
| UNPUB-05 | 공개 취소 후 미리보기 | API 게이트 → 거부 |
| UNPUB-06 | 공개 취소 후 이전 slug URL | 404 또는 301 없음 |

### 원자성 (ATOM-)

| ID | 시나리오 | 예상 결과 |
|----|---------|---------|
| ATOM-01 | CMS 저장 성공 + outbox 등록 성공 | 양쪽 모두 반영 |
| ATOM-02 | CMS 저장 성공 + outbox 등록 실패 강제 | 전체 롤백 (CMS도 미반영) |
| ATOM-03 | 동일 서식 두 번 수정 | 각각 독립 이벤트, 순서대로 색인 |

### E2E 순방향 (E2E-)

| ID | 단계 | 확인 항목 |
|----|------|---------|
| E2E-01 | CMS 승인 → SearchDocument 생성 | object_type=REFERENCE_FORM, canonical_id=UUID |
| E2E-02 | OpenSearch 색인 | `_id=REFERENCE_FORM::{uuid}` 존재 |
| E2E-03 | 검색 API | REFERENCE_FORM 결과 포함 |
| E2E-04 | 검색 화면 | '참고서식' 섹션 레이블, 카드 렌더 |
| E2E-05 | 카드 클릭 | `/reference-form/{slug}` 상세페이지 이동 |
| E2E-06 | 상세페이지 SSR | title/description/canonical 정합 |
| E2E-07 | 사이트맵 | URL 포함 |
| E2E-08 | 비회원 다운로드 | 로그인 모달 |
| E2E-09 | 회원 다운로드 | 서버 인증 → 파일 전달 |
| E2E-10 | slug 변경 | canonical_id 불변, public_url 갱신, 이전 URL 301 |

---

## 8. 스케줄러 확인 항목 (Gate B 착수 전)

DB READ-ONLY 쿼리 필요 (환경 접근 불가로 UNVERIFIED):

```sql
SELECT job_code, is_active FROM cron_job_master
WHERE job_code IN ('shared_search_incremental', 'shared_search_reconcile');

SELECT job_code, is_enabled FROM cron_schedule_config
WHERE job_code IN ('shared_search_incremental', 'shared_search_reconcile');

SELECT status, COUNT(*) FROM search_index_outbox GROUP BY status;
SELECT MAX(completed_at) FROM search_index_outbox WHERE status='COMPLETED';
```

---

## 9. 의존성 상태

| 항목 | 상태 |
|------|------|
| REF-05 CMS DDL/RLS/Storage | BLOCKED — slug UNIQUE 인덱스 + slug_history + outbox 트랜잭션 방식 포함 |
| REF-08 파일·콘텐츠 QA | BLOCKED |
| 다운로드 방식 A/B 결정 | OWNER DECISION REQUIRED |
| 스케줄러 운영 활성 상태 | UNVERIFIED (DB 접근 필요) |
| Gate B 코드 구현 | BLOCKED |

---

## 10. 교정 요약 (GPT R2 HOLD → 처리 결과)

| GPT 지적 | 처리 결과 |
|---------|---------|
| event_key 반복 수정 누락 | `cms_event_id` 기반 event_key로 교정 |
| CMS-Outbox 원자성 | DB trigger (A) 또는 Stored Procedure (B) — REF-05 설계에서 확정 |
| canonical_id = UUID (slug 아님) | UUID 불변 확정, slug는 public_url/canonical만 |
| 스케줄러 비활성 가능성 | 마이그레이션 `is_active=false` 확인, 운영 상태 UNVERIFIED |
| 공개 취소 noindex만으로 불충분 | 미리보기·다운로드·캐시 레이어별 처리 계약 추가 |
| 사이트맵 Worker 표현 교정 | 일부 Worker 동적, 일부 Astro SSR 구분 명시 |

NEXT_GATE: GPT_REF01_GATE_A_FINAL_DESIGN_VERIFY
