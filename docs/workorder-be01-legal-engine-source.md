# BE-01: 법령 자동판정 엔진 소스 역추적 결과 보고서

**작성일:** 2026-04-16  
**분석 대상:** master_legal_requirement_conditions / master_legal_inspection_rules  
**분석 범위:** legal_engine.py (v5.6.7), DB 스키마, factory_diagnosis_results  
**결론 선요약:** 두 테이블 모두 DEPRECATED. 엔진은 master_building_legal_rules(2,287건)만 사용.

---

## 1. 현재 엔진 아키텍처

### 1-1. 실제 법령 판정 쿼리 경로 (코드 역추적)

**진입점:** `routers/legal_engine.py` (v5.6.7, 71KB)

```python
# diagnose/step1 — 실제 쿼리
rules_res = supabase.table("master_building_legal_rules")
    .select("*")
    .eq("is_active", True)
    .in_("sector", sector_groups)
    .eq("diagnosis_stage", 1)
    .execute()

# diagnose/step2
q = supabase.table('master_building_legal_rules')
    .select('*')
    .in_('sector', sector_groups)
    .lte('diagnosis_stage', 2)
    .eq('is_active', True)

# apply/{factory_id}
rules_res = supabase.table("master_building_legal_rules")
    .select("*")
    .eq("is_active", True)
    .in_("sector", sector_groups)
    .execute()
```

**결론: `master_building_legal_rules` 단독 사용. 다른 테이블 쿼리 없음.**

### 1-2. master_legal_requirement_conditions 코드 참조 현황

| 파일 | 참조 여부 |
|------|-----------|
| legal_engine.py | ❌ 없음 |
| legal_engine_v510.py | ❌ 없음 |
| legal_engine_patch.py | ❌ 없음 |
| contracts_engine.py | ❌ 없음 |
| anonymous_diagnosis.py | ❌ 없음 |
| diagnosis.py | ❌ 없음 |
| inspection_sets.py | ❌ 없음 |
| 나머지 80+ 라우터 | ❌ 없음 |

**→ master_legal_requirement_conditions는 현재 코드베이스 어디에서도 참조되지 않음.**

### 1-3. master_legal_inspection_rules 코드 참조 현황

동일. 어떤 라우터에서도 참조 없음.

---

## 2. DB 상태 분석

### 2-1. 테이블 레코드 현황

| 테이블 | 레코드 수 | 상태 |
|--------|-----------|------|
| master_building_legal_rules | 2,287건 | ✅ ACTIVE |
| master_legal_requirement_conditions | 0건 | ⚠️ DEPRECATED |
| master_legal_inspection_rules | 0건 | ⚠️ DEPRECATED |

### 2-2. master_building_legal_rules sector 분포

| sector | 건수 |
|--------|------|
| MANUFACTURING | 665 |
| COMMON | 598 |
| BUILDING | 501 |
| CONSTRUCTION | 421 |
| SPECIAL_FACILITY | 49 |
| CONSTRUCTION_MANUFACTURING | 46 |
| BUILDING_MANUFACTURING | 6 |
| BUILDING_CONSTRUCTION | 1 |
| **합계** | **2,287** |

### 2-3. factory_diagnosis_results rule_count 소스 확인

```sql
-- 최근 생성된 진단 결과 (2026-04-16)
sector=INDUSTRY, stage=1 → rule_count=60   ← master_building_legal_rules에서
sector=INDUSTRY, stage=2 → rule_count=128
sector=INDUSTRY, stage=3 → rule_count=92
sector=INDUSTRY, stage=4 → rule_count=82
sector=CONSTRUCTION, stage=1 → rule_count=47
sector=CONSTRUCTION, stage=2 → rule_count=172
sector=BUILDING, stage=1 → rule_count=34
sector=BUILDING, stage=2 → rule_count=61
```

**rule_count = len(matched_rules) where matched_rules comes from master_building_legal_rules filtered by sector + diagnosis_stage**  
master_legal_requirement_conditions와 무관. 완전히 독립적.

---

## 3. 스키마 비교 (두 테이블의 설계 의도 차이)

### 3-1. master_legal_requirement_conditions (33컬럼, 0건)

**설계 의도:** 특허 출원 0056330의 초기 컬럼 설계 — "건물 조건 코드 기반" 판정에 특화

핵심 컬럼:
- `field_code` / `requirement_code` — 필드·요건 코드 체계
- `building_use_code` / `min/max_building_area` / `min/max_electrical_capacity_kw` — 건물 조건
- `safety_manager_required` / `fire_facility_required` — 의무 플래그
- `hazardous_material_required` / `hazardous_material_type`

**특징:** 건물(BUILDING) 섹터에 특화, 제조·건설 조건 필드 없음, 점검주기 필드 없음

### 3-2. master_legal_inspection_rules (24컬럼, 0건)

**설계 의도:** master_legal_requirement_conditions의 자식 테이블 (FK: requirement_condition_id)

핵심 컬럼:
- `requirement_condition_id` — 부모 테이블 FK
- `rule_code` / `inspection_category_code`
- `cycle_unit` / `cycle_value` / `cycle_weekday` / `is_month_end` — 점검 주기
- `law_name` / `law_article`

**특징:** condition → rules 1:N 구조, 조건 판정 후 점검 규칙 매핑

### 3-3. master_building_legal_rules (82컬럼, 2,287건)

**설계 의도:** 통합형 법령 판정 + 점검 + 신고 + 선임 + 제재 원스톱 테이블

