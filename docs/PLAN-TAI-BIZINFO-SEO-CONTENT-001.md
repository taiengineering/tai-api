---
class: plans
type: SERVICE_PLAN
project: tai-safe
scope: bizinfo-program-event-content
id: PLAN-TAI-BIZINFO-SEO-CONTENT-001
version: 0.1
status: PROPOSED / DOC_REPOSITORY_REGISTRATION_PENDING
date: 2026-11-03
owner: TAI Safe
source_scope: BIZINFO_ONLY
---

# PLAN-TAI-BIZINFO-SEO-CONTENT-001 — 기업마당 기반 TAI Safe 지원사업·행사정보 콘텐츠 서비스 기획서

## 0. 문서 지위·결정 근거

- 이 문서는 TAI Safe(`https://taieng.co.kr`)의 **신규 콘텐츠/유입 서비스** 기획 초안이다. 기존 `OBJ-DISCOVERY`나 Shared Search를 교체하지 않는다.
- Owner가 2026-11-03 확정한 방향: **기업마당 정보만 1차 정보원으로 사용**; `지원사업정보 API` 및 `행사정보 API` 키를 Railway에 등록했다고 보고; 기획서 → Git 등록 → 오브젝트 작업계획서 → Git 등록 → 후속 작업 순서.
- 등록 보고된 Railway 변수명: `BIZINFO_API_KEY`, `BIZINFO_EVENT_API_KEY`. 값, Railway 실제 적용 여부, 호출 성공 여부는 미검증. 이 문서 및 Git에 키 값 기록 금지.
- 기획서는 구현·DB 마이그레이션·운영 배포 승인으로 간주하지 않는다. PR 병합 및 운영 적용은 별도 Owner Gate를 따른다.
- 2026-11-03 읽기 전용으로 확인한 구현: `taiengineering/tai-www`의 `src/lib/server/safetySearch.js`, `src/pages/safety-search.astro`; `taiengineering/tai-api`의 `routers/public_safety_search.py`, `services/shared_search/{indexer,document,result,production_bindings}.py`, `services/shared_search/adapters/marketing_knowledge.py`; `45cminc/marketing`의 `apps/api/marketing_knowledge_content_admin.py` 및 스키마.
- 참조 기획·규약: `docs/PLAN-MKT-PUBLIC-SEARCH-OBJECT-001.md`(ACTIVE로 표기), `docs/search/TAI_SHARED_SEARCH_CONSTITUTION_v1.md`, `docs/search/TAI_SHARED_SEARCH_F2_DOMAIN_INDEXING.md`, `45cminc/marketing/docs/MKT-CONST-001.md` 및 `MKT-ARCH-001.md`(MKT 경계 확인 용도; 오래된 기획을 본 프로젝트 승인으로 간주하지 않음).
- 기존 지식센터와 MKT 지식 콘텐츠 9,008건은 Owner가 보고한 기존 운영 자산이다. 본 프로젝트에서 재구성·이전·재발행하지 않는다.

## 1. 비즈니스 목표와 성공 기준

### 1.1 원래 목표

기업마당의 지원사업 공고 및 안전 관련 행사 소식을 발견해 **TAI 자체 해설·비교·체크리스트를 제공**함으로써 검색엔진 유입과 잠재고객의 TAI Safe 탐색을 늘린다. 네이버 블로그/유튜브 등은 MKT에서 재사용 가능한 콘텐츠 소재를 확보하되, 이번 프로젝트에서 해당 채널에 직접 게시하지 않는다.

### 1.2 왜 단순 복제를 하지 않는가

- 공고 내용을 그대로 복사하거나 기계적으로 요약하면 방문자가 TAI를 방문할 독자적 이유가 약하다.
- 지원대상에 관한 단정·오래된 신청정보·지원을 보장하는 표현은 사업장에 피해를 줄 수 있다.
- 기업마당 **저작권 정책**은 기업마당이 창작한 콘텐츠의 수익 목적 활용·재게시 및 임의 변경에 제약을 명시한다. API 발급은 콘텐츠 가공·상업적 재게시의 포괄 허락이 아니다.
- 따라서 공고의 사실정보와 링크/출처를 근거로 **TAI가 독립적으로 작성한 실무 설명**을 제공한다. 제3자 문장·표·이미지·PDF의 복제/재구성은 권리 확인 전 금지한다. 외부 기관의 지원 자격·조건 판단 권한을 TAI가 대신 주장하지 않는다.

