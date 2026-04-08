# TAI Safe — 공정관리 페이지 작업지시서
> 작성일: 2026-04-08 | 담당: Claude Code (백엔드) + Claude (프론트)
> 대상 파일: `tadmin/full-version/html/horizontal-menu-template/process-manage.html`
> 현재 상태: 319B 빈 파일

---

## 1. 배경 및 목적

현재 `process-select.html`은 공정을 **선택/등록**하는 기능이 있으나,
`process-manage.html`은 사업장별 **등록된 공정 목록을 조회·수정·삭제**하는 관리 화면이 없음.

안전관리자가 safe.taieng.co.kr에서 다음 흐름으로 공정을 관리할 수 있어야 함:
```
사업장 선택 → 등록된 공정 목록 확인 → 수정/삭제 → 수동 공정 추가
```

---

## 2. 기존 API 현황 (factory_process_v3.py v3.2.0)

### 사용 가능한 엔드포인트

| Method | Endpoint | 설명 |
|---|---|---|
| GET | `/factory-process/{factory_id}/processes` | 등록된 공정 목록 |
| POST | `/factory-process/{factory_id}/processes` | 공정 추가 (DB/MANUAL/KCSC) |
| POST | `/factory-process/{factory_id}/processes/bulk` | 공정 일괄 추가 |
| PATCH | `/factory-process/{factory_id}/processes/{id}` | 공정 수정 |
| DELETE | `/factory-process/{factory_id}/processes/{id}` | 공정 삭제 (soft delete) |
| GET | `/factory-process/search` | DB 공정 검색 |
| GET | `/factory-process/kcsc/search?q=` | KCSC 공정 검색 |
| GET | `/factory-process/overview` | 사업장별 공정 현황 |

### factory_process 테이블 스키마

```
id                uuid PK
factory_id        uuid FK → factories
process_id        text  (DB: IP000xxx, KCSC: kcs_code, MANUAL: MANUAL-xxx)
process_lv1~4     text  (계층 구조)
process_path      text  (> 구분 전체 경로)
process_name_manual text (MANUAL/KCSC 공정명)
source            text  (DB | MANUAL | KCSC)
is_primary        bool
is_active         bool  (soft delete 플래그)
created_at        timestamptz
```

---

## 3. 신규 API 작업 (백엔드 — Claude Code 담당)

### 3-1. 기존 엔드포인트 보완 필요 없음
현재 `factory_process_v3.py`의 엔드포인트가 충분함.
**백엔드 신규 개발 불필요.**

### 3-2. main.py 라우터 등록 확인
`factory_process_v3` 라우터가 `main.py`에 등록되어 있는지 확인:

```python
# main.py에 아래 라인이 있어야 함
from routers.factory_process_v3 import router as factory_process_v3_router
app.include_router(factory_process_v3_router)
```

**없으면 추가할 것.**

---

## 4. 프론트엔드 작업 (process-manage.html)

### 4-1. 화면 구성

```
┌─────────────────────────────────────────────────┐
│ [사업장 선택 드롭다운]  [새로고침]                │
├─────────────────────────────────────────────────┤
│ 요약: 총 N개 | DB N | MANUAL N | KCSC N          │
├─────────────────────────────────────────────────┤
│ [+ 수동 공정 추가] [공정 검색/추가 →process-select]│
├─────────────────────────────────────────────────┤
│ No. | 공정 경로 | 구분 | 주공정 | 등록일 | 관리  │
│ 1   | 제련>용해>... | DB | ✓ | 2026-03-20 | [삭제]│
│ 2   | 내가입력한공정| 수동| - | 2026-04-01 | [수정][삭제]│
└─────────────────────────────────────────────────┘
```

### 4-2. 기능 상세

**① 사업장 선택**
- `GET /factories?company_id=xxx` 로 사업장 목록 로드
- localStorage `selectedFactoryId` 기억/복원

