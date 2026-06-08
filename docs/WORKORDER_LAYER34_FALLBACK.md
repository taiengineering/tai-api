# 작업지시서: Layer 3→4 연결 표준화 (fallback 형태 일치)

> 목적: 법령엔진이 주는 형태와 검증엔진이 받는 형태를 같게 만든다.
> 범위: 연결 표준화. 값 정밀도(단위)는 범위 밖.
> 원칙: 엔진 평가 로직 수정 금지. fallback이 빠뜨린 필드를 채울 뿐.
> 브랜치: feature/layer34-fallback-standardization

## 문제: 주는 형태 ≠ 받는 형태

```
법령엔진 출력 (compiler_core_svc / anonymous_factory_service):
  task_candidate 있을 때 (기존 29개 factory):
    rule_row = { law_name, rule_type, obligation_family, ... } 채워짐
  task_candidate 없을 때 (익명 temp factory — 항상 이 경우):
    fallback rule_row = { law_name="", rule_type="", ... } 비어있음

검증엔진 기대 (rules_table 표준):
  rule_row = { law_name 필수, rule_type 필수, bucket 필수 }

→ 익명 진단은 fallback을 타는데, 받는 쪽 표준과 형태가 안 맞음
→ "연결은 됐으나 형태 불일치"
```

## 표준 (LAYER_STANDARD.md 표준3)

```
task_candidate가 없으면:
  facility_applicability의 draft_id로 executable_draft 조회
  → law_name, obligation_type, title 가져와 rule_row에 채움
  → 받는 쪽(rules_table) 형태와 일치시킴
```

## 작업

### 1. fallback 경로 확인

파일: services/anonymous_factory_service.py → _compiler_result_to_step1_format
       또는 services/compiler_core_svc.py → fetch_compiler_candidates

```
현재 fallback이 어디서 일어나는지 확인:
  - task_candidates가 빈 배열일 때
  - applicability_candidates로 rules_table을 만드는 부분
  - 그 rule_row에 law_name, rule_type이 비어있는지 확인
```

### 2. executable_draft 조회로 형태 채우기

```
fallback rule_row를 만들 때:
  draft_id로 executable_draft 조회 (배치 조회, N+1 방지)
  → law_name ← executable_draft.law_name (또는 관련 컬럼)
  → rule_type ← executable_draft.obligation_type → bucket 매핑
  → description ← executable_draft.title

조회는 READ만. executable_draft 수정 금지.
배치로 한 번에 조회 (draft_id IN [...]).
```

### 3. bucket 매핑 표준화

```
rule_type → bucket 매핑을 표준으로:
  task 경로와 fallback 경로가 같은 매핑을 쓰도록
  _TASK_TYPE_TO_BUCKET (이미 있음)을 fallback에도 적용
  → 두 경로의 bucket 분류가 일치
```

## 검증 (형태 일치 확인, 값 정밀도 아님)

```
1. 익명 BUILDING 진단:
   rules_table의 각 row에 law_name이 채워지는가? (이전: 빈값)
   rule_type, bucket이 채워지는가?

2. 형태 일관성:
   task 경로(기존 factory)와 fallback 경로(익명)의
   rule_row 필드 구조가 같은가?

3. 회귀:
   MATCH 건수는 변하지 않아야 함 (형태만 채우는 것, 평가 안 바꿈)
   BUILDING 114, CONSTRUCTION 114 유지

4. 에러 없이 완료
```

## 주의

- 엔진 평가 로직(facility_applicability_eval.py) 수정 금지
- executable_draft 등 데이터 수정 금지 (READ만)
- MATCH 건수가 변하면 안 됨 (형태만 채우는 작업)
- 단위 환산은 범위 밖 (건드리지 말 것)
- N+1 쿼리 방지 (draft_id 배치 조회)
- Draft PR, merge 금지
- Supabase MCP 사용 가능 (project_id: vwlahtguyggrhvslabax)

## 이 작업이 표준화하는 것

```
Layer 3→4 연결:
  주는 형태(fallback rule_row)를
  받는 형태(rules_table 표준)와 일치시킴
  → 익명 진단도 law_name/rule_type/bucket이 채워진 채로 전달
  → "연결됐고 형태도 맞음"
```
