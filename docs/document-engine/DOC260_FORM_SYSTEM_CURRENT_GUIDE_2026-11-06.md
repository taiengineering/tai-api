---
title: "TAI Safe DOC260 서식 서비스 운영·개발 가이드"
project: "TAI Safe / DOC260"
date: "2026-11-06"
status: "CURRENT_STATE_HANDOFF"
owner_scope: "DOC260"
source_of_truth: "GitHub main source + approved Owner decisions"
change_type: "DOCUMENTATION_ONLY"
---

# DOC260 서식 서비스 가이드 — 로직·구성·작업 이력·운영 인계

> 기준일: **2026-11-06 KST**. 이 문서는 **현재 동작과 이미 수행한 작업을 인계**하기 위한 가이드다. 신규 기능·권한 개방·배포를 승인하는 문서가 아니다.
> 최신 코드가 이 문서와 충돌하면 해당 코드·Owner의 최신 결정을 우선 확인한다. 오래된 설계서의 숫자와 Gate를 현행 상태로 복원하지 않는다.

## 0. 30초 요약

TAI Safe의 문서 260종은 모두 분류되어 있다. **260종을 모두 웹에서 작성하는 것이 목표가 아니다.**
고객에게는 문서 성격과 승인 상태에 맞춰 ① 기존 데이터로 자동 생성, ② 직접 웹 작성·저장·PDF, ③ 기관 공식 원본 HWP 다운로드, ④ 외부기관 처리 안내, ⑤ 제품 범위 제외 중 적합한 경로를 제공한다.

- **자동 작성:** 완료된 점검(INSPECTION)·TBM 데이터를 사용하는 기존 AUTO_SOURCE 경로가 있다. 260종 카탈로그와의 1:1 자동화 매핑 건수는 확정되지 않았다. 따라서 AUTO_READY=0이라고 판단하지 않는다.
- **웹 작성:** A_INTERNAL **109종**으로 분류된다. 이는 정책상 대상 수이며 실제 즉시 사용 가능 수와 다르다. 기존 커버리지 판정상 기술 준비 **62종**, 증적 승인 보류 **45종**, 스키마 후보 승인 보류 **2종**이다.
- **공식 원본:** B_OFFICIAL **16종** 중 검증된 원본 **5종** 다운로드 허용, 원본 불일치 **6종** 차단, 동일성/Owner HOLD **4종**, 원본 없는 **1종**은 404다.
- **미확정:** U_UNRESOLVED **83종**은 기존 접근 유지 정책이다. Owner Packet은 이미 작성되었고, 42종 결정 준비 / 1종 충돌 / 40종 근거 부족으로 분리되어 있다.
- **외부·제외:** E_EXTERNAL **9종**은 별도 안내·기존 자료 접근, F_SCOPE_OUT **43종**은 신규 제공 대상이 아니다.
- **파이프라인:** 기존 작성·첨부·서명·저장·확정·PDF·문서함 경로를 재사용한다. DOC260 OBJ04 R2 완료는 실행 보고 기준이며, 운영 반영 여부는 기능별 배포 증거로 구분한다.
- **2026-11-06 공식서식 배포:** API PR #789와 Admin PR #208은 GitHub 병합 확인; Railway/Cloudflare 운영 반영은 실행자가 SUCCESS 보고했다. 이 가이드 작성 과정에서 라이브 인증 다운로드를 재현하지는 않았다.

## 1. 구분표와 실제 서비스 동작

| route_group | 수 | 고객에게 제공하는 원칙 | 상태 판정의 주의점 |
| --- | ---: | --- | --- |
| A_INTERNAL | 109 | 승인된 Runtime Schema로 웹 작성·저장·출력; 필요한 경우 사업장 자동입력 | web_edit_allowed=true만으로 즉시 작성/최종확정 완료가 아니다 |
| B_OFFICIAL | 16 | **기관 공식 원본 다운로드**가 목표; 공식 파일을 임의 변형하거나 자체 웹서식으로 대체하지 않는다 | 원본 동일성 검증·공개 상태·Storage 파일 존재 모두 필요 |
| U_UNRESOLVED | 83 | 기존 고객 접근 그대로 유지, 확인된 외부 제출 경로는 안내 | 정책 미확정을 이유로 기존 작성·다운로드 기능을 일괄 차단하지 않는다 |
| E_EXTERNAL | 9 | 외부 작성·제출처 안내, 기존 제공 자료 경로 유지 | 외부기관에서 접수됐다는 의미는 아니다 |
| F_SCOPE_OUT | 43 | 신규 개발·제공 대상에서 제외 | 고객의 기존 접근 통제 변경은 별도 Gate |

