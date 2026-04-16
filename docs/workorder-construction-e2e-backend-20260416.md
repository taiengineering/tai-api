# [BACKEND] 건설 모듈 E2E 파이프라인 복구 작업

**작성일:** 2026-04-16  
**담당 윈도우:** backend (tai-api)  
**긴급도:** 🔴 Critical — 프로덕션에서 건설현장 자동진단·스케줄생성 파이프라인이 완전 마비

---

## 배경

2026-04-16 E2E DB 테스트 중 다음 상태 확인:
- `construction_sites`: 1건 (등록 시도 흔적만)
- `factory_diagnosis_results (CONSTRUCTION)`: **0건**
- `work_schedules (CONSTRUCTION LEGAL)`: **0건**
- `construction_inspections`: **0건**
- `inspection_sets (CONSTRUCTION)`: 8건 (부분적으로만 생성된 상태)

→ **POST /construction/sites 호출 시 `_auto_diagnose_and_schedule()` 내부에서 예외가 발생하여 try/except로 조용히 무시되고 있음.** 프로덕션 로그 상 드러나지 않지만 실제 자동화 체인은 전혀 동작하지 않음.

---

## BUG #1 🔴 [반드시 수정] construction_type 매핑 버그

### 위치
`routers/construction.py` → `_create_factory_for_site()` 함수

### 현재 코드 (문제)
```python
"construction_type": site.get("site_type") or "건축"
```

### 문제점
- `site.site_type` 허용값: `BUILDING` 또는 `CIVIL` (Pydantic `SiteCreate` 정의)
- `factories.construction_type` CHECK 제약: `'건축' | '토목' | '공통' | '기타'`만 허용
- 결과: factories INSERT 시점에서 `check constraint factories_construction_type_check violation` 발생
- `_create_factory_for_site` 내부 try/except로 `print()`만 되고 factory_id=None 반환 → 이후 자동진단/일정생성 완전 스킵

### 수정안 (정확한 코드)
```python
# 파일 상단 상수 추가
CONSTRUCTION_TYPE_MAP = {
    "BUILDING": "건축",
    "CIVIL":    "토목",
}

def _create_factory_for_site(supabase, site: dict) -> Optional[str]:
    try:
        contract_eok = float(site.get("contract_amount") or 0)
        site_type_raw = (site.get("site_type") or "BUILDING").upper()
        construction_type_label = CONSTRUCTION_TYPE_MAP.get(site_type_raw, "건축")

        factory_data = {
            "name":                      site.get("site_name", ""),
            "company_id":                site.get("company_id"),
            "site_type":                 "CONSTRUCTION",
            "sector":                    "CONSTRUCTION",
            "construction_amount":       contract_eok * 100_000_000,
            "employee_count":            site.get("direct_workers") or site.get("total_workers") or 0,
            "subcontractor_worker_count": site.get("subcon_workers") or 0,
            "construction_type":         construction_type_label,  # ← 수정
            "site_address":              site.get("site_address"),
            "status_code":               "ACTIVE",
            "is_active":                 True,
            "created_at":                _now_iso(),
            "updated_at":                _now_iso(),
        }
        # ...
```

### 검증 방법
```bash
# 배포 후 새 현장 등록
curl -X POST https://api.taieng.co.kr/construction/sites \
  -H "Content-Type: application/json" \
  -d '{"company_id":"9e57146a-ceb3-4a78-ad76-e36930b1a11e","site_name":"검증용현장","site_type":"BUILDING","contract_amount":180,"direct_workers":20,"subcon_workers":35,"total_workers":55}'

# 응답 내 auto.diagnosis.applicable_count > 0 이어야 함
# 응답 내 auto.schedules.created > 0 이어야 함
```

```sql
-- DB 확인
SELECT COUNT(*) FROM factory_diagnosis_results WHERE sector='CONSTRUCTION'; -- 1 이상
SELECT COUNT(*) FROM work_schedules WHERE source_type='LEGAL' 
  AND factory_id IN (SELECT id FROM factories WHERE sector='CONSTRUCTION'); -- 다수
```

---

## BUG #2 ✅ [DB 수정 완료 - 정보 공유]

### 위치
`inspection_sets.inspection_set_code` 컬럼

### 문제 (이미 해결됨)
전역 UNIQUE 인덱스 `uq_inspection_sets_code`로 여러 factory가 같은 법령 rule_id를 공유할 수 없었음 → 두 번째 현장 등록부터 `duplicate key` 예외 발생

### 해결 내역 (2026-04-16 migration `fix_inspection_sets_code_unique_scope_to_factory` 적용 완료)
```sql
DROP INDEX IF EXISTS uq_inspection_sets_code;
CREATE UNIQUE INDEX uq_inspection_sets_factory_code 
  ON inspection_sets (factory_id, inspection_set_code) 
  WHERE is_active = true AND inspection_set_code IS NOT NULL;
```

### 백엔드 코드 영향
- `inspection_set_auto.py`는 이미 `factory_id` scope로 중복 체크 중 → 추가 수정 불필요
- 향후 에러 핸들링 강화 권장: 배치 삽입 실패 시 개별 INSERT로 fallback

---

## 추가 작업 — 기존 고아 현장 수동 재진단

BUG #1 수정 배포 후, 기존 construction_sites 1건은 여전히 factory_id=null 또는 미진단 상태일 수 있음. 다음 스크립트로 일괄 재처리:

```python
# scripts/recover_construction_diagnosis.py
import os
from db.supabase_client import get_supabase
from routers.construction import _create_factory_for_site, _auto_diagnose_and_schedule

supabase = get_supabase()
sites = supabase.table("construction_sites").select("*").eq("is_active", True).execute().data

for site in sites:
    if not site.get("factory_id"):
        factory_id = _create_factory_for_site(supabase, site)
        print(f"{site['site_name']}: factory_id={factory_id}")
    else:
        factory_id = site["factory_id"]
    
    if factory_id:
        result = _auto_diagnose_and_schedule(supabase, factory_id, site)
        print(f"  diagnosis={result['diagnosis']}, schedules={result['schedules']}")
```

또는 운영 엔드포인트 호출:
```bash
# 각 현장에 대해 수동 재진단
curl -X POST https://api.taieng.co.kr/construction/sites/{site_id}/diagnose
curl -X POST https://api.taieng.co.kr/construction/sites/{site_id}/generate-schedules
```

---

## 배포 절차

1. dev 브랜치에 `routers/construction.py` 수정 커밋
2. 로컬 Python에서 syntax 체크: `python -c 'from routers.construction import _create_factory_for_site'`
3. dev→main PR 생성 및 머지
4. Fly.io Tokyo 자동 배포 확인
5. 위 검증 curl로 실제 동작 확인
6. 기존 현장 수동 재진단 실행

---

## 완료 기준

- [x] BUG #2 DB 수정 완료 (2026-04-16, Supabase migration)
- [ ] BUG #1 `construction.py` 수정 커밋
- [ ] Fly.io production 배포
- [ ] POST /construction/sites 신규 호출로 `factory_diagnosis_results` 자동 생성 확인
- [ ] POST /construction/sites 신규 호출로 `work_schedules (LEGAL)` 자동 생성 확인
- [ ] 기존 construction_sites 1건 수동 재진단 완료
- [ ] 프론트엔드 윈도우에 배포 완료 통보 (→ FRONTEND 워크오더 Step 2 시작 가능)

---

## 관련 문서
- 프론트 작업: `taiengineering/tai-admin` → `docs/workorder-construction-e2e-frontend-20260416.md`
- 전체 기획서: (없음, 이 워크오더가 primary)
