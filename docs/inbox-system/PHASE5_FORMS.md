# Phase 5 — 마케팅·SaaS 의견 폼 (Cursor 작업지시서)

> 작성일: 2026-05-04
> 선행: Phase 1·2·3 완료 + Phase 4 작업지시서 작성됨.
> 검증된 사실: anon 사용자가 inquiries 테이블에 INSERT만 하면 → DB 트리거 → 슬랙 #inbox-all 자동 알림. 백엔드 추가 코드 0줄.

---

## 1. 작업 목표

**마케팅 사이트(`taieng.co.kr`)와 SaaS(`safe.taieng.co.kr`) 양쪽에 "의견·문의" 진입점을 추가한다.**

세 가지 진입점:

| # | 위치 | source | inquiry_type | UI 형태 |
|---|---|---|---|---|
| A | 마케팅 사이트 푸터 "TAI에 바란다" | `marketing` | `FEEDBACK` | 모달 |
| B | 마케팅 사이트 도입 문의 페이지 | `marketing` | `INQUIRY` | 단독 페이지 또는 강화된 contact.html |
| C | SaaS 헤더 "의견 보내기" | `safe` | `FEEDBACK` | 모달 |

**중요한 설계 결정**: 폼 제출은 **anon Supabase 클라이언트로 직접 INSERT**한다. 백엔드 신규 엔드포인트는 만들지 않는다. Phase 1에서 RLS 정책으로 검증이 끝나 있고, Phase 3 트리거가 슬랙 발송을 처리한다. Cursor는 **프론트만 수정**한다.

---

## 2. 작업 대상 레포·파일

### 레포 ① 마케팅 사이트
- 레포: `taiengineering/taieng`
- 브랜치: `main`
- 위치: `nexas/` 정적 HTML

#### 진입점 A · TAI에 바란다 (모달)
- **모든 페이지 공통 푸터**에 진입 버튼/링크 추가
- 푸터 partial이 별도 파일로 분리되어 있으면 그 파일만, 없으면 각 페이지 푸터에 동일 패턴 추가
- 모달 자체는 공용 컴포넌트로 만들어 한 번만 작성하고 재사용

#### 진입점 B · 도입 문의
- **기존 `nexas/contact.html` (9KB) 분석**해서 재사용 여부 판단:
  - 기존 폼이 inquiries 테이블에 안 붙어 있다면 → 이번에 붙임 (`source='marketing'`, `inquiry_type='INQUIRY'`, `category` 셀렉트 추가)
  - 기존 폼이 다른 시스템(이메일 등)에 붙어 있고 변경이 위험하다면 → 신규 `nexas/inquiry-form.html` 생성하고 contact.html에서 안내만 변경
  - 둘 중 어느 쪽이든 **선택 근거를 PR 본문에 한 줄로 명시**

#### 공용 JS
- `nexas/scripts/inquiry-form.js` (신규) — 모달 + INSERT 로직 한 곳에 모은다
- 다른 페이지(`fix-request.html`, `free-diagnosis.html`)가 이미 supabase-js를 어떻게 로드·인증하는지 그 패턴을 그대로 따른다 (anon 키, supabase URL 동일)

### 레포 ② SaaS 어드민
- 레포: `taiengineering/tai-admin`
- 브랜치: `main`
- 위치: `tadmin/full-version/...` (safe.taieng.co.kr 도메인용 — `_redirects`에 매핑되어 있음)

#### 진입점 C · 의견 보내기 (모달)
- 헤더(또는 사이드바 하단)에 "의견 보내기" 버튼 추가
- 모달 구조는 ①번 마케팅 모달과 동일한 UX, 같은 카테고리 라벨
- supabase-js가 이미 인증된 컨텍스트(authenticated 사용자 세션)에서 동작 — 단, **INSERT는 anon이 가능한 형태로 남기고, source='safe'만 정확하게 박는다**. 인증된 user의 `user_id`도 함께 INSERT하면 어드민에서 누가 보냈는지 보임

---

## 3. 데이터 모델 + RLS 제약 (절대 어기지 말 것)

