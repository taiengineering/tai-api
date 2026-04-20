# 점검항목 세팅 — 플랜별 조합형 프리필 작업지시서 v2

## 1. 개요

안전관리자가 설비를 등록하고 점검항목을 세팅할 때:
- **L1 (낮은 플랜)**: 빈 화면 → 직접 항목 추가 (조합형)
- **L2+ (높은 플랜)**: 추천 항목 프리필 → 수정/삭제/추가 (같은 조합형 UI)

UI는 하나. 시작 상태만 다름. 템플릿 선택 UI 없음.

**프론트 위치: `inspection-anchor.html`에 병합** (별도 페이지 만들지 않음)

---

## 2. 기존 인프라

### 이미 있는 것
| 테이블 | 건수 | 역할 |
|---|---|---|
| `inspection_master` | 577건, 47개 설비유형 | 점검항목 마스터 (프리필 소스) |
| `inspection_sets` | 324건 | 점검세트 (법령엔진 자동생성) |
| `inspection_set_items` | 67건 | 프로덕션 점검항목 (거의 비어있음) |
| `equipment_assets` | 85건 | 등록된 설비 |
| `price_saas_plan` | 10건 | SaaS 플랜 (L1~L4, sector별) |

### inspection_master 보강 필요 컬럼
sector, check_type, risk_type, pass_description, fail_action, related_service, is_mandatory, threshold_value, threshold_operator, unit

### 기존 프론트 페이지
- `tadmin/.../inspection-anchor.html` (49KB) — 점검앵커관리
- `tadmin/.../construction-inspection-anchor.html` (45KB) — 건설 점검앵커관리

---

## 3. 플랜 분기 기준

| 플랜 | tier | 프리필 |
|---|---|---|
| INDUSTRY_L1 / FACILITY_L1 | 1 | ❌ 빈 화면 |
| INDUSTRY_L2+ / FACILITY_L2+ | 2+ | ✅ 추천항목 프리필 |
| CONSTRUCTION 전체 | - | ✅ 프리필 (건설은 L1부터 제공) |

---

## 4. 백엔드 작업

### 4-1. DDL

```sql
-- inspection_master 보강
ALTER TABLE inspection_master
  ADD COLUMN IF NOT EXISTS sector VARCHAR(50),
  ADD COLUMN IF NOT EXISTS check_type VARCHAR(20) DEFAULT 'BOOLEAN',
  ADD COLUMN IF NOT EXISTS risk_type VARCHAR(30),
  ADD COLUMN IF NOT EXISTS pass_description TEXT,
  ADD COLUMN IF NOT EXISTS fail_action TEXT,
  ADD COLUMN IF NOT EXISTS related_service TEXT,
  ADD COLUMN IF NOT EXISTS is_mandatory BOOLEAN DEFAULT false,
  ADD COLUMN IF NOT EXISTS threshold_value TEXT,
  ADD COLUMN IF NOT EXISTS threshold_operator VARCHAR(10),
  ADD COLUMN IF NOT EXISTS unit VARCHAR(20);

-- inspection_set_items 보강
ALTER TABLE inspection_set_items
  ADD COLUMN IF NOT EXISTS check_type VARCHAR(20) DEFAULT 'BOOLEAN',
  ADD COLUMN IF NOT EXISTS risk_type VARCHAR(30),
  ADD COLUMN IF NOT EXISTS pass_description TEXT,
  ADD COLUMN IF NOT EXISTS fail_action TEXT,
  ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'MANUAL',
  ADD COLUMN IF NOT EXISTS master_item_id UUID REFERENCES inspection_master(id),
  ADD COLUMN IF NOT EXISTS threshold_value TEXT,
  ADD COLUMN IF NOT EXISTS unit VARCHAR(20),
  ADD COLUMN IF NOT EXISTS check_method VARCHAR(20);
```

### 4-2. 신규 엔드포인트

#### GET /inspection-checklist/prefill
- equipment_std + company_id → 플랜 확인 → 프리필 or 빈 배열

#### POST /inspection-checklist/setup
- inspection_set_id + items → 일괄 저장 (기존 soft delete → 새로 INSERT)

### 4-3. 파일 위치
- `routers/inspection_setup.py` 신규
- `routers/inspection_checklist.py` (26KB) 기존 — 건드리지 않음

---

## 5. 프론트엔드 작업 — inspection-anchor.html 병합

### 5-1. 왜 병합인가

현재 `inspection-anchor.html`의 안전관리자 흐름:
```
점검세트 목록 → 세트 선택 → 앵커(이전점검일) 설정 → 일정 생성
```

