---
wo: WO-MEASURE-002
class: records
type: report
scope: canonical
project: test-universe
title: Pagination Ordering Hypothesis Verification
version: 1
status: active
owner: taiwang
---

# REPORT — WO-MEASURE-002 페이지네이션 정렬 가설 검증

> 원인은 분석이 아니라 **최소 수정 후 Measurement Gate PASS로 확정**한다. 이 문서는 PASS 이후 작성됨.

## 결론 (형식)
```text
Hypothesis      : ORDER BY 없는 LIMIT/OFFSET 페이지네이션이 입력 순서를 불안정하게 만들어
                  applicable_count 비결정성을 유발한다.
       ↓
Minimal Fix     : services/compiler_engine_gateway.py
                  - fetch_draft_slots_numeric_scope : .order("draft_id").order("part_id")
                  - fetch_executable_draft_articles : .order("id")
                  (Query Layer Only · Gateway Only · 2 Functions · .order 추가만)
       ↓
Measurement     : PASS
       ↓
Cause Confirmed : 페이지네이션 정렬 부재가 applicable_count 비결정성의 원인이다.
```

## Measurement Gate (수정 후)
```text
실행 조건 : RUN_WORKERS=1 · RUN_TIMEOUT_S=180 · RUN_RETRIES=1 (동일 입력 2회)
결과      : profiles 112 · changed 0 · unchanged 112 · missing 0 · success 112/112
Gate      : PASS (112 complete AND changed=0 AND timeout=0 AND missing=0)
```

## Before / After 대비
```text
수정 전 : 순차·180s·112/112 정상완료에도 12개 profile이 두 실행 간 흔들림
          (rc 고정, ac ±1~5. 예: PF-0020/0023 102↔107, PF-0025 107↔28, 건설/제조 ±1)
수정 후 : changed 0/112 (흔들림 소멸)
스모크  : PF-0019 3회 연속 ac=107 동일
```

## 근거 체인 (측정으로만)
- `evaluate_draft_for_facility`는 순수 함수(랜덤·정렬 의존 없음) → 로직 결백.
- 두 fetch가 `.range()`(LIMIT/OFFSET)만 사용, `.order()` 부재 → PostgreSQL은 정렬 없는 페이지네이션 순서 미보장 → 페이지 경계에서 slot 구성이 실행마다 달라짐 → ac 흔들림.
- `.order` 추가 후 changed=0 재현 → 가설이 원인으로 확정.

## 배포 / 반영
```text
Branch  : fix/measure-orderby-stability (검증) → PR #122 squash merge → main f20ab7e2
Deploy  : Railway tai-api-prod (GitHub 연결, main 자동배포). 검증은 브랜치 토글로 수행,
          PASS 후 main 복귀.
```

## 확정 상태
```text
Engine Determinism   : PASS (정렬 고정 시 동일 입력 → 동일 출력)
Measurement Integrity: PASS
Measurement Method   : Sequential(RUN_WORKERS=1) / Timeout 180s
Before Clean         : fix_run1 을 Before Clean 기준으로 Freeze (신뢰 가능)
기존 오염 Before      : DEPRECATED (before_snapshots)
```

## 다음
- CHG-001을 Before Clean(fix_run1) 기준으로 재시작 (이번엔 오염 없는 측정 위에서).
- WO-PERF-001(진단 28초/건, 전량 로딩)은 별도 백로그 유지 — 측정 신뢰성과 무관.
