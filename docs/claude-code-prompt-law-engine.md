# Claude Code 작업지시 — 법령엔진 수집엔진 보강 (보조/검증)

## 배경
TAI Safe 법령엔진 보강. 이슈 #24.
기준 문서: `docs/law-engine-enhancement-workorder.md` (dev, v2.1)

Cursor가 메인 코드 작업 담당. Claude Code는 보조 작업 + 검증 담당.

---

## TASK 1: tai_feature_code DDL 실행

```sql
ALTER TABLE master_building_legal_rules
  ADD COLUMN IF NOT EXISTS tai_feature_code VARCHAR(50);

COMMENT ON COLUMN master_building_legal_rules.tai_feature_code IS 
  'TAI 기능 연결: APPOINTMENT/INSPECTION/REPORT/EDUCATION/DOCUMENT/FIX/CHECKLIST';
```

터미널 또는 Supabase Dashboard에서 실행.

---

## TASK 2: tai_feature_code 자동 매핑 (기존 데이터)

master 1,133건 활성 룰에 tai_feature_code를 일괄 매핑.
의무 유형별 규칙:

```sql
-- APPOINTMENT: 선임 의무
UPDATE master_building_legal_rules
SET tai_feature_code = 'APPOINTMENT'
WHERE appointment_required = true AND tai_feature_code IS NULL;

-- INSPECTION: 점검 의무  
UPDATE master_building_legal_rules
SET tai_feature_code = 'INSPECTION'
WHERE inspection_required = true AND tai_feature_code IS NULL;

-- REPORT: 신고/보고 의무
UPDATE master_building_legal_rules
SET tai_feature_code = 'REPORT'
WHERE (report_required = true OR notify_required = true) AND tai_feature_code IS NULL;

-- CHECKLIST: 작업 전 조치 의무
UPDATE master_building_legal_rules
SET tai_feature_code = 'CHECKLIST'
WHERE action_required = true AND tai_feature_code IS NULL;

-- 나머지: obligation_type 기반
UPDATE master_building_legal_rules
SET tai_feature_code = CASE
  WHEN obligation_type = 'APPOINT' THEN 'APPOINTMENT'
  WHEN obligation_type = 'INSPECT' THEN 'INSPECTION'
  WHEN obligation_type = 'NOTIFY' THEN 'REPORT'
  WHEN obligation_type = 'REPORT' THEN 'DOCUMENT'
  WHEN obligation_type = 'ACTION' THEN 'CHECKLIST'
  ELSE NULL
END
WHERE tai_feature_code IS NULL AND obligation_type IS NOT NULL;
```

실행 후 확인:
```sql
SELECT tai_feature_code, COUNT(*) 
FROM master_building_legal_rules 
WHERE is_active = true 
GROUP BY tai_feature_code;
```

---

## TASK 3: 무결성 사전 점검 (validate 로직 검증용)

Cursor가 validate-master 엔드포인트를 만들기 전에, 현재 상태를 SQL로 확인:

```sql
-- 1. condition 깨진 건수
SELECT COUNT(*) as broken_condition
FROM master_building_legal_rules
WHERE is_active = true
  AND condition_code IS NOT NULL
  AND (condition_operator_code IS NULL OR condition_value IS NULL);

-- 2. inspection 필수인데 주기 없는 건수  
SELECT COUNT(*) as missing_cycle
FROM master_building_legal_rules
WHERE is_active = true
  AND inspection_required = true
  AND (inspection_cycle_value IS NULL OR inspection_cycle_unit_code IS NULL);

-- 3. report 필수인데 method 없는 건수
SELECT COUNT(*) as missing_report_method
FROM master_building_legal_rules
WHERE is_active = true
  AND report_required = true
  AND report_method_code IS NULL;

-- 4. appointment 필수인데 자격 없는 건수
SELECT COUNT(*) as missing_qualification
FROM master_building_legal_rules
WHERE is_active = true
  AND appointment_required = true
  AND appointment_qualification_code IS NULL;

-- 5. penalty 필수인데 값 없는 건수
SELECT COUNT(*) as missing_penalty
FROM master_building_legal_rules
WHERE is_active = true
  AND penalty_required = true
  AND penalty_value IS NULL;

-- 6. 전체 빈칸 현황 (6하원칙)
SELECT 
  COUNT(*) as total,
  COUNT(NULLIF(penalty_summary,'')) as has_why,
  COUNT(appointment_qualification_code) as has_who,
  COUNT(CASE WHEN due_days > 0 THEN 1 END) as has_when_days,
  COUNT(cycle_base_guide) as has_when_cycle,
  COUNT(submit_org_code) as has_where,
  COUNT(form_name) as has_how_form,
  COUNT(report_method_code) as has_how_method,
  COUNT(tai_feature_code) as has_tai
FROM master_building_legal_rules
WHERE is_active = true;
```

이 결과를 기록해두면 Cursor 작업 후 비교 가능.

---

## TASK 4: reparse 테스트 데이터 준비

Cursor가 reparse-master를 구현하면 테스트할 3건:

```sql
-- 테스트 대상 확인
SELECT rule_id, law_name, law_article, 
       condition_code, condition_operator_code, condition_value,
       penalty_summary, form_name, report_method_code,
       appointment_qualification_code
FROM master_building_legal_rules
WHERE rule_id IN ('FIREACT-005-MFG', 'ENERGYACT-002', 'ODORACTS-001-MFG');
```

reparse 후 동일 쿼리 실행하여 빈칸이 채워졌는지 확인.

---

## TASK 5: Cursor 작업 후 코드 리뷰

Cursor가 PR 올리면 확인할 사항:
1. `services/law_context_builder.py`가 시행령+별표+벌칙을 제대로 조립하는지
2. 시스템 프롬프트에 condition_code 24개 전부 있는지
3. reparse-master가 Sonnet 모델을 사용하는지 (Haiku 아님)
4. validate-master 검증 규칙이 7개 전부 구현됐는지
5. few-shot 예시가 포함됐는지
6. submit_org_code 한글 매핑 상수가 있는지

---

## 개발 규칙
- `from db.supabase_client import get_supabase`
- main 직접 push 금지 → dev → PR → main
- git checkout origin/dev 전 git fetch 필수
- 200줄+ 파일 MCP 수정 금지 → Cursor