**합계: 109 + 16 + 83 + 9 + 43 = 260.** 실측 기준은 현재 API main의 [r2_route_policy.py](../../services/document_engine/r2_route_policy.py) 내부 _POLICY / policy_count()이다.

관련 용어:
- route_group: 카탈로그의 제품 제공 유형.
- investment_decision: KEEP / HOLD / STOP 결정.
- official_status: B_OFFICIAL 원본 제공 정책 (CONDITIONAL_APPROVED / HOLD / MISMATCH).
- schema_availability: READY_FOR_EDIT / PREPARING / NO_SCHEMA 등 실제 Runtime Schema 상태.
- source_file_available: Storage에 해당 doc_id의 HWP 파일이 조회되는지 나타내는 목록 정보. **원본 서식의 법적 동일성에 대한 검증은 아니다.**
- file_url: 국가법령정보센터 등 외부 원본 참조 URL. **Storage 파일 보유 증거가 아니다.**

## 2. 현재 아키텍처·책임 경계

### 2.1 사용자 흐름

1. 고객 서식 목록에서 문서 검색: **GET /document-forms** → document_forms DB + route policy + 스키마 상태 + Storage 존재 여부를 합쳐 목록에 표시.
2. 문서 상세: **GET /document-engine/catalog/{doc_id}** → catalog, runtime.availability, runtime.can_create, runtime.provision_policy, fields, checklists, evidence_fields 및 export formats 반환.
3. 웹 작성 대상: 승인된 Runtime Schema가 있으면 기존 작성기를 사용해 입력하고, 문서 초안을 생성·저장·복원·출력한다.
4. 공식 원본 대상: 승인된 B_OFFICIAL 문서는 **GET /document-forms/{doc_id}/source-file**로 원본 파일만 받는다. 승인/파일 없음에는 기존 차단·안내를 적용한다.
5. 완료된 현장 기록에서 자동 문서: **GET /document-engine/auto-documents** 및 preview/pdf 경로는 별도 AUTO_SOURCE read model을 쓴다. 문서 260종의 웹 작성률과 합산하지 않는다.
6. 제출 의무의 발생·적용 판단은 LEG 책임이다. DOC260은 LEG가 전달한 사실을 사용하고 자체적으로 법률 적용 판정을 중복 수행하지 않는다.

### 2.2 코드 지도 (현행 main 기준)

| 책임 | 저장소 경로 / 함수 | 핵심 역할 |
| --- | --- | --- |
| 260종 정책 | tai-api/services/document_engine/r2_route_policy.py | _POLICY, _OFFICIAL_STATUS, get_provision_policy(), policy_count() |
| 목록 Read Model | tai-api/services/document_forms_service.py | list_document_forms(), _enrich_with_availability(), _enrich_with_source_file_availability() |
| 목록 API·원본 다운로드 | tai-api/routers/document_forms.py | GET /document-forms; GET /document-forms/{doc_id}/source-file |
| 원본 파일 경로 및 존재 조회 | tai-api/services/document_engine/source_file_allowlist.py | get_verified_path(), list_available_doc_ids() |
| Runtime Schema 해석 | tai-api/services/document_engine/catalog_resolver.py | resolve_catalog_runtime_schema() |
| 문서·카탈로그 API | tai-api/routers/document_engine_api.py | /catalog, /documents 생성·조회·저장·확정, /auto-documents |
| 최종 확정 | tai-api/services/document_confirm_svc.py | confirm_document_atomic(): 스냅샷/증적/Archive의 원자적 확정 |
| AUTO_SOURCE | tai-api/services/document_engine/auto_source_readmodel.py | 완료된 점검·TBM 목록, 권한·완료 상태 기반 read model |
| 고객 서식 화면 | tai-admin/vue3/src/pages/document-forms/index.vue | 목록, 편집, 저장, 파일 다운로드 및 안내 |
| 목록·진입 분기 | tai-admin/vue3/src/pages/document-forms/useDocumentFormsList.ts | openCatalogDetail(), OPENED_OFFICIAL_ONLY 등 |
| 편집 상태 | tai-admin/vue3/src/pages/document-forms/useDocumentFormsEditor.ts | 승인 Schema, 입력값, isEditorReady |
| 저장·출력 | tai-admin/vue3/src/pages/document-forms/useDocumentFormsGenerate.ts | 문서 초안, PATCH 저장, 출력 |
| 버튼·안내 계약 | tai-admin/vue3/src/utils/document-formsFormat.ts | shouldShowSourceFileDownload(), shouldShowFileRef(), submissionCategoryNote() |

