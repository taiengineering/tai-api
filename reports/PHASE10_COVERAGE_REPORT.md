# Phase 10 — Quality Coverage Report

> 상태: **PENDING** — 아래 숫자는 `scripts/run_quality_batch.py` 실제 실행 후 채운다. 추측 금지.

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

## 2. Quality Distribution (실행 후 기록)

| 항목 | 값 |
|------|-----|
| source_rows (is_latest 진단) | _PENDING_ |
| obligation_count (distinct rule_code) | _PENDING_ |
| READY | _PENDING_ |
| TRACE_REQUIRED | _PENDING_ |
| CORRECTION_REQUIRED | _PENDING_ |
| fully_classified | _PENDING_ |

## 3. TOP 10 원인 (quality_reason, 실행 후 기록)

| # | reason | count |
|---|--------|-------|
| 1 | _PENDING_ | |

## 4. Admin Queue 현황 (실행 후 기록)

`GET /admin/obligations/queue?status=OPEN` → OPEN 건수: _PENDING_

## 5. Schedule Gate 결과 (per-call 시연, 실행 후 기록)

> 참고: 현 generate-schedules 엔드포인트는 result_data.inspection_required를 읽는데 실제 진단은 result_data.rules를 쓴다(키 불일치, Phase 10 범위 밖 관찰). 게이트 자체 동작은 obligation_quality 기반이므로 rule_code 공간은 일치.

| field | value |
|-------|-------|
| created | _PENDING_ |
| skipped_not_ready | _PENDING_ |
| skipped_unevaluated | _PENDING_ |

## 예상 (현 시점, Check 리포트 부재)

READY 0 / 대부분 TRACE_REQUIRED(EVIDENCE_INSUFFICIENT) / law_name·law_article 누락 룰은 CORRECTION(LAW_LINK_ERROR). 실제 수치와 일치 여부 확인.
