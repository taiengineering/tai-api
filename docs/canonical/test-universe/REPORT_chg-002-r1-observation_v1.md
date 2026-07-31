---
wo: WO-CHG-002-R1
class: records
type: report
scope: canonical
project: test-universe
title: CHG-002 Re-observation (before_clean) — False Positive
version: 1
status: active
owner: taiwang
---

# REPORT — WO-CHG-002-R1 CHG-002 실재 여부 관측

> 코드·데이터 수정 없음. 관측만. Baseline=before_clean(Frozen), Engine=main(PR#122 포함), Measurement=Sequential/180s.

## 판정: Case A — CHG-002 False Positive

```text
관측 (before_clean, 노이즈 제거)
    ↓
특수시설 산업안전 미커버 = 0/10 (전건 커버)
    ↓
'산업안전 10/10 전건 미커버' 전제 반증
    ↓
CHG-002 = False Positive → 종료, 새 CHG 생성 안 함
```

## 관측 데이터 (before_clean 특수시설 10개)

| 항목 | 값 |
|---|---|
| 특수시설(other) profile | 10개 (PF-0037·0038·0039·0106·0107·0108·0109·0110·0111·0112) |
| 산업안전 미커버 | **0/10** (전건 커버) |
| 커버 산업안전 법령 | 안전보건교육규정 |
| 함께 커버 | 작업환경측정 및 정도관리 고시, 방사선 안전관리 규칙, 장애인복지법 시행규칙, 에너지절약형 친환경주택 건설기준 |

각 특수시설 총의무 6~7건, 그중 산업안전(안전보건교육규정) 2건 포함.

## 근거

- 이전 CHG-002 전제 = "특수시설 산업안전 10/10 전건 미커버(작업환경만 커버)".
- before_clean(노이즈 제거)에서는 정반대 — **10/10 전건 산업안전 커버**.
- 오염 실행(페이지네이션 비결정성, WO-MEASURE-002 확정)이 만든 허상이었음.

## 부수 관측 (별개 사실, 이번 WO 판단 대상 아님)

일부 특수시설 profile에서 안전보건교육규정 의무가 중복 2건으로 표기됨("교육방법 및 교육생의 관리 등"). 실제 중복인지 표시상 중복인지는 CHG-002와 무관한 별도 관측 사항으로 미판단.

## 종합 — CHG Set 결과

| CHG | 원래 전제 | before_clean 관측 | 판정 |
|---|---|---|---|
| CHG-001 | 대형 건축물 전기·승강기 미포함(규모 역전) | 건축물 전 규모 전기·승강기 0(역전 없음) | False Positive |
| CHG-002 | 특수시설 산업안전 10/10 미커버 | 특수시설 산업안전 0/10 미커버(전건 커버) | False Positive |

두 CHG 모두 측정 노이즈의 산물. Engine Change Set(CHG-001·CHG-002)은 노이즈 제거 후 실재하지 않음. 측정 신뢰성 확보(WO-MEASURE-002)가 없었다면 두 허위 CHG를 실제 결함으로 오인해 엔진/데이터를 잘못 수정했을 것이다.
