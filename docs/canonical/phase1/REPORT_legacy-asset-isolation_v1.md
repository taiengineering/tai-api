---
wo: WO-ISOLATION-001
class: records
type: report
scope: canonical
project: phase1
title: Legacy Asset Isolation (Canonical Phase 1 Boundary Freeze)
version: 1
status: active
owner: taiwang
---

# REPORT — Legacy Asset Isolation (Canonical Phase 1 Boundary Freeze)

> WO-ISOLATION-001 (Legacy Asset Isolation, Pre-E2E). Fence-only: 삭제·대규모 이동 없음.
> Runtime/BusinessLogic/Engine/Rule/DB/API-contract 무변경.

## 0. Baseline

- Freeze tag: `canonical-phase1-freeze` → commit `e4803d77`
- Canonical Phase 1 = By-Construction Wrapper (5개 진단 진입점 통일)
- 본 문서는 **Canonical(주배선)** 과 **Legacy(기존자산)** 의 경계를 명문화한다.

## 1. Legacy Asset Inventory (STEP 1)

| Asset (category / key files) | Canonical 사용 | Legacy 직통 | 상태 |
|---|---|---|---|
| **Wrapper** — anonymous / anonymous-leg / run / run-leg / upgrade | YES (진입) | NO | ACTIVE (Canonical Layer) |
| **DTO / Adapter / Flag / evaluate()** — `services/canonical/*` | (Canonical 자체) | NO | ACTIVE (Canonical Layer) |
| **_impl** — `_create_anonymous_diagnosis_impl`, `_create_anonymous_diagnosis_leg_impl`, `_run_diagnosis_impl`, `_run_leg_impl`, `_upgrade_diagnosis_impl` | NO (delegate로만 호출됨) | YES | ACTIVE (Legacy 본문) |
| **Service (orchestration)** — `services/diagnosis_integrated_svc.py` | NO | YES | ACTIVE (Legacy) |
| **Compiler engine** — `services/anonymous_factory_service.py`, `services/compiler_engine_gateway.py` | NO | YES | ACTIVE (Legacy) |
| **LEG engine** — `services/leg_diagnosis_svc.py`, `clients/leg_runtime_client.py` | NO | YES | ACTIVE (Legacy) |
| **Binding** — `services/legal_adapter.py::project_rules` | NO | YES | ACTIVE (Legacy, non-blocking) |
| **Utility/Adapter** — `services/diagnosis_helpers.py`, `services/diagnosis_nexas_adapter.py`, `services/diagnosis_runtime_step1.py` | NO | YES | ACTIVE (Legacy) |
| **Runtime / Rule Repository** — Compiler Runtime, LEG Runtime(`/rtm/evaluate`), Rule repo | NO | YES | ACTIVE (Legacy engine) |
| **기타 diagnosis 라우터** — `diagnosis.py`, `diagnosis_autofill.py`, `diagnosis_report.py`, `diagnosis_roi.py`, `diagnosis_proposal.py`, `diagnosis_plan_recommend.py`, `diagnosis_transform.py`, `diagnosis_result_web.py`, `diagnosis_fields.py`, `diagnosis_runtime_projection.py`, `diagnosis_engine.py`, `trigger_diagnosis.py` | NO | YES | ACTIVE (Legacy-direct 서브기능, Phase 1 미대상) |

> Phase 1의 Canonical 대상은 **run/upgrade 계열 5개 진입점**뿐이다. 위 "기타 diagnosis 라우터"는 별개 엔드포인트(서브기능)로, Phase 1 범위 밖이며 그대로 유지된다.

## 2. Canonical Boundary (STEP 4)

```
Canonical 영역 (공식 진입)          Legacy 영역 (유지보수 전용)
────────────────────────           ──────────────────────────
Wrapper (@router.post)             _impl (verbatim legacy body)
DTO (CanonicalDiagnosisRequest)    diagnosis_integrated_svc (orchestration)
Adapter (*Adapter.to_canonical)    Compiler / anonymous_factory / gateway
Feature Flag (canonical_enabled)   LEG (leg_diagnosis_svc / leg_runtime_client)
evaluate(dto, delegate)            Binding (legal_adapter.project_rules)
                                   Runtime / Rule Repository
```

Boundary를 넘는 **신규 의존성 금지**.

## 3. Dependency Boundary Map (STEP 5) — 실측

`from services.canonical` 전체 참조(저장소 grep, total=5):

```
routers/anonymous_diagnosis.py       b4549343   (create_anonymous_diagnosis wrapper)
routers/anonymous_diagnosis_leg.py   c4e2d03b   (create_anonymous_diagnosis_leg wrapper)
routers/diagnosis_integrated.py      6c851cdf   (run_diagnosis + upgrade_diagnosis wrappers)
routers/diagnosis_integrated_leg.py  a1a63938   (run_diagnosis_leg wrapper)
tests/test_canonical_skeleton.py     d5a34ae9   (B#0 test)
```

규칙 및 판정:

| 방향 | 정책 | 실측 |
|---|---|---|
| Canonical → Legacy | 허용 (delegate lambda로 _impl 호출) | OK |
| Legacy → Canonical | 금지 (Wrapper 예외) | 위반 0 (오직 5 Wrapper) |
| Runtime → Canonical | 금지 | 위반 0 |
| _impl → Canonical | 금지 | 위반 0 (5개 _impl 모두 canonical 참조 = 0, 각 003 게이트에서 실측) |
| 순환 의존성 | 0 | **0 (PASS)** |

## 4. 진입 경로 봉인 (STEP 2)

- 신규 진입은 반드시: `Request → Wrapper → (flag OFF: _impl) | (flag ON: DTO→Adapter→evaluate→delegate→_impl)`
- **직접 Runtime/Compiler/LEG 호출은 신규 개발 금지.** 신규 로직은 Canonical Layer(또는 Legacy _impl 내부 유지보수)에서만.

## 5. Deprecated Entry List (STEP 6) — 삭제하지 않음

```
DEPRECATED (직접 사용 금지, 유지):
  - 직접 Runtime 호출 (Wrapper 우회)
  - 직접 Compiler 호출 (anonymous_factory / gateway 직접 신규 호출)
  - 직접 LEG 호출 (leg_diagnosis_svc 직접 신규 호출)
상태: DEPRECATED (기존 _impl 내부 사용은 정당 / 신규 진입점 추가만 금지)
```

## 6. Legacy Fence 규칙 (STEP 3 / 7)

```
Canonical
================
공식 진입 (Wrapper / DTO / Adapter / Flag / evaluate)

Legacy
================
유지보수 전용 (_impl / Compiler / LEG / Runtime / Binding)
신규 기능 추가 금지 — 새 기능은 Phase 2에서 Canonical Layer에 구현
```

> 인라인 fence 주석(`# LEGACY ENTRY ...`)은 방금 고정한 freeze blob SHA를 훼손하므로 기본 **defer**. 필요 시 별도 단일 커밋으로 일괄 적용(운영자 승인).

## 7. 완료 판정

```
Legacy Inventory        PASS
Boundary                PASS
Circular Dependency     NONE
Legacy Fence            PASS (문서 기준)
Canonical Boundary      PASS
Deletion                NONE
Behavior Change         NONE
```

## 8. Open Backlog → 별도 트랙

- DATA-001 (시설물안전법 26→20) · DATA-LEG-001 (LEG applicable=0)
- Canonical Phase 2: Engine Selection · Claim · Upgrade · Report · Audit Hook · Shadow Execution
