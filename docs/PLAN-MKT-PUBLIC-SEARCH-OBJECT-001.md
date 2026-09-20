---
class: plans
type: WORKPLAN
scope: marketing-public-search
project: tai-www
title: TAI Marketing Public Search — Object-based Implementation Plan
version: 1
status: ACTIVE
owner: taiwang
---

# TAI Marketing Public Search — Object-based Implementation Plan v1

* **문서 ID:** `PLAN-MKT-PUBLIC-SEARCH-OBJECT-001`
* **상위 Object:** `OBJ-DISCOVERY`
* **대상:** `taieng.co.kr` 마케팅 사이트
* **Frontend Repo:** `taiengineering/tai-www`
* **Backend Repo:** `taiengineering/tai-api`
* **tai-www 기준 anchor:** `eaf55c74bf4f837b7cc13fa06b0b3adaaa766fa4`
* **Backend:** Shared Search / OpenSearch production ACTIVE
* **성격:** 마케팅 Public Search의 검색→축소→탐색→상세보기 흐름을 Object 단위로 완결하는 하위 실행계획

---

## 0. 문서 지위

기존 Safety Knowledge Object Plan의 `OBJ-DISCOVERY = 통합검색 / 스마트검색` 을 새 Object로 대체하지 않는다.

이번 문서는 `OBJ-DISCOVERY` 의 **하위 Object 구현계획**이다.

```
기존 Top-level Object count = 13
변경 = 0
```

SaaS와 Paid Diagnosis는 이번 계획에 포함하지 않는다.

---

## 1. 이번 계획의 목적

마케팅 사이트 사용자는 사업장 Context가 없다.

> 안전관리자가 필요한 안전정보를 빠르게 발견하고, 결과를 좁히고, 상세 근거까지 확인하게 하는 것.

전체 사용자 흐름:

```
검색창 → 통합 검색결과 → 정보유형 필터 → 결과 내 검색 → 더보기 → 상세보기
```

---

## 2. 범위

### IN SCOPE

검색창 / 추천 검색어 / 통합 결과목록 / 정보유형 필터 / 결과 내 검색 / 더보기 /
KOSHA 외부검색 표시 / 상세보기 / 검색 URL 상태 / 오류/빈 결과 /
Analytics / 모바일 대응 / Public E2E

### OUT OF SCOPE

SaaS Context Search / Paid Diagnosis matching / 회사/사업장/시설 Context /
공정/설비/작업 자동매칭 / 법령의무 Context retrieval / Knowledge Graph 확장 /
RISK 활성화 / CHEM hydration / 법령 적용여부 판정 / LLM ranking

후자는 별도 Object Plan으로 진행한다.

---

## 3. Object 원칙

각 Object는 반드시 다음을 가진다:

```
OBJECT ID / PURPOSE / SCOPE / INPUT / OUTPUT / PUBLIC CONTRACT /
SOURCE OF TRUTH / CONSUMERS / DEPENDENCIES / STATE / MUTATION /
HARD BLOCK / EXIT CRITERIA / EVIDENCE / OWNER
```

상태:

```
PLANNED / READY / IN_PROGRESS / BLOCKED / DONE / DEFERRED
```

---

## 4. Object Map

```
                     OBJ-DISCOVERY
                           │
                           ▼
              OBJ-MKT-SEARCH-00
               Public Search Contract
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
   OBJ-MKT-SEARCH-01          OBJ-MKT-SEARCH-02
      Search Entry              Result Surface
                                      │
                           ┌──────────┴──────────┐
                           │                     │
                           ▼                     ▼
                OBJ-MKT-SEARCH-03      OBJ-MKT-SEARCH-04
                  Result Narrowing       Result Continuation
                           │                     │
                           └──────────┬──────────┘
                                      ▼
                           OBJ-MKT-SEARCH-05
                            Canonical Detail
                                      │
                                      ▼
                           OBJ-MKT-SEARCH-06
                          Public Search Closeout
```

---

## 5. Architecture

```
User
  ↓
tai-www /safety-search
  ↓
Public Search Consumer
  ↓
tai-api /public/safety-search
  ↓
Shared Retrieval Engine
  ↓
OpenSearch
```

