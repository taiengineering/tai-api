# TAI Safe 작업 세션 — 2026-04-13

## 1. Railway → Fly.io 도쿄 이전 ✅ 완료

### 배경
- Railway 서버 레이턴시 100~150ms (싱가포르/미국)
- 고정 IP 필요 (외부 공공 API 화이트리스트 등록용)

### 완료 내역
| 항목 | 결과 |
|---|---|
| 플랫폼 | Railway → Fly.io 도쿄 (nrt) |
| 고정 IP | **137.66.9.95** ($2/월) |
| 도메인 | api.taieng.co.kr → Cloudflare A 레코드 |
| SSL | Let's Encrypt (Fly.io 자동 발급) |
| 레이턴시 | 100~150ms → 25~35ms |
| 자동배포 | GitHub Actions (main push 시 fly deploy) |

### 생성 파일
- `fly.toml` — Fly.io 앱 설정 (도쿄, 512MB, auto_stop)
- `.github/workflows/fly-deploy.yml` — 자동배포 워크플로우
- `docs/FLY_IO_MIGRATION_GUIDE.md` — 이전 가이드

### 환경변수
- Railway Variables RAW → `.env.prod` → `fly secrets import`
- 총 25개 변수 등록 (Firebase JSON 제외, 별도 처리 필요)

### 검증
```
curl https://api.taieng.co.kr/health
→ {"status":"healthy","server_ip":"189.1.164.197","version":"5.19.0","cron":"10개 등록"}
```
> server_ip는 Cloudflare 프록시 경유 IP. 실제 Fly.io 고정 IP는 137.66.9.95

---

## 2. 메일 시스템 신버전 (tai-admin) ✅ 완료

### 배경
- 기존 `mail-list.html`은 Vuexy 목데이터 기반
- 메일 본문(html_body) 렌더링 안 됨
- 첨부파일, 답장 기능 없음

### 완료 내역 (tai-admin repo)
| 파일 | 내용 |
|---|---|
| `admin/.../tai-mail.html` | TAI 전용 메일 관리 페이지 신규 |
| `admin/.../assets/js/tai/mail.page.js` | 메일 JS v1.0.0 |
| `admin/.../mail-list.html` | tai-mail.html 자동 redirect |
| `admin/.../mail-send.html` | tai-mail.html 자동 redirect |
| `admin/.../index.html` | 메일 아이콘 링크 변경 |

### 기능
- 수신/발신 탭 + 미읽음 배지
- html_body → iframe srcdoc 렌더링 (XSS 격리)
- 첨부파일 다운로드 (`/mail/attachment/:id/:name`)
- 메일 작성: multipart/form-data, 파일 첨부
- 답장: Re: 자동, 발신자 자동 입력

---

## 3. 메세지미 발송 이슈 🔄 진행 중

### 원인 분석
- code 315 = IP 미등록 오류
- 메세지미 서버(`221.139.14.136`)가 IP 화이트리스트 방식 운용
- Supabase Edge Function IP → 미등록
- Fly.io 고정 IP(137.66.9.95) → 미등록

### 시도 이력
| 버전 | 방식 | 결과 |
|---|---|---|
| v2.0.0 | Supabase Edge Function 경유 | code 315 (IP 미등록) |
| v3.0.0 | Fly.io 직접 연결 (잘못된 API 형식) | 응답 없음 |
| v3.1.0 | Fly.io 직접 연결 (form-data 수정) | 응답 없음 (IP 차단) |
| v3.2.0 | Supabase Edge Function 경유 복구 | 현재 상태 |

### 진행 중
- 메세지미 고객센터 1:1 문의 접수
- 요청 내용: `137.66.9.95` IP 화이트리스트 등록
- 등록 완료 후 messaging.py v3.1.0 (직접 연결)으로 전환 예정

---

## 4. 다음 할 일

- [ ] 메세지미 IP 등록 답변 대기 → 137.66.9.95 등록 후 직접 연결 전환
- [ ] 외부 API들에 137.66.9.95 IP 등록 (기상청, 법제처 등)
- [ ] Railway 서비스 종료 (1주일 후 안정 확인 뒤)
- [ ] Firebase 환경변수 Fly.io에 등록 (FCM 기능 필요 시)
