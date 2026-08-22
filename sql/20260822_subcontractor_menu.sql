-- 하도급관리 메뉴: construction-subcontractor-list (CONSTRUCTION, 현장목록 옆)
INSERT INTO public.menu_catalog (menu_code, title, group_code, group_title, sort_order, sectors)
VALUES ('construction-subcontractor-list', '하도급관리', 'ETC', '기타', 1025, '{CONSTRUCTION}')
ON CONFLICT (menu_code) DO UPDATE
  SET title = EXCLUDED.title,
      group_code = EXCLUDED.group_code,
      group_title = EXCLUDED.group_title,
      sort_order = EXCLUDED.sort_order,
      sectors = EXCLUDED.sectors,
      is_active = true;

INSERT INTO public.role_menu_permissions (role_code, menu_code, can_list, can_create, can_update, can_delete, can_export)
SELECT r.role_code, 'construction-subcontractor-list', r.can_list, r.can_create, r.can_update, r.can_delete, r.can_export
FROM public.role_menu_permissions r
WHERE r.menu_code = 'construction-site-list'
ON CONFLICT (role_code, menu_code) DO UPDATE
  SET can_list = EXCLUDED.can_list,
      can_create = EXCLUDED.can_create,
      can_update = EXCLUDED.can_update,
      can_delete = EXCLUDED.can_delete,
      can_export = EXCLUDED.can_export;