### inquiries 테이블 (Phase 4 작업지시서와 동일)
주요 컬럼만:
- `id` uuid (자동)
- `source` text — **`'marketing'` 또는 `'safe'` 만 anon INSERT 허용**
- `inquiry_type` text — **`'INQUIRY'` 또는 `'FEEDBACK'` 만 허용**
- `category` text
- `title` text (선택)
- `content` text **NOT NULL, 10~2000자** ← RLS가 직접 검증
- `name`, `email`, `phone`, `company` (모두 선택)
- `page_url` text (선택, `window.location.href` 자동 캡처 권장)
- `is_member` bool (SaaS에서는 true, 마케팅은 false)
- `user_id` uuid (SaaS에서 인증된 사용자가 있으면 같이 보냄)
- `status`, `priority`, `created_at` 등은 기본값으로 자동

### RLS 정책 (현재 운영 중, 건드리지 말 것)
```sql
-- 정책: anon insert external inquiries
-- 조건:
--   source ∈ {'marketing', 'safe'}
--   inquiry_type ∈ {'INQUIRY', 'FEEDBACK'}
--   content IS NOT NULL
--   length(content) BETWEEN 10 AND 2000
```

⚠️ 이 조건을 어기는 INSERT는 RLS가 막는다. 프론트에서 같은 검증을 클라이언트에서 한 번 더 하고(즉시 사용자 피드백), 서버에서 RLS가 한 번 더 막는 이중 구조.

---

## 4. 라벨 단일 출처 (Phase 4 작업지시서와 100% 동일)

⚠️ 어드민(Phase 4) / 슬랙(`services/inbox_notify_svc.py`)과 라벨이 일치해야 한다. **임의로 추가/수정 금지**.

```javascript
// nexas/scripts/inquiry-form.js (또는 tadmin 측 동일한 곳)
const TYPE_LABEL = {
  INQUIRY:  "도입 문의",
  FEEDBACK: "TAI에 바란다",
};

const INQUIRY_CATEGORIES = [
  { key: "consult",  label: "법적진단 컨설팅" },
  { key: "safety",   label: "안전관리자 선임대행" },
  { key: "electric", label: "전기설비 점검" },
  { key: "risk",     label: "위험성평가" },
  { key: "csia",     label: "중대재해처벌법" },
  { key: "saas",     label: "SaaS 서비스" },
  { key: "repair",   label: "수선중개" },
  { key: "edu",      label: "안전보건교육" },
  { key: "partner",  label: "파트너/협력 제안" },
  { key: "other",    label: "기타" },
];

const FEEDBACK_CATEGORIES = [
  { key: "fb_feature", label: "기능 제안" },
  { key: "fb_bug",     label: "버그/오류" },
  { key: "fb_ux",      label: "사용성 불편" },
  { key: "fb_idea",    label: "아이디어" },
  { key: "fb_praise",  label: "응원·칭찬" },
];
```

---

## 5. 변경 사항 상세

### 5-1. 마케팅 사이트 푸터 — TAI에 바란다 (모달)

**진입 트리거**: 푸터 우측에 작은 링크/버튼
- 텍스트: "💬 TAI에 바란다" 또는 "의견 보내기"
- 클릭 → 모달 오픈

**모달 구조** (FEEDBACK 전용):
- 제목: "TAI에 바란다"
- 안내문 1줄: "TAI를 더 좋게 만들 의견을 보내주세요. 서비스에 반영합니다."
- **카테고리 셀렉트**: FEEDBACK_CATEGORIES 5종
- **내용 textarea**: placeholder "어떤 점이 불편하셨나요? 또는 어떤 기능이 있으면 좋겠나요?", maxlength=2000, required, **최소 10자 검증**
- **이름** (선택): text input
- **이메일** (선택): email input. 입력하면 답변 받을 수 있다는 안내
- **전송 버튼**: 클릭 시 검증 → INSERT → 성공 토스트 → 모달 닫기

**제출 데이터**:
```javascript
{
  source: "marketing",
  inquiry_type: "FEEDBACK",
  category: <selected fb_* key>,
  content: <textarea>,
  name: <input or null>,
  email: <input or null>,
  page_url: window.location.href,  // 어떤 페이지에서 보냈는지
  is_member: false,
}
```

