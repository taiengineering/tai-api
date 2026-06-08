# 작업지시서: STEP A — normalizer를 소비자 경로에 연결

> 목적: input_normalizer를 소비자 진단 경로(legal_context 앞)에 연결하여
>       단위 문자열 입력("800kVA", "78억")이 파이프라인을 깨뜨리지 않게 한다.
> 성격: 안정성 확보. 관찰 실험(B)에서 확인된 wiring gap 해소.
> 원칙: 엔진 평가 로직, draft_slot 수정 금지.
> 브랜치: feature/layer-standardization-20260608

## 배경 (관찰 B에서 확인됨)

- normalize_input은 현재 v510 경로만 연결됨
- 소비자 경로(create_temp_factory / legal_context)에는 미연결
- legal_context는 float(inp.get("electric_capacity") or 0)로 직접 파싱
  → "800kVA" 문자열이 오면 ValueError로 깨짐
- legal_context는 이미 자체 환산 일부 보유 (contract_amount_eok * 1억)
  → normalizer는 "환산"이 아니라 "단위 문자열 방어"가 주 역할

## 작업

### A-1. 소비자 진단 진입점에서 normalize_input 호출

대상 경로 (소비자):
```
routers/anonymous_diagnosis.py → _build_step1_body / _merge_body_input
services/diagnosis_integrated_svc.py → run_step1_via_compiler
services/anonymous_factory_service.py → run_anonymous_diagnosis (create_temp_factory 앞)
```

연결 위치:
```
소비자 입력(body) 
  → normalize_input(body)   ← 추가 (단위 문자열 정리)
  → create_temp_factory / legal_context
  → 엔진
```

### A-2. normalize_input에 STEP B 단위 환산 포함 여부

STEP B 관찰 결과:
- 입력 환산만으로 MATCH 증가는 없음 (draft_slot도 환산 필요)
- 그러나 "단위 문자열 방어"는 효과 있음

따라서 STEP A에서는:
- normalize_input의 기존 기능(별칭, 타입, 빈값, 단위 문자 제거) 연결
- STEP B의 단위 환산(_convert_to_standard_unit)은 포함하되,
  draft_slot 미환산이므로 MATCH 기대 안 함 (방어 목적)

### A-3. 검증

```
1. "800kVA" 전기용량 입력 → 깨지지 않고 800으로 처리되는가?
2. "78억" 금액 입력 → 깨지지 않고 처리되는가?
3. 정상 숫자 입력(기존 동작) → MATCH 건수 변화 없는가? (회귀 없음)
4. BUILDING/INDUSTRIAL/CONSTRUCTION 각 정상 완료
```

통과 기준:
- 단위 문자열 입력이 더 이상 파이프라인을 깨지 않음
- 정상 숫자 입력은 기존과 동일 결과 (회귀 없음)
- 에러 없이 완료

## 주의

- 엔진 평가 로직(facility_applicability_eval.py) 수정 금지
- draft_slot 데이터 수정 금지
- normalize_input을 legal_context "앞"에 배치 (순서 중요)
- 회귀 방지: 정상 숫자 입력 결과가 변하면 안 됨
- Draft PR, merge 금지
- Supabase MCP 사용 가능 (project_id: vwlahtguyggrhvslabax)

## STEP B 관찰 기록 (수정 안 함, 기록만)

```
관찰 결과 (입력부만 단위 환산):
  - 단위 문자열 입력 방어: 효과 있음 (→ STEP A로 연결)
  - MATCH 증가: 없음
    이유: draft_slot이 억원/만원/kW/W 혼재
          입력만 원/kW로 맞춰도 엔진이 UNIT_MISMATCH → AMBIGUOUS
  - monetary_value, voltage_level, storage_capacity 조건은
    draft_slot 단위 정규화가 선행되어야 MATCH 가능

  결론: 단위 정합 매칭(B)은 draft_slot 측 정규화 필요 → 엔진/배치 영역
        별도 과제로 분리. 이번 범위 밖.
```
