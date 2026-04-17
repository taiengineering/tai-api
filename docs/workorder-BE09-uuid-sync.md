# BE-09: auth.users ↔ public.users UUID 동기화

> **작성일**: 2026-04-17
> **위험도**: 🔴 HIGH — 57개 FK, 30+ 테이블 영향
> **반드시 별도 세션에서 신중하게 진행**

---

## 문제

public.users.id와 auth.users.id가 **전원(10명) 불일치**.
JWT의 sub(auth.users.id)로 API를 호출하면 public.users에서 찾을 수 없어 FK 제약 위반 발생.

| email | public.users.id | auth.users.id |
|---|---|---|
| hetto@kakao.com | c4b3d044-... | ec34402f-... |
| sim.taewang@taieng.co.kr | e6d6da1b-... | aaaaaaaa-0001-... |
| lee.jeong@taieng.co.kr | 4229ea5b-... | aaaaaaaa-0002-... |
| admin@tai.com | 251c81a1-... | 4816c780-... |
| (외 6명) | ... | ... |

## 영향 범위

57개 FK 제약, 30+ 테이블:
construction_sites, construction_works, construction_workers, construction_inspections,
work_schedules, work_assignments, safety_inspections, corrective_actions,
inspection_sets, tbm_meetings, tbm_attendees, payments, education_assignment,
worker_registry, posts, notification_logs, 외 다수

## 접근 방법 (2가지 중 선택)

### 방법 A: public.users.id → auth.users.id로 변경 (권장)

1. 전체 FK 제약 임시 DROP
2. 매핑 테이블로 public↔auth UUID 매핑 생성
3. 참조하는 모든 테이블 UPDATE (old_id → new_id)
4. public.users.id UPDATE
5. FK 제약 재생성
6. 검증

장점: 구조적으로 깨끗. JWT sub = public.users.id 직접 일치.
단점: 대규모 마이그레이션, 실패 시 데이터 손상 위험

### 방법 B: public.users에 auth_uid 컨럼 추가

1. `ALTER TABLE public.users ADD COLUMN auth_uid UUID`
2. 매핑 UPDATE
3. 인증 미들웨어(dependencies.py)에서 auth_uid로 조회 → public user 반환

장점: 기존 FK 미수정, 안전
단점: 모든 API에서 인증 후 2단계 조회 (auth_uid → user.id)

## 전제 조건

- 작업 전 DB 백업 필수
- 작업 중 서비스 일시 중단 가능성 있음
- 테스트: 방법 선택 후 1명으로 먼저 실행, 전체 확장

## 검증 스크립트 (마이그레이션 후)

```sql
SELECT u.id, u.email, au.id AS auth_id,
  CASE WHEN u.id = au.id THEN '✅' ELSE '❌' END AS match
FROM public.users u
JOIN auth.users au ON au.email = u.email;
```

## 🔴 금지사항

1. legal_engine.py 수정 금지
2. FK DROP 전 백업 필수
3. 작업 중 다른 창에서 DB 쓰기 금지
