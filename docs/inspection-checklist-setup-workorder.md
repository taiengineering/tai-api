# 점검항목 세팅 — 플랜별 조합형 프리필 작업지시서

## 1. 개요

안전관리자가 설비를 등록하고 점검항목을 세팅할 때:
- **L1 (낮은 플랜)**: 빈 화면 → 직접 항목 추가 (조합형)
- **L2+ (높은 플랜)**: 추천 항목 프리필 → 수정/삭제/추가 (같은 조합형 UI)

UI는 하나. 시작 상태만 다름. 템플릿 선택 UI 없음.

---

## 2. 기존 인프라

### 이미 있는 것
| 테이블 | 건수 | 역할 |
|---|---|---|
| `inspection_master` | 577건, 47개 설비유형 | 점검항목 마스터 (프리필 소스) |
| `inspection_sets` | 324건 | 점검세트 (법령엔진 자동생성) |
| `inspection_set_items` | 67건 | 프로덕션 점검항목 (거의 비어있음) |
| `equipment_assets` | 85건 | 등록된 설비 |
| `equipment_model_master` | 2,874건 | 설비 모델 마스터 |
| `price_saas_plan` | 10건 | SaaS 플랜 (L1~L4, sector별) |

### inspection_master 샘플
```
equipment_std: "forklift"
equipment_name_ko: "지게차"
inspection_item: "작동 전 외관 이상 여부 확인"
cycle: "daily"
rule_type: "DAILY"
legal_basis: "산업안전보건기준에 관한 규칙 제171조"
check_method: "육안"
```
→ 이미 설비 유형별 점검항목이 구조화되어 있음. 이걸 프리필 소스로 활용.

### inspection_master 보강 필요 (GPT 재수집 대상)
| 현재 있는 컬럼 | 없어서 추가 필요 |
|---|---|
| equipment_std | ✅ | 
| inspection_item | ✅ |
| cycle | ✅ |
| legal_basis | ✅ (일부만) |
| check_method | ✅ |
| **sector** | ❌ 추가 필요 |
| **check_type** | ❌ (BOOLEAN/NUMERIC/STATUS) |
| **risk_type** | ❌ (전도/충돌/협착/추락/감전 등) |
| **pass_description** | ❌ |
| **fail_action** | ❌ |
| **related_service** | ❌ (TAI Fix 연결) |
| **is_mandatory** | ❌ (법정 필수 여부) |
| **threshold_value** | ❌ (판정 기준값) |

---

## 3. 플랜 분기 기준

| 플랜 | tier | 프리필 |
|---|---|---|
| INDUSTRY_L1 / FACILITY_L1 | 1 | ❌ 빈 화면 |
| INDUSTRY_L2+ / FACILITY_L2+ | 2+ | ✅ 추천항목 프리필 |
| CONSTRUCTION 전체 | - | ✅ 프리필 (건설은 L1부터 제공) |

`price_saas_plan` 테이블에 `include_checklist_prefill BOOLEAN` 컬럼 추가.
또는 코드에서 `plan_code`의 L2 이상 체크. (후자 권장 — 컬럼 추가 불필요)

---

## 4. 백엔드 작업

### 4-1. inspection_master 스키마 보강 (DDL)

```sql
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
```

### 4-2. inspection_set_items 스키마 보강 (DDL)

```sql
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

`source` 값: `TEMPLATE` (마스터에서 프리필) / `MANUAL` (직접 추가)

### 4-3. 신규 엔드포인트

#### GET /inspection-checklist/prefill

```
Query params:
  equipment_std: "forklift" (필수)
  company_id: UUID (필수 — 플랜 조회용)
  cycle: "daily" (선택 — 필터)

동작:
1. company_id → companies → subscription → price_saas_plan 조회
2. plan_code에서 tier 추출 (L1/L2/L3/L4)
3. tier >= 2 (또는 건설 섹터):
   → inspection_master에서 equipment_std 매칭 항목 반환
4. tier == 1:
   → 빈 배열 반환 { items: [], source: "MANUAL" }

