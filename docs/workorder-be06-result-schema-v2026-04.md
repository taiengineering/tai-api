# BE-06: result_data JSON 스키마 v2026.04 표준화

**작업일:** 2026-04-16  
**Migration:** `add_schema_version_to_results`  
**상태:** ✅ 미완료 (스키마 + DB + 산출물 완료, 엔진 연동 대기)

---

## 배경

`factory_diagnosis_results.result_data` 기로 스키마 다양 (전하 6가지 패턴):

| 패턴 | 키 예시 | 건수 |
|---|---|---|
| seed | stage, is_seed, summary, applicable_count | 다수 |
| 엔진 v1 | step, rules, obligations, law_badges | 다수 |
| 엔진 v2 | tier, risk_summary, applicable_laws, headline_message | 일부 |
| 건설전용 | construction_specific_tips | 1 |
| 경고 키 | warnings, urgent_action_items, edge_case_warning | 혼용 |
| 테스트 | trigger_test, 임시 데이터 | 일부 |

현재 **43건** 중 `schema_version` 키 **0건** → 전체 마킹 필요.

---

## 완료 작업

### DB Migration: `add_schema_version_to_results`
- `schema_version VARCHAR(10)` 컨럼 추가
- 기존 43건 전부 `'legacy'` 마킹 ✅
- `result_data` 내부에도 `schema_version: 'legacy'` 키 삽입 ✅
- 신규 INSERT 트리거: `result_data->>'schema_version'` 자동 동기화 ✅

### 스키마 파일
- `schemas/diagnosis_result_v2026_04.json` — JSON Schema Draft 2020-12 ✅
- `app/models/diagnosis_result.py` — Pydantic v2 모델 ✅
- `scripts/migrate_result_data_v2026_04.py` — 백필 스크립트 ✅

---

## DB 상태 (확인 쿼리 결과)

```sql
SELECT schema_version, COUNT(*) FROM factory_diagnosis_results GROUP BY schema_version;
-- legacy | 43
```

---

## 다음 단계 (미완료)

### legal_engine.py 연동
실제 엔진이 `DiagnosisResultV202604` 모델로 INSERT하도록
`routers/legal_engine.py` 개선이 필요함 — **기획창 승인 후 별도 스프린트**.

수정 대상:
```python
# routers/legal_engine.py save_diagnosis 함수 내에서
from app.models.diagnosis_result import DiagnosisResultV202604

result_dict = build_result_dict(...)  # 기존 로직
result_dict["schema_version"] = "2026.04"
try:
    validated = DiagnosisResultV202604.model_validate(result_dict)
    result_dict = validated.model_dump(mode="json")
except Exception as e:
    log.warning("[SCHEMA] v2026.04 검증 실패 (미저장): %s", e)
    raise

supabase.table("factory_diagnosis_results").insert({..., "result_data": result_dict}).execute()
```

### 백필 대상

`upgrade_to_v202604()` 함수로 legacy 43건을 v2026.04로 변환하는 SQL은
**기획창 장임표에서 확인 후** Supabase MCP로 실행 예정.
(데이터 수정이므로 무결성 체크 후 진행)

---

## 펴기 키 (신규 INSERT 시 사용 금지)

| 구 키 | 대체제 |
|---|---|
| `urgent_action_items` | `warnings` |
| `construction_specific_tips` | `warnings` |
| `edge_case_warning` | `warnings` |
| `age_warnings` | `warnings` |
| `key_obligations` | `obligations` |
| `headline_message` | `headline.summary` |
| `rule_count` / `applicable_count` | `rule_count_total` / `rule_count_shown` |

---

## 금기
- 스키마 임의 변경 금지 (기획창 승인 후만) ✅
- main 직접 커밋 금지 (dev 브랜치만) ✅
