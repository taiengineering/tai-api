"""이메일 발송 유틸 — Gmail SMTP.

v1.2.0  2026-05-26  발신자 tai@taieng.co.kr 통일
v1.1.0  2026-05-26  발신자 noreply 분리, Reply-To 추가
v1.0.0  2026-05-26  신규 생성

환경변수:
  GMAIL_USER       = SMTP 인증 + 발신자 (tai@taieng.co.kr)
  GMAIL_APP_PASS   = Gmail 앱 비밀번호 (16자리)
  GMAIL_FROM_NAME  = 발신자 표시명 (기본: TAI Safe)
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List

logger = logging.getLogger(__name__)

GMAIL_USER = os.getenv("GMAIL_USER", "tai@taieng.co.kr")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")
GMAIL_FROM_NAME = os.getenv("GMAIL_FROM_NAME", "TAI Safe")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_email(
    to: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
    cc: Optional[List[str]] = None,
) -> bool:
    if not GMAIL_USER or not GMAIL_APP_PASS:
        logger.warning("GMAIL_USER or GMAIL_APP_PASS not set, skipping email")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{GMAIL_FROM_NAME} <{GMAIL_USER}>"
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(cc)

        if body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        recipients = [to] + (cc or [])

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.sendmail(GMAIL_USER, recipients, msg.as_string())

        logger.info(f"Email sent to {to}, subject='{subject}'")
        return True

    except Exception as e:
        logger.error(f"Email send failed to {to}: {e}")
        return False


async def send_email_async(
    to: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
    cc: Optional[List[str]] = None,
) -> bool:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, send_email, to, subject, body_html, body_text, cc)


def payment_success_email(user_name: str, company_name: str, plan_code: str, 
                          total_amount: int, sector_kr: str) -> tuple:
    subject = "[TAI Safe] 결제가 완료되었습니다"
    
    html = f"""
    <div style="font-family:'Apple SD Gothic Neo',sans-serif;max-width:600px;margin:0 auto;padding:20px;">
      <div style="background:#7367f0;color:#fff;padding:24px;border-radius:12px 12px 0 0;text-align:center;">
        <h1 style="margin:0;font-size:22px;">🎉 결제가 완료되었습니다</h1>
      </div>
      <div style="background:#fff;padding:24px;border:1px solid #e8e8e8;border-top:none;border-radius:0 0 12px 12px;">
        <p style="font-size:15px;color:#333;">{user_name}님, 안녕하세요.</p>
        <p style="font-size:15px;color:#333;"><strong>{company_name}</strong>의 TAI Safe {sector_kr} 플랜 결제가 완료되었습니다.</p>
        
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr style="background:#f8f8f8;">
            <td style="padding:12px;font-weight:600;border:1px solid #eee;">플랜</td>
            <td style="padding:12px;border:1px solid #eee;">{plan_code}</td>
          </tr>
          <tr>
            <td style="padding:12px;font-weight:600;border:1px solid #eee;">결제 금액</td>
            <td style="padding:12px;border:1px solid #eee;">{total_amount:,}원</td>
          </tr>
          <tr style="background:#f8f8f8;">
            <td style="padding:12px;font-weight:600;border:1px solid #eee;">섹터</td>
            <td style="padding:12px;border:1px solid #eee;">{sector_kr}</td>
          </tr>
        </table>
        
        <div style="text-align:center;margin:24px 0;">
          <a href="https://safe.taieng.co.kr" style="display:inline-block;background:#7367f0;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">
            TAI Safe 시작하기
          </a>
        </div>
        
        <p style="font-size:13px;color:#888;margin-top:20px;">
          로그인 후 대시보드에서 안전관리 세팅을 시작하세요.<br>
          문의사항이 있으시면 tai@taieng.co.kr로 연락 부탁드립니다.
        </p>
      </div>
      <p style="text-align:center;font-size:11px;color:#aaa;margin-top:16px;">
        TAI Engineering | 서울 강남구 테헤란로79길 6 JS타워 3층
      </p>
    </div>
    """
    
    text = (
        f"{user_name}님, 결제가 완료되었습니다.\n"
        f"플랜: {plan_code}\n"
        f"금액: {total_amount:,}원\n"
        f"지금 바로 이용하세요 → https://safe.taieng.co.kr"
    )
    
    return subject, html, text
