-- T5 ENFORCE: overdue 는 테넌트+cron 이라 PLATFORM_* 매핑 제거.
DELETE FROM api_permissions
 WHERE api_code IN (
   'API_PLT_OD_CHECK',
   'API_PLT_OD_SUMMARY',
   'API_PLT_OD_HIST',
   'API_PLT_OD_RESOLVE'
 );
