---
wo: WO-ENGINE-CAUSE-INVESTIGATION-001
class: records
type: report
scope: canonical
project: test-universe
title: Engine Change Set Cause Investigation v1
version: 1
status: active
owner: taiwang
---

# REPORT — Engine Change Set Cause Investigation v1

> WO-ENGINE-CAUSE-INVESTIGATION-001. Before Baseline 기준 CHG-001·CHG-002 원인을 계층에 귀속.
> **코드 read-only 실측만. 엔진·Rule·Before·Golden·Master 무수정. 추측 금지 — 근거 없으면 UNKNOWN.**
> Before: BEFORE_BASELINE_V1 (checksum d2d2e39f...) · Frozen: True
> Goal: G-ms88y8w6-74b588

## 0. 측정 환경

| 구분 | 계층 | 사유 |
|---|---|---|
| 측정 가능 | Consumer · Compiler · Rule Gate | tai-api 리포 코드 read-only |
| 측정 불가 | Rule Data · Master · Engine | engine_isolated 스키마(draft_slot·facility_applicability·law_sector_mapping)의 project_ref가 런타임 env(SUPABASE_URL)에만 존재. governance ref·leg-prod ref 모두 미보유 확인. 클라우드 세션 SELECT 불가. |

> 측정 불가 계층은 UNKNOWN 유지. UNKNOWN은 실패가 아니라 측정 한계다.

## 1. 조사 순서 (운영자 확정)

Consumer Profile → Compiler Context → Master → Rule Mapping → Engine Resolution → Snapshot(Output).

## 2. 계층 귀속

### CHG-001 — 건축물 규모 역전 (대형 건축물 전기·승강기 대표의무 미포함)

| 계층 | 판정 | 근거(코드 실측) |
|---|---|---|
| Consumer | ❌ | 전기·승강기 필드(electrical_capacity_kw·elevator_count)가 대형·소형 모두 0으로 동일 → 규모 역전을 만들 수 없음. 차등 입력은 scale/workers뿐. |
| Compiler | ❌ | `_build_step1_body`·`_input_to_facility_context`가 `total_floor_area`를 scale대로 충실 반영(small 400 / large 12000). 규모별 draft를 선택적으로 누락하지 않음. |
| Rule Gate | ❌ | `_load_sector_allowed_draft_ids`는 sector=BUILDING에 대해 규모 무관 동일 draft 집합 반환 → scale 의존 역전을 만들 수 없음(구조적 반증). |
| Rule Data | UNKNOWN | 역전을 만들 `draft_slot` IF_NUMERIC 임계값(연면적/인원 컷)·`facility_applicability`가 Rule Repository(engine_isolated)에 있음 — 미접근. |
| Master | UNKNOWN | `law_sector_mapping`·`law_master`(BUILDING 대형 draft 매핑) — 미접근. |
| Engine | UNKNOWN | `evaluate_draft_for_facility` 실제 매칭 결과 — 런타임 데이터, 미접근. |

결론: Consumer·Compiler·Rule Gate 아님(반증). 역전 메커니즘은 Rule Data / Master / Engine으로 좁혀지며 전부 UNKNOWN.

### CHG-002 — 특수시설(SPECIAL_FACILITY) 산업안전 대표의무 전건 미커버 (작업환경만 10/10)