저장소:
- API: https://github.com/taiengineering/tai-api
- Admin: https://github.com/taiengineering/tai-admin

### 2.3 데이터·보관

- 카탈로그: document_forms (doc_id는 DOC-... 식별자; 내부 id는 UUID).
- 편집 가능 여부: runtime_form_schema.status가 APPROVED_FOR_RUNTIME_USE이고 resolver가 유일한 활성 Schema를 해석해야 한다.
- 입력·증적: Runtime fields, checklists, evidence의 개별 승인·무결성 계약을 따른다. CANDIDATE는 임의 승격하지 않는다.
- 임시 작성 및 출력: 기존 runtime document/renderer 경로 사용.
- 확정본: confirm_document_atomic()의 원자적 확정 및 runtime_document_archive 등 기존 보관 자산 재사용.
- 공식 원본: Supabase Storage **form-originals** bucket의 **doc_forms/{doc_id}.hwp** 경로. 고객은 Storage 경로 자체가 아닌 인증된 API로 다운로드한다.
- 인증·권한: 원본 다운로드 API는 회원 인증을 요구한다. 작성·조회·자동문서에서도 기존 회사/사업장 scope를 유지한다.
- 운영 자산: Railway(tai-api), Cloudflare Pages(tai-admin/safe.taieng.co.kr), Supabase(DB/Storage). 배포 시각과 실행 SHA는 개별 운영 기록을 따른다.

## 3. 서식별 로직과 승인 기준

### 3.1 AUTO — 기존 현장 데이터 기반 자동문서

AUTO_SOURCE는 별도 경로다. 데이터 원천은 **INSPECTION**과 **TBM**, 각각 기존 Fetcher/Generator를 재사용한다. 완료 상태와 회사·사업장 접근권한을 확인한 뒤 미리보기/출력을 허용한다. 목록 자체는 읽기 전용(Zero persistence)이다.

- GET /document-engine/auto-documents?source_type=ALL|INSPECTION|TBM
- GET /document-engine/auto-documents/{source_type}/{source_id}/preview
- GET /document-engine/auto-documents/{source_type}/{source_id}/pdf

AUTO_SOURCE 구현은 존재하지만, **DOC260 260종과 자동문서가 몇 대 몇으로 연결되는지는 현재 확정된 전수 매핑 자료가 없다.** 이를 근거 없이 AUTO_READY=0 혹은 109로 기록하지 않는다.

### 3.2 WEB_EDIT — 내부 작성 서식

- 정책상 A_INTERNAL이면 web_edit_allowed=true다.
- 실제 작성 버튼의 조건은 **availability=READY_FOR_EDIT, can_create=true, active_schema_id 존재, active_schema_status=APPROVED_FOR_RUNTIME_USE, unsupportedReason 없음** 등 기존 편집기 조건을 만족해야 한다.
- PREPARING은 스키마 후보가 있다는 뜻이며 승인 완료가 아니다. NO_SCHEMA는 바인딩된 스키마가 없는 경우다.
- 사업장 정보 자동 채움, 번호/날짜/측정/서명/사진/첨부, 임시 저장·복원, HTML/PDF, 확정·보관은 기존 구현 사용.
- 현재 분석 기준 A_INTERNAL 109종: 기술 준비 62 / 증적 승인 보류 45 / 스키마 **CANDIDATE** 2. 마지막 2종 DOC-CON-LAW-015와 DOC-SERA-008은 DB에 후보 스키마가 있으므로 ‘스키마 없음’이 아니라 ‘미승인’으로 관리한다.
- 증적 승인기관 권한 SUSPENDED 이슈를 기능 로직으로 우회하거나 일괄 승인하지 않는다.

