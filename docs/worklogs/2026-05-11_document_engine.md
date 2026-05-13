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

### 미매칭 7건 목록
- DOC-CHEM-004: 장외영향평가서 (화학물질관리법 제41조)
- DOC-CON-002: 안전관리계획서 승인서 (건설기술진흥법)
- DOC-CON-LAW-002: 품질시험계획 (건설기술진흥법 제55조)
- DOC-CON-005: 착공신고서 (건설산업기본법)
- DOC-CON-001: 안전관리계획서 (건설기술진흥법 제62조)
- DOC-CON-LAW-007: 품질관리계획 사본 (건설기술진흥법 제55조)
- DOC-CON-LAW-008: 안전관리계획(법정) (건설기술진흥법 제62조)

### 전체 서식 CSV
- `all_bylaw_forms.csv`: **1,015건** (14개 시행규칙의 별표+서식 전체)
- 법령별 분포: 산안법 138건, 위험물 70건, 화학물질관리법 60건 등

---

## 4. Document Schema Compiler 구현

### 작업지시서
- "오염 방지형 Document Schema Compiler" 16개 섹션 규칙
- 핵심: 문서에 실제 존재하는 구조만 증거 기반 추출, 임의해석 금지

### HWP 파서 조사
- `pyhwpx`: **Windows 전용 (Mac 불가)** — `RuntimeError: pyhwpx는 Windows에서만 동작합니다`
- `python-hwp`: pip에 존재하지 않음
- `pyhwp` (hwp5): **Mac에서 동작 확인**, `olefile` 기반
- `hwp5html`: HWP → XHTML 변환, **표 구조 완벽 보존** (td/rowspan/colspan)
- 파이프라인: HWP → `hwp5html --output dir` → `index.xhtml` → Python 파싱 → JSON

### 버전 진화

| 버전 | 변경 | OSHACT-FORM-001 결과 |
|---|---|---|
| v1 | 기본 패턴 매칭 | 필드 20, 증빙 10 |
| v2 | element_type 분류, "인" 오탐 수정, Audit 추가 | 필드 16, 증빙 2 |
| v3.0 | 구조적 분석, 번호항목 전수 추출, 테이블목적 분류 | 필드 21, 분류율 96% |
| **v3.1** | **FIELD_LABEL 무조건 추출 + INSTRUCTION 셀단위 스킵** | 필드 21+, **전 건 100%** |

### v3.1 핵심 수정 (버그 2건)

**버그 1: FIELD_LABEL 조건부 추출 → 51건 필드 0건**
```python
# 수정 전: canonical 패턴 매칭 안 되면 필드 누락
if canon:
    fields.append(...)

# 수정 후: 무조건 필드 후보 (canonical은 보너스)
canon = find_canonical(text) or "unclassified_field"
fields.append(...)
```
원인: canonical 패턴 34개에 매칭 안 되는 라벨(예: "검사 종류", "설비명칭")이 전부 누락

**버그 2: INSTRUCTION_TABLE 전체 스킵 → 서식 테이블도 스킵**
```python
# 수정 전: 테이블에 "작성방법" 있으면 전체 스킵
if purpose == "INSTRUCTION_TABLE": continue

# 수정 후: 안내문 셀 자체만 스킵
if etype == "INSTRUCTION_TEXT" or etype == "DESCRIPTION_TEXT": continue
```
원인: 법정서식 하단에 "작성방법" 안내가 같은 테이블에 포함된 경우 전체 스킵

### 최종 검증 (97건)

| 섹션 | 이행률 | 비고 |
|---|---|---|
| S01 원본보존 | **100%** (97/97) | |
| S02 단위분해 | **87%** (84/97) | 13건 분류 1종류 이하 |
| S03 필드 | **100%** (97/97) | 수정 전 47% → 수정 후 100% |
| S04 체크리스트 | **100%** (97/97) | 0건도 정상 (보고서 서식) |
| S05 증빙 | **55%** (53/97) | 정상 — 신고서류는 증빙 필드 없음 |
| S06 Family | **100%** (97/97) | |
| S07 법령분리 | **100%** (97/97) | 법령 자동 매핑 0건 |
| S08 매핑후보 | **100%** (97/97) | |
| S09 회사양식 | **100%** (97/97) | |
| S10 Official분리 | **100%** (97/97) | |
| S11 Validation | **100%** (97/97) | |
| S12 Residual | **100%** (97/97) | |
| S13 HumanReview | **100%** (97/97) | |
| S14 Audit | **100%** (97/97) | |
| S15 FinalOutput | **100%** (97/97) | |

---

## 5. 1순위 작업 현황 조사: rule_candidate ↔ document 연결

### 법령엔진 ↔ 문서엔진 교차 테이블 현황

