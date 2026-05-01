# 5/1 세션 — 룰/문서/점검 통합 + 데이터 분리 정책

**날짜**: 2026-05-01  
**프로젝트**: vwlahtguyggrhvslabax (서울 리전, taieng)  
**핵심 결정**: 데이터 분리 정책 적용 — 메인 테이블은 운영 데이터만

---

## 핵심 결정 사항

### 정책 변경
- **메인 테이블 컬럼 추가 금지** = 시스템 전체 변경 발생
- **사용 안 하는 데이터는 별도 테이블로 분리**
- 정제 ≠ 운영 (다른 차원)
  - 정제 = 룰 신뢰도 (drafts.APPROVED)
  - 운영 = 사업장 적용 (공장이면 산안+소방+화학+가스 등)

---

## 데이터 분리 결과

### 4개 테이블 구조

| 테이블 | 행수 | 의미 |
|---|---|---|
| `master_building_legal_rules` (운영) | **1,998** | 정제 거친 룰 1,601 + AGENCY_API 397 (사업장 적용) |
| `master_legal_rules_preserved` (보관) | **321** | TECHNICAL_STANDARD (NFTC 기술기준) |
| `master_legal_rules_pending_review` (검토) | **1,468** | UNKNOWN_SOURCE 752 + AI_GENERATED 714 + 기타 2 |
| `master_legal_rules_archive` (폐기) | **44** | 4월 정제 중복 33 + SPECIAL_FACILITY 잔재 11 |
| 합계 | 3,831 | |

### 사용자 기억 "1,900대"의 정체
- `law_rule_drafts.status='APPROVED'` = 1,988 (정제 결과)
- `master_building_legal_rules` 운영 = 1,998 (운영 룰)
- 둘 다 정확

---

## doc_rule_mapping 재구성 (최종)

### 변화
| 항목 | 이전 | 이후 |
|---|---|---|
| `doc_rule_mapping` (운영) | 616 | **198** (재구성) |
| `doc_rule_mapping_preserved` | 0 | 165 |
| `doc_rule_mapping_pending_review` | 0 | 183 |
| 고아 매핑 | 117 | 0 (정리됨) |

### 매핑 효과 (1,998 기준)
- 매핑 총수: **198건**
- **문서 커버리지: 38.1% (99/260)**
- 룰 커버리지: 5.5% (110/1998)
- 매칭 방식: `LAW_REF_DIRECT_MATCH` — 100% 결정론적, 임의해석 0%

### 매칭 로직 (3단계)
1. `document_forms.required_fields[i].law_ref` 파싱
2. **단일 표기**: parsed_law_name + parsed_article 매칭
3. **혼합 표기**: "법령1 제N조, 법령2 제M조" → 콤마 분리 + "시행규칙/시행령" 컨텍스트 보강
4. law_alias로 약칭 변환 (산안법 → 산업안전보건법 등) + 공백 정규화

### 매칭 진화
- 1단계 (정확 매칭): 67건
- 2단계 (alias + 공백): 114건 (+70%)
- 3단계 (master 1,998 적용): 169건 (+48%)
- 4단계 (혼합 표기 분리): **198건** (+17%)

### law_alias 등록 (15건)
- 기존: 산안법, 고압가스안전관리법, 승강기안전관리법 등 11건
- 신규: 산안법 시행규칙, 산안법 시행령, 안전보건규칙, 시설물안전법 4건

---

## 정제 흐름 완전 복원

```
[4/7 5차 세션] 활성 룰 ~1,196건
  ↓ 4/22 KICKOFF — 새 법령엔진 시작
[4/23 ATOMIC SWITCH] 182 laws / 60,636 records
  - law_article: 10,974 / law_paragraph: 20,125 / law_item: 28,813
  ↓ Claude Sonnet (auto_parse_parallel.py) 의무 추출
law_rule_drafts 2,583
  ├ APPROVED 1,988 → master 등록 1,601
  ├ PENDING 542 / REJECTED 46 / NEEDS_REVIEW 6
  ↓
master_building_legal_rules 운영 1,998
  ├ 1,601: drafts 정제 거친 (산안법 위주)
  └ 397: 부처 API 직접 수집 (소방/화학/가스/위험물/환경 등 사업장 적용)
```

