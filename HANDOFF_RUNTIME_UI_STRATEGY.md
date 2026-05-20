# Runtime UI Strategy + 법령진단 Runtime 연결

## 2026-05-20

## 핵심 전환

```
기존: 엔진 중심 SaaS (법령메뉴 / 마케팅메뉴 / CRM메뉴)
현재: 운영(Runtime) 중심 OS (오늘상태 / 승인대기 / 이벤트 / Risk)
```

## UI = Runtime Projection

UI는 엔진을 드러내지 않는다.
사용자는 "회사 운영"을 한다.

## 공통 Runtime 구조

state / assignment / schedule / escalation / evidence / reviewer / risk / audit / projection

모든 엔진은 공통 Runtime Workspace로 통합.

## 제품 경계

- FREE: 법령진단 + Candidate Preview + PDF
- PAID (전환점 = Activation): Schedule + Assignment + Evidence + Cockpit
- BUSINESS: + Reviewer + Escalation + Risk + Document
- ENTERPRISE: + Audit + Multi-site + API

## E2E 흐름

무료: 주소입력 → 법령매칭 → Preview → PDF → CTA
유료: 세팅입력 → Runtime생성 → Cockpit → PDF/Excel → 지속운영

## 운영 철학

- Human Governance: 사람 최종판단
- Runtime State: 업무=상태
- Deterministic: 구조 기반
- Optional Adoption: 엑셀 운영도 가능

## P0
1. Candidate Preview 컴포넌트
2. Activation CTA
3. Runtime Cockpit 웹페이지
4. 운영계획서 PDF