KOSHA는 별도 Provider:

```
tai-www
  ├─ Shared Search (TAI internal)
  └─ KOSHA Smart Search (external provider)
```

KOSHA external result → TAI canonical object로 저장/위장 금지.

---

## 6. OBJ-MKT-SEARCH-00 — Public Search Contract

```
OBJECT ID:        OBJ-MKT-SEARCH-00
PURPOSE:          마케팅 Public Search 전체의 공통 검색/상태/라우팅 계약 고정
SCOPE:            query, type, within, page, result routing
SOURCE OF TRUTH:  tai-api Shared Search API
CONSUMERS:        OBJ-MKT-SEARCH-01~06
DEPENDENCIES:     Shared Search production ACTIVE
STATE:            READY
MUTATION:         Contract only. Search Engine 재설계 금지.
HARD BLOCK:
  - Shared Search ranking을 프론트에서 재구현
  - 법적 applicability 추가
  - KOSHA canonical merge
EXIT CRITERIA:
  q/type/within/page 역할이 고정되고
  하위 Object가 동일 계약을 사용한다.
```

### Public 상태 계약

| 파라미터 | 역할 |
|---|---|
| `q` | 기본 검색어 (ranking authority) |
| `type` | 정보유형 filter |
| `within` | 현재 결과 안에서 추가 narrowing |
| `page` | continuation state |

---

## 7. OBJ-MKT-SEARCH-01 — Search Entry

```
OBJECT ID:        OBJ-MKT-SEARCH-01
PURPOSE:          안전관리자가 어떤 페이지에서도 쉽게 Public Search에 진입
SCOPE:            검색창 / 검색 submit / 추천 검색어 / landing state
INPUT:            사용자 텍스트
OUTPUT:           canonical search URL
PUBLIC CONTRACT:  search(q) → /safety-search?q={q}
SOURCE OF TRUTH:  URL query parameter q
CONSUMERS:        마케팅 사이트 방문자
DEPENDENCIES:     OBJ-MKT-SEARCH-00
STATE:            IN_PROGRESS
```

현재 `/safety-search`에 검색폼은 존재하므로 신규 Object가 아니라 기존 구현을 완성한다.

### UI

```
필요한 안전정보를 한 번에 찾아보세요

┌──────────────────────────────────────────┐
│ 지게차, 밀폐공간, 추락, MSDS 등 검색  🔍 │
└──────────────────────────────────────────┘

많이 찾는 안전정보
[지게차] [밀폐공간] [추락] [MSDS] [위험성평가]
[안전난간] [작업발판] [이동식크레인]
```

### 하지 않는 것

개인화 추천 / 사업장 추천 / AI 자동완성 / LLM 검색어 생성

### EXIT CRITERIA

검색 submit 정상 / URL 공유 가능 / 새로고침 동일상태 / 추천어 클릭 검색 /
모바일 정상 / blank query 안전처리

---

## 8. OBJ-MKT-SEARCH-02 — Unified Result Surface

```
OBJECT ID:        OBJ-MKT-SEARCH-02
PURPOSE:          모든 TAI 내부 Knowledge를 하나의 relevance-ranked 결과목록으로 제공
SCOPE:            검색결과 페이지 / ResultCard / type filtering / KOSHA external block
INPUT:            Shared Search SearchResult[]
OUTPUT:           통합 결과목록
PUBLIC CONTRACT:  render(results, type)
SOURCE OF TRUTH:  tai-api /public/safety-search ordering
CONSUMERS:        Public Search Result Page
DEPENDENCIES:     OBJ-MKT-SEARCH-00, OBJ-MKT-SEARCH-01
STATE:            IN_PROGRESS
```

기존 그룹별(지식센터/안전자료/안전가이드/재해사례...) 결과 구조 →
**Shared Search 통합 ranking 순서 단일 목록**으로 변경.

### Backend object_type → Public label

