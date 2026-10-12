# TAI EXT-037 / EXT-132 / EXT-165 공공 API 서비스 정의서

- 문서 ID: TAI-CONTENT-P0-EXT037-132-165-SERVICE-DEF-20261012
- 작성일: 2026-10-12 (KST)
- 버전: 1.0
- 상태: 구현·운영배포 완료 / 신규 Shared Search 색인 반영 여부 별도 미확인
- 시스템: TAI Safe / tai-api / tai-www / Supabase / Shared Search
- 적용 근거: 병합된 tai-api PR #602 (cf0af61cb9c734de0db3fa3cba40f93264a04f0b), tai-www PR #267 (f47235a9d1ccfcfb5e8632af5fb023dfca00a5c6)
- 목적: 세 공공데이터 API의 **기획·수집·저장·공개 조회·검색 연결·작업 이력**을 하나의 기준 문서에 보존한다.

> 구분 원칙: 본 문서의 **구현 사실**은 위 병합 소스를 기준으로 기술한다. 수집 건수와 배포 결과는 2026-10-12 작업 보고 시점의 관측치이다. 해당 관측치가 검색 인덱스 실반영이나 이후 자동갱신의 성공을 증명하지는 않는다.

## 1. 기획 배경과 제품 목표

TAI 안전정보 서비스에는 KOSHA MSDS·KECO 규제정보와 사고사례·통합검색이 존재한다. 세 개의 공공 원천을 추가해 (1) 물질별 안전정보, (2) 소방청 위험물 정보, (3) 실제 화학사고 사례를 제공한다.

| Source ID | 공식 공급기관 / 주제 | 서비스 목적 | 핵심 연결 키 |
|---|---|---|---|
| EXT037_CHEMICAL_SAFETY | 화학안전원, 화학물질안전정보 | CAS를 통해 기존 MSDS에 증상·노출경로 등의 참고자료 추가 | 원천 PK dataNo, 조회 CAS |
| EXT132_HAZARDOUS_MATERIAL | 소방청, 위험물안전관리 | 기존 MSDS에서 위험물 번호·명칭·분류 등 확인 | 원천 PK chemicalno, 조회 CAS |
| EXT165_CHEMICAL_ACCIDENT | 화학물질안전원, 화학사고 | 사고 목록·검색·개별 상세페이지 제공 | 원천 PK dataNo; CAS 자동결합 없음 |

**제품 경계**: 원천 자료의 공개·검색·참고정보 제공을 위한 것이다. 이 자료만으로 법령 적용, 위반, 점검 의무, 처벌, 의학적 판단을 자동 확정하지 않는다. LEG 법령 SoT 및 기존 법령엔진은 수정하지 않는다. EXT-165의 사고물질명 텍스트를 CAS로 추정해 EXT-037/132/MSDS와 자동 병합하지 않는다.

### 공식 API 계약

| 원천 | 실수집 API 엔드포인트 | 공공데이터포털 참조 |
|---|---|---|
| EXT-037 | https://apis.data.go.kr/1480802/iciskischem/kischemlist | https://www.data.go.kr/data/15072442/openapi.do |
| EXT-132 | https://apis.data.go.kr/1661000/materialInfoSvc/getMaterialList | https://www.data.go.kr/data/15061055/openapi.do |
| EXT-165 | https://apis.data.go.kr/1480802/iciscsc/csclist | https://www.data.go.kr/data/15072446/openapi.do |

인증은 공통 DATA_GO_KR_SERVICE_KEY를 사용한다. 원천 응답은 수집 계층에서 파싱해 raw JSONB로 보존한다. EXT-132 파서는 XML 외 JSON 응답도 처리하도록 구현돼 있다. API 실제 응답의 제한·변경 여부는 별도의 원천 계약 사항이다.

## 2. 전체 아키텍처

