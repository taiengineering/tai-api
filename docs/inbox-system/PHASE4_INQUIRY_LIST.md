# Phase 4 — 어드민 inquiry-list 확장 (Cursor 작업지시서)

> 작성일: 2026-05-04
> 선행: Phase 1·2·3 완료. 인박스 자동 발송 파이프라인 정상 작동 확인 완료.
> 검증: `INSERT inquiries → DB Trigger → /internal/inbox/notify → Slack #inbox-all` `sent:true`

---

## 1. 작업 목표

`inquiry-list.html`을 **인박스 통합 관리 화면**으로 확장한다.
지금까지 이 페이지는 도입 문의(`INQUIRY`)만 다뤘지만, 이제 다음 두 축을 추가로 처리해야 한다.

- **인입경로(source)**: `direct` (어드민 직접 입력) / `marketing` (taieng.co.kr) / `safe` (safe.taieng.co.kr)
- **유형(inquiry_type)**: `INQUIRY` (도입 문의) / `FEEDBACK` (TAI에 바란다)

설계 철학(중요): 신규 테이블·신규 페이지를 만들지 않는다. **inquiries 테이블 1개, inquiry-list 페이지 1개**로 다 처리한다. `fix-chat-list`(수선 챗봇)는 별개로 유지.

---

## 2. 작업 대상 레포·파일

### 레포
- `taiengineering/tai-admin` (브랜치: `main`만 사용. dev 없음)

### 파일 위치
정확한 경로는 Cursor 로컬에서 다음 명령으로 확인할 것.
```bash
find . -name "inquiry-list.html" -not -path "*/node_modules/*" -not -path "*/dist*" -not -path "*/.npm-cache/*"
```

**예상 결과** (둘 다 존재할 가능성):
- `admin/full-version/html/horizontal-menu-template/inquiry-list.html` — 슈퍼어드민 (admin.taieng.co.kr, role=001) ← **이게 우선**
- `tadmin/full-version/html/horizontal-menu-template/inquiry-list.html` — SaaS 어드민 (safe.taieng.co.kr)

`tai-api/services/inbox_notify_svc.py`의 슬랙 "어드민에서 보기" 버튼은 admin.taieng.co.kr로 링크되므로, **admin/ 쪽이 1순위**.
tadmin/ 쪽도 같은 페이지 구조면 동일하게 적용. 다르면 admin/만 우선 작업하고 별도 보고.

### 관련 백엔드 (참고만 — 손대지 말 것)
- `tai-api/services/inbox_notify_svc.py` — `SOURCE_LABEL`, `CATEGORY_LABEL` 라벨 정의 (이 파일을 라벨 단일 출처로 본다)
- `tai-api/routers/internal_inbox.py` — `/internal/inbox/notify` 엔드포인트
- `tai-api/db/migrations/20260504_inbox_phase1_inquiries.sql` — 테이블 정의

---

## 3. 데이터 모델 (현재 운영 중인 inquiries 테이블)

| 컬럼 | 타입 | NULL | 기본값 | 비고 |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| no | text | YES | - | (legacy) |
| **category** | text | YES | - | 분류 (아래 §4 참고) |
| title | text | YES | - | 제목 (선택) |
| **content** | text | **NO** | - | 본문 (필수) |
| answer | text | YES | - | 답변 |
| name | text | YES | - | 보낸이 |
| company | text | YES | - | 회사명 |
| phone | text | YES | - | 전화번호 |
| email | text | YES | - | 이메일 |
| is_member | bool | YES | false | 회원 여부 |
| user_id | uuid | YES | - | FK → users (선택) |
| company_id | uuid | YES | - | FK → companies (선택) |
| status | text | YES | 'RECEIVED' | RECEIVED / IN_PROGRESS / RESOLVED / CLOSED |
| priority | text | YES | 'NORMAL' | LOW / NORMAL / HIGH / URGENT |
| assigned | text | YES | - | 담당자 |
| **source** | text | YES | 'direct' | direct / marketing / safe |
| **inquiry_type** | text | YES | 'INQUIRY' | INQUIRY / FEEDBACK |
| page_url | text | YES | - | 폼 제출 페이지 URL |
| ip_hash | text | YES | - | 해시된 IP |
| replied_at | timestamptz | YES | - | 답변 시각 |
| created_at | timestamptz | NO | now() | |
| updated_at | timestamptz | NO | now() | |

RLS는 활성화되어 있고, anon은 INSERT만 가능, 조회·수정은 service_role/authenticated.
어드민 페이지는 기존 인증 체계(supabase auth + role 체크)를 그대로 사용.

