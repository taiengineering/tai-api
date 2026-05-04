# 인박스 시스템 핸드오프 — 2026-05-04

이 문서 한 장으로 다음 세션·Cursor·다른 AI가 바로 이어 작업할 수 있도록 정리.

---

## TL;DR

**상태**: tai-api 라우터·서비스·main 브랜치 배포까지 완료. Supabase Vault에 secret 등록도 완료. 직접 호출 시 라우터는 200으로 정상 응답하지만, 슬랙 발송 단계에서 `sent: false` 상태로 막혀 있음.

**남은 블로커**: Railway env에 `SLACK_CHANNEL_ID_INBOX` 등록 + 슬랙 채널에 봇 초대. 둘 다 대표가 직접 확인·조치 필요.

**완료 후 남은 작업**: Supabase에 트리거 SQL 적용 → INSERT 경유 검증 → Phase 4(어드민 페이지 확장) → Phase 5(폼).

---

## 시스템 개요

마케팅 사이트(`taieng.co.kr`)와 SaaS(`safe.taieng.co.kr`)의 외부 문의·의견을 어드민 한 곳에서 관리하기 위한 통합 인박스.

```
[폼 제출 또는 어드민 직접 입력]
   ↓
Supabase: INSERT inquiries (anon RLS or service_role)
   ↓
DB Trigger AFTER INSERT (Vault에서 secret 조회 → net.http_post)
   ↓
tai-api: POST /internal/inbox/notify (X-Internal-Secret 검증)
   ↓
Slack #inbox-all (C0B1HKW5Y7N) — 새 메시지 알림
```

설계 원칙:
1. inquiries 테이블 1개에 source/inquiry_type 컬럼만 추가 → 신규 테이블 X
2. 어드민 inquiry-list 페이지 1개로 통합 → fix-chat-list(수선 챗봇)는 별개 유지
3. 슬랙 알림은 신규 채널 #inbox-all로 분리 (기존 마케팅 채널과 섞이지 않게)

---

## 채널 구분

| source | 의미 | 진입점 |
|---|---|---|
| `direct` | 어드민 직접 입력 | inquiry-list 신규 등록 |
| `marketing` | taieng.co.kr | 푸터 "TAI에 바란다" + 도입 문의 폼 |
| `safe` | safe.taieng.co.kr | 헤더 "의견 보내기" 메뉴 |

| inquiry_type | 카테고리 |
|---|---|
| `INQUIRY` (도입 문의) | consult / safety / electric / risk / csia / saas / repair / edu / partner / other |
| `FEEDBACK` (TAI에 바란다) | fb_feature / fb_bug / fb_ux / fb_idea / fb_praise |

---

## 진행 현황

| Phase | 작업 | 상태 | 검증 |
|---|---|---|---|
| 1 | DB 마이그레이션 (inquiries + RLS) | ✅ 완료 | V1·V2·V3·V4 모두 통과 |
| 2-a | Vault에 internal_api_secret 등록 | ✅ 완료 | id `42ef59f1-c484-4419-9d3b-00282b6464dc` |
| 2-b | Railway env: `SLACK_CHANNEL_ID_INBOX` | ⏳ 미확인 | 대표가 Variables 탭 확인 필요 |
| 2-c | 슬랙 #inbox-all에 @slackbot 초대 | ⏳ 미확인 | 대표가 슬랙에서 `/invite` 실행 필요 |
| 3 | tai-api `/internal/inbox/notify` + 라우터 등록 | ✅ 완료 | curl 직접 호출 시 200 응답 확인 |
| 3-trigger | DB Trigger SQL 적용 | ⏳ 대기 | 2-b·c 끝난 뒤 적용 |
| 4 | 어드민 inquiry-list 확장 | ⏳ 미시작 | Cursor 작업 예정 |
| 5 | 마케팅 + SaaS 의견 폼 | ⏳ 미시작 | MCP / Cursor 작업 예정 |

---

## 인프라 정보

### Supabase (서울)
- Project ID: `vwlahtguyggrhvslabax`
- Vault secret: `internal_api_secret` (id `42ef59f1-c484-4419-9d3b-00282b6464dc`, Railway 값과 동일)
- pg_net extension: `net` 스키마에 함수 위치 (extensions 아님 — 주의)

