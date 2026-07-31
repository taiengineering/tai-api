---
wo: WO-E2E-BASELINE-001
class: records
type: report
scope: canonical
project: test-universe
title: Baseline Outlier Analysis v1
version: 1
status: active
owner: taiwang
---

# REPORT — Baseline Outlier Analysis v1

> WO-E2E-BASELINE-001. 이상치 자동 계산. **표시만. 판정 금지.**
> 기준: |obligation − sector_avg| > 2 × sector_StdDev.

## 1. 섹터 기준값

| Sector | Avg | StdDev | Outlier Threshold(±2σ) |
|---|---|---|---|
| 제조 | 21.7 | 2.1 | 4.2 |
| 건축물 | 98.1 | 23.9 | 47.8 |
| 건설 | 23.3 | 1.2 | 2.4 |
| 특수시설 | 7 | 0.0 | 0.0 |

## 2. 이상치 목록 (표시만)

| Snapshot | Profile | Sector | obligation | 섹터평균 | ±2σ | 편차 |
|---|---|---|---|---|---|---|
| SNAP-0021-001 | PF-0021 | 건축물 | 28 | 98.1 | 47.8 | -70.1 |
| SNAP-0025-001 | PF-0025 | 건축물 | 28 | 98.1 | 47.8 | -70.1 |
| SNAP-0026-001 | PF-0026 | 건축물 | 28 | 98.1 | 47.8 | -70.1 |
| SNAP-0034-001 | PF-0034 | 건설 | 20 | 23.3 | 2.4 | -3.3 |
| SNAP-0098-001 | PF-0098 | 건설 | 20 | 23.3 | 2.4 | -3.3 |
| SNAP-0100-001 | PF-0100 | 건설 | 20 | 23.3 | 2.4 | -3.3 |

> 이상치는 '틀렸다'는 뜻이 아니다. 통계적 편차 표시일 뿐이며, 정당한지 여부는 판정하지 않는다.
> StdDev=0 섹터(특수시설)는 이상치 계산 대상에서 제외(전건 동일값).
