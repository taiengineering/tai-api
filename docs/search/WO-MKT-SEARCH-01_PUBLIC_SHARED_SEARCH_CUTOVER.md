---
class: work-order
type: IMPLEMENTATION
scope: marketing-public-search
project: tai-www
title: WO-MKT-SEARCH-01 — Public Shared Search Cutover
version: 1
status: READY
owner: taiwang
plan: PLAN-MKT-PUBLIC-SEARCH-OBJECT-001
objects: OBJ-MKT-SEARCH-01, OBJ-MKT-SEARCH-02
---

# WO-MKT-SEARCH-01 — Public Shared Search Cutover

**Repo:** `taiengineering/tai-www`  
**Base:** `eaf55c74bf4f837b7cc13fa06b0b3adaaa766fa4`  
**Backend:** `GET /public/safety-search` ACTIVE · `GET /public/safety-search/kosha` ACTIVE  
**CODE CHANGE = tai-www only · DB CHANGE = 0 · tai-api CHANGE = 0**

---

## 0. 사전 확인된 사실

조사 불필요. 이미 확인된 사실만.

### 현재 구조 (OLD)

```
runSafetySearch()
  ├─ searchKnowledgeCenter()  → MKT_API_BASE (Railway 직접)
  ├─ searchSafetyMaterials()  → materials.list() (Supabase 직접)
  ├─ searchGuides()           → listGuides() (KOSHA API 직접)
  ├─ searchAccidents()        → domestic + construction + CSI (3개 병렬)
  ├─ searchLawUpdates()       → sbQuery(law_revision_board) (Supabase 직접)
  ├─ searchPrecedents()       → precedents.list() (Supabase 직접)
  └─ searchKoshaSmart()       → DIRECT_BASE + '/public/safety-search/kosha'
```

### 목표 구조 (NEW)

```
runSafetySearch()
  ├─ callSharedSearch()   → DIRECT_BASE + '/public/safety-search'
  └─ searchKoshaSmart()   → DIRECT_BASE + '/public/safety-search/kosha' (그대로 유지)
```

### 새 Backend API Contract

```
GET DIRECT_BASE + '/public/safety-search'
params:
  q          required
  type       optional (guide|material|accident|chem|knowledge|precedent|law)
  page       default 1
  page_size  default 10, max 50  ← 항상 20 명시 전달

response:
  query, page, page_size, total, status, active_tiers
  items[]: { object_type, canonical_id, title, summary, public_url,
             source_id, source_key, source_updated_at,
             match_type, matched_on, matched_term,
             subject_type, subject_key, subject_match_type, rank_tier }
```

CHEM: `KOSHA_MSDS_PUBLIC_MODE=seo_preview` or `full`이면 backend가 포함, 아니면 자동 제외.  
503: `{"code":"SHARED_SEARCH_UNAVAILABLE"}` — 0건으로 위장 금지.

---

## 1. 수정 파일

```
MUST CHANGE:
  src/lib/server/safetySearch.js
  src/pages/safety-search.astro
  tests/wave2-safety-search.test.mjs

DO NOT TOUCH:
  src/lib/api.js          (DIRECT_BASE 정의, 변경 없음)
  src/lib/sb.js
  src/lib/modules/safety.js
  src/lib/server/koshaGuides.js
  src/lib/server/csiAccidents.js
  모든 SaaS/Paid/Matrix 파일
```

---

## 2. safetySearch.js 변경

### 삭제 — 함수

```
searchKnowledgeCenter()
searchSafetyMaterials()
searchGuides()
searchAccidents()
searchLawUpdates()
searchPrecedents()
sortInternalResults()
classifyMatch()
normMatchText()
unifiedResult()
presentGroups()
settleAdapter()
emptyGroup()
```

### 삭제 — import

```js
// 제거
import { materials, precedents, accidentsConstruction, accidentsDomestic } from '../modules/safety.js';
import { listGuides, verifiedCategoryLabel } from './koshaGuides.js';
import { listCsiAccidents } from './csiAccidents.js';
```

### 삭제 — 상수

```
MKT_API_BASE
MATCH_RANK
ALL_TOP_N
```

### 삭제 전 grep 확인

삭제하기 직전, 프로젝트 전체에서 아래 함수들이 `safetySearch.js`와 기존 테스트 외에 다른 consumer가 있는지 1회 확인.

```bash
rg "searchKnowledgeCenter|searchSafetyMaterials|searchGuides|searchAccidents|searchLawUpdates|searchPrecedents" --include="*.js" --include="*.astro" --include="*.ts"
```

다른 consumer 발견 시 삭제하지 말고 보고.

### 유지 (수정 없음)

