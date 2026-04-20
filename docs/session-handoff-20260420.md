# TAI 세션 핸드오프 — 2026-04-20

## 세션 요약
PM/기획 세션 3일차. 모니터링 4단계 전부 완료, SMS 정상화, 이슈 정리.

## 완료 작업 (이번 세션)

### 1. Smoke Test 수정
- S4(diagnosis) 제거 → S1~S3(3/3) 통과
- SMS 알림: MessageMi 직접 호출 → TAI API `/messaging/debug-send` 경유로 변경
- warm-up 로직 추가 (서버 깨우기 + 5초 대기)

### 2. /health 테이블명 수정
- `master_legal_inspection_rules`(0건) → `master_building_legal_rules`(1,133건)
- Production 배포 완료, `{"status":"healthy"}` 확인

### 3. 모니터링 STEP 4 (pg_cron)
- pg_net 확장 활성화
- `monitoring_config` 테이블 생성 (alert_phone: 01047758888)
- `daily_health_check()` SQL 함수 생성
- pg_cron 스케줄: 매일 KST 09:00 (UTC 00:00)
- 점검 항목: fix_chat 이탈율 80% 초과 시 SMS

### 4. mail.py v2.1.0 배포
- dev 커밋 → admin MCP로 main 직접 push → production 배포
- webhook_inbound: payload에서 html/text 직접 추출

### 5. 메세지미 SMS 정상화 (#16)
- Vultr 정책위반 삭제 → iwinv VPS (115.68.227.222) + Squid 프록시
- Fly.io OUTBOUND_PROXY 설정 (prod + staging)
- SMS 발송 테스트 성공 (code=100)

### 6. dev ↔ main 브랜치 동기화 (#20)
- `git reset --hard origin/main` + force push

### 7. wrangler.toml 삭제 (#17)
- taiengineering/taieng main에서 GitHub UI로 삭제

### 8. diagnosis/free 성능 확인 (#18)
- 실제 엔드포인트: `/diagnosis/run` (not `/diagnosis/free`)
- warm 상태에서 0.7초 → cold start가 원인

### 9. 이슈 정리
- #3 Closed (배포 안전 인프라 완료)
- #15 Closed (PR, main 직접 반영)
- #16 Closed (SMS 정상화)
- #17 Closed (wrangler.toml 삭제)
- #18 Closed (cold start 원인)
- #19 Closed (pg_cron 완료)
- #20 Closed (브랜치 동기화)

## 오픈 이슈
| # | 제목 | 비고 |
|---|------|------|
| #5 | 유료 상세 PDF 프로덕션 검증 | 다음 세션 진행 |

## 다음 세션 진행 사항

### #5 유료 PDF 검증
- 테이블: `anonymous_diagnosis_results`
- 유료 데이터 없음 (모두 FREE 티어)
- 테스트 데이터 생성 후 `/diagnosis/report-pdf/{public_token}` 호출 필요
- 관련 파일: `routers/diagnosis_report.py`, `templates/diagnosis_report_paid.html`

## 인프라 현황
- Backend: Fly.io 도쿄 (tai-api-prod + tai-api-staging + tai-gotenberg)
- Proxy: iwinv VPS 115.68.227.222:3128 (한국 고정 IP, Squid)
- DB: Supabase (xntdkrjhgcscmqctdzyo)
- Frontend: Cloudflare Pages
- 모니터링: Sentry + UptimeRobot + Smoke Test + pg_cron

## 메모리 업데이트 필요
- iwinv VPS IP: 115.68.227.222 (Vultr 158.247.224.158 → iwinv 115.68.227.222)
- 모니터링 STEP 4 완료
- Smoke Test 3/3 (S4 제외)
- 알림톡 템플릿: 미등록 (발송 대상/내용 결정 후 등록 예정)
