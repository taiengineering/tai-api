# WO-TAI-DOC-LAWREF-P1-001 — 보호구 문서 법령 참조 정정 계획서

**작성일**: 2026-10-21  
**작업 유형**: 정정 계획 (PLAN ONLY — 운영 DB 미수정)  
**기준 커밋**: d7521e05

---

## 1. 정정 대상 확인

### 현재 DB 상태 (직접 조회 결과)

| doc_id | doc_name | 현재 law_ref | tai_auto | is_active |
|--------|----------|------------|---------|----------|
| DOC-OSH-045 | 보호구 지급대장 | `산안법 제41조` | true | true |
| DOC-OSH-046 | 보호구 착용 점검기록 | `산안법 제41조` | false | true |

### 오류 확인

- 현행 산업안전보건법 제41조 = 고객의 폭언 등으로 인한 건강장해 예방조치. 보호구와 **전혀 무관**.
- 두 문서 모두 동일 오류값 보유.

---

## 2. 정정 근거

| 법령 | 내용 | law_key |
|------|------|---------|
| 산업안전보건기준에 관한 규칙 제32조 | 보호구의 **지급** 및 착용 의무 | 007363_273603 |
| (지급대장 보존 의무 별도 규정) | 제32조에 명시 없음 — 확인 미완료 | — |

**정정 값 결정 근거**:
- 기존 `document_forms.law_ref` 약어 패턴: `"산안기준"`, `"안전보건규칙 제N조"` 형식 사용. (`안전보건규칙 제657조`, `안전보건규칙 제662조` 확인)
- 산업안전보건기준에 관한 규칙 = **"안전보건규칙"** (기존 테이블 사용 약어).
- 정정값: **`안전보건규칙 제32조`**

**중요 한계 명시**: 
- 제32조는 보호구 지급·착용 **의무**의 근거. 지급대장·점검기록 자체의 법정 **작성·보존** 의무는 제32조에 명시되어 있지 않음.
- law_ref 정정은 조문 오류를 바로잡는 것이며, 해당 서식이 법정 필수서식임을 주장하는 것이 아님.

---

## 3. 변경 전후 비교

| doc_id | doc_name | 변경 전 | 변경 후 |
|--------|----------|--------|--------|
| DOC-OSH-045 | 보호구 지급대장 | `산안법 제41조` | `안전보건규칙 제32조` |
| DOC-OSH-046 | 보호구 착용 점검기록 | `산안법 제41조` | `안전보건규칙 제32조` |

**변경 범위**: `document_forms` 테이블 2행, `law_ref` 컬럼만 수정. 다른 컬럼·테이블 변경 없음.

---

## 4. 실행 SQL (PRJ 승인 후 실행)

```sql
-- 실행 전 현재 값 확인 (READ-ONLY)
SELECT doc_id, doc_name, law_ref
FROM document_forms
WHERE doc_id IN ('DOC-OSH-045', 'DOC-OSH-046');

-- 정정 실행 (PRJ 승인 후만 실행)
UPDATE document_forms
SET law_ref = '안전보건규칙 제32조',
    updated_at = NOW()
WHERE doc_id IN ('DOC-OSH-045', 'DOC-OSH-046')
  AND law_ref = '산안법 제41조';

-- 실행 후 검증 (READ-ONLY)
SELECT doc_id, doc_name, law_ref, updated_at
FROM document_forms
WHERE doc_id IN ('DOC-OSH-045', 'DOC-OSH-046');
```

**예상 결과**: `UPDATE 2` (2행 변경). WHERE 조건에 기존값(`산안법 제41조`) 포함으로 의도치 않은 변경 방지.

---

## 5. 검증 SQL

```sql
-- 검증 1: 변경 후 올바른 값 확인
SELECT doc_id, doc_name, law_ref
FROM document_forms
WHERE doc_id IN ('DOC-OSH-045', 'DOC-OSH-046');
-- 기대값: 두 행 모두 law_ref = '안전보건규칙 제32조'

-- 검증 2: 산안법 제41조 참조 잔존 여부 확인
SELECT doc_id, doc_name, law_ref
FROM document_forms
WHERE law_ref = '산안법 제41조';
-- 기대값: 0행 (DOC-OSH-045, 046 외 다른 문서에 없음을 확인)

-- 검증 3: 안전보건규칙 제32조 참조 문서 전체 확인
SELECT doc_id, doc_name, law_ref
FROM document_forms
WHERE law_ref = '안전보건규칙 제32조';
-- 기대값: DOC-OSH-045, DOC-OSH-046 2행
```

---

## 6. 롤백 방법

```sql
-- 롤백 (원복 필요 시)
UPDATE document_forms
SET law_ref = '산안법 제41조',
    updated_at = NOW()
WHERE doc_id IN ('DOC-OSH-045', 'DOC-OSH-046')
  AND law_ref = '안전보건규칙 제32조';
```

**롤백 조건**: 정정 후 시스템 오류 또는 Owner 철회 요청 시. 롤백해도 근본 오류는 유지되므로 재검토 후 다시 정정 필요.

---

## 7. 제외 항목

| 항목 | 상태 |
|------|------|
| DOC-CHEM-004 `화학물질관리법 제41조` | 이번 P1 범위 아님. 별도 검증 필요. |
| 법령 버전 동기화 (P2) | 별도 PRJ·LEG 파이프라인 승인 필요. |
| 법정 작성·보존 의무 조항 확인 | 법령 조사 미완료. 별도 WO 대상. |
| 82쌍 재분석, PROPOSED 자동 등록 | 완전 제외. |

---

## 8. 제출 상태

```
WO = WO-TAI-DOC-LAWREF-P1-001

PLAN_STATUS = READY
TARGET_DOCS = 2 (DOC-OSH-045, DOC-OSH-046)
CHANGE_COLUMN = document_forms.law_ref
BEFORE = '산안법 제41조'
AFTER  = '안전보건규칙 제32조'

LAW_BASIS = 안전보건기준에 관한 규칙 제32조 (지급·착용 의무)
LEGAL_FORMAT_CLAIM = 없음 (법정 필수서식 주장 아님)
FORMAT_CONVENTION = 기존 '안전보건규칙 제N조' 패턴 준수

ROLLBACK_SQL = 준비됨
VALIDATION_SQL = 준비됨

PRODUCTION_WRITE = 0 (GPT IV + PRJ 승인 전 미실행)
NEW_DEVELOPMENT = 0

P1_CHANGE_PLAN_READY
```
