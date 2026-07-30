---
wo: WO-E2E-PROFILE-001
class: records
type: note
scope: canonical
project: test-universe
title: Profile Universe v2 Direction (Scenario, Tracking IDs)
version: 1
status: active
owner: taiwang
---

# NOTE — Profile Universe v2 보완 방향 (운영자 제시)

> 운영자 제시 방향의 기록. v2는 지금 구현하지 않는다. 다음 단계 = E2E Runner 연결(Profile 늘리기 아님).
> WO-E2E-PROFILE-001(v1, 112 Profile, PF-0001~PF-0112)은 완료. 본 노트는 v1 자산을 변경하지 않는다.

## 1. v1 완료 상태 (기준선)

profile_universe_v1.json / REGISTRY_profile-universe_v1.md — 112 Consumer Profile.
현재 Profile은 정적 상태(Static State) 중심: Company · Building · Process · Facility · Work · (Construction).

## 2. v2 보완 방향 ① — Static / Scenario 분리 (운영자 제시)

실제 법령 적용은 상태 + 이벤트 조합으로 발생하는 경우가 많다(예: 정기보수 기간·야간작업·밀폐공간 작업 시작·위험물 반입·신규 설비 설치·공사 착공/준공). 동일 사업장이라도 이벤트가 적용 의무를 바꿀 수 있다.

```
Profile
 ├─ Static                     (사업장 고정 특성)
 │   ├─ Company
 │   ├─ Building
 │   ├─ Process
 │   ├─ Facility
 │   └─ Work
 │
 └─ Scenario                   (특정 시점의 운영 상태)
     ├─ Normal
     ├─ Maintenance
     ├─ Construction
     ├─ Emergency
     └─ Shutdown
```

- Profile = 사업장의 고정 특성.
- Scenario = 특정 시점의 운영 상태.
- 구체 Scenario 필드·Compiler field_code 매핑은 E2E Runner 설계 시 함께 확정(운영자 결정).

## 3. v2 보완 방향 ② — 추적 식별자 (운영자 제시)

E2E는 결과를 비교하므로 각 Profile에 추적 식별자를 둔다. Profile 변경·Engine 변경·Golden 변경을 서로 독립적으로 추적하기 위함.

```
PF-0041
 ├─ Profile Version : v1
 ├─ Engine Version  : compiler-core-3.x
 ├─ Snapshot ID     : SNAP-0041-001
 └─ Golden ID       : GOLD-0041
```

- Profile Version / Engine Version / Snapshot ID / Golden ID 4종.
- Snapshot ID·Golden ID는 E2E Runner가 생성 시 채운다(현재 v1에는 미포함).

## 4. 다음 단계 (순서)

```
PROFILE_UNIVERSE_V1  →  E2E Runner  →  Engine  →  Snapshot  →  Golden  →  Diff  →  Regression
```

다음 WO는 Profile을 늘리지 않는다. profile_universe_v1.json 을 E2E Runner에 연결하여 Snapshot·Golden을 생성한다. v2(Scenario·추적ID)는 그 이후 별도 WO에서 반영 여부·시점을 운영자가 결정한다.
