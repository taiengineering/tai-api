# 건설 모듈 — 분류→공정→작업→점검앵커 파이프라인 작업지시서

**작성일:** 2026-04-15  
**기준:** 12층 빌딩 건설현장 E2E 테스트 결과  
**핵심 문제:** 법령진단 → inspection_sets 자동생성 로직 누락

---

## 현재 상태 요약

```
산업(제조): 법령진단 → inspection_sets 303건 자동생성(LEGAL_ENGINE) → 앵커관리 → 일정생성 ✅
건설:       법령진단 → work_schedules만 생성 → inspection_sets 0건 → 앵커관리 빈 화면 ❌
```

**테스트 데이터 (DB에 이미 존재):**
- construction_sites: `42941f8d-0247-45ee-bb16-2899213137ec` (강남 센트럴타워 신축, 12층, 200억)
- factories mirror: `b692bc36-6199-426b-9d4c-b39080b5947e`
- 공정 9건, 작업 4건, 작업자 6건
- inspection_sets 8건 (수동 삽입 — 자동생성 검증용)

**이번 세션에서 완료된 DB 변경:**
- inspection_sets에 `obligation_type`, `obligation_summary` 컬럼 추가 완료 (마이그레이션)
- construction_sites에 업종/발주처/층수 등 10개 컬럼 추가 완료 (마이그레이션)
- system_codes에 건설업 분류체계 등록 완료 (종합5+전문14+공사종류9+발주처5+선임기준5+공종lv3 30건)

---

## 백엔드 작업 (tai-api, dev 브랜치)

### 🔴 BE-Step1: inspection_sets 자동생성 로직 추가 (P0, 최우선)

**파일:** `routers/construction.py`  
**함수:** `_run_diagnosis()` 이후 호출되는 새 함수 `_create_inspection_sets_from_diagnosis()`

```python
def _create_inspection_sets_from_diagnosis(supabase, factory_id, company_id, diagnosis_result):
    """
    법령진단 결과에서 inspection_sets를 자동 생성.
    - inspection_required + action_required + report_required 규칙을
      inspection_sets 레코드로 변환
    - 중복 방지: legal_rule_code 기준
    - source = 'LEGAL_ENGINE'
    - status_code = 'PENDING_ANCHOR'
    """
```

**로직:**
1. `diagnosis_result`에서 `inspection_required`, `action_required`, `report_required`(notify 포함) 추출
2. 각 rule을 inspection_sets 레코드로 변환:
   - `inspection_set_name` ← rule의 `obligation_summary` 앞 30자
   - `inspection_set_code` ← rule의 `rule_id`
   - `legal_rule_code` ← rule의 `rule_id`
   - `law_name`, `law_article` ← rule에서 직접
   - `obligation_type` ← rule의 `obligation_type` (INSPECT/BEFORE_WORK/REPORT/NOTIFY/APPOINT/ACTION)
   - `obligation_summary` ← rule의 `obligation_summary`
   - `cycle_unit`, `cycle_value` ← rule의 `cycle_info` 파싱 (없으면 기본값 year/1)
   - `source` = 'LEGAL_ENGINE'
   - `status_code` = 'PENDING_ANCHOR'
3. 중복 체크: `factory_id` + `legal_rule_code`로 이미 존재하면 skip
4. 생성 결과 반환: `{created: N, skipped: N}`

**호출 위치 2곳:**
- `_auto_diagnose_and_schedule()` 내부 (현장 등록 시 자동)
- `POST /sites/{site_id}/diagnose` 엔드포인트 (수동 재진단 시)

**master_building_legal_rules에서 cycle 정보 확인:**
```sql
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'master_building_legal_rules' 
AND column_name LIKE '%cycle%';
```
→ cycle 컬럼이 없으면, obligation_type별 기본 주기 매핑 사용:
- BEFORE_WORK → day/1
- INSPECT → month/1  
- REPORT → quarter/1
- NOTIFY → year/1
- APPOINT → year/1
- ACTION → month/1

**완료 조건:**
- POST /construction/sites 호출 시 inspection_sets가 자동 생성됨
- POST /construction/sites/{id}/diagnose 호출 시에도 동일하게 생성됨
- 중복 호출해도 기존 건 skip
- construction-inspection-anchor.html에서 목록 표시 확인

---

### 🔴 BE-Step2: 산업 모듈 기존 데이터 obligation_type 정규화 (P0)

**방식:** SQL 업데이트 (Supabase MCP)

산업 모듈 기존 304건의 inspection_sets에 obligation_type이 전부 'INSPECT'로 들어가 있음.  
실제로는 master_building_legal_rules의 obligation_type과 매칭해야 함.

```sql
-- legal_rule_code가 있는 경우 원본 규칙의 obligation_type으로 업데이트
UPDATE inspection_sets s
SET obligation_type = r.obligation_type,
    obligation_summary = COALESCE(s.obligation_summary, r.obligation_summary)
FROM master_building_legal_rules r
WHERE s.legal_rule_code = r.rule_id
  AND s.source = 'LEGAL_ENGINE'
  AND (s.obligation_type IS NULL OR s.obligation_type = 'INSPECT' OR s.obligation_type = 'OTHER');
```

