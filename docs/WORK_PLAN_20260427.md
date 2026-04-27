# TAI Safe 작업계획 — 2026-04-27 기준

> 기획창(Claude)이 수립, Cursor/Code에 할당

## Phase 1: 즉시 (이번 주)

| # | 작업 | 할당 | 레포 | 이슈 |
|---|---|---|---|---|
| 1-1 | saas.html 요금제 누락 텍스트 + 시각화 | Cursor | taieng | - |
| 1-2 | 카운터 0 표시 버그 수정 | Cursor | taieng | #57 |
| 1-3 | 법령엔진 rules_table 19필드 출력 | Cursor | tai-api (dev) | #55, #56 |
| 1-4 | diagnosis-sample.html 헤더/푸터 | Cursor | taieng | - |

## Phase 2: 이번 주 후반

| # | 작업 | 할당 | 레포 | 이슈 |
|---|---|---|---|---|
| 2-1 | 서비스 분리 — legal_engine.py (77KB) | Cursor | tai-api (dev) | #29 |
| 2-2 | RLS 긴급 테이블 8개 | Code | tai-api | #43 |
| 2-3 | 판례 데이터 1회 수집 | Code | tai-api | - |

## Phase 3: 다음 주

| # | 작업 | 할당 | 레포 | 이슈 |
|---|---|---|---|---|
| 3-1 | 서비스 분리 — construction.py (58KB) | Cursor | tai-api (dev) | #29 |
| 3-2 | 서비스 분리 — payment.py (52KB) | Cursor | tai-api (dev) | #29 |
| 3-3 | 정기결제 빌링키 Phase 2-5 | Cursor | tai-api (dev) | #45 |
| 3-4 | 개정법령 자동 파이프라인 | Code | tai-api | #54 |
| 3-5 | DB 구조 보강 (input_scope 등) | Code | tai-api | #59 |

## Phase 4: 기능 완성 후

| # | 작업 | 할당 | 이슈 |
|---|---|---|---|
| 4-1 | 서울 리전 이전 | Code + 수동 | #58 |
| 4-2 | Smoke Test 완성 | Code | - |
| 4-3 | 프론트엔드 백로그 | Cursor | - |

## 상세 작업지시

- Phase 1 작업지시: `/mnt/user-data/outputs/` 에 개별 파일
- 서비스 분리 규칙: `docs/DEV_RULES_SERVICE_LAYER.md`
- 가격 기준: `docs/PRICING_FINAL.md`
