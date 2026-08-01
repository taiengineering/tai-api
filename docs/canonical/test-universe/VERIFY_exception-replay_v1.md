---
wo: WO-VERIFY-001
class: records
type: verification
scope: canonical
project: test-universe
title: Exception Replay Verification
version: 1
status: active
owner: taiwang
---

# EXCEPTION REPLAY VERIFICATION (FROZEN) — WO-VERIFY-001

> WO-MAPPING-004 Exception Taxonomy가 기존 393을 실제로 설명하는지 독립 검증. 번역표·sector 변경·DB 수정 없음.
> Input: 기존 393 매핑(정답지), Exception Taxonomy(3a3c4ab5).

## 판정: KEEP WITH LIMITATION — 구조 재현, 대상 목록 정밀도 부족

## STEP 1-2 — Replay + Explainability
Replay 순서: EX-01(대상→SPECIAL) → EX-02(MULTI) → 나머지.
```text
설명 가능 : 230 (58.5%)
  EX-02 MULTI 정합       : 147
  EX-01 대상→SPECIAL 정합 :  83
부분 설명 :   0
설명 불가 : 163 (41.5%)
  어휘규칙 영역(EX 아님)   : 135
  EX-01 오탐(과매칭)       :  28
```

## STEP 3 — Conflict (설명 불가 163 분류)
```text
예외 부족(어휘규칙 영역, EX 아님) : 135  ← 정상(단일 sector, 예외 아님)
EX 오탐(EX-01 키워드 과매칭)      :  28  ← 결함
Replay 오류                     :   0
기타                            :   0
```
- **EX 오탐 28의 원인 (대상 목록이 거침):**
  - 전기 22: "재활용"·"전기공사"·"전기공급"에 부분매칭(전기설비 SPECIAL과 무관, 실제는 CONSTRUCTION/BUILDING).
  - 재활 3: "재활용"(건설폐기물)에 오매칭.
  - 어린이 3: 어린이놀이시설은 실제 {BUILDING,INDUSTRIAL}(SPECIAL 아님).

## STEP 4 — Coverage
```text
Replay 성공                : 230/393 = 58.5%
설명 불가(어휘규칙 영역, 정상): 135/393 = 34.4%
EX 오탐(대상목록 결함)       :  28/393 =  7.1%
```
- 예외 대상(SPECIAL 83 + MULTI 147 = 230)만 놓고 보면 Exception 구조가 정합. 135는 예외가 아닌 어휘규칙 영역이므로 Exception 밖(설명 안 되는 게 정상).

## STEP 5 — Independent Review
- **Exception만으로 393 설명 가능한가? 아니오 — 그리고 그게 정상.** Exception은 예외(SPECIAL·MULTI)만 설명하는 체계. 어휘규칙 영역 135(건축물→BUILDING 등 단일 sector)는 예외가 아니므로 Exception 밖.
- **진짜 문제 = EX 오탐 28.** EX-01 대상 목록(특히 "전기")이 과매칭. 짧은 키워드가 무관 법령("재활용"·"전기공사")까지 잡음. 목록 정제(단어 경계·맥락·불용어 제외) 필요.
- 검증 결론: **Exception 구조(대상 우선 → MULTI)는 재현됨**(예외 230건 정합), **단 대상 목록의 정밀도가 부족**(28 오탐, 7.1%).

## STEP 6 — Independent Audit
```text
Replay        : PASS (393 전량, 순서 EX-01→EX-02→나머지 적용)
Coverage      : PASS (230 성공 / 135 어휘영역 / 28 오탐, 합 393)
Conflict      : PASS (오탐 28 원인 규명 — 전기22·재활3·어린이3)
Explainability: PASS (설명가능 230·불가 163 분류)
특기: 설명력 58.5%는 낮아 보이나, 135는 예외 아닌 어휘영역(Exception 밖). 예외 대상만 보면 재현 양호. 결함은 대상목록 조악함(28).
```

## STEP 7 — Freeze
```text
Replay Report   : EX-02 147·EX-01 83 정합 / 135 어휘영역 / 28 오탐
Coverage Report : 성공 58.5%·어휘영역 34.4%·오탐 7.1%
Conflict Matrix : EX 오탐 28 (전기22·재활3·어린이3) — 대상목록 과매칭
Review          : KEEP WITH LIMITATION (구조 재현, 목록 정밀도 부족)
Audit           : PASS
```

## 결론
- **Exception 구조는 유효** — 대상 우선(→SPECIAL) + MULTI 허용이 예외 230건을 정합하게 설명. WO-MAPPING-004의 근본 예외 2종이 정답지에서 재현됨.
- **한계 = 대상 목록의 조악함** — "전기"·"재활" 같은 짧은 키워드가 과매칭(28 오탐, 7.1%). 이는 Exception 구조의 결함이 아니라 **대상 목록 정의의 정밀도 문제**. 목록을 정제해야(단어 경계, "전기설비 관리자" 같은 맥락 한정, "재활용"·"전기공사" 제외) 오탐 제거 가능.
- **번역표 진입 판단:** Exception 구조는 재현되나, 번역표에 넣을 EX-01 대상 목록은 아직 미완성(과매칭 상태). 목록 정제가 선행돼야 함. 어휘규칙 영역 135는 별도(번역표 본체).
- 이 검증이 없었다면 조악한 "전기→SPECIAL" 규칙이 번역표에 들어가 28건(7.1%)을 오분류했을 것.

## Exit Criteria 점검
```text
[v] Replay 완료 (393)
[v] Explainability 완료 (230/0/163)
[v] Conflict 완료 (135 어휘영역·28 오탐)
[v] Coverage 완료 (58.5/34.4/7.1)
[v] Review PASS
[v] Audit PASS
[v] Freeze 완료
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑬ Evidence Reconstruction    ✓ WO-EVIDENCE-001
⑭ Exception Taxonomy         ✓ WO-MAPPING-004
⑮ Exception Replay Verify    ✓ WO-VERIFY-001 (구조 재현, 대상목록 정밀도 부족 28) ← 현재
⑯ 대상 목록 정제             ← 다음 (EX-01 목록 정밀화, 과매칭 제거)
⑰ 번역표 수립                ← 그 후
⑱ DB 반영 CHG + Verify       ← WO-CHG-005
```