**성공 토스트**: "의견 감사합니다. 신중하게 검토하겠습니다."  
**실패 토스트**: "전송에 실패했습니다. 잠시 후 다시 시도해주세요." (콘솔에 error 출력)

### 5-2. 마케팅 사이트 도입 문의 (강화된 페이지)

**선택 1 — contact.html 강화 (권장 시작점)**:
기존 contact.html을 열어서:
- supabase-js 연결 추가 (다른 페이지 패턴 그대로)
- 카테고리 셀렉트 추가 (INQUIRY_CATEGORIES 10종)
- 제출 시 inquiries에 INSERT (`source='marketing'`, `inquiry_type='INQUIRY'`)
- 성공 시 안내 페이지 또는 인라인 메시지

**선택 2 — 신규 inquiry-form.html**:
contact.html 변경이 위험하면 별도 페이지 생성 + contact.html에서 링크.

**제출 데이터**:
```javascript
{
  source: "marketing",
  inquiry_type: "INQUIRY",
  category: <selected key>,  // consult, safety, ...
  title: <optional>,
  content: <textarea, 10~2000자>,
  name: <required>,
  email: <required>,
  phone: <optional>,
  company: <optional>,
  page_url: window.location.href,
  is_member: false,
}
```

INQUIRY는 답변을 주는 채널이므로 **이름·이메일은 사실상 필수**로 클라이언트 검증.

### 5-3. SaaS 헤더 — 의견 보내기 (모달)

**진입 트리거**: 헤더 우상단(알림 아이콘 옆) 또는 좌측 사이드바 하단
- 아이콘: 💬 또는 lightbulb
- 텍스트: "의견 보내기"
- 클릭 → 모달 오픈

**모달 구조**: §5-1과 거의 동일하지만 차이:
- 제목: "TAI 팀에 의견 보내기"
- 사용자 정보가 이미 인증되어 있으므로 name/email 필드 생략 가능 (대신 hidden으로 전송)
- `is_member: true`, `user_id: <session user.id>`

**제출 데이터**:
```javascript
{
  source: "safe",
  inquiry_type: "FEEDBACK",
  category: <selected fb_* key>,
  content: <textarea>,
  name: session.user.user_metadata?.name ?? null,
  email: session.user.email ?? null,
  user_id: session.user.id,
  company_id: <현재 회사 ID, 있으면>,
  page_url: window.location.href,
  is_member: true,
}
```

---

## 6. 구현 패턴 (코드 스니펫)

### 6-1. supabase-js INSERT (양 쪽 공통)

```javascript
// supabase 클라이언트는 이미 페이지에 로드되어 있다고 가정
// 없으면 다른 페이지(fix-request.html 등)에서 어떻게 로드하는지 그 패턴 그대로 사용

async function submitInquiry(data) {
  // 1. 클라이언트 검증 (RLS와 동일한 조건)
  if (!data.content || data.content.length < 10 || data.content.length > 2000) {
    return { ok: false, error: "내용은 10자 이상 2000자 이하로 입력해주세요." };
  }
  if (!["marketing", "safe"].includes(data.source)) {
    return { ok: false, error: "internal: invalid source" };
  }
  if (!["INQUIRY", "FEEDBACK"].includes(data.inquiry_type)) {
    return { ok: false, error: "internal: invalid type" };
  }

  // 2. INSERT
  const { data: inserted, error } = await supabase
    .from("inquiries")
    .insert([data])
    .select("id")
    .single();

  if (error) {
    console.error("[inquiry] insert failed:", error);
    return { ok: false, error: "전송에 실패했습니다. 잠시 후 다시 시도해주세요." };
  }
  return { ok: true, id: inserted.id };
}
```

### 6-2. 모달 HTML 골격 (Tailwind/Bootstrap 등 사이트 스택에 맞춰 변환)

