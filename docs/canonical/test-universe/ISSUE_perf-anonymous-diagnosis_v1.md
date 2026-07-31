---
wo: WO-PERF-001
class: plans
type: issue
scope: canonical
project: test-universe
title: Anonymous Diagnosis Performance (backlog)
version: 1
status: backlog
owner: taiwang
---

# ISSUE — Anonymous Diagnosis Performance (WO-PERF-001, backlog)

> WO-MEASURE-001에서 분리된 별도 트랙. **이 WO는 아직 실행하지 않는다.** 측정 신뢰성과 무관(긴 타임아웃에서 결과 정확성은 유지됨).

## 확정 사실 (실측)
```text
Engine Determinism   : PASS  (PF-0019 → applicable_count=107, 3회 연속 동일)
Measurement Method   : Sequential(RUN_WORKERS=1) / Timeout 180s → 결정적
Write Bottleneck     : DISPROVED
  - INSERT 738행 = 883ms · SELECT = 8ms · DELETE 738행 = 9.5ms (합 1초 미만)
  - facility_applicability 인덱스 정상(idx_fa_factory 등), Index Scan 13.9ms
  - VACUUM ANALYZE로 통계 교정(n_live_tup 161→394만, dead 137,072→23) — 그러나 진단시간 28초 유지
Performance Issue    : CONFIRMED, SEPARATE TRACK
Observed Diagnosis Time : 약 28초/건
```

## 성능 가설 (미확정 — WO-PERF-001에서 구간 계측으로 확정할 것)
아직 프로파일링 전이므로 "27초의 원인이 확정됐다"고 기록하지 않는다. 유력 후보:
```text
- executable_draft 전량 로딩 (약 1만행 페이지네이션)
- law_article / law_sector_mapping 조인 처리
- draft_slot 전량 로딩 (약 5만행 페이지네이션)
- Python draft evaluation loop (738 draft × factory)
```
이들은 `evaluate_single_factory`가 **매 진단마다** 6만여 행을 로딩·평가하는 구조에서 비롯된다는 가설이다. 구간별 타이밍으로 확정 후 최소 수정(캐싱/사전적재 등, Query→Code 순) 검토.

## 실행 조건
CHG 진행을 막지 않는다. WO-MEASURE-001 종료 및 CHG-001 재개 이후 별도로 착수한다.
