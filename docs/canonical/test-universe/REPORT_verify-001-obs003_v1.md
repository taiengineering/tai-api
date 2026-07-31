---
wo: WO-VERIFY-001
class: records
type: report
scope: canonical
project: test-universe
title: Obs-003 Semantic Verification
version: 1
status: active
owner: taiwang
---

# REPORT — WO-VERIFY-001 Obs-003 Semantic Verification

> 최종 판정은 의미(Semantic). 숫자는 보조. Obs-003만 검증. 다른 Observation은 관측만(해결·Analysis 없음).
> Input: Before=before_clean, After=after_obs003(수정 Runner로 112 재실행, 병렬 워커6·180s·재시도2 — 워커6 결정성 사전 PASS), CHG Report(acdc230c).

## 1. Before
- 집계 방식: 구 Runner(preview). 집계 지표 preview_count = rules_table 길이.
- 분포: preview_count ∈ {6, 7, 12} (대부분 12로 절단).

## 2. After
- 집계 방식: 수정 Runner(full, *_required 전량). 지표 full_count.
- 무결성: full_count == applicable_count, 112/112 일치. full_count 범위 7~107.

## 3. Semantic Difference (읽어서 판정)

### (A) Obs-003 순수 효과 — 엔진 응답이 동일한 102 profile
- 구 집계(preview_count) 12/7 → 신 집계(full_count) 전량. 93/102에서 full_count > preview_count (예: PF-0001 12→18, PF-0002 12→23).
- 의미 확인(PF-0001): before/after 의무 **집합 동일(True)**. 내용 변화 없음 — preview 12개 절단에서 전량 노출로 바뀐 것. 순서 차이만 존재(정렬).
- 판정: **Expected Change** — CHG-001 의도(preview→full 집계)와 일치. 새 의무 생성 아님, 기존 전량의 온전한 집계.

### (B) 엔진 응답이 달라진 10 profile
- PF-0020·0023·0027 (applicable_count 102→107), PF-0030·0031·0032·0033·0034·0036 (23→24 또는 19→20), PF-0038 (6→7).
- applicable_count는 **엔진 응답값**이다. Obs-003 수정은 Runner 집계 로직이므로 엔진 응답(applicable_count)을 바꿀 수 없다.
- 따라서 이 차이의 원인은 CHG-001이 아니라 **before_clean(순차)과 after(병렬) 재실행 사이 엔진 출력 편차**이며, 이는 Obs-001(동일 입력/실행 편차)의 발현이다.
- 판정: **Unexpected Change, 단 CHG-001 원인 아님** → Side Effect로 분리(§4).

## 4. Side Effect (관측만 — 해결·Analysis 없음)
- 관측: 위 10 profile에서 재실행 간 applicable_count가 낮은값→높은값으로 변동. before_clean은 순차, after는 병렬(워커6). 값 자체는 각 실행 2회 비교에서 결정적(워커6 결정성 PASS)이었으나, 순차 대비 병렬에서 높은값이 관측됨.
- 이는 이미 등록된 **Obs-001** 범위. 본 WO에서 해결·분석하지 않는다.
- CHG-001과의 관계: CHG-001은 Engine 무수정이므로 이 변동의 원인이 아니다. 10개 모두 after에서 full_count==applicable_count로 집계는 정상.

## 5. Verification Decision
```text
Obs-003 검증 (엔진 응답 동일 102개 기준)
    ↓
before 집계 = preview(12/7 절단)
after  집계 = full (applicable_count 일치, 112/112)
의무 집합 = 동일 (내용 불변, 전량 노출)
    ↓
Expected Change 확인
    ↓
Obs-003 = SEMANTIC PASS (RESOLVED, 의미 검증됨)
```
- Side Effect(10 profile)는 Obs-001의 발현이며 CHG-001의 부작용이 아님 → OPEN 유지, 후속 Obs-001 WO에서 다룸.
- 최종 판정 근거: 숫자가 아니라 의무 집합을 읽어 '내용은 동일, 집계 범위만 preview→full로 정상 확장'을 확인한 것.

## 상태
```text
Obs-003 : RESOLVED (Semantic Verified)
Obs-001 : OPEN (Side Effect로 재확인됨 — 다음 Analysis 대상)
Obs-002 : OPEN
Obs-004 : OPEN
Obs-005 : OPEN
Obs-006 : OPEN
```