```html
<dialog id="feedbackModal" class="...">
  <form id="feedbackForm">
    <header><h2>TAI에 바란다</h2><button type="button" data-close>✕</button></header>
    <p class="hint">TAI를 더 좋게 만들 의견을 보내주세요. 서비스에 반영합니다.</p>

    <label>분류
      <select name="category" required>
        <!-- FEEDBACK_CATEGORIES 5종 옵션 -->
      </select>
    </label>

    <label>내용 <span class="req">*</span>
      <textarea name="content" minlength="10" maxlength="2000" rows="6" required></textarea>
      <small class="counter"><span data-len>0</span>/2000</small>
    </label>

    <label>이름 (선택)
      <input type="text" name="name" maxlength="50" />
    </label>

    <label>이메일 (선택, 답변 받기)
      <input type="email" name="email" maxlength="100" />
    </label>

    <footer>
      <button type="button" data-close>취소</button>
      <button type="submit" class="primary">보내기</button>
    </footer>
  </form>
</dialog>
```

### 6-3. SaaS 모달의 인증 사용자 자동 주입

```javascript
const { data: { session } } = await supabase.auth.getSession();
if (!session) {
  // 비로그인 상태에서 모달 진입 시 처리 — 대부분 이미 로그인된 컨텍스트
  return;
}

const data = {
  source: "safe",
  inquiry_type: "FEEDBACK",
  category: form.category.value,
  content: form.content.value,
  name: session.user.user_metadata?.name ?? null,
  email: session.user.email ?? null,
  user_id: session.user.id,
  is_member: true,
  page_url: window.location.href,
};
```

---

## 7. UI/UX 원칙 (TAI 표준)

1. **"지금 보지 않아도 되는 것은 보여주지 않는다"** (토스 참조)
   - 푸터 진입 링크는 작고 차분하게. 강조하지 않는다.
   - 모달은 카테고리·내용을 메인으로, 연락처는 부가.
2. **카카오 API 절대 금지**. 폼 제출은 supabase 직접 INSERT만.
3. **에러 표시는 인라인** (필드 아래 빨간 텍스트), 토스트는 성공/실패 결과만.
4. **로딩 상태**: 보내기 버튼 클릭 시 disabled + "보내는 중..." 텍스트.
5. **이중 제출 방지**: submit 핸들러에서 즉시 disabled 처리.
6. **모달 닫기**: ESC 키 + 배경 클릭 + ✕ 버튼 모두 동작.
7. **글자수 카운터**: textarea 옆에 0/2000 형식.
8. **개인정보 안내**: 이메일·전화 입력 영역 아래에 "민감정보는 입력하지 마세요. 답변·문의 처리 목적으로만 사용됩니다." 한 줄.

---

## 8. 검증 방법 (PR 머지 전 직접 돌려볼 것)

### 8-1. 마케팅 사이트 — 로컬 또는 Cloudflare Preview
1. `taieng.co.kr/index.html` 진입 → 푸터에 "TAI에 바란다" 링크 보이는가?
2. 클릭 → 모달 오픈, ESC/배경/✕로 닫히는가?
3. 카테고리 미선택 + 내용 5자만 → 인라인 에러 ("10자 이상")
4. 정상 입력 → 보내기 → 성공 토스트, 모달 닫힘
5. 슬랙 #inbox-all 확인 → 메시지 도착, 인입경로 = "마케팅 사이트", 분류 = 선택한 fb_* 라벨, page_url 표시
6. 어드민 inquiry-list 진입 → 방금 보낸 항목 보임 (Phase 4가 아직이면 Supabase Studio에서 직접 확인)
7. `contact.html` (또는 신규 inquiry-form.html) → 도입 문의 폼 동일 절차

### 8-2. SaaS — 로그인 후
1. `safe.taieng.co.kr` 로그인 → 헤더에 "의견 보내기" 보이는가?
2. 클릭 → 모달, name/email은 자동 채워져 있음 (또는 hidden)
3. 정상 입력 → 보내기 → 성공
4. 슬랙에 인입경로 = "SaaS (safe.taieng.co.kr)", **user_id**가 들어왔는가? (Supabase에서 SELECT로 확인)

### 8-3. 부정 케이스
다음 INSERT가 RLS에 의해 막혀야 정상:
- `source='direct'`로 anon이 INSERT 시도 → 거부
- `inquiry_type='SOMETHING_ELSE'` → 거부
- `content` 9자 이하 → 거부
- 1만자 본문 → maxlength로 막히거나 RLS로 거부

브라우저 콘솔에서 직접 fetch로 RLS 회피 시도해서 모두 거부되는지 한 번 확인.

