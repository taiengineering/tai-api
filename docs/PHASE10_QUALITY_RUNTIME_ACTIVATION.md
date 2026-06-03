# Phase 10 — Quality Runtime Activation

> 검증된 Quality Evaluator(Phase 9)를 실제 운영 의무에 적용. **새 엔진 없음.** Evaluator 무수정 사용.

## 중요 사실 (조사 결과, 추측 아님)

tai-api에는 **운영 의무별 Check EvidenceReport가 아직 없다.** (`HANDOFF_EVIDENCE_ENGINE.md`의 Evidence Engine은 법령 원문 파싱 파이프라인이며 Check 리포트와 무관.)

그래서 이번 배치의 의미는:
- Check 리포트 없는 의무 = 근거 미관측 = **TRACE_REQUIRED** (정상 의미, 조작 아님). 빈 well-formed Check 리포트를 넓어 evaluator가 정직하게 TRACE로 매핑.
- 법령 연결 누락 / 법령 충돌 의무 = **CORRECTION_REQUIRED**.
- **READY = 0건** (아직 어떤 의무도 Check 검증되지 않음).

## ⚠ Schedule Gate 전역 활성화 경고 (작업 4)

READY가 0건인 현 상태에서 `enforce_quality`를 전역 기본 True로 켜면 **모든 스케줄 생성이 차단**된다(운영 중단). 따라서:
- 전역 default는 **False 유지** (변경 안 함).
- 게이트는 **per-call** `?enforce_quality=true` 로 시연/검증만.
- Check 리포트 연결 → READY 발생 후 전역 활성화 권장.
(전역 강제를 원하시면 명시 지시 — 현재는 스케줄 0건이 됩니다.)

## 산출물

1. **Batch 평가 러너** — `scripts/run_quality_batch.py` (`--dry-run` / `--commit`)
2. **인구 평가 로직** — `services/obligation_quality_batch.py` (`collect_obligations_from_diagnosis`, `evaluate_population`, `empty_check_report`)
3. **Coverage** — `services/obligation_quality_coverage.py` (`compute_coverage`) + `GET /admin/obligations/coverage`
4. **Admin Queue 적재** — `--commit` 시 CORRECTION_REQUIRED → `record_evaluation` → admin_obligation_queue 자동 등록 (Phase 9 store)
5. **테스트** — `tests/test_obligation_quality_coverage.py` (순수, DB 불필요)
6. **리포트 템플릿** — `reports/PHASE10_COVERAGE_REPORT.md` (실행 후 실제 숫자로 채움)

## 의무 모집 정의

"기존 의무 전체" = 최신 진단결과(`factory_diagnosis_results.is_latest`)의 `result_data.inspection_required[]` 룰을 obligation_id(rule_id/rule_code) 기준으로 distinct 수집. 이는 Schedule Gate가 조회하는 동일 출처라 게이트 커버리지가 일치한다. (별도 master 의무 테이블이 있으면 알려주십시오.)

## 실행 절차 (사람)

```bash
# 0) 순수 테스트 (DB 불필요)
python -m pytest tests/test_obligation_quality_coverage.py -q

# 1) 마이그레이션 적용: sql/20260603_obligation_quality_layer.sql → Supabase taieng

# 2) 미리보기 (DB 쓰기 없음)
PYTHONPATH=. python scripts/run_quality_batch.py --dry-run

# 3) 적재 (obligation_quality + CORRECTION 시 admin 큐)
PYTHONPATH=. python scripts/run_quality_batch.py --commit

# 4) Coverage 확인
curl -s https://api.taieng.co.kr/admin/obligations/coverage | jq

# 5) Gate 시연 (전역 활성화 아님, per-call)
curl -s -X POST "https://api.taieng.co.kr/legal-engine/generate-schedules/<FACTORY_ID>?enforce_quality=true" | jq
```

## 성공 기준

기존 의무 전체가 READY / TRACE_REQUIRED / CORRECTION_REQUIRED 중 하나를 가진다 → `compute_coverage.fully_classified == true` 로 확인. (실행 후 리포트에 실제 숫자 기록.)

## 검증 상태: UNVERIFIED (이번 세션 실행 불가)

순수 테스트는 작성 완료(사용자 실행 필요). 배치/Coverage/Gate의 실데이터 숫자는 사람이 위 명령 실행 후 확정. 추측 숫자 기재 금지.

## 금지사항 준수

Check/LEG 수정 / 새 엔진 / 법령 재판단: 없음. Evaluator 무수정. Check 결과 소비만.
