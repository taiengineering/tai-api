---
wo: WO-ENGINE-CHANGESET-001
class: records
type: report
scope: canonical
project: test-universe
title: Engine Change Set v1
version: 1
status: active
owner: taiwang
---

# REPORT — Engine Change Set v1 (ENGINE_CHANGESET_V1)

> WO-ENGINE-CHANGESET-001. Before Baseline 기준 수정 대상 정의. **코드 미수정. 원인은 분류 후보(판정 아님).**
> Before: BEFORE_BASELINE_V1 (checksum d2d2e39f...) · Frozen: True

## 1. Change Set (수정 대상 후보 — Freeze)

| ID | 유형 | 내용 | 근거(관찰 사실) |
|---|---|---|---|
| CHG-001 | Coverage-Inversion | 건축물 규모 역전: 대형 건축물에서 전기·승강기 대표의무 미포함 | 고건축물(large·300명·60000㎡: PF-0019 obl107·PF-0023 obl102)은 전기·승강기 법령 미포함(법령 18). 저건축물(medium·50명·15000㎡: PF-0021·0025·0026 obl28)은 전기·승강기 포함(법령 14). |
| CHG-002 | Coverage-Gap | 특수시설(SPECIAL_FACILITY) 산업안전 대표의무 전건 미커버 | 특수시설 10/10 전건에서 산업안전 도메인 미커버. 작업환경만 10/10 커버. obligation 전건 7(동일). |

## 2. 원인 분류 (STEP 2 — 분류만, 판정 아님)

| ID | 분류 후보 | 원인 판정 | 확정에 필요한 실측 |
|---|---|---|---|
| CHG-001 | Engine 문제(규모 분기 로직) / Rule 데이터 문제(대형 building draft 매핑) / 정상 동작(대형은 별도 체계로 제외) | **UNKNOWN — 추가 실측 필요** | 고/저 건축물의 facility_applicability·draft_slot 매칭 결과 실측(engine_isolated), law_sector_mapping BUILDING draft 대조 |
| CHG-002 | Compiler 문제(site_kind=other 매핑) / Rule 데이터 문제(SPECIAL_FACILITY sector 매핑 부재) / Consumer Profile 문제(특수시설 입력 표현) / 정상 동작 | **UNKNOWN — 추가 실측 필요** | site_kind=other→sector 매핑(anonymous_diagnosis.py SECTOR_BY_KIND=SPECIAL_FACILITY) 후 law_sector_mapping에 SPECIAL_FACILITY 산업안전 draft 존재 여부 실측 |

> 원인은 분류 후보로만 제시한다. 확정(Engine/Compiler/Rule/Master/정상)은 엔진 수정 전 별도 실측 WO에서.

## 3. Change Set 제외 항목

| 항목 | 제외 사유 |
|---|---|
| 건축물 이상치 3건(obl28) | CHG-001과 동일 현상의 반대편(저건축물). 별도 변경 아님 — CHG-001에 포섭. |
| 제조·건설 균일성 | 기대 도메인 전건 커버(제조 5/5·건설 3/3). 변경 대상 아님. |
| HTTP 502 실패 2건 | 라이브 인프라 일시 오류. FREEZE에서 재실행 해소(112/112). 엔진 변경 아님. |

## 4. Freeze

```
ENGINE_CHANGESET_V1
  CHG-001  건축물 규모 역전: 대형 건축물에서 전기·승강기 대표의무 미포함
  CHG-002  특수시설(SPECIAL_FACILITY) 산업안전 대표의무 전건 미커버
```

> 이 목록만 수정 대상 검토 후보로 인정한다. 다음 순서: 원인 실측 → Engine 수정 → AFTER 112 → Semantic Diff.
