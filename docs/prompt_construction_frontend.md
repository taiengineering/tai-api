# 프론트엔드 창 시작 프롬프트 — 건설관리 v2.1.0

> 이 파일을 프론트엔드 Claude 창에 붙여넣어 세션을 시작합니다.

---

아래 내용을 읽고 즉시 준비됐다고 알려주세요.

## 프로젝트 정보

- **레포**: `taiengineering/tai-admin` (branch: main)
- **작업 경로**: `tadmin/full-version/html/horizontal-menu-template/`
- **배포**: Cloudflare Pages → safe.taieng.co.kr
- **템플릿**: Vuexy Bootstrap 5 (HTML 버전)

## 필수 HTML 속성 (모든 페이지 공통)
```html
<html class="layout-navbar-fixed layout-menu-fixed layout-compact"
  data-assets-path="../../assets/"
  data-bs-theme="light"
  data-skin="default"
  data-template="horizontal-menu-template"
  dir="ltr" lang="ko">
```

## 필수 CSS/JS 로드 순서
```html
<!-- HEAD -->
<script src="../../assets/js/tai/auth-guard.js"></script>
<link href="../../assets/vendor/fonts/iconify-icons.css" rel="stylesheet"/>
<link href="../../assets/vendor/libs/node-waves/node-waves.css" rel="stylesheet"/>
<link href="../../assets/vendor/css/core.css" rel="stylesheet"/>
<link href="../../assets/css/demo.css" rel="stylesheet"/>
<link href="../../assets/css/tai/custom.css" rel="stylesheet"/>
<script src="../../assets/vendor/js/helpers.js"></script>
<script src="../../assets/vendor/js/template-customizer.js"></script>
<script src="../../assets/js/config.js"></script>

<!-- BODY 하단 -->
<script src="../../assets/vendor/libs/jquery/jquery.js"></script>
<script src="../../assets/vendor/libs/popper/popper.js"></script>
<script src="../../assets/vendor/js/bootstrap.js"></script>
<script src="../../assets/vendor/libs/node-waves/node-waves.js"></script>
<script src="../../assets/vendor/js/menu.js"></script>
<script src="../../assets/js/main.js"></script>
<script src="../../assets/js/utils.js"></script>
<script src="../../assets/js/tai/api.js"></script>
<script src="../../assets/js/tai/toast.js"></script>
<script src="../../assets/js/tai/globals.js"></script>
<script src="../../assets/js/tai/menu-tadmin.js"></script>
<script src="../../assets/js/tai/nav-tadmin.js"></script>
<script src="../../assets/js/tai/notification.js"></script>
<script>buildMenu('layout-menu');</script>
```

## 건설관리 API 기본 정보

- **기준 API**: `https://api.taieng.co.kr/construction`
- **현재 API 버전**: v2.1.0 (완전 완료)

### 핵심 구조
```
company → construction_site (현장) → factory_id (자동생성, inspection-sets 연동)
```

### v2.1.0 신규 API (프론트 구현 필수)
```
POST /construction/sites/{id}/diagnose          → 법령진단 재실행 버튼
POST /construction/sites/{id}/generate-schedules → 일정 생성 버튼
```

### 점검 저장 시 FCM 자동 발송
- `overall_result` 생략 가능 → API가 자동 계산
- ISSUE/FAIL 시 관리자 FCM 자동 발송 (프론트 처리 불필요)
- 응답의 `overall_result`, `defect_count`만 UI에 표시

### checklist_items 형식
```json
[{ "item_name": "PPE 착용", "result": "good", "note": "" }]
```

## 건설 색상 (시설관리 파란색 대신 주황)
```css
background: linear-gradient(135deg, #d97706, #92400e);
```

## localStorage 키 규칙
```js
localStorage.getItem('company_id')                   // 회사 ID
localStorage.getItem('selectedConstructionSiteId')    // construction_sites.id
localStorage.getItem('selectedConstructionFactoryId') // factory_id (inspection-sets용)
```

## 상태코드 배지
```js
const STATUS_CLR = { PLANNED:'secondary', IN_PROGRESS:'primary', DONE:'success', SUSPENDED:'warning' };
const ENTRY_CLR  = { IN:'success', OUT:'secondary', OFFSITE:'warning' };
const RESULT_CLR = { PASS:'success', ISSUE:'warning', FAIL:'danger' };
const WORKER_CLR = { DIRECT:'primary', SUBCON:'secondary' };
```

## 테이블 공통 규칙
- 1번 컬럼: 전체선택 체크박스
- 2번 컬럼: No. (1부터)

## 작업 순서 (이 순서대로 진행)

```
1. construction-site-list.html    ← 전면 재작성 (大)
2. construction-process.html      ← 신규 (中)
3. construction-worker-list.html  ← worker-list.html 재활용 (中)
4. construction-inspection-list.html ← 전면 재작성 (中)
5. construction-inspection-anchor.html ← inspection-anchor.html 재활용 (小)
6. worker-check-construction.html ← worker-check.html 재활용 (小)
```

## 참조 파일 (재활용 원본)

| 파일 | SHA | 용도 |
|------|-----|------|
| inspection-anchor.html | 5afb9f1b | #5 재활용 원본 |
| worker-list.html | eba689f0 | #3 재활용 원본 |
| worker-check.html | 2535ab23 | #6 재활용 원본 |

## 상세 워크오더

```
tai-api/docs/workorder_construction_frontend.md
tai-admin/docs/workorder_construction_frontend.md  (동일)
```

## 커밋 방법

```js
// 단일 파일
github-tai-admin:create_or_update_file (SHA 반드시 확인)

// 다중 파일 (권장)
github-tai-admin:push_files (SHA 불필요)
```

준비됐으면 OK라고 알려주세요.
