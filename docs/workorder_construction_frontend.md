# TAI Safe 건설섹터 프론트엔드 작업지시서

---

## ★ API v2.1.0 추가 기능 (최우선 반영)

### 1. 법령진단 독립 실행 — `construction-site-list.html` 사이드패널

**표시 위치**: 사이드패널 > 법령진단 탭

**버튼 코드 패턴:**
```javascript
async function runDiagnosis(siteId) {
  const btn = document.getElementById('btnDiagnose');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>진단 중...';
  try {
    const res = await fetch(`${API_BASE}/construction/sites/${siteId}/diagnose`, {
      method: 'POST', headers: hdr()
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || '진단 실패');
    const d = json.data;
    // 결과 표시
    document.getElementById('diagnosisResult').innerHTML = `
      <div class="alert alert-success py-2">
        <strong>진단 완료</strong> — 적용 의무 ${d.applicable_rules}건
        <div class="mt-1 small">
          작업 전 점검 ${d.by_obligation_type?.BEFORE_WORK || 0}건 ·
          조치 ${d.by_obligation_type?.ACTION || 0}건 ·
          정기점검 ${d.by_obligation_type?.INSPECT || 0}건
        </div>
      </div>`;
    // 현장 데이터 업데이트
    const site = _sites.find(s => s.id === siteId);
    if (site) site.diagnosis_applicable_count = d.applicable_rules;
    showToast('success', `법령진단 완료 — ${d.applicable_rules}건 적용`);
  } catch(e) {
    showToast('error', e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="ti tabler-stethoscope me-1"></i>법령진단 실행';
  }
}
```

---

### 2. 작업일정 자동 생성 버튼

**`diagnosis_applicable_count == 0` 시 버튼 비활성 조건:**
```javascript
function renderScheduleBtn(site) {
  const hasRules = (site.diagnosis_applicable_count || 0) > 0;
  return hasRules
    ? `<button class="btn btn-primary btn-sm" onclick="generateSchedules('${site.id}')">
         <i class="ti tabler-calendar-plus me-1"></i>일정 생성
       </button>`
    : `<button class="btn btn-secondary btn-sm" disabled
         title="법령진단을 먼저 실행하세요">
         <i class="ti tabler-lock me-1"></i>일정 생성
       </button>`;
}

async function generateSchedules(siteId) {
  try {
    const res = await fetch(`${API_BASE}/construction/sites/${siteId}/generate-schedules`, {
      method: 'POST', headers: hdr()
    });
    const json = await res.json();
    if (!res.ok) {
      // "법령진단을 먼저 실행하세요" 에러 처리
      if (res.status === 400) {
        showToast('warning', json.detail || '법령진단을 먼저 실행하세요.');
        return;
      }
      throw new Error(json.detail || '생성 실패');
    }
    const d = json.data;
    showToast('success', `일정 생성 완료 — ${d.created}건 생성, ${d.skipped}건 조건미충족`);
  } catch(e) {
    showToast('error', e.message);
  }
}
```

---

### 3. 점검 저장 → 제출 후 결과별 UI 처리

```javascript
async function submitCheck(siteId, processId, results) {
  const btn = document.getElementById('submitBtn');
  btn.disabled = true;
  btn.textContent = '저장 중...';
  try {
    const checklist_items = Object.entries(results).map(([item_name, result]) => ({
      item_name, result, note: ''
    }));
    const res = await fetch(`${API_BASE}/construction/inspections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        site_id: siteId,
        process_id: processId,
        inspector_phone: MY_PHONE,
        checklist_items   // overall_result 생략 → API 자동 계산
      })
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || '저장 실패');

    const issues = checklist_items.filter(i => i.result === 'bad');
    // 결과별 UI 처리
    document.getElementById('mainContent').style.display = 'none';
    const success = document.getElementById('successScreen');
    success.style.display = 'flex';
    if (issues.length > 0) {
      success.querySelector('.result-msg').textContent =
        `이상 항목 ${issues.length}건 — 안전관리자에게 자동 전달됐습니다.`;
      success.querySelector('.result-icon').textContent = '⚠️';
    } else {
      success.querySelector('.result-msg').textContent = '모든 항목 정상입니다.';
      success.querySelector('.result-icon').textContent = '✅';
    }
  } catch(e) {
    showToast('error', e.message);
    btn.disabled = false;
    btn.textContent = '점검 완료';
  }
}
```

---

## 구현 화면 목록 (safe.taieng.co.kr — tadmin)

---

## 화면 1: 건설현장 목록 (construction-site-list.html)

**경로**: `tadmin/full-version/html/horizontal-menu-template/construction-site-list.html`  
**메뉴**: 건설관리 > 건설현장

### 레이아웃
```
[+ 현장 등록] 버튼

[검색] [상태 필터] [공사유형 필터]

테이블:
  No. | 현장명 | 공사유형 | 공사금액 | 근로자 | 공기(시작-종료) | 진단 | 일정생성 | 상태

