# TAI Safe — TBM 설정 페이지 작업지시서
> 작성일: 2026-04-08 | 담당: Claude Code (백엔드) + Claude (프론트)
> 파일: `tadmin/.../tbm-setting.html` (신규)
> DB: `tbm_templates` (신규 생성 완료)

---

## 1. 기획 배경 및 핵심 컨셉

**문제:** 현장에서 TBM은 매일 거의 같은 내용이 반복됩니다.
- 같은 공정 → 같은 위험요소
- 같은 작업자 → 같은 참석자
- 같은 안전수칙 → 매번 다시 입력

**해결:** TBM 템플릿을 한 번 세팅해두면, 이후에는 **버튼 하나**로 오늘의 TBM을 즉시 시작

```
[TBM 설정 페이지]                    [TBM 실행 (tbm-list에서)]
  └ 템플릿 생성/관리        →→→       └ 템플릿 선택 → 날짜만 확인 → 바로 시작
       ↓                                   ↓
  - 제목/위치/작업 내용               자동 불러오기:
  - 위험요소 목록                      - 위험요소
  - 안전수칙 목록                      - 안전수칙
  - 기본 참석자                        - 참석자
```

**사용 흐름:**
```
안전관리자: 설정 → TBM 템플릿 만들기 (최초 1회)
  ↓
다음날부터: TBM → [+ TBM 실행] → 템플릿 선택 → 날짜 확인 → 생성
  ↓
현장: QR 스캔 → 서명 완료
```

---

## 2. DB 스키마 (신규 — 이미 생성 완료)

### tbm_templates 테이블
```sql
id                uuid PK
company_id        uuid FK → companies
factory_id        uuid FK → factories
template_name     text NOT NULL         -- 템플릿명
work_location     text                  -- 작업 위치
work_description  text                  -- 작업 내용
risk_items        jsonb DEFAULT '[]'    -- 위험요소 배열
safety_items      jsonb DEFAULT '[]'    -- 안전수칙 배열
default_attendees jsonb DEFAULT '[]'    -- 기본 참석자 배열
use_count         integer DEFAULT 0     -- 사용 횟수 (인기순 정렬)
last_used_at      timestamptz           -- 마지막 사용일
is_active         boolean DEFAULT true
created_at        timestamptz
updated_at        timestamptz
```

### jsonb 배열 구조
```json
// risk_items
[
  {"id": "uuid", "content": "낙하물에 의한 충돌 위험", "category": "충돌"}
]

// safety_items  
[
  {"id": "uuid", "content": "안전모 착용 의무화"}
]

// default_attendees
[
  {"name": "홍길동", "job_type": "용접", "phone": "010-1234-5678"}
]
```

### 위험요소 카테고리 (system_codes 또는 고정값)
- 전도, 협착, 충돌, 추락, 낙하, 폭발, 화재, 질식, 감전, 기타

---

## 3. 백엔드 API 작업 (Claude Code 담당)

### 신규 파일: `routers/tbm_templates.py`

#### 엔드포인트 목록

| Method | Path | 설명 |
|---|---|---|
| GET | `/tbm-templates` | 템플릿 목록 |
| POST | `/tbm-templates` | 템플릿 생성 |
| GET | `/tbm-templates/{id}` | 템플릿 상세 |
| PATCH | `/tbm-templates/{id}` | 템플릿 수정 |
| DELETE | `/tbm-templates/{id}` | 템플릿 삭제 (soft delete) |
| POST | `/tbm-templates/{id}/use` | 템플릿으로 TBM 생성 (use_count +1) |

#### GET /tbm-templates
```
Query params:
  factory_id: uuid (필수 아님, 없으면 company 전체)
  company_id: uuid
  q: 검색어 (template_name ILIKE)
  sort: popular(use_count DESC) | recent(updated_at DESC) | name(template_name ASC)
  page: int = 1
  size: int = 20

Response:
{
  status: "success",
  data: {
    items: [
      {
        id, template_name, factory_id, factory_name,
        work_location, work_description,
        risk_count: len(risk_items),
        safety_count: len(safety_items),
        attendee_count: len(default_attendees),
        use_count, last_used_at, created_at
      }
    ],
    total, page, page_size
  }
}
```

#### POST /tbm-templates
```json
{
  "factory_id": "uuid",
  "company_id": "uuid",
  "template_name": "1공장 프레스 작업 TBM",
  "work_location": "1공장 A구역",
  "work_description": "프레스 금형 교체 및 성형 작업",
  "risk_items": [
    {"id": "uuid", "content": "협착 위험 — 금형 교체 시", "category": "협착"}
  ],
  "safety_items": [
    {"id": "uuid", "content": "반드시 비상정지 버튼 확인 후 작업"}
  ],
  "default_attendees": [
    {"name": "홍길동", "job_type": "용접", "phone": "010-1234-5678"}
  ]
}
```

