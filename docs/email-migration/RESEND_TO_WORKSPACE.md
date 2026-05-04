# Resend → Google Workspace 이전 가이드

> 작성: 2026-05-04
> 목적: Resend 단일 의존에서, **수신=Workspace Gmail / 발송 자동=Resend** 분리 구조로 전환.

---

## 1. 왜 분리하는가

| 역할 | 도구 | 이유 |
|---|---|---|
| 자동 발송(인증·결제·다이제스트) | **Resend** | API 친화적, 발송량 추적, 트랜잭션 메일 최적화 |
| 외부 메일 수신·답장 | **Google Workspace (Gmail)** | 표준 메일 UX, 모바일 푸시, 알림·검색·라벨 |

Resend는 본질적으로 발송 인프라라 메일함 UX가 약함.  
"답장을 잘 처리해야 한다"는 요구는 Gmail이 정답.

---

## 2. 변경 전후 비교

### Before
```
외부 → MX(Resend) → /mail/webhook/inbound → mail_logs(direction=inbound)
TAI 코드 → Resend SDK → 발송 → mail_logs(direction=outbound)
사용자 답장 → MX(Resend) → /mail/webhook/inbound → mail_logs (어드민에서 답장 작성)
```

### After
```
외부 → MX(Google) → Gmail 받은편지함 → 푸시 알림
TAI 코드 → Resend SDK → 발송 → mail_logs(direction=outbound)
          (reply_to: admin@taieng.co.kr 자동 부착)
사용자 답장 → MX(Google) → Gmail → 거기서 직접 답장
```

핵심 변화:
- Resend Inbound webhook은 호출이 멈춤 (코드는 살아있어도 무해)
- 자동 발송 메일에 `reply_to`가 박혀 답장이 Gmail로 들어감
- 어드민의 mail_logs inbound 화면은 과거 메일만 보임 (정상)

---

## 3. 단계별 작업

### Step 1 — Workspace 가입 (외부, 대표 직접)
- Business Starter 이상 선택
- `taieng.co.kr` 도메인 입력
- 기본 사용자 1명 생성 (예: `taewang@taieng.co.kr`)
- 가입 마법사가 자동으로 도메인 인증 TXT/MX 발급

### Step 2 — DNS 변경 (Cloudflare)

#### 2-1. 도메인 소유 확인 TXT
가입 마법사가 주는 TXT 그대로 추가.

#### 2-2. MX 레코드 — 기존 Resend MX 삭제 후 추가
```
타입  이름  값                        우선순위
MX   @    smtp.google.com.            1
```

구버전 Google MX 5종 (ASPMX, ALT*) 대신 **단일 smtp.google.com (priority 1)** 권장.

#### 2-3. SPF — Resend + Google 양립
```
타입  이름  값
TXT  @    "v=spf1 include:_spf.google.com include:amazonses.com ~all"
```
- `_spf.google.com`: Workspace에서 사람이 보내는 메일 검증
- `amazonses.com`: Resend가 자동 발송 시 사용 (Resend는 AWS SES 위에서 동작)
- 둘 다 필요하므로 한 줄에 같이 명시

#### 2-4. DKIM — Workspace 콘솔에서 발급
admin.google.com → Apps → Google Workspace → Gmail → 도메인 인증.  
발급된 키를 Cloudflare에 TXT(`google._domainkey`)로 추가.

Resend도 DKIM 키가 별도로 있는데 그건 그대로 유지(`resend._domainkey` 등). 두 DKIM이 공존해도 충돌 없음.

#### 2-5. DMARC — 시작은 monitor only
```
타입  이름     값
TXT  _dmarc  "v=DMARC1; p=none; rua=mailto:dmarc-reports@taieng.co.kr"
```
나중에 안정화되면 `p=quarantine` → `p=reject` 단계 강화.

### Step 3 — Railway 환경변수 추가
```
MAIL_DEFAULT_REPLY_TO=admin@taieng.co.kr
```
Workspace에서 만든 메인 메일함 주소를 박는다.  
시스템 자동 발송(`/mail/send-system`)에 답장이 이 주소로 들어옴.