~~~text
공공데이터포털 API (EXT-037 / 132 / 165)
  → 각 원천 client.py (HTTP/인증/호출 예산)
  → parse.py (응답 구조 확인, PK 정규화)
  → sync.py (페이지 수집/예산/체크포인트/재개)
  → store.py (STAGING 스냅샷 + 원본 raw → COMPLETED 현행 스냅샷)
                │
                ├─ EXT-037/132 CAS 읽기
                │    → GET /public/chemical-enrichment/by-cas/{cas_no}
                │    → tai-www MSDS Worker (/msds/{chem_id})에 보강 표시
                │
                ├─ EXT-165 사고 읽기
                │    → GET /public/accidents/chemical
                │    → GET /public/accidents/chemical/{datano}
                │    → /accident-cases?tab=chemical
                │    → /accident/chemical/{datano}
                │
                └─ 세 원천 Shared Search DomainAdapter
                     → 기존 Common Indexer / Writer / SearchStore
                     → 기존 OpenSearch / Public Safety Search API
                     → /safety-search
~~~

수집 실행과 검색 인덱스 갱신은 서로 다른 작업이다. **DB Snapshot 교체 및 Git/WWW 배포만으로 기존 OpenSearch 색인이 자동 갱신됐다고 판단하지 않는다.** 신규 인덱스 반영 여부는 별도 실행·증거가 없으면 미확인으로 유지한다.

## 3. 공통 수집·저장 로직

### 3.1 수집기 모듈

각 원천은 다음 동일한 책임 분리를 사용한다.

- contract.py: SOURCE_ID, BASE_URL, 페이지 크기·예산, 테이블명, Snapshot 상태
- client.py: 공통 인증키로 페이지 호출, HTTP/속도 제한 처리
- parse.py: 응답 파싱, 문서별 원천 PK 추출, 페이지 수·건수 확인
- sync.py: 전체 페이지 순회, 호출 예산 상한, 중단·재시작, 원천 총건수 정합성
- store.py: 스테이징 Snapshot, 아이템 Upsert, 페이지 Checkpoint, 소유권 검증과 현행판 승격
- read.py: 운영 DB의 **현행 COMPLETED** Snapshot만 조회하는 공개 읽기 계층

관련 코드:
- [EXT037](../../../services/ext037_chemical_safety/contract.py)
- [EXT132](../../../services/ext132_hazardous_material/contract.py)
- [EXT165](../../../services/ext165_chemical_accident/contract.py)

### 3.2 저장 계약

| 원천 | Snapshot 테이블 | Snapshot item 테이블 | item 식별 |
|---|---|---|---|
| 037 | ext037_chemical_safety_snapshots | ext037_chemical_safety_snapshot_items | snapshot_id + datano |
| 132 | ext132_hazardous_material_snapshots | ext132_hazardous_material_snapshot_items | snapshot_id + chemicalno |
| 165 | ext165_chemical_accident_snapshots | ext165_chemical_accident_snapshot_items | snapshot_id + datano |

- 신규 수집은 STAGING에서 시작한다. 페이지별 Upsert·Checkpoint를 통해 중단 후 재개할 수 있다.
- 소유권(Run fencing)·진행상태·데이터 건수 등 승격 조건을 확인해 COMPLETED로 전환한다. 실패한 STAGING이 기존 현행 COMPLETED 자료를 교체하지 못하도록 설계한다.
- 원문 필드는 raw JSONB에 유지하며, 공개 API는 승인된 필드만 추출한다.
- 공개 읽기·검색은 status=COMPLETED 및 is_current=true를 필수로 사용한다.
- EXT-165는 연도 필터 yyyy 수집을 지원한다. 연도 범위 수집은 collect_scope로 구분하며, **공개 목록/검색은 collect_scope IS NULL인 전체수집 Snapshot만** 조회한다.
- 원천별 호출 예산 기본값 500, 페이지 기본 크기 10, 최대 5,000페이지 안전상한이 contract.py에 정의돼 있다. 실제 실행 시 환경변수·실행 파라미터가 이를 변경할 수 있다. 자동 수집 실행 빈도는 본 정의서에서 임의로 확정하지 않는다.

### 3.3 오류/부분 수집 취급

- 인증 오류·쿼리 장애·원천 응답 오류는 각 원천의 실패 상태로 구분한다.
- API 호출 예산 소진·429 등의 경우 해당 수집 작업은 중단/부분 수집 상태로 처리하며 재개 가능한 STAGING과 체크포인트를 활용한다.
- 3개 원천의 데이터가 동일 CAS라고 동일 원본 레코드로 간주하지 않는다.
- 운영 데이터 읽기에서는 새로 수집 중인 STAGING을 노출하지 않는다.