```
SEARCH_CANONICAL / SEARCH_ROBOTS / SEARCH_SITE
MAX_Q_LENGTH / TYPE_PAGE_SIZE / KOSHA_PAGE_SIZE
normalizeQuery() / normalizeType() / normalizePage() / searchPageMeta()
stripTags() / truncateText() / safeHttpUrl()
FORBIDDEN_RESULT_KEYS
searchKoshaSmart()
normalizeKoshaProviderBody()
```

### 변경 — TYPE_ALLOWLIST

`kosha` 유지 (기존 URL 호환성):

```js
export const TYPE_ALLOWLIST = Object.freeze([
  'all',
  'guide',
  'material',
  'accident',
  'chem',
  'knowledge',
  'precedent',
  'law',
  'kosha',      // backward compat — external provider type
]);
```

### 변경 — GROUP_DEFS

```js
export const GROUP_DEFS = Object.freeze([
  { type: 'guide',     objectType: 'GUIDE',          label: '안전가이드' },
  { type: 'material',  objectType: 'SAFETY_MATERIAL', label: '안전자료'  },
  { type: 'accident',  objectType: 'CSI_ACCIDENT',    label: '재해사례'  },
  { type: 'chem',      objectType: 'CHEM',            label: 'MSDS'      },
  { type: 'knowledge', objectType: 'KNOWLEDGE',       label: '지식센터'  },
  { type: 'precedent', objectType: 'PRECEDENT',       label: '판례'      },
  { type: 'law',       objectType: 'LEGAL',           label: '법령'      },
  { type: 'kosha',     objectType: null,              label: 'KOSHA 공식검색' },
]);
```

### 추가 — callSharedSearch()

```js
export async function callSharedSearch(q, {
  type,
  page = 1,
  pageSize = TYPE_PAGE_SIZE,
  fetchFn = fetch,
} = {}) {
  const params = new URLSearchParams({
    q,
    page: String(page),
    page_size: String(pageSize),
  });
  if (type && type !== 'all') params.set('type', type);
  const url = DIRECT_BASE + '/public/safety-search?' + params.toString();
  const res = await fetchFn(url, { headers: { accept: 'application/json' } });
  if (res.status === 503) {
    return { status: 'unavailable', total: 0, items: [], page, page_size: pageSize };
  }
  if (!res.ok) throw new Error('SHARED_SEARCH_ERROR_' + res.status);
  const body = await res.json();
  // Legal guard: strip forbidden fields from every item
  const items = (body.items || []).map((it) => {
    const clean = { ...it };
    for (const key of FORBIDDEN_RESULT_KEYS) delete clean[key];
    return clean;
  });
  return {
    status: 'ok',
    total: Number(body.total) || 0,
    items,
    page: Number(body.page) || page,
    page_size: Number(body.page_size) || pageSize,
    active_tiers: body.active_tiers || [],
  };
}
```

### 변경 — runSafetySearch()

Dependency injection 유지 (테스트용). `adapters.shared` / `adapters.kosha`만.

```js
export async function runSafetySearch({
  q,
  type = 'all',
  page = 1,
  adapters = {},
} = {}) {
  const query = normalizeQuery(q);
  const normalizedType = normalizeType(type);
  const pageN = normalizePage(page);

  const impl = {
    shared: callSharedSearch,
    kosha: searchKoshaSmart,
    ...adapters,
  };

  if (!query) {
    return {
      query: '',
      type: normalizedType,
      page: pageN,
      landing: true,
      status: 'ok',
      items: [],
      total: 0,
      page_size: TYPE_PAGE_SIZE,
      kosha: null,
    };
  }

  // type=kosha → KOSHA external only, no Shared Search call
  const wantShared = normalizedType !== 'kosha';
  // KOSHA only in 'all' or 'kosha' mode
  const wantKosha = normalizedType === 'all' || normalizedType === 'kosha';

  let sharedResult = { status: 'ok', total: 0, items: [], page: pageN, page_size: TYPE_PAGE_SIZE };
  if (wantShared) {
    try {
      sharedResult = await impl.shared(query, {
        type: normalizedType,
        page: pageN,
        pageSize: TYPE_PAGE_SIZE,
      });
    } catch {
      sharedResult = { status: 'unavailable', total: 0, items: [], page: pageN, page_size: TYPE_PAGE_SIZE };
    }
  }

  let koshaSResult = null;
  if (wantKosha) {
    try {
      koshaSResult = await impl.kosha(query, { page: pageN, pageSize: KOSHA_PAGE_SIZE });
    } catch {
      koshaSResult = { status: 'unavailable', total: 0, items: [] };
    }
  }

  return {
    query,
    type: normalizedType,
    page: sharedResult.page,
    landing: false,
    status: sharedResult.status,
    items: sharedResult.items,
    total: sharedResult.total,
    page_size: sharedResult.page_size,
    active_tiers: sharedResult.active_tiers || [],
    kosha: koshaSResult,
  };
}
```

