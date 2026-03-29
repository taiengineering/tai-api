# TAI Cursor 작업지시서 — 법령진단 입력폼

> 우선순위: 🔴 긴급  
> 작성일: 2026-03-29  
> 레포: taiengineering/tai-admin  
> 대상 파일: 신규 생성

---

## 개요

법령진단 3단계 입력폼 페이지를 신규 생성합니다.

- **파일 위치:** `site/full-version/html/tadmin/diagnosis-step1.html`
- **URL:** tadmin.taieng.co.kr/html/.../diagnosis-step1.html
- **기반:** Vuexy HTML Bootstrap 5 (기존 factory-list.html 스타일 참고)
- **API:** `POST https://api.taieng.co.kr/legal-engine/diagnose/step1`

---

## 페이지 구조

```
diagnosis-step1.html
├── 상단: 섹터 선택 카드 4개
│   ├── 🏢 건물·시설 (BUILDING)
│   ├── 🏭 공장·제조업 (MANUFACTURING)
│   ├── 🏗️ 건설현장 (CONSTRUCTION)
│   └── 🏥 특수시설 (SPECIAL_FACILITY)
│
├── 중단: 섹터별 입력폼 (선택된 섹터만 표시)
│   ├── BUILDING 폼
│   ├── MANUFACTURING 폼
│   ├── CONSTRUCTION 폼
│   └── SPECIAL_FACILITY 폼
│
└── 하단: 결과 섹션 (진단 후 표시)
```

---

## 1. 섹터 선택 카드 UI

```html
<div class="row g-3 mb-4" id="sectorCards">
  <div class="col-6 col-md-3">
    <div class="card sector-card cursor-pointer" data-sector="BUILDING">
      <div class="card-body text-center py-4">
        <i class="bx bx-building-house bx-lg text-primary mb-2"></i>
        <h6 class="mb-1">건물·시설</h6>
        <small class="text-muted">소방·전기·산안법</small>
      </div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="card sector-card cursor-pointer" data-sector="MANUFACTURING">
      <div class="card-body text-center py-4">
        <i class="bx bx-factory bx-lg text-warning mb-2"></i>
        <h6 class="mb-1">공장·제조업</h6>
        <small class="text-muted">산안법·위험물·화관법</small>
      </div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="card sector-card cursor-pointer" data-sector="CONSTRUCTION">
      <div class="card-body text-center py-4">
        <i class="bx bx-hard-hat bx-lg text-danger mb-2"></i>
        <h6 class="mb-1">건설현장</h6>
        <small class="text-muted">공사금액 기준</small>
      </div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="card sector-card cursor-pointer" data-sector="SPECIAL_FACILITY">
      <div class="card-body text-center py-4">
        <i class="bx bx-plus-medical bx-lg text-success mb-2"></i>
        <h6 class="mb-1">특수시설</h6>
        <small class="text-muted">병원·학교·복지시설</small>
      </div>
    </div>
  </div>
</div>
```

카드 클릭 시:
- 선택 카드에 `border-primary bg-light` 추가
- 해당 섹터 입력폼 표시 (나머지 숨김)

---

## 2. 섹터별 입력폼

### BUILDING 폼

| 필드 | 타입 | 변수명 | 단위 |
|------|------|--------|------|
| 건물 용도 | select | building_use_category | - |
| 연면적 | number | gross_floor_area | ㎡ |
| 지상 층수 | number | above_ground_floors | 층 |
| 상시 근로자수 | number | worker_count | 명 |
| 수전용량 | number | electric_capacity_kw | kW |
| 고압가스 사용 여부 | toggle | has_high_pressure_gas | Y/N |
| 위험물 취급 여부 | toggle | has_hazardous_material | Y/N |

건물 용도 옵션:
```
업무시설 / 판매시설 / 의료시설 / 노유자시설 / 숙박시설
교육연구시설 / 창고시설 / 공장 / 위락시설 / 기타
```

### MANUFACTURING 폼

| 필드 | 타입 | 변수명 |
|------|------|--------|
| KSIC 대분류 | select | ksic_lv1_code |
| 상시 근로자수 | number | worker_count |
| 수전용량 | number | electric_capacity_kw |
| 위험물 취급 | toggle | has_hazardous_material |
| 고압가스 사용 | toggle | has_high_pressure_gas |
| 화학물질 취급 | toggle | has_chemical_substance |
| 보일러 설치 | toggle | has_boiler |

KSIC 대분류 주요 옵션:
```
C10 음식료품 / C13 섬유 / C17 종이 / C19 석유정제
C20 화학 / C21 의약품 / C24 1차금속 / C25 금속가공
C28 기계 / C29 자동차 / C30 항공 / 기타
```

### CONSTRUCTION 폼