## 4. EXT-037: 화학물질 안전정보

### 4.1 기획

기존 MSDS가 제공하는 16개 섹션을 대체하지 않고, 화학안전원 출처의 **노출경로·증상 등 부가 안전정보**를 더한다. 검색에서 물질명·CAS·안전 관련 텍스트를 찾을 수 있도록 한다.

### 4.2 데이터 및 필드

- 원천 식별: dataNo → datano
- CAS: raw.casNo
- 물질명: raw.chemKo / raw.chemEn
- 안전 텍스트: raw.symptom, oral, skin, inhale, eyeball, etc
- 공개 응답: datano, chem_ko, chem_en, cas_no, oral, skin, inhale, eyeball, symptom, etc

### 4.3 조회 흐름

1. CAS 형식을 기존 KECO의 validate_cas()로 검증한다.
2. EXT-037의 현행 COMPLETED Snapshot ID를 읽는다.
3. 해당 Snapshot의 raw->>casNo 값으로 **정확히 일치**하는 모든 아이템을 조회한다.
4. raw 중 공개 필드만 변환해 반환한다.
5. Snapshot 부재(None), 정상 일치 0건([]), 데이터베이스 장애(Ext037Unavailable)는 서로 다른 상태로 유지한다.

**서비스 위치**: GET /public/chemical-enrichment/by-cas/{cas_no} 응답의 chemical_safety 블록, 그리고 MSDS 상세의 ext037 부가정보 영역.

### 4.4 Shared Search

- object_type=CHEM_SAFETY, source_id=EXT037_CHEMICAL_SAFETY
- canonical_id/source_key=datano; 제목 우선순위 chemKo → chemEn → dataNo
- search_text: 한·영문명, CAS, 증상, 노출경로 텍스트 등
- 별도 전용 상세 페이지가 없어 public_url=null
- visibility_scopes=[PUBLIC], publication_status=PUBLISHED
- source_updated_at: 선택된 현행 Snapshot의 completed_at; 필수 timestamp 없으면 색인에서 제외
- CAS가 있으면 chemical context로 기록하되 기존 물질의 법령 의무를 변경하지 않는다.

## 5. EXT-132: 위험물안전관리

### 5.1 기획

소방청 위험물 분류를 별도 출처로 제공한다. 기존 MSDS·KECO를 수정하지 않고 위험물 번호·명칭·분류의 공개 참고정보를 추가한다.

### 5.2 데이터 및 필드

- 원천 식별: chemicalno (원문 매핑에서 원문 변형 키 chemaicalno를 fallback으로 지원)
- CAS: raw.casno
- 물질명: raw.chemicalname
- UN 번호: raw.unno
- 위험물 분류: raw.hazardmaterialclass
- 공개 응답: chemicalno, chemical_name, cas_no, un_no, hazard_class

### 5.3 조회 흐름

1. CAS 형식 검사 후 현행 COMPLETED Snapshot을 선택한다.
2. raw->>casno가 CAS와 정확히 일치하는 아이템을 검색한다.
3. 동일 CAS에 복수의 위험물 레코드가 있으면 **전부 반환**한다.
4. 조회 실패·Snapshot 부재·정상 빈 결과를 분리한다.

**서비스 위치**: GET /public/chemical-enrichment/by-cas/{cas_no}의 hazardous_material 블록 및 MSDS 상세의 ext132 부가정보 영역.

### 5.4 Shared Search

- object_type=HAZARDOUS_MATERIAL, source_id=EXT132_HAZARDOUS_MATERIAL
- canonical_id/source_key=chemicalno; 제목은 물질명, 없으면 No {chemicalno}
- search_text: 물질명, CAS, UN 번호, 위험물 분류
- 공개 URL은 전용 상세 화면 부재로 null
- 공개 범위=[PUBLIC], 원천 Snapshot completed_at 사용
- 동일 CAS 복수건 보존; KECO 규제정보와 자동 병합하지 않음

## 6. EXT-165: 화학사고

### 6.1 기획

사고 자료를 사용자가 TAI 내에서 검색·열람하도록 **사고 목록/검색·개별 SSR 상세**로 서비스화한다. 화학물질명이 유사하다는 이유로 사고 데이터를 CAS나 특정 MSDS에 자동 연결하지 않는다.

