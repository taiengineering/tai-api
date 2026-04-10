# TAI Safe 세션 기록 — 2026-04-11

## tai-api 작업

### 1. auth.py v3.5.0 — PWA OTP 인증 API 추가

**신규 엔드포인트:**
- `POST /auth/send-otp` — 전화번호 OTP 발송 (개발용 `dev_otp` 응답 포함)
- `POST /auth/verify-otp` — OTP 검증 후 PWA 작업자 사용자 정보 반환

**verify-otp 응답 구조 (tai_user localStorage 형식):**
```json
{
  "id": "...",
  "worker_id": "...",
  "phone": "01047758888",
  "name": "심태왕",
  "sector": "CONSTRUCTION",
  "factory_id": null,
  "site_id": null,
  "company": "",
  "job_type": ""
}
```

**OTP 저장 우선순위:**
1. `otp_store` 테이블 (upsert)
2. fallback: `users.raw_app_meta_data` 필드

**향후:** SMS 실제 발송은 SENS/Solapi 연동 필요.

---

### 2. DB 변경

**`users` 테이블:**
- `sector TEXT DEFAULT 'INDUSTRY'` 컬럼 추가 (apply_migration)
- `users.sector = 'CONSTRUCTION'` WHERE phone = '01047758888' (심태왕)

**목적:** PWA 로그인 시 verify-otp 응답에 sector 포함 → `gotoInspect()` 분기 처리
- sector = CONSTRUCTION → `construction_inspect.html`
- sector = INDUSTRY → `inspect.html`

---

## 다음 세션 작업 예정

- SMS 실제 발송 연동 (SENS/Solapi)
- otp_store 테이블 DDL 추가 (현재 fallback으로 raw_app_meta_data 사용)
- law engine → auto-schedule 파이프라인 연결
- safe.taieng.co.kr 작업자 대시보드 구성