| 필드 | 타입 | 변수명 | 단위 |
|------|------|--------|------|
| 공사금액 | number | contract_amount | 원 |
| 공사 종류 | select | construction_type | - |
| 상시 근로자수 | number | worker_count | 명 |
| 터널·교량 포함 | toggle | has_tunnel_bridge | Y/N |

공사금액 입력 편의: 억 단위 입력 → 내부적으로 ×100000000 변환
```javascript
// 억 단위 입력 → 원 단위 변환
document.getElementById('contractAmountEok').addEventListener('input', function() {
  const won = parseFloat(this.value || 0) * 100000000;
  document.getElementById('contract_amount').value = won;
});
```

공사 종류: `건축공사 / 토목공사 / 전문공사`

### SPECIAL_FACILITY 폼

| 필드 | 타입 | 변수명 |
|------|------|--------|
| 시설 유형 | select | facility_type |
| 연면적 | number | gross_floor_area |
| 병상수 (병원) | number | hospital_beds |
| 학생수 (학교) | number | student_count |
| 상시 근로자수 | number | worker_count |

시설 유형: `병원 / 요양병원 / 학교 / 복지시설 / 다중이용업소 / 어린이집 / 위험물창고`

---

## 3. 진단하기 버튼 + API 호출

```javascript
const BASE_URL = 'https://api.taieng.co.kr';

async function runDiagnosis() {
  const factory_id = getSelectedFactoryId(); // localStorage 또는 URL 파라미터
  const sector = selectedSector;
  const input = getFormInput(sector); // 해당 섹터 입력값 수집
  
  if (!factory_id || !sector) {
    showToast('danger', '시설과 섹터를 선택해주세요.');
    return;
  }
  
  showLoading(true);
  
  try {
    const resp = await apiCall('POST', '/legal-engine/diagnose/step1', {
      factory_id,
      sector,
      input
    });
    showResult(resp.data);
  } catch(e) {
    showToast('danger', '진단 중 오류가 발생했습니다.');
  } finally {
    showLoading(false);
  }
}
```

---

## 4. 결과 표시 섹션

```html
<div id="resultSection" class="d-none">
  <!-- 리스크 레벨 배지 -->
  <div class="d-flex align-items-center mb-3">
    <h5 class="mb-0 me-2">진단 결과</h5>
    <span id="riskBadge" class="badge bg-danger">HIGH</span>
  </div>
  
  <!-- 적용 법령 카테고리 -->
  <div class="mb-3">
    <label class="form-label fw-bold">적용 법령</label>
    <div id="lawCategories"><!-- 배지 목록 --></div>
  </div>
  
  <!-- 선임 의무 여부 -->
  <div class="alert alert-warning mb-3" id="appointmentAlert">
    <i class="bx bx-user-check me-2"></i>
    <strong>선임 의무가 있습니다</strong>
  </div>
  
  <!-- 주요 의무 목록 -->
  <div class="mb-3">
    <label class="form-label fw-bold">주요 의무</label>
    <ul id="obligationList" class="list-group"></ul>
  </div>
  
  <!-- 룰 상세 테이블 -->
  <table class="table table-hover" id="rulesTable">
    <thead>
      <tr>
        <th>법령명</th>
        <th>조문</th>
        <th>의무사항</th>
      </tr>
    </thead>
    <tbody id="rulesBody"></tbody>
  </table>
  
  <!-- 2단계 유도 배너 (1단계 결과 후) -->
  <div class="alert alert-info">
    <i class="bx bx-info-circle me-2"></i>
    공정 및 설비까지 등록하면 더 정밀한 진단이 가능합니다.
    <a href="#" class="btn btn-sm btn-primary ms-2">2단계 진단 →</a>
  </div>
</div>
```

---

## 5. 기존 파일 참고 경로

```
site/full-version/html/tadmin/factory-list.html  ← 전체 레이아웃 참고
site/full-version/html/tadmin/index.html         ← 대시보드 카드 스타일 참고
```

- Navbar/Footer: 기존 패턴 그대로 인라인 삽입
- `const BASE_URL = 'https://api.taieng.co.kr';` 상단에 선언
- 로그인 체크: `if (!localStorage.getItem('access_token')) { location.href = '../auth-login-cover.html'; }`
- Toast 함수: 기존 factory-list.html의 showToast() 패턴 사용
- system_codes 동적 로드 패턴 유지

---

## 완료 체크리스트

```
□ diagnosis-step1.html 파일 생성
□ 섹터 선택 카드 4개 표시
□ 카드 클릭 시 해당 폼 표시
□ 각 섹터별 입력폼 구현 (4종)
□ [진단하기] 버튼 → POST /legal-engine/diagnose/step1 호출
□ 결과 섹션 표시 (법령 배지, 의무 목록, 룰 테이블)
□ 리스크 레벨 배지 (HIGH=빨강, MEDIUM=주황, LOW=초록)
□ 2단계 유도 배너
□ GitHub push
```
