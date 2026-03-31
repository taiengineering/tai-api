# TAI Backend Memory — 2026-03-31 (FINAL)

## 현재 API 버전
- **main.py**: v4.7.0
- **Railway**: api.taieng.co.kr
- **Supabase**: xntdkrjhgcscmqctdzyo

---

## 오늘 세션 완료 작업 전체 목록

### 1. Rolling 방식 전환
- `inspection_sets.py` **v1.5.0**
  - `_build_next_schedule_row()`: 오늘 이후 첫 1건만 생성
  - `_next_planned_from()`: 계산 함수 신규
  - `GET /inspection-sets/preview-schedule`: 캘린더용 가상 렌더링 API
  - `end_date` 파라미터 제거
  - POST /anchor/bulk: Rolling 1건 생성 방식으로 전환
- `inspection_checklist.py` **v1.4.0**
  - `POST /complete/{id}`: 완료 시 다음 회차 1건 자동 INSERT
  - `schedule_end_date` 초과 시 생성 안 함
  - `assigned_user_id=NULL`
  - `next_schedule_created` / `next_planned_date` 응답 포함
- **DB migration**: `rolling_schedule_cleanup_keep_one_scheduled_per_set`
  - inspection_set_id별 SCHEDULED 1건만 유지

### 2. 테스트 계정 Auth 등록
- `auth.py` **v3.3.0**
  - `POST /auth/seed-test-accounts`: 4개 계정 Supabase Auth 등록 + auth_id 연결
  - 대상: admin@tai.com, safety-mgr@korean-safe.co.kr, worker@tai.com, worker@korean-safe.co.kr
  - 비밀번호: tai1234!

### 3. 회사등록 온보딩 API
- `companies.py` **v2.0.0** (15개 엔드포인트)
  - `POST /companies/onboarding`: 회사+담당자+시설 통합 1-step 등록
  - `GET/POST /companies/{id}/contacts`: 담당자 CRUD
  - `PATCH/DELETE /companies/{id}/contacts/{cid}`
  - `GET /companies/{id}/contracts`: 계약 이력
  - `POST/DELETE /companies/{id}/files`: 파일 등록/삭제
  - `PATCH /companies/{id}/contract-url`: 전자계약서 URL
- `factories.py` **v2.0.0**
  - `GET/POST /factories/{id}/contacts`: 시설 담당자 CRUD
  - `PATCH/DELETE /factories/{id}/contacts/{cid}`

### 4. 회원가입 + 사업자번호 중복 확인
- `auth.py` **v3.4.0**
  - `RegisterRequest`: `business_number`, `representative_name` 필드 추가
  - companies INSERT 시 반영, 이메일 중복 확인 추가
  - 사업자번호 중복 시 기존 회사 연결
- `companies.py` **v2.1.0**
  - `GET /companies/check-biz?business_number=`: 사업자번호 중복 확인
  - 하이픈 자동 제거, 10자리 검증, 회사명 반환

### 5. 이벤트 기반 신고·보고 일정 트리거
- `event_trigger.py` **v1.0.0** (신규)
  - `trigger_event_schedules()`: 공통 트리거 함수
  - diagnosis_rule_results에서 REPORT/NOTIFY + cycle_base_type 매칭
  - 30일 이내 중복 체크 후 work_schedules INSERT (source_type='EVENT')
  - `POST /event-schedules/trigger`: 수동 트리거
  - `GET /event-schedules/factory/{id}`: 이벤트 일정 목록
- `users.py` **v2.1.0**
  - `PATCH /users/{id}/role`: role_code='002' 설정 시 factory_id 있으면 APPOINTMENT 트리거
- `factories.py` **v2.1.0**
  - `PATCH /factories/{id}`: 변경 시 CHANGE 트리거, status_code='INACTIVE' 시 CLOSURE 트리거
- `equipment_assets.py` **v1.1.0**
  - `POST /equipment-assets`: 신규 등록 시 INSTALL 트리거
- **main.py v4.6.0**: event_trigger_router 등록