---

## 4. 라벨 단일 출처 (services/inbox_notify_svc.py와 동일하게)

⚠️ **추가/수정하지 말 것.** 백엔드 라벨이 정답. UI에서 다른 문구를 쓰면 슬랙·어드민 간 표기 불일치 발생.

```javascript
const SOURCE_LABEL = {
  direct:    "어드민 직접 입력",
  marketing: "마케팅 사이트",
  safe:      "SaaS (safe.taieng.co.kr)",
};

const TYPE_LABEL = {
  INQUIRY:  "도입 문의",
  FEEDBACK: "TAI에 바란다",
};

const CATEGORY_LABEL = {
  // INQUIRY 카테고리
  consult:  "법적진단 컨설팅",
  safety:   "안전관리자 선임대행",
  electric: "전기설비 점검",
  risk:     "위험성평가",
  csia:     "중대재해처벌법",
  saas:     "SaaS 서비스",
  repair:   "수선중개",
  edu:      "안전보건교육",
  partner:  "파트너/협력 제안",
  other:    "기타",
  // FEEDBACK 카테고리
  fb_feature: "기능 제안",
  fb_bug:     "버그/오류",
  fb_ux:      "사용성 불편",
  fb_idea:    "아이디어",
  fb_praise:  "응원·칭찬",
};

const STATUS_LABEL = {
  RECEIVED:    "접수",
  IN_PROGRESS: "처리중",
  RESOLVED:    "해결됨",
  CLOSED:      "종료",
};
```

라벨이 페이지 여러 곳에서 쓰이므로 **상단 `<script>` 한 곳에 상수로 모아두고 재사용**할 것. 인라인 하드코딩 금지.

---

## 5. 변경 사항 (Done의 정의)

### 5-1. 상단 필터 영역 — 신규 추가
기존 status·검색어 필터 옆에 다음 두 셀렉트 추가:

1. **인입경로** (`source`): 전체 / 어드민 직접 입력 / 마케팅 사이트 / SaaS
2. **유형** (`inquiry_type`): 전체 / 도입 문의 / TAI에 바란다

기존 필터(status, 검색)와 AND 조건으로 결합. URL query string에 반영(`?source=marketing&inquiry_type=FEEDBACK`)해서 새로고침해도 유지될 것.

기본값은 모두 "전체". 즉 페이지 첫 진입 시 동작이 기존과 동일해야 한다(회귀 방지).

### 5-2. 리스트 테이블 — 컬럼 정비

⚠️ **TAI 리스트 페이지 필수 규칙** (절대 어기지 말 것):
- 1번째 컬럼 = 전체선택 체크박스
- 2번째 컬럼 = 순번(No., 페이지네이션 기준 1부터 증가)

그 뒤 컬럼 순서 (좌→우):

| # | 컬럼 | 출처 | 비고 |
|---|---|---|---|
| 1 | ☑ | - | 전체선택 |
| 2 | No. | - | 순번 |
| 3 | 인입경로 | source | 짧은 배지 ("마케팅", "SaaS", "어드민") — 컬럼 좁게 |
| 4 | 유형 | inquiry_type | 배지 ("도입 문의" 회색 / "TAI에 바란다" 청록) |
| 5 | 분류 | category | CATEGORY_LABEL[category] |
| 6 | 제목/본문 요약 | title or content[:40] | title 있으면 우선, 없으면 content 앞 40자 + "…" |
| 7 | 보낸이 | name | 익명이면 "익명" |
| 8 | 상태 | status | 기존 배지 색상 유지 |
| 9 | 접수일 | created_at | YYYY-MM-DD HH:mm |
| 10 | 액션 | - | "보기" 버튼 (사이드패널 오픈) |

**컬럼 좁히기 원칙**(토스 UI 참조 — "지금 보지 않아도 되는 것은 보여주지 않는다"): 인입경로/유형/상태는 배지 형태로 짧게. 본문 요약 컬럼이 가장 넓도록.

### 5-3. 사이드패널(또는 모달) — 유형별 분기

행의 "보기" 클릭 시 우측 사이드패널이 열린다. **유형(inquiry_type)에 따라 하단 액션 영역이 달라진다.**

#### 공통 영역 (상단)
- 헤더: "💬 TAI에 바란다" 또는 "📨 도입 문의" + 분류 배지
- 메타: 인입경로 · 분류 · 접수일 · 페이지 URL(있으면 링크)
- 보낸이: 이름 / 회사 / 이메일 / 전화 (없는 항목은 "-")
- 본문: content 전체 (스크롤 가능)
- 상태/우선순위/담당자: 인라인 수정 가능 (저장 버튼)