---

## 3. safety-search.astro 변경

### import 변경

```js
import {
  GROUP_DEFS,
  SEARCH_CANONICAL,
  SEARCH_ROBOTS,
  runSafetySearch,
} from '../lib/server/safetySearch.js';
```

### frontmatter 추가 — OBJECT_TYPE_LABEL, 페이지네이션

```js
const OBJECT_TYPE_LABEL = {
  GUIDE:           '안전가이드',
  SAFETY_MATERIAL: '안전자료',
  CSI_ACCIDENT:    '재해사례',
  CHEM:            'MSDS',
  KNOWLEDGE:       '지식센터',
  PRECEDENT:       '판례',
  LEGAL:           '법령',
};

const currentPage = result.page;
const pageSize    = result.page_size;
const totalPages  = result.total > 0 ? Math.ceil(result.total / pageSize) : 0;
const hasMore     = currentPage < totalPages;
const hasPrev     = currentPage > 1;
```

raw URL `page` 문자열을 직접 사용하지 않는다. 항상 `result.page` 기준.

### hrefFor() 변경

```js
function hrefFor(next = {}) {
  const sp = new URLSearchParams();
  const nq = next.q  !== undefined ? next.q  : result.query;
  const nt = next.type !== undefined ? next.type : result.type;
  const np = next.page !== undefined ? next.page : result.page;
  if (nq) sp.set('q', nq);
  if (nt && nt !== 'all') sp.set('type', nt);
  if (np && Number(np) > 1) sp.set('page', String(np));
  const s = sp.toString();
  return s ? '/safety-search?' + s : '/safety-search';
}
```

### 타입 필터 탭 — GROUP_DEFS 유지

```html
<nav class="ss-tabs" aria-label="출처 필터">
  <a class:list={['ss-tab', { active: result.type === 'all' }]}
     href={hrefFor({ type: 'all', page: 1 })}>전체</a>
  {GROUP_DEFS.map((d) => (
    <a class:list={['ss-tab', { active: result.type === d.type }]}
       href={hrefFor({ type: d.type, page: 1 })}>{d.label}</a>
  ))}
</nav>
```

### 결과 영역 — 기존 groups 렌더링 완전 교체

```html
{/* 1. 서비스 불가 */}
{!result.landing && result.status === 'unavailable' && (
  <div class="ss-error">
    검색 서비스를 일시적으로 이용할 수 없습니다. 잠시 후 다시 검색해 주세요.
  </div>
)}

{/* 2. 결과 없음 */}
{!result.landing && result.status === 'ok' && result.items.length === 0
  && result.type !== 'kosha' && (
  <p class="ss-empty">
    '<strong>{result.query}</strong>'에 대한 결과가 없습니다. 다른 검색어를 사용해 보세요.
  </p>
)}

{/* 3. 통합 ranked list */}
{result.status === 'ok' && result.items.length > 0 && (
  <>
    <div class="ss-total">총 {result.total.toLocaleString()}건 · {currentPage}페이지</div>
    <div class="ss-list">
      {result.items.map((item) => {
        const label   = OBJECT_TYPE_LABEL[item.object_type] || item.object_type;
        const dateStr = item.source_updated_at ? item.source_updated_at.slice(0, 10) : null;
        return item.public_url ? (
          <a class="ss-item" href={item.public_url}>
            <span class="ss-badge">{label}</span>
            <div class="ss-title">{item.title || '(제목 없음)'}</div>
            {item.summary && <div class="ss-sum">{item.summary}</div>}
            {dateStr && <div class="ss-meta">{dateStr}</div>}
          </a>
        ) : (
          <div class="ss-item">
            <span class="ss-badge">{label}</span>
            <div class="ss-title">{item.title || '(제목 없음)'}</div>
            {item.summary && <div class="ss-sum">{item.summary}</div>}
            {dateStr && <div class="ss-meta">{dateStr}</div>}
          </div>
        );
      })}
    </div>
  </>
)}

{/* 4. 페이지네이션 */}
{!result.landing && (hasPrev || hasMore) && (
  <div class="ss-pager">
    {hasPrev && <a class="ss-more" href={hrefFor({ page: currentPage - 1 })}>이전</a>}
    {hasMore && <a class="ss-more" href={hrefFor({ page: currentPage + 1 })}>다음 {pageSize}개</a>}
  </div>
)}

{/* 5. KOSHA 별도 섹션 */}
{result.kosha && (
  <section class="ss-group" data-source="kosha">
    <h2>KOSHA 공식검색</h2>
    {result.kosha.status === 'unavailable' ? (
      <p class="ss-empty">KOSHA 공식검색을 현재 이용할 수 없습니다.</p>
    ) : result.kosha.items.length === 0 ? (
      <p class="ss-empty">KOSHA에서 검색된 결과가 없습니다.</p>
    ) : (
      result.kosha.items.map((it) => {
        const href = it.source_url || it.original_url || null;
        return href ? (
          <a class="ss-item" href={href} target="_blank" rel="noopener noreferrer">
            <span class="ss-badge">KOSHA</span>
            <div class="ss-title">{it.title || '(제목 없음)'}</div>
            {it.summary && <div class="ss-sum">{it.summary}</div>}
          </a>
        ) : (
          <div class="ss-item">
            <span class="ss-badge">KOSHA</span>
            <div class="ss-title">{it.title || '(제목 없음)'}</div>
            {it.summary && <div class="ss-sum">{it.summary}</div>}
          </div>
        );
      })
    )}
  </section>
)}
```

