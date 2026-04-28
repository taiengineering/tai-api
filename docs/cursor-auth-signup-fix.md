# Cursor 작업지시서: auth.py register — sign_up() 방식으로 변경

> **파일**: `routers/auth.py` (28KB)
> **문제**: `admin.create_user()` → "User not allowed" (service_role key로도 실패)
> **해결**: `admin.create_user()` 대신 `auth.sign_up()` 사용

---

## 변경: register 함수 내 Supabase auth 호출 부분만 변경

### 기존 코드 (약 L240 부근)
```python
    try:
        auth_res = supabase.auth.admin.create_user({
            "email": req.email, "password": req.password, "email_confirm": True,
            "user_metadata": {"name": req.name, "phone": phone_normalized, "role_code": req.role_code}
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"계정 생성 실패: {str(e)}")
    if not auth_res.user:
        raise HTTPException(status_code=400, detail="회원가입 실패")
    auth_id = str(auth_res.user.id)
```

### 변경 코드
```python
    try:
        auth_res = supabase.auth.sign_up({
            "email": req.email,
            "password": req.password,
            "options": {
                "data": {"name": req.name, "phone": phone_normalized, "role_code": req.role_code}
            }
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"계정 생성 실패: {str(e)}")
    if not auth_res.user:
        raise HTTPException(status_code=400, detail="회원가입 실패")
    auth_id = str(auth_res.user.id)
```

### 핵심 차이
- `admin.create_user()` → service_role key 필수, "User not allowed" 발생
- `sign_up()` → anon key로 동작, Dashboard에서 signups 활성화되어 있으면 정상 작동
- `email_confirm: True` 제거 — sign_up()은 이 옵션 미지원
- `user_metadata` → `options.data`로 이동

### 주의
- `get_supabase()` (anon key) 사용 — `get_supabase_admin()` 불필요
- 기존에 추가한 `get_supabase_admin()` 함수는 그대로 두어도 됨 (다른 곳에서 필요할 수 있으므로)
- register 함수 첫 줄: `supabase = get_supabase()` 로 되돌리기 (현재 get_supabase_admin()이면)

## 검증

1. push 후 Railway 배포 대기
2. `taieng.co.kr/log-in` → 회원가입 탭
3. 이메일/비밀번호/이름/전화번호 입력 → 회원가입
4. "User not allowed" 에러 없이 성공 확인
