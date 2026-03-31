# TAI Backend MEMORY — 2026-03-31 마감

## 오늘 완료된 작업 전체

---

### 1. 교육 발령·이수 관리 (education_assign.py v1.0.0) — 기존 완성 확인

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | /education/master | 교육 마스터 목록 |
| GET | /education/company-settings | 회사별 링크 목록 (effective_url 포함) |
| PUT | /education/company-settings/{education_id} | UPSERT |
| DELETE | /education/company-settings/{education_id} | 기본값 복원 |
| POST | /education/assign | 교육 발령 다건 |
| GET | /education/assignments/summary | 요약 통계 |
| GET | /education/assignments | 목록 (effective_url 포함) |
| PATCH | /education/assignment/{id}/complete | 이수 완료 |
| POST | /education/assignment/{id}/certificate | 이수증 URL 저장 |
| POST | /education/assignments/expire | 만료 처리 (크론용) |

- **cron_job_master 신규 등록**: `EDU_EXPIRE_DAILY` — 매일 01:00 — `POST /education/assignments/expire`

---

### 2. factory_process_v3.py v3.2.0 — KCSC 검색·등록

**신규 엔드포인트:**
- `GET /factory-process/kcsc/search?q=&limit=` — kcsc_process_master ILIKE 검색
  - 반환: `{kcs_code, process_name, level1_name, level2_name, construction_type}`
  - 고정경로 선언 (`/{factory_id}` 앞)

**POST /{factory_id}/processes source='KCSC' 분기 추가:**
- `kcs_code` 필수 → `kcsc_process_master` 조회 → 중복 체크 → `factory_process` INSERT
- `process_id = kcs_code`, `source = 'KCSC'`, `process_name_manual = process_name`
- `SOURCE_BADGE['KCSC'] = 'KCSC'` 추가

---

### 3. 버그 수정 — work_schedules 컬럼 누락

**원인 파악 (Supabase 로그):**
- `GET /event-schedules/factory/{factory_id}` → 400 반복
  - `work_schedules?order=created_at.desc` → 컬럼 없어서 오류
- `GET /education/assignments/summary` → 400 반복
  - `factory_id=cc000003` (문자열) → UUID 타입 불일치 (프론트 수정 필요)

**조치:**
```sql
ALTER TABLE work_schedules
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
CREATE INDEX IF NOT EXISTS idx_work_schedules_created_at ON work_schedules(created_at DESC);
```

**프론트 전달 사항:** factory_id는 UUID 형식으로 전달 (`cc000003` 형식 사용 불가)

---

### 4. 법령진단 잠금 로직 (diagnosis.py v1.0.0) — 신규

**DB Migration — `diagnosis_purchases` 테이블:**
```sql
CREATE TABLE diagnosis_purchases (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id),
  factory_id UUID NOT NULL REFERENCES factories(id),
  sector     TEXT NOT NULL,        -- BUILDING / MANUFACTURING / CONSTRUCTION 등
  step       INTEGER NOT NULL,     -- 2 or 3 or 99(종합리포트)
  price      INTEGER NOT NULL,
  status     TEXT DEFAULT 'PAID',  -- PAID / REFUNDED
  paid_at    TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ,          -- NULL = 영구
  created_at TIMESTAMPTZ DEFAULT now()
);
```
인덱스: `(factory_id, step, status)`, `(company_id)`

**API — `GET /diagnosis/access-check?factory_id=&step=`:**

| step | 조건 | 응답 |
|------|------|------|
| 1 | 항상 | `has_access: true, reason: "FREE"` |
| 2/3/99 | 구매 없음 | `has_access: false, reason: "NO_PURCHASE"` |
| 2/3/99 | expires_at 초과 | `has_access: false, reason: "EXPIRED"` |
| 2/3/99 | PAID + 유효 | `has_access: true, reason: "PAID"` |

- SaaS contract_level 체크 없음 (법령진단은 완전 별도 서비스)

---

### 5. main.py v4.9.0

- `diagnosis_router` 등록 (`/diagnosis` prefix)
- Railway 배포 완료

---

## 현재 API 버전

```
main.py                      v4.9.0
routers/auth.py              v3.4.0
routers/companies.py         v2.1.0
routers/factories.py         v2.1.0
routers/users.py             v2.1.0
routers/equipment_assets.py  v1.1.0
routers/event_trigger.py     v1.0.0
routers/worker_registry.py   v1.0.0
routers/inspection_sets.py   v1.5.0
routers/inspection_checklist.py v1.4.0
routers/education_assign.py  v1.0.0
routers/factory_process_v3.py v3.2.0
routers/diagnosis.py         v1.0.0  ← NEW
```

---

## PENDING 작업

1. `POST /auth/seed-test-accounts` 호출 (Railway 배포 후 미실행)
2. 12개 법령 수집 (data.go.kr: 근로기준법, 소음진동관리법 등)
3. 80개 report-obligation rules → form_code 매핑
4. 건설섹터 알고리즘 (하청 인원 포함, 공종별 분기)
5. Cloudflare Zero Trust Access (taieng.co.kr 잠금)
6. 공지예외주장 제출 기한: **2026-04-28** (patent.go.kr)
7. 프론트: `factory_id` UUID 형식으로 수정 (cc000003 → 실제 UUID)
8. 프론트: `education-setting.html`, `education-list.html` 구현