### tai-api (Railway 싱가포르)
- Live: https://api.taieng.co.kr
- 현재 main 브랜치 APP_VERSION: **5.44.0**
- 최신 commit: `d3ca018` — pg_net 스키마 수정
- 신규 라우터: `routers/internal_inbox.py`
- 신규 서비스: `services/inbox_notify_svc.py`
- 마이그레이션: `db/migrations/20260504_inbox_phase3_notify_trigger_vault.sql`

### Railway 환경변수 정책
```
SLACK_BOT_TOKEN          ← 기존 (공용)
SLACK_CHANNEL_ID         ← 기존 (마케팅 채널, 네이버 지식인 AI 답변 승인용 — 절대 건드리지 않음)
SLACK_SIGNING_SECRET     ← 기존
INTERNAL_API_SECRET      ← 기존 (Vault와 동일 값)
SLACK_CHANNEL_ID_INBOX   ← 신규 추가 필요 = C0B1HKW5Y7N (#inbox-all)
```

### 슬랙
- 봇 이름: `@slackbot`
- 신규 채널: `#inbox-all` (ID: `C0B1HKW5Y7N`)
- 봇 초대 명령: `/invite @slackbot`

---

## 브랜치 전략 주의 ⚠️

**dev 브랜치가 main보다 stale 상태**.
- main에는 v5.38~v5.43에 추가된 라우터 6개 이상이 dev에 없음
  - kosha_collect / slack_kin / kin_generate / law_catalog_collector / tbm_issue / document_engine 등
- **dev → main 일반 머지 절대 금지** (이번 Phase 3는 cherry-pick으로 main에 적용)
- 추후 정리 별도 작업 필요

이번 세션의 main commit:
- `8329e00` — Phase 3 cherry-pick (코드 + 트리거 SQL 초안)
- `d3ca018` — pg_net 스키마 수정 (extensions → net)

---

## 진단 로그 (직접 검증 결과)

### Supabase에서 net.http_post로 직접 호출 → 라우터 응답 200

| id | content | 의미 |
|---|---|---|
| 2777 | `{"ok":true,"sent":false,"row_id":"00000000-..."}` | 라우터까지 정상, 슬랙 발송에서 실패 |
| 2775 | `{"ok":true,"sent":false,"row_id":"00000000-..."}` | 같은 결과, 일관성 확인 |

→ Phase 3 코드는 정상 작동. **slack 발송 단계만 막힘**.

### `sent: false` 원인 후보 (서비스 코드 기준)

`services/inbox_notify_svc.py`의 분기:

1. `SLACK_BOT_TOKEN` 또는 `SLACK_CHANNEL_ID_INBOX` 환경변수 누락 → 즉시 false
2. `chat.postMessage` 호출 시 슬랙 에러 응답 (not_in_channel / channel_not_found / invalid_auth 등)
3. httpx 예외 (timeout, network)

가장 가능성 높음: **#1 SLACK_CHANNEL_ID_INBOX 미등록** 또는 **봇이 채널에 미초대 → not_in_channel**.

진단법: Railway → tai-api → Logs 검색창에 `inbox_notify` 입력 → 가장 최근 warning 확인.

---

## 다음 세션 작업 순서

### 1. 슬랙 발송 정상화 (대표 + AI 협업)

대표가 확인할 것 (각 30초):

**A. Railway env 확인**
- Railway → tai-api → Variables 탭
- `SLACK_CHANNEL_ID_INBOX` 변수 존재 여부 확인
- 없으면 추가, 값 = `C0B1HKW5Y7N`
- 저장하면 자동 재배포 (1~2분)

**B. 슬랙 봇 초대 확인**
- 슬랙 `#inbox-all` 채널 입장
- 입력창에 `/invite @slackbot` 실행
- 이미 멤버면 "이미 추가됨" 안내 — 그것도 OK

**C. (필요 시) Railway 로그 확인**
- Railway → tai-api → Deployments → 최신 배포 → Logs
- 검색창에 `inbox_notify` 입력
- 가장 최근 warning 메시지 공유

### 2. 진단 SQL 재실행 (Supabase SQL Editor)