| Backend | Public |
|---|---|
| `GUIDE` | 안전가이드 |
| `SAFETY_MATERIAL` | 안전자료 |
| `CSI_ACCIDENT` | 재해사례 |
| `CHEM` | MSDS |
| `KNOWLEDGE` | 지식/서비스안내 |
| `PRECEDENT` | 판례 |
| `LEGAL` | 법령 |

### ResultCard Contract

```
[정보유형] [출처]

제목

요약

검색어와의 관계 (예: 관련 주제: 지게차)

업데이트일

[상세보기 >]
```

내부값 노출 금지: `rank_tier` / `opensearch_score` / `BM25_NORI` / `DICTIONARY_EXACT` / `score=87.33`

### Type Filter

상단 chip 사용. **API authority 사용. 프론트 local filtering 금지.**
(전체 result의 일부만 받아놓고 클라이언트에서 filtering하면 total/pagination 오류 발생)

### KOSHA

TAI internal results 이후 별도 External Provider 영역으로 분리.
KOSHA 장애 시 TAI 결과 정상 유지.

---

## 9. OBJ-MKT-SEARCH-03 — Result Narrowing

```
OBJECT ID:        OBJ-MKT-SEARCH-03
PURPOSE:          안전관리자가 추가 키워드로 결과를 좁힐 수 있게 한다
SCOPE:            within input / AND narrowing / URL state
INPUT:            q + within
OUTPUT:           기본 검색결과의 subset
PUBLIC CONTRACT:  search(q, within)
SOURCE OF TRUTH:  Shared Search backend
CONSUMERS:        OBJ-MKT-SEARCH-02
DEPENDENCIES:     OBJ-MKT-SEARCH-00, Shared Search within extension
STATE:            PLANNED
HARD BLOCK:       프론트가 q와 within을 문자열 단순 합쳐서 가짜 AND를 만드는 것
```

### URL Contract

```
/safety-search?q=지게차&within=충돌
/safety-search?q=지게차&type=accident&within=충돌
```

### UI

```
'지게차' 검색결과

[ 결과 내 검색: 충돌                  ]

검색조건
[지게차] + [충돌 ×]
```

`충돌 ×` 제거 → `/safety-search?q=지게차` 복귀.

### Backend GAP

현재 Public API에 `within` 없음. **이 Object에서만 Backend 변경 필요.**

```
q      = ranking authority
within = additional MUST narrowing
```

Search Engine 복제 금지. OpenSearch common Reader/Query 확장만 허용.

---

## 10. OBJ-MKT-SEARCH-04 — Result Continuation

```
OBJECT ID:        OBJ-MKT-SEARCH-04
PURPOSE:          사용자가 현재 검색맥락을 잃지 않고 결과를 계속 탐색
SCOPE:            20건 단위 continuation / append / loading / retry
INPUT:            q / type / within / page
OUTPUT:           next result batch
PUBLIC CONTRACT:  loadNext(page + 1)
SOURCE OF TRUTH:  Shared Search page/page_size
CONSUMERS:        OBJ-MKT-SEARCH-02
DEPENDENCIES:     OBJ-MKT-SEARCH-02, OBJ-MKT-SEARCH-03 when within active
STATE:            IN_PROGRESS
```

**page_size = 20.** 무한스크롤 사용하지 않음. **Explicit [20개 더보기] 버튼.**

이유: 현장 모바일 사용성 / 현재 위치 인지 / API 호출 방지 / 접근성 / 오류 복구

```
1~20 / 248

[20개 더보기]
```

### Progressive Enhancement

JS 정상 → append. JS 실패 → `?page=2` 일반 링크. 뒤로가기 시 q/type/within 유지.

---

## 11. OBJ-MKT-SEARCH-05 — Canonical Public Detail

```
OBJECT ID:        OBJ-MKT-SEARCH-05
PURPOSE:          검색결과에서 각 Domain의 canonical 상세정보로 안전하게 이동
SCOPE:            public_url resolution / Domain detail route / source provenance
INPUT:            object_type + canonical_id
OUTPUT:           canonical Public Detail
PUBLIC CONTRACT:  resolve(object_type, canonical_id) → public_url
SOURCE OF TRUTH:  각 Domain SoT + Domain Adapter
CONSUMERS:        SearchResultCard, Public/Search 유입
DEPENDENCIES:     각 Domain canonical identity
STATE:            IN_PROGRESS
```

