# 작업지시서: Layer 5→6 출력 표준화 (partial 통합 + source 필드)

> 목적: 출력 함수를 하나로 통합하고, 표준에 source 필드를 포함시킨다.
> 범위: 무료 진단 출력 통합 + source 필드 표준 정의까지.
>       SaaS MANUAL 공정 주입은 다음 단계로 분리 (한 번에 안 함).
> 원칙: 엔진 평가 로직 수정 금지. 형태 통합만.
> 브랜치: feature/layer56-output-standardization

## 배경: source 구분 설계 (DB 구조가 이미 답)

```
factory_id (시설) 아래:
  facility_applicability  ← 법령진단 (엔진 산출)
  factory_process         ← 공정 (source: DB/KCSC/MANUAL, legal_status)

→ 임의 등록(MANUAL)과 진단은 이미 factory_id로 공존
→ "두 개 파이프라인"이 아니라 "하나의 표준 + source 구분"
```

## 문제 (LAYER_PROBLEMS.md P-5-x)

```
_partial_from_full (익명) vs _build_partial (통합):
  같은 full_result라도 다른 필드 반환
  익명: evaluated_at, rules_preview, construction_summary, message 포함
  통합: 없음
  → 같은 진단이 경로에 따라 다른 형태로 출력
```

## 작업 1: 출력 함수 통합

파일: services/anonymous_factory_service.py + 관련

```
_partial_from_full과 _build_partial을 하나로 통합:
  _build_standard_output(full_result) → 표준 출력

  두 경로(익명/통합)가 같은 함수 호출
  표준 필드 (LAYER_STANDARD.md 표준5):
    sector, risk_level, applicable_count, evaluated_at,
    rules_table[], key_obligations[], law_badges[],
    appointment/inspection/action/report_required[],
    construction_summary, engine_version
```

## 작업 2: 표준에 source 필드 포함

```
rules_table의 각 row + key_obligations의 각 item에:
  source: "DIAGNOSIS"   ← 법령진단 결과 (기본값)

무료 진단(익명)은 전부 DIAGNOSIS:
  facility_applicability/task 기반 → source="DIAGNOSIS" 고정

→ 이 단계에서는 source 필드를 표준에 "추가"만 하고
  값은 전부 "DIAGNOSIS"
→ MANUAL 주입은 다음 단계 (SaaS 전용)
```

## 작업 3: 검증

```
1. 익명 진단과 통합 진단이 같은 출력 형태인가?
   → evaluated_at, rules_preview 등 일관

2. 모든 rule_row/obligation에 source="DIAGNOSIS"가 있는가?

3. 회귀 없음:
   applicable_count 244 유지
   MATCH_CANDIDATE 114 유지
   rules_table flat, law_name 채워짐 (PR #107/#108 유지)

4. 에러 없이 완료
```

## 범위 밖 (다음 단계)

```
SaaS MANUAL 공정 주입:
  factory_process (source=MANUAL)를
  표준 형태로 변환하여 결과에 합치기
  → 별도 작업지시서 (Layer 6 SaaS extension)
  → 지금 하지 않음 (폭주 방지)

Check 엔진 연결:
  메모리에 기록됨, 출력 표준화 완료 후
```

## 주의

- 엔진 평가 로직(facility_applicability_eval.py) 수정 금지
- 출력 함수 통합 + source 필드 추가만
- source 값은 전부 "DIAGNOSIS" (MANUAL 주입은 다음)
- 회귀 없어야 함 (건수 불변)
- Draft PR, merge 금지
- Supabase MCP 사용 가능 (project_id: vwlahtguyggrhvslabax)

## 이 작업이 표준화하는 것

```
Layer 5→6 연결:
  출력 함수 하나로 통합 (익명/통합 일관)
  + 표준에 source 필드 (DIAGNOSIS/MANUAL 구분 기반 마련)

다음(별도): SaaS MANUAL 공정 주입
그 다음(별도): Check 엔진 연결
```
