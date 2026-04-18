# 워크오더 — 모바일 Phase B (백엔드) v2

**작성일**: 2026-04-16 (v2: GPS + WebAuthn 추가)
**착수일**: 2026-04-17
**대상 창**: 백엔드 세션 (tai-api)
**프론트엔드 연계**: `tai-admin/docs/workorder-2026-04-17-mobile-phase-b-frontend.md`
**푸시 대상**: `taiengineering/tai-api` repo, `dev` 브랜치
**예상 소요**: 7일

> 전체 내용은 이전 기획세션에서 작성됨. 핵심 항목만 요약.

## 핵심 변경 (v1→v2)
- GPS 컬럼 5개 테이블 마이그레이션
- WebAuthn API 6종 (register/login options+verify, credentials GET/DELETE)
- require_role 미들웨어
- 안전관리자 API 4종 (dashboard-summary, PTW approve/reject)
- TBM 세션 API 5종
- 기존 6개 POST API에 lat/lng 수신 추가

## DB 마이그레이션
- workers.role (WORKER/FOREMAN/SAFETY_MANAGER)
- GPS 컬럼: inspections, emergency_reports, incident_reports, tbm_meetings, attendance_logs
- webauthn_credentials + webauthn_challenges 테이블
- work_requests 승인/반려 컬럼

## 7일 일정
- Day 1: DB 마이그레이션 + role 배포
- Day 2: WebAuthn API + require_role
- Day 3: 안전관리자 API
- Day 4: TBM 세션 API
- Day 5: GPS 수신 로직
- Day 6: E2E 테스트
- Day 7: 크론 + 로깅 + 마무리

## 주의사항
- Breaking change 금지
- dev 브랜치만
- WebAuthn RP_ID = safe.taieng.co.kr 고정
- challenge 5분 만료
- 한국 범위 밖 GPS: 차단X 로그만
