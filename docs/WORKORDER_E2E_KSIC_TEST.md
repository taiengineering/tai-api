# 작업지시서: KSIC 실입력 E2E 테스트 (사용자 입력값 반영 검증)

> 목적: 사용자가 입력한 KSIC 코드가 진단 결과 끝까지 반영되는지 확인.
> 성격: 검증. 코드 수정 없음. 실제 API + DB 추적.
> 배경: 이전 E2E는 scale/workers 위주. KSIC 등 실제 사용자 입력값의
>       엔드투엔드 반영은 미검증.

## 핵심 질문

```
사용자가 KSIC 코드(예: C26 반도체, C20 화학)를 입력하면
→ 그 값이 factory에 저장되는가?
→ 엔진 평가(facility_applicability)에 반영되는가?
→ 결과(rules_table)가 KSIC에 따라 달라지는가?

또는: KSIC는 저장만 되고 평가에 안 쓰이는가?
(process_type binding이 fac_col=None이면 MISSING_DATA)
```

## 사전 확인 (DB)

```sql
-- 1. ksic_process_map이 진단 경로에서 쓰이는가?
--    factory_process 생성 시 ksic로 공정을 매핑하는지
SELECT * FROM ksic_process_map LIMIT 5;

-- 2. draft_slot의 process_type/facility_type이 ksic와 연결되는가?
SELECT section, binding_field, COUNT(*)
FROM draft_slot
WHERE binding_field IN ('process_type','facility_type')
GROUP BY section, binding_field;

-- 3. FIELD_MAP에서 ksic_code가 어디로 매핑되는가?
--    (facility_applicability_eval.py 확인 — process_type? facility_type?)
```

## E2E 테스트: KSIC 다른 값으로 결과 비교

실제 API 스키마 확인 후(site_kind + scale + workers + ksic 필드명),
같은 규모에 KSIC만 다르게 하여 결과 차이를 본다.

```
테스트 A: 제조업 + KSIC C26 (반도체)
  site_kind=manufacturing, scale=large, workers=300, ksic=C26 (실제 필드명 확인)

테스트 B: 제조업 + KSIC C20 (화학물질)
  동일 규모, ksic=C20

테스트 C: 제조업 + KSIC 미입력
  동일 규모, ksic 없음

비교:
  A vs B vs C의 applicable_count, rules_table 차이
  → KSIC가 결과를 바꾸는가?
  → 화학(C20)은 유해물질 관련 법령이 더 나오는가?
```

## 입력 스키마 먼저 확인

```
routers/anonymous_diagnosis.py의 AnonymousDiagnosisCreate 스키마에서
KSIC를 받는 정확한 필드명 확인:
  - ksic? ksic_code? ksic_major? industry_code?
  - scale은 어떤 값? (small/medium/large?)
  - workers는 정수?

→ 정확한 필드명으로 curl 작성
```

## DB 추적 (입력값 반영 확인)

```sql
-- 방금 생성된 진단의 factory에 ksic가 저장됐는지
SELECT 
  f.id, f.sector, f.ksic_code, f.employee_count,
  adr.public_token, adr.created_at
FROM anonymous_diagnosis_results adr
JOIN factories f ON f.id = (adr.input_data->>'factory_id')::uuid
WHERE adr.created_at > now() - interval '10 minutes'
ORDER BY adr.created_at DESC;

-- 주의: 익명 진단은 temp factory가 cleanup되므로
-- factory가 이미 삭제됐을 수 있음 → input_data에서 ksic 확인
SELECT 
  public_token,
  input_data->>'ksic' as ksic_input,
  input_data->>'ksic_code' as ksic_code_input,
  full_result->>'applicable_count' as applicable,
  jsonb_array_length(full_result->'rules_table') as rules_count
FROM anonymous_diagnosis_results
WHERE created_at > now() - interval '10 minutes'
ORDER BY created_at DESC;
```

## 판정 기준

```
Case 1: KSIC가 결과를 바꿈
  → A/B/C의 rules_count 또는 내용이 다름
  → KSIC 입력이 엔드투엔드 반영됨 ✅

Case 2: KSIC가 결과를 안 바꿈
  → A/B/C 결과 동일
  → 원인 분석 필요:
    a) ksic가 factory에 저장 안 됨 (입력 유실)
    b) 저장되나 FIELD_MAP에 없어 평가 미반영
    c) process_type binding이 fac_col=None → MISSING_DATA
  → 어느 경우인지 기록 (수정은 별도 판단)
```

## 산출물

docs/E2E_KSIC_TEST_20260609.md
```
- 입력 스키마 (정확한 KSIC 필드명)
- A/B/C 결과 비교표
- KSIC 반영 여부 판정 (Case 1/2)
- Case 2면 원인 (a/b/c)
```

## 주의

- 코드 수정 금지 (검증만)
- KSIC가 평가에 안 쓰여도 그대로 기록 (사실 확인)
- 익명 temp factory cleanup 고려 (factory 삭제됐을 수 있음)
- Supabase MCP project_id: vwlahtguyggrhvslabax