### Step 4 — Resend 대시보드 정리
- Resend → Inbound Email 설정 비활성화 (또는 그대로 둬도 무해 — MX가 안 가니까)
- Resend 도메인 검증 상태는 그대로 유지 (DKIM이 Resend 쪽도 살아있어야 발송 동작)

### Step 5 — 검증

#### 5-1. Workspace 수신
- 외부에서 `taewang@taieng.co.kr`로 메일 → Gmail 받은편지함에 도착하면 OK
- DNS 전파 시간 5분~수 시간

#### 5-2. Resend 발송
- 어드민 메일함에서 `/mail/send` 한 번 보내기
- Resend 대시보드에 로그 남는지 확인
- 수신자에게 도착 확인 + reply_to 헤더가 `admin@taieng.co.kr`로 보이는지

#### 5-3. Reply 흐름 (가장 중요)
- 자동 발송 메일을 받은 외부 사용자가 "답장" 클릭
- 답장이 `admin@taieng.co.kr` 으로 가야 함
- Gmail 받은편지함에 도착 → 답장 작성 → 정상 동작

---

## 4. 코드 변경 요약 (이번 작업)

### `routers/mail.py` v2.2.0
- `send_mail` / `reply_mail`: Form 파라미터 `reply_to` 추가 (Optional)
- `send_system_mail`: Body 필드 `reply_to` 추가 + 미지정 시 `MAIL_DEFAULT_REPLY_TO` 환경변수 fallback
- `webhook_inbound`: MX 마이그레이션 안내 주석
- 기존 동작 회귀 없음 — `reply_to` 미지정 시 from으로 답장 (이전과 동일)

### `.env.example`
- `RESEND_API_KEY`, `MAIL_DEFAULT_REPLY_TO` 명시

---

## 5. 손대지 않은 것 (의도적)

- 어드민 메일함 UI (`mail_logs` 기반): 그대로. MX 변경 후 inbound 신규 row가 안 쌓일 뿐.
- 첨부파일 시스템 (`mail-attachments` 버킷): 그대로.
- ALLOWED_FROM 발신 주소 3개: 그대로. Workspace에서 alias로 만들어 두면 발송·수신 둘 다 가능.
- Resend Inbound webhook 라우터: 코드 유지. 호출이 안 들어오면 자동 비활성.

---

## 6. 향후 정리 후보 (Phase 2, 선택)

- Workspace 정착 후 사용 패턴 보고:
  - 어드민 mail_logs UI를 outbound 발송 로그 전용으로 슬림화
  - inbound 화면은 "과거 보관함"으로 표기 변경
  - 또는 inbound 화면 자체 제거
- Resend Webhook을 outbound delivery 추적용으로 재활용 (bounce·complaint·delivered 이벤트)

---

## 7. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| Gmail로 메일 안 옴 | DNS 전파 지연 | `dig MX taieng.co.kr` 로 확인. 5분~수 시간 대기 |
| 자동 발송이 스팸함으로 | DKIM 미설정 또는 SPF 누락 | Workspace 콘솔에서 DKIM 활성화, SPF에 `_spf.google.com` 포함 확인 |
| Resend에서 도메인 인증 풀림 | DKIM 키 한 종류만 남기면서 Resend 쪽 삭제 | Resend 대시보드에서 DKIM 재발급 후 Cloudflare에 다시 추가 |
| `MAIL_DEFAULT_REPLY_TO`가 안 박힘 | Railway env 미반영 | Railway → Variables → 저장 후 재배포 (1~2분) |

---

## 8. 참고

- Resend Inbound: https://resend.com/docs/dashboard/emails/inbound
- Workspace 도메인 인증: https://support.google.com/a/answer/33786
- SPF Record Best Practices: 한 도메인에 SPF TXT는 1개만 (다중은 무효), include만 추가
