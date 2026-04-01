# 백엔드 작업지시서 — B-CON-002
# 건설 Step1 룰 데이터 정비

> 작성일: 2026-04-01  
> 우선순위: 🔴 긴급  
> 작업 대상: Supabase MCP execute_sql

---

## 배경

현재 master_building_legal_rules CONSTRUCTION Step1 185개 룰에서:
- `construction_work_type` = 전부 NULL → 건축/토목 기준금액 구분 불가
- `condition_code` = 160개 NULL → 공통적용 의도인지 조건 누락인지 불명확

---

## 작업 1 — construction_work_type 값 입력

### 배경
산안법 시행령 별표4: 건축 150억 이상 / 토목 120억 이상 → 안전관리자 선임 의무
현재 work_type이 NULL이어서 건축/토목 구분 판정 불가.

### 실행 쿼리

```sql
-- 건축공사 기준 룰 (150억)
UPDATE master_building_legal_rules
SET construction_work_type = '건축',
    construction_work_type_label = '건축공사 (기준금액 150억)'
WHERE sector = 'CONSTRUCTION'
  AND diagnosis_stage = 1
  AND rule_id IN ('CONST-003', 'OSH-CON-102');
-- ※ CONST-003은 오늘 이미 비활성화됨. OSH-CON-102만 유효

-- 토목공사 기준 룰 (120억)
UPDATE master_building_legal_rules
SET construction_work_type = '토목',
    construction_work_type_label = '토목공사 (기준금액 120억)'
WHERE sector = 'CONSTRUCTION'
  AND diagnosis_stage = 1
  AND rule_id IN ('CONST-004', 'OSH-CON-101');
-- ※ CONST-004는 이미 비활성화됨. OSH-CON-101만 유효

-- 나머지 모든 Step1 룰 → 공통(건축+토목 모두 적용)
UPDATE master_building_legal_rules
SET construction_work_type = '공통',
    construction_work_type_label = '건축·토목 공통'
WHERE sector = 'CONSTRUCTION'
  AND diagnosis_stage = 1
  AND construction_work_type IS NULL;
```

### 검증 쿼리
```sql
SELECT construction_work_type, COUNT(*) as cnt
FROM master_building_legal_rules
WHERE sector = 'CONSTRUCTION' AND diagnosis_stage = 1
GROUP BY construction_work_type;
-- 기대 결과: 건축 1개, 토목 1개, 공통 183개
```

---

## 작업 2 — Step1 조건 없는 룰 160개 분류

### 분류 기준

조건 없는 160개를 아래 3가지로 분류:

| 분류 | 의미 | 처리 |
|------|------|------|
| `COMMON` | 건설현장 등록만 해도 무조건 적용 (조건 불필요) | condition_code NULL 유지, remarks에 'COMMON' 표기 |
| `NEED_CONDITION` | summary에 조건이 언급되어 있으나 condition_code 미입력 | condition_code 입력 필요 |
| `SECTOR_MISMATCH` | 건설과 무관하거나 조건 불명확 | is_active = false 처리 |

### COMMON으로 확정할 룰 (건설현장 모두 적용)

```sql
-- 중대재해 현장보존, 도급 협의체, 기초교육 등 → 무조건 공통 적용
UPDATE master_building_legal_rules
SET remarks = COALESCE(remarks,'') || ' [COMMON: 건설현장 공통적용]'
WHERE sector = 'CONSTRUCTION'
  AND diagnosis_stage = 1
  AND condition_code IS NULL
  AND rule_id IN (
    'CON1-ACC-002',  -- 중대재해 현장보존
    'CON1-CON-001',  -- 안전보건협의체 구성
    'CON1-CON-002',  -- 도급인 협의 의무
    'CON1-EDU-002',  -- 특별교육
    'CON1-REG-001',  -- 안전보건관리규정 (100인 이상 → NEED_CONDITION으로 이동)
    'CONST-IND-003', -- 건설업 시공능력 유지
    'CONST-TECH-001',-- 안전관리계획 수립
    'CONST-TECH-005',-- 품질관리
    'CONST-TECHR-002'-- 안전관리계획 확인
  );
```

### NEED_CONDITION으로 확정 — 조건이 summary에 있으나 미입력

```sql
-- 100인 이상 조건이 summary에 명시된 룰
UPDATE master_building_legal_rules
SET condition_code = 'employee_count',
    condition_operator_code = 'gte',
    condition_value = 100,
    remarks = COALESCE(remarks,'') || ' [NEED_CONDITION 복원: 100인이상]'
WHERE sector = 'CONSTRUCTION'
  AND diagnosis_stage = 1
  AND rule_id IN (
    'CON1-COM-001',  -- 산업안전보건위원회 (100인 이상)
    'CON1-COM-002',  -- 위원회 분기 개최 (100인 이상)
    'CON1-REG-001'   -- 안전보건관리규정 (100인 이상)
  );
```

### SECTOR_MISMATCH — 건설과 무관 또는 조건 불명확한 환경/화학 룰

```sql
-- 대기환경, 화학물질, 에너지 등 건설 전용이 아닌 범용 룰
-- 조건 없이 모든 건설현장에 적용하면 과잉 판정됨 → 비활성화
UPDATE master_building_legal_rules
SET is_active = false,
    remarks = COALESCE(remarks,'') || ' [SECTOR_MISMATCH: 건설전용 아님, 조건미정]'
WHERE sector = 'CONSTRUCTION'
  AND diagnosis_stage = 1
  AND condition_code IS NULL
  AND rule_id LIKE '%-CON'
  AND law_name IN (
    '대기환경보전법 시행령',
    '대기환경보전법 시행규칙',
    '화학물질의 등록 및 평가 등에 관한 법률',
    '화학물질의 등록 및 평가 등에 관한 법률 시행령',
    '화학물질의 분류·표시 및 물질안전보건자료에 관한 기준',
    '유해화학물질별 구체적인 취급기준에 관한 규정',
    '화학물질관리법 시행규칙',
    '에너지이용 합리화법',
    '전기공사업법 시행령'
  );
```

---

## 작업 3 — 최종 현황 검증

```sql
SELECT
  diagnosis_stage,
  is_active,
  COUNT(*) as total,
  SUM(CASE WHEN condition_code IS NULL THEN 1 ELSE 0 END) as null_cond,
  SUM(CASE WHEN construction_work_type IS NULL THEN 1 ELSE 0 END) as null_worktype
FROM master_building_legal_rules
WHERE sector = 'CONSTRUCTION'
GROUP BY diagnosis_stage, is_active
ORDER BY diagnosis_stage, is_active;
```

---

## 완료 기준

- [ ] construction_work_type NULL = 0개 (활성 룰 기준)
- [ ] Step1 조건 없는 룰 = 전부 COMMON 확정 또는 condition 복원 또는 비활성화 처리
- [ ] law_master 미연결 룰 = 0개 (이미 완료)
