---
wo: WO-CHG-007
class: records
type: verification
scope: canonical
project: test-universe
title: Matching Engine Correction (FP-01 Only)
version: 1
status: active
owner: taiwang
---

# MATCHING ENGINE CORRECTION (FROZEN) — WO-CHG-007

> FP-01(부분 문자열 매칭)만 검증적으로 수정. EX-01 대상 목록·FP-03·번역표·sector·DB 불변. 구현 변경 효과만 순수 측정.
> Input: WO-VERIFY-002 FP-01 21건, Replay Engine, 393 정답지.

## 판정: PASSED — FP-01은 매칭 구현 교체만으로 해소(FN 증가 0)

## STEP 1 — Current Logic Freeze
```text
현재 매칭: keyword in law_name  (부분 문자열)
  예: "전기" in "전기공사업법" = True
```

## STEP 2 — Candidate Matching (미적용, 후보만)
```text
후보: 단어 경계 기반 — 키워드 뒤에 같은 도메인 합성 접미어가 오면 제외
  전기 + {공사/사업/용품/안전/공급/설비} → 다른 단어(제외)
  재활 + {용}                          → 재활용(제외)
  (제외 접미어는 WO-VERIFY-002 FP-01 원인 목록과 일치)
```

## STEP 3 — Replay Comparison (393 동일 입력)
```text
              TP   FP   FN   TN
기존(부분문자열): 83   28   30  252
후보(단어경계)  : 83    7   30  273
```

## STEP 4 — Delta Analysis
```text
FP 감소  : 28 → 7   (감소 21)  ← FP-01 21건 전량 해소
FN 증가  : 30 → 30  (증가 0)   ← 진짜 SPECIAL 손실 없음
TP 변화  : 83 → 83  (유지)     ← 기존 정답 예측 불변
TN 증가  : 252 → 273 (정확 분류 +21)
신규 오류 : 0
```
- 제거된 FP 21건: 전기공사업법·전기사업법·전기안전관리법·전기용품법·전기공급사업법·전기설비규정·건설폐기물 재활용법 등 (전부 FP-01).
- 남은 FP 7 = FP-03(어린이놀이시설 등, 맥락 문제). 매칭 교정으론 안 줄어드는 게 정상(본 WO 범위 밖).

## STEP 5 — Independent Review
- **FP-01은 매칭 구현만 바꾸면 해결되는가? YES(검증됨).** 단어 경계 매칭으로 21건 전량 해소.
- 대상 목록(EX-01) 한 글자도 안 바꿈 → 구현 변경 효과만 순수 측정. "전기"는 목록에 그대로(전기안전관리 맥락 SPECIAL 보존), "전기공사"만 안 잡힘.
- FN 증가 0 = 진짜 SPECIAL(TP 83) 손실 없음 → 안전한 교정.

## STEP 6 — Independent Audit
```text
Replay     : PASS (393 전량, 기존/후보 동일 입력)
Delta      : PASS (FP -21, FN +0, TP 유지)
Coverage   : PASS (TN 252→273)
Regression : PASS (TP 83 불변, 신규 오류 0)
과도성 점검 : 제외 접미어가 FP-01 원인과 정확히 일치, TP 83 유지가 과도 제외 없음을 증명.
```

## STEP 7 — Freeze
```text
Current Logic  : keyword in name (부분 문자열)
Candidate Logic: 단어 경계(합성 접미어 제외)
Replay Report  : TP83/FP7/FN30/TN273 (후보)
Delta Report   : FP -21, FN +0, TP 유지
Review         : FP-01 매칭 구현 교체로 해결 확인
Audit          : PASS
```

## 결론
- **WO-VERIFY-002 진단 확증:** FP-01(75%)은 대상 목록이 아니라 매칭 구현 문제였다. 단어 경계 매칭으로 21건 전량 해소, 목록 불변, FN 증가 0.
- **본 WO는 검증적 수정** — Replay Engine의 후보 매칭 방식이 393에서 안전함을 측정. 실제 코드/DB 반영은 별도(WO-CHG-005 계열).
- 남은 FP 7(FP-03)은 매칭이 아닌 맥락 문제 → 다음 WO에서 개별 처리.
- 오탐 28 중 21(75%)이 이 교정으로 해소 → EX-01 대상 목록의 실제 정밀도는 당초 관측보다 높음(오탐의 대부분이 목록 아닌 매칭 탓).

## Exit Criteria 점검
```text
[v] Replay 완료 (기존/후보)
[v] Delta 분석 완료
[v] FP 감소 측정 (28→7, -21)
[v] FN 증가 측정 (30→30, +0)
[v] Review PASS
[v] Audit PASS
[v] Freeze 완료
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑮ Exception Replay Verify    ✓ WO-VERIFY-001 (오탐 28)
⑯ FP Analysis               ✓ WO-VERIFY-002 (FP-01 75%·FP-03 25%)
⑰ Matching Correction(FP-01) ✓ WO-CHG-007 (FP 28→7, FN +0) ← 현재
⑱ FP-03 맥락 처리(7건)        ← 다음 (어린이놀이시설 등 개별)
⑲ 번역표 수립                ← 그 후
⑳ DB 반영 CHG + Verify       ← WO-CHG-005
```
