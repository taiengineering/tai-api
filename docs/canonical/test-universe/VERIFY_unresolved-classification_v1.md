---
wo: WO-CORRECTION-002
class: records
type: verification
scope: canonical
project: test-universe
title: UNRESOLVED Structure Classification
version: 1
status: active
owner: taiwang
---

# UNRESOLVED STRUCTURE CLASSIFICATION (FROZEN) — WO-CORRECTION-002

> WO-CORRECTION-001의 unresolved_queue 56건을 기존 구조 안에서만 분류. **새 Pattern·Rule·Exception·Taxonomy·Role 변경·sector 판단 없음.** UNRESOLVED가 왜 Pattern 밖에 남았는지 구조적 원인만 분류 → 해결 대상이 아니라 구조화된 작업 대기열.
> Input(Read Only): Pattern Dictionary·role_pattern_v2·Context Matrix·Evidence Sheet v2·unresolved_queue.csv.

## 판정: PASSED

## STEP 1 — Inventory
- unresolved_queue.csv 56건 전량 확인 (법령·값·근거조문·Context·Role). Role은 전부 UNRESOLVED(CORRECTION-001).

## STEP 2-4 — Structure Classification + Statistics
각 UNRESOLVED가 기존 Pattern으로 해결 안 된 구조적 이유(빈도만, 해석 없음):
```text
UC-01 정의문 없음      : 17
UC-05 참조문           : 16
UC-07 복합문           : 11
UC-03 열거문           :  6
UC-04 목적문           :  3
UC-06 표/별표 참조     :  3
UC-02 적용문 없음      :  0
UC-08 원문 부족        :  0
UC-09 기타             :  0
합계                  : 56
```
- 예시: 건축물착공통계조사규칙·건축물 → UC-01(정의 조문 없음), 건축물관리법 시행령·공동주택 → UC-05(타법 참조), 기계설비법 시행령·건축물 → UC-06(별표 참조), 공동주택관리법 시행규칙·공동주택 → UC-04(목적문).
- 관측: 같은 값(건축물 등)이 법령마다 다른 문형(정의/참조/열거)으로 등장 → 그것이 UNRESOLVED의 구조적 원인. (해석 아님, 빈도 기록)

## STEP 3 — Replay
- 동일 분류기 재적용: **56 → 56, Classification Drift 0.**

## STEP 5 — Review
```text
새 Pattern    : 0 (Pattern Dictionary 13개 불변)
새 Rule       : 0
새 Exception  : 0
새 Taxonomy   : 0
Role 변경     : 0 (UNRESOLVED 유지)
Pattern 변경  : 0
Context 변경  : 0
```
- UC-01~09는 "왜 Pattern 밖인가"의 분류 라벨(작업 대기열 태그)이지, sector/Role을 결정하는 Taxonomy가 아님. 지시서 제공 분류 체계를 적용만 함.

## STEP 6 — Freeze
```text
unresolved_classification.csv : 56행 (법령·값·UC·분류사유), checksum 84402ec4b4b451f0
unresolved_statistics         : 본 문서 STEP2-4 (UC별 빈도)
correction_review             : 본 문서 STEP5 (신규 생성 0)
```

## 결론
- 56 UNRESOLVED를 구조적 원인(UC-01~09)으로 전량 분류. **해결 대상이 아니라 구조화된 작업 대기열로 전환.**
- 최다 원인: UC-01 정의문 없음 17·UC-05 참조문 16·UC-07 복합문 11 (전체의 61%).
- 신규 Pattern/Rule/Exception/Taxonomy 0, Role/Pattern/Context Drift 0. Correction 흐름 유지(Discovery로 회귀 안 함).
- **효과:** 다음 Discovery가 필요할 때 56건 전체를 다시 읽지 않고, 동일 구조 원인별(UC)로 묶어 처리 가능. 예: UC-01 17건은 "정의 문형 확장"이 필요한지 한 번에 판단.
- **여전히 미판단:** UNRESOLVED의 Role·sector는 결정 안 함. 이 WO는 "왜 미해결인가"의 분류만.

## Exit Criteria 점검
```text
[v] 56건 전량 분류
[v] Role Drift 0
[v] Pattern Drift 0
[v] 새 Pattern 0 · 새 Rule 0 · 새 Exception 0 · 새 Taxonomy 0
[v] Classification Replay Drift 0
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
㉕ Pattern Dictionary Normalize ✓ WO-PATTERN-002
㉖ Discovery Freeze·구조 보정    ✓ WO-CORRECTION-001 (RESOLVED 103·UNRESOLVED 56)
㉗ UNRESOLVED 구조 분류          ✓ WO-CORRECTION-002 (UC-01~07, Drift 0) ← 현재
㉘ (선택) UC별 Discovery or sector 함의 ← 다음
```
