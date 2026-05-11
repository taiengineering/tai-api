# 작업지시서: 카카오 OAuth 로그인 백엔드 연동

## 문제

카카오 OAuth는 Supabase Auth를 통해 성공하지만, OAuth로 생성된 auth.users ID와 TAI users 테이블 ID가 불일치하여 세션이 유지되지 않음.

| 시스템 | user_id | email |
|---|---|---|
| auth.users (카카오) | `ec34402f-...` | hetto@kakao.com |
| users 테이블 (이메일 가입) | `c4b3d044-...` | hetto@kakao.com |

## 해결: 백엔드 OAuth 로그인 엔드포인트

### 새 파일: `routers/auth_oauth.py`

```python
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from db.supabase_client import get_supabase
from uuid import uuid4
from datetime import datetime

router = APIRouter(prefix="/auth", tags=["auth-oauth"])

class OAuthLoginRequest(BaseModel):
    access_token: str
    provider: str = "kakao"  # kakao, naver, google

@router.post("/oauth-login")
async def oauth_login(body: OAuthLoginRequest):
    """
    소셜 로그인 후 프론트엔드가 Supabase access_token을 보내면:
    1. Supabase에서 토큰 검증 + 사용자 정보 조회
    2. TAI users 테이블에서 email로 기존 사용자 찾기
    3. 없으면 자동 생성
    4. /auth/login과 동일한 형식으로 응답
    """
    sb = get_supabase()
    
    # 1. Supabase access_token 검증
    try:
        user_response = sb.auth.get_user(body.access_token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"토큰 검증 실패: {str(e)}")
    
    auth_user = user_response.user
    email = auth_user.email
    if not email:
        raise HTTPException(status_code=400, detail="이메일 정보가 없습니다. 카카오 계정에 이메일이 등록되어 있는지 확인해 주세요.")
    
    meta = auth_user.user_metadata or {}
    name = meta.get("name") or meta.get("full_name") or meta.get("preferred_username") or ""
    avatar = meta.get("avatar_url") or meta.get("picture") or ""
    
    # 2. TAI users 테이블에서 기존 사용자 찾기
    result = sb.table("users").select("*").eq("email", email).maybe_single().execute()
    
    if result.data:
        # 기존 사용자 — 세션 반환
        user = result.data
        # provider 정보 업데이트 (최초 OAuth 연동 시)
        if not user.get("oauth_provider"):
            sb.table("users").update({
                "oauth_provider": body.provider,
                "oauth_linked_at": datetime.utcnow().isoformat(),
            }).eq("id", user["id"]).execute()
    else:
        # 신규 사용자 — 자동 생성
        new_id = str(uuid4())
        new_user = {
            "id": new_id,
            "email": email,
            "name": name,
            "role_code": "010",  # 기본 역할: 일반 사용자
            "oauth_provider": body.provider,
            "oauth_linked_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat(),
        }
        insert_result = sb.table("users").insert(new_user).execute()
        if not insert_result.data:
            raise HTTPException(status_code=500, detail="사용자 생성에 실패했습니다.")
        user = insert_result.data[0]
    
    # 3. /auth/login과 동일한 형식으로 응답
    return {
        "data": {
            "access_token": body.access_token,
            "refresh_token": "",  # OAuth는 refresh_token 불필요 (Supabase가 관리)
            "user": {
                "id": user["id"],
                "email": user.get("email", ""),
                "name": user.get("name", ""),
                "role_code": user.get("role_code", "010"),
                "company_id": user.get("company_id"),
                "company_name": user.get("company_name"),
            }
        }
    }
```

### main.py에 라우터 추가

```python
from routers.auth_oauth import router as auth_oauth_router
app.include_router(auth_oauth_router)
```

### DB 마이그레이션 (users 테이블에 OAuth 컬럼 추가)

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_linked_at TIMESTAMPTZ;
```

## 프론트엔드 (이미 반영됨)

`log-in.html`의 `handleOAuthCallback` 함수가 백엔드 `/auth/oauth-login`을 호출합니다.

## 플로우

```
[카카오 버튼 클릭]
  → Supabase signInWithOAuth('kakao')
  → 카카오 인증 화면
  → Supabase /callback
  → log-in.html#access_token=...
  → handleOAuthCallback() 실행
  → POST /auth/oauth-login { access_token }
  → 백엔드: 토큰 검증 → users 테이블 조회/생성
  → 응답: { data: { access_token, user: { id, email, name, ... } } }
  → saveSession() → mypage로 이동
```

## 테스트

1. 기존 이메일 사용자가 카카오로 로그인 → 기존 계정 연결
2. 신규 카카오 사용자 → 자동 회원가입
3. 로그인 후 mypage 정상 접근
4. access_token으로 API 호출 정상

## 주의사항

- `from db.supabase_client import get_supabase` (TAI API 규칙)
- Router/Service 분리는 추후 리팩토링 시 적용 (현재는 단일 파일로 구현)
- 에러 메시지는 한국어로
