---
wo: 45CM-OPERATION-MODE
class: records
type: standard
scope: canonical
project: test-universe
title: 45CM Operation Mode
version: 1
status: active
owner: taiwang
---

# 45CM Operation Mode

```text
MODE       : E2E_IMPROVEMENT
Status     : ACTIVE
Applies To : 모든 CHG · 모든 E2E Loop · 법령엔진(test-universe) 프로젝트
Until      : 운영자가 변경할 때까지
```

> 새 세션은 이 레코드의 MODE만 읽으면 된다. 이 규칙들은 메모리가 아니라 프로젝트 Operation Mode로 관리한다(다른 프로젝트 오염 방지).

## 1. Engine Fix의 의미
"Engine Fix"(및 WO명의 Fix)는 **Code 수정이 아니라 '원인으로 확인된 계층의 수정'**을 뜻한다. 이 프로젝트는 Code 중심이 아니라 Data 중심 — 대부분의 장애는 Object / Configuration / Rule Data / Master / Mapping에서 해결된다.

## 2. 수정 우선순위
```text
Object → Configuration → Rule Data → Master Data → Code
```
상위에서 해결되면 하위는 수정하지 않는다. Code는 앞 4계층이 **모두 반증된 경우에만** 검토하는 최후 선택지이며 기본 가정이 아니다.

## 3. Measure Before Modify
UNKNOWN(Master/Engine 등)이 남아도 Code 수정을 준비하지 않는다. 먼저 해당 계층 데이터(Rule Data=draft_slot, Master=law_sector_mapping, Configuration)를 실측/판단해 실제 수정 대상 계층을 정한 뒤에만 수정한다.

## 4. Investigation 종료 조건 (즉시 수정 진입)
아래 3조건이면 Investigation은 종료된 것으로 간주하고 즉시 수정 단계로 간다. 원인 100% 증명을 기다리지 않는다.
```text
수정 대상 계층 식별  AND  최소 범위  AND  Rollback 가능
```

## 5. E2E Loop (모든 Change Set)
```text
Measure(Before) → Hypothesis → Minimum Modify → Runner(112) → After Snapshot
→ Semantic Diff → Regression → KEEP / REVISE / ROLLBACK
```
- Modify는 산출물이 아니라 Runner의 입력이다.
- 실행 주체 = Operator가 end-to-end 수행. 실행환경 제약으로 직접 Runner를 못 돌리는 경우에만 "엔진 런타임에서 apply Modify + Runner 1회 + After"를 **단일 실행 스텝**으로 간주하며, 별도 Investigation·사용자작업으로 쪼개지 않는다.

## 6. Max Loop (종료 보장)
동일 Change Set는 **최대 3회**까지 E2E Loop를 반복한다.
```text
Loop1 FAIL → Loop2 FAIL → Loop3 FAIL
→ Cause Reclassification → 새 가설 → Loop1부터 재시작
```
3회 안에 KEEP에 도달하지 못하면 REVISE가 아니라 **Cause Reclassification**(수정 계층 재분류)으로 넘어간다. 성공하지 못했다고 무한히 Investigation으로 회귀하지 않는다.

## 7. Investigation 재개 조건 (이때만)
```text
Regression FAIL  OR  가설 반증  OR  수정 계층 자체가 틀림(3회 실패 → Cause Reclassification)
```
그 외에는 Investigation을 다시 시작하지 않는다.

## 8. Goal 종료 기준
Goal은 **문서 생성으로 종료하지 않는다.** 다음까지 완료해야 종료한다.
```text
Modify → Runner → After Snapshot → Semantic Diff → Regression → KEEP/REVISE/ROLLBACK 판정
```

## 9. 매 WO의 첫 질문
```text
현재 확보된 근거로 가장 작은 수정 가설을 만들 수 있는가?
```
YES → 즉시 Modify → Runner → Regression. 추가 Investigation 없음.
NO → 4계층 중 어디를 측정하면 가설이 서는지 최소 측정 후 즉시 루프.

## 10. Operator 역할
Investigator가 아니라 **E2E Improvement Operator**. 판단 기준은 "더 조사할 것인가?"가 아니라 "현재 근거로 가장 작은 수정을 적용해 검증할 수 있는가?"이다. 목표는 UNKNOWN 제거가 아니라 품질 개선.
