---
class: plans
type: OBJECT_WORKPLAN
id: TAI-REF-FORM-OBJECT-PLAN-001
parent: TAI-REF-FORM-PLAN-001
version: 1.0
status: ACTIVE_DISCOVERY_ONLY
date: 2026-10-08
---
# TAI 참고서식 Object 방식 작업계획서 v1.0

## 0. 불변 원칙
Object는 독립적인 검증/완료 단위. 모든 객체는 PURPOSE, IN/OUT, INPUT, OUTPUT, SoT, CONSUMER, DEPENDENCY, STATE, MUTATION, HARD BLOCK, EXIT, EVIDENCE, OWNER, ROLLBACK을 가진다. 상태 PLANNED/READY/IN_PROGRESS/BLOCKED/DONE/DEFERRED. PRJ 거버넌스 준수. 법령=LEG SoT. GPT=설계·검증, Claude Code=조사·실행, Owner=승인. 조사 전용 작업 외 production mutation 금지.

## 1. Object 의존성
```text
REF-00 기준선 → REF-01 안전관리 전업무 조사 → REF-02 중복/정규화
                                            ├→ REF-03 항목·법령·권리 검증 ─┬→ REF-05 DB/RLS
                                            └→ REF-04 SEO/내용 계약 ────────┘
REF-03 → REF-06 파일 포맷·공통디자인
REF-05 + REF-06 → REF-07 대표 서식 샘플
REF-07 → REF-08 전체 서식 제작/QA
REF-05 + REF-08 → REF-09 공개/검색/관측
```

## 2. Object 카드

### OBJ-REF-00 — Baseline and boundary
PURPOSE 현재 소스/DB/인벤토리 현황을 재현 가능하게 기록. IN 읽기 전용 Supabase 3테이블, Git 현행 문서엔진 및 서비스 경계, 이전 후보 파일의 시트 구조. OUT 자료 복제/변경. INPUT 기존 DB, Repo, 첨부 xlsx. OUTPUT 계수·스키마·기존 자산 맵·미확인 사항. SoT DB 실측/Git main; CONSUMER REF-01~06. DEPENDENCY 없음. STATE IN_PROGRESS. MUTATION SELECT + docs 기록만. HARD BLOCK DB write. EXIT 재계수, 식별자/기존 구조, 초안 파일 확인, 조사 누락 표기. EVIDENCE SQL·레포 파일명·근거 시간. OWNER GPT. ROLLBACK docs 새 커밋으로 수정.

### OBJ-REF-01 — Whole workflow inventory
PURPOSE 산업별 안전관리 업무의 문서 전수 후보 발굴. IN 공식부처/공단 및 실제 업무 프로세스 조사. OUT 문서 제작·법적 의무 추정. INPUT REF-00, 공공 자료. OUTPUT 업무 트리/문서명/사용시점/출처/추가 필요 자료. SoT 공식 출처와 업무 evidence. CONSUMER REF-02. DEPENDENCY REF-00. STATE BLOCKED. MUTATION 조사파일/docs. HARD BLOCK 특정 218종을 최종 고정. EXIT 업무영역별 coverage/근거/unknown 분리. EVIDENCE URL/확인일. OWNER GPT. ROLLBACK 후보 취소 사유 추적.

### OBJ-REF-02 — Canonicalization
PURPOSE 기존 335 레코드+신규 조사 후보의 실무 의도 기준 정규화. IN 이름·필드·업무·사용주기 비교. OUT 이름 동일만으로 병합. INPUT REF-01. OUTPUT canonical ID, exact/alias/related/distinct/unknown verdict, legacy mapping. SoT DB 원본과 판단 evidence. CONSUMER REF-03/04. DEPENDENCY REF-01. STATE BLOCKED. MUTATION 연구 산출물. HARD BLOCK 무증거 중복 제거. EXIT 모든 인풋 처리 및 REVIEW_REQUIRED 계수. EVIDENCE 판정근거. OWNER GPT. ROLLBACK 원본 보존.

### OBJ-REF-03 — Field and rights contract
PURPOSE 작성항목과 법령 필수성/저작권 게이트. IN 서식별 required/recommended/optional, 사용법, 원본 라이선스. OUT 법령 SoT 추측·저작권 미확인 재배포. INPUT REF-02+LEG/공식법령. OUTPUT field dictionary/source terms/review flags. SoT LEG 및 확인된 정부 자료. CONSUMER REF-05/06. DEPENDENCY REF-02. STATE BLOCKED. MUTATION docs only. HARD BLOCK 무검증 법적 강제성. EXIT 필드 근거와 권리유형 명시. EVIDENCE URL/날짜/법조항. OWNER GPT. ROLLBACK 변경이력.