### 1.3 측정 지표 (기존 측정자산 우선 재사용)

1. 지원사업/행사 상세페이지의 검색 유입 세션 및 비브랜드 유입 쿼리(가능한 기존 GSC/GA4 자산 사용).
2. 상세페이지에서 공식 원공고 클릭 비율, 관련 안전정보 클릭 비율.
3. 직접 관련된 콘텐츠에서 TAI 무료진단/문의로 이동한 수(적절한 경우에만 CTA).
4. 콘텐츠별 마지막 공식 확인일과 상태 신뢰도, 만료 정보 오표시 0건.
5. 발행량 자체를 목표 KPI로 두지 않는다. 수치 목표와 빈도는 실제 유입 기준선 확인 후 Owner 결정.

## 2. 고객과 콘텐츠 범위

### 2.1 핵심 사용자

- 소규모 제조사업장 대표, 공장장, 현장소장, 안전관리자.
- 안전시설 투자·위험설비 개선·안전보건관리체계 운영·안전교육 참가를 검토하는 실무자.

### 2.2 초기 포함 대상

- 정부/유관기관의 재해예방 설비·안전시설 개선·위험공정 개선 관련 지원사업.
- 중소사업장 안전·보건·산업재해 예방에 직접 연결되는 교육·설명회·세미나·전시/박람회.
- 산업안전 관련성이 충분히 확인된 프로그램과 행사만 선별. **기업마당의 분류코드나 해시태그만으로 안전 관련성이 자동 확정되지 않는다.**

### 2.3 초기 제외 대상

- 일반 창업자금, 수출마케팅, 금융, 비안전 교육·전시회 등 산업안전 목적에 직접 관련이 없는 정보.
- 기업마당 외 독자적인 수집 소스(KOSHA API, 고용노동부 크롤링, 공공데이터포털 등). 기업마당이 제공하는 원공고 링크는 출처 표시용으로만 사용하며, 링크된 타 사이트를 별도 수집하지 않는다.
- 기존 지식센터 9,008건 변경, LEG 법령 정본 편입, CHEM 개발, 블로그 게시, 유튜브 게시.

## 3. 공식 API 정보원 계약(설계 입력)

### 3.1 지원사업정보 API

- 원천: `https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do`
- 방식: GET, `crtfcKey`(필수), `dataType=json` 또는 `rss`, `searchCnt`, `searchLclasId`, `hashtags`, `pageUnit`, `pageIndex`(문서상 선택 파라미터).
- 문서상 예시 응답: `jsonArray.item`, 고유 공고 ID `pblancId` 또는 `seq`, 공고명 `pblancNm`, 공고 URL `pblancUrl`, 신청기간 `reqstBeginEndDe`/`reqstDt`, 지원대상 `trgetNm`, 요약 `bsnsSumryCn`, 소관기관 `jrsdInsttNm`, 수행기관 `excInsttNm` 등.
- `searchCnt=0` 또는 미설정 시 전체 제공이라고 안내하나, 과도한 전체 호출 금지. 우선 작은 페이지와 실제 한도·오류/중복/빈값 응답 확인.

### 3.2 행사정보 API

- 원천: `https://www.bizinfo.go.kr/uss/rss/bizinfoEventApi.do`
- 방식: GET, `crtfcKey`(필수), `dataType`, `searchCnt`, `searchLclasId`, `hashtags`, `pageUnit`, `pageIndex`.
- 문서상 예시 응답: `jsonArray.item`, 행사 ID `eventInfoId` 또는 `seq`, 행사 유형 `eventType`, 지역 `areaNm`, 접수기간 `rceptPd`, 행사기간 `eventPeriod`, 출처기관 `originOrg`, 기업마당 URL `bizinfoUrl`, 원출처 URL `originUrl` 등.
- 예시 데이터에는 URL과 날짜가 일관되지 않을 수 있다. 링크·날짜·기간을 실제 응답으로 검증하고, 임의 보정/추론 금지.

