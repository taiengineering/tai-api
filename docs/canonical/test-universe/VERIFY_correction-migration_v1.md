---
wo: WO-CORRECTION-001
class: records
type: verification
scope: canonical
project: test-universe
title: Discovery Freeze 이후 구조 보정
version: 1
status: active
owner: taiwang
---

# DISCOVERY FREEZE 이후 구조 보정 (FROZEN) — WO-CORRECTION-001

> Discovery 종료. 검증된 구조(Pattern Dictionary 등)를 393에 적용해 운영 가능 상태로 고정. **새 Pattern·Rule·Exception·Taxonomy·sector 추론 없음.** 억지 PASS 금지, 미발견은 UNRESOLVED.
> Input(검증 완료 자산만): Evidence Sheet v2·Context Matrix(+Normalized)·Role Verification·Role Pattern·Pattern Dictionary·393 mapped.

## 판정: PASSED

## STEP 1 — Discovery Freeze (Read Only, checksum)
```text
Evidence Sheet v2         45ac892d4290a198
Context Matrix            0a78f4e327d3de2a
Context Matrix Normalized b8e95fcc317639ab
Role Verification         9bf9f272d8994a31
Role Pattern              93477bed5907152d
Role Pattern v2           9968bbf658491284
Pattern Dictionary        de58bdca9fb911ce
393 mapped evidence       f61964917838837f
```

## STEP 2-4 — Migration + Replay (Pattern Dictionary → 393)
- Pattern Dictionary 13문형을 393 각 법령의 시설/규율대상 후보값에 적용(새 Pattern·어휘 발명 없음).
```text
393 후보값 총           : 159건
Pattern 매칭(RESOLVED)  : 103 (64.8%)  — REGULATED 79 · FACILITY 24
UNRESOLVED(문형 없음)   :  56 (35.2%)
사용 Pattern: P-R1 45·P-R4 28·P-F5 12·P-F6 11·P-R2 3·P-R5 2·P-R3 1·P-F4 1
```

## STEP 4 — Drift 검증
```text
Role Drift (FP-03 7법령 확정 Role 재현) : 0  (변경 없음)
과매칭 점검 (P-R1 표본)                : 정상 — 전부 실제 정의 조문
  "건설기계"란 건설공사에 사용하는 기계 · "건축물"이란 토지에 정착하는 공작물 (진짜 정의)
```

## STEP 5 — Stability Audit
```text
새 Pattern 생성   : 0 (Dictionary 13개 그대로)
새 Rule 생성      : 0
새 Exception 생성 : 0
새 Taxonomy 생성  : 0
Structure Drift   : 0
Role Drift        : 0
Replay 가능       : Yes (Pattern Dictionary → 재현)
```

## 중대한 한계 (정직 명시)
- **이 Migration은 Role 층(규율대상/시설)이지 sector 층(BUILDING/INDUSTRIAL 등)이 아님.** 393의 실제 정답은 sector이고 Role은 그 아래 중간 단계. "Role migration이 393 sector 정답과 맞는가"는 **층이 달라 비교 불가.** 억지 연결 시 sector 추론(금지)이 됨.
- Pattern Dictionary는 FP-03 7법령의 규율대상/시설 문형에서 도출 → 393 전체에 대한 UNRESOLVED 35.2%는 **정상**(이 문형 밖 표현이 다수). 억지 일반화 배제.

## STEP 6 — Freeze 산출물
```text
correction_result.csv : 159행 (법령·값·Role·Pattern_ID), checksum b4aaac85102581f8
unresolved_queue.csv  : 56행 (사람 검토 대상, 문형 미매칭)
migration_log         : 본 문서 STEP2-4
replay_report         : 본 문서 STEP4 (Drift 0)
stability_audit       : 본 문서 STEP5 (신규 생성 0)
```

## 결론
- 검증된 구조를 393에 적용해 운영 가능 상태로 고정. **신규 Pattern/Rule/Exception/Taxonomy 0, Drift 0.**
- RESOLVED 103(64.8%)은 Role(규율대상/시설)까지 연결·근거 Pattern 보유. UNRESOLVED 56(35.2%)은 문형 밖 → 억지 일반화 없이 unresolved_queue로 분리(사람 검토 대상).
- **Discovery는 종료.** 이후 신규 발견이 필요하면 별도 Discovery WO. 본 WO는 발견 아닌 적용·고정.
- **sector는 여전히 미판단** — Role까지만 운영 구조화. sector 함의는 별도 단계(Role+Pattern 기반).

## Exit Criteria 점검
```text
[v] Discovery Freeze 유지 (checksum 기록)
[v] 신규 Pattern 0 · Rule 0 · Exception 0 · Taxonomy 0
[v] 393 Migration 완료 (159 후보값)
[v] Replay 성공 (Drift 0)
[v] Drift 없음 (Role/Structure)
[v] UNRESOLVED 분리 완료 (56, unresolved_queue.csv)
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
㉔ Role Pattern Extraction      ✓ WO-PATTERN-001
㉕ Pattern Dictionary Normalize ✓ WO-PATTERN-002
㉖ Discovery Freeze·구조 보정    ✓ WO-CORRECTION-001 (RESOLVED 103·UNRESOLVED 56·Drift 0) ← 현재
㉗ (선택) sector 함의 분석 or unresolved_queue 처리 ← 다음
```
