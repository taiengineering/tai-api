# 작업지시서: 전체 엔진 연결 감사 (Engine Connection Audit)

> 레포: taiengineering/tai-api
> 목적: "엔진은 있는데 소비자 경로가 연결 안 됨" 패턴을 전체 시스템에서 발견
> 원칙: 분석만. 수정 금지. 발견 목록 작성.

## DB 실측 (2026-06-08)

| 엔진 | 핵심 테이블 | 건수 | 의심 |
|------|------------|------|------|
| Check | inspection_sets | 327 | 소비자 연결? |
| Check | inspection_set_items | 5,184 | 소비자 연결? |
| Check | obligation_quality | 1,000 | evidence.chain? |
| Document | document_form_master | 63 | documents=0 |
| Document | generated_document | 28 | 소비자 연결? |
| Equipment | equipment_assets | 1,285 | checkins=0 |
| Schedule | work_schedules | 60 | 자동생성? |
| Education | education_master | 20 | setting=0 |
| Notification | runtime_notification_metrics | 3,151 | 활성 |

## 감사 방법 (각 엔진)

1. router 파일 읽기 → 어떤 service 호출?
2. service 파일 읽기 → 어떤 DB 테이블 읽기?
3. 기획된 데이터 소스 = 실제 데이터 소스?
4. 판정: CONNECTED / DISCONNECTED / DEAD / PARTIAL / ACTIVE_NO_ENGINE

## 우선순위

1. Check/Inspection (evidence.chain 미연결 알려짐)
2. Document (documents=0 vs form_master=63)
3. Equipment (assets=1285, checkins=0)
4. Schedule (Compiler Core schedule_candidate 연결?)
5~9. Education, Contract, Notification, Runtime, SaaS

## 산출물: docs/ENGINE_CONNECTION_AUDIT.md

상세 작업지시서: 로컬 WORKORDER_ENGINE_CONNECTION_AUDIT.md