### 3.3 인증 및 오류 원칙

- Railway 등록 보고된 키는 서버 측에서만 사용. 브라우저·HTML·로그·버전관리·URL 공개 영역에 노출 금지. 호출 URL에 인증키가 포함되므로 전체 URL 로깅, 추적, 오류 반영 금지.
- 연동 서비스의 운영 소유 위치는 TAI API 우선 검토. **실제 서비스 환경·기존 수집 인프라 확인 후 확정**하며, 신규 Railway 서비스 추가 금지.
- API 키 존재 보고와 실호출 성공은 별도. 인증/쿼터/응답포맷/타임아웃은 첫 read-only smoke에서 확인한다.

## 4. 제품 IA/기능

### 4.1 공개 정보구조(경로는 제안)

- `/support-programs`: 정부지원사업 목록(산업안전 관련 공고만).
- `/support-programs/{id}`: 고유 공고 상세와 TAI 독립 해설 및 공식 공고 링크.
- `/safety-events`: 안전 관련 교육·행사 목록.
- `/safety-events/{id}`: 행사 상세와 TAI 독립 실무 해설 및 공식 등록/공고 링크.
- 두 영역을 메뉴에서는 `정부지원·안전행사`와 같은 상위 카테고리로 묶을 수 있으나, 콘텐츠 유형·상태·URL 정체성은 분리.
- 기존 `/safety-search`는 discovery로 유지하며 `GOV_SUPPORT_PROGRAM`, `SAFETY_EVENT` 후보 유형을 독립 그룹으로 검색하도록 최소 확장. 신규 검색엔진·검색 DB 금지.

### 4.2 목록·상세 최소 표시 필드

- 공통: 유형, 원천 고유 ID, 제목, 출처기관, 분야, 대상/지역, 원공고 링크, TAI 자체 해설 표시, 마지막 공식 확인시각.
- 지원사업: 신청 시작/종료일, **접수 상태**, 확인 필요/변경 알림, 기본 지원 내용·준비 사항.
- 행사: 접수 시작/종료일과 **행사 개최일/종료일** 분리, 행사 유형·지역, 행사 및 접수 상태.
- 상세의 공식 원문 링크는 항상 명시. 공식 정보와 TAI 해설을 시각적으로 구분. TAI는 신청 승인·법적 적용·지원금 수령을 보장하지 않음.

### 4.3 검색유입(SEO) 원칙

- 목록/상세는 고유한 유용한 설명이 있는 페이지만 색인 대상으로 검토. 기존 `/safety-search`의 `noindex,follow`를 신규 상세에 무단 복제하지 않음.
- 단순 복사·중복·빈 페이지는 자동 색인 유도 금지. 제목/설명/canonical, 모바일 가독성, 내부링크, 정확한 날짜 정보 제공.
- 행사 구조화 데이터가 필요하면 실제 `Event` 필드·공식 장소·일정이 검증되는 경우에만 검토. 스키마 허위 생성 금지.
- 마감 공고/종료 행사는 역사 정보로 보존 가능하나, `접수 중`·`참가 가능`으로 표시하지 않음. 오래된 정보의 색인/유지 정책은 품질 기준으로 결정.

## 5. 독립 해설 콘텐츠 정책

### 5.1 권장 상세 구성

1. `공식 공고 사실` — 제목/기관/기간/대상/공식 URL + 확인시각. 외부 원문을 대량 재게시하지 않음.
2. `TAI의 핵심 해설` — 어떤 안전위험·설비·관리 책임과 관련되는지 독립적인 설명.
3. `누가 확인할 만한가` — 사업장 관점 조건을 정확한 근거와 함께 정리(지원 가능 단정 금지).
4. `준비·확인 체크리스트` — 자체 제작 표·다이어그램·현장 실무 질문.
5. `주의사항` — 예산 소진/공고 변경/별도 심사/현장 적합성 유의.
6. `공식 출처`와 관련 TAI 정보. 무료진단·서비스 CTA는 실제 관련성이 있는 경우만.

