# TAI Safe 신규 창 시작 프롬프트
**작성일: 2026-04-06 3차 세션 종료 | 목적: 법령엔진·데이터 고도화**

---

## 🎯 현재 상황 요약

### 완료된 것
- ✅ 법령엔진 v5.6.4 운영 중 (https://api.taieng.co.kr/ → version: 5.6.4)
- ✅ GitHub Actions CI 파이프라인 완성 — push 시 자동으로 78건 무결성 검증
  - `.github/workflows/integrity.yml` (3-Job)
  - `tests/check_db_integrity.py`, `tests/check_mapping_coverage.py`, `tests/wait_for_deploy.py`
- ✅ DB 제약조건 5개 추가 (APPOINT target 필수, 영문 형식, INSPECT executor 필수 등)
- ✅ DB 데이터 수정 (height_work→has_high_work, 비활성화 6건)
- ✅ 78건 무결성 테스트 ALL PASS 확인

### 미완료
- ⚠️ Railway "Wait for CI" 미활성 — Service → Settings → GitHub → Wait for CI 체크 필요

---

## 📋 이번 세션 목표: 법령엔진·데이터 고도화

### 1️⃣ 현황 파악 (시작 시 반드시 실행)
```sql
-- 섹터별 INSPECT 4완비율 확인
SELECT
  sector,
  COUNT(*) AS total,
  COUNT(CASE WHEN condition_code IS NOT NULL
             AND inspection_cycle_unit_code IS NOT NULL
             AND executor_type_code IS NOT NULL
             AND law_article IS NOT NULL THEN 1 END) AS complete_4,
  ROUND(COUNT(CASE WHEN condition_code IS NOT NULL
                   AND inspection_cycle_unit_code IS NOT NULL
                   AND executor_type_code IS NOT NULL
                   AND law_article IS NOT NULL THEN 1 END)::numeric
        / COUNT(*) * 100, 1) AS ratio
FROM master_building_legal_rules
WHERE obligation_type = 'INSPECT' AND is_active = true
GROUP BY sector ORDER BY sector;
```

### 2️⃣ 고도화 대상 (우선순위순)

**BUILDING INSPECT 미완비 18건**
```sql
SELECT rule_id, law_name, condition_code, inspection_cycle_unit_code, executor_type_code
FROM master_building_legal_rules
WHERE obligation_type='INSPECT' AND sector='BUILDING' AND is_active=true
  AND (condition_code IS NULL
    OR inspection_cycle_unit_code IS NULL
    OR executor_type_code IS NULL)
ORDER BY law_name;
```

**MANUFACTURING INSPECT condition 미설정건**
```sql
SELECT rule_id, law_name, obligation_summary, condition_code
FROM master_building_legal_rules
WHERE obligation_type='INSPECT' AND sector='MANUFACTURING'
  AND is_active=true AND condition_code IS NULL
ORDER BY law_name;
```

**건설 BEFORE_WORK 64건 — 주기 없는 작업전 점검**
```sql
SELECT rule_id, law_name, obligation_summary, construction_work_type
FROM master_building_legal_rules
WHERE obligation_type='INSPECT' AND sector='CONSTRUCTION'
  AND is_active=true AND inspection_cycle_unit_code IS NULL
ORDER BY law_name;
```

**PENDING 263개 검토**
```sql
SELECT status, COUNT(*) FROM law_rule_drafts GROUP BY status;
```

### 3️⃣ 수정 후 필수 검증
```
GitHub push → Actions 자동 실행 → 3개 Job 모두 ✅ 확인
```
수동 검증이 필요하면:
```
https://github.com/taiengineering/tai-api/actions 에서 결과 확인
```

---

## 📌 엔진 핵심 상수 (변경 금지)

### 가스 단계별 임계값
```
gas_capacity_kg >= 1    → 기본 점검/선임
gas_capacity_kg >= 100  → 정기검사 (고압가스안전관리법)
gas_capacity_kg >= 300  → 추가 검사
gas_capacity_kg >= 1000 → 특별 의무
```
이 값들은 법적 기준값 — 절대 수정 금지

### ENGINE_CONTEXT_KEYS (check_mapping_coverage.py와 동기화 필수)
새 condition_code를 DB에 추가하면 반드시:
1. `routers/legal_engine.py` `CONDITION_CODE_TO_CONTEXT_KEY` 또는 `_input_to_facility_context()`에 추가
2. `tests/check_mapping_coverage.py` `ENGINE_CONTEXT_KEYS` 셋에 추가
3. GitHub push → CI 통과 확인

### has_appt() 비교 주의
엔진이 `appointment_target`을 한글 레이블로 반환하므로 테스트 시:
```python
# 반드시 영문코드+한글레이블 둘 다 비교
APPOINTMENT_TARGET_MAP = {
  "safety_manager": "안전관리자",
  "electric_safety_manager": "전기안전관리자",
  ...
}
def has_appt(data, target_code):
    label = APPOINTMENT_TARGET_MAP.get(target_code, target_code)
    return any(r.get("appointment_target") in (target_code, label)
               for r in data.get("appointment_required", []))
```

---

## 🔐 인증
- **Supabase**: xntdkrjhgcscmqctdzyo
- **Railway API**: https://api.taieng.co.kr/ (v5.6.4)
- **Admin**: hetto@kakao.com (role 001)
- **GitHub**: taiengineering/tai-api (main branch)

## 📌 주의사항
1. API 사이즈: `size <= 100`
2. SHA 필수: create_or_update_file 시 현재 SHA 먼저 조회
3. 무결성 원칙: 변경 후 CI 통과 확인 필수
4. **공지예외주장 기한: 2026-04-28** (patent.go.kr)