**완료 조건:**
- 산업 모듈 inspection-anchor.html에서도 의무구분(점검/보고/선임/조치 등) 탭 필터가 정상 동작

---

### 🟡 BE-Step3: contract_amount 단위 명확화 + 검증

**파일:** `routers/construction.py`

1. `SiteCreate` 모델에 `contract_amount` 필드 description 추가: `"도급금액 (억원 단위)"`
2. `create_site` 엔드포인트에서 contract_amount가 0~99999 범위 검증 (억원 기준 상한)
3. DB 컬럼 comment 추가:
```sql
COMMENT ON COLUMN construction_sites.contract_amount IS '도급금액 (억원 단위, 예: 200 = 200억원)';
```

**완료 조건:**
- API 문서에 단위 명시
- 비정상 값(음수, 소수점 등) 입력 시 에러

---

### 🟡 BE-Step4: master_building_legal_rules에 cycle 컬럼 추가 (조건부)

**전제:** BE-Step1에서 cycle 컬럼이 없는 것이 확인되면 실행.

```sql
ALTER TABLE master_building_legal_rules
  ADD COLUMN IF NOT EXISTS default_cycle_unit text,
  ADD COLUMN IF NOT EXISTS default_cycle_value integer DEFAULT 1;
```

그리고 CONSTRUCTION 규칙 173건에 cycle 값 일괄 업데이트.

**완료 조건:**
- inspection_sets 자동생성 시 법령별 정확한 주기가 반영됨

---

## 프론트엔드 작업 (tai-admin, dev 브랜치)

### 🟡 FE-Step1: construction-inspection-anchor.html — 빈 화면 가이드

**파일:** `tadmin/full-version/html/horizontal-menu-template/construction-inspection-anchor.html`

**현재 문제:** 현장 선택 후 inspection_sets가 0건이면 "더 실행되는 점검항목이 없습니다. 법령진단을 먼저 실행하세요." 메시지만 표시.

**변경:**
```html
<!-- 빈 화면 가이드 카드 -->
<div id="emptyGuide" class="card border border-dashed" style="display:none">
  <div class="card-body text-center py-5">
    <div style="font-size:3rem;margin-bottom:16px;">🏗️</div>
    <h5>점검항목이 아직 없습니다</h5>
    <p class="text-body-secondary mb-4">
      건설현장 법령진단을 실행하면 해당 현장에 적용되는<br>
      점검·보고·선임 의무가 자동으로 생성됩니다.
    </p>
    <button class="btn btn-warning text-white" onclick="runDiagnosis()">
      <i class="ti tabler-shield-check me-2"></i>법령진단 실행하기
    </button>
    <div class="mt-3">
      <a href="construction-site-list.html" class="text-decoration-none small">
        ← 현장 정보 먼저 확인하기
      </a>
    </div>
  </div>
</div>
```

**JS 추가:**
```javascript
async function runDiagnosis() {
  if (!_siteId) { showToast('warning', '현장을 선택하세요.'); return; }
  showSaving();
  try {
    const res = await fetch(`${API}/construction/sites/${_siteId}/diagnose`, {
      method: 'POST', headers: hdr()
    });
    const j = await res.json();
    if (!res.ok) throw new Error(j.detail || '진단 실패');
    hideSaving(true);
    showToast('success', `법령진단 완료 — 적용 규칙 ${j.data?.applicable_rules || 0}건`);
    loadRows(); // 재조회
  } catch(e) {
    hideSaving(false);
    showToast('error', e.message || '법령진단 실패');
  }
}
```

**완료 조건:**
- 빈 화면에서 "법령진단 실행하기" 버튼 표시
- 클릭 시 진단 실행 → 점검앵커 자동 생성 → 목록 표시

---

### 🟡 FE-Step2: construction-process-list.html — KCSC 마스터 검색 선택 UI

**파일:** `tadmin/full-version/html/horizontal-menu-template/construction-process-list.html`

**현재 문제:** 공정 등록 시 이름을 수동 타이핑. KCSC 마스터(161건)와 연결 안 됨.

**변경:** 공정 추가 모달에 KCSC 검색 필드 추가
```html
<div class="mb-3">
  <label class="form-label">KCSC 표준공정 (선택)</label>
  <input type="text" class="form-control" id="kcscSearch" 
    placeholder="공정명 검색 (예: 기초, 골조, 방수...)" 
    oninput="searchKcsc(this.value)">
  <div id="kcscResults" class="list-group mt-1" style="max-height:200px;overflow-y:auto;"></div>
  <div class="form-text">선택하면 공정명과 공종코드가 자동 입력됩니다.</div>
</div>
```

