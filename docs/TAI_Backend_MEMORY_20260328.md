# TAI Backend MEMORY — 2026-03-28

## 서버 정보
- API: api.taieng.co.kr (Railway)
- DB: Supabase (xntdkrjhgcscmqctdzyo)
- GitHub: taiengineering/tai-api
- 현재 버전: main.py **v3.8.0**

---

## 오늘 완료된 작업

### 1. legal_engine.py v4.1.2 ✅
- `/apply` 응답에서 `not_applicable` 전체 목록 제거 → 응답 경량화
- `not_applicable_count` (건수만) 응답에 포함
- DB(factories) 저장은 not_applicable 포함 전체 저장 유지
- `/result` 조회 시에도 not_applicable 제거

### 2. inspection_sets.equipment_set_id nullable ✅
- `equipment_set_id NOT NULL` → nullable 변경 (DB 마이그레이션)
- `/create-inspection-sets` 정상 동작 확인 (67개 생성)

### 3. inspection_checklist.py v1.1.0 ✅
- 7개 엔드포인트 구현 완료
- `/status`: 전체 조회 → 각각 count 쿼리 4개로 분리 (성능 최적화)
- DB 마이그레이션:
  - `safety_inspection_results`: inspection_id, inspection_set_item_id, result_code, note, photo_url, checked_at 추가
  - `work_schedules`: completed_at, inspector_name, summary 추가

### 4. MV 기반 성능 최적화 ✅
- MV 2개 생성 및 populate: `engine_equipment_summary`, `dashboard_stats`
- `GRANT SELECT ON engine_equipment_summary TO anon, authenticated, service_role` ← 핵심 수정
- `GRANT SELECT ON dashboard_stats TO anon, authenticated, service_role`

**engine_equipment.py v1.2.2:**
- `/stats`: count 쿼리 제거 → MV 단일 조회
- `/list`: Python 전체 조회 제거 → DB 측 `range()` 페이징

**admin_stats.py v1.0.0 (신규):**
- `GET /admin/stats`: dashboard_stats MV 기반
- `POST /admin/stats/refresh`: MV 수동 갱신

### 5. personnel.py v1.1.0 ✅
필드 정합성 보완:
- `/stats`: `matched_count`, `contracted_count`, `fee_total` 추가
- `/requests`: 신규 엔드포인트 (matching_requests PERSONNEL 기반)
- `/list`, `/agencies` 응답에 alias 필드 추가:
  - `contact_phone` = phone, `contact_email` = email
  - `service_regions` = region_sido
  - `max_factory_count` = max_clients, `current_factory_count` = current_clients
  - `representative_name`, `address` (safety_agencies)
- `POST /personnel`, `POST /agencies`: alias body 처리
- `POST /personnel/create`: alias 엔드포인트 추가
- `/verify`: `VERIFIED` 상태 추가 (DB에는 APPROVED로 저장)

### 6. repair.py v1.0.0 (신규) ✅
- prefix: `/repair`
- 대상 테이블: `repair_companies`, `matching_requests(request_type=REPAIR)`
- 엔드포인트:
  - `GET/POST /repair/companies`
  - `GET/PATCH /repair/companies/{id}`
  - `POST /repair/companies/{id}/verify`
  - `GET/POST /repair/requests`
  - `PATCH /repair/requests/{id}`
  - `GET /repair/stats`

---

## main.py 이력 주의사항

**중요**: 오늘 세션 중 main.py가 v3.2.0 구버전으로 덮어씌워지는 사고 발생.
원인: push_files로 여러 파일 동시 push 시 main.py SHA 충돌로 구버전이 올라감.
해결: main.py 단독 create_or_update_file로 복구.

**예방책**: main.py는 push_files에 포함하지 말고 항상 단독 create_or_update_file로 수정.

---

## 최종 성능 측정 결과

| API | 최적화 전 | 최적화 후 |
|-----|---------|---------|
| ee/list | 3.381s | ~0.4s (MV + DB 페이징) |
| ee/stats | 3.213s | ~0.5s (MV + count 제거) |
| admin/stats | 404 | ~0.4s (MV 권한 부여) |
| inspection/status | 2.231s | ~0.8s (count 쿼리 분리) |
| factories | 0.763s | 유지 |

---

## DB 마이그레이션 완료 목록

