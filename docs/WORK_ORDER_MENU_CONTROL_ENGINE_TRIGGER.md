# 작업지시서: 산업 메뉴 제어 + 법령엔진 가동 연결

> 작성일: 2026-04-24  
> 우선순위: 🔴 최상위  
> 대상 레포: `tai-admin` (프론트엔드)

---

## 배경

산업 섹터는 플랜에 따라 입력 깊이가 다릅니다:
- STARTER (79K): 시설까지만 → 공정/설비 메뉴 🔒
- BUSINESS (149K): + 공정까지 → 설비 메뉴 🔒
- PRO (249K): + 설비까지 → 모든 메뉴 활성
- CUSTOM: 전체 활성

건물/건설은 메뉴 제어 없음 (모든 플랜 동일 메뉴).

---

## TASK 1: 산업 플랜별 메뉴 잠금

### 파일: `tadmin/full-version/assets/js/tai/menu-tadmin.js`

### 로직

로그인 시 localStorage에 저장되는 값:
```js
const sector = localStorage.getItem('contract_sector');   // 'BUILDING' | 'INDUSTRY' | 'CONSTRUCTION'
const planCode = localStorage.getItem('contract_plan_code'); // 'INDUSTRY_STARTER_V2' | 'INDUSTRY_BUSINESS_V2' | 'INDUSTRY_PRO' | 'INDUSTRY_CUSTOM_V2'
```

### 메뉴 잠금 규칙 (산업만 적용)

```
if (sector === 'INDUSTRY') {
  STARTER: 공정관리, 설비관리 메뉴 → 클릭 시 잠금 모달
  BUSINESS: 설비관리 메뉴 → 클릭 시 잠금 모달
  PRO / CUSTOM: 모두 활성
}
```

### 잠금 모달 UI

메뉴 클릭 시 잠금된 메뉴면 페이지 이동 대신 모달 표시:

```html
<div class="modal">
  <div class="modal-header">
    <h5>🔒 공정 관리</h5>
  </div>
  <div class="modal-body">
    <p>이 기능은 <strong>BUSINESS</strong> 이상에서 사용할 수 있습니다.</p>
    <p class="text-muted">공정별 위험요인을 등록하면 더 정밀한 점검항목이 생성됩니다.</p>
  </div>
  <div class="modal-footer">
    <a href="my-contract.html" class="btn btn-primary">플랜 업그레이드</a>
    <button class="btn btn-secondary" data-bs-dismiss="modal">닫기</button>
  </div>
</div>
```

### 메뉴 아이템 대상 (메뉴 ID 기준)

| 메뉴 | 잠금 대상 |
|------|----------|
| 공정 관리 (`process-manage`, `process-select`) | STARTER 잠금 |
| 설비 관리 (`my-equipment`, `equipment-qr-manager`) | STARTER + BUSINESS 잠금 |

🚨 **주의**: `inspection-anchor`, `work-schedule-list`, `worker-check` 등 핵심 메뉴는 절대 잠금하지 않음

---

## TASK 2: "일정생성" 버튼 → 법령엔진 가동 → inspection-anchor 연결

### 파일: `tadmin/full-version/html/horizontal-menu-template/factory-list.html`

### 요구사항

사업장 목록 테이블의 각 행에 "일정생성" 버튼 추가.

### 버튼 동작 흐름

```js
async function generateSchedule(factoryId) {
  const btn = event.target;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>법령 분석 중...';

  try {
    // Step 1: 법령엔진 가동
    const r1 = await fetch(`${API}/legal-engine/apply/${factoryId}`, {
      method: 'POST',
      headers: hdr()
    });
    if (!r1.ok) throw new Error('법령 분석 실패');

    // Step 2: inspection_sets 자동 생성
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>점검항목 생성 중...';
    const r2 = await fetch(`${API}/legal-engine/create-inspection-sets/${factoryId}`, {
      method: 'POST',
      headers: hdr()
    });
    if (!r2.ok) throw new Error('점검항목 생성 실패');
    const data = await r2.json();

    // Step 3: inspection-anchor로 이동
    showToast('success', `점검항목 ${data.data?.created || 0}건 생성 완료`);
    setTimeout(() => {
      location.href = `inspection-anchor.html?factory_id=${factoryId}`;
    }, 1000);

  } catch(e) {
    showToast('error', e.message);
    btn.disabled = false;
    btn.innerHTML = '<i class="ti tabler-calendar-plus me-1"></i>일정생성';
  }
}
```

### 버튼 UI

테이블 행의 액션 열에 추가:
```html
<button class="btn btn-sm btn-primary" onclick="generateSchedule('${factory.id}')">
  <i class="ti tabler-calendar-plus me-1"></i>일정생성
</button>
```

### 표시 조건
- 이미 inspection_sets가 있는 사업장: "점검관리" 버튼 (파란색, inspection-anchor로 직행)
- 없는 사업장: "일정생성" 버튼 (초록색, 엔진 가동)

이를 확인하려면:
```js
// 사업장 목록 로드 시 inspection_sets 존재 여부 확인
const setsRes = await fetch(`${API}/inspection-sets?factory_id=${f.id}&page=1&size=1`, {headers: hdr()});
const setsData = await setsRes.json();
const hasInspectionSets = (setsData.data?.items?.length || 0) > 0;
```

---

## TASK 3: 사이드 메뉴에 inspection-anchor 링크 확인

### 파일: `tadmin/full-version/assets/js/tai/menu-tadmin.js`

사이드 메뉴에 "점검항목관리" 메뉴가 있는지 확인.
없으면 추가 (위치: "안전관리" 그룹 내):

```js
{ text: '점검항목관리', icon: 'ti tabler-list-check', url: 'inspection-anchor.html' }
```

---

## API 참조 (백엔드 이미 존재)

| 엔드포인트 | 용도 | 상태 |
|-----------|------|------|
| `POST /legal-engine/apply/{factory_id}` | 법령엔진 가동 | ✅ 작동 |
| `POST /legal-engine/create-inspection-sets/{factory_id}` | inspection_sets 생성 | ✅ 작동 (323건 생성 이력) |
| `GET /inspection-sets?factory_id=...` | 점검 세트 조회 | ✅ 작동 |
| `GET /contracts/my` | 현재 계약 조회 | ✅ 작동 |

---

## localStorage 키 참조

로그인 시 `auth-login-cover.html`의 `saveContractInfo()`에서 저장:

```
contract_plan_code  → 'INDUSTRY_STARTER_V2' | 'INDUSTRY_BUSINESS_V2' | ...
contract_sector     → 'INDUSTRY' | 'BUILDING' | 'CONSTRUCTION'
contract_level      → '1' | '2' | '3'
contract_addons     → JSON array
```

---

## 서비스 계층 분리 규칙

20KB 이상 라우터는 Router/Service/Schema/Tests 분리 필수.  
Max 400라인 / 15KB 제한.  
`from db.supabase_client import get_supabase` 필수.

---

## 테스트 시나리오

1. 산업 STARTER 로그인 → 공정관리 메뉴 클릭 → 잠금 모달 표시
2. 산업 PRO 로그인 → 모든 메뉴 접근 가능
3. 건물 LITE 로그인 → 메뉴 제한 없음
4. 사업장 목록에서 "일정생성" 클릭 → 엔진 가동 → inspection-anchor 이동
5. 이미 생성된 사업장에서 "점검관리" 클릭 → inspection-anchor 직행
