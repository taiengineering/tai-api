# TAI 통합 인박스 시스템

외부 사이트(taieng.co.kr / safe.taieng.co.kr)에서 들어오는 모든 메시지를 어드민 한 곳에서 관리하는 시스템.

## 배경

어드민의 inquiry-list 페이지(문의관리)를 확장해서 두 종류의 외부 입력을 통합:

- **도입 문의 (INQUIRY)**: 기존 fix-request.html, 컨설팅·선임·수선 폼
- **TAI에 바란다 (FEEDBACK)**: 신규 — 마케팅 사이트와 SaaS에서 의견·버그·아이디어 수집

수선 챗봇(fix-chat-list)은 별도 시스템이라 통합하지 않음.

## 핵심 원칙

1. **테이블 1개로 통합** — `inquiries` 테이블에 `source` + `inquiry_type` 컬럼 추가
2. **어드민 페이지 1개만 사용** — inquiry-list 페이지 확장
3. **알림은 슬랙 통합** — 신규 채널 `C0B1HKW5Y7N` (#inbox-all)
4. **답변 시스템 재활용** — 기존 inquiry-list의 사이드패널 그대로

## 진행 현황

| Phase | 작업 | 상태 | 담당 |
|---|---|---|---|
| 1 | DB 마이그레이션 (inquiries 확장) | ✅ 완료 (2026-05-04) | 대표 직접 실행 |
| 2 | Railway env 추가 + 슬랙 봇 초대 | ⏳ | 대표 직접 |
| 3 | tai-api notify 엔드포인트 + DB Trigger | 📝 지시서 완성 | Cursor |
| 4 | 어드민 inquiry-list 포함 확장 | ⏳ | Cursor |
| 5 | 마케팅 + SaaS 의견 폼 | ⏳ | MCP / Cursor |

Phase 별 상세 가이드:
- `PHASE1_DB_MIGRATION.md`
- `PHASE2_SLACK_SETUP.md`
- `PHASE3_NOTIFY_ENDPOINT.md`

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

## 슬랙 환경변수 분리 정책

Railway env에서:

```
SLACK_BOT_TOKEN          ← 기존 (공용)
SLACK_CHANNEL_ID         ← 기존 (마케팅 채널 — 네이버 지식인 AI 승인)
SLACK_SIGNING_SECRET     ← 기존 (공용)
SLACK_CHANNEL_ID_INBOX   ← 신규 (C0B1HKW5Y7N — TAI에 바란다 + 도입 문의)
```

기존 `SLACK_CHANNEL_ID`(마케팅 채널)는 절대 건드리지 않음.

봇 이름: `@slackbot` (공용)

## 보안

- anon role은 외부 INSERT만 가능 (`source IN ('marketing','safe')` + 본문 길이 10~2000자)
- service_role(서버·어드민)은 RLS 무시 → 기존 페이지 그대로 작동
- DB Trigger는 `app.internal_api_secret`으로 X-Internal-Secret 헤더 전송
- Phase 3 진입 전 INTERNAL_API_SECRET 재발급 권장 (메모리 노트: 세션 중 노출 이력)