### 5.2 웹·블로그의 역할 분리

- TAI 웹사이트는 고유 상세/원천 링크/최신성 안내의 기준 페이지가 된다.
- MKT는 승인된 사실·해설 원천을 **콘텐츠 제작 입력**으로 전달받되, 블로그 문구를 그대로 복제하지 않고 채널별 별도 원고를 작성·검토한다.
- 이번 계획의 범위는 **MKT로 소재를 전달할 수 있는 인터페이스 설계**까지. 네이버 블로그·유튜브 콘텐츠 제작, 자동발행, 채널 KPI 변경은 다른 작업/승인 대상.

### 5.3 권리·사실 검증 Gate

- `FACT_VERIFIED`: 각 핵심 숫자/날짜/대상에 확인 가능한 기업마당 원천 링크와 확인시각 존재.
- `RIGHTS_CLEARED`: 공고 사실의 독립 재서술 또는 명시적으로 사용 허용된 소재만 활용. 기업마당 창작 원문·이미지·첨부 PDF의 편집/재게시는 별도 허락 없으면 제외.
- `EDITORIAL_APPROVED`: TAI 고유 실무 해설과 시각자료가 있는지, 지원 자격/금액을 오도하지 않는지 검토.
- 세 Gate가 모두 통과한 콘텐츠만 공개 후보로 전환. 무검증 자동 발행 금지. 저작권 판단이 애매하면 `HOLD`와 출처 링크만 유지.
- 기업마당 저작권 정책: `https://www.bizinfo.go.kr/biz/bizd/selectBIZD120View.do` 참고. 구체적 상업적 재게재 허용 범위는 제공기관 확인 전 미확정.

## 6. 공고·행사 상태 및 최신성

### 6.1 게시 상태와 접수/개최 상태 분리

- **콘텐츠 게시 상태:** DRAFT / REVIEW / APPROVED / PUBLISHED / ARCHIVED (기존 승인 흐름의 재사용 후보).
- **사업 접수 상태:** UPCOMING / OPEN / CLOSED / BUDGET_EXHAUSTED / UNKNOWN. `NOTICE_CHANGED`는 독립 변경 플래그/이력으로 표시하며, OPEN과 동시 존재 가능.
- **행사 상태:** REGISTRATION_UPCOMING / REGISTRATION_OPEN / REGISTRATION_CLOSED / EVENT_FINISHED / CANCELED / UNKNOWN. 행사기간과 접수기간은 별도.
- 날짜 비교는 `Asia/Seoul` 기준. 시간이 없으면 날짜 경계 보수적 처리; 모호하거나 확인불가시 OPEN 추정 금지.
- API 자체에 예산 소진/취소가 구조화되어 있지 않으면 임의 판정 금지. 정정 공고는 ID/원문 변경·확인 메모를 구분한다.

### 6.2 갱신·중복·출처

- 자연키 후보: `(provider='BIZINFO', record_kind, source_id)`; 지원사업은 `pblancId`, 행사는 `eventInfoId`. 같은 URL·제목의 다른 ID 병합 금지. 원문 공고의 법적 정본은 소관기관에 있으며 TAI는 파생 안내만 소유.
- 원본 필드 수신시각, 마지막 확인시각, 콘텐츠 수정시각을 구분. 변경이 없어도 마지막 확인시각은 갱신될 수 있음.
- API 실패/미수신을 공고 삭제나 종료로 해석 금지. 오래된 항목은 `확인 필요` 표시 정책과 색인 제외 정책 검토.
- 주기적 자동 수집·상태 갱신은 1차 필수 아님. 우선 작은 표본으로 품질·업데이트 업무량 확인 후 승인.

## 7. 서비스 소유권·기존 자산 재사용

