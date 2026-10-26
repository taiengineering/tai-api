---
document_id: TAI-REFERENCE-FORMS-MASTER-DEFINITION-20261011
title: "TAI 안전관리 참고서식 — 조사·제작·CMS·공개·검색·SEO 통합 정의서 및 다중창 인수인계"
date: 2026-10-11
version: "1.0"
type: MASTER_DEFINITION_AND_HANDOFF
status: DOCUMENTATION_ONLY_PR_PENDING
owner: TAI Engineering
repos: ["taiengineering/tai-api", "taiengineering/tai-www"]
source_production_api_sha: "172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c"
source_production_www_sha: "3b10ece193ee2ccc3f61e0cca0ea38799eb38520"
source_production_research_pr: 564
source_production_research_sha: "7a8eec5116bacd85234b3da17f86677be5ec7857"
change_authority: "Owner approval required for PR merge, deploy, production DB and public search submissions"
---

# TAI 안전관리 참고서식 — 통합 정의서 / 실행·인수인계 기준서

> **읽기 순서:** 본 문서 §0 → §1 → §2(수량) → §3~§10(구조/이력) → §11(미결) → §12(다음 실행) → §13(원본 근거).  
> **범위:** 안전관리 *참고서식 콘텐츠 서비스*의 조사, 제작, 등록, 검수, 게시, 공개, 검색, SEO. 기존 **TAI 자동문서 엔진/법령엔진 자체의 재설계 문서가 아님**.  
> **증거 구분:** **GitHub 직접확인 / 운영 DB SELECT 직접확인 / Claude Code 실행 보고 / 역사적 설계**를 섞어 확정하지 않는다. 기준 시점 2026-10-11(KST). 시간 경과 시 §12대로 다시 실측할 것.

## 0. 새 ChatGPT 창 시작 프롬프트 — 그대로 복사

> 아래 파일을 기준으로 TAI 안전관리 참고서식 작업을 이어받으세요.  
> https://github.com/taiengineering/tai-api/blob/main/docs/reference-forms/TAI_REFERENCE_FORMS_MASTER_DEFINITION_2026-10-11.md  
> (main 병합 전이면 문서 PR 또는 docs/reference-forms-master-definition-20261011 브랜치의 동일 경로를 사용)
>
> 역할: GPT=조사 결과 분석, 설계, 작업지시, 독립검증, 게이트 판정; Claude Code=사실조사, 구현·실행, 테스트, 증거 수집; Owner=병합·운영 DB 변경·배포·외부 제출 승인. PRJ/45cm 개발 거버넌스, 법령 SoT=LEG. Claude에게 독립 정책판단/무승인 생산변경을 위임하지 마세요.
>
> 작업 시작 시 (1) tai-api, tai-www 원격 main/PR #564의 HEAD와 변경 여부, (2) 운영 CMS의 189 연구행 / 138 공개 서식 / 394 파일 / 138 미리보기 / 권리·승인 상태, (3) WO-020 검색색인 138건, (4) WO-SEO 사이트맵/캐시 상태, (5) 권리 변경 자동색인 갭과 Excel GUI 미검증을 **읽기 전용**으로 재검증하세요. 역사적 DRAFT 138/FILE 0 기록을 현재 상태로 오인하지 마세요.
>
> 이전 작업을 재구현하거나 이미 등록된 138종을 다시 INSERT하지 말고, 사용자가 새로 요청한 작업의 변경 범위를 먼저 제시하세요. Owner의 별도 승인 전에는 머지/운영 DB write/배포/권리 승인/게시/검색엔진 제출을 실행하지 마세요. 모든 완료는 독립 검증증거를 제시하세요.

## 1. 기획·제품 경계와 불변 결정

### 1.1 목적/고객

안전관리자가 실제 사용하는 관리대장, 점검표, 계획서, 보고서, 위험성평가표, 교육·서명기록, 법정 별지 및 실무 참고문서 등을 독립 조사·제작하여 **한 서식당 하나의 정식 상세페이지**에서 작성방법/출처/연관서식/검수된 다운로드 파일을 제공한다. 주요 사용자는 사업주, 안전관리자, 현장관리자, 실무자.

- 검색명·별칭·업무/산업 분류·작성 주체·사용 시점·적용 전제를 설명한다. 검색 키워드를 바꾼 중복페이지를 대량 생성하지 않는다.
- **기존 TAI 자동문서 엔진이 다루는 업무유형도 범위에 포함**하되, 자동서식 원본의 데이터·레이아웃·코드를 복제하지 않는다. 원 기획의 기존 document_forms/document_form_master/form_templates 비교·중복제거는 Owner 지시로 중단되었다.
- **PRJ=개발 거버넌스, LEG=법령 SoT, 참고서식 CMS는 별도 콘텐츠 제품.** 법적 의무판단은 참고서식/LLM이 독자 생성하지 않는다. 공식 별지 원본은 허용 범위와 버전 확인 후 그대로, 자체 실무서식은 법적 필수항목과 실무 권장항목을 분리하여 독립 설계한다.
- 공공/민간 원본의 사용권·수정·재배포·상업적 활용 허용 여부는 문서별 증거로 확인한다. 출처 표시만으로 재배포 허용이 증명되는 것은 아니다.
- 산출 포맷: PDF(인쇄·열람), DOCX(편집), XLSX(대장·계산·누적). HWPX/HWP는 원 기획 지원 후보이며 실제 제작 및 호환 QA가 확인되지 않았다면 제공 완료로 표기하지 않는다. 문서당 모든 포맷을 강제로 생산하지 않는다.
- 익명 상세/미리보기는 허용; **다운로드는 로그인 필요**(유료 결제는 별도 요구되지 않음). 게시·권리·파일 승인 없이 공개 금지.
- 상세 URL에 서식 종류와 관계없이 실제 slug를 사용한다. PDF/XLSX 버전별 별도 SEO 페이지를 만들지 않는다.

**원안:** [PLAN-001](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/TAI-REF-FORM-PLAN-001.md), [REF-00~09 Object Plan](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/TAI-REF-FORM-OBJECT-PLAN-001.md), [실제 UI 사양](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/WO-REF04-REF09-UI-SPECIFICATION-001.md).