### 6.2 데이터 및 필드

- 원천 식별: dataNo → datano
- 일시/유형: raw.cscDe, raw.cscTy
- 지역/장소: raw.area, raw.place
- 화학물질/원인/개요: raw.chem, raw.cause, raw.summary
- 공개 응답: datano, accident_date, accident_type, area, place, chemical, cause, summary
- raw.addr 및 Snapshot 내부 필드는 공개 응답에 포함하지 않음

### 6.3 공개 API

| 메서드 | 경로 | 기능 |
|---|---|---|
| GET | /public/accidents/chemical?q=&page=1&page_size=20 | 화학사고 목록·키워드 검색·페이지네이션 |
| GET | /public/accidents/chemical/{datano} | 특정 사고 상세 조회 |

- page>=1, page_size 1~50 (기본 20), 검색어 최대 80자.
- 검색 필드: summary, chem, area, cscTy, cause, place (6개).
- 검색어 문자 제한, PostgREST ilike 이스케이프 적용.
- 현행 COMPLETED + is_current=true + collect_scope IS NULL 조건 필수.
- 스냅샷 없음 또는 DB 장애: HTTP 503; 스냅샷 있음 + 검색 결과 없음: HTTP 200 및 items=[]; 존재하지 않는 개별 사고: HTTP 404; 잘못된 입력: HTTP 422.
- 목록 반환 키: items, total, page, page_size.

### 6.4 화면·SEO

- /accident-cases?tab=chemical — 기존 사고 검색의 화학사고 탭
- /accident/chemical/{datano} — SSR 개별 상세
- 사고 원문 출력 시 escape 적용, 출처 및 법령 참고정보 고지
- 정상 상세는 canonical 및 index,follow; 404/503은 noindex,follow
- 공식 출처: https://www.data.go.kr/data/15072446/openapi.do

### 6.5 Shared Search

- object_type=CHEM_ACCIDENT, source_id=EXT165_CHEMICAL_ACCIDENT
- canonical_id/source_key=datano
- search_text: 물질명, 지역, 사고유형, 장소, 원인, 사고개요, 사고일자
- public_url=/accident/chemical/{datano}, 다른 화학물질 도메인과 병합하지 않음
- visibility_scopes=[PUBLIC], source_updated_at=현행 Snapshot completed_at

## 7. 두 종류의 공개 검색 계약

### 7.1 CAS 보강 조회 — WP-01 + WP-02

~~~http
GET /public/chemical-enrichment/by-cas/7664-41-7
~~~

개념 응답:

~~~json
{
  "cas_no": "7664-41-7",
  "chemical_safety": {
    "source_id": "EXT037_CHEMICAL_SAFETY",
    "display_name": "화학안전원 화학물질안전정보",
    "status": "AVAILABLE",
    "items": []
  },
  "hazardous_material": {
    "source_id": "EXT132_HAZARDOUS_MATERIAL",
    "display_name": "소방청 위험물안전관리",
    "status": "AVAILABLE",
    "items": []
  }
}
~~~

위 JSON은 **계약 설명용 예시**이며 해당 CAS에 실제 결과가 0건이라는 뜻이 아니다.

- CAS 부적합은 HTTP 422.
- 두 블록은 개별 AVAILABLE / NO_CURRENT_SNAPSHOT / UNAVAILABLE 상태를 가질 수 있다.
- 한 원천이 장애여도 다른 원천 결과는 반환하는 부분 실패 허용 방식이며, 전체 503을 자동 반환하는 구조가 아니다.
- Worker가 보강 API를 호출할 수 없거나 일부 원천이 미가용이면 기존 MSDS·KECO 표시를 유지하는 **fail-open** 동작이다.
- KOSHA MSDS 기존 16개 섹션은 유지하고 추가 출처를 별도 표시한다. 성공/부분실패 여부에 따라 Worker의 캐시를 구분한다.

### 7.2 통합검색 — WP-04

기존 Shared Search 시스템 하나를 사용한다.

- GET /public/safety-search?q={query}&type=chem_safety
- GET /public/safety-search?q={query}&type=hazardous
- GET /public/safety-search?q={query}&type=chem_accident
- GET /public/safety-search/sections?q={query}
- 웹 화면: /safety-search