사이드 패널 (등록/상세/수정):
  기본정보 탭:
    - 현장명 * (text)
    - 공사유형 * (select: 건축/토목/복합)
    - 공사금액 * (number, 원 단위)
    - 총 근로자 수 * → 직영/하도급 분리 입력
    - 주소 (주소검색 버튼)
    - 공사 기간 * (시작일, 종료일)
    - 안전관리자 선임 필요 여부: [자동계산 뱃지]
      - 건축 150억 이상 / 토목 120억 이상 → 빨간 뱃지 "선임 필요"
      - 미만 → 회색 뱃지 "선임 불필요"
  
  공정 탭:
    - 공정 목록 테이블 (공정명, 작업유형, 계획기간, 진행률)
    - [+ 공정 추가] 버튼
  
  법령진단 탭 (★ v2.1.0):
    - [법령진단 실행] 버튼 → runDiagnosis() 호출
    - 진단 결과 요약 (applicable_rules, by_obligation_type 표시)
    - [일정 생성] 버튼 → diagnosis_applicable_count=0 이면 비활성
    - [점검항목관리로 이동] 링크
```

### API 연결
```javascript
GET  /construction/sites?company_id={cid}&page=1&size=20
POST /construction/sites
POST /construction/sites/{id}/diagnose          // ★ v2.1.0
POST /construction/sites/{id}/generate-schedules // ★ v2.1.0
GET  /construction/sites/{id}/processes
```

---

## 화면 2: 건설 공정 관리 (construction-process.html)

**경로**: `tadmin/full-version/html/horizontal-menu-template/construction-process.html`  
**메뉴**: 건설관리 > 공정관리  
**URL 파라미터**: `?site_id={id}`

### 레이아웃
```
[현장명] 배너

공정 목록 테이블:
  No. | 공정명 | 작업유형 | 고위험 | 계획시작 | 계획종료 | 진행률 | 상태
  - 고위험: 빨간 뱃지
  - 진행률: Progress bar
  - 행 클릭 → 사이드 패널

사이드 패널:
  - 공정명 *
  - 작업유형 * (굴착/철골/거푸집/해체/고소작업/크레인/기타)
  - 고위험 자동 판별 [자동 뱃지]
  - 계획 기간 * (시작일, 종료일)
  - 진행률 슬라이더 (0-100)
  - 현장 근로자 수
```

---

## 화면 3: 건설 점검항목관리 (construction-inspection-anchor.html)

**산업 섹터 inspection-anchor.html 재활용 + 건설 차이점:**

```
차이점 1: 현장 선택 (factorySelect → siteSelect)
차이점 2: 공정 연결 컬럼 추가 (BEFORE_WORK → 공정 선택 필수)
차이점 3: BEFORE_WORK → 주기 자동 '매일', 기준일 = 공정 시작일

4가지 조건 동일:
  언제 · 누가 · 무엇을 · 어떻게 → 모두 충족 시 스케줄 생성
```

---

## 화면 4: 건설 점검 결과 (construction-inspection-list.html)

```
[현장 선택] [공정 필터] [기간 필터] [결과 필터]

테이블:
  No. | 현장 | 공정 | 점검일시 | 점검자 | 이상건수 | 시정상태 | 결과

상세 패널:
  - 체크항목 목록 (정상/이상)
  - 이상 항목 사진
  - 시정조치 입력
  - [시정완료 처리] 버튼

통계 카드: 전체 | 이번달 | 이상발생 | 시정미완료
```

---

## 화면 5: 건설 작업자 관리 (construction-worker-list.html)

```
구분 탭: [전체] [직영] [하도급]

테이블:
  No. | 이름 | 구분 | 업체명 | 직종 | 등록일 | 앱설치 | 상태

등록 패널:
  - 이름, 연락처 *
  - 구분: 직영 / 하도급 *
  - 하도급 시: 업체명 추가
  - 직종 *
```

---

## 화면 6: 건설 현장 작업자 점검 (worker-check-construction.html)

**★ v2.1.0 checklist_items 형식 + 결과별 UI 처리 적용**

```
[현장명] 헤더

공정별 그룹화:
  공정명 (고위험 뱃지)
  └─ 작업 전 점검 항목
       [정상] [이상] 버튼
       이상 → 사진 첨부 영역

[점검 완료] → submitCheck() 호출 (★ v2.1.0 패턴)
  이상: ⚠️ + "안전관리자에게 즉시 전달됐습니다"
  정상: ✅ + "모든 항목 정상입니다"
```

---

## 메뉴 연결 (menu-tadmin.js)

```
건설현장     → construction-site-list.html
공정관리     → construction-process.html
점검항목관리 → construction-inspection-anchor.html
점검이력     → construction-inspection-list.html
작업자관리   → construction-worker-list.html
```

---

## 구현 순서

```
1단계: construction-site-list.html (★ v2.1.0 진단 버튼 포함)
2단계: construction-inspection-anchor.html
3단계: construction-inspection-list.html
4단계: construction-process.html
5단계: construction-worker-list.html
6단계: worker-check-construction.html (★ v2.1.0 submitCheck 패턴)
```

---

## 중요 비고

1. **건설현장은 factory가 아님**: `site_id` 기반으로 동작
2. **diagnosis_applicable_count**: 일정생성 버튼 활성화 조건 — 반드시 체크
3. **overall_result 생략**: API가 자동 계산하므로 프론트에서 보내지 않아도 됨
4. **공사 완료 현장**: `status_code=COMPLETED` → 읽기전용 표시
