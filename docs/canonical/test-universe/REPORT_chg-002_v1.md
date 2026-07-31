---
wo: WO-CHG-002
class: records
type: report
scope: canonical
project: test-universe
title: Resolve Obs-001 (Baseline Replacement)
version: 1
status: active
owner: taiwang
---

# REPORT — WO-CHG-002 Resolve Obs-001 (기준선 교체)

> Obs-001 하나만 해결. CHG의 첫 단계는 구현이 아니라 Root Cause 전제의 최종 확인. Engine/Rule/Query 코드 무수정.
> Input: Observation Inventory(6be576e4), Priority(c78ccf7c), Analysis(91273b6f).

## 1. Scope
- 대상: Obs-001(동일 입력, 다른 출력).
- 해결 형태: 코드 수정이 아니라 **측정 기준선(before_clean) 교체**.
- 불변: Engine, Rule, Query 코드.

## 2. STEP 1 — Root Cause 전제 최종 확인 (구현 아님)
현재 main 엔진에서 편차 10개 + 대조 3개를 동일 조건(순차 워커1·180s)으로 재생성해 old_before / after / new_before 3자 비교.

| 판정 | 결과 |
|---|---|
| new==after & !=old (오염 확정 지지) | **10 / 10** (편차 profile 전부) |
| new==old (오염 재현 → RootCause 재검토) | 0 |
| 대조군(원래 편차 없음) | 3개 세 기준 동일 |

- PF-0020/0023/0027: old 102 → after 107 = new 107. construction 6개: old 23/19 → 24/20 = new. special PF-0038: 6 → 7 = new.
- 결론: 현재 main에서 순차 재생성해도 **오염 미재현**. Root Cause(before_clean이 .order 과도기 배포 산물로 오염)가 CHG 전제로 **성립 확정**.

## 3. STEP 2 — 기준선 교체 + Gate
- 새 기준선 후보 = 안정 엔진(main 재배포 후, PR#122 포함) 산출 `after_obs003`(full 집계, 112).
- Baseline Gate: `after_obs003`(run1) vs 신규 run2 → **changed 0/112, 112/112 정상, missing 0 → PASS**.
- Semantic: 새 기준선 full_count==applicable_count **112/112**. 편차 10개 전부 안정 높은값(PF-0020=107, PF-0030=24, PF-0034=20, PF-0038=7).

## 4. 기준선 교체 결과 (측정 산출물)
```text
before_clean                          = 안정 엔진 산물 (112, 새 정식 기준선)
before_clean2                         = 검증 사본 (112)
before_clean_DEPRECATED_ordertransition = 구 오염 기준선 (112, 보존)
```

## 5. Verification
- Root Cause 전제 확인: PASS (new==after!=old 10/10).
- Baseline Gate: PASS (changed 0/112).
- Semantic: PASS (full==applicable 112/112, 편차 profile 안정).
- Engine/Rule/Query 코드 수정: 0.

## 6. Conclusion
- Obs-001 = **RESOLVED (기준선 교체)**. 현재 엔진은 해당 편차를 재현하지 않으며(순차·병렬 무관 결정적), 오염 기준선을 안정 엔진 산물로 교체함.
- 이 해결은 코드 수정이 아니라 측정 기준선 교체였다(Root Cause가 엔진이 아니라 기준선이었으므로).

## 7. 파급 (기록만 — 본 WO 판단 아님)
- 기존 before_clean 기반으로 기술된 Obs-004/005/006의 관측·범위는 **오염 기준선 위**였다. 새 기준선(안정)에서 재확인이 필요할 수 있다. 각 Observation의 후속 WO에서 다룬다.
- Obs-002(중복)도 새 기준선에서 재확인 대상.

## 상태
```text
Obs-003 : RESOLVED (Semantic Verified)
Obs-001 : RESOLVED (Baseline Replacement)
Obs-002 : OPEN (새 기준선 재확인 대상)
Obs-004 : OPEN (새 기준선 재확인 대상)
Obs-005 : OPEN (새 기준선 재확인 대상)
Obs-006 : OPEN (새 기준선 재확인 대상)
```
