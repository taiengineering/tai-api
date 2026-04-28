# Cursor 작업지시서: auth.py — service_role key 적용

> **파일**: `routers/auth.py` (28KB)
> **문제**: register에서 `supabase.auth.admin.create_user()` 호출 시 "User not allowed" 에러
> **원인**: `SUPABASE_KEY` = anon key → admin API 권한 없음
> **해결**: admin 작업에 `SUPABASE_SERVICE_KEY` (service_role key) 사용

---

## 변경 1: 파일 상단 환경변수 추가 (L17 부근)

기존:
```python
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
```

변경:
```python
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", SUPABASE_KEY)
```

## 변경 2: admin용 클라이언트 함수 추가 (get_supabase 아래)

기존:
```python
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)
```

변경 (get_supabase는 유지, 아래에 추가):
```python
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def get_supabase_admin():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
```

## 변경 3: register 함수에서 admin client 사용

register 함수 내부 첫 줄:
```python
# 기존
supabase = get_supabase()
```
→
```python
# 변경
supabase = get_supabase_admin()
```

## 변경 4: seed-test-accounts도 동일 적용

seed_test_accounts 함수 내부 첫 줄:
```python
# 기존
supabase = get_supabase()
```
→
```python
# 변경
supabase = get_supabase_admin()
```

## 요약

- `get_supabase()` = anon key → 로그인, 조회 등 일반 작업
- `get_supabase_admin()` = service_role key → 회원가입(admin.create_user), 시드 등 admin 작업
- Railway 환경변수 `SUPABASE_SERVICE_KEY`가 이미 존재하므로 추가 설정 불필요

## 검증

1. `taieng.co.kr/log-in` → 회원가입 탭
2. 이메일/비밀번호/이름/전화번호 입력
3. 회원가입 성공 확인
4. 로그인 성공 확인