### OBJ-REF-04 — SEO information contract
PURPOSE 문서당 canonical/별칭/설명/FAQ/연관서식 정의. IN 검증 검색의도. OUT 키워드만 바꾼 중복페이지. INPUT REF-02. OUTPUT metadata draft + slug collision tests. SoT 승인된 canonical inventory. CONSUMER REF-05/09. DEPENDENCY REF-02. STATE BLOCKED. MUTATION docs only. HARD BLOCK 미검수 자동색인. EXIT 타이틀·내용 정합/유일성. EVIDENCE 검색의도·QA matrix. OWNER GPT. ROLLBACK 이전 승인 버전.

### OBJ-REF-05 — CMS schema and security
PURPOSE 별도 8테이블 물리 DDL/RLS/storage/API 읽기계약 확정. IN PK/FK/index/RLS/publication state. OUT 승인 전 production apply. INPUT REF-03+04. OUTPUT migration dryrun/권한·기존소스 충돌 검사. SoT 승인 스키마. CONSUMER REF-07/09. DEPENDENCY REF-03+04. STATE BLOCKED. MUTATION Owner 별도 승인 후만. HARD BLOCK service_role 공개·RLS 누락. EXIT 보안/데이터무결성 테스트 PASS. EVIDENCE SQL diff/rollback. OWNER GPT+Owner. ROLLBACK 마이그레이션 계획 선행.

### OBJ-REF-06 — Format and common design
PURPOSE 서식 종류/필드에 맞는 포맷과 독자 양식 디자인. IN HWPX/HWP/DOCX/XLSX/PDF 매트릭스. OUT 사전 디자인 확정/무검수 변환. INPUT REF-03. OUTPUT 유형별 시안·인쇄/호환 QA 계획. SoT 승인 field dictionary. CONSUMER REF-07. DEPENDENCY REF-03. STATE BLOCKED. MUTATION 로컬 시안만. HARD BLOCK 공공 원본 TAI로 위장. EXIT Owner 디자인 승인. EVIDENCE 실물 렌더·호환 캡처. OWNER GPT+Owner. ROLLBACK 디자인 버전 고정.

### OBJ-REF-07 — Pilot production
PURPOSE 관리대장/점검/계획/법정원본 유형 대표파일 제작. IN 승인된 필드·디자인. OUT 대량생산. INPUT REF-05+06. OUTPUT 편집본/인쇄본/QA 리포트. SoT 승인 계약. CONSUMER REF-08. DEPENDENCY REF-05+06. STATE BLOCKED. MUTATION 승인된 개발환경만. HARD BLOCK 미검수 HWPX 홍보. EXIT 열기/수정/저장/계산/출력/출처 PASS. EVIDENCE QA sheet. OWNER GPT+Owner. ROLLBACK 샘플 폐기.

### OBJ-REF-08 — Content factory and QA
PURPOSE 개별 파일과 내용의 10개 품질게이트 통과. IN 승인 샘플. OUT 미검수 게시. INPUT REF-07. OUTPUT 파일별 버전·해시·rights/SEO 검수. SoT 승인 inventory. CONSUMER REF-09. DEPENDENCY REF-07. STATE BLOCKED. MUTATION 승인된 파일 제작. HARD BLOCK 자동배포. EXIT 각 서식 QA PASS. EVIDENCE 검사기록. OWNER GPT+Owner. ROLLBACK 버전 rollback.

### OBJ-REF-09 — Publish and observe
PURPOSE Owner 승인 자료만 자료실 공개, sitemap, canonical, 성과 측정. IN 승인된 파일/페이지. OUT 무승인 운영반영. INPUT REF-05+08. OUTPUT 배포/SEO/E2E 및 다운로드검증. SoT published CMS. CONSUMER 이용자/검색엔진. DEPENDENCY REF-05+08. STATE BLOCKED. MUTATION Owner 승인 후만. HARD BLOCK public RLS/권리 미검증. EXIT 브라우저/권한/색인/롤백 PASS. EVIDENCE live QA. OWNER GPT+Owner. ROLLBACK 공개 상태 회수·버전 되돌림.

## 3. 첫 작업 지시: WO-REF-00-001
이 계획서 Git 업로드와 독립확인 후 시작. SQL SELECT만 사용, repo 열람, 기존 엑셀 구조 검사. 3개 기존 테이블 레코드 재계수 및 key 필드 확인. 별도 CMS 테이블 존재 여부 확인. 결과를 docs/reference-forms/OBJ-REF-00-BASELINE.md로 증거화. 이후 REF-01 착수 여부 독립판정. 디비/코드/배포 mutation은 0. 완료하지 않은 체크는 완료 표시 금지.