여기에 "점검항목 세팅"이 빠져있음. 별도 페이지로 만들면 안전관리자가 두 곳을 오가야 함.

### 5-2. 병합 후 흐름

```
점검세트 목록 → 세트 선택 → [점검항목 세팅] + [앵커 설정] → 일정 생성
```

### 5-3. UI 구조 (inspection-anchor.html 수정)

점검세트 상세 영역에 **탭 또는 섹션 추가**:

```
┌─────────────────────────────────────────────────────────┐
│ 점검앵커관리                                              │
├─────────────────────────────────────────────────────────┤
│ [점검세트 목록]                                           │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ☐ No. │ 점검세트명        │ 주기  │ 상태          │ │
│ │ 1     │ 지게차 일상점검    │ 매일  │ PENDING_ANCHOR│ │
│ │ 2     │ 소화기 정기점검    │ 6개월 │ ACTIVE        │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                           │
│ ── 선택된 세트: 지게차 일상점검 ──                         │
│                                                           │
│ ┌─ [앵커 설정] ─┬─ [점검항목 세팅] ─┐  ← 탭 추가         │
│ │               │                    │                    │
│ │ (기존)        │ (신규 — 아래 참고)  │                    │
│ └───────────────┴────────────────────┘                    │
└─────────────────────────────────────────────────────────┘
```

### 5-4. [점검항목 세팅] 탭 내부

```
┌─────────────────────────────────────────────────────┐
│ 지게차 (전동식 3t) 점검항목                          │
│                                                       │
│ 추천 항목 7개가 자동으로 채워졌습니다.  ← L2+ only    │
│ 필요에 따라 수정·삭제·추가하세요.                     │
│                                                       │
│ ┌─────────────────────────────────────────────────┐ │
│ │ ☑ 타이어 마모·파손·공기압 이상 없음              │ │
│ │   [전도] [필수] [육안]                           │ │
│ │   이상 시: 정비 요청 후 사용 금지                 │ │
│ │                              [수정] [삭제]      │ │
│ └─────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────┐ │
│ │ ☑ 경적 정상 작동                                 │ │
│ │   [충돌] [필수] [작동확인]                       │ │
│ │   이상 시: 관리자 알림 후 작업 금지               │ │
│ │                              [수정] [삭제]      │ │
│ └─────────────────────────────────────────────────┘ │
│                                                       │
│ [+ 항목 추가]                                         │
│                                                       │
│ ── 항목 추가 (펼침) ──                                │
│ 항목명: [________________________]                    │
│ 점검방식: ○ 정상/이상  ○ 수치입력  ○ 상태선택        │
│ 위험유형: [전도 ▾]                                    │
│ 이상 시 조치: [________________________]              │
│ 필수 여부: ☐                                          │
│                              [추가]                   │
│                                                       │
│                     [임시저장]  [점검항목 확정]        │
└─────────────────────────────────────────────────────┘
```

### 5-5. 코드 변경 범위

`inspection-anchor.html` (49KB) 수정:
1. 점검세트 상세 영역에 탭 UI 추가 (`앵커 설정` | `점검항목 세팅`)
2. 점검항목 세팅 탭: prefill API 호출 → 항목 렌더링 → 추가/삭제/수정 → 확정 저장
3. 기존 앵커 설정 로직은 그대로 유지

⚠️ 49KB 파일이므로 Cursor에서 작업.

---

## 6. 실행 순서

### Phase 1: DB 준비
1. DDL 실행 (inspection_master + inspection_set_items 보강)
2. GPT로 기존 577건 보강 데이터 수집 → DB UPDATE

### Phase 2: 백엔드
3. `routers/inspection_setup.py` 신규 (prefill + setup)
4. main.py에 라우터 등록
5. 테스트: L1 → 빈 배열, L2+ → 프리필

### Phase 3: 프론트
6. `inspection-anchor.html`에 점검항목 세팅 탭 추가 (Cursor)
7. prefill API 연동
8. 확정 저장 연동

---

## 7. 파일 위치

### 백엔드 (tai-api)
- `routers/inspection_setup.py` — 신규
- `sql/20260420_inspection_master_enhance.sql` — DDL

### 프론트 (tai-admin → safe)
- `tadmin/.../inspection-anchor.html` — 기존 파일에 병합 (49KB, Cursor)
- 별도 페이지 만들지 않음

### 주의사항
- `routers/inspection_checklist.py` 기존 — 건드리지 않음
- `from db.supabase_client import get_supabase`
- inspection-anchor.html은 200줄+ → Cursor 필수
- dev → PR → main