### 6. 작업자 명부 API
- `worker_registry.py` **v1.0.0** (신규)
  - `POST /worker-registry`: 수동 1건 등록
  - `POST /worker-registry/bulk-import`: xlsx/csv 일괄 등록 (직종명 → WJT 코드 자동 매핑)
  - `GET /worker-registry`: 목록 조회 (factory_id/job_type_code/is_active/keyword 필터)
  - `GET /worker-registry/template`: 엑셀 템플릿 다운로드 (openpyxl → CSV fallback)
  - `PATCH /worker-registry/{id}`: 수정
  - `DELETE /worker-registry/{id}`: 비활성화
  - `POST /worker-registry/{id}/invite`: 앱 초대 문자 (invite_sent_at 업데이트)
- **requirements.txt**: openpyxl 추가
- **main.py v4.7.0**: worker_registry_router 등록

---

## 현재 파일 버전 현황

| 파일 | 버전 | 비고 |
|---|---|---|
| main.py | v4.7.0 | worker_registry_router 추가 |
| routers/auth.py | v3.4.0 | seed + register 사업자/대표자 |
| routers/companies.py | v2.1.0 | 온보딩+contacts+files+check-biz |
| routers/factories.py | v2.1.0 | contacts+CHANGE/CLOSURE 트리거 |
| routers/users.py | v2.1.0 | APPOINTMENT 트리거 |
| routers/equipment_assets.py | v1.1.0 | INSTALL 트리거 |
| routers/event_trigger.py | v1.0.0 | 신규 |
| routers/worker_registry.py | v1.0.0 | 신규 |
| routers/inspection_sets.py | v1.5.0 | Rolling 1건 생성 |
| routers/inspection_checklist.py | v1.4.0 | 완료 후 다음 회차 자동 생성 |

---

## 테스트 계정 (Supabase Auth 등록 완료)

| 이메일 | 비밀번호 | role | 용도 |
|---|---|---|---|
| hetto@kakao.com | tai1234! | 001 | superadmin |
| admin@tai.com | tai1234! | 002 | admin 로그인 |
| safety-mgr@korean-safe.co.kr | tai1234! | 002 | tadmin 테스트 |
| worker@tai.com | tai1234! | 014 | 작업자 계정 |
| worker@korean-safe.co.kr | tai1234! | 014 | 작업자 계정 |

> 신규 계정 등록 시: `POST /auth/seed-test-accounts` 1회 호출 필요 (이미 완료됨)

---

## 핵심 설계 원칙 (누적)

### Rolling 방식
```
anchor 설정 → 오늘 이후 첫 번째 planned_date 1건 INSERT
완료 처리 → 완료일 + delta = 다음 planned_date 1건 INSERT
schedule_end_date 있으면 초과 시 생성 안 함
COMPLETED 절대 건드리지 않음
assigned_user_id=NULL
```

### 이벤트 트리거
```
APPOINTMENT: PATCH /users/{id}/role → role_code=002 + factory_id
CHANGE:      PATCH /factories/{id} → 변경 발생 시
CLOSURE:     PATCH /factories/{id} → status_code=INACTIVE
INSTALL:     POST /equipment-assets → 신규 등록 시
트리거 실패는 try/except 처리 (메인 응답 영향 없음)
```

### 고정 경로 우선 원칙
```
모든 고정 경로(e.g. /manual, /check-biz, /template, /bulk-import)는
동적 경로(/{id}) 앞에 반드시 선언
```

---

## PENDING 작업 (다음 세션)

| 작업 | 상세 |
|---|---|
| POST /auth/seed-test-accounts 호출 | Railway 배포 후 1회 실행 |
| 12개 법령 수집 | data.go.kr API |
| 80개 report-obligation rules form_code 매핑 | |
| 건설섹터 알고리즘 구현 | 하청 인원 포함, 공종별 분기 |
| Cloudflare Zero Trust Access | taieng.co.kr 잠금 |
| **공지예외주장 제출 기한: 2026-04-28** | patent.go.kr |