| HTTP type | Shared Search object_type | 결과 상세 링크 |
|---|---|---|
| chem_safety | CHEM_SAFETY | null (전용 상세 URL 미구현) |
| hazardous | HAZARDOUS_MATERIAL | null (전용 상세 URL 미구현) |
| chem_accident | CHEM_ACCIDENT | /accident/chemical/{datano} |

어댑터는 기존 DomainAdapter 인터페이스(iter_documents, iter_expected_hashes, object_reindex_payload)를 구현하고 production_bindings.build_production_adapters()에 등록된다. Common Indexer/Writer 및 기존 OpenSearch 검색 인프라를 재사용한다.

**기존 체계의 보존**: CHEM(KOSHA MSDS), CHEM_REGULATION(KECO), CSI_ACCIDENT, LEGAL, REFERENCE_FORM 및 나머지 도메인을 재사용·유지한다. 기존 KECO용 object_type에 신규 원천을 덮어쓰지 않는다.

**현재 유보 사항**: 2026-10-12 운영배포 시 신규 3개 도메인의 검색 색인 반영은 **미확인/별도 실행하지 않음**. Public API나 화면의 HTTP 200 및 색인 어댑터 배포가 실제 신규 검색 문서 존재를 의미하지 않는다. Owner 결정에 따라 별도 운영 색인 작업은 열지 않았다.

## 8. 수행 작업 내역 (2026-10-12 기준)

| WP | 구현 내역 | 주 변경점 |
|---|---|---|
| WP-00 | 원천 수집·Snapshot 기반 데이터 확보 | EXT-037/132/165 수집 모듈과 Scheduler 기반 운영 구조 |
| WP-01 | 공개 CAS 보강 API | EXT-037·132 read.py, public_chemical_enrichment.py; 원천별 가용성 상태 |
| WP-02 | MSDS 화면에 보강정보 추가 | tai-www workers/pages-live-worker.js; 16개 MSDS 섹션 유지, 장애 시 기존 화면 유지 |
| WP-03 | 화학사고 목록·상세 API 및 웹 화면 | read.py, public_chemical_accident.py, chemicalAccidents.js, 사고 목록 탭 및 SSR 상세 |
| WP-04 | 3개 원천 Shared Search 도메인 어댑터 | adapters 3개, production_bindings.py, public_safety_search.py, tai-www safetySearch.js |
| WP-05 | 통합 QA 및 릴리즈 | API/WWW 각각 PR 병합, Railway/Cloudflare 운영 배포, 7개 Production Smoke 보고 |

### 작업 중 보완한 주요 사항

- EXT-165에서 collect_scope IS NULL이 아닌 연도별 부분 Snapshot을 공개 서비스에 쓰지 않도록 고정.
- 현행 Snapshot 부재(503)와 정상 빈 결과(200), 개별 사고 미존재(404) 구분.
- 사고 검색의 cause/place 추가, 총 6개 필드 검색 및 입력 안전성.
- 공식 화학사고 원천 링크를 15072446으로 수정.
- 기존 Reference Form 검색 어댑터를 포함한 어댑터 등록 보존.
- 사고 자유 텍스트와 CAS 물질 자동 동일성 연결 금지.

### 구현·병합 및 배포 기준점

