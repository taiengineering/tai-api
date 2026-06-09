# E2E 테스트 결과 — 배포 후 전체 파이프라인 (2026-06-09)

> 대상: api.taieng.co.kr (Railway tai-api-prod), version 6.0.2
> 범위: PR #105~#109 배포 후 법령진단 전체 파이프라인 라이브 검증
> 결과: 전체 정상

## 배포 확인

| 항목 | 결과 |
|------|------|
| origin/main | e0fd2df (PR #109 57f552b 포함) |
| GET /health | 200 — {"status":"ok","version":"6.0.2"} |

## 라이브 API 테스트 (유효 스키마: site_kind + scale + workers)

| 테스트 | HTTP | applicable | MATCH | law_name | source | Transform |
|--------|------|-----------|-------|----------|--------|-----------|
| BUILDING medium 50 | 200 | 244 | 114 | 채움 | DIAGNOSIS | flat 244, wrapper 없음 |
| INDUSTRIAL large 300 | 200 | 115 | 115 | 채움 | DIAGNOSIS | flat 115 |
| CONSTRUCTION large 120 | 200 | 245 | — | 채움 | DIAGNOSIS | flat 245 |

- partialResult: evaluated_at, engine_version, rules_table/rules_preview 등 PR #109 필드 확인
- INDUSTRIAL 500 오류 없음 (PR #106 sector 표준화)

## Layer별 검증

| Layer | 항목 | 결과 |
|-------|------|------|
| 1→2 | 입력 저장 + sector 표준 | PASS (INDUSTRIAL 정상) |
| 3→4 | rules_table law_name 채움 | PASS |
| 4→5 | obligations flat 전개 | PASS (wrapper 0건) |
| 5→6 | source 필드 + partial 일관 | PASS (DIAGNOSIS) |

## DB 검증 (최근 결과)

- engine_version: v3.0-compiler-core-anonymous
- first_source: DIAGNOSIS
- first_law_name: 채워짐

## 작업지시서 스키마 갭 (기능 결함 아님)

```
작업지시서의 curl payload는 상세 필드(floor_area, floor_count 등)만 전송.
실제 API(AnonymousDiagnosisCreate)는 site_kind + scale + workers 필수.
→ 422 응답은 작업지시서 payload 스키마 갭 (파이프라인 결함 아님)
→ 유효 스키마로 재테스트 시 전부 통과
→ 800kVA 단위 방어: 로컬 normalize_consumer_inp PASS (prod는 필드 스키마 차이로 미도달)
```

## 결론

```
배포 환경 전체 파이프라인 정상.
BUILDING MATCH 114 유지 (회귀 없음).
Layer 3~6 표준화 항목 모두 PASS.
엔진(facility_applicability_eval.py) 미변경 유지.

남은 작업:
  - SaaS MANUAL 공정 주입 (표준에 source 준비됨)
  - Check 엔진 연결 (메모리 기록)
  - 입력 스키마 문서화 (site_kind + scale + workers)
```