#### `inquiry_type === "INQUIRY"` 일 때 (도입 문의)
하단에 **답장 영역**:
- `answer` 텍스트에어리어
- "답장 저장" 버튼 → `update inquiries set answer=$1, replied_at=now(), status='RESOLVED' where id=$2`
- 저장 후 사이드패널 헤더에 "답변 완료" 표시

#### `inquiry_type === "FEEDBACK"` 일 때 (TAI에 바란다)
하단에 **처리 메모 영역** (답장 X — 사용자에게 회신하지 않는다):
- `answer` 컬럼을 "내부 처리 메모"로 재활용 (별도 컬럼 추가 X)
- 라벨: "처리 메모 (내부용)"
- "메모 저장" 버튼 → `update inquiries set answer=$1, status=$2 where id=$3` (replied_at 건드리지 않음)
- 상태 옵션 강조: RECEIVED → IN_PROGRESS → RESOLVED → CLOSED

이 분기 로직 한 줄 요약:
```javascript
const isFeedback = row.inquiry_type === "FEEDBACK";
// 답장 / 처리 메모 라벨, 저장 시 replied_at 처리만 다름
```

### 5-4. 신규 등록 (어드민 직접 입력) 모달
기존에 신규 등록 기능이 이미 있으면 다음만 추가:
- `source` 강제 = `'direct'`
- `inquiry_type` 셀렉트 추가 (기본 INQUIRY)
- inquiry_type=FEEDBACK이면 카테고리 셀렉트가 fb_* 5종으로 바뀜
- inquiry_type=INQUIRY면 기존 10종

기존 등록 기능이 없으면 이번 Phase에서는 만들지 않는다(범위 밖). source=direct 케이스는 Phase 5(폼 작업) 이후에 다시 본다.

### 5-5. 빈 상태 / 에러 처리
- 결과 0건: "조건에 맞는 인박스가 없습니다." (필터 초기화 버튼)
- 로드 실패: 토스트 + 콘솔 에러
- 사이드패널 저장 실패: 토스트 + 원래 값 복원

---

## 6. TAI UI 원칙 (필수 준수)

1. **"지금 보지 않아도 되는 것은 보여주지 않는다"** (토스 참조)
   - 필터는 "전체" 기본값. 처음 진입 시 노출 정보 최소화.
   - 사이드패널은 행 클릭 시에만 열림. 인라인 expand 금지.
2. **카테고리 동적 셀렉트**: 신규 등록 모달에서 inquiry_type 변경 시 카테고리 옵션이 즉시 갱신.
3. **배지 색상 일관성**: 기존 페이지 배지 색상 토큰 그대로 사용. 신규 색 추가 금지.
4. **모바일 대응**: 1080px 이하에서 좌측 리스트 + 사이드패널이 한 화면에 안 들어가면, 사이드패널을 모달로 전환.
5. **카카오 API 절대 금지** (이 페이지에는 안 쓸 가능성 크지만 혹시라도).

---

## 7. Supabase 호출 (참고 코드)

기존 inquiry-list가 supabase-js를 어떻게 쓰는지 그 패턴을 그대로 따를 것. 새로 만들 필요 없음. 컬럼 추가만 반영.

```javascript
// 목록 조회 (필터 적용 후)
let q = supabase.from("inquiries")
  .select("*", { count: "exact" })
  .order("created_at", { ascending: false })
  .range(from, to);

if (sourceFilter !== "all")  q = q.eq("source", sourceFilter);
if (typeFilter   !== "all")  q = q.eq("inquiry_type", typeFilter);
if (statusFilter !== "all")  q = q.eq("status", statusFilter);
if (searchTerm)              q = q.or(`title.ilike.%${searchTerm}%,content.ilike.%${searchTerm}%,name.ilike.%${searchTerm}%`);

const { data, count, error } = await q;
```

```javascript
// 답장/메모 저장
const updates = isFeedback
  ? { answer: memo, status: nextStatus }
  : { answer: reply, status: "RESOLVED", replied_at: new Date().toISOString() };

const { error } = await supabase
  .from("inquiries")
  .update(updates)
  .eq("id", row.id);
```

