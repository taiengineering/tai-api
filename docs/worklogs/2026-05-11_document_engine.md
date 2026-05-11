# 업무정리일지 — 2026-05-11 (일)

## 세션: TAI 문서엔진 — 법정서식 HWP 수집 + Document Schema Compiler

---

## 1. 현황 조사

### Supabase 스토리지
- 17개 버킷 중 문서 관련 3개(form-templates, form-originals, form-outputs) **전부 비어있음** 확인
- law-attachments 버킷: 1,320건 (공정시험기준/설계기준 첨부파일, 서식 아님)

### DB 테이블
- `form_templates` 11건: hwp_url만 있고 파일 미다운로드, storage 경로 전부 NULL
- `document_forms` 260건: file_url 전부 NULL, has_legal_form=true 138건
- 기존 bylSeq URL 11건 **전부 404** (법령 개정으로 만료)

---

## 2. 법제처 bylSeq 404 문제 해결

### 문제
- `bylFileP.do?bylSeq=` URL이 법령 개정마다 변경되어 전부 404

### 시도 1: 법제처 DRF API `target=bylSc`
- 결과: 엔드포인트 자체 존재하지 않음 → 14건 전부 404

### 시도 2 (해결): DB `law_content_raw.raw_xml` 파싱
- `raw_xml`에 이미 최신 법령 XML 저장되어 있음 발견
- 산안법 시행규칙: 138개 `<별표단위>` 블록, 276개 `별표서식파일링크`
- `<별표서식파일링크>/LSW/flDownload.do?flSeq=...` 추출
- **외부 API 호출 0회**, DB 읽기만으로 동작

### 가운뎃점 문제
- form_templates: `·` (U+00B7) vs XML: `ㆍ` (U+318D) → 4/11만 자동 매칭
- 나머지 7건: CSV에서 flSeq 확인 후 SQL UPDATE → v1 스크립트 재실행

---

## 3. 법정서식 HWP 수집 결과

| 항목 | 대상 | 성공 | 방법 |
|---|---|---|---|
| form_templates | 11건 | **11/11** | DB raw_xml → flSeq → 다운로드 |
| document_forms (has_legal_form=true) | 138건 | **131/138** | CSV 1,015건 매칭 → 다운로드 |
| 미매칭 | 7건 | 보류 | 서식명 너무 일반적 |
| **합계** | **142건** | | `form-originals` 버킷 적재 |

### 전체 서식 CSV
- `all_bylaw_forms.csv`: **1,015건** (14개 시행규칙의 별표+서식 전체)
- 법령별 분포: 산안법 138건, 위험물 70건, 화학물질관리법 60건 등

---

## 4. Document Schema Compiler 구현

### 작업지시서
- "오염 방지형 Document Schema Compiler" 16개 섹션 규칙
- 핵심: 문서에 실제 존재하는 구조만 증거 기반 추출, 임의해석 금지

### HWP 파서
- `pyhwpx`: Windows 전용 (Mac 불가)
- `pyhwp` (hwp5): Mac에서 동작 확인
- 파이프라인: HWP → `hwp5html` → XHTML → Python 파싱 → JSON

### 버전 진화

| 버전 | 변경 | OSHACT-FORM-001 결과 |
|---|---|---|
| v1 | 기본 패턴 매칭 | 필드 20, 증빙 10 |
| v2 | element_type 분류, "인" 오탐 수정 | 필드 16, 증빙 2 |
| v3.0 | 구조적 분석, 번호항목 전수 추출, 테이블목적 분류 | 필드 21, 분류율 96% |
| **v3.1** | **FIELD_LABEL 무조건 추출 + INSTRUCTION 셀단위 스킵** | 필드 21+, 전 건 100% |

### v3.1 핵심 수정 (버그 2건)

**버그 1: FIELD_LABEL 조건부 추출**
```python
# 수정 전: canonical 패턴 매칭 안 되면 필드 누락
if canon:
    fields.append(...)

# 수정 후: 무조건 필드 후보 (canonical은 보너스)
canon = find_canonical(text) or "unclassified_field"
fields.append(...)
```

**버그 2: INSTRUCTION_TABLE 전체 스킵**
```python
# 수정 전: 테이블에 "작성방법" 있으면 전체 스킵
if purpose == "INSTRUCTION_TABLE": continue

# 수정 후: 안내문 셀 자체만 스킵
if etype == "INSTRUCTION_TEXT" or etype == "DESCRIPTION_TEXT": continue
```

### 최종 검증 (97건)

| 섹션 | 이행률 |
|---|---|
| S01 원본보존 | **100%** |
| S02 단위분해 | **87%** |
| S03 필드 | **100%** (47% → 100%) |
| S04 체크리스트 | **100%** |
| S05 증빙 | **55%** (정상범위) |
| S06 Family | **100%** |
| S07 법령분리 | **100%** |
| S08~S15 | **100%** |

---

## 5. GitHub 커밋 이력

| 파일 | 브랜치 | 내용 |
|---|---|---|
| `scripts/collect_form_templates_v2.py` | dev | DB raw_xml 파싱 → 서식 flSeq 추출 |
| `scripts/collect_document_forms.py` | dev | 260건↔CSV 매칭 → HWP 다운로드 |
| `scripts/document_schema_compiler.py` | dev | v3.1: 16섹션 전체 이행 Document Schema Compiler |

---

## 6. 다음 작업

- [ ] Document Schema Compiler v3.1 결과 97건 JSON → Supabase DB 적재
- [ ] 미매칭 7건 수동 매칭 (DOC-CON-001 등)
- [ ] 나머지 45건 HWP 로컬 확보 → 재컴파일 (142-97=45)
- [ ] S02 분류율 87% → 95%+ 개선
- [ ] compiled JSON 기반 Human Review UI 구현
- [ ] admrule-kr(행정규칙) INSERT 및 매핑 SQL 실행 (Track B 계속)
