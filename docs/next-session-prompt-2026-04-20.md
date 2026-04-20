# 다음 창 인계 프롬프트 — 2026-04-20

## 역할
백엔드 창 (tai-api 레포, Fly.io 배포)

## 우선 확인 사항
세션 시작 전 아래 문서 읽고 맥락 파악:
- `docs/session-2026-04-19-infra.md` (어제 인프라 작업)
- `docs/session-2026-04-19-backend.md` (어제 백엔드 작업)

---

## 즉시 처리 — 메세지미 SMS 복구 (#16)

**원인:** Vultr 프록시 서버 삭제 → 502 Bad Gateway

**Step 1: OUTBOUND_PROXY 제거 후 직접 발송 테스트 (무료)**
```bash
fly secrets unset OUTBOUND_PROXY -a tai-api-prod
```
이후 테스트:
```
https://api.taieng.co.kr/messaging/debug-send?receiver=01047758888&message=TAI+테스트
```
→ 성공하면 완료. 실패 시 Step 2.

**Step 2: Fly.io 고정 IP 발급 ($2/월)**
```bash
fly ips allocate-v4 -a tai-api-prod
# 발급된 IP를 메세지미 콘솔에서 허용 IP 등록
```
이후 `/messaging/debug` 확인 → 테스트 발송.

---

## PR #10 머지 대기 중

**기안 PDF v2.0.0** (백엔드 완료, 프론트 템플릿 창 대기)
- tai-api dev 브랜치 → main PR #10 오픈 상태
- 프론트 창에서 `templates/proposal_pdf.html` v6 작업 완료 후 **동시 머지**
- 단독 머지 금지 (Jinja2 UndefinedError 발생)

**백엔드 `_build_context` 반환 스펙 (프론트 창 계약):**
```
penalty_sum_text  (max_penalty_text 대체)
paid_tiers        {mode, tiers} or {mode, determined, upper, basis}
```

---

## PENDING 이슈 목록

| 이슈 | 내용 | 우선순위 |
|---|---|---|
| #16 | 메세지미 SMS 복구 | 🔴 즉시 |
| #10 | PR 머지 (기안PDF v2.0.0) | 🟡 프론트 대기 |
| #17 | taieng 레포 wrangler.toml 삭제 | 🟢 낮음 |
| 미착수 | `POST /precedents/collect` 1회 수동 실행 | 🟡 |
| 미착수 | weather.py 안전관리자 대시보드 위젯 연결 | 🟡 |
| 미착수 | smoke_test.py Actions Secrets 등록 + 수동실행 | 🟡 |

---

## 개발 원칙 (반드시 준수)
1. 모든 커밋 → `dev` 브랜치 (main 직접 커밋 금지)
2. `/health` 절대 503 금지 (200 고정)
3. 200줄+ 파일 MCP 수정 금지 → Cursor 사용
4. `from db.supabase_client import get_supabase`
5. dev → PR → main → 자동 배포 흐름

## 인프라 현황
- **백엔드 API:** Fly.io `tai-api-prod` (Tokyo)
- **DB:** Supabase `xntdkrjhgcscmqctdzyo`
- **프론트:** Cloudflare Pages (admin, safe, new, taieng)
- **PDF:** Gotenberg on Railway (`http://gotenberg.railway.internal:3000`)
- **메세지미 발신번호:** `070-8080-1858`