---

## 매핑 한계 (62% 미매핑) — 다음 세션 작업

### 매핑 안 된 161 문서의 패턴

| 원인 | 건수 | 다음 세션 작업 |
|---|---|---|
| master 운영에 없는 조문 (pending_review에 있음) | ~15+ | pending_review 산안법 룰 검토 후 master 복귀 |
| master에 없는 법령 (석면, 화학물질등록평가법) | 8 | 추가 정제 필요 |
| 모호 표기 ("법", "시행규칙" 단독) | 11 | 컨텍스트 보강 |
| 조문번호 없는 law_ref | 143 | 문서 데이터 보강 (GPT 작업 필요) |

### 발견된 핵심 인사이트
- 산안법 일부 조문은 master 운영에 없고 pending_review에 있음
  - 예: "산안법 제36조" → pending에 3건, "산안법 제64조" → pending에 3건
  - 이유: NULL/AI_GENERATED 출처라 분리됨
  - 다음 세션: pending_review의 산안법 조문 출처 추적 후 검증 시 master 복귀 검토

---

## 다음 세션 우선순위

### 즉시 진행
1. **pending_review 산안법 룰 검토** — 매핑 안 된 산안법 조문이 pending에 있음
2. **부분 일치 48건 검토** (3월 잔재 중 3개키 16 + 2개키 32)
3. **inspection_master 영향 확인** — master 1,998 변경 후 점검 항목 동기화

### 검토 후 결정
4. **NULL 출처 752개 추적** (pending_review) — 출처 식별 가능한지
5. **AI_GENERATED 716개 추적** — 어떤 AI/언제/어떻게 생성됐는지
6. **TECHNICAL_STANDARD 321 (NFTC) 활용 방안** — 점검 마스터에 직접 사용 가능한지

### 운영 전
7. inspection_set_items 사업장 인스턴스 시드
8. safety_inspection_results 운영 시작

---

## 데이터 품질 등급 재정의

```
master_building_legal_rules 운영 1,998
├─ A등급 (1,601): drafts.APPROVED 정제 거침 ✅
└─ A'등급 (397): 부처 API 직접 수집 (출처 신뢰, 정제 안 거침)

master_legal_rules_preserved 321
└─ B등급: TECHNICAL_STANDARD (NFTC, 너무 세분화)

master_legal_rules_pending_review 1,468
├─ C등급 (752): UNKNOWN_SOURCE
└─ D등급 (716): AI_GENERATED

master_legal_rules_archive 44
└─ E등급: 폐기/대체됨
```

---

## 사용자 작업 원칙 (절대 준수)

1. **임의해석 금지** — AI 의미 매칭 거부, 법령 텍스트 기반만
2. **결정론적 매칭만** (4개 키: law_name + law_article + obligation_type + condition_code)
3. **메인 테이블 깔끔 유지** — 컬럼 추가 금지, 별도 테이블 분리
4. **DELETE 대신 분리 보관** — 데이터 손실 방지
5. **한 번에 하나씩만 진행** — 비개발자 사용자 결정 단순화
6. **신뢰 추락 방지** — 잘못 매핑 시 모든 사용업체가 안 해도 될 의무 수행

---

## 핵심 SQL (재실행용)

