-- api_permissions.menu_code: 테넌트 통제면(role_menu_permissions) 매핑.
-- PLATFORM_* 와 system-codes 는 NULL (게이트 제외 / 플랫폼은 role_permissions).
ALTER TABLE public.api_permissions ADD COLUMN IF NOT EXISTS menu_code text;

UPDATE public.api_permissions SET menu_code = NULL WHERE permission_code LIKE 'PLATFORM_%';

UPDATE public.api_permissions SET menu_code = CASE
  WHEN api_path LIKE '/companies%' THEN 'my-company'
  WHEN api_path LIKE '/factories%' THEN 'factory-list'
  WHEN api_path LIKE '/equipment-assets%' THEN 'my-equipment'
  WHEN api_path LIKE '/inspection/%' THEN 'my-inspection'
  WHEN api_path LIKE '/inspection-sets%' THEN 'inspection-anchor'
  WHEN api_path LIKE '/work-schedules%' THEN 'work-schedule-list'
  WHEN api_path LIKE '/legal-engine%' THEN 'engine-document'
  WHEN api_path LIKE '/users%' THEN 'worker-list'
  WHEN api_path LIKE '/system-codes%' THEN NULL
  ELSE menu_code
END
WHERE permission_code NOT LIKE 'PLATFORM_%';
