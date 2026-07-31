---
wo: WO-CHG-001-R1
class: records
type: report
scope: canonical
project: test-universe
title: CHG-001 Re-observation (before_clean) — False Positive
version: 1
status: active
owner: taiwang
---

# REPORT — WO-CHG-001-R1 CHG-001 실재 여부 관측

> 코드·데이터 수정 없음. 관측만. Baseline=before_clean(Frozen), Engine=main(PR#122 포함), Measurement=Sequential/180s.

## 판정: Case A — CHG-001 False Positive

```text
관측 (before_clean, 노이즈 제거)
    ↓
건축물 전기·승강기 의무 = 전 profile 0 (large/medium/small 무차별)
    ↓
규모 역전 없음
    ↓
CHG-001 = False Positive → 종료, 새 CHG 생성 안 함
```

## 관측 데이터 (before_clean 건축물 29개)

| scale | profile 수 | 전기·승강기 의무 |
|---|---|---|
| large | 12 | 전부 0 |
| medium | 15 | 전부 0 |
| small | 2 | 전부 0 |

대상 profile 상세: PF-0020(medium)·PF-0022/0023/0024(large) 모두 총의무 12 / 전기·승강기 0.

## 근거

- 이전 CHG-001 전제 = "대형 건축물은 전기·승강기 대표의무 미포함, 소형/중형은 포함(규모 역전)".
- 그 전제는 **오염된 측정**(페이지네이션 비결정성, WO-MEASURE-002에서 확정) 위에서 관측된 것.
- 오염된 실행에서 보였던 "medium PF-0021 전기·승강기 3건(KEC)"은 노이즈였음 — before_clean에서는 0.
- 노이즈 제거 후: **건축물은 전 규모에서 전기·승강기 = 0**, 규모 역전 자체가 존재하지 않음.

## 부수 관측 (별개 사실, 이번 WO 판단 대상 아님)

익명진단 경로에서 건축물은 전 규모 전기·승강기 의무 0. 이것이 정상(익명 4필드로 전기용량·승강기수 입력 불가 → 해당 의무 미매칭이 설계상 정상)인지 여부는 CHG-001과 무관한 별도 관측 사항으로, 지금 판단하지 않는다. 필요 시 별도 관측 WO.

## 의의

WO-MEASURE-002의 측정 신뢰성 확보가 없었다면, 이 False Positive를 실제 결함으로 오인해 엉뚱한 계층을 수정했을 것이다. "관측 → 가설 → 최소 수정 → Measurement → Cause Confirmed" 흐름이 허위 CHG를 걸러냈다.
