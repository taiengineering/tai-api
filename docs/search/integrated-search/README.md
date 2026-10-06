# TAI Integrated Search

> 상태: DECISION BASELINE  
> 기준일: 2026-10-07  
> 대상: TAI 통합검색 / 안전정보 전문검색  
> 저장소: taiengineering/tai-api  
> 원칙: 이 폴더는 통합검색의 사업·제품·데이터·검색·SEO·SaaS 연결 결정사항을 고정한다.

## 목적

TAI Search는 별도의 검색 포털이나 커뮤니티가 아니다.

**TAI가 보유·연결한 공신력 있는 안전정보를 하나의 검색 계층으로 탐색하게 하고, 필요한 경우 법령진단·TAI Safe·화학물질관리·SI로 연결하는 공통 진입/탐색 계층**이다.

핵심 사용 이유는 자료의 양이 아니라 다음 세 가지다.

1. 일반 검색엔진의 과도한 모수와 노이즈를 줄인다.
2. 공공기관별로 분산된 안전정보를 기관 경계 없이 찾게 한다.
3. 일반 AI가 법규제 영역에서 제공하기 어려운 현재 근거·출처·법령 연결을 구조화해 보여준다.

## 확정 결정

- 검색 UX는 TAI 안에 유지한다. 당장은 `search.taieng.co.kr`로 분리하지 않는다.
- 검색 DB는 별도 `tai-search` 소유영역으로 분리한다.
- `taeng`, `LEG`, `tai-chemical` 등 원천 DB는 각각 SoT를 유지한다.
- Search DB는 원천을 복제해 새 SoT가 되지 않고, 검색용 Projection/Index/Dictionary/Graph/Usage 데이터를 소유한다.
- 일반 전문검색과 구조화검색을 병행한다.
- 등록되지 않은 키워드도 항상 검색되어야 한다.
- Canonical/Topic은 반복 가치가 높은 안전관리 개념만 구조화한다.
- 회원 검색어는 구조화 후보 생성에 사용한다.
- 자동화는 후보 생성까지 허용하고, 공개 구조화 자산 승격은 Human Review를 거친다.
- 권장 상태 흐름: `CANDIDATE → REVIEWED → APPROVED → INDEXABLE`.
- 대화형 AI 검색을 메인 UX로 만들지 않는다.
- 검색 자체는 사업장 법적 적용 여부를 판정하지 않는다.
- 사업장 적용성/의무 판정은 LEG 법령엔진으로 연결한다.
- 자유검색 결과 URL은 원칙적으로 `noindex`.
- SEO 대상은 검증·승인된 Topic/Hub 페이지다.
- 상세 콘텐츠 페이지에서 관련 검색/Topic으로 역방향 연결한다.
- 실무문서를 통합검색의 핵심 차별축으로 연결한다.
- 추가 공공기관 API 수집은 '모수 확대'가 아니라 실제 검색/업무 gap이 확인될 때 우선순위 방식으로 진행한다.

## 문서

- [TAI_INTEGRATED_SEARCH_DECISION_BASELINE_v1.md](./TAI_INTEGRATED_SEARCH_DECISION_BASELINE_v1.md)  
  지금까지 논의하고 확정한 통합검색의 전체 결정 기준선.

## 관련 기존 자산

현재 TAI에는 이미 Shared Search/OpenSearch, Search Dictionary, Knowledge Graph, Public Safety Search API/화면이 존재한다. 본 계획은 이를 폐기하고 새 검색엔진을 만드는 계획이 아니다.

구현 전에는 현재 Main 기준 자산을 다시 실측하고, 기존 엔진을 재사용하는 것을 기본으로 한다.

## 역할

- GPT: 분석 / 설계 / 작업지시 / 독립검증 / semantic 판정
- Claude Code: 조사 / 실행 / 구현 / 증거수집
- Owner: 승인 / 정책결정 / Production 권한

