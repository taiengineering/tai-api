-- T4: api_permissions 를 실제 FastAPI path template 에 정합.
-- /api 접두 제거, {id} → 실제 파라미터명, 없는 경로(defects) 삭제.
-- permission_code 기존값 유지. 없는 조합만 INSERT.

-- 1) /api 접두·잘못된 템플릿 교정
UPDATE api_permissions SET api_path = '/users', http_method = 'GET'
 WHERE api_code = 'API_USER_LIST';
UPDATE api_permissions SET api_path = '/users', http_method = 'POST'
 WHERE api_code = 'API_USER_CREATE';
UPDATE api_permissions SET api_path = '/equipment-assets', http_method = 'GET'
 WHERE api_code = 'API_EQUIPMENT_LIST';
UPDATE api_permissions SET api_path = '/equipment-assets', http_method = 'POST'
 WHERE api_code = 'API_EQUIPMENT_CREATE';
UPDATE api_permissions SET api_path = '/inspection/start/{work_schedule_id}', http_method = 'POST'
 WHERE api_code = 'API_INSPECTION_RUN';
UPDATE api_permissions SET api_path = '/inspection/complete/{work_schedule_id}', http_method = 'POST'
 WHERE api_code = 'API_WORK_EXECUTE';

UPDATE api_permissions SET api_path = '/companies/{company_id}'
 WHERE api_code IN ('API_COMPANY_UPDATE', 'API_COMPANY_DELETE');
UPDATE api_permissions SET api_path = '/factories/{factory_id}'
 WHERE api_code IN ('API_FACTORY_UPDATE', 'API_FACTORY_DELETE');
UPDATE api_permissions SET api_path = '/users/{user_id}'
 WHERE api_code IN ('API_USER_UPDATE', 'API_USER_DELETE');
UPDATE api_permissions SET api_path = '/legal-engine/apply/{factory_id}'
 WHERE api_code = 'API_LEGAL_APPLY';
UPDATE api_permissions SET api_path = '/legal-engine/result/{factory_id}'
 WHERE api_code = 'API_LEGAL_RESULT';
UPDATE api_permissions SET api_path = '/legal-engine/summary/{factory_id}'
 WHERE api_code = 'API_LEGAL_SUMMARY';

UPDATE api_permissions SET api_path = '/inspection/schedules', http_method = 'GET'
 WHERE api_code = 'API_INSPECTION_LIST';
UPDATE api_permissions SET api_path = '/inspection-sets/manual', http_method = 'POST'
 WHERE api_code = 'API_INSPECTION_CREATE';
UPDATE api_permissions SET api_path = '/work-schedules/bulk-assign', http_method = 'POST'
 WHERE api_code = 'API_WORK_ASSIGN';
UPDATE api_permissions SET api_path = '/work-schedules/auto-assign', http_method = 'POST'
 WHERE api_code = 'API_WORK_CREATE';

-- 2) 실제 라우트 없는 defects 3행 제거
DELETE FROM api_permissions
 WHERE api_code IN ('API_DEFECT_CREATE', 'API_DEFECT_LIST', 'API_DEFECT_UPDATE');

-- 3) ENFORCE 대상 자원의 누락 조합만 추가 (permission_code 기존 45종)
INSERT INTO api_permissions (api_code, api_name, api_path, http_method, permission_code)
VALUES
  ('API_COMPANY_GET', '회사상세조회', '/companies/{company_id}', 'GET', 'COMPANY_VIEW'),
  ('API_FACTORY_GET', '공장상세조회', '/factories/{factory_id}', 'GET', 'FACTORY_VIEW'),
  ('API_USER_GET', '사용자상세조회', '/users/{user_id}', 'GET', 'USER_VIEW'),
  ('API_EQUIPMENT_UPDATE', '설비수정', '/equipment-assets/{asset_id}', 'PATCH', 'EQUIPMENT_UPDATE'),
  ('API_EQUIPMENT_DELETE', '설비삭제', '/equipment-assets/{asset_id}', 'DELETE', 'EQUIPMENT_DELETE'),
  ('API_WORK_GET', '작업상세조회', '/work-schedules/{schedule_id}', 'GET', 'WORK_VIEW'),
  ('API_INSPECTION_STATUS', '점검상태조회', '/inspection/status/{factory_id}', 'GET', 'INSPECTION_VIEW')
ON CONFLICT (api_code) DO UPDATE
  SET api_path = EXCLUDED.api_path,
      http_method = EXCLUDED.http_method,
      permission_code = EXCLUDED.permission_code,
      api_name = EXCLUDED.api_name;
