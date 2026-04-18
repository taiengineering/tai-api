# 건설 모듈 프론트엔드 작업지시서

**작성일:** 2026-04-16  
**우선순위:** FE-1 → FE-3 → FE-2 순서  
**리포:** taiengineering/tai-admin (main 브랜치)  
**경로:** `tadmin/full-version/html/horizontal-menu-template/`

---

## FE-Step1: construction-inspection-anchor.html — 빈 화면 가이드 (🟡 P1)

### 현재 문제
현장 선택 후 inspection_sets가 0건이면 빈 테이블만 표시. 사용자가 뭘 해야 하는지 모름.

### 작업 내용

#### 1) 빈 화면 가이드 HTML 추가 (테이블 위 또는 대체)
```html
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

#### 2) JS: loadRows() 결과가 0건일 때 가이드 표시
```javascript
// 기존 loadRows() 함수 내부, 데이터 렌더링 후:
if (rows.length === 0) {
  document.getElementById('emptyGuide').style.display = 'block';
  document.getElementById('dataTable').style.display = 'none'; // 또는 테이블 wrapper
} else {
  document.getElementById('emptyGuide').style.display = 'none';
  document.getElementById('dataTable').style.display = 'block';
}
```

#### 3) JS: runDiagnosis() 함수
```javascript
async function runDiagnosis() {
  if (!_siteId) { showToast('warning', '현장을 선택하세요.'); return; }
  const btn = event.target.closest('button');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>진단 중...';
  try {
    const res = await fetch(`${API}/construction/sites/${_siteId}/diagnose`, {
      method: 'POST', headers: hdr()
    });
    const j = await res.json();
    if (!res.ok) throw new Error(j.detail || '진단 실패');
    showToast('success', `법령진단 완료 — 적용 규칙 ${j.data?.applicable_rules || 0}건`);
    loadRows(); // 재조회
  } catch(e) {
    showToast('error', e.message || '법령진단 실패');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="ti tabler-shield-check me-2"></i>법령진단 실행하기';
  }
}
```

### 완료 조건
- [ ] 빈 화면에서 "법령진단 실행하기" 버튼 표시
- [ ] 클릭 시 진단 실행 → 점검앵커 자동 생성 → 목록 표시 (BE-1 배포 후)
- [ ] BE-1 미배포 상태에서도 가이드 메시지는 정상 표시

---

## FE-Step3: construction-site-list.html — 등록 폼 신규 필드 (🟢 P2)

### 현재 문제
이번 세션에서 추가한 DB 컬럼(biz_category, floors_above 등)이 등록 폼에 미반영.

### 작업 내용

#### 1) 등록/수정 모달에 필드 추가

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

<!-- 공사종류 -->
<div class="col-md-3">
  <label class="form-label">공사종류</label>
  <select id="workClass" class="form-select">
    <!-- CONSTRUCTION_WORK_CLASS에서 동적 로드 -->
  </select>
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
  <input type="number" id="floorsAbove" class="form-control" min="0" placeholder="12">
</div>
<div class="col-md-2">
  <label class="form-label">지하 층수</label>
  <input type="number" id="floorsBelow" class="form-control" min="0" placeholder="3">
</div>
<div class="col-md-3">
  <label class="form-label">연면적 (㎡)</label>
  <input type="number" id="totalFloorArea" class="form-control" min="0" placeholder="28500">
</div>
<div class="col-md-3">
  <label class="form-label">공사금액 (억원)</label>
  <input type="number" id="contractAmount" class="form-control" min="0" placeholder="200">
  <div class="form-text">억원 단위 입력</div>
</div>
```

#### 2) JS: system_codes에서 select options 동적 로드
```javascript
async function loadBizCodes() {
  const cat = document.getElementById('bizCategory').value;
  const codeType = cat === 'GENERAL' ? 'CONSTRUCTION_BIZ_GENERAL' : 'CONSTRUCTION_BIZ_SPECIALTY';
  const res = await fetch(`${API}/system-codes?code_type=${codeType}`, { headers: hdr() });
  const j = await res.json();
  const sel = document.getElementById('bizCode');
  sel.innerHTML = (j.data?.items || []).map(c =>
    `<option value="${c.code_value}">${c.code_name}</option>`
  ).join('');
}

async function loadWorkClasses() {
  const res = await fetch(`${API}/system-codes?code_type=CONSTRUCTION_WORK_CLASS`, { headers: hdr() });
  const j = await res.json();
  document.getElementById('workClass').innerHTML = 
    '<option value="">선택</option>' +
    (j.data?.items || []).map(c => `<option value="${c.code_value}">${c.code_name}</option>`).join('');
}

async function loadClientTypes() {
  const res = await fetch(`${API}/system-codes?code_type=CONSTRUCTION_CLIENT_TYPE`, { headers: hdr() });
  const j = await res.json();
  document.getElementById('clientType').innerHTML = 
    '<option value="">선택</option>' +
    (j.data?.items || []).map(c => `<option value="${c.code_value}">${c.code_name}</option>`).join('');
}

// 페이지 로드 시 호출
loadBizCodes();
loadWorkClasses();
loadClientTypes();
```

