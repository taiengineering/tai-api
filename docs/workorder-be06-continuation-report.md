# BE-06-continuation: v2026.04 완전 전환 완료 보고

**작업일:** 2026-04-16  
**Migration:** `backfill_result_data_to_v202604`  
**백업:** `diagnosis_results_backup_20260416` (Supabase 내 테이블)  
**롤백 스크립트:** `supabase/backups/rollback_v202604_backfill.sql`  
**상태:** ✅ 완료

---

## STEP 볔 진행 기록

| STEP | 내용 | 결과 |
|---|---|---|
| 3-1 | Supabase 백업 테이블 생성 | ✅ 43건 |
| 3-2 | GitHub 롤백 스크립트 저장 | ✅ |
| 3-3 | 43건 변환 (migration) | ✅ |
| 3-4 | is_latest 중복 수정 | ✅ 0건 |
| 3-5 | 검증 쾼리 | ✅ 전체 통과 |
| 3-6 | 기획창 최종 보고 | ✅ |

---

## STEP 3-5 검증 쾼리 결과

| 검증 항목 | 기대값 | 실제값 |
|---|---|---|
| `schema_version='2026.04'` | 43건 | **43건** ✅ |
| `legacy` 잔존 | 0건 | **0건** ✅ |
| `result_data ? 'headline'` | 43건 | **43건** ✅ |
| `evidence` 키 존재 | 43건 | **43건** ✅ |
| `evidence` 비어 있지 않음 | >0건 | **43건** ✅ |
| `MANUFACTURING` 잔존 | 0건 | **0건** ✅ |
| `is_latest` 중복 | 0건 | **0건** ✅ |
| 시나리오 데이터 (SEED_* 8건) | 보존 | **8건 보존** ✅ |

---

## 적용된 변환 규칙 (12개 + Q3)

| # | 규칙 | 비고 |
|---|---|---|
| 1 | tier 정규화: PAID_FULL→PAID, PAID1_FACILITY→PAID1, PAID2_PROCESS→PAID2, PAID3_EQUIPMENT→PAID3 | ✅ |
| 2 | sector 교정: MANUFACTURING→INDUSTRY (column + result_data 양쪽) | ✅ |
| 3 | warnings 통합: 4개 키 병합 (array/object 타입 방어) | ✅ |
| 4 | obligations 통합: obligations > key_obligations > mandatory > critical 우선순위 | ✅ |
| 5 | rule_count 분리: rule_count_total / rule_count_shown | ✅ |
| 6 | risk_summary 표준화: 없으면 `{critical:0, high:0, medium:0, low:0}` | ✅ |
| 7 | schema_version='2026.04' 고정 | ✅ |
| 8 | _legacy_process_hazards 보존 (한글 키 이름 변경) | ✅ |
| 9 | seed 10건 obligations: [] 유지 | ✅ |
| 10 | roi 필드 현행 유지 (4개 필수 키 충족) | ✅ |
| 11 | evidence[]: 알파벳 오름차순, source·factory_id 제외, 상위 5개 | ✅ |
| Q3 | headline.severity: risk_summary 기반 → rule_count 추정 (없으면 ≥100=HIGH, ≥50=MEDIUM, else LOW) | ✅ |

---

## 특이사항

- `age_warnings`이 JSON object 타입 (1건): key-value 연결 문자열로 변환하여 warnings[]에 통합
- SCENARIO_TEST_% 레코드 factory_diagnosis_results에 미존재 (SEED_* source 8건 보존 확인)
- evidence 샘플: `["input.electric_capacity=500", "input.total_floor_area=3000", "input.worker_count=85"]` (알파벳 순 확인)

---

## headline.severity 분포

| severity | 건수 |
|---|---|
| CRITICAL | 8건 |
| HIGH | 19건 |
| MEDIUM | 12건 |
| LOW | 4건 |

---

## 백업 정보

- **Supabase 내 백업 테이블:** `diagnosis_results_backup_20260416` (43건)
- **롤백 스크립트:** `supabase/backups/rollback_v202604_backfill.sql`
- **백업 파일:** `supabase/backups/factory_diagnosis_results_before_v202604.sql`

---

## 신규 INSERT 자동 v2026.04 화 (PENDING)

`routers/legal_engine.py` 개선 작업은 이후 별도 스프린트에서 진행:
- INSERT 시 `DiagnosisResultV202604` Pydantic 모델 검증 연동
- 실패시 500 에러 명시 반환 (silently fallback 금지)
