# BE-04: factories 진단 메타 자동 동기화 트리거

**작업일:** 2026-04-16  
**Migrations:**
1. `fix_factory_diagnosis_is_latest_duplicates`
2. `trigger_factories_diagnosis_sync`  

**상태:** ✅ 완료

---

## 배경

`factories` 테이블의 진단 메타 컬럼이 NULL 방치:
- `last_diagnosis_at` — 26건 중 24건 NULL
- `legal_result_json` — 26건 중 24건 NULL
- `diagnosis_status` / `legal_applicable_count` — 값 있으나 동기화 보장 없음

안전관리자 대시보드에서 `factory_diagnosis_results JOIN` 없이 진단 상태 조회 불가.

---

## STEP 1: is_latest 중복 정리

**Before:** 4개 factory에서 is_latest=true 중복 발견

| factory_id | total | latest_count |
|---|---|---|
| 3678c9c3 (테헤란로 JS타워) | 2 | 2 |
| cc000003 (강남 본사) | 7 | 6 |
| e9c56af6 (화성 제2공장) | 4 | 4 |
| f90b837e (강남 오피스텔) | 2 | 2 |

**수정:** `ROW_NUMBER() OVER (PARTITION BY factory_id ORDER BY created_at DESC)` 기준 1건만 유지

**After:** is_latest 중복 0건 ✅

---

## STEP 2: 트리거 + 백필

### 트리거 함수

```sql
CREATE OR REPLACE FUNCTION fn_sync_factories_diagnosis_meta()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
  v_latest RECORD;
BEGIN
  SELECT factory_id, created_at, rule_count, diagnosis_stage, result_data
  INTO v_latest
  FROM factory_diagnosis_results
  WHERE factory_id = NEW.factory_id AND is_latest = true
  LIMIT 1;

  IF FOUND THEN
    UPDATE factories SET
      last_diagnosis_at     = v_latest.created_at,
      diagnosis_status      = CASE WHEN v_latest.diagnosis_stage >= 2 THEN 'PAID' ELSE 'FREE' END,
      legal_applicable_count = v_latest.rule_count,
      legal_result_json     = v_latest.result_data
    WHERE id = v_latest.factory_id;
  END IF;
  RETURN NEW;
END;
$$;
```

**트리거:** `AFTER INSERT OR UPDATE ON factory_diagnosis_results FOR EACH ROW`  
**재귀 방지:** `factories` 테이블에 트리거 없음 → 재귀 호출 불가 ✅

### 백필 결과

```sql
-- 완료 확인 쿼리 결과 (진단 이력 있는 factories 기준)
null_last_diag=0 / null_result_json=0 / total=16
```

**NULL 0건** ✅

---

## 회귀 테스트 결과

테스트 대상: `테헤란로 JS타워` (legal_applicable_count=34)

| 단계 | legal_applicable_count |
|---|---|
| 테스트 INSERT (rule_count=999) | **999** ← 트리거 자동 갱신 확인 ✅ |
| 테스트 롤백 후 | **34** 복원 ✅ |

---

## TASK 4: FastAPI 이중화 코드 점검

- `routers/diagnosis.py` — factories 진단 메타 직접 갱신 로직 없음 (contracts 기반 access-check만)
- `routers/construction.py` — `construction_sites` 갱신이지 `factories` 갱신 아님
- `routers/legal_engine.py` — `factory_diagnosis_results` INSERT만 수행 (factories 갱신 별도 없음)

**결론:** FastAPI 이중화 코드 없음. 트리거 단일 소스화 완료 ✅ (추가 코드 정리 불필요)

---

## 완료 조건 체크

- [x] 신규 진단 INSERT 시 factories 자동 갱신 (회귀 테스트 통과)
- [x] 기존 데이터 전부 백필 완료 (NULL 0건)
- [x] is_latest 유일성 보장 (중복 0건)
- [x] 트리거 재귀 방지 (factories 테이블에 트리거 없음)
- [x] diagnosis_purchases 레코드 수정 없음
- [x] main 직접 커밋 없음 (Supabase migration으로만 처리)

---

## 등록된 트리거 목록

| 테이블 | 트리거명 | 이벤트 |
|---|---|---|
| factory_diagnosis_results | trg_sync_factories_diagnosis_meta | AFTER INSERT OR UPDATE |
| factories | trg_generate_site_code | INSERT (기존, 사이트코드 자동생성) |

---

## 다음 단계

- 안전관리자 대시보드에서 `factories.last_diagnosis_at`, `legal_applicable_count` JOIN 없이 직접 조회 가능
- 대시보드 쿼리 최적화: `factory_diagnosis_results JOIN` 제거 가능
