---
wo: WO-E2E-DATASET-002
class: records
type: report
scope: canonical
project: test-universe
title: Stage 2a Validation Snapshot (Governance Reset before Freeze)
version: 1
status: active
owner: taiwang
---

# REPORT — Stage 2a Validation Snapshot

> WO-E2E-DATASET-002 Stage 2a. Generator 산출 84건을 taeng `test_universe.cases`에 적재·검증 완료.
> 검증은 **PASS**했으나, "최초 적재는 Stage 2b DDL Freeze 이후"라는 거버넌스 기준선 원칙을
> 회복하기 위해 **운영자 결정으로 84행을 TRUNCATE**함. (실패가 아니라 원칙 준수를 위한 되돌림.)

## Stage 2a Validation Snapshot

```
Generated Cases : 84   (16 Representative × scale×공사유무 발산축, dedup 후)
Target          : taeng (vwlahtguyggrhvslabax) schema test_universe.cases
Universe        : test-universe-v1

Invariant
  ✓ signature ⊆ contract.leg      (전수 위반 0)
  ✓ Allowed Matrix                 (scale band 준수)
  ✓ Deterministic                  (2회 재실행 동일)
  ✓ Dedup                          (fingerprint 84/84 unique)

Database Validation
  total 84 · uniq_case_id 84 · uniq_fingerprint 84 · REP 16
  bad_version 0 · empty_signature 0 · nonempty_objects 0
  fingerprint set == Generator expected  (drift 0, missing 0, extra 0)
  VERDICT: PASS

Disposition
  Rows removed by governance decision before Freeze.
  (검증 성공 · 기준선 원칙(Freeze 후 최초 적재) 준수를 위해 되돌림)
```

## 보존 자산 (TRUNCATE 후에도 유지)

```
Generator     tai-api : tools/test_universe/generator.py @ 8cd0df6d   유지 (Build Asset)
DDL/Migration guri-cf : supabase/migrations/20260730115204_create_test_universe_cases.sql  유지
Table         taeng   : test_universe.cases (schema/index)  유지 (데이터만 0)
Evidence      이 문서  유지
```

## 원칙 (재확정)

```
1. 기준선(Freeze) > 데이터.
2. Generator = Build Asset (Runtime 미import · Dataset 생성 시에만 실행 · E2E 사전 빌드 도구).
3. DDL 최종 Freeze = Stage 2b Objects Expansion Dry Run 이후.
4. 첫 공식 Dataset 적재 = DDL Freeze 시점 이후.
```

## WO 종료 상태

```
Generator      ✓
Dry Run        ✓
Invariant      ✓
Repository     ✓
Database Rows  0 (Governance Reset)
```

## 다음 WO (Stage 2b)
```
Objects Expansion → Dry Run → DDL Freeze → Migration → 첫 공식 INSERT
```