| 대상 | PR / SHA 또는 ID |
|---|---|
| tai-api | [PR #602](https://github.com/taiengineering/tai-api/pull/602) — cf0af61cb9c734de0db3fa3cba40f93264a04f0b |
| tai-www | [PR #267](https://github.com/taiengineering/tai-www/pull/267) — f47235a9d1ccfcfb5e8632af5fb023dfca00a5c6 |
| Railway Production | deployment 7f2fd613-088f-4a4e-92bf-e4049561c52e (SUCCESS 보고) |
| Cloudflare Production | deployment f8b87130-2c27-4b5a-b004-6d354bb5377a (success 보고) |

**검증 보고**: WP-04 신규 42 + 관련 회귀 431 = 473 PASS. WP-05 통합 QA 5/5 PASS, WP 대상 91/91 PASS. 배포 후 API 및 웹 7개 Smoke PASS 보고. 전체 리포지토리의 기존 무관 실패가 0이라는 뜻은 아니다.

### 데이터 규모 (2026-10-12 시점 수집 현행 Snapshot 관측치)

| 원천 | Snapshot item 관측 수 |
|---|---:|
| EXT-037 | 7,189 |
| EXT-132 | 7,277 |
| EXT-165 | 1,143 |
| 합계 | 15,609 |

위 숫자는 **현행 원천행 수**이며 신규 OpenSearch 색인 문서 수, 유효 물질 수, 자동 갱신 주기나 현재 실시간 건수를 의미하지 않는다.

## 9. 운영 기준 및 책임 경계

- 공급기관/공공데이터: 원자료 제공. TAI는 수집·정규화·검색·UI 제공.
- TAI API: 원천별 수집/스냅샷 관리, 공개 read endpoint, Shared Search Adapter.
- TAI WWW: MSDS 보강 UI, 사고 검색·상세, 통합검색 유형 표시.
- Shared Search: 공통 정규화/색인/검색; 원천 문서의 상호 자동 병합 없음.
- LEG: 법률 적용성·의무 판정의 별도 SoT. 공공 API 정보로 LEG를 덮어쓰지 않음.
- 변경관리: 소스 Merge, Railway 배포, Cloudflare 배포, 운영 Snapshot 갱신, OpenSearch 색인 변경은 서로 구분해 관리한다.
- 신규 색인 운영 작업은 본 문서 작성 작업에 포함하지 않는다.

## 10. 근거 파일 색인

### API 수집/저장/읽기

- [EXT-037 contract](../../../services/ext037_chemical_safety/contract.py), [read](../../../services/ext037_chemical_safety/read.py), [sync](../../../services/ext037_chemical_safety/sync.py), [store](../../../services/ext037_chemical_safety/store.py)
- [EXT-132 contract](../../../services/ext132_hazardous_material/contract.py), [read](../../../services/ext132_hazardous_material/read.py), [sync](../../../services/ext132_hazardous_material/sync.py), [store](../../../services/ext132_hazardous_material/store.py)
- [EXT-165 contract](../../../services/ext165_chemical_accident/contract.py), [read](../../../services/ext165_chemical_accident/read.py), [sync](../../../services/ext165_chemical_accident/sync.py), [store](../../../services/ext165_chemical_accident/store.py)
- [CAS 보강 공개 라우터](../../../routers/public_chemical_enrichment.py)
- [화학사고 공개 라우터](../../../routers/public_chemical_accident.py)

### 검색 어댑터/등록

- [EXT037 Adapter](../../../services/shared_search/adapters/ext037_chem_safety.py)
- [EXT132 Adapter](../../../services/shared_search/adapters/ext132_hazardous.py)
- [EXT165 Adapter](../../../services/shared_search/adapters/ext165_chem_accident.py)
- [Production adapter binding](../../../services/shared_search/production_bindings.py)
- [Public Safety Search router](../../../routers/public_safety_search.py)

### WWW 코드 (별도 저장소)

- [MSDS Pages Worker](https://github.com/taiengineering/tai-www/blob/f47235a9d1ccfcfb5e8632af5fb023dfca00a5c6/workers/pages-live-worker.js)
- [화학사고 API 클라이언트](https://github.com/taiengineering/tai-www/blob/f47235a9d1ccfcfb5e8632af5fb023dfca00a5c6/src/lib/server/chemicalAccidents.js)
- [화학사고 목록](https://github.com/taiengineering/tai-www/blob/f47235a9d1ccfcfb5e8632af5fb023dfca00a5c6/src/pages/accident-cases.astro)
- [화학사고 상세 SSR](https://github.com/taiengineering/tai-www/blob/f47235a9d1ccfcfb5e8632af5fb023dfca00a5c6/src/pages/accident/chemical/%5Bdatano%5D.astro)
- [안전정보 통합검색](https://github.com/taiengineering/tai-www/blob/f47235a9d1ccfcfb5e8632af5fb023dfca00a5c6/src/lib/server/safetySearch.js)

---

**유지관리 주의**: 새로운 원천 필드·수집 범위·공개권한·검색 색인 기준·상세 URL이 바뀌면 이 정의서를 함께 갱신한다. 문서 생성은 운영 코드/DB/색인 변경을 동반하지 않는다.