**② 공정 목록 표시**
- API: `GET /factory-process/{factory_id}/processes`
- 응답의 `source_badge` 값으로 뱃지 표시
  - `DB` → 파란 뱃지
  - `수동입력` → 회색 뱃지
  - `KCSC` → 초록 뱃지
- `is_primary: true` → ⭐ 표시

**③ 수동 공정 추가 (인라인 모달)**
```
공정명*: [입력]
대분류: [입력]  중분류: [입력]  소분류: [입력]
주공정 여부: [체크박스]
[취소] [저장]
```
API: `POST /factory-process/{factory_id}/processes`
```json
{
  "source": "MANUAL",
  "process_name_manual": "내 공정명",
  "process_lv1": "대분류",
  "process_lv2": "중분류",
  "process_lv3": "소분류",
  "is_primary": false
}
```

**④ MANUAL 공정 수정**
- MANUAL/KCSC 공정만 수정 가능 (DB 공정은 수정 버튼 숨김)
- API: `PATCH /factory-process/{factory_id}/processes/{id}`
```json
{
  "process_name_manual": "수정된 공정명",
  "process_lv1": "대분류"
}
```

**⑤ 공정 삭제**
- 모든 공정 삭제 가능
- confirm() 다이얼로그 후 API 호출
- API: `DELETE /factory-process/{factory_id}/processes/{id}`

**⑥ 공정 검색/추가 이동**
- `[공정 검색/추가]` 버튼 → `process-select.html?factory_id=xxx` 이동

---

## 5. 파일 작업 범위

### 백엔드 (Claude Code)
- [ ] `main.py`에 `factory_process_v3_router` 등록 여부 확인 및 추가
- 신규 API 없음

### 프론트엔드 (Claude)
- [ ] `tadmin/full-version/html/horizontal-menu-template/process-manage.html` 구현
  - Vuexy horizontal-menu-template 레이아웃 기반
  - menu-tadmin.js, nav-tadmin.js, footer-nav.js 포함
  - 인증 체크 (access_token 없으면 로그인 페이지로)
  - 사업장 선택 → 공정 목록 → CRUD

---

## 6. API 호출 패턴 (프론트 참고)

```javascript
const API = 'https://api.taieng.co.kr';
const token = localStorage.getItem('access_token');
const headers = {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json'
};

// 공정 목록 조회
const res = await fetch(`${API}/factory-process/${factoryId}/processes`, { headers });
const { data } = await res.json();
// data.items 배열 사용

// 수동 공정 추가
await fetch(`${API}/factory-process/${factoryId}/processes`, {
  method: 'POST', headers,
  body: JSON.stringify({
    source: 'MANUAL',
    process_name_manual: '공정명',
    process_lv1: '대분류',
    is_primary: false
  })
});

// 공정 수정 (MANUAL만)
await fetch(`${API}/factory-process/${factoryId}/processes/${recordId}`, {
  method: 'PATCH', headers,
  body: JSON.stringify({ process_name_manual: '수정명' })
});

// 공정 삭제
await fetch(`${API}/factory-process/${factoryId}/processes/${recordId}`, {
  method: 'DELETE', headers
});
```

---

## 7. 완료 기준

- [ ] 사업장 선택 후 공정 목록 정상 표시
- [ ] source 별 뱃지 구분 (DB/수동입력/KCSC)
- [ ] 수동 공정 추가 → 목록에 즉시 반영
- [ ] MANUAL 공정 수정 동작
- [ ] 공정 삭제 → 목록에서 즉시 제거
- [ ] `process-select.html` 이동 버튼 동작
- [ ] 모바일(375px) 기준 정상 표시

---

## 8. 연관 파일

| 파일 | 역할 |
|---|---|
| `routers/factory_process_v3.py` | 공정 API (기존, 수정 없음) |
| `process-select.html` | 공정 검색/선택 (기존) |
| `process-manage.html` | **신규 구현 대상** |
| `menu-tadmin.js` | 공정관리 메뉴 항목 (`process-manage.html`) |
