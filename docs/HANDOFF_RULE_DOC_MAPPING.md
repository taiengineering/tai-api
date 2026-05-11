# Rule ↔ Document 매핑 작업 핸드오프

> 세션 날짜: 2026-05-01
> 상태: **진행 중**

---

## 1. 배경

`law_rule_drafts` (2,583건)의 법령 의무와 `document_forms` (260건)의 문서 서식 간 N:N 매핑 작업.

이전 세션에서 `related_doc_id` (1:1 텍스트 필드)로 LIKE 키워드 매핑을 시도했으나 실패 → 전부 초기화됨.

## 2. 이번 세션 완료 사항

### 2-1. `rule_doc_mapping` 테이블 생성 (N:N)

```sql
CREATE TABLE rule_doc_mapping (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  rule_id uuid NOT NULL REFERENCES law_rule_drafts(id) ON DELETE CASCADE,
  doc_id text NOT NULL,
  relation_type text NOT NULL DEFAULT 'PRODUCES'
    CHECK (relation_type IN ('PRODUCES', 'REQUIRES', 'REFERENCES')),
  note text,
  created_at timestamptz DEFAULT now(),
  UNIQUE(rule_id, doc_id, relation_type)
);
```

**relation_type 정의:**
- `PRODUCES`: 의무 이행 시 이 문서가 산출됨
- `REQUIRES`: 의무 이행에 이 문서가 필요함
- `REFERENCES`: 의무가 이 문서를 참조/언급함

인덱스: `rule_id`, `doc_id`, `relation_type`

### 2-2. 기존 데이터 마이그레이션

`law_rule_drafts.related_doc_id` (기존 1:1 매핑) → `rule_doc_mapping`으로 이전 완료.
- 427건 마이그레이션됨 (note = NULL)
- 기존 `related_doc_id` 컬럼은 하위호환을 위해 유지

### 2-3. 배치 매핑 (SQL LIKE)

- **batch1-appoint**: APPOINT 룰 → 선임신고서 매핑 (+16건)
- **batch2-notify**: NOTIFY 룰 → 신고/통보서 매핑 (+4건)

### 2-4. Claudeception 매핑 도구 (미완성)

`tools/rule_doc_mapper.jsx` — Claude API를 사용한 법 계열별 자동 매핑 도구.
- 문서 260건 embedded
- 룰 JSON을 텍스트 영역에 붙여넣기 → Claude API 처리 → 결과 테이블 → SQL 생성
- **데이터 로딩 미완료**: 룰 데이터를 JSON으로 추출하여 도구에 입력하는 단계에서 세션 종료

## 3. 현재 수치

| 항목 | 수치 |
|------|------|
| 전체 룰 | 2,583 |
| 전체 문서 | 260 |
| 매핑 완료 | 447 (72개 문서 커버) |
| 미매핑 룰 | 2,136 |
| - 문서 관련 키워드 포함 | 801 |
| - 물리적 조치 (매핑 불필요) | 1,335 |

## 4. 미매핑 룰 법 계열별 분포 (문서 키워드 포함만)

| 법 계열 | 코드 | 건수 |
|---------|------|------|
| 기타법령 | ETC | 390 |
| 고압가스법 | HGAS | 72 |
| 소방법 | FIRE | 62 |
| 산안법 | OSH | 53 |
| 위험물법 | HZMT | 46 |
| LPG법 | LPG | 42 |
| 화학물질법 | CHEM | 39 |
| 도시가스법 | UGAS | 29 |
| 재난안전법 | DSMT | 27 |
| 승강기법 | ELEV | 16 |
| 전기안전법 | ELEC | 10 |
| 중대재해법 | SERA | 8 |
| 안전보건규칙 | OSH_R | 7 |

## 5. 이슈 & 교훈

### SQL LIKE 매핑의 한계
- `obligation_summary` 텍스트가 일관성 없어 LIKE 패턴 매칭 정확도 낮음
- 예: "건강진단 실시" → "특수건강진단결과서" 연결 불가
- 조문번호 매칭도 본법/시행령/시행규칙 간 번호 불일치로 실패

### N:N 관계 발견
- 하나의 문서를 충족하기 위해 여러 의무 필요
- 하나의 의무가 여러 문서 산출 가능
- 기존 `related_doc_id` (1:1) → `rule_doc_mapping` (N:N) 전환 이유

### Claudeception 접근법 선택 이유
- Python TF-IDF/코사인 유사도 = 결국 패턴 매칭 (SQL LIKE와 같은 한계)
- Claude API = 법률 용어의 의미적 관계 이해 가능
- relation_type (PRODUCES/REQUIRES/REFERENCES) 구분 가능

## 6. 다음 세션 작업

### 6-1. 룰 데이터 추출

아래 쿼리로 법 계열별 룰 JSON 추출:

```sql
SELECT json_agg(json_build_object(
  'i', id, 'f', '<FAMILY_CODE>', 'o', LEFT(obligation_summary, 60), 't', obligation_type
)) FROM law_rule_drafts
WHERE id NOT IN (SELECT rule_id FROM rule_doc_mapping)
  AND law_name LIKE '%<법률명키워드>%'
  AND (obligation_summary LIKE '%보고%' OR ... 문서 키워드 ...);
```

### 6-2. Claudeception 매핑 실행

1. `tools/rule_doc_mapper.jsx` 아티팩트 열기
2. 법 계열별 룰 JSON 붙여넣기
3. 법 계열 선택 → "Claude API 매핑 실행"
4. 결과 검토 후 SQL 생성
5. 생성된 SQL을 Supabase에서 실행

### 6-3. 처리 순서 (작은 것부터)

1. SERA (8건) — 테스트
2. OSH_R (7건)
3. ELEC (10건)
4. ELEV (16건)
5. DSMT (27건)
6. UGAS (29건)
7. CHEM (39건)
8. LPG (42건)
9. HZMT (46건)
10. OSH (53건)
11. FIRE (62건)
12. HGAS (72건)
13. ETC (390건) — 가장 마지막, 분할 처리

### 6-4. 매핑 후 검증

```sql
-- 매핑 현황
SELECT relation_type, COUNT(*) FROM rule_doc_mapping GROUP BY 1;

-- 문서별 매핑 수
SELECT d.doc_id, d.doc_name, COUNT(m.id) as mapping_count
FROM document_forms d
LEFT JOIN rule_doc_mapping m ON m.doc_id = d.doc_id
GROUP BY d.doc_id, d.doc_name
ORDER BY mapping_count DESC;

-- 매핑 0건 문서
SELECT d.doc_id, d.doc_name
FROM document_forms d
LEFT JOIN rule_doc_mapping m ON m.doc_id = d.doc_id
WHERE m.id IS NULL;
```

## 7. 관련 파일

- `tools/rule_doc_mapper.jsx` — Claudeception 매핑 도구 (React)
- Supabase 테이블: `rule_doc_mapping`, `law_rule_drafts`, `document_forms`
- Supabase Project: `vwlahtguyggrhvslabax` (서울)
