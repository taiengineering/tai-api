# Railway 환경변수 백업 방법

> 작성일: 2026-04-11

---

## 방법 1. Railway CLI (권장)

```bash
# CLI 설치 (맥)
brew install railway

# 로그인
railway login

# 프로젝트 연결 (tai-api 폴더에서)
railway link

# 환경변수 전체 추출
railway variables --json > railway_env_backup.json
```

## 방법 2. 대시보드
```
railway.app → tai-api 프로젝트
→ Settings → Variables → Raw Editor
→ 전체 선택(Cmd+A) → 복사 → 텍스트 파일 저장
```

---

## 보관 원칙

| 보관처 | 가능 여부 |
|---|---|
| 1Password / Bitwarden | ✅ 권장 |
| iCloud 메모 (잠금) | ✅ 가능 |
| USB 오프라인 | ✅ 가능 |
| 이메일·카카오톡 | ❌ 절대 금지 |
| GitHub 커밋 | ❌ 절대 금지 |
| 구글 드라이브 공유 | ❌ 절대 금지 |

---

## 현재 TAI 주요 환경변수 목록

```
BUILDING_API_KEY      data.go.kr 공통 키
DATA_GOV_SERVICE_KEY  법제처 전용 (미설정)
LAW_API_OC            law.go.kr 인증값 (taieng)
KMA_SERVICE_KEY       기상청 API Hub 전용
JUSO_API_KEY          도로명주소 API
SUPABASE_URL          Supabase 프로젝트 URL
SUPABASE_KEY          Supabase Service Key
MAIL_*                메일 발송 설정
```

## 백업 주기 권고
```
환경변수 변경 즉시 → 갱신 저장
분기 1회 → 정기 전체 백업
```
