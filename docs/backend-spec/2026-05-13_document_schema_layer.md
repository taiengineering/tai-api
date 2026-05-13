# Document Schema Layer — Backend Spec

## 날짜: 2026-05-13
## 유형: backend-spec

---

## 개요

문서를 Runtime Structured Data 기반으로 렌더 가능한 Document Schema System.

핵심 구조:
```
Runtime Data → Document Schema → HTML Render → PDF Export(Optional)
```

## 테이블

### document_schema_registry
문서 유형별 섹션/필드 구조 정의. 97개 문서 유형, 3,873 필드, 428 섹션 적재.

| 컬럼 | 타입 | 용도 |
|---|---|---|
| document_type | text | 문서 유형 (예: OSHACT_FORM_001) |
| section_code | text | 섹션 코드 (예: BASIC_INFO) |
| field_code | text | 필드 코드 (예: site_name_001) |
| field_label | text | 필드 라벨 (예: 사업장명) |
| field_type | text | text/number/date/select/checkbox/table/image/signature/evidence_ref |
| required_level | text | MANDATORY/RECOMMENDED/OPTIONAL |
| source_mapping | text | 런타임 데이터 소스 (예: company.manager_name) |
| validation_rule | jsonb | 검증 규칙 (예: {"rules": ["required"]}) |
| render_component | text | 프론트엔드 컴포넌트 (예: text-input, date-picker) |
| conditional_rule | jsonb | 조건부 렌더링 규칙 |
| source_trace | text | 법령 근거 |
| status | text | CANDIDATE/CONFIRMED/DEPRECATED |

### document_schema_section
섹션 메타데이터. 중첩 섹션 지원 (parent_section_code).

### document_schema_audit
모든 변경 이력. INSERT/UPDATE/CONFIRM/REJECT 기록.

## API 엔드포인트

| Method | Path | 용도 |
|---|---|---|
| GET | /document-schema/list | 문서 유형 목록+요약 |
| GET | /document-schema/{type} | 전체 스키마 (섹션+필드) |
| GET | /document-schema/render-structure/{type} | 렌더링 구조 |
| GET | /document-schema/field-mapping/{type} | 소스 매핑 |
| GET | /document-schema/integrity/{type} | 무결성 점검 |

## 데이터 파이프라인

```
HWP 원본 (form-originals 버킷)
  → hwp5html → XHTML
  → document_schema_compiler.py v3.1 → compiled JSON (97건)
  → load_document_schema.py → document_schema_registry (3,873 필드)
  → API → Admin Console → Human Review → CONFIRMED
```

## 절대 금지
- HTML hardcoding
- PDF 저장 중심 구조
- semantic field inference
- AI 기반 field 생성
- guessed schema
