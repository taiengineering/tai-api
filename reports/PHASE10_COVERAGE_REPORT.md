# Phase 10 — Quality Coverage Report

## 의무 출처 (실데이터로 확정)

라이브 DB 프로브 결과:
- `work_schedules` 60건 = MANUAL 58 / LEGAL 2, **rule_code 0건 / law 연결 없음** → 의무 원장 아님.
- `master_rules` / `obligation*` 테이블 없음, `legal_obligations` 0건.
- **최신 진단 `factory_diagnosis_results(is_latest).result_data.rules` = 1,000 룰** → rule_code / law_name / law_article / obligation 보유. **이것이 의무 전체.**

→ 배치 출처 = diagnosis (result_data.rules), obligation_id = rule_code.

## 1. 실행 명령
```bash
PYTHONPATH=. python scripts/run_quality_batch.py --dry-run                       # 미리보기(anon 가능)
railway run sh -c 'PYTHONPATH=. python scripts/run_quality_batch.py --commit'    # 적재(service_role)
railway run sh -c 'PYTHONPATH=. python scripts/quality_coverage_report.py'       # 테이블에서 Coverage 읽기
```

## 2. Quality Distribution — **VERIFIED (commit, 2026-06-03)**

`railway run ... --commit` 실제 출력 (추측 아님):
```json
{"source":"diagnosis","mode":"commit","source_rows":1,"obligation_count":1000,
 "conflicts":0,
 "coverage":{"total":1000,
   "distribution":{"READY":0,"TRACE_REQUIRED":1000,"CORRECTION_REQUIRED":0},
   "top_reasons":[{"reason":"EVIDENCE_INSUFFICIENT","count":1000}],
   "unclassified":0,"fully_classified":true},
 "persisted":1000}
```

| 항목 | 값 |
|------|-----|
| obligation_count (distinct rule_code) | 1000 |
| READY | 0 |
| TRACE_REQUIRED | 1000 |
| CORRECTION_REQUIRED | 0 |
| conflicts | 0 |
| **persisted (obligation_quality upsert)** | **1000** ✅ |
| **fully_classified** | **true** ✅ |

## 3. TOP 10 원인 — VERIFIED

| # | reason | count |
|---|--------|-------|
| 1 | EVIDENCE_INSUFFICIENT | 1000 |

## 4. Admin Queue 현황

CORRECTION_REQUIRED = 0 → 자동 등록 없음. 예상 OPEN 건수 **0**. (테이블 확인: `scripts/quality_coverage_report.py` → _PENDING_)

## 5. Schedule Gate — 배포 후

`enforce_quality` 파라미터는 피처 브랜치에만 있어 현 운영(main)에 미배포. READY=0이므로 활성화 시 전량 skipped_not_ready(스케줄 0). 로직은 순수 테스트로 검증됨(`is_schedulable`). 전역 활성화는 Check 연결 후.

## 참고 — Coverage HTTP 엔드포인트 404

`GET /admin/obligations/coverage` 가 prod에서 404인 것은 라우터(routers/admin_obligation_queue.py)가 아직 main에 미머지·미배포라서. PR #89/#90 머지 + 배포 후 동작. 그 전엔 위 스크립트로 테이블에서 직접 확인.

## 결론

성공 기준 달성: 기존 의무 전체(1000)가 3상태 중 하나를 가진다 (fully_classified=true), 실 DB 적재 완료(persisted=1000). 현 품질은 "전체 추적 필요(Check 미수행)" — 정직한 산출. 다음 근본 과제 = 의무별 Check 리포트(LEG→Check) 연결 → READY 발생.
