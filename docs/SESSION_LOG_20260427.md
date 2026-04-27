# 세션 로그 — 2026-04-27 (모니터링 파이프라인 + SaaS 점검 + 가격 정합성)

## 완료 작업

### 1. SaaS 플랜 데이터 정합성 수정
- Enterprise SMS/카카오/문서/저장 → -1(무제한)
- extra_user_fee_v2 → 0 (전 활성 플랜)
- INDUSTRY_STARTER storage → -1 (기능 동일 원칙)
- input_scope 컬럼 추가 (facility_only/with_process/with_equipment)
- area_threshold / amount_threshold 컬럼 추가
- subscriptions.factory_id 추가
- revision_type_code 빈 값 보정

### 2. 정기결제 빌링키 엔드포인트 4개 (커밋 9a3f501)
- POST /payments/inicis/billing/prepare
- POST /payments/inicis/billing/return
- POST /payments/inicis/billing/charge
- POST /payments/subscriptions/{id}/cancel

### 3. 15시간 배포 실패 원인 수정 (커밋 0a91dc1)
- 원인: `_next_planned_from` (밑줄 private) vs `next_planned_from` (import 시 밑줄 없음)
- inspection_sets_helpers.py에 public alias 추가
- Railway 배포 성공 (15시간 만에 첫 성공)

### 4. 모니터링 파이프라인 구축

#### 자체 등록형 프로브 시스템
- `services/health_registry.py` — register_probe 모듈
- `services/health_probes.py` — 인프라 프로브 (DB, PDF, SMS, Storage, 프론트 2개)
- `routers/health.py` — /health + /health/deep 엔드포인트
- 서비스별 프로브: auth, law_engine, payment, construction, education, inspection, matching, tbm, risk
- 총 15개 프로브 배포 완료

#### /health/deep 응답 구조
```json
{
  "status": "degraded",
  "status_ko": "⚠️ 일부 서비스가 정상적이지 않습니다.",
  "probe_count": 15,
  "fail_count": 0,
  "warn_count": 1,
  "probes": { ... },
  "alert_ko": "한글 상세 알림",
  "sms_ko": "90자 SMS 메시지"
}
```

#### 프로브 메타 정보 (커밋 31049cc)
- 각 프로브에 impacts(영향범위), fix_links(수정링크), api, code 포함
- 대시보드에서 "어디서 문제 → 어디로 가서 수정" 즉시 파악

#### DB 테이블
- health_checks: 체크 결과 저장 (pg_cron 30일 자동 정리)
- health_alerts: 알림 기록 (중복 방지)

### 5. auto-qa-dashboard 재설계 (커밋 5dd5acc)
- /health/deep 단일 소스 기반으로 전면 교체
- 기존 auto_qa_checks(86개) 기반 → /health/deep(15개) 기반
- 상단 Hero (정상/경고/장애)
- 이슈 카드: 실패/경고만 표시 (영향범위 + 수정링크 + 재체크)
- 전체 프로브 그리드 (접기)
- 30초 자동 새로고침
- 24시간 히스토리

### 6. GitHub Actions CI/CD 재설계
- 삭제: smoke-test.yml(매시간 cron), pytest.yml, integrity.yml, fly-deploy.yml
- 신규: ci.yml (dev push + PR), service-check.yml (6시간), post-deploy.yml (수동)
- 예상 메일: 40~60통/일 → 정상 시 0통

### 7. safe.taieng.co.kr 기능 점검
- 건물 설비관리 메뉴 노출 (menu-tadmin v5.4.0, 커밋 f8414ec)
- plan-gate.js 모듈 배포 (커밋 843afc9)
- RLS 8개 민감 테이블 활성화

### 8. 문서화
- docs/INSPECTION_PRINCIPLES.md — 서비스 점검 원칙
- docs/PRICING_FINAL.md — 가격 정책 (3회 업데이트)
- docs/WORK_PLAN_20260427.md — 작업계획
- services/README_HEALTH_PROBE.md — 프로브 작성 가이드

## 이슈 등록
| 레포 | # | 제목 |
|---|---|---|
| tai-api | #59 | SaaS 플랜 데이터 정합성 수정 + 중기 구조 개선 |
| tai-api | #60 | 자체 등록형 헬스체크 + 한글 알림 + CI/CD 재설계 |
| tai-api | #61 | 멀티테넌시 RLS 전체 적용 — 고객 데이터 격리 |
| tai-admin | #4 | safe.taieng.co.kr 전체 기능 분석 |
