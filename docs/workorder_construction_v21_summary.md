# 건설 섹터 작업지시서 v2.1.0 — 요약

> 전체 작업지시서는 workorder_construction_backend.md / workorder_construction_frontend.md 참조

## 창 구성

| 창 | 작업 | 프롬프트 파일 |
|---|---|---|
| 백엔드 창 | construction.py API 구현 | `docs/prompt_construction_backend.md` |
| 프론트엔드 창 | HTML 화면 6개 구현 | `docs/prompt_construction_frontend.md` |

## 핵심 스펙 (v2.1.0)

| # | 기능 | 스펙 |
|---|---|---|
| 1 | 법령진단 | 응답: applicable_rules + by_obligation_type 필수 |
| 2 | 일정 생성 | 응답: created + skipped + total_rules / 진단=0이면 HTTP 400 |
| 3 | 점검 저장 | overall_result 생략 가능 / 이상 시 FCM 자동 발송 |

## 프론트 구현 순서

1. construction-site-list.html — 법령진단 버튼 + 일정생성 버튼(조건부)
2. construction-inspection-anchor.html — inspection-anchor.html 재활용
3. construction-inspection-list.html
4. construction-process.html
5. construction-worker-list.html
6. worker-check-construction.html — v2.1.0 submitCheck

## 백엔드 구현 순서

1. sites CRUD
2. 법령진단 (v2.1.0 응답구조)
3. 공정 CRUD
4. 점검 저장 + FCM
5. 작업자 관리
6. 작업일정 자동 생성 (v2.1.0)
