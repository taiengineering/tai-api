# TAI 백업 정책 및 현황

> 작성일: 2026-04-11  
> 상태: 확인 완료

---

## 저장소별 백업 현황

### 1. 코드 — GitHub ✅
- tai-api, tai-admin, taieng 3개 repo
- 커밋 단위 영구 보관, 언제든 롤백 가능
- 오늘까지 커밋 정상

### 2. DB — Supabase Pro ✅
- 플랜: **Pro** 사용 중
- 자동 백업: 매일 1회 (pg_dumpall)
- 보관 기간: **최근 7일치**
- 현재 DB 크기: 약 850MB+ (15GB 미만 → 논리 백업)
- 복구 위치: Supabase 대시보드 → Database → Backups → Scheduled

**PITR (Point-in-Time Recovery) 옵션:**
- 7일 보관: $100/월 추가
- 분 단위 복구 가능
- MVP 초기에는 불필요, 고객 증가 시 검토

### 3. 서버 — Railway ✅
- Stateless 서버, 코드는 GitHub에 보관
- 장애 시 즉시 재배포 가능
- **환경변수는 Railway 외부에 별도 보관 필요**

### 4. 프론트 — Cloudflare Pages ✅
- GitHub 연동 자동 배포 구조
- 코드가 곧 백업

---

## Railway 환경변수 백업 방법

```bash
# CLI 방법 (권장)
brew install railway
railway login
railway link
railway variables --json > railway_env_backup.json
```

또는 Railway 대시보드 → Settings → Variables → Raw Editor → 전체 복사

**보관처:** 1Password, Bitwarden 등 비밀번호 관리자  
**절대 금지:** 이메일·카카오톡 전송, GitHub 커밋, 공유 드라이브

---

## 리스크 및 조치

| 리스크 | 조치 |
|---|---|
| Supabase 7일 이전 데이터 복구 불가 | PITR 검토 (고객 증가 후) |
| Railway 환경변수 미백업 | 1Password에 즉시 저장 권고 |
| GitHub Public Repo | 민감 정보 코드에 포함 금지 (환경변수로 관리 중) |
