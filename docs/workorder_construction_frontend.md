# TAI Safe 건설섹터 프론트엔드 작업지시서

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
  No. | 현장명 | 공사유형 | 공사금액 | 근로자 | 공기(시작-종료) | 진단 | 상태 | 액션

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
  
  법령진단 탭:
    - [법령진단 실행] 버튼
    - 진단 결과 요약 (의무 수, 유형별 분포)
    - [점검항목관리로 이동] 링크

```

### API 연결
```javascript
// 목록 조회
GET /construction/sites?company_id={cid}&page=1&size=20

// 등록
POST /construction/sites { site_name, construction_type, contract_amount, ... }

// 법령진단
POST /construction/sites/{id}/diagnose

// 공정 목록
GET /construction/sites/{id}/processes
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
  
  - 고위험 공정: 빨간 뱃지 "고위험"
  - 진행률: Progress bar
  - 행 클릭 → 사이드 패널 (수정)

사이드 패널:
  - 공정명 *
  - 작업유형 * (select: 굴착/철골/거푸집/해체/고소작업/크레인/기타)
  - 고위험 자동 판별 [자동 뱃지]
  - 계획 기간 * (시작일, 종료일)
  - 진행률 (0-100 슬라이더)
  - 현장 근로자 수
  - 메모
```

---

## 화면 3: 건설 점검항목관리 (construction-inspection-anchor.html)

**경로**: `tadmin/full-version/html/horizontal-menu-template/construction-inspection-anchor.html`  
**메뉴**: 건설관리 > 점검항목관리

### 산업 섹터 inspection-anchor.html과 동일한 구조 + 건설 차이점:

```
차이점 1: 현장 선택 (factorySelect → siteSelect)
  - 건설현장 드롭다운

차이점 2: 공정 연결 컬럼 추가
  - "어떤 공정" 컬럼: 해당 점검이 어느 공정과 연결되는지
  - BEFORE_WORK 의무 → 공정 선택 필수
  - 공정 없는 경우 현장 전체 적용

차이점 3: 작업 전 점검 자동 설정
  - BEFORE_WORK 의무 → 주기 자동 '매일' 고정
  - 기준일 = 공정 시작일 자동 적용 가능

4가지 조건 동일:
  언제(기준일) · 누가(담당자) · 무엇을(의무내용) · 어떻게(체크항목)
  → 모두 충족 시 스케줄 생성 버튼 활성
```

### API 연결
```javascript
// 건설 inspection_sets 조회 (sector=CONSTRUCTION)
GET /inspection-sets?site_id={site_id}&sector=CONSTRUCTION&page=1&size=100

// 스케줄 생성
POST /construction/sites/{site_id}/generate-schedules
```

---

## 화면 4: 건설 점검 결과 (construction-inspection-list.html)

**경로**: `tadmin/full-version/html/horizontal-menu-template/construction-inspection-list.html`  
**메뉴**: 건설관리 > 점검이력

### 레이아웃
```
[현장 선택] [공정 필터] [기간 필터] [결과 필터: 전체/정상/이상]

테이블:
  No. | 현장 | 공정 | 점검일시 | 점검자 | 체크항목 | 이상건수 | 시정상태 | 결과

행 클릭 → 점검 상세 패널:
  - 체크항목 목록 (정상/이상 결과)
  - 이상 항목 사진
  - 시정조치 입력 (이상 있는 경우)
  - 시정 기한
  - [시정완료 처리] 버튼

통계 카드 (상단):
  전체 | 이번달 | 이상발생 | 시정미완료
```

### API 연결
```javascript
GET /construction/inspections?site_id={id}&page=1&size=20
PATCH /construction/inspections/{id}  // 시정조치 업데이트
```

---

## 화면 5: 건설 작업자 관리 (construction-worker-list.html)

**경로**: `tadmin/full-version/html/horizontal-menu-template/construction-worker-list.html`  
**메뉴**: 건설관리 > 작업자관리

### 레이아웃 (기존 worker-list.html 구조 재활용 + 건설 특화)
```
[현장 선택] 배너

구분 탭: [전체] [직영] [하도급]

테이블:
  No. | 이름 | 구분(직영/하도급) | 업체명 | 직종 | 등록일 | 앱설치 | 상태

등록 패널:
  - 이름, 연락처 *
  - 구분: 직영 / 하도급 *
  - 하도급 선택 시: 업체명 입력 필드 추가
  - 직종 *
  - worker_registry 자동 연동
```

---

## 화면 6: 건설 현장 작업자 점검 (worker-check-construction.html)

**경로**: `tadmin/full-version/html/horizontal-menu-template/worker-check-construction.html`  
**접근**: 작업자 앱 / 모바일 웹  
**특징**: 로그인 없이 전화번호 인증으로 접근

### 레이아웃 (worker-check.html 기반 확장)
```
[현장명] 헤더

오늘 점검 목록:
  공정별 그룹화:
    공정명 (고위험 뱃지)
    └─ 작업 전 점검 항목 목록
         [정상] [이상] 버튼
         이상 선택 시 → 사진 첨부 영역 표시

[점검 완료] 버튼 → 이상 있으면 팝업 "안전관리자에게 즉시 전달됩니다"
```

---

## 메뉴 연결

**menu-tadmin.js 건설관리 메뉴 확인 및 추가:**
```javascript
// 건설관리 하위 메뉴
건설현장     → construction-site-list.html
공정관리     → construction-process.html
점검항목관리 → construction-inspection-anchor.html
점검이력     → construction-inspection-list.html
작업자관리   → construction-worker-list.html
```

---

## 구현 순서

```
1단계: construction-site-list.html (현장 등록 + 목록)
2단계: construction-inspection-anchor.html (점검항목 설정 — inspection-anchor.html 재활용)
3단계: construction-inspection-list.html (점검 이력 조회)
4단계: construction-process.html (공정 관리)
5단계: construction-worker-list.html (작업자)
6단계: worker-check-construction.html (작업자 모바일 점검)
```

---

## 공통 컴포넌트 재활용

| 기존 컴포넌트 | 건설 재활용 방식 |
|---|---|
| `inspection-anchor.html` | 사이트 선택 → `site_id` 기반으로 변환 |
| `worker-list.html` | 직영/하도급 탭 추가 |
| `worker-check.html` | 공정 그룹화 추가 |
| 담당자 슬라이드 패널 | 동일 사용 |
| 체크항목 슬라이드 패널 | 동일 사용 |

---

## 중요 비고

1. **건설현장은 factory가 아님**: `factory_id` 없이 `site_id` 기반으로 동작
2. **inspection_sets 연결**: `construction_sites.id` 를 `factory_id` 대신 별도 컬럼으로 연결 필요 (또는 factory_id에 site_id 저장하는 방식 확인)
3. **공사 완료 현장**: `status_code=COMPLETED` 현장은 읽기전용으로 표시
4. **하도급 권한**: 하도급 업체 작업자는 자기 현장 데이터만 접근