| 책임 | 우선 검토 주체 | 기존 자산 | 결정 상태 |
|---|---|---|---|
| 기업마당 API 호출/안전한 키 사용 | TAI API | 기존 서버형 API/공공데이터 수집 패턴 | PROPOSED |
| 원천 ID·사업 상태·검증 이력 | TAI Domain | 기존 저장 구조의 적합성 확인 필요 | STORAGE_HOLD |
| 공고/행사 공개 목록·상세 | TAI WWW | Astro SSR/상세 페이지 패턴 | PROPOSED |
| 기존 통합검색 검색색인 | TAI API | Shared Search Domain Adapter/Indexer/OpenSearch | REUSE |
| 마케팅용 해설 검수/콘텐츠 연결 | MKT | 버전·승인·발행·관측 기능 | CONTRACT_HOLD |
| 법령 정본·법적 적용판정 | LEG | 법령 전용 | OUT_OF_SCOPE |

- Shared Search는 원천이 아니라 **discovery projection**. 검색 결과는 canonical identity + `public_url`로 Domain 상세에 연결.
- 기존 MKT `MarketingKnowledgeAdapter`는 `object_type=KNOWLEDGE`로 고정된 지식 콘텐츠 경로다. 여기에 지원사업·행사를 섞지 않는다.
- `GOV_SUPPORT_PROGRAM`, `SAFETY_EVENT`는 **검색 유형 후보**이며, 실제 등록은 검색 계약 승인 후.
- 새로운 DB/테이블, RLS 변경, Railway 서비스, 콘텐츠 엔진은 기존 자산의 부족을 확인하고 Owner가 별도로 승인한 경우만 검토.
- MKT DB RLS 관련 과거 경고는 접근 설계시 위험으로 기록하되, 이번 프로젝트에서 보안 수정을 함께 지시하지 않는다.

## 8. 최소 단계와 승인 지점

1. **Gate DOC-1 — 기획서 정본 등록:** 본 문서를 `taiengineering/tai-api/docs/`에 docs-only 경로로 등록. CODE/DB/DEPLOY 금지. GPT는 실제 Git SHA와 내용 대조.
2. **Gate DOC-2 — Object 작업계획 등록:** DOC-1 검증 후 별도 오브젝트 계획서를 `docs/`에 등록. 각 Object의 의존성·승인 범위·검증 기준 고정. GPT 독립검증.
3. **Gate SRC-1 — 실제 API 읽기 검증:** API 키의 Railway 등록 여부(값 노출 없이), 호출/응답 구조, `pageIndex`, 빈필드, 인증실패만 최소 시험. 별도 Owner 실행 승인 필요; 운영 환경변수 추가·배포 금지.
4. **Gate DATA-1 — 저장 방식 확정:** 기존 TAI/MKT 데이터 구조 재사용 가능성 검증 후 소유권·필드·권리 게이트 확정. 신규 스키마 필요시 별도 DB 승인.
5. **Gate CODE-1 — 소수의 지원사업/행사 상세 MVP:** 독립 해설·승인 게이트·공식 원문 링크를 가진 공개 페이지. 코드 구현·PR·운영 반영은 각각 승인 분리.
6. **Gate SEARCH-1 — 통합검색 편입:** 새 Domain Adapter, 공개 allowlist/section, www 결과 타입, 링크 연결을 기존 검색에만 최소 추가. 운영 재색인/배포 별도 승인.
7. **Gate MKT-1 — 콘텐츠 원천 전달:** 기존 MKT 승인 파이프라인으로 소재 전달. 채널 자동게시 금지. 성과 측정 후 갱신 자동화 필요성 결정.

## 9. 수용 기준(서비스 품질)

