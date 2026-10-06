# TAI 통합검색 결정 기준선 v1

> 문서 ID: TAI-INTEGRATED-SEARCH-DECISION-BASELINE-v1  
> 기준일: 2026-10-07  
> 상태: DECISION BASELINE  
> 성격: 지금까지의 통합검색 논의·결정사항 고정 문서  
> 구현 승인: 별도 Object/WO 필요  
> Production mutation: 없음

---

## 0. 문서 목적

이 문서는 TAI 통합검색을 "검색 기능 하나"가 아니라 TAI 전체 사업 안에서 어떤 역할을 맡는지 고정한다.

이 기준선의 목적은 다음과 같다.

1. 통합검색을 별도 커뮤니티/포털 사업으로 확장하지 않는다.
2. 검색 자체의 트래픽이 아니라 TAI Safe, 법령진단, 화학물질관리, SI로 연결되는 사업적 가치를 기준으로 개발한다.
3. 이미 존재하는 검색·법령·화학·문서 자산을 중복 개발하지 않는다.
4. 구조화검색, 검색 DB 분리, 공공 API 수집, 사용자 검색어 학습, SEO, 문서서비스를 하나의 방향으로 묶는다.
5. 검색과 법적 판단의 경계를 유지한다.

---

# 1. 문제 정의

## 1.1 일반 검색엔진의 문제

네이버·Google 등 범용 검색엔진은 정보의 양이 매우 많다.

안전관리자는 검색 결과에서 다음을 다시 판단해야 한다.

- 공식 자료인지
- 광고/홍보성 자료인지
- 오래된 자료인지
- 현재 법령과 맞는지
- 어느 기관 자료를 봐야 하는지
- 사고사례인지 가이드인지 법령인지
- 실제 업무에 바로 쓸 수 있는 자료인지

따라서 문제는 "자료가 없다"가 아니라 **정확히 필요한 공신력 있는 자료까지 가는 탐색비용이 크다**는 것이다.

## 1.2 공공기관 검색의 문제

공공기관 자료는 신뢰성이 높지만 기관별로 분절되어 있다.

안전관리 업무는 실제로 여러 기관·법체계를 가로지른다.

예:

- KOSHA
- 고용노동부
- 국가법령정보센터
- 한국환경공단
- 화학물질 관련 기관
- 전기·가스·소방·승강기 등 개별 안전기관

각 기관은 자기 소관 데이터를 제공하지만 사용자의 업무는 기관 경계를 따라 움직이지 않는다.

따라서 TAI의 기회는 **기관별 사일로를 사용자의 안전관리 주제 기준으로 다시 연결하는 것**이다.

## 1.3 범용 AI의 문제

범용 AI는 질문 이해·요약에는 강하다.

그러나 안전관리처럼 법규제와 책임이 연결된 영역에서는 사용자가 다음을 별도로 확인해야 한다.

- 실제 공식 근거
- 법령 조문
- 시행일/버전
- 적용 조건
- 원문
- 최신성
- 사업장 적용 여부

TAI는 AI와 "더 자연스러운 대화"로 경쟁하지 않는다.

TAI의 방향은 **공식 근거를 구조화해서 찾게 하고, 사업장 적용 판단이 필요한 경우 별도의 LEG 법령엔진으로 넘기는 것**이다.

---

# 2. 제품 정의

## 2.1 한 문장 정의

> **TAI Search는 안전관리만 좁고 깊게 찾고, 여러 공신력 있는 출처의 근거와 실무행동을 연결하는 TAI 공통 탐색 계층이다.**

## 2.2 하지 않는 것

TAI Search는 다음이 아니다.

- 커뮤니티
- 별도 미디어 사업
- 범용 웹검색
- ChatGPT형 대화형 검색
- AI가 법적 책임을 자유롭게 판단하는 서비스
- 자료 수 경쟁
- 원천 DB를 다시 만드는 중앙 SoT
- 등록된 키워드만 검색 가능한 폐쇄형 taxonomy 검색