핵심 원칙: **Search = discovery, Detail = Domain authority.**
검색 DB에 상세본문 별도 복제 금지.

### Public Detail 현재 Matrix

| Object | 현재 Public Route | 상태 |
|---|---|---|
| GUIDE | `/safety-guide/{id}` | READY |
| CSI_ACCIDENT | `/accident/csi/{uuid}` | READY |
| SAFETY_MATERIAL | 검증된 canonical route 없음 | GAP |
| CHEM | HTML canonical route 없음 | GAP |
| KNOWLEDGE | 검증된 Public route 없음 | GAP |
| PRECEDENT | 기존 route는 legacy source | GAP |
| LEGAL | current law_article와 검증된 route 없음 | GAP |

**2 READY / 5 GAP**

### Detail 구현 원칙

- `/safety-search/detail?id=...` 단일 generic route **금지**
- Domain별 canonical route: `/safety-guide/{id}` / `/msds/{id}` / `/law/{id}` 등
- **실제 route는 Domain canonical identity 실측 후 확정. 추측 생성 금지.**

### Detail 공통 화면 Contract

```
[정보유형] [출처]

제목

요약 / 설명

─────────────────

본문 / 상세데이터

─────────────────

공식 출처
최종 업데이트
원문 링크

─────────────────

관련 안전정보 (자리 확보, 이번에 강제 구현 안 함)
```

### LEGAL Guard

Public Search가 법적 applicability 판정 금지.
고지: "검색된 법령정보는 정보 탐색용이며 개별 사업장의 적용 여부를 판정하지 않습니다."
CTA: 진단 제품으로 연결 가능.

### CHEM Guard

상세보기 때문에 외부 API 호출 / 새 hydration / 새 snapshot / 추가 materialization 실행 금지.
기존 PUBLISHED CHEM만 표시. `SEARCH DETAIL ≠ CHEM COLLECTION`

---

## 12. OBJ-MKT-SEARCH-06 — Public Search Operations & Closeout

```
OBJECT ID:        OBJ-MKT-SEARCH-06
PURPOSE:          Public Search 전체가 실제 사용자 흐름에서 안정적으로 동작함을 검증
SCOPE:            E2E / analytics / mobile / error states / production audit
INPUT:            OBJ-MKT-SEARCH-01~05
OUTPUT:           VERIFIED Public Search
SOURCE OF TRUTH:  production tai-www + tai-api
CONSUMERS:        운영자 / 제품 담당자
DEPENDENCIES:     OBJ-MKT-SEARCH-01~05
STATE:            PLANNED
MUTATION:         QA/analytics only. Search ranking 변경 금지.
EXIT CRITERIA:
  대표검색 E2E + detail + loadmore + within + mobile + failure isolation PASS
```

### Analytics Contract

최소 이벤트:

```
public_search_submit
public_search_type_filter
public_search_within_submit
public_search_load_more
public_search_result_click
public_search_external_click
public_search_diagnosis_cta
```

공통 필드: `q` / `type` / `within` / `object_type` / `position` / `canonical_id`
(개인정보 저장 금지)

### Error Objects

**Empty Result:** 빈 결과를 장애로 표현 금지. 다른 검색어 안내.

**Shared Search Failure:**
"검색 서비스를 일시적으로 이용할 수 없습니다. 잠시 후 다시 검색해 주세요."
HTTP 503을 0건으로 위장 금지.

**KOSHA Failure:** TAI internal results 정상 유지. KOSHA 영역만 unavailable.

---

## 13. Dependency Graph

```
Shared Search Production
          │
          ▼
OBJ-MKT-SEARCH-00
          │
     ┌────┴────┐
     ▼         ▼
   01 Entry   02 Result
                │
          ┌─────┴─────┐
          ▼           ▼
       03 Narrow    04 More
          │           │
          └─────┬─────┘
                ▼
          05 Detail
                │
                ▼
          06 Closeout
```

---