- 지원사업/행사 결과를 `KNOWLEDGE`와 구별하고, 원본 ID로 중복을 막는다.
- 안전 분야와 무관한 일반 창업·수출·금융 콘텐츠 대량 유입 0.
- 지원사업 마감/행사 종료를 현재 접수 가능으로 오표시 0.
- 모든 공개 상세에 출처·공식 링크·마지막 확인시각·TAI 고유 해설 존재.
- 원문 무단 복제·첨부 이미지 무단 사용·키 유출 0.
- 기존 지식센터 9,008건과 기존 검색 유형에 회귀 0.
- SEO 유입/원문 클릭/TAI 관심 행동을 기존 분석 자산으로 관찰 가능.
- 운영 부하·품질을 확인하기 전 전체 자동수집·자동발행 하지 않음.

## 10. Hard Block

- 기업마당 외 데이터 원천 수집·자동 통합 금지.
- 기획서 등록을 DB/코드/운영 배포·PR 병합 승인으로 오인 금지.
- 기업마당 원문 표현의 단순 순서 변경/축약 재게시, 원본 그림·표·첨부파일 가공 발행 금지(권리 확인 전).
- 콘텐츠 자동 승인/발행, 접수 상태 허위 추론 금지.
- 기존 지식센터 9,008건·MKT 블로그·유튜브 작업 금지.
- 기존 통합검색 전면 재구축·새 독립 검색엔진·LEG 법령 정본 편입 금지.
- 신규 Railway 서비스/운영 변수 변경/DB/RLS 변경/배포/병합은 별도 승인 전 금지.

## 11. 근거 링크 (읽기 전용 확인)

- 기업마당 API 목록: https://www.bizinfo.go.kr/apiList.do
- 기업마당 지원사업 API: https://www.bizinfo.go.kr/apiDetail.do?id=bizinfoApi
- 기업마당 행사 API: https://www.bizinfo.go.kr/apiDetail.do?id=bizinfoEventApi
- 기업마당 저작권 정책: https://www.bizinfo.go.kr/biz/bizd/selectBIZD120View.do
- 검색 현재 계획: https://github.com/taiengineering/tai-api/blob/main/docs/PLAN-MKT-PUBLIC-SEARCH-OBJECT-001.md
- 검색 헌법: https://github.com/taiengineering/tai-api/blob/main/docs/search/TAI_SHARED_SEARCH_CONSTITUTION_v1.md
- TAI API 검색 라우트: https://github.com/taiengineering/tai-api/blob/main/routers/public_safety_search.py
- TAI WWW 공통 검색: https://github.com/taiengineering/tai-www/blob/main/src/lib/server/safetySearch.js
- MKT 편집·발행 경계: https://github.com/45cminc/marketing/blob/main/apps/api/marketing_knowledge_content_admin.py

## [Owner용 쉬운 설명 및 방향 점검]

1. **원래 목표:** 안전시설 개선 지원금과 산업안전 행사 소식을 활용해 TAI Safe의 검색 유입과 잠재고객을 늘리고, 블로그 소재를 확보합니다.
2. **이번 작업:** 먼저 서비스의 목적·공고 활용 조건·데이터 소유권·기존 검색 재사용 원칙을 기획서로 고정합니다.
3. **완료 후 변화:** 개발자가 무엇을 만들어야 하는지와 어디까지 하지 말아야 하는지가 분명해집니다. 고객에게 노출되는 기능은 아직 바뀌지 않습니다.
4. **하지 않는 작업:** 코드, DB, 운영 배포, 공고 자동 발행, 블로그 게시, 기존 9,008건 재편집은 하지 않습니다.
5. **원기획 일치 여부:** **부분일치.** 확인 근거는 TAI Public Search 계획(`PLAN-MKT-PUBLIC-SEARCH-OBJECT-001`), Shared Search Constitution, 실제 `tai-www`/`tai-api` 소스입니다. 기존 검색 재사용 원칙과는 일치하나 신규 지원사업/행사 Domain 소유·저장 계약은 아직 승인되지 않았습니다.
6. **방향 이탈 위험:** 콘텐츠 갯수 늘리기, 지원사업 자동게시 도입, 별도 검색엔진/DB 신설로 과도하게 확장할 위험이 있습니다. 검색·블로그 유입에 도움이 되는 독립적인 안전 해설만 우선합니다.
