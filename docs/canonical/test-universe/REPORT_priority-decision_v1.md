---
wo: WO-PRIORITY-001
class: records
type: report
scope: canonical
project: test-universe
title: Observation Priority Decision
version: 1
status: active
owner: taiwang
---

# REPORT — WO-PRIORITY-001 Observation Priority Decision

> Review의 연장. 처리 순서(Priority)와 선행관계(Dependency)만 결정한다. 원인·분류·가설·CHG·수정안 없음. Observation Inventory(commit 6be576e4)는 불변.

## 1. Observation 목록 (입력 — 불변)
Source: Observation Inventory, commit `6be576e4`.

| ID | 관측 | 범위 | 영향 |
|---|---|---|---|
| Obs-001 | 동일 입력, 다른 출력 | building/construction/special | Critical |
| Obs-002 | 동일 (law,obligation) 다중 등장 | 112/112 | High |
| Obs-003 | Measurement Input Incomplete | 전체 | Critical |
| Obs-004 | 타 도메인으로 보이는 법령 존재 | 전 sector | Critical |
| Obs-005 | 선임류 의무가 report에 위치 | 광범위 | High |
| Obs-006 | 법/시행령/시행규칙 분리 등장 | 광범위 | Medium |

## 2. Dependency Table
> "먼저 처리되어야 하는 Observation"만 기록. 이유는 분석하지 않음.

| Observation | Depends On |
|---|---|
| Obs-003 | — |
| Obs-001 | Obs-003 |
| Obs-002 | Obs-003 |
| Obs-004 | Obs-003, Obs-001 |
| Obs-005 | Obs-003, Obs-001 |
| Obs-006 | Obs-003, Obs-001 |

Dependency 그래프:
```text
Obs-003
   ↓
Obs-001 ──────────────┐
   ↓                  │
Obs-004  Obs-005  Obs-006   (003·001 이후, 상호 독립)
Obs-002  (003 이후, 001과 독립)
```

## 3. Priority Table

| Observation | Priority | Depends On |
|---|---|---|
| Obs-003 | P1 | — |
| Obs-001 | P2 | Obs-003 |
| Obs-002 | P3 | Obs-003 |
| Obs-004 | P4 | Obs-003, Obs-001 |
| Obs-005 | P5 | Obs-003, Obs-001 |
| Obs-006 | P6 | Obs-003, Obs-001 |

## 4. Decision Summary
- 처리 순서: P1 Obs-003 → P2 Obs-001 → P3 Obs-002 → P4 Obs-004 → P5 Obs-005 → P6 Obs-006.
- 선행: Obs-003이 전체 선행(측정 입력이 전량이어야 나머지를 전량 기준으로 다룰 수 있음). Obs-001이 Obs-004·005·006의 선행(출력이 안정되어야 그 존재·범위를 확정 가능). Obs-002는 Obs-003 이후, Obs-001과 독립.
- 본 WO는 순서만 확정한다. 각 Observation의 분류·원인·가설·CHG는 후속 Analysis WO의 책임이다.

## 5. 상태 확인
- Observation Inventory 변경 없음(6be576e4 불변).
- CHG 0건. Analysis 미시작. 수정안 없음.
