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

## 11. Measurement Integrity (측정 신뢰성 — CHG보다 우선)
측정이 신뢰되지 않으면 모든 Regression이 무효다. 그러므로 아래는 모든 CHG에 선행한다.

**11.1 Measurement Gate.** 모든 CHG는 시작 전 다음을 통과해야 한다.
```text
동일 입력 → Runner 2회 → changed = 0
```
changed > 0 이면 CHG를 시작하지 않고 **측정 환경부터 수정**한다.

**11.2 Runner 표준.** CHG 동안 Runner 기본값:
```text
RUN_WORKERS=1 · RUN_TIMEOUT_S=180 · RUN_RETRIES=1
```
병렬 Runner는 성능 검증 전까지 사용하지 않는다. (실측: 짧은 타임아웃/병렬은 394만 행 스캔 지연으로 부분집계 노이즈를 만들어 결과를 오염시킴 — 엔진 자체는 결정적.)

**11.3 Before Clean.** 타임아웃 오염 가능성이 있는 기존 Before는 Regression 기준으로 쓰지 않는다. 새 기준 `Before Clean` 생성 조건:
```text
Runner 2회 → changed = 0 → Freeze
```

**11.4 성능 수정 우선순위.** 성능은 Code 문제가 아니다.
```text
Configuration → Index → Query → Code
```

**11.5 CHG 재개 조건.**
```text
Before Clean 생성  AND  Runner 결정성 확보  AND  Measurement Gate PASS
```

**11.6 측정 완전성 (Preview ≠ Full).** 측정은 전체 결과를 담아야 한다. 익명 `/anonymous-diagnosis`는 preview(rules_table 12)만 반환하며 전체 의무는 `appointment/inspection/action/report_required` 배열에 있다(합 = applicable_count, `hasFullResult:true`). Runner/Snapshot은 preview가 아니라 **전량 의무**를 저장·비교해야 한다. preview 기준 관측은 무효로 간주한다.

## 12. E2E_REVIEW 모드 (발견 ≠ 해결)
Review는 **수정이 아니라 발견(Discovery)**이다. Claude의 '첫 문제 몰입'(발견 즉시 원인분석·수정으로 진입)을 규칙으로 차단한다.

**12.1 Review 중 CHG 생성 금지.** 흐름은 오직: 읽기 → Issue 등록 → 다음 Profile → 반복. 발견 즉시 CHG로 가지 않는다.

**12.2 Issue는 누적만.** Issue-001, 002, 003 … Issue-N을 쌓기만 한다. 중간에 해결하지 않는다. 첫 Issue에 몰입하다 더 근본 Issue를 놓치는 것을 막는다. (실례: Issue-001에 몰입해 CHG 생성 → 이후 Issue-003 Preview저장이 더 근본임을 발견.)

**12.3 전수 후 분류.** 전량 검토가 끝난 뒤에야 Issue를 분류한다: Engine / Data / Query / UI / Rule / Performance / Measurement.

**12.4 영향도 계산.** 분류 후 각 Issue의 영향도를 매긴다: Critical / High / Medium / Low.

**12.5 그다음에야 CHG.** 순서는 반드시 Issue → 우선순위 → CHG. 절대 'Issue 발견 → CHG 생성'으로 직행하지 않는다.

**12.6 허용/금지 표현.** Review 중 허용: 관측 · 등록 · 보류 · 후순위 · 분류. 금지: "원인을 찾겠습니다" · "수정하겠습니다" · "가설을 세우겠습니다".

**12.7 완성 표 전제.** Review 종료 시 아래 표가 반드시 존재해야 하며, 이 표가 완성되기 전에는 **어떤 CHG도 생성하지 않는다.**
```text
ID   | Issue           | 범위        | 영향도    | CHG 여부
001  | 동일 입력 다른 출력 | 10 Profile | Critical | 후보
002  | 의무 중복         | 112 Profile| High     | 후보
003  | Preview 저장      | 전체        | Critical | 후보
...  | ...             | ...        | ...      | 보류
```

**12.8 Goal 종료.** Review는 '모든 Issue를 발견하는 것'으로 끝난다. 고치는 것은 다음 WO다.
