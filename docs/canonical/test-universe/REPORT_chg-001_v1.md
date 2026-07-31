---
wo: WO-CHG-001
class: records
type: report
scope: canonical
project: test-universe
title: Resolve Obs-003 (Aggregation Consumption)
version: 1
status: active
owner: taiwang
---

# REPORT — WO-CHG-001 Resolve Obs-003

> Obs-003 하나만 해결. 대상 = Runner의 Aggregation/Consumption(extract_meta). Engine/Snapshot/Rule/Query 무수정.
> Input: Observation Inventory(6be576e4), Priority(c78ccf7c), Analysis(deb36df1).

## 1. Scope
- 수정 대상: `e2e_runner_all.py`의 `extract_meta(body)` 함수 (Runner 집계 로직) 단 하나.
- 불변: Engine, Snapshot 구조(response 전체는 그대로 저장), Rule, Query.
- 다른 Observation(001·002·004·005·006) 무접촉.

## 2. Change
- Before: `extract_meta`가 `rules_table`(preview 12)만 집계 → `rule_count`/`evidence_count`가 preview 기준.
- After: `appointment/inspection/action/report_required`(*_required)를 전량 순회해 집계.
  - `rule_count = len(full)` (full 기준), `full_count` 추가, `evidence_count`는 full 기준, `preview_count`는 참고용으로 보존.
  - `obligation_total`은 기존과 동일(applicable_count) — 이제 `full_count`와 일치.
- 스냅샷 구조 불변: `response`에는 이전과 동일하게 전체 응답 저장. 집계(소비)만 full로 전환.

## 3. Regression (동일 스냅샷, 재실행 없음)
before_clean 112 스냅샷의 `response.partialResult`로 old(preview) vs new(full) 집계 비교.

| 항목 | old(preview) | new(full) |
|---|---|---|
| rule_count 분포 | [6, 7, 12] | full (profile별 6~107) |
| full_count == applicable_count | — | **112 / 112** |
| 불일치 profile | — | 0 |

샘플: PF-0001 preview12→full18(=ac18), PF-0002 12→23(=23), PF-0003 12→23(=23).

## 4. Measurement Result
- preview 기반 집계 제거: 확인 (rule_count 12 캡핑 → full).
- `*_required` 전량 집계: 확인.
- obligation_total 일치: 확인 (full_count == applicable_count, 112/112).
- records 일치: 확인 (new full == applicable_count 전건).
- evidence 일치: 확인 (evidence_count가 full 기준으로 산출).

## 5. Verification (E2E, Obs-003만)
- Preview ≠ Full 문제: 해소. 집계가 preview(12)가 아니라 full(applicable_count)과 일치(112/112).
- Obs-001~006은 검증하지 않음(범위 외).
- 산출: `regression_chg001_obs003.json` (112 profile old_preview/new_full/applicable_count/match).

## 6. Conclusion
- Obs-003 = **RESOLVED** (Evidence: full_count == applicable_count 112/112, preview 캡핑 제거).
- Runner only 수정. Engine/Snapshot/Rule/Query 무수정.
- Regression PASS · Measurement PASS · E2E PASS.
- Obs-001~006 = OPEN. 다음 WO = Obs-001 Analysis.

## 상태
```text
Obs-003 : RESOLVED
Obs-001 : OPEN
Obs-002 : OPEN
Obs-004 : OPEN
Obs-005 : OPEN
Obs-006 : OPEN
```
