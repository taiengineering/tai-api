---
wo: WO-ENGINE-CHANGESET-001
class: records
type: report
scope: canonical
project: test-universe
title: Change Impact v1
version: 1
status: active
owner: taiwang
---

# REPORT — Change Impact v1

> WO-ENGINE-CHANGESET-001 STEP3. 각 Change의 변경 범위·예상 영향. **예상은 참고이며 판정 아님.**

## CHG-001 — 건축물 규모 역전: 대형 건축물에서 전기·승강기 대표의무 미포함

| 항목 | 값 |
|---|---|
| 유형 | Coverage-Inversion |
| 영향 섹터 | BUILDING |
| 영향 Profile | 건축물 29건 중 대형 다수(전기·승강기 미커버 26건) |
| 커버리지 통계 | 건축물 전기 3/29·승강기 3/29 (커버가 저건축물에 몰림) |
| 관찰 사실 | 고건축물(large·300명·60000㎡: PF-0019 obl107·PF-0023 obl102)은 전기·승강기 법령 미포함(법령 18). 저건축물(medium·50명·15000㎡: PF-0021·0025·0026 obl28)은 전기·승강기 포함(법령 14). 규모↑일수록 전기·승강기 빠지는 역전 관찰. |
| 예상 영향(참고) | 전기·승강기 대표의무 포함 시 대형 건축물 obligation 증가 가능 |
| 원인 판정 | UNKNOWN — 추가 실측 필요 |

## CHG-002 — 특수시설(SPECIAL_FACILITY) 산업안전 대표의무 전건 미커버

| 항목 | 값 |
|---|---|
| 유형 | Coverage-Gap |
| 영향 섹터 | SPECIAL_FACILITY |
| 영향 Profile | 특수시설 10건 전체 |
| 커버리지 통계 | 특수시설 산업안전 0/10 |
| 관찰 사실 | 특수시설 10/10 전건에서 산업안전 도메인 미커버. 작업환경만 10/10 커버. obligation 전건 7(동일). |
| 예상 영향(참고) | 산업안전 draft 매핑 시 특수시설 obligation 증가 가능 |
| 원인 판정 | UNKNOWN — 추가 실측 필요 |

## 원칙

> 예상 영향은 Before 사실에서 도출한 참고 정보다. 실제 영향은 Engine 수정 후 AFTER/Before Semantic Diff에서 측정한다.
> 이 WO는 수정하지 않는다.