### 매핑 재구성 SQL (단일 + 혼합 표기 통합)
```sql
-- 단일 표기 매칭
DELETE FROM doc_rule_mapping;
WITH law_ref_parsed AS (
  SELECT df.doc_id, rf->>'field_key' as field_key, rf->>'field_name' as field_name,
    rf->>'law_ref' as law_ref,
    (regexp_match(rf->>'law_ref', '(제\d+조(?:의\d+)?)\s*$'))[1] as parsed_article,
    trim(regexp_replace(rf->>'law_ref', '\s*제\d+조(?:의\d+)?\s*$', '')) as parsed_law_name
  FROM document_forms df, jsonb_array_elements(df.required_fields) rf
  WHERE rf->>'law_ref' IS NOT NULL AND rf->>'law_ref' != ''
),
law_ref_resolved AS (
  SELECT lrp.doc_id, lrp.field_key, lrp.field_name, lrp.law_ref, lrp.parsed_article,
    COALESCE(
      (SELECT m.law_name FROM master_building_legal_rules m WHERE m.law_name = lrp.parsed_law_name LIMIT 1),
      (SELECT la.full_name FROM law_alias la WHERE la.short_name = lrp.parsed_law_name LIMIT 1),
      (SELECT m.law_name FROM master_building_legal_rules m 
       WHERE replace(m.law_name, ' ', '') = replace(lrp.parsed_law_name, ' ', '') LIMIT 1)
    ) as resolved_law_name
  FROM law_ref_parsed lrp
),
matched AS (
  SELECT lrr.doc_id, m.rule_id,
    array_agg(DISTINCT lrr.law_ref) as source_law_refs,
    array_agg(DISTINCT lrr.field_key) as source_field_keys,
    array_agg(DISTINCT lrr.field_name) as source_field_names
  FROM law_ref_resolved lrr
  JOIN master_building_legal_rules m ON m.law_name = lrr.resolved_law_name AND m.law_article = lrr.parsed_article
  WHERE lrr.resolved_law_name IS NOT NULL
  GROUP BY lrr.doc_id, m.rule_id
)
INSERT INTO doc_rule_mapping (...)
SELECT ... FROM matched ON CONFLICT (doc_id, rule_id) DO NOTHING;

-- 혼합 표기 매칭 (콤마 분리)
WITH mixed_law_refs AS (
  SELECT df.doc_id, rf->>'field_key' as field_key, rf->>'field_name' as field_name,
    rf->>'law_ref' as original_law_ref,
    trim(unnest(string_to_array(rf->>'law_ref', ','))) as part
  FROM document_forms df, jsonb_array_elements(df.required_fields) rf
  WHERE rf->>'law_ref' LIKE '%,%'
),
parsed_parts AS (
  SELECT doc_id, field_key, field_name, original_law_ref, part,
    (regexp_match(part, '(제\d+조(?:의\d+)?)\s*$'))[1] as part_article,
    CASE 
      WHEN trim(regexp_replace(part, '\s*제\d+조(?:의\d+)?\s*$', '')) IN ('시행규칙', '시행령') THEN
        trim(regexp_replace((string_to_array(original_law_ref, ','))[1], '\s*제\d+조(?:의\d+)?\s*$', '')) || ' ' || 
        trim(regexp_replace(part, '\s*제\d+조(?:의\d+)?\s*$', ''))
      ELSE trim(regexp_replace(part, '\s*제\d+조(?:의\d+)?\s*$', ''))
    END as part_law_name
  FROM mixed_law_refs
)
-- ... resolved + matched + INSERT (위 패턴 동일)
```

### 데이터 분리 테이블 구조
- `master_legal_rules_archive`: LIKE INCLUDING ALL + archived_at, archive_reason
- `master_legal_rules_preserved`: LIKE INCLUDING ALL + preserved_at, preservation_category
- `master_legal_rules_pending_review`: LIKE INCLUDING ALL + moved_at, review_category
- `doc_rule_mapping_preserved`: LIKE INCLUDING ALL + moved_at
- `doc_rule_mapping_pending_review`: LIKE INCLUDING ALL + moved_at

---

**작성일**: 2026-05-01  
**최종 매핑**: 198건 (38.1% 문서 커버리지) — 100% 결정론적  
**다음 세션**: pending_review 산안법 룰 검토로 추가 매핑 가능
