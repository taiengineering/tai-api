# TAI Safe — 설비 등록 기능 작업지시서
> 작성일: 2026-04-08 | 담당: Claude Code (백엔드 신규 API) + Claude (프론트)

---

## 1. 배경 및 핵심 설계 결정

### 문제
`my-equipment.html`에 설비 목록 조회는 있으나 **등록 기능이 없음**.

### 두 가지 등록 경로

```
경로 1 (기본 — 공정 기반)
  process-manage.html
  └ 공정 선택 → [이 공정의 설비 추천 보기]
    └ MUST/CORE 설비 목록 체크박스로 표시
      └ 선택 + 수량·위치·설치연도 입력
        └ [일괄 등록] → POST /equipment-assets

경로 2 (별도 — 법령진단용 직접 등록)
  my-equipment.html
  └ [+ 직접 등록] 버튼
    └ 설비명 검색 (equipment_model_master 2,874개에서)
      └ 예) "지게차" 입력 → 지게차 목록 표시
        └ 선택 → 수량·위치·설치연도 입력
          └ [저장] → POST /equipment-assets
```

### 핵심 원칙
- **우리가 보유한 설비 마스터(equipment_model_master)에서 선택**하는 방식
- 법령 점검 의무가 있는 설비는 마스터에 등록되어 있음
- 직접 텍스트 입력 없이 **검색→선택→등록** 흐름

---

## 2. 현재 API 현황

| 엔드포인트 | 상태 | 비고 |
|---|---|---|
| `GET /equipment-assets` | ✅ | 설비 목록 조회 |
| `POST /equipment-assets` | ✅ | 설비 등록 (v1.1.0) |
| `PATCH /equipment-assets/{id}` | ✅ | 설비 수정 |
| `DELETE /equipment-assets/{id}` | ✅ | soft delete |
| `GET /factory-process/{id}/recommend-equipment` | ✅ | MUST/CORE 설비 추천 |
| `GET /equipment-model/search` | ❌ **신규 필요** | 설비 마스터 검색 |

---

## 3. 백엔드 신규 API (Claude Code 담당)

### equipment_assets.py에 엔드포인트 추가

#### GET /equipment-assets/model/search

> 주의: route 순서 — `/model/search` 고정경로를 `/{asset_id}` 파라미터 경로보다 **반드시 앞에** 선언

```python
@router.get("/model/search")
def search_equipment_model(
    q:    str   = Query(..., description="설비명 검색어 (ILIKE)"),
    lv2:  Optional[str] = Query(None, description="equipment_lv2 필터 (전기|기계|가스|안전|환경 등)"),
    size: int   = Query(20, ge=1, le=100),
):
    """
    equipment_model_master에서 equipment_std ILIKE 검색.
    법령진단용 설비 직접 등록 시 사용.
    """
    supabase = get_supabase()
    query = supabase.table("equipment_model_master").select(
        "id, equipment_std, primary_equipment_std, equipment_lv2,"
        "certification_class, maintenance_cycle_months, risk_score"
    ).ilike("equipment_std", f"%{q.strip()}%")

    if lv2:
        query = query.eq("equipment_lv2", lv2)

    # primary_equipment_std가 있는 것 우선 (중복 제거용)
    query = query.order("equipment_std")
    res = query.limit(size).execute()
    items = res.data or []

    # equipment_std 기준 중복 제거
    seen, unique = set(), []
    for row in items:
        key = row["equipment_std"]
        if key not in seen:
            seen.add(key)
            unique.append({
                "id":             row["id"],
                "name":           row["equipment_std"],
                "category":       row.get("equipment_lv2") or "기타",
                "cert_class":     row.get("certification_class"),
                "cycle_months":   row.get("maintenance_cycle_months"),
                "risk_score":     row.get("risk_score"),
            })

    return {
        "status": "success",
        "data": {"q": q, "items": unique, "total": len(unique)}
    }
```

**route 선언 위치:** 기존 `/scan` 바로 아래, `/{asset_id}` 이전에 삽입:
```python
@router.get("/scan")       # 기존
@router.get("/model/search")  # ← 신규 삽입
@router.get("/area/{area_id}")  # 기존
@router.get("/{asset_id}")  # 기존
```

---

## 4. 프론트엔드 작업 (Claude 담당)

### 4-1. my-equipment.html 개선 (경로 2 — 직접 등록)

**카드 헤더에 버튼 추가:**
```
[설비 목록]                    [+ 직접 등록]
```

**직접 등록 모달 (modal-direct-add):**
```
┌─────────────────────────────────────────┐
│ 설비 직접 등록                           │
├─────────────────────────────────────────┤
│ 설비 검색 *                             │
│ [지게차🔍_______________________________]│
│                                         │
│ 검색 결과:                              │
│ ┌────────────────────────────────────┐  │
│ │ ● 지게차        [전동기계] [선택]  │  │
│ │ ● 지게차(전동식) [전동기계] [선택] │  │
│ │ ● 지게차(내연기관) [기계] [선택]  │  │
│ └────────────────────────────────────┘  │
│                                         │
│ ✅ 선택됨: 지게차 (전동기계)            │
│ ─────────────────────────────────────  │
│ 수량 *:   [1  ]                         │
│ 설치연도: [2022]                        │
│ 설치위치: [1공장 A구역_______________]  │
│ 법정점검 대상: ☑ 예                    │
│                                         │
│              [취소] [등록]              │
└─────────────────────────────────────────┘
```

