# 🔒 Supabase RLS 보안 감사 (2026-04-22)

## 배경

2026-04-19 기준 Supabase Security Advisor에서 277개 lint 감지 (ERROR 54, WARN 41, INFO 182). 공개 테이블 RLS 미활성화로 프로젝트 URL과 anon key를 아는 사람은 누구나 민감 데이터에 접근 가능한 상태였음.

## 긴급 조치 (완료)

### `otp_store` RLS enable ✅

- **위험도**: 🚨 최상위 (OTP 인증 코드, 개인 전화번호)
- **조치**: RLS enable + `service_role_full_access` 정책 적용
- **검증**: POST `/auth/send-otp` 호출 → OTP 정상 저장 확인 (end-to-end)
- **Migration**: `sql/20260422_secure_otp_store_rls.sql`

### 환경변수 확인 결과

- **Railway `SUPABASE_KEY`**: `service_role` 키 확인 ✅
- 서버 API는 RLS를 bypass하여 정상 작동
- 외부(anon key 사용자)는 차단됨

---

## 전체 취약점 현황 (277개)

### ERROR (54개) — 즉시 조치 필요

#### A. RLS Disabled (43개)

**민감 정보 포함 (10개)** — 우선순위 1:
- `otp_store` ✅ (완료)
- `expert_applications` (license_number)
- `fix_provider_qualifications` (license_number)
- `fix_chat_messages`, `fix_chat_sessions`
- `settlements`, `price_commission`, `connection_commission`
- `diagnosis_auth_log`, `identity_logs`

**결제/프라이싱 (5개)** — 우선순위 2:
- `product_pricing`, `price_policy`, `pricing_key_map`
- `connect_pre_registration`, `connect_registrations`

**진단 데이터 (5개)** — 우선순위 3:
- `anonymous_diagnosis_results`
- `diagnosis_disclaimer_log`, `diagnosis_results_backup_20260416`
- `diagnosis_input_fields`
- `industrial_accident_precedents`

**Fix 서비스 테이블 (8개)** — 우선순위 4:
- `fix_providers`, `fix_provider_services`, `fix_providers_qualifications`
- `fix_subcategory`, `fix_category`, `fix_qualification_master`
- `fix_service_qualification_map`, `fix_service_requests`

**Connect 서비스 테이블 (6개)** — 우선순위 5:
- `connect_providers`, `connect_provider_services`, `connect_service_master`
- `connect_service_relations`, `connect_issue_service_links`, `connect_issue_service_map`

**내부 관리 (6개)** — 우선순위 6:
- `monitoring_config`, `agent_service`
- `auto_qa_checks`, `auto_qa_log`, `auto_qa_pending`, `reparse_job_log`

**기타 (3개)**:
- `notification_queue`, `overdue_history`
- `law_quality_snapshot_20260422`, `law_article_key_map` (법령엔진 어제 생성)

#### B. Security Definer Views (7개)

뷰가 소유자 권한으로 실행되어 RLS를 우회할 수 있음:
- `fix_provider_overview`
- `v_equipment_unified`, `v_expert_list`, `v_process_unified`
- `v_payments_list`, `v_demo_buildings`
- `v_industry_mapping_summary`

**조치 방향**: `SECURITY INVOKER` 로 변경하거나 명시적 검토

#### C. Sensitive Columns Exposed (4개)

A의 subset이지만 민감 컬럼 특정됨:
- `otp_store.otp` ✅ (완료)
- `expert_applications.license_number`
- `fix_provider_qualifications.license_number`
- `fix_chat_messages.session_id`

### WARN (41개)

- `function_search_path_mutable` (31개): 함수에 `SET search_path` 누락
- `public_bucket_allows_listing` (4개): Storage 버킷 공개 리스팅
- `materialized_view_in_api` (2개): Materialized view가 API 노출
- `extension_in_public` (2개): 확장이 public schema에 설치
- `auth_leaked_password_protection` (1개): 유출 비밀번호 보호 비활성
- `rls_policy_always_true` (1개): `mail_logs` 정책이 항상 true

### INFO (182개)

`rls_enabled_no_policy`: RLS는 활성화됐지만 정책이 없어 모든 접근 차단 (적절한 경우도 있지만 의도 검토 필요)

---

## 단계별 해결 계획

### Phase S-1: 긴급 (오늘~이번주)

- [x] `otp_store` RLS enable ✅
- [ ] 민감 정보 3개 테이블 (`expert_applications`, `fix_provider_qualifications`, `fix_chat_messages`)
- [ ] 결제 관련 테이블 3개 (`settlements`, `price_commission`, `connection_commission`)
- [ ] 인증/ID 로그 2개 (`diagnosis_auth_log`, `identity_logs`)

### Phase S-2: ERROR 전체 정리 (다음주)

- [ ] RLS Disabled 40개 남은 테이블
- [ ] Security Definer Views 7개 검토

### Phase S-3: WARN 정리 (이달 말)

- [ ] `function_search_path_mutable` 31개
- [ ] `mail_logs` 정책 검토 (`rls_policy_always_true`)
- [ ] Storage 버킷 공개 리스팅 4개
- [ ] 유출 비밀번호 보호 활성화 (Supabase 대시보드)

### Phase S-4: INFO 검토 (여유 있을 때)

- [ ] 182개 테이블 정책 설계 (service_role만? authenticated 허용? 공개?)

---

## 각 테이블별 기본 정책 패턴

### 패턴 A: service_role만 접근 (내부 관리용)

```sql
ALTER TABLE public.<TABLE> ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access"
  ON public.<TABLE>
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);
```

**적용 대상**: `otp_store`, `monitoring_config`, `auto_qa_*`, `law_*_snapshot`, 내부 로그

### 패턴 B: 사용자 본인 데이터만 접근

```sql
ALTER TABLE public.<TABLE> ENABLE ROW LEVEL SECURITY;

-- 본인 행만 select
CREATE POLICY "user_read_own" ON public.<TABLE>
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

-- 본인 행만 update
CREATE POLICY "user_update_own" ON public.<TABLE>
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- service_role 전체 허용 (서버 API)
CREATE POLICY "service_role_full_access" ON public.<TABLE>
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);
```

**적용 대상**: `expert_applications`, `fix_chat_sessions`, `diagnosis_*`

### 패턴 C: 공개 읽기 + 관리자만 쓰기

```sql
ALTER TABLE public.<TABLE> ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read" ON public.<TABLE>
  FOR SELECT TO anon, authenticated
  USING (is_active = true);

CREATE POLICY "service_role_write" ON public.<TABLE>
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);
```

**적용 대상**: `fix_category`, `fix_subcategory`, `industrial_accident_precedents`

---

## 실행 원칙

1. **service_role 확인 필수**: 각 테이블에 접근하는 서버 코드가 `SUPABASE_KEY` (service_role)를 쓰는지 확인
2. **기존 사용처 파악**: 프런트엔드(anon key)에서 직접 쓰는 테이블이면 정책 신중 설계
3. **End-to-end 테스트**: RLS 적용 후 반드시 관련 API 호출해서 검증
4. **기록**: 각 테이블별 migration SQL + 이 문서에 체크
5. **Rollback 준비**: 문제 시 `ALTER TABLE <T> DISABLE ROW LEVEL SECURITY;` 한 줄로 복구

---

## 참고

- Supabase 공식 문서: https://supabase.com/docs/guides/database/postgres/row-level-security
- Security Advisor: https://supabase.com/dashboard/project/xntdkrjhgcscmqctdzyo/advisors/security
