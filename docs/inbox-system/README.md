# TAI 통합 인박스 시스템

외부 사이트(taieng.co.kr / safe.taieng.co.kr)에서 들어오는 모든 메시지를 어드민 한 곳에서 관리하는 시스템.

## 핵심 원칙

1. **테이블 1개로 통합** — `inquiries` 테이블에 `source` + `inquiry_type` 컬럼 추가
2. **어드민 페이지 1개만 사용** — inquiry-list 페이지 확장
3. **알림은 슬랙 통합** — 신규 채널 `C0B1HKW5Y7N` (#inbox-all)
4. **답변 시스템 재활용** — 기존 inquiry-list의 사이드패널 그대로

## 진행 현황

| Phase | 작업 | 상태 | 담당 |
|---|---|---|---|
| 1 | DB 마이그레이션 (inquiries 확장 + RLS) | ✅ 완료 (2026-05-04) | 대표 직접 |
| 2-a | Vault에 INTERNAL_API_SECRET 등록 | ✅ 완료 (2026-05-04) | 대표 직접 |
| 2-b | Railway env: SLACK_CHANNEL_ID_INBOX | ⏳ | 대표 직접 |
| 2-c | 슬랙 #inbox-all에 @slackbot 초대 | ⏳ | 대표 직접 |
| 3 | tai-api notify 엔드포인트 + DB Trigger | 📝 지시서 완성 | Cursor |
| 4 | 어드민 inquiry-list 포함 확장 (FEEDBACK 카테고리) | 📝 [`PHASE4_INQUIRY_LIST.md`](./PHASE4_INQUIRY_LIST.md) | Cursor |
| 5 | 마케팅 + SaaS 의견 폼 | ⏳ | MCP / Cursor |

## Phase 관련 문서

- `PHASE1_DB_MIGRATION.md` — DB 확장 적용 가이드
- `PHASE2_SLACK_SETUP.md` — 슬랙/Railway 설정
- `PHASE3_NOTIFY_ENDPOINT.md` — tai-api 엔드포인트 + 트리거 설계
- `PHASE3_PATCH_VAULT.md` ⚠️ — **실제 적용할 트리거 SQL 교체본** (Vault 방식)

## 채널 분류

| source | 의미 | 진입점 |
|---|---|---|
| `direct` | 어드민 직접 입력 | inquiry-list 페이지 신규 등록 |
| `marketing` | taieng.co.kr | 푸터 "TAI에 바란다" + 도입 문의 폼 |
| `safe` | safe.taieng.co.kr | 헤더 "의견 보내기" 메뉴 |

| inquiry_type | 의미 | 카테고리 |
|---|---|---|
| `INQUIRY` | 도입 문의 | consult/safety/electric/risk/csia/saas/repair/edu/partner/other |
| `FEEDBACK` | TAI에 바란다 | fb_feature/fb_bug/fb_ux/fb_idea/fb_praise |

## 보안

- anon role은 외부 INSERT만 가능 (`source IN ('marketing','safe')` + 본문 길이 10~2000자)
- service_role(서버·어드민)은 RLS 무시 → 기존 페이지 그대로 작동
- DB Trigger는 **Supabase Vault**에서 `internal_api_secret` 조회 (Cloud 제한으로 GUC 방식 불가)
  - Vault id: `42ef59f1-c484-4419-9d3b-00282b6464dc`
  - Railway `INTERNAL_API_SECRET`과 동일 값

## 슬랙 환경변수 분리 정책

Railway env에서:

```
SLACK_BOT_TOKEN          ← 기존 (공용)
SLACK_CHANNEL_ID         ← 기존 (마케팅 채널 — 네이버 지식인 AI 승인)
SLACK_SIGNING_SECRET     ← 기존 (공용)
SLACK_CHANNEL_ID_INBOX   ← 신규 (C0B1HKW5Y7N — TAI에 바란다 + 도입 문의)
INTERNAL_API_SECRET      ← 기존 (공용, Vault와 동일)
```

기존 `SLACK_CHANNEL_ID`(마케팅 채널)는 절대 건드리지 않음.

봇 이름: `@slackbot` (공용)
