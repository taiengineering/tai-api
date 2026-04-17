# BE-09: auth.users ↔ public.users UUID 동기화 작업지시서

**작성일:** 2026-04-17  
**조사일:** 2026-04-17  
**상태:** ✅ 이미 완료됨 (추가 작업 불필요)

---

## 배경

`auth.users.id` ≠ `public.users.id` UUID 불일치 이슈 보고.
57개 FK, 30+ 테이블 영향 우려.
방법 B(탄 컴럼 추가) 권장 — 기존 FK 미수정, 안전.

---

## 실제 조사 결과 (2026-04-17)

### 현황 요약

| 구분 | 수 | 설명 |
|---|---|---|
| public.users 전체 | 17명 | 전체 사용자 |
| UUID 불일치 | 10명 | public.id ≠ auth.id |
| auth.users 미연결 | 7몁 | scen-*.test 더미 계정 |
| UUID 일치 | 0명 | 전원 불일치 |
| FK 수 | 57개 | public.users.id 참조 |

### 불일치 10명 상세

| 이메일 | 이름 | public.id (앞 8자) | auth.id (앞 8자) |
|---|---|---|---|
| admin@tai.com | 김관리자 | 251c81a1 | 4816c780 |
| hetto@kakao.com | 심태왕 | c4b3d044 | ec34402f |
| inicis@taieng.co.kr | 이니시스심사 | 90142a24 | b658ccd3 |
| lee.jeong@taieng.co.kr | 이정 | 4229ea5b | aaaaaaaa |
| newuser123@gmail.com | 테스트유저 | d01ff695 | 81bb1b33 |
| safety-mgr@korean-safe.co.kr | 이안전 | cc000005 | 488144a8 |
| sim.taewang@taieng.co.kr | 심태왕 | e6d6da1b | aaaaaaaa |
| testuser@test.com | 테스트사용자 | 6d075f6d | 6f0f66ee |
| worker@korean-safe.co.kr | 박작업 | cc000006 | cbd201bc |
| worker@tai.com | 이작업자 | 0187c156 | 1fbc0169 |

---

## 방법 B 이미 완료됨 — 추가 작업 불필요

### 원래 우려했던 문제

FastAPI JWT 인증 시 `auth.users.id`(≠`public.users.id`)를 참조하면
`public.users` 및 모든 FK 테이블 JOIN 실패.

### 실제 현황 — 방법 B 자체가 이미 적용됨

**1. `auth_id` 코럼 존재** (public.users 테이블)
```sql
column: auth_id  uuid  DEFAULT NULL
```

**2. UNIQUE INDEX 2개 존재**
```sql
CREATE UNIQUE INDEX idx_users_auth_id ON public.users(auth_id);
CREATE UNIQUE INDEX users_auth_id_unique ON public.users(auth_id);
```

**3. 10명 전원 `auth_id` 올바르게 세팅됨**
```
확인 쾼리 결과:
  auth_id_filled = 10  (불일치 10명 전원 정상 세팅)
  auth_id_null   =  7  (scen-*.test 더미 계정 — auth.users 미연결)
  total          = 17
```

**4. API 코드 전체 `auth_id` 기반 조회 이로 돈**
```python
# routers/auth.py 전 엔드포인트에서 확인

# get_current_user()
res = supabase.table("users").select("*").eq("auth_id", str(ur.user.id)).limit(1).execute()

# verify_token()
res = supabase.table("users").select("*").eq("auth_id", str(ur.user.id)).limit(1).execute()

# get_me()
res = supabase.table("users").select("*").eq("auth_id", str(ur.user.id)).limit(1).execute()

# update_me()
res = supabase.table("users").select("id").eq("auth_id", str(ur.user.id)).limit(1).execute()

# register() — 신규 가입 시 auth_id 자동 저장
supabase.table("users").insert({"auth_id": auth_id, ...}).execute()
```

---

## FK 57개 참조 테이블 리스트

모든 FK는 `public.users.id` 참조.
API는 `auth_id`로 로그인 후 `users.id`를 가져었 FK JOIN하므로 **문제 없음**.

| 테이블 | 참조 코럼 |
|---|---|
| base_audit_fields | created_by, updated_by |
| company_education_setting | created_by |
| connect_providers | user_id |
| construction_inspections | inspector_id, created_by, updated_by |
| construction_site_processes | created_by, updated_by |
| construction_sites | created_by, updated_by, manager_id |
| construction_workers | user_id, created_by, updated_by |
| construction_works | assigned_manager_id, ptw_approved_by, created_by, updated_by |
| corrective_actions | assigned_user_id |
| ... (총 57개) | ... |

---

## 더미 계정 7명 (auth.users 미연결)

| 이메일 | 이름 | 비고 |
|---|---|---|
| choi.gongjang@scen-d.test | 최공장 | 건설 더미 계정 |
| hwang.ds@scen-bp.test | 황대성 | 범위통합 더미 |
| jang.bh@scen-dp.test | 장병호 | 더미 |
| jung.gongsa@scen-c.test | 정공사 | 더미 |
| kang.hs@scen-cp.test | 강현수 | 더미 |
| park.gunju@scen-b.test | 박건주 | 더미 |
| yoon.sy@scen-ap.test | 윤서영 | 더미 |

→ auth.users 연결 없으나 로깄인할 필요가 없는 더미 데이터이므로 **방치 정상**.

---

## 결론

BE-09는 **이미 완료된 상태**입니다.

| 체크리스트 | 상태 |
|---|---|
| auth_id 코럼 존재 | ✅ |
| UNIQUE INDEX | ✅ (2개) |
| 10명 auth_id 세팅 | ✅ |
| API 코드 auth_id 기반 | ✅ |
| 신규 가입 시 auth_id 자동 저장 | ✅ |
| DB 백업 | ❌ 미완료 (생략 가능) |

**다른 창 DB 쓰기 금지 정책:** 이미 적용 중 — 기존 코드 일관성 유지.

---

## 선택적 추가 작업 (필수 아님)

1. **scen-*.test 7명 auth.users 연결** — 테스트 시나리오 확장 시 필요할 수 있음
2. **RLS 정첸에서 `auth.uid()` 대신 `auth_id` 기반 정첸 정비** — Supabase 직접 크라이언트 사용 시 필요
3. **`public.users.id`를 auth.users.id로 전체 교체** — 방법 A, FK 57개 수정 필요, 초고위험 미권장
