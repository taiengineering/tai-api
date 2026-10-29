---
title: Slack Bot Token 안전 교체 절차
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3
version: ADDENDUM-001
status: ADDENDUM_FINAL
date: 2026-10-29
---

# Slack Bot Token 안전 교체 절차 (COR-03 해소)

## 배경

GPT COR-03 지적: 대화 중 `SLACK_BOT_TOKEN1` 토큰 값이 노출됨.
"Token Rotation"(12시간 자동 갱신 기능)과 단순 토큰 재발급을 혼동하지 않도록 구분하고,
안전한 교체 절차를 확정한다.

---

## 핵심 구분

### A. Slack Token Rotation (12시간 자동 갱신)

- Slack App Settings > OAuth & Permissions > **Token Rotation** 기능
- 활성화 시: 토큰이 12시간마다 자동 만료 → 앱이 Refresh Token으로 새 토큰을 능동 갱신해야 함
- **TAI 현재 상태**: Token Rotation 미활성화
- **행동 지침**: 이 기능을 활성화하면 TAI 코드베이스에 Refresh Token 갱신 로직 추가 필요
  (별도 WO 없이 활성화 금지 — Railway 환경변수 자동 업데이트 불가)

### B. 단순 토큰 재발급 (본 절차 대상)

- 기존 토큰을 무효화하고 새 토큰을 발급받는 1회성 교체
- Token Rotation과 무관; Refresh Token 로직 불필요
- 교체 전 영향 평가 필수 (아래 체크리스트)

---

## 교체 전 영향 평가 체크리스트 (Owner 실행)

### 1. 봇 채널 멤버십 확인

```
Slack 관리 콘솔 → Apps → tai_bot → 가입된 채널 목록 스크린샷 저장
```

**주의**: `auth.revoke` 호출 시 봇이 채널에서 퇴장할 수 있음.
단순 재발급(revoke 없이 새 토큰 발급)은 채널 멤버십에 영향 없음.

### 2. 토큰 재발급 vs revoke 구분

| 방법 | 채널 멤버십 | 권장 여부 |
|------|------------|----------|
| Slack App > OAuth 토큰 재발급 (Install App 재실행) | 유지 | **권장** |
| `auth.revoke` API 호출 후 재발급 | 상실 가능 | 금지 (별도 검증 없이) |

**재발급 절차** (권장):
1. Slack App 관리 콘솔 로그인 (Owner 계정)
2. 앱 선택 → **OAuth & Permissions** 탭
3. **Reinstall to Workspace** 버튼 클릭
4. 권한 재승인
5. 새 `Bot User OAuth Token` 값 복사 (화면에서만 확인, 어디에도 붙여넣기 금지)

### 3. 스코프 변경 여부 확인

현행 스코프 목록을 재발급 전후 비교하여 누락 스코프 없음을 확인.
파일럿에서 `groups:history` 추가가 필요하므로 재발급 시 함께 추가 가능.

---

## 교체 절차 (Owner 단독 실행)

```
Step 1: Slack App 관리 콘솔에서 새 토큰 발급 (위 '재발급 절차' 참조)
Step 2: Railway 콘솔 → tai-api-prod 서비스 → Variables
        → SLACK_BOT_TOKEN1 값 업데이트 (새 토큰 붙여넣기)
Step 3: Railway 수동 배포 트리거
Step 4: 교체 후 검증 (아래 참조)
Step 5: 이전 토큰 값이 남아있는 모든 위치 삭제
        (Claude Code 대화 기록, 메모장, 클립보드 등)
```

**절대 금지**:
- 토큰 값을 Claude Code 대화창에 입력
- 토큰 값을 코드/문서에 하드코딩
- 토큰 값을 Git 커밋에 포함

---

## 교체 후 검증

### 검증 1: auth.test

```bash
# Owner가 로컬에서 실행 (결과 확인만, 터미널 기록 삭제 후)
curl -s -X POST https://slack.com/api/auth.test \
  -H "Authorization: Bearer [NEW_TOKEN]" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('ok'), d.get('bot_id'))"
# 기대: True + 기존 bot_id 동일
```

### 검증 2: tai_bot 채널 멤버십

교체 전 스크린샷과 비교하여 채널 목록 동일 확인.

### 검증 3: TAI 운영 발송 테스트

`send_slack_sync("OPS_EVENT", "INFO", "token-rotation-test")` 호출 후
`#tai-ops` 채널에서 메시지 수신 확인.

---

## Railway 환경변수 업데이트 참조

```
Railway Dashboard → tai-api-prod → Settings → Variables
→ SLACK_BOT_TOKEN1 → 수정
→ Save → Deploy (manual trigger)
```

또는 Railway MCP agent:
```
"Update SLACK_BOT_TOKEN1 environment variable in tai-api-prod service to [new value]"
```

---

## 현재 노출 상태

| 항목 | 노출 경로 | 조치 |
|------|-----------|------|
| `SLACK_BOT_TOKEN1` | Claude Code 대화 기록 (현 세션) | 교체 후 이전 토큰 자동 무효화 |
| `RAILWAY_TOKEN` | Railway MCP 인증 (세션 내부) | Railway Personal Token 재발급 권장 |

**우선순위**: `SLACK_BOT_TOKEN1` 교체 → 파일럿 구현 시작 전 완료 필수.

---

## Token Rotation 활성화 판단 기준

| 조건 | 결론 |
|------|------|
| TAI 현재 코드베이스에 Refresh Token 처리 없음 | 활성화 금지 |
| 활성화 원하는 경우 | 별도 WO 발행: Refresh Token 갱신 로직 구현 + 테스트 후 활성화 |
| 현 파일럿 범위 | Token Rotation 비활성 유지, 단순 재발급만 수행 |