## 2.3 사업 안에서의 역할

검색은 독립 매출 상품이 아니라 다음 Funnel의 앞단이다.

```
SEO / 직접방문 / 콘텐츠 상세
            ↓
       TAI Search
            ↓
   공식근거 + 관련 실무자료
            ↓
 ┌──────────┼───────────┐
 ↓          ↓           ↓
법령진단   TAI Safe   화학물질관리
                        ↓
                       SI
```

검색의 성공은 페이지뷰 자체보다 **TAI의 유료 업무로 자연스럽게 이동시키는가**로 평가한다.

---

# 3. 도메인 결정

## 3.1 확정

당장은 `search.taieng.co.kr`로 독립하지 않는다.

검색 UX는 `taieng.co.kr` 계열 안에 유지한다.

이유:

- Search가 별도 목적지가 되면 본 서비스로 다시 이동시키는 비용이 생긴다.
- 현재 목표는 검색서비스 독립사업이 아니라 TAI SaaS 전환이다.
- SEO 상세페이지 → Topic → Search → Product를 동일 서비스 경험 안에 두는 편이 유리하다.

## 3.2 프론트 원칙

"검색페이지를 하나 강화"하는 것이 아니라 **TAI 공개영역 전체를 검색 가능하게 한다.**

예:

- 홈페이지
- 안전정보
- KOSHA 자료
- 사고사례
- 법령
- MSDS/화학
- 판례
- Topic 상세

어디서든 동일한 안전검색 진입점을 제공한다.

상세페이지에는 역방향 탐색을 제공한다.

예:

```
지게차 사고사례 상세
  ↓
지게차 관련 정보 더 찾기
  - 법령
  - KOSHA Guide
  - 안전자료
  - 사고사례
  - 판례
  - 실무문서
```

---

# 4. 데이터 아키텍처 결정

## 4.1 Search DB 분리

통합검색의 검색 전용 DB는 별도 소유영역으로 분리한다.

논리명: `tai-search`

## 4.2 원천 SoT 유지

다음 원천은 기존 소유권을 유지한다.

- taeng 계열 운영/SaaS 데이터
- LEG 법령 SoT
- tai-chemical 화학물질 SoT
- 기타 공공 원천의 canonical 저장영역

Search DB는 이를 새 SoT로 복제하지 않는다.

Search DB가 소유할 수 있는 것은 다음과 같다.

- 검색 Projection
- 검색 Index 메타데이터
- Search Dictionary
- Canonical Topic Registry
- Query Log / Search Analytics
- Query Cluster
- Structure Candidate
- Knowledge Graph의 검색용 edge/projection
- sitemap/indexable 상태
- source freshness/authority metadata

## 4.3 핵심 원칙

> **Source ownership은 분리하고, Search experience는 통합한다.**

---

# 5. 검색 방식 결정

TAI 검색은 구조화검색 하나로 제한하지 않는다.

## 5.1 4단계 검색 흐름

```
QUERY
  │
  ├─ 1. Exact canonical match
  │      → Topic 중심 검색
  │
  ├─ 2. Alias / synonym / normalized match
  │      → Canonical 변환
  │
  ├─ 3. Partial concept detection
  │      → Query 내부의 구조화 가능한 개념만 활용
  │
  └─ 4. No canonical match
         → OpenSearch BM25/Nori 일반 전문검색
              ↓
           fuzzy fallback
```

## 5.2 핵심 원칙

> **모든 검색어는 검색 가능해야 한다. 구조화된 검색어는 더 정확하고 풍부하게 제공한다.**

구조화되지 않은 문장을 Topic Registry에 억지로 등록하지 않는다.

예:

`지게차 작업시 주의사항` 자체는 Topic이 아니다.

Query 안에서:

- 지게차
- 작업
- 주의/안전

등을 이해하면서 전체 문장 검색은 그대로 수행한다.

---

# 6. Canonical / Dictionary / Topic 역할

각 계층은 분리한다.