응답:
{
  "status": "success",
  "data": {
    "equipment_std": "forklift",
    "equipment_name_ko": "지게차",
    "source": "TEMPLATE",  // 또는 "MANUAL"
    "items": [
      {
        "master_item_id": "uuid",
        "item_name": "타이어 마모·파손·공기압 이상 없음",
        "check_type": "BOOLEAN",
        "risk_type": "전도",
        "cycle": "daily",
        "is_mandatory": true,
        "legal_basis": "산업안전보건기준에 관한 규칙 제171조",
        "check_method": "육안",
        "pass_description": "마모·파손·공기압 저하 없음",
        "fail_action": "정비 요청 후 사용 금지"
      }
    ],
    "total": 7
  }
}
```

#### POST /inspection-checklist/setup

```
Body:
{
  "inspection_set_id": "uuid",  // 기존 inspection_sets의 ID
  "equipment_asset_id": "uuid",
  "items": [
    {
      "item_name": "타이어 마모·파손·공기압 이상 없음",
      "check_type": "BOOLEAN",
      "risk_type": "전도",
      "is_required": true,
      "pass_description": "마모·파손·공기압 저하 없음",
      "fail_action": "정비 요청 후 사용 금지",
      "source": "TEMPLATE",
      "master_item_id": "uuid",  // TEMPLATE이면 원본 ID
      "check_method": "육안",
      "item_seq": 1
    },
    {
      "item_name": "후방카메라 정상 작동",  // 직접 추가
      "check_type": "BOOLEAN",
      "risk_type": "충돌",
      "is_required": false,
      "source": "MANUAL",
      "master_item_id": null,
      "item_seq": 8
    }
  ]
}

동작:
1. 기존 inspection_set_items에서 해당 set의 항목 전부 삭제 (soft delete)
2. 새 항목 일괄 INSERT
3. inspection_sets.status_code = 'ACTIVE' 업데이트
```

### 4-4. 기존 라우터 확인/수정

`routers/inspection_checklist.py` (26KB) — 기존 점검 체크리스트 라우터.
새 엔드포인트를 여기에 추가하거나 별도 `routers/inspection_setup.py`로 분리.

---

## 5. 프론트엔드 작업 (safe.taieng.co.kr)

### 5-1. 점검항목 세팅 화면

경로: `/inspection/setup/{inspection_set_id}`
또는 설비 상세 → 점검항목 세팅 탭

#### 진입 시
```javascript
// 1. 이미 세팅된 항목이 있으면 그대로 표시
const existing = await api.get(`/inspection-set-items?set_id=${setId}`);
if (existing.items.length > 0) {
  renderItems(existing.items);
  return;
}

// 2. 최초 세팅 — prefill API 호출
const prefill = await api.get(`/inspection-checklist/prefill`, {
  equipment_std: equipmentStd,
  company_id: companyId
});