#### POST /tbm-templates/{id}/use
- `tbm_meetings`에 새 레코드 생성 (템플릿 내용 복사)
- `tbm_templates.use_count += 1`
- `tbm_templates.last_used_at = now()`

```json
// 요청 body
{
  "work_date": "2026-04-08",           // 오늘 날짜 (기본값)
  "conductor_name": "김안전",           // 진행자명
  "override_location": null,           // 위치 덮어쓰기 (선택)
  "override_description": null         // 내용 덮어쓰기 (선택)
}

// Response
{
  status: "success",
  data: {
    meeting_id: "uuid",               // 생성된 tbm_meetings.id
    template_name: "...",
    work_date: "2026-04-08"
  }
}
```

#### Pydantic 모델
```python
from pydantic import BaseModel
from typing import Optional, List
import uuid

class RiskItem(BaseModel):
    id: Optional[str] = None          # 없으면 서버에서 str(uuid4()) 생성
    content: str
    category: str = "기타"             # 전도|협착|충돌|추락|낙하|폭발|화재|질식|감전|기타

class SafetyItem(BaseModel):
    id: Optional[str] = None
    content: str

class DefaultAttendee(BaseModel):
    name: str
    job_type: Optional[str] = None
    phone: Optional[str] = None

class TbmTemplateCreate(BaseModel):
    factory_id: Optional[str] = None
    company_id: Optional[str] = None
    template_name: str
    work_location: Optional[str] = None
    work_description: Optional[str] = None
    risk_items: List[RiskItem] = []
    safety_items: List[SafetyItem] = []
    default_attendees: List[DefaultAttendee] = []

class TbmTemplateUpdate(BaseModel):
    template_name: Optional[str] = None
    work_location: Optional[str] = None
    work_description: Optional[str] = None
    risk_items: Optional[List[RiskItem]] = None
    safety_items: Optional[List[SafetyItem]] = None
    default_attendees: Optional[List[DefaultAttendee]] = None

class TbmUseBody(BaseModel):
    work_date: Optional[str] = None   # YYYY-MM-DD, 없으면 today
    conductor_name: Optional[str] = None
    override_location: Optional[str] = None
    override_description: Optional[str] = None
```

#### main.py 등록
```python
from routers.tbm_templates import router as tbm_templates_router
app.include_router(tbm_templates_router)
```

---

## 4. 프론트엔드 화면 설계 (tbm-setting.html)

### 탭 구조
```
[탭1: 템플릿 관리] [탭2: 위험요소 라이브러리] [탭3: 안전수칙 라이브러리]
```

### 탭1: 템플릿 관리 (메인)
```
[사업장 선택] [+ 새 템플릿]
──────────────────────────────────────────
[인기순 ▼]  [검색창]
──────────────────────────────────────────
카드 그리드 (2~3열)
┌──────────────────┐  ┌──────────────────┐
│ 🏭 1공장 프레스 TBM │  │ 🔧 도장 작업 TBM   │
│ A구역 | 35회 사용  │  │ B구역 | 12회 사용  │
│ 위험요소 4개       │  │ 위험요소 2개       │
│ 안전수칙 6개       │  │ 안전수칙 3개       │
│ 참석자 8명         │  │ 참석자 5명         │
│ 최근: 오늘         │  │ 최근: 3일 전       │
│ [▶ TBM 실행] [수정] [삭제] │
└──────────────────┘  └──────────────────┘
```

### 템플릿 생성/수정 모달
```
┌─────────────────────────────────────────┐
│ 템플릿 만들기                            │
├─────────────────────────────────────────┤
│ 템플릿명 *: [________________]           │
│ 작업 위치: [________________]           │
│ 작업 내용: [________________]  (textarea)│
│                                          │
│ 위험요소 ─────────────────              │
│ [카테고리▼] [내용 입력___] [+ 추가]      │
│  ● 협착 — 금형 교체 시 협착 위험  [×]   │
│  ● 추락 — 작업대 이탈 시 추락    [×]   │
│  [라이브러리에서 선택]                   │
│                                          │
│ 안전수칙 ─────────────────              │
│ [내용 입력_______________] [+ 추가]      │
│  ✓ 안전모 착용 의무화          [×]      │
│  ✓ 작업 전 비상정지 확인       [×]      │
│  [라이브러리에서 선택]                   │
│                                          │
│ 기본 참석자 ───────────────             │
│ [이름] [직종] [연락처] [+ 추가]          │
│  홍길동 | 용접 | 010-xxxx     [×]       │
│                                          │
│           [취소] [저장]                  │
└─────────────────────────────────────────┘
```

### TBM 실행 모달 (템플릿 → 오늘 TBM 생성)
```
┌─────────────────────────────────────────┐
│ TBM 실행                                │
├─────────────────────────────────────────┤
│ 템플릿: 1공장 프레스 작업 TBM           │
│ 작업일 *: [2026-04-08]                  │
│ 진행자: [김안전___]                      │
│                                          │
│ ── 확인 ──────────────────              │
│ 위험요소 4개 | 안전수칙 6개 | 참석자 8명 │
│ (수정은 TBM 실행 후 상세에서 가능)       │
│                                          │
│           [취소] [▶ TBM 생성]           │
└─────────────────────────────────────────┘
```