| 계층 | 판정 | 근거(코드 실측) |
|---|---|---|
| Consumer | 부분 | `worker_count`·면적 제공됨(✅). 동일 입력으로 작업환경은 10/10 커버 → 입력 자체는 일부 도메인 산출에 충분. 산업안전 draft의 요구필드가 특수시설 고유필드에 의존하는지는 `draft_slot`(UNKNOWN)이라 완전 배제 보류. |
| Compiler | ❌ | `other→SPECIAL_FACILITY` 정확, factory.sector에 보존, 엔진 경로에서 BUILDING으로 접히지 않음(`_input_to_facility_context` 전용 분기 존재; `_SECTOR_NORMALIZE`는 출력/이벤트 전용). "site_kind=other 매핑" 후보는 코드로 반증. |
| Rule Gate | ❌ | 게이트 로직은 일반적 — 산업안전을 하드코딩 배제하지 않음. 배제는 `law_sector_mapping` 데이터에 "타 sector 전용"으로 명시된 경우에 한함. |
| Rule Data | UNKNOWN | `draft_slot`·`facility_applicability`(산업안전 draft 평가) — 미접근. |
| Master | UNKNOWN | `law_sector_mapping`이 산업안전 법령을 SPECIAL_FACILITY에서 제외하는지 여부 — 미접근. |
| Engine | UNKNOWN | 산업안전 draft의 `evaluate_draft_for_facility` 결과 — 미접근. |

결론: Compiler·Rule Gate 아님(반증). Consumer는 부분(주요 구동값 제공). 원인은 Rule Data / Master / Engine으로 좁혀지며 전부 UNKNOWN.

## 3. Evidence (코드 인용 — 전부 taiengineering/tai-api)

| 파일 | sha | 확인 사실 |
|---|---|---|
| routers/anonymous_diagnosis.py | b4549343 | `SECTOR_BY_KIND`(other→SPECIAL_FACILITY) · `SCALE_PRESETS`(small 400/medium 2800/large 12000) · `_build_step1_body`(BUILDING: floor_count=5 고정, electric/elevator 미설정) · `_SECTOR_NORMALIZE`는 emit_event·출력 전용(엔진 입력 미적용) |
| services/anonymous_factory_service.py | b822b865 | `_load_sector_allowed_draft_ids`(sector 단위·일반 로직·미매핑 보수 통과·타 sector 전용만 제외) · `create_temp_factory` · `run_anonymous_diagnosis` |
| services/legal_context.py | f6c2b556 | `_input_to_facility_context` — BUILDING 분기(electrical_capacity_kw=0·elevator_count=0, 대형·소형 동일) · SPECIAL_FACILITY 전용 분기(worker_count 제공·BUILDING 미접힘) |
| constants/sectors.py | 19cc47bf | `to_mapping_sector = normalize_sector_db` — SPECIAL_FACILITY 독립 표준키 유지(BUILDING 미접힘) |

## 4. 미측정 항목 (다음 단계 입력)

| 계층 | 측정 대상 | 후보 지점 |
|---|---|---|
| Rule Data | `draft_slot` IF_NUMERIC 임계값 · `facility_applicability` | CHG-001 규모 역전 발생 지점 후보 |
| Master | `law_sector_mapping`(sector↔법령) · `law_master` | CHG-002 산업안전 배제 지점 후보 |
| Engine | `evaluate_draft_for_facility` 런타임 결과 | 실제 매칭/미매칭 확정 |

접근 조건: engine_isolated project_ref 확보(taieng 서비스 배포 env의 SUPABASE_URL) 또는 On-your-computer 실측 환경.

## 5. 결론

- CHG-001·CHG-002 모두 **Consumer·Compiler·Rule Gate에서 원인 아님(반증 완료)**.
- 남은 후보: **Rule Data / Master / Engine — 전부 UNKNOWN(측정 환경 부재)**.
- `WO-ENGINE-FIX-001`은 실제 수정 대상(draft_slot 임계값 / law_sector_mapping)이 UNKNOWN 계층에 있으므로, **엔진 DB 접근 확보 전 착수 불가**.

## 6. WO 종료 조건

| 종료 조건 | 상태 |
|---|---|
| Consumer→Compiler→Rule Gate 실측 완료 | 완료 |
| Rule Data/Master/Engine UNKNOWN 유지(측정 환경 부재) | 준수 |
| 각 CHG 단일 계층 귀속 또는 UNKNOWN + Evidence 연결 | 완료 |
| 추측·단정 0 / Before·Engine·Rule 무수정 | 준수 |
