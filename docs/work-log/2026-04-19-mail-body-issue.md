# 2026-04-19 메일 본문 저장 이슈 (tai-api 리포)

**브랜치**: dev
**발견 창**: 프론트 (tai-admin 메일 페이지 점검 중)
**해결 창**: 백엔드 (다른 창에서 이미 반영됨)

---

## 상황 요약

### 증상
admin.taieng.co.kr/html/horizontal-menu-template/tai-mail 페이지에서
**모든 수신 메일이 "본문 없음"으로 표시됨**.

### 근본 원인
`routers/mail.py`의 `webhook_inbound` 함수가 Resend inbound webhook payload를
무시하고 별도 API(`https://api.resend.com/emails/{id}`)를 호출해 본문 조회를
시도하는데, 이 API는 **outbound 전용**이라 실패 → `html_body=""`로 DB 저장.

---

## 처리 상태

### ✅ 백엔드 수정 (다른 창에서 반영 완료)
`routers/mail.py` dev 브랜치 `webhook_inbound` 함수가 v2.1.0으로 업데이트됨:
- webhook payload에서 `data.html` / `data.text` 직접 추출
- html 없고 text만 있으면 `<pre>` 감싸서 `html_body` 저장
- Resend API 재조회는 fallback으로만 유지
- 첨부파일도 payload의 `data.attachments` 직접 사용
- `text_body` 컬럼 저장 시도 (없으면 자동 제외 후 재시도 로직)

### ✅ 프론트 대응 (이 창에서 완료 — tai-admin 리포)
- `tai-admin` dev 브랜치 커밋 `b8ff07d` — `mail.page.v2.js` v2.1.0
- 본문 fallback 3단계: `html_body` → `text_body`/`body` → warning alert
- 본문 없을 때 resend_id + Resend 대시보드 외부 링크 노출
- 백엔드 수정 전 배포해도 임시 대응으로 동작 (관리자가 Resend에서 원본 확인 가능)

---

## 남은 작업

### ⏳ 배포 및 검증
1. 세 리포 모두 dev → main PR 머지
   - `tai-api`: webhook_inbound v2.1.0
   - `tai-admin`: mail.page.v2.js v2.1.0
   - `taieng`: (해당 없음)
2. Staging(`tai-api-staging.fly.dev`) 자동 배포 확인
3. Actions에서 production 수동 배포 (자동 롤백 활성)
4. 검증 SQL 실행:
   ```sql
   SELECT id, subject, LENGTH(html_body) AS body_len, created_at
   FROM mail_logs
   WHERE direction = 'inbound'
   ORDER BY created_at DESC LIMIT 10;
   ```
   → 신규 수신 메일의 `body_len > 0` 확인

### ⏳ (선택) 과거 메일 백필
기존 `html_body=""`로 저장된 과거 메일 복구:
- 경로: `scripts/backfill_inbound_mail_bodies.py` (미작성)
- 내용: `resend_id`로 Resend API 재조회 → `html_body` 업데이트
- 주의: Resend API가 실제로 inbound 조회를 지원해야 성공. 실패하면 그대로 두고
  프론트의 warning alert에서 resend_id 링크로 개별 확인.

### ⏳ (선택) `text_body` 컬럼 마이그레이션
현재 코드는 `text_body` 컬럼에 저장 시도 후 실패하면 자동 제외. 컬럼 없는 상태로도
문제 없지만, 장기적으로는 마이그레이션 권장:
```sql
ALTER TABLE mail_logs ADD COLUMN IF NOT EXISTS text_body TEXT;
```

---

## 관련 문서
- 작업 지시서 원본: `/mnt/user-data/outputs/mail_webhook_inbound_fix_task.md`
  (프론트 창에서 작성, 완전한 교체 코드 + 검증 SQL + 백필 스크립트 포함)
- 프론트 로그: `taiengineering/tai-admin` dev `docs/work-log/2026-04-19-mail-page-body-fix.md`
- 프론트 변경 상세: `tai-admin` 커밋 `b8ff07d`