if (prefill.source === 'TEMPLATE') {
  // 높은 플랜: 추천 항목 프리필 + 안내 메시지
  showMessage('추천 항목이 자동으로 채워졌습니다. 필요에 따라 수정·삭제·추가하세요.');
  renderItems(prefill.items, { editable: true, preChecked: true });
} else {
  // 낮은 플랜: 빈 화면 + 추가 버튼
  showMessage('등록된 항목이 없습니다.');
  renderItems([], { editable: true });
}
```

#### UI 구성 요소

```
┌─────────────────────────────────────────────────┐
│ 지게차 (전동식 3t) 점검항목 세팅                  │
│                                                   │
│ 추천 항목 7개가 자동으로 채워졌습니다.             │ ← 높은 플랜만
│ 필요에 따라 수정·삭제·추가하세요.                 │
│                                                   │
│ ┌─────────────────────────────────────────────┐ │
│ │ ☑ 타이어 마모·파손·공기압 이상 없음          │ │
│ │   [전도] [필수] [육안]                       │ │
│ │   이상 시: 정비 요청 후 사용 금지             │ │
│ │                              [수정] [삭제]  │ │
│ └─────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ ☑ 경적 정상 작동                             │ │
│ │   [충돌] [필수] [작동확인]                   │ │
│ │   이상 시: 관리자 알림 후 작업 금지           │ │
│ │                              [수정] [삭제]  │ │
│ └─────────────────────────────────────────────┘ │
│                                                   │
│ [+ 항목 추가]                                     │
│                                                   │
│ ── 항목 추가 (펼침) ──                            │
│ 항목명: [________________________]                │
│ 점검방식: ○ 정상/이상  ○ 수치입력  ○ 상태선택    │
│ 위험유형: [전도 ▾]                                │
│ 이상 시 조치: [________________________]          │
│ 필수 여부: ☐                                      │
│                              [추가]               │
│                                                   │
│                     [임시저장]  [점검항목 확정]    │
└─────────────────────────────────────────────────┘
```

#### 항목 추가 모달/폼 필드
| 필드 | 타입 | 필수 |
|---|---|---|
| item_name | text input | ✅ |
| check_type | radio (BOOLEAN/NUMERIC/STATUS) | ✅ |
| risk_type | select (전도/충돌/협착/추락/감전/화재/질식/폭발) | ✅ |
| is_required | checkbox | |
| pass_description | text input | |
| fail_action | text input | |
| unit | text input (NUMERIC일 때만 표시) | |
| threshold_value | text input (NUMERIC일 때만 표시) | |

#### 확정 저장
```javascript
const items = collectFormItems(); // UI에서 수집
await api.post('/inspection-checklist/setup', {
  inspection_set_id: setId,
  equipment_asset_id: assetId,
  items: items.map((item, idx) => ({
    ...item,
    item_seq: idx + 1,
    source: item.master_item_id ? 'TEMPLATE' : 'MANUAL'
  }))
});
showSuccess('점검항목이 확정되었습니다.');
```

### 5-2. 업셀 유도 (낮은 플랜)

낮은 플랜 사용자가 설비 3개 이상 등록 후 점검항목을 직접 만들고 있을 때:
```
┌─────────────────────────────────────────────┐
│ 💡 설비별 추천 점검항목을 자동으로            │
│    채워드릴 수 있습니다.                      │
│    L2 스탠다드 플랜으로 업그레이드하세요.     │
│                          [자세히 보기]        │
└─────────────────────────────────────────────┘
```
조건: source='MANUAL' 항목 20개 이상 + plan_tier=1 → 배너 1회 표시

---

## 6. inspection_master 데이터 보강 (GPT 재수집)

기존 577건의 inspection_master에 새 컬럼 값을 채우는 작업.

### GPT 프롬프트 (보강용)
```
아래 CSV는 한국 산업현장의 설비별 점검항목 마스터 데이터입니다.
각 행에 아래 빈 컬럼을 채워주세요.

채워야 할 컬럼:
- sector: BUILDING/MANUFACTURING/CONSTRUCTION/COMMON 중 택1
- check_type: BOOLEAN(정상/이상)/NUMERIC(수치)/STATUS(양호/불량/주의) 중 택1
- risk_type: 전도/충돌/협착/추락/감전/화재/질식/폭발/낙하/절단 중 택1
- is_mandatory: true(법정 필수)/false
- pass_description: 정상 판정 기준 (1줄)
- fail_action: 이상 시 조치 (1줄)
- related_service: TAI Fix 연결 서비스명 (정비/교체/점검 등)

[현재 데이터]
equipment_std,equipment_name_ko,inspection_item,cycle,rule_type,check_method,legal_basis
forklift,지게차,작동 전 외관 이상 여부 확인,daily,DAILY,육안,산업안전보건기준에 관한 규칙 제171조
...
```

→ 보강된 CSV를 DB UPDATE문으로 변환하여 적용.

---

## 7. 실행 순서

### Phase 1: DB 준비
1. inspection_master 스키마 보강 (DDL)
2. inspection_set_items 스키마 보강 (DDL)
3. GPT로 기존 577건 보강 데이터 수집 → DB UPDATE

### Phase 2: 백엔드
4. GET /inspection-checklist/prefill 구현
5. POST /inspection-checklist/setup 구현
6. 테스트: L1 플랜 → 빈 배열, L2+ → 프리필 항목

### Phase 3: 프론트
7. 점검항목 세팅 화면 구현 (조합형 UI)
8. prefill API 연동
9. 확정 저장 연동
10. 업셀 배너 (optional)

---

## 8. 파일 위치

### 백엔드 (tai-api)
- `routers/inspection_setup.py` — 신규 (prefill + setup)
- `sql/20260420_inspection_master_enhance.sql` — DDL

### 프론트 (tai-admin → safe)
- `tadmin/inspection-setup.html` — 점검항목 세팅 화면

### 주의사항
- `routers/inspection_checklist.py` (26KB) 기존 — 건드리지 않음
- `from db.supabase_client import get_supabase`
- dev → PR → main
