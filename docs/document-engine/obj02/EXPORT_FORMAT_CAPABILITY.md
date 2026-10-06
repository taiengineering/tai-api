# EXPORT_FORMAT_CAPABILITY

조사일: 2026-10-07
WO: WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001
Source: tai-api HEAD 7f3b5bf9 + requirements.txt 검사
실행자: Claude Code

---

## 현재 실제 지원 format (CORR-3: DB CHECK 반영)

`chk_gd_export` CHECK 허용값: `HTML, PDF, XLSX, PRINT_VIEW, API_RESPONSE` (DOCX/HWP 없음)

| format | DB_ALLOWED (chk_gd_export) | renderer 구현 | 실제 route | frontend consumer | production evidence | 판정 |
|---|---|---|---|---|---|---|
| PDF | YES | YES (Gotenberg via renderer.py + gotenberg_svc.py) | POST /documents/{doc_type}/generate, POST /document-forms/{doc_id}/generate | /document-forms, /engine-document | documents 테이블 4건 (견적서, 2026-09-30) | ACTUAL (견적서 경로) / UNVERIFIED (문서엔진 경로) |
| HTML | YES | YES (Jinja2 render_document_html) | render_document_html() 내부 함수 | /compliance-report (일부) | 간접 증거 (Jinja2 render 코드 확인) | ACTUAL |
| XLSX | YES | NO (xlsxwriter/openpyxl 미포함) | 없음 | 없음 | 없음 | DB_ALLOWED_BUT_NOT_IMPLEMENTED |
| PRINT_VIEW | YES | NO (별도 route 없음) | 없음 | 없음 | 없음 | DB_ALLOWED_BUT_NOT_IMPLEMENTED |
| API_RESPONSE | YES | PARTIAL (runtime_document_data JSON 반환 가능) | GET /document-engine/... (부분 구현) | 없음 | 없음 | DB_ALLOWED_PARTIAL |
| DOCX | NO (CHECK에 없음) | NO (python-docx 미포함) | 없음 | 없음 | 없음 | NOT_ALLOWED_NOT_PRESENT |
| HWP | NO (CHECK에 없음) | NO (hwp 라이브러리 미포함) | 없음 | 없음 | 없음 | NOT_ALLOWED_NOT_PRESENT |

---

## PDF 상세

### 경로 A — gotenberg_svc.py (견적서용)

| 항목 | 값 |
|---|---|
| 파일 | services/gotenberg_svc.py |
| 엔드포인트 | {GOTENBERG_URL}/forms/chromium/convert/html |
| 환경변수 | GOTENBERG_URL (없으면 PdfRenderError 503 fail-closed) |
| 증거 | documents 테이블 4건 (견적서 PDF, 최근 2026-09-30) |
| 판정 | PRODUCTION_VERIFIED |

### 경로 B — renderer.py (문서 템플릿용)

| 항목 | 값 |
|---|---|
| 파일 | services/document_engine/renderer.py |
| fallback hostname | gotenberg.railway.internal:3000 |
| callers | routers/document_engine.py (TBM), routers/compliance_report.py, services/document_engine/generator.py |
| 증거 | GENERATED 9건 존재하나 storage_path=NULL — 파일 실존 UNVERIFIED |
| 판정 | UNVERIFIED (로그/스토리지 접근 불가) |

---

## 라이브러리 확인 결과

| 라이브러리 | requirements.txt 포함 여부 |
|---|---|
| xlsxwriter | NO |
| openpyxl | NO |
| python-docx | NO |
| hwp5 / pyhwp | NO |
| jinja2 | YES (HTML 렌더링) |
| httpx | YES (Gotenberg 통신) |

---

## DB vs 실제 구현 정리 (CORR-3)

XLSX: DB에서 허용(chk_gd_export)하나 renderer/route/consumer 없음 → "지원 가능"으로 표시 금지.
DOCX/HWP: DB CHECK에도 없고 renderer도 없음.

---

## OBJ01 원칙 대조

Web Document First architecture (OBJ01):
- HTML = working view → ACTUAL 구현 있음 (Jinja2)
- PDF = on-demand at download → Gotenberg 경로 존재, 견적서 경로 VERIFIED
- XLSX = DB_ALLOWED_BUT_NOT_IMPLEMENTED
- DOCX/HWP = NOT_ALLOWED_NOT_PRESENT

---

## MUTATION

application code = 0 / DB write = 0
