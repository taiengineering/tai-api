---
wo: WO-E2E-LEG-001
class: records
type: verification
scope: canonical
project: test-universe
title: LEG Runtime Semantic E2E
version: 1
status: active
owner: taiwang
---

# LEG RUNTIME SEMANTIC E2E — WO-E2E-LEG-001

> 고정된 LEG Runtime 파이프라인에서 실제 진단을 실행하여 production_semantic_repository의 Semantic 자산(337 atom)이 최종 진단 결과까지 전달되는지 E2E 검증. **LEG E2E 본선. 실행 증명 단계.** Runtime/DB/Railway 재조사·코드 수정 0.

## 최종 판정: SEMANTIC E2E PASS

## 실행 (실측)
```text
POST https://leg-runtime-production.up.railway.app/rtm/evaluate
입력: {"facility": {"is_multi_use": true}}
응답: status OK · http_status 200 · trace_id rtm-27a5328577cd · obligation_count 2
```

## STEP 1 — Test Case Selection
```text
atom_id      : 0415c8d6-c13f-5349-96af-efbafa73578e
mapped_field : is_multi_use
law          : 실내공기질법 제5조
clause       : 938bc6cf-8643-4061-a5dc-27e1bb6f00b2
evidence     : "다중이용시설의 소유자등은..." (DB 완비: field·clause·evidence)
Expected     : is_multi_use=true → atom 0415c8d6 발화 → 실내공기질법 제5조
```

## STEP 2 — Runtime Execute → 성공
```text
provenance:
  release_version  SEMREPO-RC1-2026.07.20            = 코드 EXPECTED_RELEASE
  freeze_signature 15cd17e871b6885d34214c84a58adf47  = 코드 EXPECTED_FREEZE
  repository_size  337                                = 코드 EXPECTED_ROW_COUNT
→ LEG Runtime이 production_semantic_repository(337, RC1) 실제 로드·실행.
contract: active_fields [is_multi_use] · accepted_count 1 · invalid/unknown 0
```

## STEP 3 — Semantic Consumption
```text
obligations[0]:
  atom_id 0415c8d6 (STEP1 선택 atom 일치) · mapped_field is_multi_use · 실내공기질법 5조
  evidence "다중이용시설의 소유자등은..." (DB 원문 일치)
→ semantic_clause·atom·mapped_field·evidence 전부 실제 소비됨.
```

## STEP 4 — Evidence Trace (손실 0)
```text
Repository Atom 0415c8d6 → Semantic Clause 938bc6cf → Compiler(accepted) →
Result Obligation(APPLICABLE, triggered_by [is_multi_use]) → Evidence(DB 원문 전달)
→ 입력→결과 사이 atom_id·mapped_field·evidence 손실 0. Trace 연속.
```

## STEP 5 — Before / After
```text
Expected : 실내공기질법 관련 의무, atom 0415c8d6 포함
Actual   : obligations 2건
  [0] 실내공기질법 제5조  (0415c8d6) — Expected 일치
  [1] 실내공기질법 제12조 (5152a757) — 동일 is_multi_use 필드 추가 발화(정상)
→ Expected 충족.
```

## STEP 6 — Semantic Verification: PASS
```text
Semantic Preservation : PASS (atom·field·law·article·evidence 보존)
Semantic Loss         : NONE
Evidence Consistency  : PASS (DB evidence == 응답 evidence)
```

## STEP 7 — Regression: STABLE
```text
동일 입력 2회 실행 → obligation_count 2, atom {0415c8d6, 5152a757}, 5조·12조 불변.
trace_id만 요청별 상이(정상). 판정 결과 불변.
```

## 결론
```text
337 atom이 실제 결과로 이어짐을 실행으로 증명:
  입력(is_multi_use=true) → /rtm/evaluate(RC1 337 로드) → atom 0415c8d6 발화
  → 실내공기질법 제5조 의무 + evidence 원문 전달.
Semantic이 입력에서 결과까지 손실 없이 보존됨. LEG E2E 본선 PASS.
```

## Exit Criteria 점검
```text
[v] Runtime 실행 완료 (200 OK, trace_id)
[v] Semantic Repository 소비 확인 (provenance 337/RC1, atom 발화)
[v] Compiler Output 확인 (contract accepted, obligations 생성)
[v] Evidence Trace 확인 (atom→clause→obligation→evidence 손실 0)
[v] Before/After 완료 (Expected 제5조 충족)
[v] Regression 완료 (STABLE)
[v] Semantic PASS/FAIL 판정 (PASS)
```

## 산출물
```text
REPORT_leg-e2e-execution_v1.md · REPORT_semantic-trace_v1.md
REPORT_before-after_v1.md · REPORT_regression_v1.md
```

## 상태
```text
LEG E2E 본선 = PASS (실행 증명 완료)
```
