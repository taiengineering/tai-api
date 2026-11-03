---
class: plans
type: OBJECT_WORKPLAN
project: tai-safe
scope: bizinfo-program-event-content
id: PLAN-TAI-BIZINFO-OBJECT-WORKPLAN-001
version: 0.1
status: PROPOSED / DOC_A_GIT_VERIFIED
date: 2026-11-03
owner: TAI Safe
parent_plan: PLAN-TAI-BIZINFO-SEO-CONTENT-001
source_scope: BIZINFO_ONLY
---

# PLAN-TAI-BIZINFO-OBJECT-WORKPLAN-001 — 기업마당 지원사업·안전행사 콘텐츠 서비스 Object 실행계획

## 0. 문서 지위·선행조건

- 본 문서는 상위 기획서 `PLAN-TAI-BIZINFO-SEO-CONTENT-001`의 **하위 Object 실행계획**이며, **상위 기획서가 Git에 먼저 등록되어 GPT 독립검증을 통과해야 정본으로 등록**한다.
- 상위 기획서 DOC-A SOURCE_IV PASS 확인: 커밋 `c22941645f2c02f22502c1262b80568cc2bb7c75` (PR #756)
- Owner 지시: 기업마당 지원사업정보·행사정보만 1차 정보원; 2개 키 Railway 등록 보고; GPT=분석·설계·WO·IV / Claude Code=실행.
- 기존 `OBJ-DISCOVERY` 및 Shared Search 계획과 검색엔진은 교체하지 않는다. 대상 Repo 후보: `taiengineering/tai-api`(도메인/API·정본 문서)와 `taiengineering/tai-www`(공개 UI); MKT는 기존 콘텐츠 검수/채널 연결 계약만 참조.
- 이 계획은 코드 실행권/DB 변경권/배포권을 자동으로 주지 않는다. 구현/스키마/인덱스 반영/PR 병합/배포는 Gate별 Owner 승인 필요.
- API 실호출, Railway 환경변수의 실제 적용, 운영 인덱스, DB 적합성, 저작권 추가 허락 여부는 **미확인**. 이를 이미 완료된 사실로 적지 않는다.

## 1. Goal 및 Object 설계 공통 규칙

**Goal:** 산업안전 분야 기업마당 지원사업·행사를 자체 해설 콘텐츠로 전환하여 TAI Safe의 웹 검색 유입과 관련 고객 탐색을 늘리고, MKT용 검증된 소재를 확보한다.

**원칙:** Domain SoT ≠ Search Projection ≠ MKT 채널 발행; publication state ≠ application/event state. 공고/행사 양쪽에 공통 처리 자산을 적용하되 두 유형의 필드는 혼동하지 않는다. 공식 원문은 링크/출처로 보존하고 TAI 설명은 자체 작성한다. 모든 신규 기능은 이미 있는 TAI/MKT 공통 기능을 먼저 검토한다.

**Object 기술 최소 계약:** `OBJECT ID`, `PURPOSE`, `SCOPE`, `INPUT`, `OUTPUT`, `PUBLIC CONTRACT`(후보), `SOURCE OF TRUTH`, `CONSUMERS`, `DEPENDENCIES`, `STATE`, `MUTATION`, `HARD BLOCK`, `EXIT CRITERIA`, `EVIDENCE`, `OWNER`. `PUBLIC CONTRACT`에 나온 명칭은 후보이며 코드/DB 스키마로 확정되지 않았다.

## 2. Object Group / Object 목록

| Group | Object | 고유 책임 | 활용할 기존 자산 |
|---|---|---|---|
| Source Integration | OBJ-BZI-001 API Access | 기업마당 두 API의 읽기·키 보안·호출 오류 분리 | TAI API 서버/기존 수집 패턴 |
| Source Integration | OBJ-BZI-002 Source Normalizer | 공고/행사 고유 ID·기간·출처 표준화 | Shared Search/TAI Domain 정규화 패턴 |
| Validation | OBJ-BZI-003 Safety Relevance | 산업안전 관련성만 선택/제외 사유 기록 | 기존 검증 패턴, 신규 범용 AI 판단 금지 |
| Domain Lifecycle | OBJ-BZI-004 Record Lifecycle | 게시/접수/행사 종료/변경/확인시각 관리 | 기존 상태·버전·감사 패턴 재사용 검토 |
| Editorial Validation | OBJ-BZI-005 Rights & Editorial Gate | 독립 해설, 사실·권리·발행 검수 | MKT 검증/승인/버전 관리 패턴 |
| Presentation | OBJ-BZI-006 Public SEO Pages | 독립 목록·상세·공식 링크·원문 구별 | tai-www Astro SSR/상세 패턴 |
| Discovery | OBJ-BZI-007 Shared Search Projection | 공통 검색에 별도 유형 편입 | Domain Adapter/Indexer/OpenSearch |
| Marketing Boundary | OBJ-BZI-008 MKT Content Handoff | 승인된 소재의 MKT 전달 계약 | MKT 콘텐츠 관리·검증·관측 |
| Observation | OBJ-BZI-009 Quality & Attribution | 최신성/권리/유입/CTA 품질 확인 | 기존 GSC·GA4·검색 분석 자산 |

**새 엔진/새 검색 DB/새 Railway 서비스는 Object가 아니다.** 신규 Domain 데이터 저장이 필요하더라도 저장방식은 Stage B의 별도 Owner Gate에서 확정한다.

## 3. Object 상세 계약(9개)

### OBJ-BZI-001 — Bizinfo API Access

- **PURPOSE:** 서비스키가 서버 밖으로 노출되지 않게 지원사업·행사 API를 읽는다.
- **SCOPE:** GET 호출, 페이지/응답 크기 제한, 타임아웃·인증·쿼터·실패 분리, 키 마스킹.
- **INPUT:** source_kind=`PROGRAM|EVENT`, pagination, 서버 전용 키 이름 `BIZINFO_API_KEY|BIZINFO_EVENT_API_KEY`.
- **OUTPUT:** `SourceBatch(items, provider, retrieved_at, error_code)` 후보.
- **PUBLIC CONTRACT:** `fetch_source_batch(source_kind, page, size)` (내부 호출, 외부 공개 API 아님).
- **SOURCE OF TRUTH:** 기업마당 공식 API; 키는 Railway 서버 변수(Owner 등록 보고, 실적용 미확인).
- **CONSUMERS:** OBJ-BZI-002; **DEPENDENCIES:** 없음(단, Owner read-only 호출 승인).
- **STATE:** NOT_STARTED / SOURCE_DOCS_VERIFIED, LIVE_SMOKE_HOLD.
- **MUTATION:** DOC stage NONE; 구현 승인 후 코드 변경만; 데이터 저장 금지.
- **HARD BLOCK:** 키 출력·Git 커밋·브라우저 요청·전체 일괄 수집·새 서비스 생성 금지.
- **EXIT CRITERIA:** 양 API 실응답 파싱, 인증실패/빈응답/페이지 테스트, 로그에 키 0노출.
- **EVIDENCE:** 마스킹된 호출 결과 스키마, 최소 read-only 테스트, 변경 파일 목록; **OWNER:** TAI API.

### OBJ-BZI-002 — Canonical Source Normalizer

- **PURPOSE:** 원천 공고와 행사를 중복 없이 구별한다.
- **SCOPE:** `PROGRAM:pblancId` / `EVENT:eventInfoId`, 날짜 문자열 파싱, 링크 검증, null/다중형태 방어, 원문 필드 기반 확인시각 기록.
- **INPUT:** OBJ-BZI-001의 SourceBatch; **OUTPUT:** `NormalizedSourceRecord` 후보.
- **PUBLIC CONTRACT:** `normalize_bizinfo_record(kind, raw)` (순수 로직 후보).
- **SOURCE OF TRUTH:** 기업마당 고유 ID; **CONSUMERS:** OBJ-BZI-003/004; **DEPENDENCIES:** OBJ-BZI-001.
- **STATE:** SPEC_DRAFT; **MUTATION:** 원본 수정 없음, 최초 단계 저장 없음.
- **HARD BLOCK:** 제목/URL만으로 임의 합치기, ID 추정, 출처 필드 바꼸쓰기 금지.
- **EXIT CRITERIA:** ID 안정성, 날짜/URL 누락, API `jsonArray.item` 단일·배열 응답에 안전하게 대응.
- **EVIDENCE:** 정규화 테스트/샘플(원문 민감정보 제외); **OWNER:** TAI API.

### OBJ-BZI-003 — Safety Relevance Selector

- **PURPOSE:** 실제 TAI 고객과 관련된 안전정보만 후보로 통과시킨다.
- **SCOPE:** 산업재해 예방, 안전설비, 위험공정, 안전보건관리체계, 안전교육/설명회 관련성 근거/제외 이유 보존.
- **INPUT:** NormalizedSourceRecord; **OUTPUT:** `IN_SCOPE|OUT_OF_SCOPE|REVIEW_REQUIRED`, 근거.
- **PUBLIC CONTRACT:** `review_relevance(record)->decision` 후보.
- **SOURCE OF TRUTH:** Owner가 승인한 분류 기준 + 원문 근거; **CONSUMERS:** OBJ-BZI-004/005; **DEPENDENCIES:** OBJ-BZI-002.
- **STATE:** POLICY_PROPOSED; **MUTATION:** 검토결과만, 원본 정보 불변.
- **HARD BLOCK:** 일반 창업/금융/수출 공고 무차별 수집/발행, AI만으로 최종 게시 판정 금지.
- **EXIT CRITERIA:** 포함/제외/애매한 사례 3분류가 가능하고 애매한 사례는 자동발행 불가.
- **EVIDENCE:** 분류표와 실제 표본의 제외 이유; **OWNER:** TAI 서비스 기획/검증.

### OBJ-BZI-004 — Source Record Lifecycle

- **PURPOSE:** 기간과 변경에 따른 현재 상태를 오도하지 않는다.
- **SCOPE:** publication_status와 application_status/event_status를 분리; `last_checked_at`, `source_updated_at`, `notice_changed` 보존; 수집 실패 ≠ 삭제.
- **INPUT:** 정규화된 승인 후보와 관측 시각; **OUTPUT:** `StatusSnapshot` 후보.
- **PUBLIC CONTRACT:** `resolve_business_status(kind, dates, verified_change)` 후보.
- **SOURCE OF TRUTH:** 관리 Domain(정확한 기존 테이블/신규 저장 여부는 Stage B HOLD); **CONSUMERS:** OBJ-BZI-005/006/007.
- **DEPENDENCIES:** OBJ-BZI-002/003, Owner STORAGE_GATE.
- **STATE:** STORAGE_MODEL_HOLD; **MUTATION:** DOC NONE, 코드/DB/운영 적용은 각 승인 후.
- **HARD BLOCK:** 확인되지 않은 예산 소진/취소 단정, 미수신을 삭제로 처리, 게시중을 접수중으로 오인 금지.
- **EXIT CRITERIA:** 예정/접수중/마감/예산소진/확인필요 및 행사의 접수·개최/종료 구분; 변경 표시가 상태와 독립.
- **EVIDENCE:** 날짜 경계/변경/원천 장애 상태 테스트, 소유 저장소 비교표; **OWNER:** TAI Domain.

### OBJ-BZI-005 — Rights & Editorial Approval

- **PURPOSE:** 안전한 사실 활용과 TAI만의 독창적 실무 해설을 보장한다.
- **SCOPE:** 사실·링크·확인시각 검증, 권리 확인, 자체 체크리스트·분석·비교, 사람 승인. 기존 MKT 기능은 **재사용 후보**로만 검토.
- **INPUT:** OBJ-BZI-003/004 검토 후보 + TAI 해설 초안; **OUTPUT:** `EditorialDecision`, approved-content 후보.
- **PUBLIC CONTRACT:** `validate_editorial(candidate)->FACT/RIGHTS/EDITORIAL gates` 후보.
- **SOURCE OF TRUTH:** 기업마당 공고(사실), TAI 해설(독립 저작물), 별도 저작권 확인 근거; **CONSUMERS:** OBJ-BZI-006/008.
- **DEPENDENCIES:** OBJ-BZI-003/004; **STATE:** POLICY_PROPOSED / RIGHTS_CLARIFICATION_OPEN.
- **MUTATION:** approved-content만 검수 후 변화, 자동 PUBLISHED 불가.
- **HARD BLOCK:** 기업마당 원문/그림/표/PDF를 권리 확인 없이 복제·수정 발행 금지; AI 파라프레이징만으로 독창성 간주 금지.
- **EXIT CRITERIA:** 모든 공개 후보에 출처·사업관련 해설·실무 도움·확인시각·승인 기록.
- **EVIDENCE:** 검수 규칙/샘플 독립 해설·실제 권리 확인 기록; **OWNER:** TAI 콘텐츠 책임 + MKT 협력.

### OBJ-BZI-006 — Public SEO Page

- **PURPOSE:** 사업장이 찾을 수 있는 독립 상세 콘텐츠를 제공한다.
- **SCOPE:** `support-programs`/`safety-events` 목록과 상세, 메타·canonical·원공고·최근확인·변경/마감 표시.
- **INPUT:** OBJ-BZI-005 승인 콘텐츠 + OBJ-BZI-004 status; **OUTPUT:** SSR HTML/상세 URL.
- **PUBLIC CONTRACT:** `resolve_detail(kind, canonical_id)` / URL proposal.
- **SOURCE OF TRUTH:** TAI Domain; **CONSUMERS:** 일반 검색엔진/방문자/OBJ-BZI-007; **DEPENDENCIES:** OBJ-BZI-004/005.
- **STATE:** DESIGN_ONLY; **MUTATION:** Doc stage NONE, FE 코드 단계는 별도 Owner Gate.
- **HARD BLOCK:** `/safety-search`의 `noindex`를 그대로 상세에 적용, 공고만 복제한 업은 페이지 대량 색인, 검수 전 공개 금지.
- **EXIT CRITERIA:** 독창적 콘텐츠·명확한 날짜·공식 링크·모바일 표시·적절한 index 정책, 404/장애 구분.
- **EVIDENCE:** 파일 변경/FE 테스트/실제 HTML·robots 확인(개발 승인 후); **OWNER:** TAI WWW.

### OBJ-BZI-007 — Shared Search Adapter

- **PURPOSE:** 정부지원사업·안전행사를 기존 통합검색에서 발견하게 한다.
- **SCOPE:** 두 독립 `object_type` 후보를 기존 Shared Search의 Domain Adapter, 공개 allowlist, sections, WWW GROUP_DEFS에 연결.
- **INPUT:** 검수된 공개 Canonical 콘텐츠; **OUTPUT:** 기존 `SearchResult` 스키마 (`object_type`, `canonical_id`, `title`, `summary`, `public_url` 등).
- **PUBLIC CONTRACT:** `type=support_program|safety_event` 후보(기존 type 필터 확장).
- **SOURCE OF TRUTH:** TAI Domain; Shared Search는 파생 색인; **CONSUMERS:** 기존 안전정보 통합검색.
- **DEPENDENCIES:** OBJ-BZI-004/005/006; 기존 `shared_search` F2/F3.
- **STATE:** CONTRACT_HOLD; **MUTATION:** 별도 검색엔진/DB 신설 불가, 검색코드·색인 변경은 승인 후.
- **HARD BLOCK:** `KNOWLEDGE` 유형 오염, 타 도메인 노출, 프론트 임의 검색/랜킹, 검수 전 검색노출 금지.
- **EXIT CRITERIA:** 검색 결과에서 정확히 분리, canonical 상세 이동, 이전 유형 회귀 없음, 오류와 0건 구분.
- **EVIDENCE:** 계약·색인·FE 단위 테스트와 독립 IV, 실제 운영색인 변경은 별도 승인; **OWNER:** TAI Search.

### OBJ-BZI-008 — MKT Editorial Handoff

- **PURPOSE:** 승인된 안전지원 콘텐츠를 블로그 제작자가 활용할 수 있게 한다.
- **SCOPE:** 사실카드/독립 해설/원천 링크/사용 범위/최종 확인시각 전달 계약. 기존 MKT 관리·검수 자산 우선 검토.
- **INPUT:** OBJ-BZI-005 approved content; **OUTPUT:** `MktSourcePackage` 후보.
- **PUBLIC CONTRACT:** `export_approved_content_source(id)` 후보.
- **SOURCE OF TRUTH:** TAI(사업정보) + MKT(채널 원고), 각각 독립; **CONSUMERS:** MKT 콘텐츠 관리.
- **DEPENDENCIES:** OBJ-BZI-005, Owner MKT_BOUNDARY_GATE; **STATE:** CONTRACT_ONLY.
- **MUTATION:** MKT 기존 9,008건 및 채널 콘텐츠는 손대지 않음.
- **HARD BLOCK:** 기존 Q&A에 강제 적재, 블로그/유튜브 자동 초안 생성·게시, MKT DB 직접 갱신 금지.
- **EXIT CRITERIA:** 한 공고에서 출처·검수 완료된 소재를 독립적인 블로그 기획 입력으로 전달 가능.
- **EVIDENCE:** JSON 계약 예시·MKT 경계 검토 결과; **OWNER:** TAI/MKT 계약 공동, 실행은 MKT 별도 WO.

### OBJ-BZI-009 — Quality & Attribution

- **PURPOSE:** 공고 최신성과 검색·방문·고객 행동 효과를 관측한다.
- **SCOPE:** 소스 실패/오래된 확인일/권리 보류/검색 상세 이동/공식 원공고 클릭/관련 TAI CTA 등.
- **INPUT:** 기존 관측 이벤트·검색유입 데이터·상태 경고; **OUTPUT:** 최소 품질/성과 요약.
- **PUBLIC CONTRACT:** `quality_event` / `traffic_attribution` 기존 계약 재사용 후보.
- **SOURCE OF TRUTH:** 각 Domain 상태, 기존 GSC/GA4 또는 MKT 분석 자산; **CONSUMERS:** Owner, 향후 운영정책.
- **DEPENDENCIES:** OBJ-BZI-004/006/007, 필요한 읽기 권한; **STATE:** DESIGN_ONLY.
- **MUTATION:** 새 대시보드·측정 엔진 임의 신설 금지.
- **HARD BLOCK:** 검증되지 않은 방문/전환 수치, 과도한 반복 감사, 문서화 목적의 작업 금지.
- **EXIT CRITERIA:** 원천 확인 실패와 실제 검색/방문 성과를 최소 단위로 판단 가능.
- **EVIDENCE:** 기존 분석 이벤트 재사용 매핑·실측 기준(가능 시); **OWNER:** TAI + MKT 관측.

## 4. 의존성 및 최소 실행 순서

```text
[DOC-1 기획서 Git 등록+GPT IV]
             |
             v
[DOC-2 본 Object 계획 Git 등록+GPT IV]
             |
             v
[G-SRC 소스 읽기 실행 승인]
   OBJ-BZI-001 -> OBJ-BZI-002 -> OBJ-BZI-003
                           |
                           v
[G-STORAGE 소유/저장 모델 Owner 결정]
                     OBJ-BZI-004
                           |
                           v
[G-EDITORIAL 권리/검수 Owner 결정]
                     OBJ-BZI-005
                           |
                           v
[G-CODE FE Owner 승인] OBJ-BZI-006
                           |
                           v
[G-SEARCH 검색 계약·색인 Owner 승인] OBJ-BZI-007
                           |
                           +--> [G-MKT 별도 승인] OBJ-BZI-008
                           +--> OBJ-BZI-009 (기존 측정 재사용)
```

**초기 실행의 최소 목표:** 먼저 두 API의 좋은 범위 읽기와 응답 확인 → 안전 관련 소수 공고 선별 → 권리 확인된 독립 해설 샘플 → 공개 상세 → 기존 검색에 연결. 수집량/채널 게시량을 목표로 삼지 않는다.

## 5. Stage별 WO·승인 계획

| Stage | 작업 유형 | 대상 Object | 예상 Repo/경계 | 새 DB | Owner Gate | EXIT |
|---|---|---|---|---|---|---|
| DOC-1 | 본 기획서 Git 등록 (docs-only) | Foundation | tai-api/docs | NO | 이번 명시 지시 범위 | 커밋 SHA·내용 GPT IV |
| DOC-2 | Object 계획 Git 등록 (docs-only) | 본 문서 | tai-api/docs | NO | DOC-1 IV 통과 | 커밋 SHA·내용 GPT IV |
| SRC-A | API 응답·기존 수집패턴 read-only 검증 | 001·002 | TAI API | NO | 별도 실행 승인 | 스키마·에러·보안 확인 |
| DATA-A | 저장 모델/소유/권리·상태 계약 결정 | 003·004·005 | TAI Domain/MKT 계약 | HOLD | STORAGE/RIGHTS 승인 | 기존 저장 재사용 여부 확정 |
| WEB-A | 소수 공개 목록·고유 상세, 검수 gate | 005·006 | tai-www + 필요 BE | HOLD | CODE 승인, 배포 별도 | 공고/행사 공개 품질 검증 |
| SEARCH-A | 기존 Shared Search만 확장 | 007 | tai-api/tai-www | NO 우선 | 검색 계약·색인 승인 | 검색 유형·상세 링크 PASS |
| MKT-A | 승인된 소재 패키지 전달 | 008 | TAI/MKT 계약 | NO 우선 | 별도 MKT 승인 | 블로그 자동게시 없음 |
| OBS-A | 기존 관측 재사용 | 009 | 기존 GSC/GA4/MKT | NO 우선 | 필요한 읽기 승인 | 성과/최신성 관측 가능 |

## 6. 판단해야 할 Owner Gates

- `DOC_GATE`: 기획서와 Object 계획서를 **순서대로 Git 등록**하는 문서 작업은 허용. 문서 등록이 코드 승인이 되지 않음.
- `SRC_GATE`: 기업마당 키가 적용된 서버에서 키를 노출하지 않는 최소 read-only 실호출 승인. 호출 허용은 보관/공개 승인과 다름.
- `STORAGE_GATE`: 어느 기존 저장 구조가 source ID·상태·해설 승인·버전을 소유하는지 결정. 신규 테이블/DB가 필요하면 별도 승인.
- `RIGHTS_GATE`: 원천 사실/링크 외 원문 재게재·첨부자료/이미지 활용 여부에 관한 제공기관 확인.
- `CODE_GATE`: 수정할 파일·대상 Object·테스트·Draft PR 범위를 승인. 마이그레이션은 별도.
- `INDEX_GATE`: 신규 검색 유형 계약, 운영 인덱스 반영, 재색인 승인 분리.
- `MERGE_GATE`/`DEPLOY_GATE`: 실제 PR 병합/운영 배포는 별도. Owner의 문서 등록 요청으로 자동 승인되지 않음.

## 7. 회귀·안전 검증 및 명확한 제외

- 키/사용자 정보 Git·브라우저·로그 유출 0.
- 기업마당 원천 외 수집 대상 0, 무관한 지원사업·행사 대량 발행 0.
- `KNOWLEDGE`·LEG·CHEM·기존 지식센터 9,008건에 변경 0.
- 기업마당 원문 무단 재게시 0, 자체 해설 없는 얼은 SEO 페이지 발행 0.
- 종료 공고를 모집 중으로 표시 0, 확인 불가 상태는 자동 OPEN 판정 0.
- 새로운 검색엔진, 별도 Railway 서비스, 새 자동게시 엔진, 무단 DB/RLS 변경 0.
- 반복적인 전수 문서 검사, 대규모 테스트/전체 재색인 대신 해당 Object에 필요한 증거만 수집.

## 8. 기획·설계 근거

- 상위 계획(본 계획 등록 전 검증 필요): `docs/PLAN-TAI-BIZINFO-SEO-CONTENT-001.md`
- 기존 검색 계획: `docs/PLAN-MKT-PUBLIC-SEARCH-OBJECT-001.md`
- 공통 검색 원칙: `docs/search/TAI_SHARED_SEARCH_CONSTITUTION_v1.md`
- 공통 검색 코드: `services/shared_search/indexer.py`, `production_bindings.py`, `result.py`, `routers/public_safety_search.py`
- WWW 검색 코드: `src/lib/server/safetySearch.js`, `src/pages/safety-search.astro` in `taiengineering/tai-www`
- MKT 콘텐츠 재사용 참고: `45cminc/marketing/apps/api/marketing_knowledge_content_admin.py`
- 지원사업 API: https://www.bizinfo.go.kr/apiDetail.do?id=bizinfoApi
- 행사 API: https://www.bizinfo.go.kr/apiDetail.do?id=bizinfoEventApi
- 기업마당 저작권: https://www.bizinfo.go.kr/biz/bizd/selectBIZD120View.do

## [Owner용 쉬운 설명 및 방향 점검]

1. **원래 목표:** 산업안전과 관련된 정부지원사업·행사 소식을 독자적인 실무 해설로 바꾼 TAI Safe의 방문자와 잠재고객을 늘립니다.
2. **이번 작업:** 이미 있는 기능은 그대로 활용하고, 무엇을 어떤 순서로 확인·구현할지 9개 책임 단위로 나누어 계획합니다.
3. **완료 후 변화:** 개발자가 한 번에 큰 시스템을 만들지 않고 필요한 범위만 순차적으로 진행할 기준이 생깁니다. 고객 화면과 운영 데이터는 문서 단계에서 바뀌지 않습니다.
4. **하지 않는 작업:** 기존 지식센터 재편집, 블로그 제작·게시, 전면 검색 재구축, 별도 수집엔진·DB·Railway 신설, 무승인 배포는 하지 않습니다.
5. **원기획 일치 여부:** **부분일치.** 확인한 근거는 본 기획서, 기존 Public Search Object Plan, Shared Search 헌법·코드, MKT 아키텍처/콘텐츠 관리 코드입니다. 공통 검색 재사용은 일치하지만 새 지원사업·행사 관리 Domain의 최종 소유/DB 계약은 아직 확정되지 않았습니다.
6. **방향 이탈 위험:** 데이터부터 대량 적재하거나 매체별 자동게시를 개발하는 것은 목적과 다릅니다. 검증된 공고 소수와 독립 해설·검색유입 성과부터 확인하고 확장은 별도 승인합니다.
