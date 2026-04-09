# 건설 섹터 프론트엔드 작업 프롬프트

> 이 파일을 **프론트엔드 Claude 창**에 그대로 붙여넣으세요.

---

```
당신은 TAI Safe 프론트엔드 개발자입니다.

## 프로젝트 스택
- HTML5 + Bootstrap 5 + Vuexy 템플릿
- Cloudflare Pages 배포: safe.taieng.co.kr
- GitHub: taiengineering/tai-admin
- 파일 경로: tadmin/full-version/html/horizontal-menu-template/

## Vuexy 필수 HTML 속성
```html
<html data-skin="default" dir="ltr" data-bs-theme="light" data-assets-path="../../assets/" ...>
```
필수 CSS: iconify-icons.css, node-waves.css, core.css
공유 메뉴: menu-tadmin.js
API Base: https://api.taieng.co.kr
인증: localStorage.getItem('access_token') → Bearer 토큰

## 오늘 작업: 건설 섹터 프론트엔드 구현

---

### ★ 최우선 스펙 (v2.1.0) — 반드시 준수

#### 1. 법령진단 버튼 (construction-site-list.html 사이드패널 법령진단 탭)
```javascript
async function runDiagnosis(siteId) {
  const btn = document.getElementById('btnDiagnose');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>진단 중...';
  try {
    const res = await fetch(`${API}/construction/sites/${siteId}/diagnose`,
      { method: 'POST', headers: hdr() });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || '진단 실패');
    const d = json.data;
    document.getElementById('diagnosisResult').innerHTML = `
      <div class="alert alert-success py-2">
        <strong>진단 완료</strong> — 적용 의무 ${d.applicable_rules}건
        <div class="mt-1 small">
          작업 전 점검 ${d.by_obligation_type?.BEFORE_WORK || 0}건 ·
          조치 ${d.by_obligation_type?.ACTION || 0}건 ·
          정기점검 ${d.by_obligation_type?.INSPECT || 0}건
        </div>
      </div>`;
    const site = _sites.find(s => s.id === siteId);
    if (site) site.diagnosis_applicable_count = d.applicable_rules;
    showToast('success', `법령진단 완료 — ${d.applicable_rules}건 적용`);
  } catch(e) { showToast('error', e.message); }
  finally { btn.disabled = false; btn.innerHTML = '<i class="ti tabler-stethoscope me-1"></i>법령진단 실행'; }
}
```

#### 2. 일정생성 버튼 — diagnosis_applicable_count=0이면 비활성
```javascript
function renderScheduleBtn(site) {
  const hasRules = (site.diagnosis_applicable_count || 0) > 0;
  return hasRules
    ? `<button class="btn btn-primary btn-sm" onclick="generateSchedules('${site.id}')">
         <i class="ti tabler-calendar-plus me-1"></i>일정 생성</button>`
    : `<button class="btn btn-secondary btn-sm" disabled title="법령진단을 먼저 실행하세요">
         <i class="ti tabler-lock me-1"></i>일정 생성</button>`;
}

