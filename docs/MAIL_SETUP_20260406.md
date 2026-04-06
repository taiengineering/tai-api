# TAI 메일 수신 시스템 구축 완료 (2026-04-06)

## 완료된 작업

### 1. routers/mail.py 버그 수정
- `RESEND_API_KEY` 변수 미선언 → `RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")` 추가
- `BulkDeleteRequest.ids` → `BulkDeleteRequest.mail_ids` (프론트엔드 페이로드 일치)
- 웹훅 핸들러 페이로드 구조 수정:
  - **이전**: `payload.get("from")` — Resend 구조와 불일치
  - **수정**: `payload["data"]["from"]` — Resend 실제 구조 반영
  - `event_type != "email.received"` 체크 추가
  - 웹훅에 본문 없음 → `email_id`로 Received emails API 별도 호출

### 2. Railway 배포 문제 해결
- Railway GitHub App이 `taiengineering/tai-api` 저장소 접근 권한 없음 ("GitHub Repo not found")
- GitHub Settings → Installations → Railway App → tai-api 저장소 추가
- Railway v5.6.4 정상 배포 완료

### 3. Resend 메일 수신 인프라 설정
- Resend Enable Receiving 토글 ON
- MX 레코드: `inbound-smtp.ap-northeast-1.amazonaws.com` Priority 10
- Cloudflare Email Routing 비활성화 + 기존 MX 3개 제거
- Resend Webhook 등록:
  - URL: `https://api.taieng.co.kr/mail/webhook/inbound`
  - Event: `email.received`

### 4. mail-list.html Mock → 실제 API 교체 (tai-admin)
- MOCK_MAILS 배열 전체 제거
- 실제 API 연동:
  - `GET /mail/list` — 목록 조회 (페이지네이션, 필터)
  - `GET /mail/unread-count` — 미읽음 뱃지
  - `GET /mail/{id}` — 상세 조회 (자동 읽음 처리)
  - `PATCH /mail/read/{id}` — 읽음/미읽음 처리
  - `PATCH /mail/delete/{id}` — 소프트 삭제
  - `PATCH /mail/delete-bulk` — 일괄 삭제
  - `PATCH /mail/read-all` — 전체 읽음

## 수신 주소

`taieng.co.kr` 도메인으로 오는 모든 메일 수신 가능:
- tai@taieng.co.kr
- contact@taieng.co.kr
- anything@taieng.co.kr

## 테스트 결과

웹훅 테스트 페이로드 전송 → 200 success → DB 저장 확인 (1건)

## 아키텍처

```
외부 메일 → MX(Resend) → Resend 파싱 → 웹훅 POST /mail/webhook/inbound
→ email_id로 Received emails API 호출 (본문 조회)
→ mail_logs 테이블 INSERT (direction=inbound)
→ 관리자 메일함 표시
```