**현행 레거시 호환 주의:** useDocumentFormsList.ts에는 B_OFFICIAL이더라도 runtime.can_create=true이면 기존 편집 흐름을 보존하는 분기가 있다. 제품 원칙은 ‘공식서식은 원본 다운로드’지만 이 기존 호환 동작을 이 문서만으로 제거하거나 이미 완전히 차단됐다고 표현하면 안 된다. 실제 고객 영향이 있는 통제 변경은 별도 Owner Gate가 필요하다.

### 3.3 B_OFFICIAL — 공식 원본 다운로드

제품 원칙: **공식 기관 서식은 자체 웹폼 생성으로 대체하지 않고, 검증된 공식 원본을 다운로드한다.**

서버: get_source_file()에서 doc_id 형식 → 제공 정책 → 활성 문서 → Storage 조회. B_OFFICIAL은 official_status가 **CONDITIONAL_APPROVED**일 때만 허용하고 나머지는 404. 파일 없음 404와 Storage 장애 503을 구분한다. frontend의 shouldShowSourceFileDownload() 역시 같은 조건을 쓴다.

**2026-11-06 배포 후 분류(16종):**

| 상태 | 종수 | 문서 | 제공 |
| --- | ---: | --- | --- |
| 원본 동일성 PASS / CONDITIONAL_APPROVED | **5** | DOC-FAC-020, 022, 025, 026, 027 | 기존 다운로드 API 경로 허용 |
| 동일성 미확정 / HOLD | **1** | DOC-CHEM-017 | 다운로드 보류 |
| Owner HOLD | **3** | DOC-FAC-024, 029, DOC-OSH-065 | 다운로드 보류 |
| 원본 불일치 / MISMATCH | **6** | DOC-CHEM-015, DOC-FAC-031~035 | 다운로드 404 |
| 원본 파일 없음 | **1** | DOC-FAC-019 | 정책상 CONDITIONAL_APPROVED지만 Storage 파일 부재로 404 |

위 합계 = 5+1+3+6+1=16. **배포된 코드에서 현재 허용 분기는 6종이 아니라 5종의 파일 보유 + FAC-019의 파일 미존재를 반영한 결과**다.