⚠️ **주의**: RLS가 활성화되어 있으므로 service_role 키 노출 금지. 프론트는 anon 키만 사용. 이 페이지는 로그인된 admin 사용자(role=001)가 접근하므로 authenticated 컨텍스트에서 동작해야 한다. 기존 페이지가 어떻게 인증을 거는지(jwt 헤더, 세션 등) 그 패턴을 그대로 따를 것.

---

## 8. 검증 방법 (PR 머지 전 직접 돌려볼 것)

### 8-1. 로컬에서 시각 확인
1. `admin.taieng.co.kr` (또는 cloudflare preview URL) 접속
2. 메뉴 → Inquiry List 진입
3. 첫 진입: 기존과 동일하게 보이는지 (회귀 없음)
4. 인입경로 필터 = "마케팅 사이트" 선택 → URL에 ?source=marketing 붙는지, 결과 줄어드는지
5. 유형 필터 = "TAI에 바란다" 선택 → fb_* 카테고리들만 보이는지

### 8-2. 사이드패널 분기 확인
다음 SQL을 Supabase SQL Editor에서 실행해 시드 데이터 두 개 만든다:

```sql
-- INQUIRY 테스트
INSERT INTO inquiries (source, inquiry_type, category, title, content, name, email)
VALUES ('marketing', 'INQUIRY', 'consult', 'Phase4 검증 — 도입 문의',
        '도입 문의 사이드패널 분기 확인용', '검증', 'phase4-inq@taieng.co.kr');

-- FEEDBACK 테스트
INSERT INTO inquiries (source, inquiry_type, category, title, content, name, email)
VALUES ('safe', 'FEEDBACK', 'fb_feature', 'Phase4 검증 — 의견',
        '의견 사이드패널 분기 확인용', '검증', 'phase4-fb@taieng.co.kr');
```

이 INSERT는 트리거가 발동해서 슬랙 #inbox-all로도 알림이 갈 것이다(정상).

어드민에서:
- INQUIRY 행 클릭 → 답장 영역이 보이는가?
- FEEDBACK 행 클릭 → 처리 메모 영역이 보이는가? (replied_at 손대지 않는지)

검증 끝나면 정리:
```sql
DELETE FROM inquiries WHERE title LIKE 'Phase4 검증%';
```

### 8-3. 슬랙 → 어드민 이동 확인
슬랙 #inbox-all에 도착한 메시지의 "어드민에서 보기" 버튼 클릭 → inquiry-list 페이지로 이동되는지. (메시지 ID로 직접 사이드패널을 여는 deep-link은 이번 범위 밖. 페이지가 열리기만 하면 OK.)

---

## 9. 커밋·PR 정책

- 브랜치: `main` 직접 푸시 금지면 `feat/inbox-phase4-inquiry-list` 브랜치 → PR
- main만 있는 레포라 단일 커밋 또는 squash merge
- 커밋 메시지: `feat(inbox): Phase 4 — inquiry-list 인박스 통합 (인입경로/유형 필터, FEEDBACK 분기)`
- PR 본문에 검증 §8 결과 스크린샷 1~2장 첨부

---

## 10. 손대지 말 것 (Out of Scope)

- 신규 페이지 추가
- 신규 테이블 / 신규 컬럼 추가 (이미 다 있음)
- `tai-api` 측 변경 (백엔드는 이미 완료)
- `fix-chat-list` (수선 챗봇) — 별도 시스템
- 카카오 알림톡 / 카카오 API 연결
- Phase 5 (마케팅·SaaS 폼) — 별도 작업

---

## 11. 막혔을 때

1. inquiry-list.html 위치를 못 찾으면 → §2의 find 명령
2. 기존 페이지 인증 패턴을 모르겠으면 → 같은 폴더의 다른 *-list.html 참고 (예: user-list, fix-chat-list)
3. supabase 호출이 RLS에 막히면 → 기존 페이지가 어떻게 토큰을 다는지 그대로 복붙
4. 그래도 막히면 → 코드 그대로 두고 막힌 지점만 보고. 추측해서 수정 금지.

---

## 부록 — 관련 문서

- `docs/inbox-system/HANDOFF_20260504.md` — Phase 1~3 핸드오프
- `docs/inbox-system/PHASE3_NOTIFY_ENDPOINT.md` — 알림 엔드포인트 설계
- `services/inbox_notify_svc.py` — 라벨 단일 출처
- `routers/internal_inbox.py` — 알림 엔드포인트
- `db/migrations/20260504_inbox_phase1_inquiries.sql` — 테이블 정의
- `db/migrations/20260504_inbox_phase3_notify_trigger_vault.sql` — 트리거