**검색 동작:**
- 입력 후 280ms 디바운스 → `GET /equipment-assets/model/search?q=지게차&size=20`
- 결과 클릭 → 선택 상태로 변경 (배경색 강조)
- 하나만 선택 가능

**등록 API 호출:**
```javascript
await apiCall('POST', '/equipment-assets', {
  factory_id:           factoryId,
  asset_name:           selectedModel.name,      // equipment_std
  equipment_category:   selectedModel.category,  // equipment_lv2
  equipment_model_id:   selectedModel.id,        // 마스터 연결
  quantity:             parseInt(inputQty.value),
  install_year:         parseInt(inputYear.value) || null,
  location_detail:      inputLocation.value.trim() || null,
  is_legal_target:      chkLegal.checked,
});
```

**등록 성공 시:** 모달 닫기 → `loadTable()` 호출

---

### 4-2. process-manage.html 개선 (경로 1 — 공정 기반 등록)

**공정 행에 버튼 추가:**
```
관리 열: [수정] [삭제] [⚙ 설비 등록]
```
단, `source === 'DB'` 공정만 [⚙ 설비 등록] 표시 (MANUAL/KCSC는 추천 데이터 없음)

**공정 기반 설비 등록 모달 (modal-process-eq):**
```
┌──────────────────────────────────────────────┐
│ ⚙ 공정 기반 설비 등록                         │
│ 공정: 제련 > 용해 > 용해 및 정련              │
├──────────────────────────────────────────────┤
│ TAI 권장 설비 (MUST/CORE)         총 12종     │
│ [전체선택]                                   │
│ ┌──────────────────────────────────────────┐ │
│ │ ☑ 용해로         [MUST] [수량:1] [위치]  │ │
│ │ ☑ 집진설비       [MUST] [수량:1] [위치]  │ │
│ │ ☐ 분전반         [CORE] [수량:1] [위치]  │ │
│ │ ☐ 크레인         [CORE] [수량:1] [위치]  │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ 공통 설치연도: [2022] (선택사항)             │
│                                              │
│ 이미 등록된 설비는 회색으로 표시             │
│              [취소] [선택 항목 등록]         │
└──────────────────────────────────────────────┘
```

**API 흐름:**
1. 모달 오픈 시: `GET /factory-process/{factory_id}/recommend-equipment` → MUST/CORE 목록
2. 기등록 확인: `GET /equipment-assets?factory_id=xxx&size=100` → 이름 비교로 중복 표시
3. 등록: 선택된 항목마다 `POST /equipment-assets` (순차 또는 병렬)

**POST body:**
```javascript
{
  factory_id:         factoryId,
  asset_name:         item.facility_name_std,  // v_equipment_unified.facility_name_std
  equipment_category: item.source_type || null,
  quantity:           parseInt(inputQty) || 1,
  install_year:       commonYear || null,
  location_detail:    inputLocation || null,
  is_legal_target:    true,
}
```

---

## 5. API 호출 패턴 (프론트 참고)

```javascript
const API = 'https://api.taieng.co.kr';
const hdr = () => ({ 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' });

// 설비 마스터 검색
const res = await fetch(`${API}/equipment-assets/model/search?q=${encodeURIComponent(q)}&size=20`, { headers: hdr() });
const { data } = await res.json();
// data.items: [{id, name, category, cert_class, cycle_months}]

// 설비 등록
await fetch(`${API}/equipment-assets`, {
  method: 'POST', headers: hdr(),
  body: JSON.stringify({ factory_id, asset_name, equipment_category, equipment_model_id, quantity, install_year, location_detail, is_legal_target })
});

// 공정별 권장 설비 조회
const rec = await fetch(`${API}/factory-process/${factoryId}/recommend-equipment`, { headers: hdr() });
// data.items: [{facility_name_std, match_band, process_id}]
```

---

## 6. 작업 순서

### 백엔드 (Claude Code)
- [ ] `equipment_assets.py`에 `GET /model/search` 추가
  - route 선언 순서: `/scan` 다음, `/{asset_id}` 이전
  - `equipment_model_master` ILIKE 검색
  - `equipment_std` 기준 중복 제거
  - 반환 필드: id, name, category, cert_class, cycle_months

### 프론트엔드 (Claude)
- [ ] `my-equipment.html` — [+ 직접 등록] 버튼 + 모달 구현
  - 검색 인풋 → `/equipment-assets/model/search` 실시간 조회
  - 선택 → 상세 입력 → POST
- [ ] `process-manage.html` — [⚙ 설비 등록] 버튼 + 모달 구현
  - recommend-equipment API → MUST/CORE 목록
  - 체크박스 선택 → 일괄 POST

---

## 7. 완료 기준

- [ ] `/equipment-assets/model/search?q=지게차` 정상 응답
- [ ] my-equipment.html에서 [+ 직접 등록] → 검색 → 선택 → 등록 → 목록 반영
- [ ] process-manage.html 공정 행에서 [⚙ 설비 등록] → 추천 목록 → 선택 → 등록
- [ ] 이미 등록된 설비는 회색(disabled) 표시
- [ ] 등록 완료 후 설비 목록 즉시 새로고침