### 8-4. 정리
검증 후 어드민/Supabase Studio에서 테스트 row 정리:
```sql
DELETE FROM inquiries 
WHERE created_at >= now() - interval '1 day'
  AND content LIKE '%Phase 5 검증%';
```

---

## 9. 커밋·PR 정책

### 마케팅 사이트
- 레포: `taieng`
- 브랜치: `feat/inbox-phase5-marketing-form` → PR
- 커밋: `feat(inbox): Phase 5 — 마케팅 사이트 의견·문의 폼 (FEEDBACK 모달 + INQUIRY 페이지)`

### SaaS
- 레포: `tai-admin`
- 브랜치: `feat/inbox-phase5-saas-form` → PR
- 커밋: `feat(inbox): Phase 5 — SaaS 헤더 의견 보내기 모달 (FEEDBACK)`

각 PR 본문에 §8 검증 결과 + 슬랙 메시지 스크린샷 1장씩.

---

## 10. 손대지 말 것 (Out of Scope)

- 백엔드 신규 엔드포인트 (필요 없음 — anon INSERT + 트리거가 처리)
- inquiries 테이블 컬럼 추가/수정 (이미 충분)
- 카카오 알림톡 / 카카오 API
- reCAPTCHA 도입 (스팸이 실제 문제 되면 그때 별도 작업)
- ip_hash 자동 채우기 (Edge Function 필요 — 별도 작업으로 분리)
- 어드민 페이지 변경 (Phase 4가 별도)
- fix-request.html / free-diagnosis.html 등 다른 폼 (별개 시스템)

---

## 11. 막혔을 때

1. **supabase-js 로드 패턴을 모르겠으면** → `nexas/fix-request.html` 또는 `nexas/free-diagnosis.html`이 어떻게 클라이언트를 만드는지 그대로 복사
2. **anon 키·URL 위치를 모르겠으면** → 같은 디렉토리의 다른 폼 페이지 검색: `grep -r "supabase.createClient" nexas/`
3. **푸터 partial이 어디 있는지 모르겠으면** → `grep -r "footer" nexas/scripts/` 또는 각 HTML 직접 확인. 분리 안 되어 있으면 "푸터 코드를 모든 .html에 동일하게 추가"가 답
4. **모달이 다른 모달과 z-index 충돌** → 사이트 기존 모달 z-index보다 +1
5. **그래도 막히면** → 코드 그대로 두고 막힌 지점만 보고. 추측 수정 금지.

---

## 12. 단계별 작업 순서 권장 (실패 위험 최소화)

1. **Phase 5-A**: 마케팅 푸터 모달 (FEEDBACK)부터. 가장 단순하고 위험 작음.
2. **5-A 검증** → 슬랙 도착 확인 → PR 머지
3. **Phase 5-C**: SaaS 헤더 모달 (FEEDBACK). 패턴이 5-A와 동일.
4. **5-C 검증** → PR 머지
5. **Phase 5-B**: 마케팅 도입 문의 (INQUIRY). contact.html 분석 필요해서 시간 더 듦.
6. **5-B 검증** → PR 머지

각 단계가 독립적이라 어느 단계에서 막혀도 다른 단계는 살아있다.

---

## 부록 — 관련 문서

- `docs/inbox-system/HANDOFF_20260504.md` — Phase 1~3 핸드오프
- `docs/inbox-system/PHASE3_NOTIFY_ENDPOINT.md` — 알림 엔드포인트 설계
- `docs/inbox-system/PHASE4_INQUIRY_LIST.md` — 어드민 페이지 (병행 작업)
- `services/inbox_notify_svc.py` — 라벨 단일 출처
- `db/migrations/20260504_inbox_phase1_inquiries.sql` — 테이블 + RLS 정책
- `db/migrations/20260504_inbox_phase3_notify_trigger_vault.sql` — 자동 발송 트리거

---

## 13. 핵심 1줄 요약

> **anon 사용자가 inquiries에 `source='marketing'|'safe'` + `content 10~2000자` + `inquiry_type='INQUIRY'|'FEEDBACK'`로 INSERT만 성공시키면, 슬랙·어드민·메모리가 모두 자동으로 따라온다.**