**JS:**
```javascript
async function searchKcsc(q) {
  if (!q || q.length < 1) { document.getElementById('kcscResults').innerHTML = ''; return; }
  const res = await fetch(`${API}/construction/kcsc/processes?search=${encodeURIComponent(q)}&size=10`, {headers: hdr()});
  const j = await res.json();
  const items = j.data?.items || [];
  document.getElementById('kcscResults').innerHTML = items.map(it =>
    `<a href="#" class="list-group-item list-group-item-action py-2" onclick="selectKcsc('${it.id}','${esc(it.process_name)}','${esc(it.work_type_code||'')}','${esc(it.work_type_label||'')}')">
      <div class="fw-semibold small">${esc(it.process_name)}</div>
      <div class="text-muted" style="font-size:.72rem;">${esc(it.construction_type||'')} · ${esc(it.work_type_label||'')}</div>
    </a>`
  ).join('');
}
function selectKcsc(id, name, code, label) {
  document.getElementById('processName').value = name;
  document.getElementById('kcscProcessId').value = id;
  document.getElementById('workTypeCode').value = code;
  document.getElementById('kcscResults').innerHTML = '';
  document.getElementById('kcscSearch').value = name + ' ✓';
}
```

**완료 조건:**
- 공정 추가 시 KCSC 마스터 검색/선택 가능
- 선택하면 kcsc_process_id, work_type_code 자동 입력
- 수동 입력도 여전히 가능

---

### 🟢 FE-Step3: construction-site-list.html — 등록 폼에 신규 필드 반영

**파일:** `tadmin/full-version/html/horizontal-menu-template/construction-site-list.html`

**현재 문제:** 이번 세션에서 추가한 컬럼(업종/발주처/층수 등)이 등록 폼에 반영 안 됨.

**추가할 필드:**
```html
<!-- 업종 선택 -->
<div class="col-md-6">
  <label class="form-label">건설업 업종 <span class="text-danger">*</span></label>
  <div class="row g-2">
    <div class="col-5">
      <select id="bizCategory" class="form-select" onchange="loadBizCodes()">
        <option value="GENERAL">종합건설업</option>
        <option value="SPECIALTY">전문건설업</option>
      </select>
    </div>
    <div class="col-7">
      <select id="bizCode" class="form-select">
        <!-- system_codes에서 동적 로드 -->
      </select>
    </div>
  </div>
</div>

<!-- 발주처 -->
<div class="col-md-3">
  <label class="form-label">발주처 유형</label>
  <select id="clientType" class="form-select">
    <!-- CONSTRUCTION_CLIENT_TYPE에서 동적 로드 -->
  </select>
</div>
<div class="col-md-3">
  <label class="form-label">발주처명</label>
  <input type="text" id="clientName" class="form-control" placeholder="(주)강남디벨로퍼">
</div>

<!-- 건물 정보 -->
<div class="col-md-2">
  <label class="form-label">지상 층수</label>
  <input type="number" id="floorsAbove" class="form-control" placeholder="12">
</div>
<div class="col-md-2">
  <label class="form-label">지하 층수</label>
  <input type="number" id="floorsBelow" class="form-control" placeholder="3">
</div>
<div class="col-md-3">
  <label class="form-label">연면적 (㎡)</label>
  <input type="number" id="totalFloorArea" class="form-control" placeholder="28500">
</div>
<div class="col-md-3">
  <label class="form-label">공사금액 (억원)</label>
  <input type="number" id="contractAmount" class="form-control" placeholder="200">
  <div class="form-text">억원 단위 입력</div>
</div>
```

**완료 조건:**
- 등록 폼에 업종/발주처/층수/연면적 입력 가능
- system_codes에서 동적으로 select options 로드
- 저장 시 새 컬럼에 데이터 전달

---

## 작업 순서

```
BE-Step1 (inspection_sets 자동생성) ← 이것부터. 이거 없으면 건설 점검앵커 전체가 안 됨
  ↓
BE-Step2 (산업 기존 데이터 정규화) ← SQL 한 번이면 끝
  ↓
FE-Step1 (빈 화면 가이드 + 법령진단 버튼) ← BE-Step1 배포 후 즉시
  ↓
BE-Step3 (contract_amount 단위 명확화)
  ↓
FE-Step2 (KCSC 마스터 검색 UI)
  ↓
FE-Step3 (등록 폼 신규 필드)
  ↓
BE-Step4 (cycle 컬럼, 조건부)
```

## E2E 검증 시나리오 (전체 완료 후)

```
1. safe.taieng.co.kr 로그인 (CONSTRUCTION 섹터 계정)
2. 건설관리 > 현장관리 > 현장 등록 (12층 빌딩, 200억, 건축공사업)
   → factory 자동생성 확인
   → 법령진단 자동실행 확인
   → inspection_sets N건 자동생성 확인
3. 건설관리 > 공정관리 > KCSC 마스터에서 공정 선택 등록
4. 건설관리 > 점검앵커관리 > 자동생성된 앵커 목록 확인
   → 의무구분 탭 필터 동작 확인 (점검/작업전/보고/선임/조치)
   → 4조건 설정: 기준일 + 담당자 + 체크항목
   → "스케줄 생성" 버튼 활성화 → 클릭
5. 건설관리 > 업무일정 > 생성된 일정 확인
```
