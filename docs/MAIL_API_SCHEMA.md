# mail_logs 테이블 스키마

## 테이블: mail_logs

Resend 발송·수신 메일 로그를 저장하는 테이블.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid | PK |
| direction | varchar(10) | inbound / outbound |
| from_email | text | 발신 이메일 |
| to_emails | text[] | 수신 이메일 배열 |
| cc_emails | text[] | 참조 이메일 배열 |
| subject | text | 제목 |
| html_body | text | HTML 본문 |
| text_body | text | 텍스트 본문 |
| status | text | sent / failed / pending |
| resend_id | text | Resend 이메일 ID |
| error_message | text | 발송 실패 오류 메시지 |
| read | boolean | 읽음 여부 (inbound) |
| deleted | boolean | 소프트 삭제 여부 |
| sent_by | text | 발송자 (user_id 또는 이메일) |
| webhook_payload | jsonb | Resend 웹훅 원본 페이로드 |
| created_at | timestamptz | 생성 시각 |
| updated_at | timestamptz | 수정 시각 |

## 인덱스

- idx_mail_logs_direction
- idx_mail_logs_read (WHERE deleted = false)
- idx_mail_logs_deleted
- idx_mail_logs_created_at DESC
- idx_mail_logs_status

## API 엔드포인트 (routers/mail.py)

| Method | URL | 설명 |
|--------|-----|------|
| POST | /mail/send | 메일 발송 (Resend) |
| GET | /mail/list | 목록 (direction/page/size/status/read/search) |
| GET | /mail/unread-count | 수신 미읽음 건수 |
| GET | /mail/from-addresses | 발신 허용 주소 목록 |
| GET | /mail/{id} | 단건 조회 (수신메일 자동 읽음) |
| PATCH | /mail/read/{id} | 읽음 처리 |
| PATCH | /mail/unread/{id} | 미읽음 처리 |
| PATCH | /mail/read-all | 수신 전체 읽음 |
| PATCH | /mail/delete/{id} | 소프트 삭제 |
| PATCH | /mail/delete-bulk | 일괄 소프트 삭제 |
| POST | /mail/webhook/inbound | Resend 수신 웹훅 |