## 14. Implementation WAVE

| Wave | Objects | 결과 |
|---|---|---|
| M0 | OBJ-MKT-SEARCH-00 | 검색 상태 계약 고정 |
| M1 | OBJ-MKT-SEARCH-01, 02 (병렬) | Shared Search single consumer + unified results |
| M2 | OBJ-MKT-SEARCH-03, 04 | 결과내검색 + 더보기 |
| M3 | OBJ-MKT-SEARCH-05 | 모든 Public Search Result → canonical detail |
| M4 | OBJ-MKT-SEARCH-06 | Marketing Public Search DONE |

---

## 15. Work Order Sequence

```
WO-MKT-SEARCH-00   Current State & Contract Freeze
WO-MKT-SEARCH-01   Public Shared Search Cutover          → OBJ-01 + OBJ-02
WO-MKT-SEARCH-02   Within Search Backend + Front         → OBJ-03
WO-MKT-SEARCH-03   Explicit Load More                    → OBJ-04
WO-MKT-SEARCH-04A  Public Detail Resolver Audit          → OBJ-05
WO-MKT-SEARCH-04B  Missing Canonical Detail Completion   → OBJ-05
WO-MKT-SEARCH-05   Production E2E / Analytics / Closeout → OBJ-06
```

---

## 16. 중요한 구현 원칙

**하나의 Search Engine**
Public Search 전용 검색엔진 생성 = 금지. 반드시 Shared Search를 소비.

**하나의 ResultCard**
정보유형마다 Card 새로 만들지 않음. 공통 `SearchResultCard`, Domain 차이는 metadata로.

**Detail은 공통화하지 않는다**
Result UI = 공통화 / Detail Business = Domain별 Authority 유지.

---

## 17. Object Registry

| Object | State | 현재 근거 | 완료 시 |
|---|---|---|---|
| OBJ-MKT-SEARCH-00 Contract | READY | Shared Search contract/backend 고정 | DONE |
| OBJ-MKT-SEARCH-01 Entry | IN_PROGRESS | 기존 검색폼 존재 | 검색 진입 계약 완료 |
| OBJ-MKT-SEARCH-02 Result | IN_PROGRESS | 기존 그룹형 검색 결과 존재 | Shared ranking 전환 |
| OBJ-MKT-SEARCH-03 Narrow | PLANNED | `within` API 없음 | AND narrowing 동작 |
| OBJ-MKT-SEARCH-04 More | IN_PROGRESS | pagination 존재, load-more 없음 | append continuation |
| OBJ-MKT-SEARCH-05 Detail | IN_PROGRESS | 2/7 canonical route 검증 | Public 결과 전량 상세 진입 |
| OBJ-MKT-SEARCH-06 Closeout | PLANNED | 선행 Object 필요 | production E2E PASS |

---

## 18. Object별 DONE 판정

### OBJ-01
검색창 PASS / 추천어 PASS / URL state PASS / mobile PASS

### OBJ-02
Shared Search single call PASS / 통합 ranking PASS / type filter PASS /
ResultCard PASS / KOSHA isolation PASS

### OBJ-03
q + within AND PASS / type + within PASS / URL persistence PASS / within 제거 복귀 PASS

### OBJ-04
20개 initial PASS / 20개 append PASS / 중복 0 / 순서 보존 / 마지막 page 종료

### OBJ-05
GUIDE / CSI / MATERIAL / CHEM / KNOWLEDGE / PRECEDENT / LEGAL detail 전체 PASS.
wrong-domain resolver = 0. fabricated public_url = 0.

### OBJ-06
Production E2E PASS / Mobile PASS / Analytics PASS / Failure isolation PASS /
Legal authority guard PASS

---

## 19. 대표 E2E 검색어

최소:
```
지게차 / 밀폐공간 / 추락 / MSDS / 산업안전보건법 / 안전난간
```

identifier 검색도 포함 (CAS 번호, Guide 번호) — 실제 데이터가 존재하는 identifier만 사용.

### E2E Scenario