```sql
-- inspection_sets
ALTER TABLE inspection_sets ALTER COLUMN equipment_set_id DROP NOT NULL;

-- safety_inspection_results
ALTER TABLE safety_inspection_results
  ADD COLUMN IF NOT EXISTS inspection_id uuid,
  ADD COLUMN IF NOT EXISTS inspection_set_item_id uuid,
  ADD COLUMN IF NOT EXISTS result_code text DEFAULT 'NA',
  ADD COLUMN IF NOT EXISTS note text,
  ADD COLUMN IF NOT EXISTS photo_url text,
  ADD COLUMN IF NOT EXISTS checked_at timestamptz;

-- work_schedules
ALTER TABLE work_schedules
  ADD COLUMN IF NOT EXISTS completed_at date,
  ADD COLUMN IF NOT EXISTS inspector_name text,
  ADD COLUMN IF NOT EXISTS summary text;

-- MV 권한
GRANT SELECT ON engine_equipment_summary TO anon, authenticated, service_role;
GRANT SELECT ON dashboard_stats TO anon, authenticated, service_role;
```

---

## 라우터 파일 목록 (최종 v3.8.0)

| 파일 | prefix | 버전 | 상태 |
|------|--------|------|------|
| auth.py | /auth | v3.2.0 | ✅ |
| legal_engine.py | /legal-engine | v4.1.2 | ✅ |
| ksic_engine.py | /ksic-engine | v3 | ✅ |
| factory_process_v3.py | /factory-process | v3 | ✅ |
| process_management.py | /process-management | v1.1 | ✅ |
| building_register.py | /building-register | v2.3.0 | ✅ |
| quotes.py | /quotes | v1 | ✅ |
| report_forms.py | /report-forms | v1.0.0 | ✅ |
| system_codes.py | /system-codes | v2.0.0 | ✅ |
| equipment_assets.py | /equipment-assets | v1.2.0 | ✅ |
| engine_equipment.py | /engine-equipment | v1.2.2 | ✅ |
| engine_model.py | /engine-model | v1.0.0 | ✅ |
| personnel.py | /personnel | v1.1.0 | ✅ |
| repair.py | /repair | v1.0.0 | ✅ (신규) |
| inspection_checklist.py | /inspection | v1.1.0 | ✅ |
| admin_stats.py | /admin | v1.0.0 | ✅ |
| contracts.py | — | — | ⚠️ 503 미확인 |
| contacts.py | — | — | ✅ |
| education.py | — | — | ✅ |
| notifications.py | — | — | ✅ |
| schedule_engine.py | — | — | ✅ |
| roles.py | — | — | ✅ |
| teams.py | — | — | ✅ |
| areas.py | — | — | ✅ |
| buildings.py | — | — | ✅ |
| inspection_sets.py | — | — | ✅ |
| work_schedules.py | — | — | ✅ |
| companies.py | /companies | v1 | ✅ |
| factories.py | /factories | v1 | ✅ |
| users.py | /users | v1 | ✅ |

---

## MV 정보

| MV 이름 | 행 수 | 설명 | RPC |
|---------|-------|------|-----|
| engine_equipment_summary | ~882행 | 설비 집계 | refresh_engine_equipment_summary |
| dashboard_stats | 1행 | 대시보드 통계 | refresh_dashboard_stats |

---

## 다음 진행 사항

| 순서 | 작업 | 내용 |
|------|------|------|
| 1 | contracts 503 | Railway 런타임 로그 확인 필요 |
| 2 | health 엔드포인트 | server_ip 임시 추가 → 원복 필요 |
| 3 | system_codes CRUD | POST/PATCH/DELETE 미구현 |
| 4 | 프론트엔드 연동 | personnel-list.html, repair 페이지 |

---

## 내일 첫 작업 테스트 명령어

```bash
# 성능 테스트
python3 -c "
import requests, time
BASE = 'https://api.taieng.co.kr'
FID  = 'bbbbbbbb-0003-0003-0003-000000000003'
for name, url in [
    ('ee/list',  f'{BASE}/engine-equipment/list'),
    ('ee/stats', f'{BASE}/engine-equipment/stats'),
    ('admin',    f'{BASE}/admin/stats'),
    ('insp',     f'{BASE}/inspection/status/{FID}'),
]:
    s = time.time()
    r = requests.get(url)
    print(f'{name}: {time.time()-s:.3f}s  {r.status_code}')
"

# repair 테스트
curl -s "https://api.taieng.co.kr/repair/stats" | python3 -m json.tool
curl -s "https://api.taieng.co.kr/personnel/stats" | python3 -m json.tool
```
