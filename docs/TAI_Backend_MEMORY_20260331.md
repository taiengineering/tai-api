# TAI Backend Memory — 2026-03-31

## 오늘 완료된 작업

### 1. 역할 구조 DB 마이그레이션
- `roles` 테이블 010~022 10개 신규 등록
- `roles` 003~008 비활성화
- `users.role_code` 마이그레이션: 003→012, 004→014, 005→020, 006→022
- `system_codes` 그룹 헤더 + 신규 코드 삽입
- `role_permissions` 권한 복사

### 2. 신규 테이블

#### internal_api_registry
```sql
CREATE TABLE internal_api_registry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  group_name TEXT NOT NULL,
  api_name TEXT NOT NULL,
  method TEXT NOT NULL DEFAULT 'GET',
  endpoint TEXT NOT NULL,
  auth_required BOOLEAN DEFAULT TRUE,
  expect_status INT DEFAULT 200,
  description TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  sort_order INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```
- 21개 엔드포인트 등록 완료

#### report_api_registry
```sql
CREATE TABLE report_api_registry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  system_name TEXT NOT NULL,
  operator TEXT,
  official_api TEXT,          -- Y/PARTIAL/N/PUBLIC-UNCLEAR
  api_apply_url TEXT,
  can_use_for_auto_filing TEXT,
  recommendation TEXT,
  apply_status TEXT DEFAULT 'PENDING', -- PENDING/APPLIED/APPROVED/REJECTED
  apply_date DATE,
  approved_date DATE,
  api_key_issued BOOLEAN DEFAULT FALSE,
  notes TEXT,
  ...
);
```
- 5개 외부 시스템 등록 (고용24, 화관법민원24, 올바로, 전기안전공사, 세움터)

#### master_building_legal_rules 신규 코럼
- `online_system`, `system_url`, `automation_level`, `official_api_available`
- `api_apply_required`, `api_apply_url`, `auto_report_notes`

### 3. 미구현 라우터 (다음 세션 Code 창)

`docs/TASK_API_MONITOR_BACKEND_20260330.md` 참조

```python
# Part 1: /internal-api-registry 라우터
GET  /internal-api-registry          # 목록 (is_active=true, sort_order)
POST /internal-api-registry          # 등록
DELETE /internal-api-registry/{id}   # 비활성화 (soft delete)

# Part 2: /report-api-registry 라우터  
 GET  /report-api-registry           # 목록
POST /report-api-registry            # 등록
PATCH /report-api-registry/{id}      # 상태 수정 (apply_status, apply_date 등)
DELETE /report-api-registry/{id}     # 삭제

# Part 3: main.py㕏 래우터 등록
app.include_router(internal_api_registry.router)
app.include_router(report_api_registry.router)
```

### 4. API 상태 (2026-03-31)
- 서버 버전: v4.3.2
- 정상 200: 12개
- 404 미구현: 5개 (repair-brokerage, safety-management, consulting, inspection/schedules, internal-api-registry, report-api-registry)
- CORS 오류: equipment-assets 1개
- 405 메서드: legal-engine/diagnose/step1 (GET→POST 필요)
- 응답지연: engine-legal/stats (1832ms)