#### 3) 저장 시 새 필드 전달
```javascript
// saveSite() 함수의 payload에 추가:
const payload = {
  ...existingFields,
  biz_category: document.getElementById('bizCategory').value,
  biz_code: document.getElementById('bizCode').value,
  work_class: document.getElementById('workClass').value,
  client_type: document.getElementById('clientType').value,
  client_name: document.getElementById('clientName').value,
  floors_above: parseInt(document.getElementById('floorsAbove').value) || null,
  floors_below: parseInt(document.getElementById('floorsBelow').value) || null,
  total_floor_area: parseFloat(document.getElementById('totalFloorArea').value) || null,
  contract_amount: parseFloat(document.getElementById('contractAmount').value) || null,
};
```

### 완료 조건
- [ ] 등록 폼에 업종/발주처/층수/연면적/공사금액 입력 가능
- [ ] system_codes에서 동적으로 select options 로드
- [ ] 저장 시 새 필드 데이터 API에 전달
- [ ] 기존 데이터 수정 시 값 로드

---

## FE-Step2: construction-process-list.html — KCSC 마스터 검색 (🟢 P2)

### 현재 문제
공정 등록 시 이름을 수동 타이핑. KCSC 마스터(161건)와 연결 안 됨.

### 작업 내용

#### 1) 공정 추가 모달에 KCSC 검색 필드 추가
```html
<div class="mb-3">
  <label class="form-label">KCSC 표준공정 (선택)</label>
  <input type="text" class="form-control" id="kcscSearch" 
    placeholder="공정명 검색 (예: 기초, 골조, 방수...)" 
    oninput="searchKcsc(this.value)" autocomplete="off">
  <div id="kcscResults" class="list-group mt-1" style="max-height:200px;overflow-y:auto;"></div>
  <input type="hidden" id="kcscProcessId">
  <div class="form-text">선택하면 공정명과 공종코드가 자동 입력됩니다.</div>
</div>
```

#### 2) JS: KCSC 검색 + 선택
```javascript
let _kcscTimer = null;
async function searchKcsc(q) {
  clearTimeout(_kcscTimer);
  if (!q || q.length < 1) { document.getElementById('kcscResults').innerHTML = ''; return; }
  _kcscTimer = setTimeout(async () => {
    try {
      const res = await fetch(`${API}/construction/kcsc/processes?search=${encodeURIComponent(q)}&size=10`, {headers: hdr()});
      const j = await res.json();
      const items = j.data?.items || [];
      document.getElementById('kcscResults').innerHTML = items.length === 0 
        ? '<div class="list-group-item text-muted small">검색 결과 없음</div>'
        : items.map(it =>
          `<a href="#" class="list-group-item list-group-item-action py-2" 
            onclick="selectKcsc('${it.id}','${esc(it.process_name)}','${esc(it.work_type_code||'')}')">
            <div class="fw-semibold small">${esc(it.process_name)}</div>
            <div class="text-muted" style="font-size:.72rem;">${esc(it.construction_type||'')} · ${esc(it.work_type_code||'')}</div>
          </a>`
        ).join('');
    } catch(e) { console.warn('KCSC 검색 실패:', e); }
  }, 300);
}

function selectKcsc(id, name, code) {
  document.getElementById('processName').value = name;
  document.getElementById('kcscProcessId').value = id;
  document.getElementById('kcscResults').innerHTML = '';
  document.getElementById('kcscSearch').value = name + ' ✓';
}

function esc(s) { return (s||'').replace(/'/g, "\\'").replace(/</g, '&lt;'); }
```

#### 3) 저장 시 kcsc_process_id 전달
```javascript
// 기존 saveProcess() payload에 추가:
kcsc_process_id: document.getElementById('kcscProcessId').value || null,
```

### 완료 조건
- [ ] 공정 추가 시 KCSC 마스터 검색/선택 가능 (BE-Step4 필요)
- [ ] 선택하면 공정명 자동 입력
- [ ] 수동 입력도 여전히 가능
- [ ] 저장 시 kcsc_process_id 전달

---

## 작업 순서 & 의존관계

```
[프론트 독립 작업]
FE-3 현장등록 폼 신규필드  ← 바로 시작 가능, BE 의존 없음
FE-2 KCSC 검색 UI         ← UI는 바로, API 연결은 BE-4 후

[BE 의존 작업]
FE-1 빈 화면 가이드        ← UI는 바로, "법령진단 실행" 버튼은 BE-1 후
```

## UI 표준 (필수)
- 모든 리스트 페이지 첫 번째 컬럼: 전체선택 체크박스
- 두 번째 컬럼: 행번호 (No.)
