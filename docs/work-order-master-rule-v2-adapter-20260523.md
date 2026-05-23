# 작업지시서 완료 보고: master_rule_v2 → v1 Adapter (2026-05-23)

## 구현 파일

| 파일 | Step | 상태 |
|------|------|------|
| `services/rule_v2_adapter.py` | 3 | ✅ |
| `services/rule_candidate_projection.py` | Runtime pivot | ✅ |
| `services/legal_runtime_fetch.py` | Runtime pivot | ✅ |
| `services/legal_diagnosis_rules.py` | 5·6 | ✅ 공통 fetch |
| `services/legal_v510_svc.py` | 5 | ✅ |
| `services/legal_engine_svc.py` | 5 | ✅ step1/2/3 |
| `services/construction_svc.py` | 5 | ✅ |
| `routers/anonymous_diagnosis.py` | 6 | ✅ `rule_version` 동적 |
| `routers/health.py` | — | ✅ runtime 헬스 |
| `services/legal_article_loader.py` | v5.8.0 | ✅ law+조문 fallback |
| `tests/test_rule_v2_adapter.py` | 7 | ✅ |
| `tests/test_rule_candidate_projection.py` | 7 | ✅ |
| `tests/test_work_order_adapter_pipeline.py` | 최종 확인 | ✅ |

## 검증 스크립트

```bash
cd ~/Desktop/tai-engineering/tai-api
set -a && source .env && set +a

# Step 4 DB 스키마
python3 scripts/work_order_step4_db_schema.py

# Runtime projection 스모크
python3 scripts/verify_runtime_projection_db.py

# Step 7 rules_table 파이프라인
python3 scripts/verify_work_order_step7_rules_table.py

# 단위 테스트
python3 -m pytest tests/test_rule_v2_adapter.py tests/test_rule_candidate_projection.py tests/test_work_order_adapter_pipeline.py -q
```

## 환경변수 (Step 6)

| 변수 | Seoul 권장 | 설명 |
|------|------------|------|
| `TAI_USE_RUNTIME_ENGINE` | `true` | `runtime_metadata_resolution` → v1 dict |
| `TAI_USE_V2_ENGINE` | `false` | `master_rule_v2` (Seoul 0건) |

Railway `tai-api-prod`: `TAI_USE_RUNTIME_ENGINE=true` 설정됨.

## Seoul DB 현황 (Step 4 결과 요약)

- `runtime_metadata_resolution`: ~3,395
- `master_rule_v2`: 0
- `master_building_legal_rules`: 테이블 없음 (PGRST205)

→ 프로덕션 진단은 **Runtime 경로**가 실질 소스.

## 절대 금지 준수

- `engine/` 미수정 ✅
- 새 UI 미추가 ✅
- LLM/semantic inference 미사용 ✅

## 수동 확인만 남음

- 브라우저 `paid-diagnosis-result.html` (아코디언·필터·PDF) — 배포 후 1회
- v1 vs v2 rules_table 수치 비교 — Seoul에서 v1/v2 데이터 없어 생략