- **OpenSearch**: 무엇이든 찾는다.
- **Search Dictionary**: 검색어를 이해한다.
- **Canonical Topic Registry**: 반복 가치가 높은 안전관리 개념을 구조화한다.
- **Knowledge Graph**: 개념·자료·업무를 연결한다.

Canonical Registry에는 의미가 명확하고 재사용 가치가 높은 항목을 우선한다.

예:

- 지게차
- 크레인
- 밀폐공간
- 용접
- 추락
- 감전
- 위험성평가
- MSDS
- 압력용기

모든 long-tail 검색문을 Canonical로 만들지 않는다.

---

# 7. 사용자 검색어 기반 자동 구조화

회원/사용자 검색어는 TAI Search를 개선하는 중요한 학습 데이터다.

예:

```
밀폐공간 산소농도
밀폐공간 산소측정
밀폐공간 작업전 산소
산소농도 측정
밀폐공간 가스측정
```

반복 검색을 기반으로 시스템은 다음을 만들 수 있다.

- Query Cluster
- Candidate Topic
- Alias Candidate
- Related concept 후보
- Zero-result/Low-result gap
- 신규 API/콘텐츠 수집 후보

단, 자동으로 Public Truth로 승격하지 않는다.

권장 상태:

```
CANDIDATE
  ↓
REVIEWED
  ↓
APPROVED
  ↓
INDEXABLE
```

자동화 범위는 **후보 생성까지**다.

Semantic truth/공개 구조화 승격은 Human Review를 둔다.

---

# 8. 현재 검색 자산 재사용 원칙

현재 TAI에는 이미 다음이 존재한다.

- Public Safety Search
- Shared Search
- OpenSearch
- Nori
- deterministic rank tier
- Search Dictionary
- Knowledge Graph
- source별 검색 section
- KOSHA 공식검색 연계

현재 검색결과 source group에는 다음 자산이 존재한다.

- KNOWLEDGE
- GUIDE
- LEGAL
- CSI_ACCIDENT
- SAFETY_MATERIAL
- CHEM
- CHEM_REGULATION
- PRECEDENT
- KOSHA 공식검색

따라서 새 검색엔진을 병렬 구축하지 않는다.

향후 작업은 현재 검색자산의 품질을 강화하고 Search DB ownership을 정리하는 방향으로 한다.

---

# 9. 법령 경계

검색 결과 자체는 다음을 판정하지 않는다.

- 이 사업장에 법이 적용되는가
- 의무 주체가 누구인가
- 위반인가
- 이행되었는가
- 법적 책임이 누구에게 있는가

검색은 다음을 제공한다.

- 공식 자료
- 법령/조문 근거
- 관련 기준
- 발행기관
- 시행/수정 시점
- 관련 자료
- 실무문서

그리고 사용자가:

> 우리 회사에도 이 의무가 적용되는가?

를 확인하려 하면:

```
Search
   ↓
"우리 사업장 적용 여부 확인"
   ↓
LEG Legal Engine
```

으로 이동한다.

Legal SoT와 Search Mirror/Projection을 혼동하지 않는다.

---

# 10. 공공기관 API 추가수집 원칙

공공 API를 더 확보하는 것은 방향상 필요하다.

하지만 "자료 수를 늘리기 위해" 수집하지 않는다.

추가수집 우선순위는 다음 근거로 결정한다.

1. 반복 사용자 검색인데 결과가 부족하다.
2. 특정 기관 사일로 때문에 사용자가 다른 사이트로 이동해야 한다.
3. 최신성 gap이 있다.
4. 실무문서 작성에 필요한 공식 기준이 부족하다.
5. Topic Hub의 근거 연결이 약하다.
6. 법령/화학/사고 등 cross-source 연결을 위해 필요하다.

즉:

> **검색 로그 → Gap → Source 추가**

순으로 확장한다.

---

# 11. SEO / Sitemap 결정

구조화검색은 SEO 자산으로 활용한다.

