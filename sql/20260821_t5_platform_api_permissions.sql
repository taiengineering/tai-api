-- T5: 라이브 플랫폼 라우트만 api_permissions 에 PLATFORM_* 매핑.
-- 격리(settlements/contracts_engine/matching/experts) 없음.
-- GET /companies 전사목록만 CUSTOMER_VIEW (테넌트 CRUD 유지).

UPDATE api_permissions
   SET permission_code = 'PLATFORM_CUSTOMER_VIEW',
       api_name = '회사전사목록(플랫폼)'
 WHERE api_code = 'API_COMPANY_LIST';

INSERT INTO api_permissions (api_code, api_name, api_path, http_method, permission_code)
VALUES
  -- settlement: payment_ops (테넌트 /payments/my 제외)
  ('API_PLT_PAY_LIST', '결제목록', '/payments', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  ('API_PLT_PAY_EXPIRING', '만료임박결제', '/payments/expiring', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  ('API_PLT_PAY_MANUAL', '수동입금확인', '/payments/manual/confirm', 'POST', 'PLATFORM_SETTLEMENT_MANAGE'),
  ('API_PLT_PAY_CANCEL', '결제취소', '/payments/{payment_id}/cancel', 'POST', 'PLATFORM_SETTLEMENT_MANAGE'),
  ('API_PLT_PAY_VBANK', '가상계좌상태', '/payments/{payment_id}/vbank-status', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  -- settlement: payment_ledger
  ('API_PLT_LEDGER_FLAGS', '원장라이브플래그', '/payments/ops/live-flags', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  ('API_PLT_LEDGER_READY', '게이트준비', '/payments/ops/gate-readiness', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  ('API_PLT_LEDGER_ON', '게이트활성화', '/payments/ops/gate/activate', 'POST', 'PLATFORM_SETTLEMENT_MANAGE'),
  ('API_PLT_LEDGER_OFF', '게이트비활성화', '/payments/ops/gate/deactivate', 'POST', 'PLATFORM_SETTLEMENT_MANAGE'),
  ('API_PLT_LEDGER_CREDIT', '크레딧부여', '/payments/{payment_id}/credit', 'POST', 'PLATFORM_SETTLEMENT_MANAGE'),
  ('API_PLT_LEDGER_TAX', '세금계산서발행', '/payments/{payment_id}/invoice/tax', 'POST', 'PLATFORM_SETTLEMENT_MANAGE'),
  ('API_PLT_LEDGER_CASH', '현금영수증발행', '/payments/{payment_id}/invoice/cash', 'POST', 'PLATFORM_SETTLEMENT_MANAGE'),
  ('API_PLT_LEDGER_GET', '결제원장조회', '/payments/{payment_id}/ledger', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  -- settlement: payment_activation_api
  ('API_PLT_ACT_E2E', '결제E2E검증', '/payment/e2e-validate', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  ('API_PLT_ACT_GUARD', '활성화가드', '/payment/activation-guard', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  ('API_PLT_ACT_STATUS', '결제상태요약', '/payment/status-summary', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  ('API_PLT_ACT_SUB', '구독활성화', '/payment/activate-subscription/{subscription_id}', 'POST', 'PLATFORM_SETTLEMENT_MANAGE'),
  ('API_PLT_ACT_ORPHAN', '고아결제조회', '/payment/orphans', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  -- settlement: overdue_checker
  ('API_PLT_OD_CHECK', '연체점검실행', '/overdue/check', 'POST', 'PLATFORM_SETTLEMENT_MANAGE'),
  ('API_PLT_OD_SUMMARY', '연체요약', '/overdue/summary', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  ('API_PLT_OD_HIST', '연체이력', '/overdue/history', 'GET', 'PLATFORM_SETTLEMENT_VIEW'),
  ('API_PLT_OD_RESOLVE', '연체해소', '/overdue/resolve/{history_id}', 'POST', 'PLATFORM_SETTLEMENT_MANAGE'),
  -- tax (현재 GET만)
  ('API_PLT_TAX_OPS', '세무현황', '/tax/ops', 'GET', 'PLATFORM_TAX_VIEW'),
  ('API_PLT_TAX_UNISSUED', '미발행세금계산서', '/tax/unissued', 'GET', 'PLATFORM_TAX_VIEW'),
  ('API_PLT_TAX_ISSUED', '발행세금계산서', '/tax/issued', 'GET', 'PLATFORM_TAX_VIEW'),
  -- alert
  ('API_PLT_ALERT_LIST', '알럿목록', '/alert-messages', 'GET', 'PLATFORM_ALERT_VIEW'),
  ('API_PLT_ALERT_CODES', '알럿코드', '/alert-messages/codes', 'GET', 'PLATFORM_ALERT_VIEW'),
  ('API_PLT_ALERT_CTX', '알럿컨텍스트', '/alert-messages/contexts', 'GET', 'PLATFORM_ALERT_VIEW'),
  ('API_PLT_ALERT_CREATE', '알럿등록', '/alert-messages', 'POST', 'PLATFORM_ALERT_MANAGE'),
  ('API_PLT_ALERT_PATCH', '알럿수정', '/alert-messages/{alert_id}', 'PATCH', 'PLATFORM_ALERT_MANAGE'),
  ('API_PLT_ALERT_TOGGLE', '알럿토글', '/alert-messages/{alert_id}/toggle', 'PATCH', 'PLATFORM_ALERT_MANAGE'),
  ('API_PLT_ALERT_DEL', '알럿삭제', '/alert-messages/{alert_id}', 'DELETE', 'PLATFORM_ALERT_MANAGE'),
  -- diagnosis admin
  ('API_PLT_DIAG_LIST', '익명진단목록', '/anonymous-diagnosis/admin/list', 'GET', 'PLATFORM_DIAGNOSIS_ADMIN_VIEW'),
  ('API_PLT_DIAG_DETAIL', '익명진단상세', '/anonymous-diagnosis/admin/detail/{record_id}', 'GET', 'PLATFORM_DIAGNOSIS_ADMIN_VIEW'),
  ('API_PLT_DIAG_PATCH', '익명진단수정', '/anonymous-diagnosis/admin/{record_id}', 'PATCH', 'PLATFORM_DIAGNOSIS_ADMIN_MANAGE'),
  ('API_PLT_DIAG_EXPIRE', '익명진단만료', '/anonymous-diagnosis/admin/expire-stale', 'POST', 'PLATFORM_DIAGNOSIS_ADMIN_MANAGE'),
  ('API_PLT_DIAG_DEL', '익명진단삭제', '/anonymous-diagnosis/admin/{record_id}', 'DELETE', 'PLATFORM_DIAGNOSIS_ADMIN_MANAGE'),
  -- inquiry
  ('API_PLT_INQ_LIST', '문의목록', '/admin/inquiries', 'GET', 'PLATFORM_INQUIRY_VIEW'),
  ('API_PLT_INQ_TAX', '문의분류옵션', '/admin/inquiries/taxonomy-options', 'GET', 'PLATFORM_INQUIRY_VIEW'),
  ('API_PLT_INQ_CREATE', '문의등록', '/admin/inquiries', 'POST', 'PLATFORM_INQUIRY_MANAGE'),
  ('API_PLT_INQ_PATCH', '문의처리', '/admin/inquiries/{inquiry_id}', 'PATCH', 'PLATFORM_INQUIRY_MANAGE'),
  -- saas contract writes (GET 목록은 테넌트 겸용 → 미매핑)
  ('API_PLT_QUOTE_CREATE', '견적등록', '/quotes', 'POST', 'PLATFORM_CONTRACT_MANAGE'),
  ('API_PLT_QUOTE_PATCH', '견적수정', '/quotes/{quote_id}', 'PATCH', 'PLATFORM_CONTRACT_MANAGE'),
  ('API_PLT_QUOTE_CONFIRM', '견적확정', '/quotes/{quote_id}/confirm', 'POST', 'PLATFORM_CONTRACT_MANAGE'),
  ('API_PLT_QUOTE_CONVERT', '견적전환', '/quotes/{quote_id}/convert', 'POST', 'PLATFORM_CONTRACT_MANAGE'),
  ('API_PLT_CT_CREATE', '계약등록', '/contracts', 'POST', 'PLATFORM_CONTRACT_MANAGE'),
  ('API_PLT_CT_PATCH', '계약수정', '/contracts/{contract_id}', 'PATCH', 'PLATFORM_CONTRACT_MANAGE'),
  ('API_PLT_CT_STATUS', '계약상태', '/contracts/{contract_id}/status', 'PATCH', 'PLATFORM_CONTRACT_MANAGE'),
  ('API_PLT_CT_ACT', '계약활성화', '/contracts/{contract_id}/activate', 'POST', 'PLATFORM_CONTRACT_MANAGE'),
  ('API_PLT_CT_PAY', '계약결제연결', '/contracts/{contract_id}/payment', 'POST', 'PLATFORM_CONTRACT_MANAGE'),
  ('API_PLT_CT_SUSPEND', '계약정지', '/contracts/{contract_id}/suspend', 'POST', 'PLATFORM_CONTRACT_MANAGE'),
  ('API_PLT_CT_CANCEL', '계약해지', '/contracts/{contract_id}/cancel', 'POST', 'PLATFORM_CONTRACT_MANAGE'),
  -- audit / ops / fix admin
  ('API_PLT_OPS_HOME', '관제홈', '/ops/home', 'GET', 'PLATFORM_AUDIT_VIEW'),
  ('API_PLT_AUDIT_LOGS', '감사로그', '/admin/audit-logs', 'GET', 'PLATFORM_AUDIT_VIEW'),
  ('API_PLT_AUDIT_ACTIONS', '감사액션목록', '/admin/audit-logs/actions', 'GET', 'PLATFORM_AUDIT_VIEW'),
  ('API_PLT_FIX_STATS', 'Fix상담통계', '/fix/chat/admin/stats', 'GET', 'PLATFORM_AUDIT_VIEW'),
  ('API_PLT_FIX_SESS', 'Fix상담목록', '/fix/chat/admin/sessions', 'GET', 'PLATFORM_AUDIT_VIEW'),
  ('API_PLT_FIX_SESS_ONE', 'Fix상담상세', '/fix/chat/admin/sessions/{session_id}', 'GET', 'PLATFORM_AUDIT_VIEW')
ON CONFLICT (api_code) DO UPDATE
  SET api_path = EXCLUDED.api_path,
      http_method = EXCLUDED.http_method,
      permission_code = EXCLUDED.permission_code,
      api_name = EXCLUDED.api_name;
