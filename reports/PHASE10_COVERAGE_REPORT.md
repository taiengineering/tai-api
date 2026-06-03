# Phase 10 — Quality Coverage Report

## 의무 출처 (실데이터로 확정)

라이브 DB 프로브 결과:
- `work_schedules` 60건 = MANUAL 58 / LEGAL 2, **rule_code 0건 / law 연결 없음** → 의무 원장 아님.
- `master_rules` / `obligation*` 테이블 없음, `legal_obligations` 0건.
- **최신 진단 `factory_diagnosis_results(is_latest).result_data.rules` = 1,000 룰** → 각 룰에 rule_code / law_name / law_article / obligation 보유. **이것이 의무 전체.**

→ 배치 기본 출처 = **diagnosis** (result_data.rules), obligation_id = rule_code.

## 1. 실행 명령
```bash
PYTHONPATH=. python scripts/run_quality_batch.py --dry-run   # 미리보기 (diagnosis)
PYTHONPATH=. python scripts/run_quality_batch.py --commit    # 적재
```

## 2. Quality Distribution — **VERIFIED (dry-run, 2026-06-03)**

실제 실행 출력 (추측 아님):
```json
{"source":"diagnosis","mode":"dry-run","source_rows":1,"obligation_count":1000,
 "conflicts":0,
 "coverage":{"total":1000,
   "distribution":{"READY":0,"TRACE_REQUIRED":1000,"CORRECTION_REQUIRED":0},
   "top_reasons":[{"reason":"EVIDENCE_INSUFFICIENT","count":1000}],
   "unclassified":0,"fully_classified":true}}
```

| 항목 | 값 |
|------|-----|
| source_rows (is_latest 진단) | 1 |
| obligation_count (distinct rule_code) | 1000 |
| READY | 0 |
| TRACE_REQUIRED | 1000 |
| CORRECTION_REQUIRED | 0 |
| conflicts | 0 |
| **fully_classified** | **true** ✅ |

해석: 1,000개 의무 모두 법령 연결 OK + 중복 없음. 단 Check 리포트가 없어 전부 TRACE_REQUIRED(근거 미관측). Check 연결 후 재실행하면 일부가 READY/CORRECTION으로 이동.

## 3. TOP 10 원인 — VERIFIED (dry-run)

| # | reason | count |
|---|--------|-------|
| 1 | EVIDENCE_INSUFFICIENT | 1000 |

## 4. Admin Queue 현황 (적재 후 기록)

CORRECTION_REQUIRED = 0 → 자동 등록 대상 없음. `--commit` 후 `GET /admin/obligations/queue?status=OPEN` → OPEN 건수 기대값 **0**. (실행 후 확인 기록: _PENDING_)

## 5. Schedule Gate 결과 (per-call 시연, 실행 후 기록)

> READY=0 이므로 게이트 활성화 시 모든 의무가 skipped_not_ready로 제외된다(스케줄 0건). 전역 활성화 금지, Check 연결로 READY 발생 후 검토. (per-call 시연 결과: _PENDING_)

## 결론

성공 기준 달성: 기존 의무 전체(1000)가 READY/TRACE_REQUIRED/CORRECTION_REQUIRED 중 하나를 가진다 → fully_classified=true. 현 품질 상태는 "전체 추적 필요(Check 미수행)"로 정직하게 산출됨.