단 모든 자유검색 URL을 색인시키지 않는다.

## 11.1 Indexable

Human Review를 거친 안정적인 Topic/Hub.

예:

- 설비
- 작업
- 위험
- 법정업무
- 화학물질
- 주요 사고유형

승인된 Topic Page는 sitemap에 포함할 수 있다.

## 11.2 Noindex

- 자유검색 Query Result
- 조합이 무한히 생성되는 parameter URL
- 품질 검증 전 Candidate Topic
- 사용자 개인화 결과
- 법적 적용성 결과 중 공개 SEO에 적합하지 않은 페이지

## 11.3 목표

```
검색엔진 유입
  ↓
TAI Topic
  ↓
관련 공식자료
  ↓
관련 실무문서
  ↓
TAI Search
  ↓
Legal Diagnosis / SaaS
```

---

# 12. 실무문서를 핵심 차별축으로 추가

통합검색의 강한 차별점은 단순 정보가 아니라 **실제 업무에 사용하는 문서**다.

예: 사용자가 `지게차` 검색

기존 결과:

- 법령
- KOSHA
- 사고사례
- 안전자료

강화 결과:

- 지게차 작업계획서
- 작업 전 점검표
- 위험성평가 관련 문서
- 교육 기록
- 정비/점검 기록
- 사고조사 문서

사용자가 느껴야 하는 가치는:

> 자료가 많다

가 아니라:

> **내가 오늘 해야 할 업무가 여기 있다**

이다.

## 12.1 Funnel

```
비회원
→ 양식/문서 검색 + 미리보기

회원
→ 표준 빈 양식 다운로드

TAI Safe 회원
→ 회사/사업장/설비/작업 정보 자동반영

SaaS 운영
→ 작성 + 저장 + 이력 + 증빙

기업 고객
→ 자사 양식/결재/ERP 연동 요구

SI
→ 커스터마이징
```

문서서비스는 Search와 SaaS를 잇는 핵심 Conversion Bridge로 본다.

---

# 13. GPT 사용 원칙

GPT를 검색제품의 메인 인터페이스로 만들지 않는다.

GPT 활용 후보:

- 검색어 cluster 후보 분석
- 구조화 후보 생성
- 문서의 자유서술 초안
- 작업절차 초안
- 위험요인/통제조치 서술 보조
- 설명문 생성

GPT가 해서는 안 되는 것:

- 법적 적용성 결정
- 법정 양식 자체를 임의 변경
- 공식 원문을 추론으로 보완
- 검색 결과의 authoritative truth 자동 승격
- candidate를 자동 APPROVED 처리

GPT는 **작성/보조 계층**, LEG와 공식 SoT는 **판정/근거 계층**으로 분리한다.

---

# 14. 제품 성공 기준

검색 품질은 "검색결과 수"로 측정하지 않는다.

권장 지표:

- First Relevant Result
- MRR
- Top-3 Precision
- Official-source Precision
- Time to usable evidence
- Cross-agency coverage
- Outdated/superseded source rate
- Zero-result rate
- Query reformulation rate
- Evidence completeness
- Search → Document CTR
- Search → Legal Diagnosis CTR
- Search → SaaS signup/conversion
- Repeat Search Usage

법적 경계 오류는 별도 품질 게이트로 관리한다.

---

# 15. 경쟁 비교 방식

TAI의 실제 차별성을 검증하기 위해 대표 안전관리 Query 30~50개로 비교한다.

비교 대상:

- Naver/Google
- KOSHA/공공기관 검색
- 범용 AI
- TAI Search

평가 목적은 "TAI가 무조건 이긴다"를 증명하는 것이 아니다.

어디에서 실제로 더 빠르고 정확하게 공식 근거/실무자료에 도달하는지를 확인한다.

Query군:

- 단일 개념
- 작업절차
- 법적 근거
- cross-source
- 사고+예방
- 화학물질
- 최신 개정
- 모호한 적용성 질문

