# 작업지시서: 입력부 단위 환산 — 관찰 실험

> 목적: 소비자 입력부에서만 단위를 표준 단위로 환산하고,
>       엔진(facility_applicability)이 어떻게 반응하는지 관찰한다.
> 성격: 실험. 한쪽(입력)만 환산하고 결과를 본다.
> 원칙: 엔진 평가 로직, draft_slot 데이터는 건드리지 않는다.
> 브랜치: feature/layer-standardization-20260608 (STEP 1 작업과 동일 브랜치)

## 배경

- draft_slot(법령 측)에 단위가 섞여 있음:
  monetary_value: 억원/만원, voltage_level: V/kV/kVA, power_capacity: kW/W
- input_normalizer.py는 단위를 "떼기만" 하고 환산은 안 함
- 엔진은 단위 위험 필드를 AMBIGUOUS로 회피
- 이 실험: 입력부만 표준 단위로 환산 → 엔진 반응 관찰

## 작업: input_normalizer.py에 단위 환산 추가

추가할 환산 (입력값 → 표준 단위):

```
전력 (→ kW):
  "kW" → 그대로 / "W"(kW 아님) → /1000 / "kVA" → 그대로(역률 1.0 근사, 주석)
금액 (→ 원):
  "억" → *100000000 / "만원" → *10000 / "원" → 그대로
  contract_amount_eok 키 → *100000000
면적 (→ ㎡): 이미 처리됨
거리 (→ m): "mm"→/1000, "cm"→/100
```

구현:
- _to_number 호출 전 원본 문자열에서 단위 감지
- 단위별 배율 곱한 후 표준 단위 숫자로 변환
- 단위 문자 없으면(이미 숫자) 환산 안 함 (기존 동작 유지, 추정 금지)
- 헬퍼 _convert_to_standard_unit(key, raw_value) 추가
- 기존 _strip_units, _to_number 동작 유지

## 관찰 (검증 아니라 관찰)

실험이므로 "무엇이 변하는지" 기록:

```
1. CONSTRUCTION 78억 입력
   환산 전: construction_amount = 78
   환산 후: construction_amount = 7800000000
   → monetary_value 조건 결과 변하는가? 여전히 AMBIGUOUS인가?
2. 전력 100kW → power_capacity 조건 변화
3. MATCH 건수 비교 (환산 전 vs 후) — 3개 섹터
```

핵심 관찰 질문:
```
입력부만 환산했을 때:
  - 엔진이 더 많이 MATCH? (개선)
  - 여전히 AMBIGUOUS? (draft_slot도 환산 필요)
  - NOT_MATCHED 늘어남? (단위 반대로 틀어짐)
```

## 보고

```
환산 전후 비교표: 필드 | 입력 | 환산전 | 환산후 | 엔진결과
엔진 반응: monetary_value, power_capacity 조건 / MATCH 건수
결론: 입력부만으로 충분한가? draft_slot도 필요한가?
```

## 주의
- 엔진 평가 로직(facility_applicability_eval.py) 수정 금지
- draft_slot 데이터 수정 금지
- input_normalizer.py만 수정
- 실험이므로 결과 안 좋아도 그대로 보고
- Draft PR, merge 금지
- Supabase MCP 사용 가능 (project_id: vwlahtguyggrhvslabax)
