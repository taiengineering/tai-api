# 빌링 결제 디버깅 완료 보고서 (2026-04-28~29)

## 세션 개요
- **기간**: 3창 걸친 디버깅 (이전 2창 실패 + 이번 창 해결)
- **문제**: `POST /payments/inicis/billing/prepare` 500 에러
- **근본 원인**: PostgREST 스키마 캐시가 `subscriptions.inicis_order_id` 컨럼을 인식 못함 (PGRST204)

---

## 해결된 이슈 목록

### 1. PostgREST PGRST204 스키마 캐시 문제
- **증상**: `supabase.table("subscriptions").insert(sub_row)` 실행 시 `inicis_order_id` 컨럼을 찾을 수 없다는 에러
- **시도한 방법 (모두 실패)**:
  - NOTIFY pgrst, 'reload schema'
  - ALTER TABLE DROP/ADD COLUMN
  - GRANT 권한 부여
  - RPC 함수 생성 (create_subscription)
  - Supabase 프로젝트 재시작
  - cancel_reason 컨럼 트리거 우회
- **최종 해결**: `psycopg2-binary` 추가 → PostgREST 완전 우회
  - `db/direct_sql.py` 모듈 생성 (insert_subscription, find_subscription_by_oid, update_subscription_by_oid)
  - `payment_billing.py` 3곳 수정 (Cursor로 적용)

### 2. DB 컨럼 누락
- **증상**: psycopg2 직접 연결에서 `inicis_order_id` 컨럼 존재하지 않음
- **원인**: MCP 마이그레이션으로 추가한 컨럼이 실제 DB에 반영되지 않았음
- **해결**: `/debug/db-columns` 엔드포인트에서 자동 감지/생성 + `billing_key_id` nullable 수정

### 3. IPv4 연결 문제
- **증상**: Railway(IPv4) → Supabase(IPv6) 연결 실패
- **해결**: Supabase IPv4 add-on 활성화 ($4/월)
- **DATABASE_URL**: `postgresql://postgres:Dmgmgj%21%40345@db.vwlahtguyggrhvslabax.supabase.co:5432/postgres`

### 4. billing_pay.html 프론트엔드 이슈 (5건)
1. **필드명 불일치**: inilitepay 폼 POST 방식 → INIStdPay.pay() 팝업 방식으로 전환
2. **version/currency 누락**: INIStdPay paramCheck 에러 → `version="1.0"`, `currency="WON"` 추가
3. **closeUrl 도메인 불일치**: `taieng.co.kr` vs `api.taieng.co.kr` → `window.location.origin` 동적 설정
4. **returnUrl 도메인 불일치**: 동일 문제 → `window.location.origin` 동적 설정
5. **프록시 경유 URL**: `taieng.co.kr/_api/` 경유 시 `/_api/` 프리픽스 자동 적용

### 5. 부가세 처리
- **이슈**: 가격이 부가세별도인데 그대로 결제됨
- **해결**: billing_pay.html에서 `amount * 1.1` 자동 변환, `vat_inclusive=true` 파라미터 지원

---

## 변경된 파일

### tai-api (백엔드)
| 파일 | 변경 내용 |
|------|----------|
| `requirements.txt` | `psycopg2-binary` 추가 |
| `db/direct_sql.py` | **신규** — insert_subscription, find_subscription_by_oid, update_subscription_by_oid |
| `routers/payment_billing.py` | 3곳 PostgREST → direct_sql 전환 (Cursor 적용) |
| `routers/debug.py` | **신규** — 임시 디버그 (해결 후 삭제 예정) |
| `templates/payment/billing_pay.html` | INIStdPay 팝업 방식 전환, 도메인 동적 설정, VAT 처리 |

### 환경변수 (Railway)
| 변수 | 값 |
|------|----|
| `DATABASE_URL` | `postgresql://postgres:***@db.vwlahtguyggrhvslabax.supabase.co:5432/postgres` |

### Supabase
| 변경 | 내용 |
|------|------|
| IPv4 add-on | 활성화 ($4/월) |
| `subscriptions.inicis_order_id` | 컨럼 재생성 (psycopg2 경유) |
| `subscriptions.billing_key_id` | NOT NULL → nullable 변경 |
| `create_subscription` RPC | 생성됨 (미사용, PostgREST 캐시 문제로) |

---

## 미해결 / 후속 작업

### 즉시
- [ ] `routers/debug.py` 삭제 (결제 안정화 확인 후)
- [ ] `payment_svc.py` 죽은 빌링 코드 정리 (run_billing_prepare/return/charge/cancel)
- [ ] 단건결제 로그인 유도 알럿 구현

### 카드심사 관련
- [ ] 이니시스 카드심사 메일 발송 (2026-04-29)
- [ ] billing_return 콜백 실제 테스트 (테스트 카드로 결제 완료까지)
- [ ] billing_keys 테이블 빌링키 저장 확인

### 향후
- [ ] PostgREST 캐시 문제 Supabase 지원팀 문의 (근본 해결)
- [ ] `create_subscription` RPC 함수 삭제 (미사용)
- [ ] `cancel_reason` 트리거 삭제 (move_oid_to_inicis_order_id, 미사용)