적용성 질문은 Search 승패가 아니라 LEG로 올바르게 라우팅되는지를 본다.

---

# 16. 기술/운영 아키텍처 원칙

1. 검색 DB는 분리한다.
2. 원천 DB ownership은 유지한다.
3. Search는 Projection을 소비한다.
4. 기존 Shared Search/OpenSearch를 우선 재사용한다.
5. 기존 Knowledge Graph가 있는데 별도 Graph를 중복 생성하지 않는다.
6. Legal SoT는 LEG 경계를 지킨다.
7. 검색 로그는 개인정보/민감정보 최소화 정책을 둔다.
8. 사용자 검색어 기반 자동화는 Candidate 생성까지만 한다.
9. 공개 Topic/Sitemap은 승인 상태만 포함한다.
10. 공공 API 수집은 Rights/License/Source freshness gate를 통과해야 한다.

---

# 17. 구현 순서 원칙

구현은 다음 순서로 진행한다.

### Stage A — Ownership/Current State
- 현재 Search 자산 전수조사
- Source DB / Search Projection / Index / Dictionary / Graph ownership map
- 실제 query/result 계약 확인
- 기존 Sitemap 실측

### Stage B — Search DB
- tai-search 논리/물리 ownership 확정
- Projection sync 계약
- Query log / Candidate 구조

### Stage C — Structured Search
- Topic Registry
- Query cluster
- Candidate→Approved lifecycle
- existing dictionary/graph 재사용

### Stage D — Public Surface
- site-wide search entry
- Topic Hub
- detail reverse-link
- Evidence metadata

### Stage E — Sitemap/SEO
- approved Topic only
- noindex rule
- sitemap 자동생성

### Stage F — Document Integration
- 검색결과에 실무문서 연결
- 문서 상세/미리보기/다운로드
- SaaS 자동작성 CTA

### Stage G — Benchmark
- 30~50 representative query
- 비교 실측
- ranking/source/UX 개선

---

# 18. 현재 결정하지 않은 것

다음은 아직 고정하지 않는다.

- tai-search의 정확한 Supabase project/schema 구조
- 최종 Topic taxonomy 전체 목록
- 모든 추가 공공기관 API 목록
- 회원/비회원별 문서 다운로드 정책의 가격 세부
- Search용 AI model/provider
- 자동구조화 승인 UI 상세
- Topic URL 최종 slug 규칙
- 문서 무료 제공 범위

이 항목들은 실측/사업정책/별도 Owner Approval 이후 정한다.

---

# 19. 금지사항

- 자료량을 KPI로 삼아 무분별한 수집을 하지 않는다.
- 새 검색엔진을 기존 Shared Search 옆에 병렬 구축하지 않는다.
- Search DB를 LEG/화학/운영 데이터의 새 SoT로 만들지 않는다.
- 자유검색 결과를 대량 sitemap에 넣지 않는다.
- 사용자 Query를 그대로 자동 공개 Topic으로 만들지 않는다.
- 검색에서 법 적용 여부를 추론해서 확정하지 않는다.
- ChatGPT형 대화 UI를 통합검색의 메인으로 전환하지 않는다.
- 문서서비스를 별도 양식 다운로드 사이트로 분리하지 않는다.

---

# 20. 최종 기준 문장

> **TAI Search는 별도의 검색사이트가 아니다. TAI 전체의 공신력 있는 안전정보와 실무업무를 연결하는 공통 탐색 계층이다.**

> **검색은 넓게 하지 않는다. 안전관리만 깊고 근거 있게 찾는다.**

> **찾는 것에서 끝내지 않고, 필요한 문서와 실제 안전업무까지 연결한다.**

---

## Governance

- GPT: 분석 / 설계 / 작업지시 / 독립검증 / semantic 판정
- Claude Code: 조사 / 실행 / 구현 / 증거수집
- Owner: 정책 승인 / 최종 승인 / Production 권한

이 문서는 결정 기준선이며, 구현은 별도 Object/WO로 수행한다.
