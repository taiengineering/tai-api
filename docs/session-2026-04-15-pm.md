# TAI Safe 개발 세션 기록 — 2026-04-15 (오후)

## 세션 요약

### 완료된 작업

#### 1. 메세지미 고정 IP 구축 (Vultr 서울)
- **VM:** Vultr Seoul KR, Shared CPU $5/월, Ubuntu 24.04
- **고정 IP:** `158.247.224.158`
- **구성:** Squid 프록시 3128포트
- **아키텍처:** Fly.io → Vultr 서울(158.247.224.158:3128) → 메세지미/KG이니시스
- Fly.io 환경변수: `OUTBOUND_PROXY=http://158.247.224.158:3128`
- 메세지미 IP 등록 완료 → **SMS code:100 발송 성공** ✅
- 알림톡 API 경로 정상 (code:215 = 템플릿 미등록) ✅
- messaging.py v5.0.0: OUTBOUND_PROXY 환경변수 경유 구조

#### 2. TAI Fix 업체등록 API (fix_providers_api.py v1.1.0) — main 배포
- `POST /connect/providers` — 업체 등록 (공개, 트랜잭션 롤백)
- `GET /connect/providers` — 목록 (fix_provider_overview 뷰)
- `GET /connect/providers/{id}` — 상세
- fix_service_qualification_map A등급 21개 중분류 → 30개 매핑 INSERT 완료
- DB 테스트 완료: license_count=1, cert_staff_count=4, service_count=2 ✅

#### 3. 법령진단 입력항목 API (diagnosis_fields.py v1.0.0) — v5.23.0
- `GET /diagnosis/fields?sector=BUILDING&tier=PAID` — 동적 폼 데이터
- `GET /diagnosis/pricing?sector=BUILDING&total_floor_area=8000` — 가격 자동 판단
- Supabase 검증: 총 111건, BUILDING PAID 10그룹 36건 ✅

#### 4. TAI Fix 대화형 입력부 (fix_chat.py v1.0.0) — v5.24.0
- **DB 테이블:** fix_chat_sessions, fix_chat_messages
- `POST /fix/chat/start` — 세션 생성 (인증 불필요)
- `POST /fix/chat/message` — Claude API 대화 (인증 불필요)
- `POST /fix/chat/complete` — matching_requests 저장 (회원 인증 필수)
- 턴 제한: GUEST=3, MEMBER=10, SUBSCRIBER=12
- ANTHROPIC_API_KEY Fly.io 등록 완료
- **테스트 완료:** SMS/알림톡 모두 정상, Claude 대화 응답 정상 ✅

#### 5. 어드민 메일박스 버그 수정 (tai-admin)
- **원인:** `/assets/*` Cloudflare CDN `immutable` 1년 캐시로 mail.page.js 수정 불반영
- **수정 파일:**
  - `mail.page.js` → v1.0.1 (DOMContentLoaded readyState 체크)
  - `mail.page.v2.js` → 신규 파일명으로 CDN 캐시 완전 우회
  - `tai-mail.html` → `mail.page.v2.js` 참조 변경
  - `_headers` → `/assets/js/tai/*` 캐시 1년→1시간으로 단축

---

## 현재 버전 현황

| 서비스 | 버전 | 인프라 |
|---|---|---|
| tai-api (백엔드) | v5.24.0 | Fly.io 도쿄 |
| tai-admin (어드민) | main 최신 | Cloudflare Pages |
| Vultr 프록시 | 가동중 | Seoul KR (158.247.224.158:3128) |

## 주요 환경변수 (Fly.io tai-api-prod)

| 변수 | 상태 |
|---|---|
| MESSAGEME_API_KEY | ✅ |
| MESSAGEME_SENDER | ✅ 070-8080-1858 |
| OUTBOUND_PROXY | ✅ http://158.247.224.158:3128 |
| JUSO_API_KEY | ✅ |
| ANTHROPIC_API_KEY | ✅ |

## 고정 IP 정책 확정

```
158.247.224.158 — Vultr 서울 고정 IP
  → 메세지미 등록 완료
  → KG이니시스 결제 승인 시 이 IP 등록 필요
  → 앞으로 모든 IP 제한 외부 서비스는 이 IP 하나만 등록
```

## 다음 작업 후보

- KG이니시스 결제 승인 완료 후 IP 등록
- 메세지미 알림톡 템플릿 등록 (카카오 채널 연동 후)
- TAI Fix 프론트엔드 채팅 UI 연동
- pricing.html 고도화 (SaaS 과금구조_기획서 v1.0 기반)