```sql
DO $$
DECLARE
  v_secret text;
  v_request_id bigint;
BEGIN
  SELECT decrypted_secret INTO v_secret
    FROM vault.decrypted_secrets WHERE name = 'internal_api_secret';

  SELECT net.http_post(
    url     := 'https://api.taieng.co.kr/internal/inbox/notify',
    body    := jsonb_build_object('record', jsonb_build_object(
      'id','test-handoff','source','marketing','inquiry_type','FEEDBACK',
      'category','fb_feature','content','핸드오프 후 재시도','name','테스트'
    )),
    headers := jsonb_build_object(
      'Content-Type','application/json','X-Internal-Secret', v_secret
    ),
    timeout_milliseconds := 5000
  ) INTO v_request_id;
END $$;

-- 5초 대기 후
SELECT id, status_code, content, created
FROM net._http_response
WHERE created > now() - interval '1 minute'
ORDER BY id DESC LIMIT 3;
```

기대: `content`가 `{"ok":true,"sent":true,...}` 로 변경 + 슬랙 채널에 메시지 도착.

### 3. 트리거 SQL 적용 (sent:true 확인 후)

Supabase SQL Editor에서 [`db/migrations/20260504_inbox_phase3_notify_trigger_vault.sql`](https://github.com/taiengineering/tai-api/blob/main/db/migrations/20260504_inbox_phase3_notify_trigger_vault.sql) 내용 전체 Run.

### 4. INSERT 경유 최종 검증

```sql
INSERT INTO inquiries (source, inquiry_type, category, content, name, email)
VALUES ('marketing', 'FEEDBACK', 'fb_feature',
  'INSERT 경유 최종 검증 — 슬랙에 메시지 뜨면 Phase 3 100% 완료',
  '테스트', 'admin@taieng.co.kr');

-- 응답 로그 확인
SELECT id, status_code, content, created
FROM net._http_response
WHERE created > now() - interval '1 minute'
ORDER BY id DESC LIMIT 3;

-- 정리
DELETE FROM inquiries WHERE content LIKE 'INSERT 경유%';
```

### 5. Phase 4·5 진행 (Phase 3 완료 후)

- Phase 4: 어드민 inquiry-list 페이지 확장 (인입경로·유형 필터, FEEDBACK 카테고리 추가, 사이드패널 분기)
- Phase 5: 마케팅·SaaS 사이트에 의견 폼 추가

상세 설계는 docs/inbox-system/README.md 와 PHASE3_NOTIFY_ENDPOINT.md 참고.

---

## 알려진 별개 이슈 (이번 작업과 무관, 메모만)

진단 중 `_http_response` 테이블에 보인 패턴:

1. **`Couldn't resolve host name`** 정기적 발생 (id 2770~2772 등) — 다른 cron이 잘못된 호스트로 호출 중. 누가 등록했는지 추적 필요.
2. **어드민 URL 호출 시 로그인 페이지 리다이렉트** (id 2746, 2755, 2764, 2773) — 인증 토큰 없는 cron이 어드민 URL 직접 호출. 추후 정리 필요.

위 둘은 인박스 시스템과 무관하므로 이번 작업에서는 건드리지 않음.

---

## 도구 제약 메모

이번 세션에서 끝까지 **Supabase MCP가 활성화되지 않음**. GitHub MCP 두 개(`github-tai`, `github-tai-admin`)만 사용 가능했음. 모든 SQL 작업은 대표가 Supabase Studio에서 직접 실행. 다음 세션에서 Supabase MCP가 활성화되면 진단·검증 작업이 훨씬 빨라질 것.

확인 방법: Claude.ai → Settings → Connectors에서 Supabase 연결 상태 점검 → 회색이면 재연결 → 녹색 확인 후 새 대화 시작.

---

## 관련 문서

- `docs/inbox-system/README.md` — 시스템 전체 개요
- `docs/inbox-system/PHASE1_DB_MIGRATION.md` — DB 마이그레이션
- `docs/inbox-system/PHASE2_SLACK_SETUP.md` — 슬랙·Railway 설정
- `docs/inbox-system/PHASE3_NOTIFY_ENDPOINT.md` — tai-api 엔드포인트 설계
- `docs/inbox-system/PHASE3_PATCH_VAULT.md` — Vault 기반 트리거 패치
- `db/migrations/20260504_inbox_phase1_inquiries.sql` — Phase 1 SQL
- `db/migrations/20260504_inbox_phase3_notify_trigger_vault.sql` — Phase 3 트리거 SQL