```
1. /safety-search 진입
2. 지게차 검색
3. 전체 result 확인
4. 재해사례 filter
5. 결과 내 검색 "충돌"
6. 결과 count 감소 확인
7. 더보기
8. 상세보기
9. 뒤로가기
10. q/type/within 상태 유지
```

모바일에서도 동일 흐름 PASS.

---

## 20. Git Governance

```
GPT    Object 설계 / WO / 독립검증 / Exit 판정
Cursor repo 조사 / 구현 / 테스트 / 증거수집 / PR
User   Owner Approval
```

```
1 PR = 1 WRITE window
현재 GitHub HEAD wins
merge 전 exact HEAD 재검증
production deploy ≠ production acceptance
```

### 권장 PR 경계

```
PR-A  Shared Search cutover + unified results
PR-B  within search
PR-C  load-more
PR-D  canonical detail completion
PR-E  final UX / analytics / E2E fixes
```

---

## 21. Hard Block

```
Shared Search ranking을 프론트에서 재구현
법령검색 결과를 사업장 적용판정처럼 표시
KOSHA external result를 TAI canonical로 저장
잘못된 canonical_id로 상세페이지 연결
PRECEDENT legacy detail을 IAP result에 잘못 연결
CHEM 상세 때문에 hydration 실행
Public URL 추측 생성
production search 장애를 0건으로 표시
```

---

## 22. DO NOT

```
새 Public 검색엔진
새 검색 DB
새 Kiwi / 새 Search Dictionary
LLM ranking / LLM match explanation
정보유형별 별도 검색 구현
프론트 local filter로 backend total 위조
자동 무한스크롤
모든 Domain을 generic detail 하나로 통합
SaaS 기능 끼워 넣기
Paid Diagnosis 기능 끼워 넣기
Matrix/Graph 확장 끼워 넣기
```

---

## 23. 전체 Exit Criteria

```
SEARCH ENTRY  안전관리자가 검색어로 바로 진입
RESULT        Shared Search 통합 ranking으로 표시
FILTER        정보유형별 narrowing 가능
WITHIN        현재 결과 안에서 추가검색 가능
MORE          20개 단위로 계속 탐색 가능
DETAIL        모든 internal canonical 결과 → 올바른 상세로 연결
EXTERNAL      KOSHA 결과는 별도 provider로 표시
MOBILE        현장 모바일 탐색 가능
FAILURE       빈결과/장애/KOSHA 장애 분리
LEGAL         법적 적용판정 오염 0
```

전체가 production에서 검증됐을 때:
**`OBJ-DISCOVERY > Marketing Public Search sub-scope = DONE`**

---

## 24. 이번 계획 이후 별도 계획

이번 Object Plan 종료 후 별도로:

```
PLAN-PAID-CONTEXT-KNOWLEDGE
유료진단 결과 → Matrix → 관련정보

PLAN-SAAS-CONTEXT-KNOWLEDGE
시설/공정/작업/설비/의무/점검 → Matrix → Shared Search → 관련정보
```

둘을 이번 Public Search에 섞지 않는다.

---

## 25. 현재 다음 작업

첫 실행 WO: **WO-MKT-SEARCH-00 — Current State & Contract Freeze**

목적 (구현 아님, 실측만):

```
현재 tai-www /safety-search 실측
기존 6개 직접조회 path 확정
Shared Search response 실제 contract 재확인
KOSHA external path 확인
기존 CSS/JS/test 영향범위 확정
상세 route 7종 실측 matrix 확정
```

그 결과가 고정되면 **WO-MKT-SEARCH-01 Public Shared Search Cutover** 구현 시작.

---

## 최종 구조

```
                    OBJ-DISCOVERY
                          │
                  MARKETING PUBLIC
                          │
             ┌────────────┴────────────┐
             │                         │
         Search Entry              Result Surface
                                       │
                              ┌────────┴────────┐
                              │                 │
                        Result Narrow       Load More
                              │                 │
                              └────────┬────────┘
                                       │
                                Canonical Detail
                                       │
                                       ▼
                              Production Closeout
```

**검색엔진은 하나, Public Consumer도 하나, Result UI는 공통, 상세 Authority는 각 Domain에 남긴다.**