### 1.2 거버넌스·승인권·증거 원칙

| 주체 | 할 일 | 단독 불가 |
|---|---|---|
| GPT | 조사 증거 분석, 문서/데이터 계약, 단계별 WO, 독립 소스/DB/배포 검증 | 근거 없는 법률·권리 자동확정 |
| Claude Code | read-only 조사, 파일 생성/테스트, 코드·PR, 승인 범위 내 실행 및 receipt 제출 | 독립 법적 판단, 임의 Owner 승인, 무승인 병합/배포 |
| Owner | 단계별 승인, 권리·게시 의사결정, 운영 변경 및 외부 제출 승인 | 추후 GPT 검증 없는 자동 완료 판정 |

Object 단위 PURPOSE, INPUT/OUTPUT, SoT, CONSUMER, DEPENDENCY, STATE, MUTATION, HARD BLOCK, EXIT, EVIDENCE, OWNER, ROLLBACK을 기록한다. 작업 상태 및 PR HEAD, 운영 배포 SHA와 실제 데이터의 관계를 항상 고정한다. **소스/서식 구조 QA PASS ≠ 실제 GUI PASS ≠ 권리 검증 PASS ≠ Owner 게시승인 ≠ 구글/네이버 색인됨.**

## 2. 데이터 수량 — 필히 다른 계수로 관리

### 2.1 현황 스냅샷 (2026-10-11 운영 DB SELECT 직접 재확인)

| 계수 | 실측 | 의미 및 오해 방지 |
|---|---:|---|
| public.ref_form_research_items | **189행** | 조사 후보/연구 식별자, 곧바로 189개 완제품이 아님 |
| 운영 reference_forms | **138행 전부 PUBLISHED** | CMS 고유 정식 서식 레코드 |
| 운영 reference_form_public_view | **138행 / distinct slug 138** | 게시 + 현재 승인 content hash 필터 |
| 운영 reference_form_content.body_html | **138건 비어있지 않음** | CMS 공개 본문 존재 |
| 운영 reference_form_files | **394행** | **PDF 138 + DOCX 138 + XLSX 118**; distinct form_id 138 |
| 운영 storage.objects / bucket reference-forms | **394건** | CMS 파일 개수와 동일(단, 체크섬 전량 재검사는 별도) |
| 운영 reference_form_preview_artifacts | **138행** | 미리보기 아티팩트 행; 실제 HTTP/시각 QA는 별도 |
| 활성 reference_form_sources | **CLEARED 138행** | DB 상태; 외부 법률/저작권 감사 완료를 별도로 의미하지 않음 |
| 현재 reference_form_approvals | **APPROVED/current 138행** | 역사적 비현재 승인·대기 행도 남아 있음 |
| 공개 적격 슬러그의 updated_at NULL | **0건** | 사이트맵 lastmod 데이터 존재 |

**운영 DB 조회 사실**이며 과거 인수인계서의 *138 DRAFT/FILE 0/공개 0*과 다르다. 그 과거 상태는 단계 이력일 뿐 현재 운영 현황으로 쓰면 안 된다.

### 2.2 제작 Git 산출물 (REF-01 원본 Draft PR #564, 스냅샷)

| 계수 | 당시 제작 브랜치 증거 | 의미 |
|---|---:|---|
| docs/reference-forms/output/ PDF | **147개** | 버전·예시·변형본 포함 가능 |
| 같은 경로 DOCX | **145개** | 공개 대상 파일과 반드시 1:1 아님 |
| output/xlsx XLSX | **118개** | 기존 138개 고유 서식 ID에 매핑 |
| PNG | **3개** | 제작 검토용 가능, 자동 공개 아님 |
| JSON(output 아래) | **1개** | 부수 아티팩트 |
| **제작 output 합계** | **414개** | 414종 서로 다른 서식이 아님 |
| scripts 아래 제작 JSON | **140개** | 소스/레거시/변형 포함; 140종 고유 공개 서식 아님 |

414 output blobs vs 394 CMS 파일 행의 차이는 **20개**이나, 곧바로 *미등록 대상 20건*을 뜻하지 않는다. Git 변형/실험/보조 파일과 최종 승인 파일을 **research_id, Git blob SHA, SHA256, 파일 유형, CMS form_id, storage path, QA/approval**로 파일별 대조하기 전에는 누락 확정 금지. 최신 REF-01 PR HEAD 및 tree는 재조회할 것.

