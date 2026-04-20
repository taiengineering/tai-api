# 세션 핸드오프 — 2026-04-20 (2차)

## 다음 세션 최우선: Railway 이전

### 배경
Fly.io의 cold start (45초+)와 Gotenberg cold start로 PDF 생성 실패가 반복.
Railway 싱가포르 리전으로 전체 이전 결정.

### Railway 이전 상태
- [ ] Railway 프로젝트 생성 (taiengineering/tai-api 연결)
- [ ] 싱가포르 리전 선택
- [ ] 환경변수 설정 (Fly.io secrets → Railway Variables)
- [ ] Gotenberg 서비스 추가 (Docker image: gotenberg/gotenberg:8)
- [ ] 커스텀 도메인 api.taieng.co.kr 설정
- [ ] Cloudflare DNS CNAME 변경
- [ ] GitHub Actions fly-deploy.yml 비활성화
- [ ] 테스트 (health, SMS, PDF)
- [ ] Fly.io 서비스 삭제

### Fly.io 현재 secrets (Railway에 복사 필요)
```
SUPABASE_URL
SUPABASE_KEY
RESEND_API_KEY
MESSAGEME_API_KEY
MESSAGEME_SENDER
SENTRY_DSN
OUTBOUND_PROXY=http://115.68.227.222:3128
GOTENBERG_URL=(Railway 내부 URL로 변경)
```

### 이번 세션 완료 작업
- 모니터링 STEP 1~4 전부 완료
- SMS 정상화 (iwinv 프록시 115.68.227.222)
- 유료 PDF Gotenberg 전환 (v2.0.0)
- 법령엔진 remarks 필드 연결 (PR #22)
- 이슈 8개 해결 (#3,#5,#15,#16,#17,#18,#19,#20)
- dev ↔ main 브랜치 동기화
- mail.py v2.1.0 배포

### 오픈 이슈 없음 (전부 해결)

### 인프라 현황
- Backend: Fly.io 도쿄 → **Railway 싱가포르로 이전 중**
- Proxy: iwinv VPS 115.68.227.222:3128 (한국 고정 IP)
- DB: Supabase (xntdkrjhgcscmqctdzyo)
- Frontend: Cloudflare Pages
- 모니터링: Sentry + UptimeRobot + Smoke Test + pg_cron