async function generateSchedules(siteId) {
  const res = await fetch(`${API}/construction/sites/${siteId}/generate-schedules`,
    { method: 'POST', headers: hdr() });
  const json = await res.json();
  if (res.status === 400) { showToast('warning', json.detail); return; }
  if (!res.ok) { showToast('error', json.detail || '생성 실패'); return; }
  const d = json.data;
  showToast('success', `일정 생성 완료 — ${d.created}건 생성, ${d.skipped}건 조건미충족`);
}
```

#### 3. 점검 제출 — overall_result 생략, 결과별 UI 처리
```javascript
async function submitCheck(siteId, processId, results) {
  const btn = document.getElementById('submitBtn');
  btn.disabled = true; btn.textContent = '저장 중...';
  try {
    const checklist_items = Object.entries(results).map(([item_name, result]) =>
      ({ item_name, result, note: '' }));
    const res = await fetch(`${API}/construction/inspections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        site_id: siteId, process_id: processId,
        inspector_phone: MY_PHONE,
        checklist_items  // overall_result 생략 → API 자동 계산
      })
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || '저장 실패');
    const issues = checklist_items.filter(i => i.result === 'bad');
    document.getElementById('mainContent').style.display = 'none';
    const successEl = document.getElementById('successScreen');
    successEl.style.display = 'flex';
    if (issues.length > 0) {
      successEl.querySelector('.result-icon').textContent = '⚠️';
      successEl.querySelector('.result-msg').textContent =
        `이상 ${issues.length}건 — 안전관리자에게 자동 전달됩니다.`;
    } else {
      successEl.querySelector('.result-icon').textContent = '✅';
      successEl.querySelector('.result-msg').textContent = '모든 항목 정상입니다.';
    }
  } catch(e) {
    showToast('error', e.message);
    btn.disabled = false; btn.textContent = '점검 완료';
  }
}
```

---

### 구현 순서

**1단계: construction-site-list.html**
- 경로: tadmin/full-version/html/horizontal-menu-template/construction-site-list.html
- 테이블: No. | 현장명 | 공사유형 | 공사금액 | 근로자 | 공기 | 진단 | 일정생성 | 상태
- 사이드 패널 3탭: [기본정보] [공정] [법령진단 ★]
- 선임뱃지 자동계산:
```javascript
function calcManagerBadge(type, amount) {
  const t = {"건축": 15e9, "토목": 12e9, "복합": 12e9};
  return amount >= (t[type] || 15e9)
    ? `<span class="badge bg-danger">선임 필요</span>`
    : `<span class="badge bg-secondary">선임 불필요</span>`;
}
```
- API: GET/POST /construction/sites, POST /construction/sites/{id}/diagnose ★, POST /construction/sites/{id}/generate-schedules ★

**2단계: construction-inspection-anchor.html**
- 기존 inspection-anchor.html 재활용 (동일 구조)
- 변경점:
  - factorySelect → siteSelect (건설현장 드롭다운)
  - 공정 연결 컬럼 추가 (BEFORE_WORK → 공정 선택 필수)
  - BEFORE_WORK 주기 자동 "매일" 고정
- 4가지 조건 (언제·누가·무엇을·어떻게) 동일 적용
- API: GET /inspection-sets?site_id={id}&sector=CONSTRUCTION, POST /construction/sites/{id}/generate-schedules

**3단계: construction-inspection-list.html**
- 필터: 현장 | 공정 | 기간 | 결과(전체/정상/이상)
- 테이블: No. | 현장 | 공정 | 점검일시 | 점검자 | 이상건수 | 시정상태 | 결과
- 상세 패널: 체크항목 목록 / 사진 / 시정조치 입력 / [시정완료] 버튼
- API: GET /construction/inspections?site_id={id}, PATCH /construction/inspections/{id}

**4단계: construction-process.html**
- URL: ?site_id={id}
- 테이블: 공정명 | 작업유형 | 고위험뱃지 | 계획기간 | 진행률 | 상태
- 사이드패널: 공정명* / 작업유형* / 고위험 자동뱃지 / 기간* / 진행률슬라이더
- API: GET/POST/PATCH/DELETE /construction/sites/{id}/processes

**5단계: construction-worker-list.html**
- 탭: [전체] [직영] [하도급]
- 테이블: No. | 이름 | 구분 | 업체명 | 직종 | 등록일 | 앱설치
- 하도급 선택 시 업체명 필드 추가
- API: GET/POST/DELETE /construction/sites/{id}/workers

**6단계: worker-check-construction.html**
- 기존 worker-check.html 재활용 + 공정별 그룹화 추가
- 이상 선택 시 사진 첨부 영역 표시
- submitCheck() → ★ v2.1.0 패턴 적용

---

### 메뉴 연결 (menu-tadmin.js 확인 및 추가)
- 건설현장     → construction-site-list.html
- 공정관리     → construction-process.html
- 점검항목관리 → construction-inspection-anchor.html
- 점검이력     → construction-inspection-list.html
- 작업자관리   → construction-worker-list.html

---

### 공통 주의사항
- 테이블 첫 번째 컬럼: 전체선택 체크박스, 두 번째 컬럼: No. (TAI 표준)
- diagnosis_applicable_count=0이면 일정생성 버튼 반드시 비활성
- overall_result는 API가 자동 계산하므로 전송하지 않아도 됨
- 건설현장은 factory_id 없이 site_id 기반으로 동작
- 완료 시 GitHub push (taiengineering/tai-admin)
```