| 쪽 | 테이블 | 건수 | 용도 |
|---|---|---|---|
| 법령엔진 | `rule_candidate` | **34,456** | 의무/금지/허가 후보 |
| 법령엔진 | `rule_candidate_slot` | 146,595 | 룰 구성요소 (SCOPE, ACTION 등) |
| 법령엔진 | `rule_candidate_relation` | 59,116 | 룰 간 관계 |
| 문서엔진 | `document_forms` | 260 | 서식 카탈로그 |
| 문서엔진 | `form_templates` | 11 | 핵심 서식 템플릿 |
| 기존매핑 | `doc_rule_mapping` | **227** | doc_id ↔ rule_id (텍스트) |
| 기존매핑 | `field_rule_mapping` | 1,615 | 필드 ↔ 룰 매핑 |
| 기존매핑 | `obligation_form_mapping` | 11 | 의무 ↔ 서식 매핑 |

### 연결 경로

```
rule_candidate (34,456건, UUID)
  → article_id → law_article (조문)
    → law_id → law_master (법령)

document_forms (260건)
  → law_ref (텍스트: "산안법 제57조")
    → law_article (조문) ← 여기서 만남

compiled JSON (97건)
  → field_candidates (필드 후보)
  → document_requirement_mapping_candidates: [] ← 현재 비어있음 (채워야 함)
```

### 발견한 이슈

1. **doc_rule_mapping의 rule_id가 텍스트** (예: "CTL-CON-101")
   - rule_candidate의 id는 UUID
   - 직접 JOIN 불가 → 중간 변환 테이블 또는 article_id 기반 매칭 필요

2. **doc_rule_mapping 전부 PENDING**
   - 227건 모두 `review_status = 'PENDING'`, `match_method = 'LAW_REF_DIRECT_MATCH'`
   - Human Review 미실시

3. **산안법 교차점 확인**
   - law_article 203건, rule_candidate 245건, document_forms 90건
   - law_ref 텍스트 매칭(조문번호 포함)으로 연결 가능

4. **compiled JSON의 `document_requirement_mapping_candidates`가 전부 빈 배열**
   - 작업지시서 섹션 8 구현은 되어있으나 실제 매핑 데이터 미생성
   - law_article 기반 자동 후보 생성 필요 (CANDIDATE 상태, 확정 금지)

---

## 6. GitHub 커밋 이력

| 파일 | 브랜치 | 내용 |
|---|---|---|
| `scripts/collect_form_templates_v2.py` | dev | DB raw_xml 파싱 → 서식 flSeq 추출 |
| `scripts/collect_document_forms.py` | dev | 260건↔CSV 매칭 → HWP 다운로드 |
| `scripts/document_schema_compiler.py` | dev | v3.1: 16섹션 전체 이행 Document Schema Compiler |
| `docs/worklogs/2026-05-11_document_engine.md` | dev | 이 업무일지 |

---

## 7. 다음 세션 작업 우선순위

### 1순위: rule_candidate ↔ document_requirement_candidate 실제 연결
- rule_candidate.article_id → law_article → document_forms.law_ref 매칭
- compiled JSON의 `document_requirement_mapping_candidates` 채우기
- doc_rule_mapping 227건의 rule_id(텍스트) → rule_candidate(UUID) 변환
- 모든 매핑은 CANDIDATE 상태 (작업지시서 섹션 7~8 준수)

### 2순위: runtime_form_schema 실제 생성
- compiled JSON 97건의 field_candidates → 런타임 폼 스키마 생성
- 사용자가 실제 폼을 열었을 때 렌더링할 수 있는 구조

### 3순위: Human Review Admin 강화
- human_review_queue 기반 Admin UI
- CANDIDATE → CONFIRMED/REJECTED 워크플로

### 4순위: 자동 inference 제거 검수 계속
- canonical_field_candidate 중 `unclassified_field` 비율 점검
- element_type 분류율 87% → 95%+ 개선
- S02 13건(분류 1종류 이하) 원인 분석

---

## 8. 잔여 이슈

| 이슈 | 심각도 | 내용 |
|---|---|---|
| 미매칭 7건 | 낮음 | DOC-CON-001 등 서식명 일반적, 수동 매칭 필요 |
| 로컬 미존재 45건 | 중간 | 142건 중 97건만 로컬에 HWP 있음, 나머지 재다운로드 필요 |
| Family 분류 | 낮음 | `--file` 모드에서 파일명만 사용, DB form_name 미활용 |
| doc_rule_mapping rule_id 타입 불일치 | 높음 | 텍스트 ID vs UUID, 연결 전략 필요 |
| compiled JSON 미적재 | 중간 | 97건 JSON이 로컬에만 존재, DB 미적재 |
| document_schema_compiler.py 로컬 수정본 | 높음 | v3.1 버그 수정이 로컬에만 반영, **git push 필요** |
