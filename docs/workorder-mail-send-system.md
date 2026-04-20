# 작업지시서 — /mail/send-system 엔드포인트 추가

## 목적
pg_cron에서 JSON으로 직접 호출할 수 있는 시스템 메일 발송 전용 엔드포인트.
기존 `/mail/send` (multipart)와 별도로, 내부 자동화 알림 전용.

## 파일
`routers/mail.py` (기존 파일, 함수 추가)

## 구현 내용

```python
class SystemMailRequest(BaseModel):
    to: str
    subject: str
    body: str

@router.post("/send-system")
async def send_system_mail(req: SystemMailRequest):
    \"\"\"
    pg_cron 자동QA 등 내부 시스템에서 JSON으로 호출하는 메일 발송.
    인증 불필요 (내부 Supabase pg_net 전용).
    \"\"\"
    # 기존 mail.py의 메일 발송 로직 재사용
    # from_address: system@taieng.co.kr (고정)
    # 수신: req.to
    # 제목: req.subject
    # 본문: req.body (plain text)
```

## 주의
- 외부 노출 최소화: rate limit 또는 내부 IP 체크 고려
- 기존 multipart `/mail/send`는 건드리지 않음
- 200줄 미만 추가이므로 MCP 가능

## 완료 기준
- POST https://api.taieng.co.kr/mail/send-system
- Body: `{"to":"...", "subject":"...", "body":"..."}`
- 응답: `{"ok": true}`
