# 작업지시서: Layer 4→5 연결 표준화 (obligations 형태 일치)

> 목적: 검증엔진이 주는 obligations 형태와 정제(Transform)가 받는 형태를 같게.
> 범위: TAI 내부 출력 형태 표준화. Check 엔진 계약 변환은 범위 밖(나중에 어댑터).
> 원칙: 엔진 평가 로직 수정 금지. 형태만 일치.
> 브랜치: feature/layer45-obligations-standardization

## 중요: Check 엔진과의 관계 (지금 건드리지 않음)

```
Layer 4→5의 evidence는 나중에 Check 엔진 입력(Claim/Evidence/Chain)이 됨.
그러나 지금은 Check 연결을 하지 않는다.
지금은 TAI 내부에서 obligations 형태만 일치시킨다.
Check 계약(federation-contracts schemas/check) 변환은
별도 어댑터 작업으로 분리 (메모리에 기록됨).

→ 지금 evidence를 만들 때 Check 계약 형태를 억지로 맞추려 하지 말 것.
→ TAI 내부 표준(LAYER_STANDARD.md 표준4)만 따른다.
```

## 문제 (LAYER_PROBLEMS.md에서 확인됨)

```
검증엔진 출력 (_compiler_result_to_step1_format):
  obligations = [
    {category: "inspection", label: "점검", items: [rule_row, ...]},
    {category: "appointment", label: "선임", items: [...]},
    ...
  ]
  → wrapper 구조 (category + items[])

정제 (diagnosis_transform._extract_obligations):
  wrapper를 flat obligation 1건으로 처리
  → title="의무사항", evidence=[], items[] 무시
  → 내부 rule_row들이 전부 버려짐

→ 주는 형태(wrapper)와 받는 처리(flat 1건)가 안 맞음
```

## 표준 (LAYER_STANDARD.md 표준4)

```
Transform이 obligations wrapper의 items[]를 순회하여
각 item을 개별 obligation으로 전개:

  for group in obligations:
    for item in group.items:
      obligation = {
        title: item.obligation_summary 또는 item.title,
        law_name: item.law_name,
        rule_type: item.rule_type,
        category: group.category,
        evidence: item.evidence (text 배열, 없으면 [])
      }
```

## 작업

### 1. Transform의 obligations 처리 확인

파일: routers/diagnosis_transform.py 또는 services/diagnosis_transform.py
       → _extract_obligations

```
현재 동작 확인:
  - obligations를 어떻게 읽는가?
  - wrapper {category, label, items}를 flat 1건으로 처리하는 부분
  - items[]가 무시되는 지점
```

### 2. items[] 순회로 수정

```
_extract_obligations 수정:
  obligations의 각 group에 대해
    group.items[]를 순회
    각 item을 개별 obligation으로 전개
  
  필드 매핑:
    title ← item.obligation_summary or item.title
    law_name ← item.law_name (PR #107로 이미 채워짐)
    rule_type ← item.rule_type
    category ← group.category
    evidence ← item.evidence (있으면 text 배열, 없으면 [])

주의:
  - PR #107로 rules_table의 law_name이 이미 채워져 있음
  - obligations items의 law_name도 같은 출처인지 확인
  - evidence는 TAI 내부 형태 (Check 계약 아님)
```

### 3. evidence 필드 표준 (TAI 내부)

```
evidence는 text 배열로 표준화:
  evidence: ["산업안전보건법 제17조", ...] 또는 []

주의: 이것은 TAI 내부 표시용.
      Check 엔진의 Evidence 객체(evidence_ref, attached 등)와 다름.
      Check 연결 시 어댑터가 이 내부 evidence를
      Check 계약으로 변환할 것 (지금 범위 밖).
```

## 검증 (형태 일치, 평가 무관)

```
1. Transform 출력의 obligations가 flat list인가?
   → 이전: [{category, items:[...]}] wrapper
   → 이후: [{title, law_name, category, evidence}, ...] flat

2. 각 obligation에 내용이 채워지는가?
   → 이전: title="의무사항", evidence=[]
   → 이후: title=실제 의무명, law_name 채워짐

3. items[]가 더 이상 버려지지 않는가?
   → wrapper 안 rule_row 개수 = flat obligation 개수

4. MATCH/applicable 건수 변화 없음 (형태만, 평가 안 바꿈)

5. 에러 없이 완료
```

## 주의

- 엔진 평가 로직(facility_applicability_eval.py) 수정 금지
- Check 엔진 계약을 지금 맞추려 하지 말 것 (별도 어댑터)
- evidence는 TAI 내부 형태로만 (text 배열)
- applicable 건수 회귀 없어야 함 (형태 작업)
- Draft PR, merge 금지
- Supabase MCP 사용 가능 (project_id: vwlahtguyggrhvslabax)

## 이 작업이 표준화하는 것

```
Layer 4→5 연결:
  주는 형태(obligations wrapper)를
  받는 쪽(Transform)이 items[] 전개하도록
  → 의무 상세가 버려지지 않고 출력됨
  → "연결됐고 형태도 맞음"

다음(Layer 5→6): _partial_from_full / _build_partial 통합
그 다음(별도): Check 엔진 연결 어댑터
```