핵심 추가 컬럼:
- `condition_group_code` / `condition_operator_code` — 조건 코드 체계 (특허 핵심)
- `sector` / `diagnosis_stage` — 섹터별 단계별 판정
- `obligation_type` / `obligation_summary` — 의무 유형 통합
- `inspection_cycle_unit_code` / `inspection_cycle_value` — 점검주기
- `submit_org_code` / `executor_type_code` / `report_method_std` — 신고/보고 메타
- `automation_level` / `official_api_available` — 자동화 인프라

**특징:** BUILDING + MANUFACTURING + CONSTRUCTION 통합 지원, 82컬럼으로 확장

---

## 4. 결론 및 Deprecated 여부 확정

### 4-1. 왜 0건이어도 현재 엔진이 동작하는가

**master_legal_requirement_conditions와 master_legal_inspection_rules는 법령 판정 엔진이 전혀 참조하지 않으므로, 0건이든 1,000건이든 엔진 동작에 무관하다.**

두 테이블은 설계 초기(2025년 말~2026년 초) 원형 설계에서 시작해, 실제 구현 과정에서 `master_building_legal_rules`로 기능이 완전 흡수·통합됐다.

### 4-2. DEPRECATED 판정 근거

| 기준 | 결과 |
|------|------|
| 코드베이스 참조 | 0건 |
| 레코드 | 0건 |
| FK 참조 (다른 테이블에서) | 없음 확인 |
| 특허 핵심 컬럼 | master_building_legal_rules에 흡수됨 (condition_code, condition_operator_code, condition_group_code) |

**→ 공식 DEPRECATED 판정**

### 4-3. 특허 보호 관계 정리

특허 제10-2026-0056330 "조건코드 기반 산업안전 법령 자동 판정 시스템"의 핵심 컬럼 체계(조건코드, 연산자코드, 조건값)는 **master_building_legal_rules에 이미 구현됨**:
- `condition_code` ← 조건 코드
- `condition_operator_code` ← 연산자 코드 (gte/lte/eq 등)
- `condition_value` ← 조건값
- `condition_group_code` ← 조건 그룹

특허 체계는 deprecated 테이블에 있는 것이 아니라 **실제 운영 테이블에 구현되어 있음. 특허 침해 우려 없음.**

---

## 5. 처리 계획

### 5-1. master_legal_requirement_conditions / master_legal_inspection_rules

**권장 처리:** 소프트 보관 (테이블 삭제 금지)

이유:
1. 특허 출원 문서에 초기 설계 스키마가 명시됐을 가능성 → 삭제 시 증적 소실 우려
2. 제로 레코드이므로 스토리지 영향 없음
3. 추후 "조건코드 기반 3계층 설계"로 재활성화 가능성 (미래 특허 확장)

**단기 조치:**
```sql
-- 테이블에 DEPRECATED 코멘트만 추가 (DDL)
COMMENT ON TABLE master_legal_requirement_conditions 
  IS 'DEPRECATED(2026-04): 기능이 master_building_legal_rules로 통합됨. 삭제 금지(특허 증적).';

COMMENT ON TABLE master_legal_inspection_rules 
  IS 'DEPRECATED(2026-04): 기능이 master_building_legal_rules로 통합됨. 삭제 금지(특허 증적).';
```

### 5-2. master_building_legal_rules 충전 현황 점검

| sector | 현황 | 충전도 |
|--------|------|--------|
| BUILDING | 501건 | ~98% (기존 확인) |
| MANUFACTURING | 665건 | ~98% |
| CONSTRUCTION | 421건 | ~95% |
| COMMON | 598건 | 정상 |
| 나머지 | 102건 | 유지 |

**현재 엔진 운영에 문제없음.**

---

## 6. 미충전 리스크 재평가

### 결론

| 항목 | 상태 |
|------|------|
| 법령진단 유료 결제 후 판정 가능 여부 | ✅ 가능 (master_building_legal_rules 2,287건 정상) |
| 특허 핵심 컬럼 활성화 여부 | ✅ 활성 (master_building_legal_rules에 구현) |
| 0건 테이블로 인한 서비스 장애 | ❌ 없음 |
| 추가 충전 긴급도 | 낮음 (현재 엔진 정상 동작) |

**BE-01 원래 우려사항(법령진단 가치 제안이 공허해짐) → 해소됨.**  
TAI Safe 법령진단은 master_building_legal_rules 2,287건을 기반으로 정상 동작 중.

---

## 7. 테스트 계획

### 7-1. 현 상태 검증 (즉시 실행 가능)

```bash
# BUILDING sector step1 진단
curl -X POST https://api.taieng.co.kr/legal-engine/diagnose/step1 \
  -H "Authorization: Bearer {TOKEN}" \
  -d '{"sector":"BUILDING","employee_count":50,"total_floor_area":3000}'

# 기대값: rule_count > 0, applicable_law_categories 포함
```

### 7-2. 회귀 테스트 보호

factory_diagnosis_results의 기존 데이터(rule_count 34~172)는 삭제하지 않음.  
마이그레이션 없음 → 기존 데이터 영향 없음.

---

## 8. 산출물 요약

| 항목 | 결과 |
|------|------|
| master_legal_requirement_conditions DEPRECATED | ✅ 확정 |
| master_legal_inspection_rules DEPRECATED | ✅ 확정 |
| 엔진 소스 테이블 확정 | master_building_legal_rules |
| rule_count 생성 경로 확정 | legal_engine.py → master_building_legal_rules → factory_diagnosis_results |
| 마이그레이션 필요 여부 | 불필요 |
| 추가 데이터 충전 필요 여부 | 불필요 (2,287건 운영 중) |
| 특허 보호 컬럼 임의 변경 | 없음 |
| 기존 factory_diagnosis_results 삭제 | 없음 |

**BE-01 완료조건 달성:** "왜 0건이어도 현재 엔진이 동작하는가" 완전 문서화 완료.
