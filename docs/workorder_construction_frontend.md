# 건설관리 프론트엔드 워크오더

> 작성일: 2026-04-09  
> 기준 API: `routers/construction.py` v2.1.0  
> 기준 경로: `tadmin/full-version/html/horizontal-menu-template/`  
> 메뉴 진입: `safe.taieng.co.kr` → 건설관리

---

## ★ API v2.1.0 핵심 기능 (프론트 구현 필수)

### 1. `POST /construction/sites/{site_id}/diagnose`
- CONSTRUCTION 173개 규칙 → 조건 매칭
- 응답: `applicable_rules`, `by_obligation_type`
- 버튼 위치: construction-site-list.html 사이드패널

### 2. `POST /construction/sites/{site_id}/generate-schedules`
- 최신 진단 → work_schedules 생성 (중복 스킵)
- 응답: `created`, `skipped`, `total_rules`
- `diagnosis_applicable_count=0`이면 버튼 비활성

### 3. 점검 저장 → FCM 자동 발송
- `overall_result` 생략 가능 → API가 자동 계산
- ISSUE/FAIL 시 관리자 FCM 자동 발송 (프론트 처리 불필요)
- 프론트는 응답의 `overall_result`, `defect_count`만 UI 표시

---

## 공통 구조

```
company → construction_site (현장) → factory_id (자동, inspection-sets 연동)
```

### API 기본 경로
```
https://api.taieng.co.kr/construction
```

### 현장 셀렉터 공통 패턴 (주황색 배너)
```html
<div class="card mb-3" style="background:linear-gradient(135deg,#d97706,#92400e);border:none;">
  <div class="card-body py-3">
    <label class="form-label text-white small mb-1" style="opacity:.8">현장 선택</label>
    <select id="siteSelect" class="form-select" style="max-width:480px" onchange="onSiteChange()">
      <option value="">현장을 선택하세요</option>
    </select>
  </div>
</div>
```

### localStorage 키
```js
localStorage.getItem('company_id')                     // 회사 ID
localStorage.getItem('selectedConstructionSiteId')      // construction_sites.id
localStorage.getItem('selectedConstructionFactoryId')   // factory_id (inspection-sets용)
```

### 상태코드 배지
```js
const STATUS_CLR = { PLANNED:'secondary', IN_PROGRESS:'primary', DONE:'success', SUSPENDED:'warning' };
const ENTRY_CLR  = { IN:'success', OUT:'secondary', OFFSITE:'warning' };
const RESULT_CLR = { PASS:'success', ISSUE:'warning', FAIL:'danger' };
const WORKER_CLR = { DIRECT:'primary', SUBCON:'secondary' };
```

### 테이블 공통 규칙
- 1번 컬럼: 전체선택 체크박스
- 2번 컬럼: No. (1부터)

---

## 화면 목록

| 순서 | 파일 | 방식 | 메뉴 경로 |
|------|------|------|-----------|
| 1 | construction-site-list.html | 전면 재작성 | 건설관리 > 현장관리 |
| 2 | construction-process.html | 신규 | 건설관리 > 공정관리 |
| 3 | construction-worker-list.html | worker-list.html 재활용 | 건설관리 > 작업관리 |
| 4 | construction-inspection-list.html | 전면 재작성 | 건설관리 > 점검관리 |
| 5 | construction-inspection-anchor.html | inspection-anchor.html 재활용 | 건설관리 > 점검항목관리 |
| 6 | worker-check-construction.html | worker-check.html 재활용 | 작업자 현장점검 제출 |

---

## 1. construction-site-list.html — 현장관리

### API
```
GET    /construction/sites?company_id=&status_code=&search=&page=&size=
POST   /construction/sites
PATCH  /construction/sites/:site_id
DELETE /construction/sites/:site_id
GET    /construction/sites/:site_id/stats
POST   /construction/sites/:site_id/diagnose         ← 재실행 버튼
POST   /construction/sites/:site_id/generate-schedules ← 일정 생성 버튼
```

### 테이블 컬럼
체크 | No. | 현장명 | 유형 | 도급금액 | 상태 | 안전관리자 | 진단 건수 | 기간 | 액션
- 안전관리자: `safety_manager_required=true` 시 뱃지
- 진단 건수: `diagnosis_applicable_count` 또는 `진단 필요` 버튼

### 사이드 패널 (stats)
```
현장명 / 주소
공정: 전체 N / 진행중 N
작업: 전체 N / PTW승인 N
작업자: 전체 N / 현장내 N
점검: 전체 N / 이상 N
[법령진단 재실행]  [일정 생성]  [현장 수정]
```
※ `diagnosis_applicable_count`=0이면 `일정 생성` 비활성

### 등록 모달
현장명* | 유형(BUILDING/CIVIL)* | 도급금액(억)* | 시작일 | 종료일 | 주소 | 현장소장 | 직영인원 | 하도급인원 | 비고

### 코드 포인트
```js
// 등록 후 auto 결과 표시
const { data, auto } = await res.json();
if (auto?.diagnosis) showToast('success', `법령 ${auto.diagnosis.applicable_count}건 적용`);
if (auto?.schedules) showToast('info', `작업일정 ${auto.schedules.created}건 생성`);

// 진단 재실행
POST /construction/sites/{site_id}/diagnose
→ showToast('success', `적용 ${j.data.applicable_rules}건 (선임 N, 점검 N)`);

// 일정 생성
POST /construction/sites/{site_id}/generate-schedules
→ showToast('info', `${j.data.created}건 생성, ${j.data.skipped}건 스킵`);
```