### 탭2: 위험요소 라이브러리
```
회사 공통으로 자주 쓰는 위험요소를 미리 등록해두는 곳
템플릿 생성 시 [라이브러리에서 선택]으로 바로 추가 가능

카테고리 탭: [전체] [전도] [협착] [충돌] [추락] [낙하] [기타]

[+ 위험요소 추가]
● 협착 | 프레스 금형 교체 시 협착 위험     [삭제]
● 추락 | 고소작업 시 추락 위험             [삭제]
● 충돌 | 지게차 이동 시 보행자 충돌        [삭제]
```

### 탭3: 안전수칙 라이브러리
```
자주 쓰는 안전수칙 저장 → 템플릿에서 원클릭 추가

[+ 안전수칙 추가]
✓ 작업 전 반드시 안전모·안전화 착용 확인  [삭제]
✓ 비상정지 버튼 위치 및 작동 확인         [삭제]
✓ 작업반경 내 안전선 설치 후 작업 시작    [삭제]
```

---

## 5. 라이브러리 데이터 저장 방식

**별도 DB 테이블 없이** `tbm_templates` 내 특수 레코드로 처리:
- `template_name = '__LIBRARY__'` 레코드를 회사별로 1개 유지
- `risk_items` / `safety_items`가 라이브러리 항목
- 프론트에서 이 레코드를 조회·수정하여 라이브러리 관리

```
// 라이브러리 전용 레코드 조회
GET /tbm-templates?library=true&company_id=xxx

// 라이브러리 업데이트 = 일반 PATCH와 동일
PATCH /tbm-templates/{library_id}
```

---

## 6. API 호출 패턴 (프론트 참고)

```javascript
const API = 'https://api.taieng.co.kr';
const token = localStorage.getItem('access_token');
const hdr = () => ({ 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' });

// 템플릿 목록 (인기순)
const res = await fetch(`${API}/tbm-templates?factory_id=${fid}&sort=popular`, { headers: hdr() });

// 템플릿 생성
await fetch(`${API}/tbm-templates`, {
  method: 'POST', headers: hdr(),
  body: JSON.stringify({
    factory_id: fid,
    company_id: cid,
    template_name: '1공장 프레스 작업 TBM',
    work_location: '1공장 A구역',
    risk_items: [
      { id: crypto.randomUUID(), content: '협착 위험', category: '협착' }
    ],
    safety_items: [
      { id: crypto.randomUUID(), content: '안전모 착용' }
    ],
    default_attendees: [
      { name: '홍길동', job_type: '용접', phone: '010-1234-5678' }
    ]
  })
});

// 템플릿으로 TBM 생성
await fetch(`${API}/tbm-templates/${templateId}/use`, {
  method: 'POST', headers: hdr(),
  body: JSON.stringify({
    work_date: '2026-04-08',
    conductor_name: '김안전'
  })
});
```

---

## 7. 작업 순서

### 백엔드 (Claude Code)
1. [ ] `routers/tbm_templates.py` 생성 (전체 엔드포인트)
2. [ ] `main.py`에 `tbm_templates_router` 등록
3. [ ] `/tbm-templates/{id}/use` 에서 `tbm_meetings` 레코드 생성 로직 구현
4. [ ] `/tbm-templates?library=true` 처리 구현

### 프론트엔드 (Claude)
1. [ ] `tbm-setting.html` 신규 구현
   - 탭3: 템플릿 목록 (카드 그리드, 인기순/최근순)
   - 탭1,2: 위험요소/안전수칙 라이브러리
   - 템플릿 생성/수정 모달
   - TBM 실행 모달
   - 위험요소·안전수칙 항목 동적 추가/삭제

---

## 8. 완료 기준

- [ ] 템플릿 생성 → 저장 → 목록에 표시
- [ ] 사용 횟수 인기순 정렬 동작
- [ ] [TBM 실행] → 날짜 선택 → tbm_meetings 레코드 생성됨
- [ ] 위험요소/안전수칙 라이브러리 등록 → 템플릿 생성 시 선택 가능
- [ ] 기본 참석자 → TBM 실행 시 tbm_attendees 자동 생성
- [ ] 모바일(375px) 기준 정상 표시

---

## 9. 연관 파일

| 파일 | 역할 |
|---|---|
| `routers/tbm_templates.py` | **신규** — TBM 템플릿 API |
| `tbm_templates` DB 테이블 | **신규 생성 완료** |
| `tbm-setting.html` | **신규 구현 대상** |
| `tbm-list.html` | 기존 — TBM 목록 (연동: [TBM 실행] 버튼 추가 필요) |
| `tbm_meetings` DB 테이블 | 기존 — TBM 실행 기록 저장 |