2026-11-06 PR [API #789](https://github.com/taiengineering/tai-api/pull/789) / [Admin #208](https://github.com/taiengineering/tai-admin/pull/208)에서 MISMATCH 6종과 CHEM-017 HOLD를 반영했다. 별도 차단 엔진을 추가하지 않고 기존 Gate 2b를 재사용했다.

**중요 예외:** DOC-FAC-019는 아직 CONDITIONAL_APPROVED이므로 **나중에 Storage 파일이 업로드되면 검증 전에도 기존 정책 조건을 통과할 수 있다.** 파일 업로드·교체 전 정확한 공식 원본인지 검증하고 Owner 운영 승인을 받아야 한다.

Batch01 원본 조사: PASS=5, PLAUSIBLE=2로 보고된 이력 중 이번 B_OFFICIAL 상태에는 CHEM-017 1종이 HOLD로 반영되었다. MISMATCH=6, UNRESOLVED=1. Batch01의 원자료와 최신 16종 B_OFFICIAL 테이블을 혼동해 단순 합산하지 않는다.

### 3.4 U_UNRESOLVED — 기존 접근 보존

U_UNRESOLVED 83종에 대해 신규 기능을 개방하거나 기존 기능을 일괄 차단하지 않는다. 기존 source-file 다운로드 가능 경로와 submission_category 안내만 제공정책 내에서 사용한다.

기존 [WO-DOC260-U83-OWNER-PACKET-R1-001] 결과: 결정 준비 42종, 근거 충돌 1종(DOC-CHEM-007), 근거 부족 40종. Bundle A~E 작업은 이미 진행되었다.

2026-11-05 WEB46 전환 결과, main 정책의 A_INTERNAL=109 / U_UNRESOLVED=83. 과거 WP-01 문서의 63/129는 당시 스냅샷이며 현행 수치가 아니다. [API PR #782](https://github.com/taiengineering/tai-api/pull/782)는 별도 BLD-015/SERA-009 Bundle A 작업으로 2026-11-06 확인 당시 미병합; **WEB46 46종을 다시 승인해야 한다는 뜻이 아니다.**

### 3.5 E_EXTERNAL / F_SCOPE_OUT

E_EXTERNAL 9종은 외부 작성·처리 안내를 제공하고 기존 자료 다운로드 경로가 허용된 경우에만 이를 유지한다. 기관 제출·접수 완료로 표시하지 않는다.
F_SCOPE_OUT 43종은 DOC260 신규 제공 범위 밖이다. 현재 원본 다운로드 API도 F_SCOPE_OUT에 대해 404를 반환한다. 기존 접근통제를 바꾸는 정책 작업은 별도 승인이다.

## 4. 고객 서비스 흐름별 점검 포인트

| 고객 행동 | 주된 경로 | 최소 성공 조건 | 오류/제한 |
| --- | --- | --- | --- |
| 서식 찾기 | GET /document-forms | 260종 기준 분류/표시, 목록·버튼 상태 정확 | 파일 URL 유무만으로 다운로드 표시 금지 |
| 웹 문서 작성 | GET /document-engine/catalog/{doc_id} + 기존 document API | 승인된 Runtime Schema + 회사/사업장 권한 | CANDIDATE는 READY 아님 |
| 작성본 저장·재열기 | POST/PATCH /document-engine/documents, GET 문서 | 값·서식 ID·사업장 scope 일치 | 다른 회사 데이터 접근 거부 |
| 문서 확정·보관 | POST /document-engine/documents/{id}/status 등 | 승인자·서명·증적·Snapshot 무결성 | 미승인 증적 우회 금지 |
| 문서 출력 | 기존 generate/preview/pdf | 동일 데이터에 대한 보존 가능한 출력 | 실패를 성공으로 표시하지 않음 |
| 공식 원본 받기 | GET /document-forms/{doc_id}/source-file | 회원 인증 + B_OFFICIAL 승인 + 정확한 HWP 파일 | 401 인증 / 404 없음·차단 / 503 Storage 장애 |
| 자동 점검/TBM 출력 | /document-engine/auto-documents/{type}/{id}/preview 또는 /pdf | 원천 기록 COMPLETED + 소유권·사업장 검증 | 미완료 기록은 fail-closed |
| 외부 제출 안내 | 기존 제출처 안내 | 실제 기관·제출 방식의 확인된 범위만 안내 | TAI 저장을 법적 제출 완료로 오해 금지 |

## 5. 작업 이력 — 완료 자산을 다시 열지 말 것

| 날짜·단계 | 내용 | 근거 / 상태 |
| --- | --- | --- |
| 2026-10-07 | DOC260 완료 마스터플랜: OBJ10 260종 제공 방식 완성, OBJ11 검색 연동, OBJ12 고객 E2E | [Master Plan v1](./TAI_SAFE_DOCUMENT_COMPLETION_MASTER_PLAN_v1.md) |
| 2026-10-25 (UTC 병합) | 기본 작성·첨부·서명·Archive 관련 P1-A/B | [tai-api #700](https://github.com/taiengineering/tai-api/pull/700), [tai-admin #174](https://github.com/taiengineering/tai-admin/pull/174) — MERGED 직접 확인 |
| 2026-10-26 (UTC 병합) | Evidence FK 연계와 FE Gate | [tai-api #709](https://github.com/taiengineering/tai-api/pull/709), [tai-admin #176](https://github.com/taiengineering/tai-admin/pull/176) — MERGED 직접 확인 |
| 2026-11-02 | 제품 범위 및 WP-01 제공경로 설계 | [WP-01 이력](./WO-DOC260-MAINLINE-WP01-DELIVERY-ROUTING-001.md); **당시 63/129, Draft #752 표기는 현행 아님** |
| 2026-11-03 | Batch01: 스키마 후보 2종 문구 검토, 공식 원본 파일 동일성 조사 | HANDOFF_DOC260_BATCH01_20261103.md (인계 자료); 이미 수행한 조사 |
| 2026-11-04 | 문서 목록/라벨 및 원본 파일 연결 단계 | [tai-api #760](https://github.com/taiengineering/tai-api/pull/760) 등 기존 구현; 재구현 금지 |
| 2026-11-05 | WEB46 재분류 반영; U83 Owner Packet(Bundle A~E) 작성; evidence 45종 분석 | 현재 main _POLICY=109/83, 기존 인계 및 Owner Packet |
| 2026-11-06 | 공식서식 원본 불일치 6종 차단 + CHEM-017 HOLD | [API #789](https://github.com/taiengineering/tai-api/pull/789) merge ed926c19296690508d4cc97834ed22fb0f642d47 / [Admin #208](https://github.com/taiengineering/tai-admin/pull/208) merge a61b3a02d6765a6eb2d4a80a20264c95fa79840e — GitHub 직접 확인 |
| 2026-11-06 | 운영 반영 | Claude Code 보고: Railway(tai-api) 1b57f038 / ed926c19 SUCCESS, Cloudflare Pages(tai-admin) 1c934a9a / a61b3a02 SUCCESS. 인증된 고객 다운로드 라이브 재현은 이 문서에서 수행하지 않음. |
| 2026-11-06 | 고객 제공 범위 마무리 | WO-DOC260-CUSTOMER-DELIVERY-RELEASE-PREP-001 CLOSED_FINAL(공식서식 해당 범위) / 전체 260종 고객 제공 CLOSED_FINAL과 혼동 금지 |

작업 원칙: 분석 완료와 고객 제공 승인/운영 반영은 별개다. 260종 분류, WEB46, Batch01, U83 Owner Packet, Evidence 분석, PDF·문서 파이프라인을 새 WO로 되돌리지 않는다.

## 6. 이미 알려진 보류·주의사항

1. **증적 45종:** 기존 EVIDENCE_UNBLOCK_R1 분석 완료. review_authority SUSPENDED 문제의 해제는 Owner Gate만 가능.
2. **스키마 후보 2종:** DOC-CON-LAW-015, DOC-SERA-008은 runtime_form_schema에 CANDIDATE가 존재한다. 신규 스키마 작성으로 오인하지 말고 기존 승인 절차 적용.
3. **공식 원본 11종:** MISMATCH 6, HOLD 4, 파일 미확보 1. 검증되지 않은 파일을 다른 공식서식으로 대체하거나 HOLD를 임의 해제하지 않는다.
4. **U83:** Owner Packet 이미 작성. 진행 중인 Bundle A/PR #782와 WEB46 완료 영역을 구별한다.
5. **자동 작성:** 별도 AUTO_SOURCE 작동 경로가 있지만 260종 전체 자동화 매핑률은 확인되지 않았다.
6. **레거시 호환:** B_OFFICIAL + can_create=true의 기존 편집 분기를 임의 삭제하지 않는다. 공식서식 다운로드 원칙과 현행 동작 사이의 예외는 승인된 작업으로만 정리한다.
7. **정책/버전:** 문서법령 적용 판단은 LEG, 실제 원본 동일성은 승인된 공식 출처 검증 결과를 따른다. 추정으로 승인하지 않는다.
8. **공개 범위:** 고객 화면에서 파일 다운로드 버튼이 보이는 것만으로 해당 파일 내용·규격·법적 유효성이 검증됐다고 선언하지 않는다.

상위 통제: **O-01~O-09 중 Owner가 명시적으로 지시한 Gate만** 수행한다. O 번호 전체의 최신 승인표가 이 문서에 완전하게 포함되어 있지는 않으므로, 번호로 임의 승인 상태를 만들어내지 않는다. DB·Storage 쓰기, 정책 변경, 병합, 배포는 각각 해당 승인에 따른다.

## 7. 유지보수·장애 대응 가이드 (재조사 최소화)

- 목록에 서식이 없다 → GET /document-forms 응답, active 여부, 페이지/필터, route_group을 먼저 확인.
- 웹 작성 버튼이 비활성 → GET /catalog/{doc_id}의 availability / can_create / schema 상태 확인. route_group만 보며 새 스키마를 생성하지 말 것.
- 원본 다운로드 버튼 없음 → official_status, source_file_available, shouldShowSourceFileDownload() 확인.
- 다운로드 404 → 먼저 B_OFFICIAL policy HOLD/MISMATCH인지 확인, 이후 파일 존재 여부 확인. **404는 무조건 장애가 아니다.**
- 다운로드 503 → Storage 접근 장애. 404와 별개로 조사.
- 파일 링크는 있지만 열리지 않음 → file_url은 참조 링크이며 다운로드 API의 Storage 경로와 다름. 잘못된 원본을 우회해 직접 공개 금지.
- AUTO 문서가 없다 → 완료된 점검/TBM 원천 기록 및 회사/사업장 scope 확인. AUTO_SOURCE를 260종 A_INTERNAL 웹 작성 수와 연결하지 말 것.
- 문서 확정 실패 → Schema, Evidence, 첨부·서명, 승인 권한, 상태 전이를 순서대로 확인. 차단 사유를 없애려고 Gate를 우회하지 말 것.
- 완료된 일반 경로의 회귀 테스트를 광범위하게 반복하지 않고 실제 변경된 연결과 인접 계약만 확인한다.

### 변경 시 품질·인계 기준

1. 사용자 행동별로 **실제 READY / 정책상 대상 / 보류 / 제외**를 다른 숫자로 보고한다.
2. Source of Truth와 코드 변경 영역이 맞는지 먼저 확인한다. 오래된 WP-01의 숫자는 자동 상속하지 않는다.
3. 검증된 내용, Claude Code 보고, 운영 라이브 확인을 구분한다.
4. 변경 PR은 다른 WO 소스를 혼입하지 않는다(과거 PR #789/#208에서 범위 혼입을 분리한 사례).
5. 문서 작성이나 테스트 자체를 최종 목표로 삼지 않는다. 고객이 적합한 문서 동작을 수행하는 것이 종료 기준이다.
6. 완료된 작업을 새 WO로 반복하지 않는다. 새로운 사실이 발견됐을 때만 해당 Gate 범위에서 처리한다.

## 8. 근거·참고 링크

- [DOC260 완료 Master Plan](./TAI_SAFE_DOCUMENT_COMPLETION_MASTER_PLAN_v1.md) — OBJ10~OBJ12 목표와 E2E (2026-10-07 기획)
- [WP-01 제공경로 계약](./WO-DOC260-MAINLINE-WP01-DELIVERY-ROUTING-001.md) — **과거 상태·설계 이력**, 최신 숫자는 이 가이드와 main 소스 우선
- [현재 route policy](../../services/document_engine/r2_route_policy.py)
- [현재 문서 API](../../routers/document_engine_api.py)
- [현재 서식 목록/원본 API](../../routers/document_forms.py)
- [현재 Source File 서비스](../../services/document_engine/source_file_allowlist.py)
- [현재 AUTO_SOURCE read model](../../services/document_engine/auto_source_readmodel.py)
- [현재 Admin 서식 화면](https://github.com/taiengineering/tai-admin/blob/main/vue3/src/pages/document-forms/index.vue)
- [현재 Admin 버튼·타입 계약](https://github.com/taiengineering/tai-admin/blob/main/vue3/src/utils/document-formsFormat.ts)
- [고객 제공 정책 보정 API #789](https://github.com/taiengineering/tai-api/pull/789)
- [고객 제공 정책 보정 Admin #208](https://github.com/taiengineering/tai-admin/pull/208)
- [진행 중인 별도 U83 Bundle A #782](https://github.com/taiengineering/tai-api/pull/782)

**문서 책임 범위:** 인수인계·운영 가이드. 이 문서만으로 신규 코드, 데이터 변경, 승인 또는 배포를 자동 승인하지 않는다.