근거: [제작 output 디렉터리](https://github.com/taiengineering/tai-api/tree/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/output), [189 inventory](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/B14-189-INVENTORY.csv), [XLS02 118 빌드 매니페스트](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/XLS02-118-BUILD-MANIFEST.md), [XLS03 보고서](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/XLS03-FUNCTIONAL-QA-REPORT.md).

## 3. 시스템·데이터 흐름과 책임 소스

    공식/현장 자료·원천 버전·출처/권리 증거
      → REF-01 조사 원장 189 (후보·근거)
      → 독립 canonical 서식 ID / type / 사용상황 / 항목/필드 / source lineage
      → common-v1 JSON + 포맷별 빌더 / XLSX 빌더
      → PDF · DOCX · XLSX 파일과 구조/GUI/법률/권리 QA
      → CMS reference_forms/content/sources/files/previews/approvals/events
      → Owner 승인 + publish RPC (콘텐츠/파일해시/권리/미리보기)
      → 공개 API /reference-forms/{slug} + preview + 로그인 전용 download
      → Astro /reference-form/{slug} 공개 상세 SSR
      → 기존 Shared Search / Outbox / Worker / OpenSearch
      → /safety-search (reference_form/REFERENCE_FORM; 화면명 안전관리서식)
      → sitemap_reference_forms.xml → sitemap_index.xml → 검색엔진 발견/색인 관측

**저장소/런타임**
- REF-01 제작/기초 조사: [tai-api PR #564](https://github.com/taiengineering/tai-api/pull/564), 브랜치 docs/tai-reference-forms-charter-obj-20261008; **2026-10-11 조회 시 OPEN/DRAFT/UNMERGED**, HEAD 7a8eec5116bacd85234b3da17f86677be5ec7857. 모든 대량 제작 파일이 main에 있다고 가정하지 않는다.
- API/CMS/공용 검색 소스: [tai-api](https://github.com/taiengineering/tai-api), 2026-10-11 main 172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c; 운영 Railway API.
- SSR 프론트/SEO: [tai-www](https://github.com/taiengineering/tai-www), 2026-10-11 main 3b10ece193ee2ccc3f61e0cca0ea38799eb38520; Cloudflare Pages Advanced Worker + Astro SSR.
- 운영 DB: Supabase 프로젝트 vwlahtguyggrhvslabax. PROD 직접 변경은 Owner 승인, 실행 receipt, GPT 독립 재검증 필요. 조회 결과에서 자격증명/사용자정보 노출 금지.
- LEG는 법령 SoT, PRJ/45cm는 거버넌스. 별도 기존 document engine / 진단 DB / 법령엔진 데이터 및 동작은 **변경 대상 아님**.

## 4. REF-00~09 원 작업 계획과 조사·제작 기록

| Object | 원래 역할 | 제작·운영 이력/현재 참고 |
|---|---|---|
| REF-00 | 저장소·DB 경계선, 개수/스키마 기초 조사 | 구 DB 3종과 독립형 서비스 경계 정의 |
| REF-01 | 안전관리 전업무/업종/역할/시점별 문서 후보 조사 | 189 research rows, 공식 출처·field QA, 제작 PR #564 |
| REF-02 | 업무 기준 canonical ID·분류·우선순위 | 연구행·원본 source section·고유 서식/variant 구분; 연구 ID≠완제품 |
| REF-03 | 필수/권장/선택 필드, 법령·출처·권리 검증 | 법적 필수성/현행성은 LEG와 공식 근거로 독립 확인 |
| REF-04 | SEO 이름·별칭·canonical·FAQ·관련 문서 | 중복 상세 금지, 공개 적격 콘텐츠만 색인 |
| REF-05 | 독립 CMS 물리 DB/RLS/Storage/API | PR #594/#596 및 3 migrations 병합·적용 |
| REF-06 | 포맷과 공통 디자인 | COMMON-DESIGN-SPEC-053 및 common-v1 공통 렌더러 |
| REF-07 | 대표 서식 시범 제작·수정/인쇄 QA | 대표 pilot → 단계별 B 시리즈 파일 생성 |
| REF-08 | 대량 제작/QA | B14~B18, XLS01~XLS03, 산출물 414개 당시 tree |
| REF-09 | 공개·검색·운영 관측 | API/WWW 실서비스, WO-020 검색, WO-SEO 사이트맵 |

이 표의 Object 계획은 **원 기획/작업 분류**이며 당시 문서 내부의 BLOCKED/IN_PROGRESS 표시는 작성 당시 이력이다. 현재 구현 상태는 §2·§8~§11의 소스/운영 실측이 우선한다.

### 4.1 공식자료·범위·정규화 조사

- 기초공식자료: [Source Discovery 02](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/OBJ-REF-01-OFFICIAL-SOURCE-DISCOVERY-02.md), [KOSHA 24 forms 03](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/OBJ-REF-01-KOSHA-24-FORMS-SOURCE-03.md), [Sector Guides 06](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/OBJ-REF-01-SECTOR-OFFICIAL-GUIDES-06.md).
- 분야 조사: [환경·가스·수소·연구실 17](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/OBJ-REF-01-ENV-GAS-HYDROGEN-LAB-DOCS-17.md), [고위험 설비·밀폐공간 14](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/OBJ-REF-01-HIGH-RISK-EQUIPMENT-CONFINED-14.md), [실무자 유지보수·화학물질·창고 21](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/OBJ-REF-01-PRACTITIONER-MAINT-CHEM-WAREHOUSE-21.md).
- 출처/필드/근거 품질: [Three-level identity 046](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/OBJ-REF-01-THREE-LEVEL-IDENTITY-CONTRACT-046.md), [section/cell 047](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/WO-REF01-SOURCE-SECTION-CELL-EXTRACTION-047.md), [identity correction 048](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/WO-REF01-SOURCE-IDENTITY-CORRECTION-048.md), [field evidence 32](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/OBJ-REF-01-FIELD-SOURCE-EVIDENCE-QA-32.md).
- **Three-level identity(046)는 제안 모델**: research item → source asset+section → canonical form+variant. 당시 제안 테이블을 이미 운영에 적용된 물리 테이블로 오인하지 않는다.
- 문서 기능 분류: FORM / CHECKLIST / WORKFLOW_DIAGRAM / REGISTER / PLAN / REPORT / EVALUATION / RECORD / REFERENCE / UNDETERMINED. type, 파일포맷, source의 sample/blank 여부를 별도로 관리. [51 classification](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/WO-REF01-DOCUMENT-TYPE-CLASSIFICATION-051.md).

## 5. 독립 서식 제작 로직 — 원본 재현 방법

### 5.1 필드 JSON 및 공통 디자인

- 공통 명세 스키마: [COMMON-ENGINE-SCHEMA-058](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/design/COMMON-ENGINE-SCHEMA-058.md), schema_version common-v1, _meta / document / sections 배열. 섹션 순서와 document title 렌더링 책임을 보존한다.
- 유형별 blocks: approval, basic_info, repeat_table, freeform_area 등. orientation portrait 기본, landscape는 유효한 명시 값. repeat_table의 2단 헤더/header_groups 등 구현 계약은 설계 버전·출력기에서 확인.
- 디자인: [COMMON-DESIGN-SPEC-053](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/design/COMMON-DESIGN-SPEC-053.md). A4 세로 210×297mm(필요시 가로), 제목/결재란/필드별 가독성, 표 반복 헤더, 문서 버전 메타, NanumGothic. **디자인 참고본의 원본 KOSHA/MOEL 고유 레이아웃·문구 복제 금지.** 폰트 조달 미결을 이미 해결됐다고 쓰지 않는다.
- 공통 렌더러 출력 경로: [제작 scripts](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/scripts/batch_build.py), [제작 source/JSON 폴더](https://github.com/taiengineering/tai-api/tree/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/scripts). 레거시 C002/C012 등은 common-v1 변경 영향/호환을 먼저 확인.

### 5.2 PDF/DOCX 배치 제작 안전계약

batch_build.py의 기존 구현 규칙:
- 기본값 dry-run(스키마 검증, output write 없음).
- verify-only: 임시 재생성 및 얼려둔 SHA 검증, output 디렉터리 미변경.
- build: 명시된 BUILD_APPROVED_IDS만 제작; 중복 ID 거절.
- 승인된/기존 파일 overwrite 금지, force 옵션 없음.
- PDF + DOCX를 임시로 모두 성공해야 배치 완성으로 기록. 부분 write 실패 시 롤백.
- 신규 제작은 사용자의 실제 목적·현재 승인 범위와 최신 registry를 확인한 뒤에만. **기등록 138종 전체를 이유 없이 재생성 금지**.

원본 스크립트 주석의 사용 예(실행 전 항상 해당 HEAD에서 도움말 확인):

    python3 docs/reference-forms/scripts/batch_build.py --list
    python3 docs/reference-forms/scripts/batch_build.py --dry-run
    python3 docs/reference-forms/scripts/batch_build.py --verify-only

--build는 별도 명시적 제작 승인과 approved ID/원본 보호 확인 후만 실행.

### 5.3 XLSX 제작 및 QA의 정확한 계약

- [XLS01 suitability 189](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/XLS01-189-SUITABILITY-EVIDENCE.csv) → [XLS02 118 manifest](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/XLS02-118-BUILD-MANIFEST.md) → [XLS03 bulk](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/XLS03-BULK-QA.md) → **최종 교정 [XLS03 functional report](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/XLS03-FUNCTIONAL-QA-REPORT.md)** 순서. 이전 bulk 문서의 SUM 자동 수식 설명은 후속 교정에서 **모든 SUM 자동생성 제거, 수동 입력 전용**으로 바뀌었다.
- XLSX 118개: CUMULATIVE 29 / CALC_AGG 13 / DATE_STATUS 11 / CHECKLIST 30 / DAILY_LOG 8 / DOC_TABLE 24 / PLAN_EVAL 3.
- 최종 구조/필드/섹션/파일 생성 QA는 Claude 보고 기준 **188 passed / 0 failed**. Excel Table, 데이터 유효성, 인쇄영역, 섹션 순서, 필드 커버리지 등 검증.
- **실제 Microsoft Excel GUI에서 열기/편집/행 확장/저장/인쇄 QA는 UNVERIFIED**. [XLS03 GUI QA 005](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/XLS03-GUI-QA-005.md). 파일 DB가 QA_PASS/APPROVED여도 이 별도 실사용 검증 부재가 소급하여 없어진 것은 아니다.
- 무근거 계산식, 법적 수치/의무의 자동 생성, 구버전 파일 덮어쓰기는 금지한다. 원본 JSON/빌더와 CMS에 등록된 hash를 각각 비교한다.

## 6. CMS 물리 구조·게시·권리·파일 데이터 계약

### 6.1 SoT 및 migration

- 실제 DB/스토리지 변경 출처: [core migration](https://github.com/taiengineering/tai-api/blob/172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c/supabase/migrations/20261011120000_reference_forms_core.sql), [storage migration](https://github.com/taiengineering/tai-api/blob/172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c/supabase/migrations/20261011120001_reference_forms_storage.sql), [RPC migration](https://github.com/taiengineering/tai-api/blob/172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c/supabase/migrations/20261011120002_reference_forms_rpc.sql).
- 주요 논리 객체: reference_forms(상태/Owner), reference_form_content(한국어 본문/slug/content_hash), reference_form_files(형식·storage ref·SHA/QA), reference_form_sources(원천·권리), reference_form_approvals(현재 승인 해시), reference_form_preview_artifacts(검수·게시 미리보기), reference_form_slug_registry(유일성), reference_form_relations / legacy_links / aliases / events, reference_form_public_view 등. 정확한 컬럼·제약/권한은 **운영 information_schema와 migration**에서 확인.
- storage: private reference-forms 파일 버킷, 미리보기 전용 private 버킷; 파일별 SHA/크기/MIME/업로드 성공과 CMS 행을 1:1 매핑. Git URL을 Storage 파일대신 다운로드 링크로 쓰지 않는다.
- reference_form_public_view는 **PUBLISHED + 현재 APPROVED approval + 현재 content_hash == approved_content_hash**를 제공한다. rights_status CLEARED는 공개 API/검색 adapter/사이트맵 API에서 추가로 확인한다. 보안 없는 anon 직접 테이블 조회 또는 service_role 키 브라우저 노출 금지.

### 6.2 게시 7 gate (운영 RPC의 코드 기준)

**운영 RPC가 검사하는 항목**: G1 form DRAFT, G2 current APPROVED, G3 content_hash 일치, G4 활성 파일 각각 QA_PASS/approved_at 및 현재 승인된 SHA 집합 양방향 일치, G5 REVIEW_REQUIRED/BLOCKED source 없음, G6 is_published+QA_PASS 미리보기 1개 이상, G7 활성 파일 1개 이상. 모든 단계 성공 뒤 PUBLISHED·Owner 상태·이벤트·기존 검색 인덱스 outbox 등록.

**주의:** 출처는 별도 공개 API/검색/사이트맵 경로에서 **최소 1개 활성 source 존재 + 활성 source 전부 CLEARED**로 검사한다. RPC 본문과 read-path의 조건 차이가 존재할 수 있으므로 새 게시 전 બંને 계약의 일치 여부 테스트 필수. 승인됐다는 DB 기록은 원본 라이선스의 외부 감사가 아니라 내부 승인 상태다.

미승인 파일·기존 버전의 해시 변경·권리 상태 변경·slug 변경은 본문/승인 해시, SEO URL, 검색색인과 연결되어 재검토 필요. 게시/취소는 기존 RPC 및 감사 이벤트·Outbox를 사용한다. 임의 직접 UPDATE로 상태를 우회하지 않는다.

### 6.3 파일·상세·미리보기/다운로드 API

- 공개 상세: [routers/reference_forms.py](https://github.com/taiengineering/tai-api/blob/172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c/routers/reference_forms.py) GET /reference-forms/{slug}: 현재 게시, 승인 content hash, 활성 원본 권리 CLEARED → title, description, body_html, 관련 서식, 승인 파일 목록 제공. 내부 storage path/approval IDs 비공개.
- 익명 미리보기: GET /reference-forms/{slug}/preview/{file_id}: 게시/권리 + 활성 file QA + 승인 SHA + published/QA_PASS preview를 검증한 뒤 **서버 프록시**. URL 직접 노출 금지.
- 회원 전용 다운로드: GET /reference-forms/{slug}/files/{file_id}/download: JWT 사용자 검증, 파일 승인 및 승인 SHA 최신바인딩 확인, private Storage를 서버에서 프록시, 20MB 한도, no-store. 브라우저로 signed Storage URL 원문을 직접 반환하지 않는다.
- 프론트: [reference form SSR](https://github.com/taiengineering/tai-www/blob/3b10ece193ee2ccc3f61e0cca0ea38799eb38520/src/pages/reference-form/[slug].astro), [CMS connector](https://github.com/taiengineering/tai-www/blob/3b10ece193ee2ccc3f61e0cca0ea38799eb38520/src/lib/server/referenceFormDetail.js), [Cloudflare composite router](https://github.com/taiengineering/tai-www/blob/3b10ece193ee2ccc3f61e0cca0ea38799eb38520/workers/composite-entry.js). SSR은 미존재 404 / 서버 불가 503 fail-closed. 상세·미리보기는 공개, 실제 다운로드는 로그인 요구. 자세한 Owner UI 변경 사항은 [UI 사양](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/WO-REF04-REF09-UI-SPECIFICATION-001.md) 및 **운영 코드가 우선**.

## 7. 검색 연동 — WO-020 (CLOSED FINAL)

- 기존 소스: CMS 게시/변경 → public.enqueue_search_index_sync → search_index_outbox → 기존 Shared Search Worker/Indexer → OpenSearch → public_safety_search/sections → /safety-search. 새 검색엔진/Worker scheduler/index table/권리 trigger 생성 없음.
- [ReferenceFormAdapter](https://github.com/taiengineering/tai-api/blob/172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c/services/shared_search/adapters/reference_form.py) 및 [production binding](https://github.com/taiengineering/tai-api/blob/172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c/services/shared_search/production_bindings.py)에서 public view + 활성 source CLEARED + ko body_html을 추출, text/aliases, canonical UUID와 /reference-form/{slug}를 형성.
- [공개 검색 router](https://github.com/taiengineering/tai-api/blob/172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c/routers/public_safety_search.py) object_type=REFERENCE_FORM; WWW [safetySearch GROUP_DEFS](https://github.com/taiengineering/tai-www/blob/3b10ece193ee2ccc3f61e0cca0ea38799eb38520/src/lib/server/safetySearch.js) type=reference_form. **화면 표시 이름 '안전관리서식'은 UI 레이블만** 변경(PR #265, merge b2bfc08f39b04e9d8e9d3443183a91c3d31f14be). 저장 type/objectType 변경 금지.
- API [WO-020 PR #598](https://github.com/taiengineering/tai-api/pull/598), merge **36ec14ba7863c635499cd9fcb52b3fac523d2841**; WWW [PR #263](https://github.com/taiengineering/tai-www/pull/263), merge **850ba2ac11204187a2c47d5dadcfff914f13cb51**. 운영 outbox **새 이벤트 138건 재전송** 및 138/138 COMPLETED(기존 DEAD 138건 이력 보존), 검색 E2E는 Claude 보고 PASS.
- **열린 갭: RIGHTS_CHANGE_GAP = OPEN / OPERATION CONTROL.** reference_form_sources.rights_status를 DB 직접 변경해도 검색 outbox 이벤트가 자동 발생하지 않음. 기존 publish/unpublish와 무관한 직접 권리 변경 시 Owner 승인 후 기존 enqueue_search_index_sync를 수동 호출하고 Worker COMPLETED + 실제 OpenSearch 변화를 확인. 새 trigger를 임의 신설하지 않는다.

## 8. SEO 사이트맵 연동 — WO-SEO-REF-FORM-SITEMAP-001

- API [PR #599](https://github.com/taiengineering/tai-api/pull/599), merged commit **172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c**: /public/safety-search/sitemap/reference-forms (UUID 커서, 공개 적격 + 권리 필터, 권리 조회 오류 503), /latest-updated-at.
- WWW [PR #266](https://github.com/taiengineering/tai-www/pull/266), merged commit **3b10ece193ee2ccc3f61e0cca0ea38799eb38520**: 기존 [pages-live-worker.js](https://github.com/taiengineering/tai-www/blob/3b10ece193ee2ccc3f61e0cca0ea38799eb38520/workers/pages-live-worker.js)의 CONTENT_SITEMAPS / handleContentSitemap / handleSitemapIndex 재사용. 새 별도 엔진/스케줄러/DB 없음.
- 웹 URL: https://taieng.co.kr/sitemap_reference_forms.xml → 기존 https://taieng.co.kr/sitemap_index.xml → robots.txt의 sitemap index 지시. 서식 개수를 138로 하드코딩하지 않고 **실시간 적격성 + 캐시 TTL**로 생성; 각 서식 loc는 canonical slug.
- 현재 138개 URL / 중복 0 / 공개 부적격 노출 0 / 샘플 ref-c001, ref-c002, ref-c005 self-canonical/JSON-LD/robots index,follow **Claude Code 운영 HTTP E2E 보고**. 운영 DB 적격 138개 및 Cloudflare 배포 SHA는 GPT가 독립 조회.
- Cloudflare Pages production deployment **82bccbec-971a-4af8-9c83-bea1ca435056**, 성공, commit 3b10ece193ee2ccc3f61e0cca0ea38799eb38520. API Railway 배포 ID는 당시 접근 제약으로 미확인; health 200과 live API 반영은 Claude 보고.
- **캐시 이슈:** 2026-10-11 12:40Z경 Claude 확인 시 기본 sitemap_index.xml 12개(HIT, age 1190초), cache-bust URL 13개(MISS, 신규 서식 포함). 판정 STALE_CACHE; s-maxage=3600 및 stale-while-revalidate 정책. 기본 URL에서 13개로 자연 갱신됐는지 추가 실측 전에는 **캐시 갱신 VERIFIED로 표기하지 않는다**.
- Owner가 **참고서식 사이트맵 추가 제출 완료**를 2026-10-11 보고함. 어느 검색엔진에 어떤 속성/제출 시각으로 제출됐는지 Provider response 증거는 본 문서 시점 미확인. **제출 ≠ 크롤링 ≠ 실제 색인**.
- IndexNow [allow/deferred 계약](https://github.com/taiengineering/tai-www/blob/3b10ece193ee2ccc3f61e0cca0ea38799eb38520/scripts/lib/indexnow-sitemap.mjs): sitemap_reference_forms.xml은 DEFERRED; 임의 활성화 금지. 기존 SEO [종합정리](https://github.com/taiengineering/tai-www/blob/3b10ece193ee2ccc3f61e0cca0ea38799eb38520/docs/seo/OVERVIEW_seo-overhaul-2026-09.md), [dup guard](https://github.com/taiengineering/tai-www/blob/3b10ece193ee2ccc3f61e0cca0ea38799eb38520/docs/seo/DUPGUARD.md) 유지.
- **lastmod 잔여 주의:** latest-updated-at는 public view 전체의 MAX(updated_at)을 사용하며 rights CLEARED 필터가 없음; 개별 URL은 권리 필터 적용. 권리 차단 항목 날짜가 인덱스 lastmod에 영향 줄 가능성은 별도 개선 대상으로 기록, 이번 병합을 되돌리거나 무승인 수정하지 않는다.

## 9. 변경/제작/게시 시 검증 매트릭스

| 구간 | 반드시 맞출 값 | 대표 실패/HOLD |
|---|---|---|
| 조사·대상 | 189 연구행 ≠ 138 canonical, 근거/source date | 원본 출처 미확인, 업무유형 오분류 |
| 원본/field | 연구 ID→source asset→section→정식서식 lineage | 근거 없는 법정 필수항목, TAI 자동문서 복제 |
| 빌드 | common-v1 JSON, 독립 디자인, filename, frozen source SHA | 승인 산출물 overwrite, partial build |
| PDF/DOCX | 편집/렌더/페이지/인쇄/텍스트·필드 커버리지 | 실제 Word GUI/폰트 차이 미검증 |
| XLSX | 118 전량 매핑, 수식 금지, Table/입력범위, 기능 188 PASS | MS Excel GUI UNVERIFIED, 인쇄범위/행 확장 |
| CMS | 138 form ID, 각 파일 SHA+Storage 존재, 394 승인 파일, 본문 | Git blob = 공개파일이라는 추정 |
| 게시/권리 | 승인 content_hash/file hashes, CLEARED, preview QA, Owner | 문서 수정 후 기존 approval 재사용 |
| 상세·다운로드 | 익명 상세/preview, 인증 download, 내부 path 미노출 | 404/503 fallback, 미승인 파일 공개 |
| Shared Search | REFERENCE_FORM, 이벤트→Worker COMPLETED→검색 E2E | rights 직접 변경 이벤트 누락 |
| SEO | canonical, robots index, sitemap URL 전량/중복 0, index 13개 | stale edge cache, lastmod rights gap |
| 외부 검색엔진 | 등록 URL, provider 수락·크롤·실제 색인 각각 실측 | 제출만 하고 색인 COMPLETE로 오판 |

## 10. 주요 릴리즈/결정 연대기 (고정 근거)

1. **2026-10-08 REF-01 시작:** 전체 업무 참고서식 독립 서비스 선언. 기존 TAI 자동문서 범위 포함하되 원본/DB 대조·복제 금지. 조사·source/field/rights 기록 → 제작 JSON/대표서식.
2. **REF-01 Draft PR #564:** B14~B18 PDF/DOCX 배치 + XLS01~XLS03 XLSX 118종; 산출물 총 414개(당시 원격 tree), 여러 빌드/증거문서.
3. **2026-10-11 CMS 초기 구축:** [API DB PR #594](https://github.com/taiengineering/tai-api/pull/594) merge 47f209a8bef6ac1df9bde1ed54462a037caac78c, 3개 migration; [API #596](https://github.com/taiengineering/tai-api/pull/596) merge 49da99b3fe433d088d20e7b7db1e7684b26e13f4; [WWW #257](https://github.com/taiengineering/tai-www/pull/257) merge ff1d5bb8a678c29d9c90321a99b6976149296786. WWW PR #256은 별도 미병합 종료.
4. **역사적 초기 등록:** 138개의 DRAFT 메타데이터만 생성됐고 파일/미리보기/본문 0이었던 시점이 있었음. **현재 상태 아님.** 이후 승인·파일 등록·게시가 진행되어 §2의 운영 실측 상태로 전환.
5. **WO-020 검색 통합:** API #598 / WWW #263 병합, 기존 Outbox로 138 이벤트 재발행/138 완료, Rights change gap 운영통제로 남김.
6. **WWW 검색 탭 라벨:** [#265](https://github.com/taiengineering/tai-www/pull/265), 안전관리서식으로 표시 변경, type=reference_form 불변.
7. **WO-SEO 참고서식 사이트맵:** API #599 / WWW #266 병합·배포, 신규 서식 sitemap 138건, sitemap_index 13개는 캐시 우회 확인. Owner 신규 사이트맵 추가 제출 보고. 기본 URL 캐시 만료 확인 후 작업 상태 최종 판정.
8. **이 문서:** 기존 기능을 변경하지 않는 정의서/인수인계 전용 Git 문서 PR; main 병합은 Owner의 별도 승인.

## 11. 미결·리스크 및 작업 금지

| 항목 | 상태 | 다음 창의 처리 |
|---|---|---|
| REF-01 원본 PR #564 | OPEN/DRAFT/UNMERGED (조회 시점) | 새 HEAD/산출물 blob read-only 실측; 이유 없이 본선 merge 금지 |
| 414 제작물 vs 394 CMS 등록 | LINEAGE_RECONCILIATION_NOT_PROVEN | 20개 수치 차이가 실제 누락인지 파일별 매핑. 업로드/재생성은 별도 승인 |
| XLSX 실제 GUI 사용성·출력 | UNVERIFIED_GUI | 실제 Excel 앱에서 대표·전수 수락 기준/증거 정한 뒤 수행 |
| RIGHTS_CHANGE_GAP | OPEN/OPERATION CONTROL | 직접 변경 시 기존 수동 outbox + COMPLETED/검색 확인, Owner 승인 |
| sitemap_index 기본 URL의 캐시 | STALE_CACHE (12 vs 13) | 만료 후 기본 URL 재실측; 캐시 우회 PASS를 기본 URL PASS로 대체 금지 |
| sitemap index 최신일 | RIGHTS_FILTER_GAP | 직접 공개 소스와 lastmod 필터 정합성 개선 별도 WO |
| Google/Naver 실제 색인 | OBSERVATION_PENDING | URL 검사/색인 현황 실측, 제출 완료만으로 색인 완료 선언 금지 |
| 공개자료 권리 | DB CLEARED 138 | 내부 상태 외 독립 원천 라이선스/법률 증거 검증 필요 여부 Owner 검토 |
| Cloudflare 환경설정 | SECURITY_REVIEW_REQUIRED | MKT_SUPABASE_ANON_KEY에 service_role 성격 키가 설정된 사실 발견. 원문 문서/로그 노출 금지, 별도 인증정보 감사를 승인 받아 진행 |
| 제작물/원천 자료 재배포 | HOLD unless licensed | 공식/민간 외부 저작권을 독자 확정하거나 무단 공개 금지 |

## 12. 다음 창 즉시 실행 프로토콜 (먼저 READ-ONLY)

### 12.1 먼저 확인할 앵커

- GitHub tai-api main SHA 및 PR #564 HEAD/state; tai-www main SHA; 이 문서 PR/base/merge 상태. 표의 SHA를 무조건 현재라고 가정하지 않는다.
- DB: 연구행, CMS form status, public view slug, body_html 수, 파일 행 포맷별 수/Storage 건수, 현재 승인 및 권리, preview 건수를 SELECT로 재계수.
- API public sitemap URL, worker/SEO 배포 SHA, 새 sitemap의 실제 URL 집합, 기본 sitemap_index.xml과 cache-bust의 응답 헤더/항목 수.
- WO-020 outbox COMPLETED 138을 새 변경 상태와 비교; 권리 변경 이력 여부 확인.
- XLSX 실사용 QA 증거와 원본 PR 수정 여부 확인.

**SELECT-only 재계수 예시(쓰기/DDL 불가):**

    SELECT status, count(*) FROM public.reference_forms GROUP BY status;
    SELECT count(*) FROM public.ref_form_research_items;
    SELECT count(*) AS published FROM public.reference_form_public_view;
    SELECT lower(split_part(file_ref,'.',-1)) ext, count(*) 
      FROM public.reference_form_files GROUP BY 1 ORDER BY 1;
    SELECT count(*) FROM storage.objects WHERE bucket_id='reference-forms';
    SELECT rights_status, count(*) FROM public.reference_form_sources WHERE is_active GROUP BY 1;
    SELECT approval_status, is_current, count(*) FROM public.reference_form_approvals GROUP BY 1,2;
    SELECT count(*) FROM public.reference_form_preview_artifacts;

쿼리 결과가 baseline과 달라도 직접 보정하지 않는다. 사용자가 요청한 다음 작업의 Scope/읽기 결과부터 정리한다. 운영 승인 없는 publish/rights/파일 업로드/SEO 제출 절대 금지.

### 12.2 새 서식을 실제 추가할 때(별도 Owner 승인 필요)

1. 조사 원장/공식 출처/법령 SoT 대조, 기존 참고서식 canonical/variant 정합성 결정 — 기존 자동문서 복제 금지.
2. 타입과 field Required/Recommended/Optional, 권리·적용범위·사용 시점, 파일 포맷 계약 생성. URL slug 충돌 조사.
3. common-v1 JSON·공통 디자인 기반 pilot → 파일별 PDF/DOCX/XLSX 제작·QA; original sha 보존. GUI·법적 근거·권리 실패는 HOLD.
4. 신규 CMS 메타/본문·private Storage 파일·미리보기/승인 바인딩을 **승인된 쓰기 WO**로 등록. 추가 건수가 확정되기 전 수량 138 하드코딩 금지.
5. Owner 권리·게시 승인, 승인 파일/본문 SHA와 7 gates + read path 확인 후 기존 RPC 사용.
6. 기존 Outbox/Worker로 검색색인 정합성, 기존 사이트맵 동적 포함/canonical, 누락/중복·권리 노출 0 확인. 외부 검색엔진 제출은 따로 승인.

### 12.3 이미 게시한 서식을 수정·취소할 때

- 본문/slug 변경은 승인 content_hash·기존 인덱스 URL·SEO canonical에 영향을 준다. 승인 해시와 파일/preview를 재검증하고 Owner에게 게시 영향도를 제출한다.
- 파일 교체는 동일 form_id에 신규 파일 버전/SHA/QA를 연결하고 기존 승인 파일 hash를 혼용하지 않는다. 기존 Storage 원본 즉시 파기 금지.
- 취소는 기존 unpublish RPC/이벤트/기존 검색색인/사이트맵 제외/404(또는 정책에 맞는 URL 처리)를 증거로 확인.
- 권리 직접 변경은 RIGHTS_CHANGE_GAP에 따라 수동 색인 이벤트 운영 절차가 필수. 임의 트리거 신설 금지.

### 12.4 GPT 독립검증 제출 폼

    WORKSTREAM =
    TASK_WO =
    OWNER_APPROVED_SCOPE =
    SOURCE_REPO/BRANCH/HEAD =
    API_MAIN / WWW_MAIN =
    REF01_PR_564_STATE/HEAD =
    RESEARCH_ITEMS =
    FORM_STATUS_COUNTS =
    PUBLIC_ELIGIBLE =
    CONTENT_BODY_COUNT =
    FILE_PDF / FILE_DOCX / FILE_XLSX / FILE_TOTAL =
    STORAGE_OBJECTS / PREVIEW_ROWS =
    SOURCE_RIGHTS_COUNTS / APPROVAL_COUNTS =
    BUILD_TEST / GUI_QA / LICENSE_QA =
    SHARED_SEARCH_COMPLETED / LIVE_E2E =
    SITEMAP_URL_COUNT / INDEX_BASE_COUNT / CACHE_HEADERS =
    GSC_NAVER_PROVIDER_RECEIPT =
    NEW_DB_WRITE = 0 unless explicit approval
    MERGE = NONE unless explicit approval
    DEPLOY = NONE unless explicit approval
    GPT_INDEPENDENT_GATE = PENDING

## 13. 원본 및 기술참고 링크 지도

**기획/계획**
- [원 기획 TAI-REF-FORM-PLAN-001](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/TAI-REF-FORM-PLAN-001.md)
- [Object 00~09 계획](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/TAI-REF-FORM-OBJECT-PLAN-001.md)
- [공통 디자인](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/design/COMMON-DESIGN-SPEC-053.md)
- [공통 JSON/엔진 스키마](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/design/COMMON-ENGINE-SCHEMA-058.md)

**조사/출처/필드/분류**
- [공식자료 discovery](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/OBJ-REF-01-OFFICIAL-SOURCE-DISCOVERY-02.md)
- [권리 및 근거 원장 24](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/OBJ-REF-01-FULL-PROVENANCE-LEDGER-24.md)
- [Three-level identity 046](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/OBJ-REF-01-THREE-LEVEL-IDENTITY-CONTRACT-046.md)
- [Functional classification 051](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/WO-REF01-DOCUMENT-TYPE-CLASSIFICATION-051.md)
- [189행 조사 매니페스트](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/B14-189-INVENTORY.csv)

**제작/파일 QA**
- [batch_build.py](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/scripts/batch_build.py)
- [B18 QA](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/B18-DISTINCT-FORM-QA.md)
- [XLS02 build manifest](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/XLS02-118-BUILD-MANIFEST.md)
- [XLS03 최종 기능교정](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/XLS03-FUNCTIONAL-QA-REPORT.md)
- [XLS03 GUI 한계](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/evidence/XLS03-GUI-QA-005.md)

**CMS·보안·웹**
- [CMS 계약](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/WO-REF05-CMS-CONTRACT-FINALIZATION-003.md)
- [상세 UI 정의](https://github.com/taiengineering/tai-api/blob/7a8eec5116bacd85234b3da17f86677be5ec7857/docs/reference-forms/WO-REF04-REF09-UI-SPECIFICATION-001.md)
- [CMS migrations](https://github.com/taiengineering/tai-api/blob/172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c/supabase/migrations/20261011120002_reference_forms_rpc.sql)
- [공개 API](https://github.com/taiengineering/tai-api/blob/172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c/routers/reference_forms.py)
- [SSR 상세](https://github.com/taiengineering/tai-www/blob/3b10ece193ee2ccc3f61e0cca0ea38799eb38520/src/pages/reference-form/[slug].astro)

**공용 검색·SEO**
- [ReferenceFormAdapter](https://github.com/taiengineering/tai-api/blob/172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c/services/shared_search/adapters/reference_form.py)
- [공개 검색 및 sitemap API](https://github.com/taiengineering/tai-api/blob/172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c/routers/public_safety_search.py)
- [Cloudflare sitemap Worker](https://github.com/taiengineering/tai-www/blob/3b10ece193ee2ccc3f61e0cca0ea38799eb38520/workers/pages-live-worker.js)
- [SEO 전체 정의](https://github.com/taiengineering/tai-www/blob/3b10ece193ee2ccc3f61e0cca0ea38799eb38520/docs/seo/OVERVIEW_seo-overhaul-2026-09.md)
- [WO-020 API #598](https://github.com/taiengineering/tai-api/pull/598), [WWW #263](https://github.com/taiengineering/tai-www/pull/263)
- [WO-SEO API #599](https://github.com/taiengineering/tai-api/pull/599), [WWW #266](https://github.com/taiengineering/tai-www/pull/266)
- [사이트맵 Index](https://taieng.co.kr/sitemap_index.xml), [참고서식 Sitemap](https://taieng.co.kr/sitemap_reference_forms.xml)

## 14. 문서 유지보수 규칙

- 새 WO가 끝날 때 **변경된 사실/앵커/검증수준/미결/참조링크만** 갱신하며 근거 없는 소급 확정 금지.
- 원본 자료는 SHA 앵커를 고정해서 링크한다. branch main에 아직 없는 REF-01 초안 자료를 main 링크로 바꾸지 않는다.
- 과거 handoff에서 명시한 시점별 DRAFT/파일0 기록은 역사적 기록으로 보존한다. 최신 수량은 실제 운영 DB가 우선.
- 문서 자체의 Git commit/PR은 실행 사실이며 **운영코드·DB·배포 변경을 승인하거나 수행하지 않는다**. PR merge는 Owner 승인 이후 별도 진행한다.
- 데이터·화면·검색·법령·권리의 서로 다른 성공기준을 한 개의 PASS로 합치지 않는다.

---
**Document baseline:** 2026-10-11. **Next action:** Owner가 요청한 새 구체 작업이 없는 한 이 문서는 인수인계 기준서로만 유지하며, 대량 신규 제작/재게시/권리변경/검색엔진 제출을 자동 재시작하지 않는다.