---

## 2. construction-process.html — 공정관리

### API
```
GET    /construction/sites/:site_id/processes?status_code=&page=&size=
POST   /construction/sites/:site_id/processes
PATCH  /construction/processes/:process_id
DELETE /construction/processes/:process_id
GET    /construction/kcsc/processes?search=&size=20   ← 자동완성
```

### 테이블 컬럼
No. | 공정명 | KCSC코드 | 계획시작 | 계획종료 | 진행율 | 투입인원 | 위험작업 | 상태 | 액션
- 진행율: 프로그레스 바 (`progress_rate`)
- 위험작업: `is_high_risk=true` → `⚠️ 위험` 뱃지

### 등록 모달
공정명* | KCSC 공정 검색 | 계획시작 | 계획종료 | 투입인원 | 위험작업여부 | 비고

---

## 3. construction-worker-list.html — 작업자관리

`worker-list.html` 재활용. **worker_registry → construction_workers** 교체.

### API
```
GET    /construction/sites/:site_id/workers?worker_type=&entry_status=&search=&page=&size=
POST   /construction/sites/:site_id/workers
PATCH  /construction/workers/:worker_id
PATCH  /construction/workers/:worker_id/entry   ← 출입 상태 변경
DELETE /construction/workers/:worker_id
```

### 테이블 컬럼
No. | 이름 | 구분(DIRECT/SUBCON) | 소속 | 역할 | 출입상태 | 안전교육일 | 입사일 | 출입변경 | 액션

### 통계 카드
`[전체 N] [현장내(IN) N] [직영 N] [하도급 N]`

### 코드 포인트
```js
async function changeEntry(workerId, status) {
  await fetch(`${API}/construction/workers/${workerId}/entry`, {
    method: 'PATCH', headers: hdr(),
    body: JSON.stringify({ entry_status: status })
  });
}
```

---

## 4. construction-inspection-list.html — 점검관리

### API
```
GET    /construction/sites/:site_id/inspections?inspection_type=&overall_result=&page=&size=
POST   /construction/sites/:site_id/inspections
PATCH  /construction/inspections/:inspection_id/corrective
DELETE /construction/inspections/:inspection_id
```

### 테이블 컬럼
No. | 점검일시 | 점검유형 | 점검자 | 결과 | 이상건수 | 시정조치 | 마감일 | 액션
- 결과: PASS=초록, ISSUE=주황, FAIL=빨강
- 시정조치: PENDING/IN_PROGRESS/DONE + 인라인 변경

### 통계 카드
`[전체 N건] [이상 N건] [시정완료율 N%] [이번달 N건]`

### 등록 모달 체크리스트
```js
// overall_result 생략 → API 자동 계산 (v2.1.0)
const payload = {
  inspection_type: 'BEFORE_WORK',
  checklist_items: items.map(i => ({ item_name:i.name, result:i.result, note:i.note||'' })),
  // overall_result 생략
};
```

---

## 5. construction-inspection-anchor.html — 점검항목관리

`inspection-anchor.html` (SHA: 5afb9f1b) 재활용. **변경 사항만 적용.**

### 변경 사항

```js
// 1. 타이틀
'점검항목관리' → '건설 점검항목관리'

// 2. 배너 컬러
'#1a5fd4,#0c2d5c' → '#d97706,#92400e'

// 3. 셀렉터
factorySelect → siteSelect
GET /factories → GET /construction/sites

// 4. 값 매핑 (inspection-sets는 factory_id 기반)
o.value = s.factory_id;  // ← factory_id
o.dataset.siteId = s.id; // ← 원본 site_id 보관

// 5. localStorage
localStorage.setItem('selectedConstructionSiteId', _siteId);
localStorage.setItem('selectedConstructionFactoryId', _factoryId);
```

나머지 탭/4조건/법령원문 모달 등 원본 그대로.

---

## 6. worker-check-construction.html — 작업자 현장점검

`worker-check.html` (SHA: 2535ab23) 재활용.

### 변경 사항

```js
// URL 파라미터
기존: ?factory_id=xxx&set_id=xxx
건설: ?site_id=xxx&work_id=xxx

// 기본 체크리스트 (DB 항목 없을 때)
const DEFAULT_CHECKLIST = [
  { id:'c1', name:'PPE(안전모/조끼/안전화) 착용 확인' },
  { id:'c2', name:'작업구역 안전 펜스 설치 확인' },
  { id:'c3', name:'위험물질 취급 안전 절차 확인' },
  { id:'c4', name:'비상연락망 및 소화기 위치 확인' },
  { id:'c5', name:'장비/공구 이상 유무 확인' },
];

// 제출 API (v2.1.0 — FCM 자동 발송)
POST /construction/sites/{site_id}/inspections
body: { inspection_type:'BEFORE_WORK', checklist_items:[{item_name,result,note}] }

// 제출 후
if (j.data.overall_result === 'ISSUE') {
  showResult('⚠️ 이상 항목이 감지됐습니다. 관리자에게 자동 보고됐습니다.', 'warning');
} else {
  showResult('✅ 점검 완료. 안전하게 작업해주세요!', 'success');
}
```