**주의:**
- `rank_tier` / `opensearch_score` / raw `match_type` UI 노출 금지
- `public_url=null` 항목을 숨기지 않는다 — `<div>`로 렌더
- HTTP 503 → 에러 메시지. 0건으로 위장 금지

---

## 4. 테스트 변경 (wave2-safety-search.test.mjs)

기존 6개 adapter mock 제거. `adapters.shared` / `adapters.kosha` 2개 주입 패턴으로 재작성.  
`TEST NETWORK CALL = 0`.

### 최소 필수 케이스

```
T-01  landing state
      q='' → { landing:true, items:[], kosha:null }

T-02  정상 검색 (type='all')
      adapters.shared 호출됨 (type=undefined or 'all')
      adapters.kosha 호출됨
      result.items = shared items
      result.kosha = kosha result

T-03  type 필터 (type='guide')
      adapters.shared 호출됨 (type='guide')
      adapters.kosha 호출 안 됨
      result.kosha = null

T-04  type=kosha
      adapters.shared 호출 안 됨
      adapters.kosha 호출됨
      result.items = []
      result.kosha = kosha result
      (backward compat)

T-05  Shared Search 503
      adapters.shared → status='unavailable'
      result.status = 'unavailable'
      result.items = []
      (0건으로 표현 안 됨)

T-06  KOSHA 실패
      adapters.shared 정상
      adapters.kosha 실패(throw)
      result.kosha.status = 'unavailable'
      result.items 정상 유지

T-07  FORBIDDEN_RESULT_KEYS strip
      item에 legal_applicable 포함 → result.items[0]에 없음

T-08  pagination (result.page 기준)
      adapters.shared → { page:2, total:50, page_size:20, items:[...] }
      result.page = 2
      result.page_size = 20
      Math.ceil(50/20) = 3 → hasMore = (2 < 3) = true

T-09  page_size=20 전달
      callSharedSearch 호출 시 page_size=20 확인
```

기존 테스트 중 `groups`, `GROUP_DEFS.length`, `sortInternalResults`, `classifyMatch` 검증 → 삭제.

---

## 5. 금지

```
within 파라미터 구현
상세 route 신규 생성
/safety-guide, /accident/csi 기존 route 변경
analytics event 추가
append형 load-more JS 구현 (WO-03 대상)
SaaS/Paid/CHEM hydration/RISK 작업
CSS framework 교체
KOSHA items을 TAI items에 합치는 것
public_url=null 항목을 결과에서 숨기는 것
```

---

## 6. PR 기준

```
Branch: feat/wo-mkt-search-01-shared-search-cutover
Base:   main (eaf55c74)
Files:  safetySearch.js + safety-search.astro + wave2-safety-search.test.mjs
Tests:  npm test PASS
```

---

## 7. 완료 기준 (Acceptance)

```
T01~T09 전체 PASS
지게차 검색 → items[] 있음 (Shared Search 단일 호출)
type=accident → kosha null (KOSHA 호출 0)
type=kosha    → items=[] / kosha 결과 있음
Shared 503    → 에러 메시지 표시 (0건 아님)
callSharedSearch에 page_size=20 전달 확인
public_url=null item → div로 렌더 (결과 숨김 없음)
legal_applicable 등 forbidden keys = 0
수정 파일 = 정확히 3개
```

완료 후:

```
STOP
PR 생성 후 HEAD + test evidence 반환
자체 merge 금지
```

---

## 8. 이번 WO 이후

```
WO-MKT-SEARCH-02   within search backend + front    → OBJ-03
WO-MKT-SEARCH-03   append load-more JS              → OBJ-04
WO-MKT-SEARCH-04A  public detail resolver audit     → OBJ-05 (해당 Domain만 조사)
WO-MKT-SEARCH-04B  missing canonical detail         → OBJ-05
WO-MKT-SEARCH-05   E2E / analytics / closeout       → OBJ-06
```
