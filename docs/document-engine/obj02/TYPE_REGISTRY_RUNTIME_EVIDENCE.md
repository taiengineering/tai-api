# TYPE_REGISTRY_RUNTIME_EVIDENCE

조사일: 2026-10-07
WO: WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001
DB: Supabase vwlahtguyggrhvslabax
Source: tai-api HEAD 7f3b5bf9 (branch docs/integrated-search-document-plan-20261007)
실행자: Claude Code

---

## 전체 현황

| doc_type | type_label | template_file | template_exists | fetcher_key | fetcher_exists | fetcher_status | 판정 |
|---|---|---|---|---|---|---|---|
| APPT | 선임 보고 | DOC-APPT.html | NO | null | NO | NO_SOURCE | METADATA_ONLY |
| CHK | 점검 체크리스트 | DOC-CHK.html | YES | inspection | YES | EXISTING | IMPLEMENTED |
| CONLOG | 공사일지 | DOC-CONLOG.html | NO | construction | NO | NEW_NEEDED | MISSING |
| EDU | 교육일지 | DOC-EDU.html | NO | education | NO | NEW_NEEDED | MISSING |
| EQUIP | 설비점검기록부 | DOC-EQUIP.html | YES | inspection | YES | EXISTING | IMPLEMENTED |
| INSP | 안전점검일지 | DOC-INSP.html | YES | inspection | YES | EXISTING | IMPLEMENTED |
| PPE | 보호구 착용 점검 | DOC-PPE.html | YES | inspection | YES | EXISTING | IMPLEMENTED |
| TBM | 작업 전 안전점검회의 | DOC-OSH-056.html | YES | tbm | YES | EXISTING | IMPLEMENTED |

---

## 판정 근거

### IMPLEMENTED (5건)

**CHK / EQUIP / INSP / PPE** — 공통 fetcher: `inspection_fetcher.py`
- template 파일 실존: `templates/documents/DOC-CHK.html` 등 (CORR-1: 실제 경로 확인)
- fetcher 실존: `services/document_engine/fetchers/inspection_fetcher.py`
- evidence_source: `safety_inspections + safety_inspection_results`
- GENERATOR_MAP["inspection"] 등록 확인: `services/document_engine/generator.py` (FETCHER_MAP)

**TBM** — fetcher: `tbm_fetcher.py`
- template 파일 실존: `templates/documents/DOC-OSH-056.html` (CORR-1: 실제 경로 확인)
- fetcher 실존: `services/document_engine/fetchers/tbm_fetcher.py`
- evidence_source: `tbm_meetings(risk_items, safety_items)`
- generic route: `POST /documents/TBM/generate` via `routers/document_generate.py` (CORR-2)
- legacy TBM-specific route: `POST /document-forms/{doc_id}/generate` via `routers/document_engine.py` → PDF bytes + documents 테이블 INSERT

### METADATA_ONLY (1건)

**APPT**
- template 파일: `DOC-APPT.html` — OBJ00 확인 결과 MISSING
- fetcher: null (fetcher_key = null, fetcher_status = NO_SOURCE)
- source_note: "신고성 문서, 운영 데이터 소스 없음. 입력폼 기반"
- 판정 근거: registry 행은 존재하나 template도 fetcher도 없음. 입력폼 기반 의도만 기록됨.

### MISSING (2건)

**CONLOG**
- template: `DOC-CONLOG.html` — OBJ00 확인 결과 MISSING
- fetcher: fetcher_key="construction", fetcher_status="NEW_NEEDED" — 미구현
- evidence_source: "construction_inspections+factories" — DB 테이블 존재 여부 미확인
- missing dependency: template 파일 + construction_fetcher.py

**EDU**
- template: `DOC-EDU.html` — OBJ00 확인 결과 MISSING
- fetcher: fetcher_key="education", fetcher_status="NEW_NEEDED" — 미구현
- evidence_source: "education_history" — 교육 모듈 미운영
- source_note: "교육 모듈 미운영으로 보류"
- missing dependency: template 파일 + education_fetcher.py + 교육 모듈 운영

---

## 요약 수치

| 분류 | 건수 |
|---|---:|
| IMPLEMENTED | 5 |
| PARTIAL | 0 |
| METADATA_ONLY | 1 |
| MISSING | 2 |
| **합계** | **8** |

---

## Current Consumer (CORR-2)

- CHK/EQUIP/INSP/PPE: `routers/document_generate.py` → `services/document_engine/generator.py` (generic route)
- TBM: `routers/document_generate.py` (generic) + `routers/document_engine.py` (legacy TBM-specific, documents 테이블 저장)
- CONLOG/EDU/APPT: 현재 consumer 없음

---

## Supported Output Today

| doc_type | PDF | HTML | XLSX | DOCX | HWP |
|---|---|---|---|---|---|
| TBM | ACTUAL (Gotenberg) | ACTUAL (Jinja2) | NO | NO | NO |
| INSP/CHK/EQUIP/PPE | ACTUAL (Gotenberg) | ACTUAL (Jinja2) | NO | NO | NO |
| APPT/CONLOG/EDU | NOT IMPLEMENTED | NOT IMPLEMENTED | NO | NO | NO |

---

## MUTATION

application code = 0 / DB write = 0
