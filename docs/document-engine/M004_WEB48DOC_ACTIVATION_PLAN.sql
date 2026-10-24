-- =====================================================================
-- M004_WEB48DOC_ACTIVATION_PLAN.sql
-- WO-TAI-M004-WEB48DOC-ACTIVATION-EXEC-001 — WEB 48종 운영 활성화
-- =====================================================================
-- !!! NOT EXECUTED — Owner + PRJ 운영 변경 승인 전 실행 금지 !!!
-- 목적: WEB 48종 서식 스키마 활성화 (INSPECTION_SOURCE 15종 제외)
--   runtime_field (245건): CANDIDATE/CANDIDATE_ONLY
--     → APPROVED_BY_HUMAN / REQUIRED_BY_HUMAN(186) 또는 NOT_REQUIRED(59)
--   runtime_form_schema (48건): CANDIDATE
--     → APPROVED_BY_HUMAN → APPROVED_FOR_RUNTIME_USE
--   runtime_checklist_item (119건): APPROVED_BY_HUMAN 유지 (변경 없음)
--   runtime_form_audit_log: 48건 삽입
--
-- 기준: Step4D (docs/sql/20260825_WP_PERSISTENCE_02A_STEP4D_UP.sql)
-- 파일럿: docs/document-engine/M004_PILOT_ACTIVATION_PLAN_DOC_CON_044.sql
-- 63종 원본: docs/document-engine/M004_63DOC_ACTIVATION_PLAN.sql
-- 작성: Claude Code (WO-TAI-M004-WEB48DOC-ACTIVATION-EXEC-001) 2026-10-23
--
-- 대상:
--   TARGET_DOCS          = 48
--   TARGET_FIELDS        = 245 (REQUIRED_BY_HUMAN=186, NOT_REQUIRED=59)
--   CHECKLISTS_PRESERVED = 119 (APPROVED_BY_HUMAN 불변)
--   EXCLUDE_COMPLETED    = DOC-CON-044 (별도 실행 완료 2026-10-22)
--   EXCLUDE_INSPECTION   = INSPECTION_SOURCE 15종 (별도 AUTO_SOURCE 경로 유지)
--   EXCLUDE_UNSUPPORTED  = DOC-SERA-011 (편집기 미지원 타입)
--
-- 고객 활성화 영향:
--   APPROVED_FOR_RUNTIME_USE = READY_FOR_EDIT = can_create=true.
--   이 SQL 실행 즉시 48종 모든 고객 사업장에서 API 수준에서 문서 생성 가능.
--   기술적 격리 없음. SQL 실행 = 실제 고객 노출.
--
-- 원자성: 단일 DO 블록. ASSERT 실패 시 전체 롤백. 부분 승격 없음.
-- =====================================================================

DO $$
DECLARE
  v_cnt        integer;
  v_before_all jsonb;

  v_schema_ids  uuid[];
  v_catalog_ids uuid[];
  v_cand_ids    uuid[];

BEGIN

  v_schema_ids := ARRAY[
    '2c62ce24-baea-4d39-a5dc-ce030648d0d7'::uuid,
    'f9de138a-138d-4202-a7be-4bb7158d92c4'::uuid,
    'ecc54b1d-7f3e-4556-9134-94ad4dd3cd97'::uuid,
    'dcea0582-d5eb-4671-a258-b75d142e83f3'::uuid,
    'ee1e9dde-2b7f-4278-9cf2-a64476d8a014'::uuid,
    '331ab855-e930-434b-9f8c-25f8a6c8988a'::uuid,
    '910ef261-3f3b-46a7-9f0b-d6ced4a92376'::uuid,
    '0204725e-c5e8-4cdb-b9a8-ddf8a423ed00'::uuid,
    '3b246692-a2d2-4b83-978b-11754dfca0ce'::uuid,
    '3214f248-9fce-4169-a243-a4e43f3e81e5'::uuid,
    '9c34459f-5b82-40f7-a03a-a532cfdefdd4'::uuid,
    '5d5a2b58-80e3-4924-933a-006b89267d26'::uuid,
    '99905f16-9b1e-4b79-8e15-ef2d2d56b5e0'::uuid,
    'b3071484-1547-4f1e-8b5f-12ed391f5519'::uuid,
    '98b60eca-5a11-4fc5-a386-c62fb67277a4'::uuid,
    '4bf3ed32-a9b3-4fdc-ba1a-dd9e5a6de27d'::uuid,
    '48b04ae3-4c0e-4f78-949c-fc8a24421c50'::uuid,
    '769d94ff-476e-4d2a-9310-acdff418bda0'::uuid,
    '328bcdb1-45cf-401c-99ad-76e131a39be5'::uuid,
    '5e89caa2-da79-4d20-86f1-cdfe138b5ac7'::uuid,
    '3ce74995-9679-4cf0-acde-f46fbd940454'::uuid,
    '4f783679-c8ab-42f1-98c5-ce429cd38b19'::uuid,
    '3ac8db99-aede-460f-b2d5-daa969b29b6b'::uuid,
    'c959e7e9-942b-449a-aead-904996476687'::uuid,
    '117958e3-f936-4d06-b869-273001ea023d'::uuid,
    'b920ccaf-191a-492c-b43f-8c8f785c632c'::uuid,
    'eddf1605-7b4f-469f-947d-a4380ba6a8cc'::uuid,
    '8e1aea7d-1220-4352-bfd0-569d6c9478eb'::uuid,
    'b65478e8-d239-41e0-8959-c4d5b3b73347'::uuid,
    '2d4a097a-0a5c-47d7-8115-b537218142fd'::uuid,
    'c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid,
    '91217759-bd5e-44fa-9348-0ee5b68e8abc'::uuid,
    '7758efc8-6cf4-4c4f-9209-3c704813c56c'::uuid,
    'e7e367d6-845a-490d-96b4-994dd67f3703'::uuid,
    '85d3d8e0-421e-46d9-971d-cfda24713402'::uuid,
    'e71177c7-76e4-4009-a14a-c8d7d0532550'::uuid,
    '4c871f98-6a30-4cbb-a89a-5751d829471b'::uuid,
    '4781af01-ab18-4e81-b679-6bca175e8c99'::uuid,
    '7fee07c5-e992-4000-ac07-dcf4b38013fd'::uuid,
    'dd8b30a3-4084-4e6f-a2c0-57f4325bdc44'::uuid,
    '835ef8bb-9433-4044-97bb-5f8966809ac3'::uuid,
    '67e1f882-221c-4a6a-9a82-6312f75a548f'::uuid,
    '65e92560-3823-42b0-88af-45d661801bb1'::uuid,
    '59d28560-4a8a-4727-925e-cd9a19e0b585'::uuid,
    '1491b3f4-2742-40ac-942b-9f20819f854d'::uuid,
    '22c0195f-1719-4858-b653-0af0b3128f38'::uuid,
    '0fd7c6a9-4b79-4f61-86f5-6a2e349deae1'::uuid,
    '36d9ccda-546a-4549-8c74-72daa15140bf'::uuid
  ];
  v_catalog_ids := ARRAY[
    '36d1559f-b95e-4f3d-9838-840bce0722ed'::uuid,
    'e0d058bb-43ac-4d16-900f-1de8d9566324'::uuid,
    'c16dbdff-941c-4c7e-a89f-3a2fdc375a69'::uuid,
    '615e9ed3-8e0f-4859-8826-8de5e539d9ad'::uuid,
    'ed1c5d1b-1d73-4a15-9a5b-889b8c4874c7'::uuid,
    'f7976d16-1afa-47ee-ab04-9dd0345686c2'::uuid,
    '7b4e72af-d82d-4bc9-aa59-352feb7a3d00'::uuid,
    '41e18ccf-ea77-4f11-882d-27492d4441ba'::uuid,
    'bfe45c4b-d562-4384-af5f-ed3571ec24d5'::uuid,
    '872223d2-63fd-4f66-a348-0a85fb1f0b45'::uuid,
    '501fef0d-8c03-4cfe-bed9-44d0ab8bcc3f'::uuid,
    '44f76f14-0d1e-4288-83aa-3eed329a2671'::uuid,
    '0a178992-7c5f-448c-a512-751df33de955'::uuid,
    'b46554fd-7d47-42ae-9fb2-551ce0aa594c'::uuid,
    '28aa89db-ace5-4233-9581-31a13038a4f3'::uuid,
    '5863fee5-1a9d-4c78-beca-3d4b0d677641'::uuid,
    '8a2ceea6-6725-4880-adff-ed4813651ad9'::uuid,
    '0175d554-ff5b-4a6b-a0b8-c595cb5c30fa'::uuid,
    '218b1a1c-0976-4c61-addd-b7c9509d80e4'::uuid,
    'ab556daa-7366-45ce-a0be-4f19ab1e7b43'::uuid,
    '30bdb92c-2be3-4652-a471-f77c5bfb19de'::uuid,
    '2179484b-9923-4f62-bfb2-5cbeccf5edb5'::uuid,
    'afa892b6-c766-4fb0-9a0f-de7785b2791b'::uuid,
    '799f409d-762b-4e59-aa08-6c4553e5b4a9'::uuid,
    '7789ea55-5adf-4ff7-bbc7-dc2076189ab3'::uuid,
    'e6db9020-c479-4623-bff2-48f1bac28fb4'::uuid,
    '6a43296b-4950-4805-b41e-3e64f5ad24dc'::uuid,
    '2f17ec34-c1ad-4c42-b142-63b51f252392'::uuid,
    '98c45426-63e7-4649-9e83-8d5a5625f17c'::uuid,
    'a9d3e80e-8fd5-44ed-bbfc-86cdd1200421'::uuid,
    '0cbefa24-b862-4a2f-9307-a94a88aca254'::uuid,
    'a4a8c008-57d3-4351-b020-2b5f97a1b20a'::uuid,
    'ed047fe4-4a0c-443f-9159-b1be0318f779'::uuid,
    '3c4114ef-1dc1-482e-a67b-44fae3a2c2db'::uuid,
    '1814f7c6-85da-4091-bb17-47604937e3bd'::uuid,
    'da7bf5d8-157a-4cb0-9d11-e80361352757'::uuid,
    '3eb30ecb-23dc-4d63-a85f-d54576f8d4fa'::uuid,
    '5d5ddf0a-a0b6-4fbc-a76d-a1276960d467'::uuid,
    '8f17f61d-ed0e-4cf9-89bf-57f517304a3d'::uuid,
    'b87f8767-ba27-4d36-8ed7-7b3a2aaecc60'::uuid,
    'fe6800b7-1488-4c25-b2bc-c79b78b7ad62'::uuid,
    'db99e086-4a00-43bc-affc-2a25dbe1b648'::uuid,
    '6a19c356-0560-4296-beac-34b609690a44'::uuid,
    'c060a7a2-1c90-47c1-b179-e49de27b88a6'::uuid,
    '082eb4f4-9129-4ad6-9bf6-223f608eb9f2'::uuid,
    '62718fa4-8021-453d-b13c-076b9285e616'::uuid,
    'a05c67c5-73a3-411a-8c2e-49c0975f9cb6'::uuid,
    'a18932fb-3631-4fb2-ba8e-d8cdc8b2628d'::uuid
  ];
  v_cand_ids := ARRAY[
    '2c115735-1623-4194-b9ec-c422074dd52e'::uuid,
    'd196dcd5-bf0b-48e3-a039-42e96fe5eb54'::uuid,
    '96707556-53df-458c-8a9d-47308f0983d4'::uuid,
    '000b3f54-7069-4fa0-9c8a-7622f218f807'::uuid,
    '0e7aac32-232e-463e-b6ab-39d2b885a59d'::uuid,
    'a115086b-0dd2-4bad-afbf-e38cf449fa43'::uuid,
    '29e65ed1-63bd-4950-927e-2120ee0e7964'::uuid,
    '236814ee-9a69-4e72-894a-386caf813407'::uuid,
    '6df4e1ff-1b90-41ad-8627-d4aafe924935'::uuid,
    'fe450f3e-7de0-4357-8b5a-d7caa41a78aa'::uuid,
    '8b11c26e-ab5a-4b72-bf53-f10c75f59d19'::uuid,
    'dbabd0b1-4632-44b8-be03-17b48b52a3fc'::uuid,
    'e15ba1ce-497a-4a39-88b5-a5e25a6f3355'::uuid,
    '4ed7e74f-634f-493d-a480-092888575a84'::uuid,
    '3d0192fd-9df7-4538-ae01-e77baf500d20'::uuid,
    '01b83c70-8a99-41bf-b504-ae17cb1ee0ac'::uuid,
    'da2f0fa4-e9a1-4c0c-9f27-c1176eaf3113'::uuid,
    '7c72150b-05ec-48c9-a44c-849160965842'::uuid,
    '05844c28-493e-46f9-87b2-07124c5012f2'::uuid,
    '9e414d2c-4653-4210-9753-ea4afae33d10'::uuid,
    'd05bcd57-cd5e-4f57-9928-66fca70ae137'::uuid,
    '0c325df0-d5f7-414f-aad0-7283648866be'::uuid,
    '40ff1dcc-1ee1-40c8-89c7-e156370dc259'::uuid,
    '5192356d-f57f-4547-aaac-1b253bd8dc7e'::uuid,
    'f9a593b2-56af-449c-a2c8-4e84a468a6ad'::uuid,
    'a2ec2df5-d9e3-4389-a53e-adc9714be31f'::uuid,
    '1ff1dc5f-ab36-44c9-a44c-75e5e1c1d688'::uuid,
    '69649676-4228-4d1f-95b1-bf83106f875a'::uuid,
    '346fb469-3b94-48dd-87fe-c1dd2e9db6a6'::uuid,
    '34df1592-0c3f-4b81-a6bd-84ae45ebe55f'::uuid,
    '6ad7c853-369c-4cb7-ba41-78a713fbb671'::uuid,
    'a65c6132-085a-4914-ba4c-bb1a9b76ecd7'::uuid,
    '7b40975e-a32b-4a84-b445-1c62c9990295'::uuid,
    'd60144c9-58ae-471c-a0e1-7633785c2fe4'::uuid,
    '3a7d6a0b-5966-4d1b-a74b-fd83eac9e3d6'::uuid,
    'b2768726-c20d-4f29-9608-24b3c9d9ba22'::uuid,
    'a44a414e-b564-41b1-b917-b8793cf1a9a9'::uuid,
    '5e139474-cea5-4a45-92dc-0e1535215a07'::uuid,
    'f02c647b-c4c7-432d-a656-5bc74e99ed00'::uuid,
    'a338e637-5bc7-41f8-bb70-2708eb639db7'::uuid,
    '2e0461b6-c83a-4b0b-93dd-0aeca206d3eb'::uuid,
    '2a018727-9a4a-494b-a8a2-ab5abec498d7'::uuid,
    'b4f1f6ec-7383-485b-b049-5489a4a7c3a0'::uuid,
    '045d28e0-a971-4c14-862b-f29666ca3def'::uuid,
    '6d2549d1-d354-421b-a48c-a80c7527ad61'::uuid,
    'db086849-2290-421c-a3bd-d71f48d6b7c9'::uuid,
    '647eaeb5-e444-485a-b644-b2ae8701da83'::uuid,
    'a43c29c1-2a71-4868-80bf-8ba5ff733204'::uuid
  ];

  -- ── GLOBAL PRECONDITION ASSERTS ─────────────────────────────────────

  -- P1: 48종 스키마 CANDIDATE + version=1
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = ANY(v_schema_ids)
        AND status = 'CANDIDATE' AND version = 1) <> 48 THEN
    RAISE EXCEPTION 'ABORT: P1 schema CANDIDATE/v=1 count <> 48. STOP.';
  END IF;

  -- P2: 245 필드 CANDIDATE/CANDIDATE_ONLY
  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = ANY(v_schema_ids)
        AND status = 'CANDIDATE'
        AND required_status = 'CANDIDATE_ONLY') <> 245 THEN
    RAISE EXCEPTION 'ABORT: P2 field CANDIDATE/CANDIDATE_ONLY count <> 245. STOP.';
  END IF;

  -- P3: 총 필드 수 = 245 (예상 외 필드 차단)
  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = ANY(v_schema_ids)) <> 245 THEN
    RAISE EXCEPTION 'ABORT: P3 total field count <> 245. STOP.';
  END IF;

  -- P4: 기존 운영 문서 참조 없음
  IF (SELECT count(*) FROM runtime_document_data
      WHERE form_schema_id = ANY(v_schema_ids)) <> 0 THEN
    RAISE EXCEPTION 'ABORT: P4 runtime_document_data references exist. STOP.';
  END IF;

  -- P5: bridge 참조 없음
  IF (SELECT count(*) FROM runtime_inspection_bridge
      WHERE runtime_form_schema_id = ANY(v_schema_ids)) <> 0 THEN
    RAISE EXCEPTION 'ABORT: P5 runtime_inspection_bridge references exist. STOP.';
  END IF;

  -- P6: 기존 승격 감사기록 없음 (중복 실행 차단)
  IF (SELECT count(*) FROM runtime_form_audit_log
      WHERE source_table = 'runtime_form_schema'
        AND source_id = ANY(v_schema_ids)
        AND action = 'PROMOTE_TO_RUNTIME_USE') <> 0 THEN
    RAISE EXCEPTION 'ABORT: P6 promotion audit already exists. STOP.';
  END IF;

  -- P7: catalog_document_id 기준 기존 APPROVED 스키마 없음
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE catalog_document_id = ANY(v_catalog_ids)
        AND status = 'APPROVED_FOR_RUNTIME_USE') <> 0 THEN
    RAISE EXCEPTION 'ABORT: P7 existing APPROVED_FOR_RUNTIME_USE. STOP.';
  END IF;

  -- P8: per-doc (schema_id, catalog_document_id, schema_candidate_id) exact triplet 48건
  IF (SELECT count(*) FROM runtime_form_schema rfs
      JOIN (VALUES
      ('2c62ce24-baea-4d39-a5dc-ce030648d0d7'::uuid, '36d1559f-b95e-4f3d-9838-840bce0722ed'::uuid, '2c115735-1623-4194-b9ec-c422074dd52e'::uuid),
      ('f9de138a-138d-4202-a7be-4bb7158d92c4'::uuid, 'e0d058bb-43ac-4d16-900f-1de8d9566324'::uuid, 'd196dcd5-bf0b-48e3-a039-42e96fe5eb54'::uuid),
      ('ecc54b1d-7f3e-4556-9134-94ad4dd3cd97'::uuid, 'c16dbdff-941c-4c7e-a89f-3a2fdc375a69'::uuid, '96707556-53df-458c-8a9d-47308f0983d4'::uuid),
      ('dcea0582-d5eb-4671-a258-b75d142e83f3'::uuid, '615e9ed3-8e0f-4859-8826-8de5e539d9ad'::uuid, '000b3f54-7069-4fa0-9c8a-7622f218f807'::uuid),
      ('ee1e9dde-2b7f-4278-9cf2-a64476d8a014'::uuid, 'ed1c5d1b-1d73-4a15-9a5b-889b8c4874c7'::uuid, '0e7aac32-232e-463e-b6ab-39d2b885a59d'::uuid),
      ('331ab855-e930-434b-9f8c-25f8a6c8988a'::uuid, 'f7976d16-1afa-47ee-ab04-9dd0345686c2'::uuid, 'a115086b-0dd2-4bad-afbf-e38cf449fa43'::uuid),
      ('910ef261-3f3b-46a7-9f0b-d6ced4a92376'::uuid, '7b4e72af-d82d-4bc9-aa59-352feb7a3d00'::uuid, '29e65ed1-63bd-4950-927e-2120ee0e7964'::uuid),
      ('0204725e-c5e8-4cdb-b9a8-ddf8a423ed00'::uuid, '41e18ccf-ea77-4f11-882d-27492d4441ba'::uuid, '236814ee-9a69-4e72-894a-386caf813407'::uuid),
      ('3b246692-a2d2-4b83-978b-11754dfca0ce'::uuid, 'bfe45c4b-d562-4384-af5f-ed3571ec24d5'::uuid, '6df4e1ff-1b90-41ad-8627-d4aafe924935'::uuid),
      ('3214f248-9fce-4169-a243-a4e43f3e81e5'::uuid, '872223d2-63fd-4f66-a348-0a85fb1f0b45'::uuid, 'fe450f3e-7de0-4357-8b5a-d7caa41a78aa'::uuid),
      ('9c34459f-5b82-40f7-a03a-a532cfdefdd4'::uuid, '501fef0d-8c03-4cfe-bed9-44d0ab8bcc3f'::uuid, '8b11c26e-ab5a-4b72-bf53-f10c75f59d19'::uuid),
      ('5d5a2b58-80e3-4924-933a-006b89267d26'::uuid, '44f76f14-0d1e-4288-83aa-3eed329a2671'::uuid, 'dbabd0b1-4632-44b8-be03-17b48b52a3fc'::uuid),
      ('99905f16-9b1e-4b79-8e15-ef2d2d56b5e0'::uuid, '0a178992-7c5f-448c-a512-751df33de955'::uuid, 'e15ba1ce-497a-4a39-88b5-a5e25a6f3355'::uuid),
      ('b3071484-1547-4f1e-8b5f-12ed391f5519'::uuid, 'b46554fd-7d47-42ae-9fb2-551ce0aa594c'::uuid, '4ed7e74f-634f-493d-a480-092888575a84'::uuid),
      ('98b60eca-5a11-4fc5-a386-c62fb67277a4'::uuid, '28aa89db-ace5-4233-9581-31a13038a4f3'::uuid, '3d0192fd-9df7-4538-ae01-e77baf500d20'::uuid),
      ('4bf3ed32-a9b3-4fdc-ba1a-dd9e5a6de27d'::uuid, '5863fee5-1a9d-4c78-beca-3d4b0d677641'::uuid, '01b83c70-8a99-41bf-b504-ae17cb1ee0ac'::uuid),
      ('48b04ae3-4c0e-4f78-949c-fc8a24421c50'::uuid, '8a2ceea6-6725-4880-adff-ed4813651ad9'::uuid, 'da2f0fa4-e9a1-4c0c-9f27-c1176eaf3113'::uuid),
      ('769d94ff-476e-4d2a-9310-acdff418bda0'::uuid, '0175d554-ff5b-4a6b-a0b8-c595cb5c30fa'::uuid, '7c72150b-05ec-48c9-a44c-849160965842'::uuid),
      ('328bcdb1-45cf-401c-99ad-76e131a39be5'::uuid, '218b1a1c-0976-4c61-addd-b7c9509d80e4'::uuid, '05844c28-493e-46f9-87b2-07124c5012f2'::uuid),
      ('5e89caa2-da79-4d20-86f1-cdfe138b5ac7'::uuid, 'ab556daa-7366-45ce-a0be-4f19ab1e7b43'::uuid, '9e414d2c-4653-4210-9753-ea4afae33d10'::uuid),
      ('3ce74995-9679-4cf0-acde-f46fbd940454'::uuid, '30bdb92c-2be3-4652-a471-f77c5bfb19de'::uuid, 'd05bcd57-cd5e-4f57-9928-66fca70ae137'::uuid),
      ('4f783679-c8ab-42f1-98c5-ce429cd38b19'::uuid, '2179484b-9923-4f62-bfb2-5cbeccf5edb5'::uuid, '0c325df0-d5f7-414f-aad0-7283648866be'::uuid),
      ('3ac8db99-aede-460f-b2d5-daa969b29b6b'::uuid, 'afa892b6-c766-4fb0-9a0f-de7785b2791b'::uuid, '40ff1dcc-1ee1-40c8-89c7-e156370dc259'::uuid),
      ('c959e7e9-942b-449a-aead-904996476687'::uuid, '799f409d-762b-4e59-aa08-6c4553e5b4a9'::uuid, '5192356d-f57f-4547-aaac-1b253bd8dc7e'::uuid),
      ('117958e3-f936-4d06-b869-273001ea023d'::uuid, '7789ea55-5adf-4ff7-bbc7-dc2076189ab3'::uuid, 'f9a593b2-56af-449c-a2c8-4e84a468a6ad'::uuid),
      ('b920ccaf-191a-492c-b43f-8c8f785c632c'::uuid, 'e6db9020-c479-4623-bff2-48f1bac28fb4'::uuid, 'a2ec2df5-d9e3-4389-a53e-adc9714be31f'::uuid),
      ('eddf1605-7b4f-469f-947d-a4380ba6a8cc'::uuid, '6a43296b-4950-4805-b41e-3e64f5ad24dc'::uuid, '1ff1dc5f-ab36-44c9-a44c-75e5e1c1d688'::uuid),
      ('8e1aea7d-1220-4352-bfd0-569d6c9478eb'::uuid, '2f17ec34-c1ad-4c42-b142-63b51f252392'::uuid, '69649676-4228-4d1f-95b1-bf83106f875a'::uuid),
      ('b65478e8-d239-41e0-8959-c4d5b3b73347'::uuid, '98c45426-63e7-4649-9e83-8d5a5625f17c'::uuid, '346fb469-3b94-48dd-87fe-c1dd2e9db6a6'::uuid),
      ('2d4a097a-0a5c-47d7-8115-b537218142fd'::uuid, 'a9d3e80e-8fd5-44ed-bbfc-86cdd1200421'::uuid, '34df1592-0c3f-4b81-a6bd-84ae45ebe55f'::uuid),
      ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, '0cbefa24-b862-4a2f-9307-a94a88aca254'::uuid, '6ad7c853-369c-4cb7-ba41-78a713fbb671'::uuid),
      ('91217759-bd5e-44fa-9348-0ee5b68e8abc'::uuid, 'a4a8c008-57d3-4351-b020-2b5f97a1b20a'::uuid, 'a65c6132-085a-4914-ba4c-bb1a9b76ecd7'::uuid),
      ('7758efc8-6cf4-4c4f-9209-3c704813c56c'::uuid, 'ed047fe4-4a0c-443f-9159-b1be0318f779'::uuid, '7b40975e-a32b-4a84-b445-1c62c9990295'::uuid),
      ('e7e367d6-845a-490d-96b4-994dd67f3703'::uuid, '3c4114ef-1dc1-482e-a67b-44fae3a2c2db'::uuid, 'd60144c9-58ae-471c-a0e1-7633785c2fe4'::uuid),
      ('85d3d8e0-421e-46d9-971d-cfda24713402'::uuid, '1814f7c6-85da-4091-bb17-47604937e3bd'::uuid, '3a7d6a0b-5966-4d1b-a74b-fd83eac9e3d6'::uuid),
      ('e71177c7-76e4-4009-a14a-c8d7d0532550'::uuid, 'da7bf5d8-157a-4cb0-9d11-e80361352757'::uuid, 'b2768726-c20d-4f29-9608-24b3c9d9ba22'::uuid),
      ('4c871f98-6a30-4cbb-a89a-5751d829471b'::uuid, '3eb30ecb-23dc-4d63-a85f-d54576f8d4fa'::uuid, 'a44a414e-b564-41b1-b917-b8793cf1a9a9'::uuid),
      ('4781af01-ab18-4e81-b679-6bca175e8c99'::uuid, '5d5ddf0a-a0b6-4fbc-a76d-a1276960d467'::uuid, '5e139474-cea5-4a45-92dc-0e1535215a07'::uuid),
      ('7fee07c5-e992-4000-ac07-dcf4b38013fd'::uuid, '8f17f61d-ed0e-4cf9-89bf-57f517304a3d'::uuid, 'f02c647b-c4c7-432d-a656-5bc74e99ed00'::uuid),
      ('dd8b30a3-4084-4e6f-a2c0-57f4325bdc44'::uuid, 'b87f8767-ba27-4d36-8ed7-7b3a2aaecc60'::uuid, 'a338e637-5bc7-41f8-bb70-2708eb639db7'::uuid),
      ('835ef8bb-9433-4044-97bb-5f8966809ac3'::uuid, 'fe6800b7-1488-4c25-b2bc-c79b78b7ad62'::uuid, '2e0461b6-c83a-4b0b-93dd-0aeca206d3eb'::uuid),
      ('67e1f882-221c-4a6a-9a82-6312f75a548f'::uuid, 'db99e086-4a00-43bc-affc-2a25dbe1b648'::uuid, '2a018727-9a4a-494b-a8a2-ab5abec498d7'::uuid),
      ('65e92560-3823-42b0-88af-45d661801bb1'::uuid, '6a19c356-0560-4296-beac-34b609690a44'::uuid, 'b4f1f6ec-7383-485b-b049-5489a4a7c3a0'::uuid),
      ('59d28560-4a8a-4727-925e-cd9a19e0b585'::uuid, 'c060a7a2-1c90-47c1-b179-e49de27b88a6'::uuid, '045d28e0-a971-4c14-862b-f29666ca3def'::uuid),
      ('1491b3f4-2742-40ac-942b-9f20819f854d'::uuid, '082eb4f4-9129-4ad6-9bf6-223f608eb9f2'::uuid, '6d2549d1-d354-421b-a48c-a80c7527ad61'::uuid),
      ('22c0195f-1719-4858-b653-0af0b3128f38'::uuid, '62718fa4-8021-453d-b13c-076b9285e616'::uuid, 'db086849-2290-421c-a3bd-d71f48d6b7c9'::uuid),
      ('0fd7c6a9-4b79-4f61-86f5-6a2e349deae1'::uuid, 'a05c67c5-73a3-411a-8c2e-49c0975f9cb6'::uuid, '647eaeb5-e444-485a-b644-b2ae8701da83'::uuid),
      ('36d9ccda-546a-4549-8c74-72daa15140bf'::uuid, 'a18932fb-3631-4fb2-ba8e-d8cdc8b2628d'::uuid, 'a43c29c1-2a71-4868-80bf-8ba5ff733204'::uuid)
      ) AS t(sid, cid, did)
        ON rfs.id = t.sid
       AND rfs.catalog_document_id = t.cid
       AND rfs.schema_candidate_id = t.did) <> 48 THEN
    RAISE EXCEPTION 'ABORT: P8 exact provenance triplet count <> 48. STOP.';
  END IF;

  -- G1: has_legal_form = FALSE (48종 전부)
  IF (SELECT count(*) FROM document_forms
      WHERE id = ANY(v_catalog_ids) AND has_legal_form = FALSE) <> 48 THEN
    RAISE EXCEPTION 'ABORT: G1 has_legal_form != FALSE for some docs. STOP.';
  END IF;

  -- G2: 증빙 필드 없음
  IF (SELECT count(*) FROM runtime_evidence_field
      WHERE form_schema_id = ANY(v_schema_ids)) <> 0 THEN
    RAISE EXCEPTION 'ABORT: G2 evidence_fields present. STOP.';
  END IF;

  -- G4: document_schema_candidate 전부 CANDIDATE
  IF (SELECT count(*) FROM document_schema_candidate
      WHERE id = ANY(v_cand_ids) AND status = 'CANDIDATE') <> 48 THEN
    RAISE EXCEPTION 'ABORT: G4 schema_candidate not all CANDIDATE. STOP.';
  END IF;

  -- ── PER-DOCUMENT FIELD COUNT ASSERT ──────────────────────────────────
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '2c62ce24-baea-4d39-a5dc-ce030648d0d7') <> 3 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-BLD-023 expected 3. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'f9de138a-138d-4202-a7be-4bb7158d92c4') <> 3 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-BLD-024 expected 3. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'ecc54b1d-7f3e-4556-9134-94ad4dd3cd97') <> 3 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-BLD-039 expected 3. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'dcea0582-d5eb-4671-a258-b75d142e83f3') <> 4 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-BLD-041 expected 4. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'ee1e9dde-2b7f-4278-9cf2-a64476d8a014') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-BLD-042 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '331ab855-e930-434b-9f8c-25f8a6c8988a') <> 4 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-BLD-043 expected 4. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '910ef261-3f3b-46a7-9f0b-d6ced4a92376') <> 2 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CHEM-021 expected 2. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '0204725e-c5e8-4cdb-b9a8-ddf8a423ed00') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-004 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '3b246692-a2d2-4b83-978b-11754dfca0ce') <> 6 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-008 expected 6. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '3214f248-9fce-4169-a243-a4e43f3e81e5') <> 6 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-010 expected 6. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '9c34459f-5b82-40f7-a03a-a532cfdefdd4') <> 6 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-015 expected 6. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '5d5a2b58-80e3-4924-933a-006b89267d26') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-021 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '99905f16-9b1e-4b79-8e15-ef2d2d56b5e0') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-022 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'b3071484-1547-4f1e-8b5f-12ed391f5519') <> 6 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-023 expected 6. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '98b60eca-5a11-4fc5-a386-c62fb67277a4') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-024 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '4bf3ed32-a9b3-4fdc-ba1a-dd9e5a6de27d') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-025 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '48b04ae3-4c0e-4f78-949c-fc8a24421c50') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-027 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '769d94ff-476e-4d2a-9310-acdff418bda0') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-029 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '328bcdb1-45cf-401c-99ad-76e131a39be5') <> 6 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-031 expected 6. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '5e89caa2-da79-4d20-86f1-cdfe138b5ac7') <> 6 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-033 expected 6. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '3ce74995-9679-4cf0-acde-f46fbd940454') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-034 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '4f783679-c8ab-42f1-98c5-ce429cd38b19') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-035 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '3ac8db99-aede-460f-b2d5-daa969b29b6b') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-036 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'c959e7e9-942b-449a-aead-904996476687') <> 6 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-038 expected 6. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '117958e3-f936-4d06-b869-273001ea023d') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-039 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'b920ccaf-191a-492c-b43f-8c8f785c632c') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-040 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'eddf1605-7b4f-469f-947d-a4380ba6a8cc') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-042 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '8e1aea7d-1220-4352-bfd0-569d6c9478eb') <> 4 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-045 expected 4. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'b65478e8-d239-41e0-8959-c4d5b3b73347') <> 6 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-CON-LAW-013 expected 6. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '2d4a097a-0a5c-47d7-8115-b537218142fd') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-001 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'c0e894c4-f8bc-4f0f-8820-bf633ce81f86') <> 16 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-012 expected 16. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '91217759-bd5e-44fa-9348-0ee5b68e8abc') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-016 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '7758efc8-6cf4-4c4f-9209-3c704813c56c') <> 4 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-037 expected 4. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'e7e367d6-845a-490d-96b4-994dd67f3703') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-040 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '85d3d8e0-421e-46d9-971d-cfda24713402') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-043 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'e71177c7-76e4-4009-a14a-c8d7d0532550') <> 6 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-050 expected 6. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '4c871f98-6a30-4cbb-a89a-5751d829471b') <> 6 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-051 expected 6. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '4781af01-ab18-4e81-b679-6bca175e8c99') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-054 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '7fee07c5-e992-4000-ac07-dcf4b38013fd') <> 4 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-068 expected 4. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = 'dd8b30a3-4084-4e6f-a2c0-57f4325bdc44') <> 4 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-069 expected 4. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '835ef8bb-9433-4044-97bb-5f8966809ac3') <> 4 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-075 expected 4. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '67e1f882-221c-4a6a-9a82-6312f75a548f') <> 4 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-OSH-076 expected 4. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '65e92560-3823-42b0-88af-45d661801bb1') <> 7 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-SERA-001 expected 7. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '59d28560-4a8a-4727-925e-cd9a19e0b585') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-SERA-004 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '1491b3f4-2742-40ac-942b-9f20819f854d') <> 3 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-SERA-006 expected 3. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '22c0195f-1719-4858-b653-0af0b3128f38') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-SERA-007 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '0fd7c6a9-4b79-4f61-86f5-6a2e349deae1') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-SERA-009 expected 5. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = '36d9ccda-546a-4549-8c74-72daa15140bf') <> 6 THEN
    RAISE EXCEPTION 'ABORT: field count mismatch for DOC-SERA-012 expected 6. STOP.';
  END IF;

  -- ── BEFORE STATE SNAPSHOT ──────────────────────────────────────────────
  SELECT jsonb_object_agg(
    rfs.id::text,
    jsonb_build_object(
      'schema_status',  rfs.status,
      'schema_version', rfs.version,
      'doc_id',         df.doc_id,
      'fields', (
        SELECT jsonb_agg(jsonb_build_object(
          'field_key',       rf2.field_key,
          'status',          rf2.status,
          'required_status', rf2.required_status
        ) ORDER BY rf2.field_key)
        FROM runtime_field rf2
        WHERE rf2.form_schema_id = rfs.id
      )
    )
  )
  INTO v_before_all
  FROM runtime_form_schema rfs
  JOIN document_forms df ON df.id = rfs.catalog_document_id
  WHERE rfs.id = ANY(v_schema_ids);

  -- ── [1] runtime_field ×245 UPDATE ─────────────────────────────────────
  -- CANDIDATE/CANDIDATE_ONLY → APPROVED_BY_HUMAN + REQUIRED_BY_HUMAN(186) or NOT_REQUIRED(59)
  -- 근거: document_forms.required_fields.is_mandatory (CSV 정본 + DB 재확인)
  UPDATE runtime_field AS rf
  SET status = 'APPROVED_BY_HUMAN',
      required_status = v.req_status
  FROM (VALUES
    ('2c62ce24-baea-4d39-a5dc-ce030648d0d7'::uuid, 'inspection_findings', 'REQUIRED_BY_HUMAN'),
    ('2c62ce24-baea-4d39-a5dc-ce030648d0d7'::uuid, 'action_plan', 'REQUIRED_BY_HUMAN'),
    ('2c62ce24-baea-4d39-a5dc-ce030648d0d7'::uuid, 'planned_date', 'REQUIRED_BY_HUMAN'),
    ('f9de138a-138d-4202-a7be-4bb7158d92c4'::uuid, 'completion_detail', 'REQUIRED_BY_HUMAN'),
    ('f9de138a-138d-4202-a7be-4bb7158d92c4'::uuid, 'completion_date', 'REQUIRED_BY_HUMAN'),
    ('f9de138a-138d-4202-a7be-4bb7158d92c4'::uuid, 'inspector', 'REQUIRED_BY_HUMAN'),
    ('ecc54b1d-7f3e-4556-9134-94ad4dd3cd97'::uuid, 'order_details', 'REQUIRED_BY_HUMAN'),
    ('ecc54b1d-7f3e-4556-9134-94ad4dd3cd97'::uuid, 'implementation_plan', 'REQUIRED_BY_HUMAN'),
    ('ecc54b1d-7f3e-4556-9134-94ad4dd3cd97'::uuid, 'planned_completion_date', 'REQUIRED_BY_HUMAN'),
    ('dcea0582-d5eb-4671-a258-b75d142e83f3'::uuid, 'facility_overview', 'REQUIRED_BY_HUMAN'),
    ('dcea0582-d5eb-4671-a258-b75d142e83f3'::uuid, 'inspection_diagnosis_plan', 'REQUIRED_BY_HUMAN'),
    ('dcea0582-d5eb-4671-a258-b75d142e83f3'::uuid, 'repair_reinforcement_plan', 'REQUIRED_BY_HUMAN'),
    ('dcea0582-d5eb-4671-a258-b75d142e83f3'::uuid, 'maintenance_budget_personnel', 'REQUIRED_BY_HUMAN'),
    ('ee1e9dde-2b7f-4278-9cf2-a64476d8a014'::uuid, 'facility_overview', 'REQUIRED_BY_HUMAN'),
    ('ee1e9dde-2b7f-4278-9cf2-a64476d8a014'::uuid, 'performance_evaluation_agency', 'REQUIRED_BY_HUMAN'),
    ('ee1e9dde-2b7f-4278-9cf2-a64476d8a014'::uuid, 'performance_evaluation_result', 'REQUIRED_BY_HUMAN'),
    ('ee1e9dde-2b7f-4278-9cf2-a64476d8a014'::uuid, 'performance_grade', 'REQUIRED_BY_HUMAN'),
    ('ee1e9dde-2b7f-4278-9cf2-a64476d8a014'::uuid, 'maintenance_needs', 'REQUIRED_BY_HUMAN'),
    ('331ab855-e930-434b-9f8c-25f8a6c8988a'::uuid, 'repair_target_facility', 'REQUIRED_BY_HUMAN'),
    ('331ab855-e930-434b-9f8c-25f8a6c8988a'::uuid, 'defect_damage_details', 'REQUIRED_BY_HUMAN'),
    ('331ab855-e930-434b-9f8c-25f8a6c8988a'::uuid, 'repair_reinforcement_actions', 'REQUIRED_BY_HUMAN'),
    ('331ab855-e930-434b-9f8c-25f8a6c8988a'::uuid, 'completion_date', 'REQUIRED_BY_HUMAN'),
    ('910ef261-3f3b-46a7-9f0b-d6ced4a92376'::uuid, 'workplace_information', 'REQUIRED_BY_HUMAN'),
    ('910ef261-3f3b-46a7-9f0b-d6ced4a92376'::uuid, 'annual_handling_quantity', 'REQUIRED_BY_HUMAN'),
    ('0204725e-c5e8-4cdb-b9a8-ddf8a423ed00'::uuid, 'project_name_work_type', 'REQUIRED_BY_HUMAN'),
    ('0204725e-c5e8-4cdb-b9a8-ddf8a423ed00'::uuid, 'construction_scope_method', 'NOT_REQUIRED'),
    ('0204725e-c5e8-4cdb-b9a8-ddf8a423ed00'::uuid, 'construction_sequence_schedule', 'NOT_REQUIRED'),
    ('0204725e-c5e8-4cdb-b9a8-ddf8a423ed00'::uuid, 'labor_equipment_material_plan', 'NOT_REQUIRED'),
    ('0204725e-c5e8-4cdb-b9a8-ddf8a423ed00'::uuid, 'quality_safety_management_plan', 'NOT_REQUIRED'),
    ('3b246692-a2d2-4b83-978b-11754dfca0ce'::uuid, 'work_name_location', 'REQUIRED_BY_HUMAN'),
    ('3b246692-a2d2-4b83-978b-11754dfca0ce'::uuid, 'site_ground_strata_survey_result', 'REQUIRED_BY_HUMAN'),
    ('3b246692-a2d2-4b83-978b-11754dfca0ce'::uuid, 'work_plan_sequence', 'REQUIRED_BY_HUMAN'),
    ('3b246692-a2d2-4b83-978b-11754dfca0ce'::uuid, 'equipment_and_movement_route', 'REQUIRED_BY_HUMAN'),
    ('3b246692-a2d2-4b83-978b-11754dfca0ce'::uuid, 'work_supervisor_assignment', 'REQUIRED_BY_HUMAN'),
    ('3b246692-a2d2-4b83-978b-11754dfca0ce'::uuid, 'hazards_and_protective_measures', 'REQUIRED_BY_HUMAN'),
    ('3214f248-9fce-4169-a243-a4e43f3e81e5'::uuid, 'contracted_work_name_location', 'REQUIRED_BY_HUMAN'),
    ('3214f248-9fce-4169-a243-a4e43f3e81e5'::uuid, 'contractor_safety_health_measures', 'REQUIRED_BY_HUMAN'),
    ('3214f248-9fce-4169-a243-a4e43f3e81e5'::uuid, 'subcontractor_worker_hazards', 'REQUIRED_BY_HUMAN'),
    ('3214f248-9fce-4169-a243-a4e43f3e81e5'::uuid, 'sanitary_facility_cooperation', 'REQUIRED_BY_HUMAN'),
    ('3214f248-9fce-4169-a243-a4e43f3e81e5'::uuid, 'workplace_patrol_inspection_plan', 'REQUIRED_BY_HUMAN'),
    ('3214f248-9fce-4169-a243-a4e43f3e81e5'::uuid, 'subcontractor_safety_training_check', 'REQUIRED_BY_HUMAN'),
    ('9c34459f-5b82-40f7-a03a-a532cfdefdd4'::uuid, 'excavation_location_depth', 'REQUIRED_BY_HUMAN'),
    ('9c34459f-5b82-40f7-a03a-a532cfdefdd4'::uuid, 'ground_strata_condition_survey', 'REQUIRED_BY_HUMAN'),
    ('9c34459f-5b82-40f7-a03a-a532cfdefdd4'::uuid, 'excavation_face_height_slope', 'REQUIRED_BY_HUMAN'),
    ('9c34459f-5b82-40f7-a03a-a532cfdefdd4'::uuid, 'collapse_prevention_measures', 'REQUIRED_BY_HUMAN'),
    ('9c34459f-5b82-40f7-a03a-a532cfdefdd4'::uuid, 'earth_retaining_support_status', 'NOT_REQUIRED'),
    ('9c34459f-5b82-40f7-a03a-a532cfdefdd4'::uuid, 'underground_utility_check', 'NOT_REQUIRED'),
    ('5d5a2b58-80e3-4924-933a-006b89267d26'::uuid, 'final_as_built_drawings', 'REQUIRED_BY_HUMAN'),
    ('5d5a2b58-80e3-4924-933a-006b89267d26'::uuid, 'design_change_history', 'REQUIRED_BY_HUMAN'),
    ('5d5a2b58-80e3-4924-933a-006b89267d26'::uuid, 'material_usage_records', 'REQUIRED_BY_HUMAN'),
    ('5d5a2b58-80e3-4924-933a-006b89267d26'::uuid, 'test_and_inspection_results', 'REQUIRED_BY_HUMAN'),
    ('5d5a2b58-80e3-4924-933a-006b89267d26'::uuid, 'maintenance_reference_data', 'REQUIRED_BY_HUMAN'),
    ('99905f16-9b1e-4b79-8e15-ef2d2d56b5e0'::uuid, 'facility_overview', 'REQUIRED_BY_HUMAN'),
    ('99905f16-9b1e-4b79-8e15-ef2d2d56b5e0'::uuid, 'inspection_items_and_frequency', 'REQUIRED_BY_HUMAN'),
    ('99905f16-9b1e-4b79-8e15-ef2d2d56b5e0'::uuid, 'maintenance_methods', 'REQUIRED_BY_HUMAN'),
    ('99905f16-9b1e-4b79-8e15-ef2d2d56b5e0'::uuid, 'emergency_response_procedure', 'NOT_REQUIRED'),
    ('99905f16-9b1e-4b79-8e15-ef2d2d56b5e0'::uuid, 'component_replacement_criteria', 'NOT_REQUIRED'),
    ('b3071484-1547-4f1e-8b5f-12ed391f5519'::uuid, 'excavation_work_name_location', 'REQUIRED_BY_HUMAN'),
    ('b3071484-1547-4f1e-8b5f-12ed391f5519'::uuid, 'pre_survey_record', 'REQUIRED_BY_HUMAN'),
    ('b3071484-1547-4f1e-8b5f-12ed391f5519'::uuid, 'excavation_method_sequence', 'REQUIRED_BY_HUMAN'),
    ('b3071484-1547-4f1e-8b5f-12ed391f5519'::uuid, 'soil_collapse_risk_control', 'REQUIRED_BY_HUMAN'),
    ('b3071484-1547-4f1e-8b5f-12ed391f5519'::uuid, 'equipment_route_signalman', 'REQUIRED_BY_HUMAN'),
    ('b3071484-1547-4f1e-8b5f-12ed391f5519'::uuid, 'post_rain_excavation_face_reinspection', 'NOT_REQUIRED'),
    ('98b60eca-5a11-4fc5-a386-c62fb67277a4'::uuid, 'earth_retaining_location_excavation_depth', 'REQUIRED_BY_HUMAN'),
    ('98b60eca-5a11-4fc5-a386-c62fb67277a4'::uuid, 'ground_strata_survey_result', 'REQUIRED_BY_HUMAN'),
    ('98b60eca-5a11-4fc5-a386-c62fb67277a4'::uuid, 'excavation_face_collapse_prevention', 'REQUIRED_BY_HUMAN'),
    ('98b60eca-5a11-4fc5-a386-c62fb67277a4'::uuid, 'earth_retaining_support_status', 'NOT_REQUIRED'),
    ('98b60eca-5a11-4fc5-a386-c62fb67277a4'::uuid, 'drainage_and_water_inflow_status', 'NOT_REQUIRED'),
    ('4bf3ed32-a9b3-4fdc-ba1a-dd9e5a6de27d'::uuid, 'scaffold_type_and_location', 'REQUIRED_BY_HUMAN'),
    ('4bf3ed32-a9b3-4fdc-ba1a-dd9e5a6de27d'::uuid, 'working_platform_status', 'REQUIRED_BY_HUMAN'),
    ('4bf3ed32-a9b3-4fdc-ba1a-dd9e5a6de27d'::uuid, 'guardrail_installation_status', 'REQUIRED_BY_HUMAN'),
    ('4bf3ed32-a9b3-4fdc-ba1a-dd9e5a6de27d'::uuid, 'wall_tie_support_status', 'NOT_REQUIRED'),
    ('4bf3ed32-a9b3-4fdc-ba1a-dd9e5a6de27d'::uuid, 'overturning_collapse_risk', 'NOT_REQUIRED'),
    ('48b04ae3-4c0e-4f78-949c-fc8a24421c50'::uuid, 'formwork_location_scope', 'REQUIRED_BY_HUMAN'),
    ('48b04ae3-4c0e-4f78-949c-fc8a24421c50'::uuid, 'formwork_assembly_sequence', 'REQUIRED_BY_HUMAN'),
    ('48b04ae3-4c0e-4f78-949c-fc8a24421c50'::uuid, 'formwork_support_status', 'REQUIRED_BY_HUMAN'),
    ('48b04ae3-4c0e-4f78-949c-fc8a24421c50'::uuid, 'deformation_check_during_concrete_pouring', 'NOT_REQUIRED'),
    ('48b04ae3-4c0e-4f78-949c-fc8a24421c50'::uuid, 'dismantling_sequence_falling_object_prevention', 'NOT_REQUIRED'),
    ('769d94ff-476e-4d2a-9310-acdff418bda0'::uuid, 'rebar_delivery_storage_location', 'REQUIRED_BY_HUMAN'),
    ('769d94ff-476e-4d2a-9310-acdff418bda0'::uuid, 'rebar_transport_lifting_method', 'REQUIRED_BY_HUMAN'),
    ('769d94ff-476e-4d2a-9310-acdff418bda0'::uuid, 'falling_overturning_prevention', 'REQUIRED_BY_HUMAN'),
    ('769d94ff-476e-4d2a-9310-acdff418bda0'::uuid, 'cutting_bending_machine_guard_status', 'NOT_REQUIRED'),
    ('769d94ff-476e-4d2a-9310-acdff418bda0'::uuid, 'impalement_protection_cap_status', 'NOT_REQUIRED'),
    ('328bcdb1-45cf-401c-99ad-76e131a39be5'::uuid, 'tower_crane_install_assembly_dismantle_scope', 'REQUIRED_BY_HUMAN'),
    ('328bcdb1-45cf-401c-99ad-76e131a39be5'::uuid, 'site_ground_condition_survey_result', 'REQUIRED_BY_HUMAN'),
    ('328bcdb1-45cf-401c-99ad-76e131a39be5'::uuid, 'install_assembly_dismantle_sequence', 'REQUIRED_BY_HUMAN'),
    ('328bcdb1-45cf-401c-99ad-76e131a39be5'::uuid, 'work_supervisor_assignment', 'REQUIRED_BY_HUMAN'),
    ('328bcdb1-45cf-401c-99ad-76e131a39be5'::uuid, 'outrigger_foundation_support_status', 'NOT_REQUIRED'),
    ('328bcdb1-45cf-401c-99ad-76e131a39be5'::uuid, 'hoist_brake_wire_rope_status', 'NOT_REQUIRED'),
    ('5e89caa2-da79-4d20-86f1-cdfe138b5ac7'::uuid, 'load_type_weight', 'REQUIRED_BY_HUMAN'),
    ('5e89caa2-da79-4d20-86f1-cdfe138b5ac7'::uuid, 'lifting_equipment_and_rated_capacity', 'REQUIRED_BY_HUMAN'),
    ('5e89caa2-da79-4d20-86f1-cdfe138b5ac7'::uuid, 'lifting_method_sequence', 'REQUIRED_BY_HUMAN'),
    ('5e89caa2-da79-4d20-86f1-cdfe138b5ac7'::uuid, 'signalman_and_signal_method', 'REQUIRED_BY_HUMAN'),
    ('5e89caa2-da79-4d20-86f1-cdfe138b5ac7'::uuid, 'rigging_gear_damage_status', 'NOT_REQUIRED'),
    ('5e89caa2-da79-4d20-86f1-cdfe138b5ac7'::uuid, 'lifting_radius_access_control', 'NOT_REQUIRED'),
    ('3ce74995-9679-4cf0-acde-f46fbd940454'::uuid, 'demolition_structure_overview', 'REQUIRED_BY_HUMAN'),
    ('3ce74995-9679-4cf0-acde-f46fbd940454'::uuid, 'demolition_method_sequence', 'REQUIRED_BY_HUMAN'),
    ('3ce74995-9679-4cf0-acde-f46fbd940454'::uuid, 'collapse_fall_prevention', 'REQUIRED_BY_HUMAN'),
    ('3ce74995-9679-4cf0-acde-f46fbd940454'::uuid, 'equipment_usage_plan', 'NOT_REQUIRED'),
    ('3ce74995-9679-4cf0-acde-f46fbd940454'::uuid, 'access_control_plan', 'NOT_REQUIRED'),
    ('4f783679-c8ab-42f1-98c5-ce429cd38b19'::uuid, 'demolition_risk_analysis', 'REQUIRED_BY_HUMAN'),
    ('4f783679-c8ab-42f1-98c5-ce429cd38b19'::uuid, 'safety_management_organization', 'REQUIRED_BY_HUMAN'),
    ('4f783679-c8ab-42f1-98c5-ce429cd38b19'::uuid, 'emergency_response_plan', 'REQUIRED_BY_HUMAN'),
    ('4f783679-c8ab-42f1-98c5-ce429cd38b19'::uuid, 'stop_work_criteria', 'REQUIRED_BY_HUMAN'),
    ('4f783679-c8ab-42f1-98c5-ce429cd38b19'::uuid, 'debris_handling_safety', 'NOT_REQUIRED'),
    ('3ac8db99-aede-460f-b2d5-daa969b29b6b'::uuid, 'welding_location_work_detail', 'REQUIRED_BY_HUMAN'),
    ('3ac8db99-aede-460f-b2d5-daa969b29b6b'::uuid, 'combustible_material_removal_status', 'REQUIRED_BY_HUMAN'),
    ('3ac8db99-aede-460f-b2d5-daa969b29b6b'::uuid, 'spark_scatter_prevention', 'REQUIRED_BY_HUMAN'),
    ('3ac8db99-aede-460f-b2d5-daa969b29b6b'::uuid, 'fire_extinguisher_available', 'NOT_REQUIRED'),
    ('3ac8db99-aede-460f-b2d5-daa969b29b6b'::uuid, 'fire_watch_assigned', 'NOT_REQUIRED'),
    ('c959e7e9-942b-449a-aead-904996476687'::uuid, 'height_work_location_height', 'REQUIRED_BY_HUMAN'),
    ('c959e7e9-942b-449a-aead-904996476687'::uuid, 'fall_prevention_measures', 'REQUIRED_BY_HUMAN'),
    ('c959e7e9-942b-449a-aead-904996476687'::uuid, 'guardrail_work_platform_status', 'REQUIRED_BY_HUMAN'),
    ('c959e7e9-942b-449a-aead-904996476687'::uuid, 'personal_fall_arrest_ppe_status', 'REQUIRED_BY_HUMAN'),
    ('c959e7e9-942b-449a-aead-904996476687'::uuid, 'opening_cover_warning_status', 'NOT_REQUIRED'),
    ('c959e7e9-942b-449a-aead-904996476687'::uuid, 'falling_object_prevention', 'NOT_REQUIRED'),
    ('117958e3-f936-4d06-b869-273001ea023d'::uuid, 'electrical_work_location_scope', 'REQUIRED_BY_HUMAN'),
    ('117958e3-f936-4d06-b869-273001ea023d'::uuid, 'power_shutdown_and_verification_procedure', 'REQUIRED_BY_HUMAN'),
    ('117958e3-f936-4d06-b869-273001ea023d'::uuid, 'grounding_insulation_status', 'REQUIRED_BY_HUMAN'),
    ('117958e3-f936-4d06-b869-273001ea023d'::uuid, 'electrical_ppe_usage', 'NOT_REQUIRED'),
    ('117958e3-f936-4d06-b869-273001ea023d'::uuid, 'live_work_control_measures', 'NOT_REQUIRED'),
    ('b920ccaf-191a-492c-b43f-8c8f785c632c'::uuid, 'equipment_type_specification', 'REQUIRED_BY_HUMAN'),
    ('b920ccaf-191a-492c-b43f-8c8f785c632c'::uuid, 'equipment_usage_purpose', 'REQUIRED_BY_HUMAN'),
    ('b920ccaf-191a-492c-b43f-8c8f785c632c'::uuid, 'operation_method_sequence', 'REQUIRED_BY_HUMAN'),
    ('b920ccaf-191a-492c-b43f-8c8f785c632c'::uuid, 'equipment_inspection_maintenance_status', 'NOT_REQUIRED'),
    ('b920ccaf-191a-492c-b43f-8c8f785c632c'::uuid, 'work_radius_access_control', 'NOT_REQUIRED'),
    ('eddf1605-7b4f-469f-947d-a4380ba6a8cc'::uuid, 'falling_object_risk_location', 'REQUIRED_BY_HUMAN'),
    ('eddf1605-7b4f-469f-947d-a4380ba6a8cc'::uuid, 'falling_object_prevention_facility_plan', 'REQUIRED_BY_HUMAN'),
    ('eddf1605-7b4f-469f-947d-a4380ba6a8cc'::uuid, 'access_control_plan', 'REQUIRED_BY_HUMAN'),
    ('eddf1605-7b4f-469f-947d-a4380ba6a8cc'::uuid, 'safety_net_catch_platform_status', 'NOT_REQUIRED'),
    ('eddf1605-7b4f-469f-947d-a4380ba6a8cc'::uuid, 'material_stacking_binding_status', 'NOT_REQUIRED'),
    ('8e1aea7d-1220-4352-bfd0-569d6c9478eb'::uuid, 'existing_small_safety_plan_information', 'REQUIRED_BY_HUMAN'),
    ('8e1aea7d-1220-4352-bfd0-569d6c9478eb'::uuid, 'change_details', 'REQUIRED_BY_HUMAN'),
    ('8e1aea7d-1220-4352-bfd0-569d6c9478eb'::uuid, 'change_reason', 'REQUIRED_BY_HUMAN'),
    ('8e1aea7d-1220-4352-bfd0-569d6c9478eb'::uuid, 'revised_safety_measures', 'REQUIRED_BY_HUMAN'),
    ('b65478e8-d239-41e0-8959-c4d5b3b73347'::uuid, 'project_and_target', 'REQUIRED_BY_HUMAN'),
    ('b65478e8-d239-41e0-8959-c4d5b3b73347'::uuid, 'inspection_history', 'REQUIRED_BY_HUMAN'),
    ('b65478e8-d239-41e0-8959-c4d5b3b73347'::uuid, 'major_issues', 'REQUIRED_BY_HUMAN'),
    ('b65478e8-d239-41e0-8959-c4d5b3b73347'::uuid, 'action_result', 'REQUIRED_BY_HUMAN'),
    ('b65478e8-d239-41e0-8959-c4d5b3b73347'::uuid, 'residual_risk', 'NOT_REQUIRED'),
    ('b65478e8-d239-41e0-8959-c4d5b3b73347'::uuid, 'overall_opinion', 'REQUIRED_BY_HUMAN'),
    ('2d4a097a-0a5c-47d7-8115-b537218142fd'::uuid, 'safety_organization_duties', 'REQUIRED_BY_HUMAN'),
    ('2d4a097a-0a5c-47d7-8115-b537218142fd'::uuid, 'safety_training_items', 'REQUIRED_BY_HUMAN'),
    ('2d4a097a-0a5c-47d7-8115-b537218142fd'::uuid, 'workplace_safety_standards', 'REQUIRED_BY_HUMAN'),
    ('2d4a097a-0a5c-47d7-8115-b537218142fd'::uuid, 'incident_investigation_reporting', 'REQUIRED_BY_HUMAN'),
    ('2d4a097a-0a5c-47d7-8115-b537218142fd'::uuid, 'risk_assessment_procedure', 'NOT_REQUIRED'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'product_company_information', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'hazards_identification', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'composition_ingredient_information', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'first_aid_measures', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'firefighting_measures', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'accidental_release_measures', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'handling_and_storage', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'exposure_controls_ppe', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'physical_chemical_properties', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'stability_reactivity', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'toxicological_information', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'ecological_information', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'disposal_considerations', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'transport_information', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'regulatory_information', 'REQUIRED_BY_HUMAN'),
    ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, 'other_information', 'REQUIRED_BY_HUMAN'),
    ('91217759-bd5e-44fa-9348-0ee5b68e8abc'::uuid, 'contract_safety_measures', 'REQUIRED_BY_HUMAN'),
    ('91217759-bd5e-44fa-9348-0ee5b68e8abc'::uuid, 'hazard_and_action_result', 'REQUIRED_BY_HUMAN'),
    ('91217759-bd5e-44fa-9348-0ee5b68e8abc'::uuid, 'joint_inspection_status', 'REQUIRED_BY_HUMAN'),
    ('91217759-bd5e-44fa-9348-0ee5b68e8abc'::uuid, 'subcontractor_compliance_status', 'NOT_REQUIRED'),
    ('91217759-bd5e-44fa-9348-0ee5b68e8abc'::uuid, 'corrective_action_completion', 'NOT_REQUIRED'),
    ('7758efc8-6cf4-4c4f-9209-3c704813c56c'::uuid, 'education_done', 'REQUIRED_BY_HUMAN'),
    ('7758efc8-6cf4-4c4f-9209-3c704813c56c'::uuid, 'education_hours', 'REQUIRED_BY_HUMAN'),
    ('7758efc8-6cf4-4c4f-9209-3c704813c56c'::uuid, 'education_content', 'REQUIRED_BY_HUMAN'),
    ('7758efc8-6cf4-4c4f-9209-3c704813c56c'::uuid, 'target', 'NOT_REQUIRED'),
    ('e7e367d6-845a-490d-96b4-994dd67f3703'::uuid, 'implementation_status_vs_plan', 'REQUIRED_BY_HUMAN'),
    ('e7e367d6-845a-490d-96b4-994dd67f3703'::uuid, 'risk_improvement_result', 'REQUIRED_BY_HUMAN'),
    ('e7e367d6-845a-490d-96b4-994dd67f3703'::uuid, 'joint_inspection_result', 'REQUIRED_BY_HUMAN'),
    ('e7e367d6-845a-490d-96b4-994dd67f3703'::uuid, 'subcontractor_guidance_training', 'NOT_REQUIRED'),
    ('e7e367d6-845a-490d-96b4-994dd67f3703'::uuid, 'noncompliance_and_action_plan', 'NOT_REQUIRED'),
    ('85d3d8e0-421e-46d9-971d-cfda24713402'::uuid, 'chemical_name', 'REQUIRED_BY_HUMAN'),
    ('85d3d8e0-421e-46d9-971d-cfda24713402'::uuid, 'storage_location', 'REQUIRED_BY_HUMAN'),
    ('85d3d8e0-421e-46d9-971d-cfda24713402'::uuid, 'storage_quantity', 'REQUIRED_BY_HUMAN'),
    ('85d3d8e0-421e-46d9-971d-cfda24713402'::uuid, 'handler', 'NOT_REQUIRED'),
    ('85d3d8e0-421e-46d9-971d-cfda24713402'::uuid, 'leak_incident_status', 'NOT_REQUIRED'),
    ('e71177c7-76e4-4009-a14a-c8d7d0532550'::uuid, 'target_work_name', 'REQUIRED_BY_HUMAN'),
    ('e71177c7-76e4-4009-a14a-c8d7d0532550'::uuid, 'pre_work_safety_measures', 'REQUIRED_BY_HUMAN'),
    ('e71177c7-76e4-4009-a14a-c8d7d0532550'::uuid, 'step_by_step_hazards', 'NOT_REQUIRED'),
    ('e71177c7-76e4-4009-a14a-c8d7d0532550'::uuid, 'step_by_step_safety_rules', 'NOT_REQUIRED'),
    ('e71177c7-76e4-4009-a14a-c8d7d0532550'::uuid, 'required_ppe_and_equipment', 'NOT_REQUIRED'),
    ('e71177c7-76e4-4009-a14a-c8d7d0532550'::uuid, 'emergency_response_procedure', 'NOT_REQUIRED'),
    ('4c871f98-6a30-4cbb-a89a-5751d829471b'::uuid, 'emergency_scenario_type', 'REQUIRED_BY_HUMAN'),
    ('4c871f98-6a30-4cbb-a89a-5751d829471b'::uuid, 'evacuation_and_rescue_procedure', 'REQUIRED_BY_HUMAN'),
    ('4c871f98-6a30-4cbb-a89a-5751d829471b'::uuid, 'emergency_contact_system', 'NOT_REQUIRED'),
    ('4c871f98-6a30-4cbb-a89a-5751d829471b'::uuid, 'first_aid_equipment_location', 'NOT_REQUIRED'),
    ('4c871f98-6a30-4cbb-a89a-5751d829471b'::uuid, 'emergency_response_roles', 'NOT_REQUIRED'),
    ('4c871f98-6a30-4cbb-a89a-5751d829471b'::uuid, 'drill_and_inspection_plan', 'NOT_REQUIRED'),
    ('4781af01-ab18-4e81-b679-6bca175e8c99'::uuid, 'subcontractor_basic_info', 'REQUIRED_BY_HUMAN'),
    ('4781af01-ab18-4e81-b679-6bca175e8c99'::uuid, 'safety_management_evaluation', 'REQUIRED_BY_HUMAN'),
    ('4781af01-ab18-4e81-b679-6bca175e8c99'::uuid, 'hazard_control_level', 'NOT_REQUIRED'),
    ('4781af01-ab18-4e81-b679-6bca175e8c99'::uuid, 'incident_history', 'NOT_REQUIRED'),
    ('4781af01-ab18-4e81-b679-6bca175e8c99'::uuid, 'improvement_and_rating', 'NOT_REQUIRED'),
    ('7fee07c5-e992-4000-ac07-dcf4b38013fd'::uuid, 'process_safety_information', 'REQUIRED_BY_HUMAN'),
    ('7fee07c5-e992-4000-ac07-dcf4b38013fd'::uuid, 'process_hazard_analysis', 'REQUIRED_BY_HUMAN'),
    ('7fee07c5-e992-4000-ac07-dcf4b38013fd'::uuid, 'safe_operation_plan', 'REQUIRED_BY_HUMAN'),
    ('7fee07c5-e992-4000-ac07-dcf4b38013fd'::uuid, 'emergency_response_plan', 'REQUIRED_BY_HUMAN'),
    ('dd8b30a3-4084-4e6f-a2c0-57f4325bdc44'::uuid, 'existing_psm_report_information', 'REQUIRED_BY_HUMAN'),
    ('dd8b30a3-4084-4e6f-a2c0-57f4325bdc44'::uuid, 'changed_equipment_or_process', 'REQUIRED_BY_HUMAN'),
    ('dd8b30a3-4084-4e6f-a2c0-57f4325bdc44'::uuid, 'change_details', 'REQUIRED_BY_HUMAN'),
    ('dd8b30a3-4084-4e6f-a2c0-57f4325bdc44'::uuid, 'post_change_risk_assessment_safety_measures', 'REQUIRED_BY_HUMAN'),
    ('835ef8bb-9433-4044-97bb-5f8966809ac3'::uuid, 'work_process_name', 'REQUIRED_BY_HUMAN'),
    ('835ef8bb-9433-4044-97bb-5f8966809ac3'::uuid, 'musculoskeletal_burden_work_status', 'REQUIRED_BY_HUMAN'),
    ('835ef8bb-9433-4044-97bb-5f8966809ac3'::uuid, 'work_condition_survey_result', 'REQUIRED_BY_HUMAN'),
    ('835ef8bb-9433-4044-97bb-5f8966809ac3'::uuid, 'symptom_survey_result', 'REQUIRED_BY_HUMAN'),
    ('67e1f882-221c-4a6a-9a82-6312f75a548f'::uuid, 'hazard_factor_survey_result', 'REQUIRED_BY_HUMAN'),
    ('67e1f882-221c-4a6a-9a82-6312f75a548f'::uuid, 'work_environment_improvement_plan', 'REQUIRED_BY_HUMAN'),
    ('67e1f882-221c-4a6a-9a82-6312f75a548f'::uuid, 'medical_management_plan', 'REQUIRED_BY_HUMAN'),
    ('67e1f882-221c-4a6a-9a82-6312f75a548f'::uuid, 'education_training_plan', 'REQUIRED_BY_HUMAN'),
    ('65e92560-3823-42b0-88af-45d661801bb1'::uuid, 'safety_health_goals_policy', 'REQUIRED_BY_HUMAN'),
    ('65e92560-3823-42b0-88af-45d661801bb1'::uuid, 'dedicated_safety_health_organization', 'REQUIRED_BY_HUMAN'),
    ('65e92560-3823-42b0-88af-45d661801bb1'::uuid, 'hazard_identification_improvement_procedure', 'REQUIRED_BY_HUMAN'),
    ('65e92560-3823-42b0-88af-45d661801bb1'::uuid, 'prevention_personnel_budget_plan', 'REQUIRED_BY_HUMAN'),
    ('65e92560-3823-42b0-88af-45d661801bb1'::uuid, 'safety_manager_evaluation_criteria', 'REQUIRED_BY_HUMAN'),
    ('65e92560-3823-42b0-88af-45d661801bb1'::uuid, 'worker_opinion_process', 'REQUIRED_BY_HUMAN'),
    ('65e92560-3823-42b0-88af-45d661801bb1'::uuid, 'outsourcing_safety_health_standards', 'REQUIRED_BY_HUMAN'),
    ('59d28560-4a8a-4727-925e-cd9a19e0b585'::uuid, 'safety_health_staffing_plan', 'REQUIRED_BY_HUMAN'),
    ('59d28560-4a8a-4727-925e-cd9a19e0b585'::uuid, 'safety_health_budget_plan', 'REQUIRED_BY_HUMAN'),
    ('59d28560-4a8a-4727-925e-cd9a19e0b585'::uuid, 'facility_equipment_provision_plan', 'REQUIRED_BY_HUMAN'),
    ('59d28560-4a8a-4727-925e-cd9a19e0b585'::uuid, 'budget_execution_result', 'REQUIRED_BY_HUMAN'),
    ('59d28560-4a8a-4727-925e-cd9a19e0b585'::uuid, 'unexecuted_reason_and_follow_up_plan', 'NOT_REQUIRED'),
    ('1491b3f4-2742-40ac-942b-9f20819f854d'::uuid, 'education_done', 'REQUIRED_BY_HUMAN'),
    ('1491b3f4-2742-40ac-942b-9f20819f854d'::uuid, 'result', 'NOT_REQUIRED'),
    ('1491b3f4-2742-40ac-942b-9f20819f854d'::uuid, 'action', 'NOT_REQUIRED'),
    ('22c0195f-1719-4858-b653-0af0b3128f38'::uuid, 'outsourcing_work_scope', 'REQUIRED_BY_HUMAN'),
    ('22c0195f-1719-4858-b653-0af0b3128f38'::uuid, 'safety_health_measures', 'REQUIRED_BY_HUMAN'),
    ('22c0195f-1719-4858-b653-0af0b3128f38'::uuid, 'contractor_safety_level_check', 'REQUIRED_BY_HUMAN'),
    ('22c0195f-1719-4858-b653-0af0b3128f38'::uuid, 'hazard_information_sharing', 'REQUIRED_BY_HUMAN'),
    ('22c0195f-1719-4858-b653-0af0b3128f38'::uuid, 'inspection_and_improvement_result', 'NOT_REQUIRED'),
    ('0fd7c6a9-4b79-4f61-86f5-6a2e349deae1'::uuid, 'serious_accident_occurrence', 'REQUIRED_BY_HUMAN'),
    ('0fd7c6a9-4b79-4f61-86f5-6a2e349deae1'::uuid, 'rescue_and_first_aid_action', 'REQUIRED_BY_HUMAN'),
    ('0fd7c6a9-4b79-4f61-86f5-6a2e349deae1'::uuid, 'additional_damage_prevention_action', 'REQUIRED_BY_HUMAN'),
    ('0fd7c6a9-4b79-4f61-86f5-6a2e349deae1'::uuid, 'cause_identification_action', 'REQUIRED_BY_HUMAN'),
    ('0fd7c6a9-4b79-4f61-86f5-6a2e349deae1'::uuid, 'response_owner_and_timeline', 'NOT_REQUIRED'),
    ('36d9ccda-546a-4549-8c74-72daa15140bf'::uuid, 'sms_establishment_status', 'REQUIRED_BY_HUMAN'),
    ('36d9ccda-546a-4549-8c74-72daa15140bf'::uuid, 'hazard_identification_improvement_records', 'REQUIRED_BY_HUMAN'),
    ('36d9ccda-546a-4549-8c74-72daa15140bf'::uuid, 'prevention_budget_staffing', 'REQUIRED_BY_HUMAN'),
    ('36d9ccda-546a-4549-8c74-72daa15140bf'::uuid, 'worker_opinion_reflection_records', 'REQUIRED_BY_HUMAN'),
    ('36d9ccda-546a-4549-8c74-72daa15140bf'::uuid, 'outsourcing_safety_measures', 'REQUIRED_BY_HUMAN'),
    ('36d9ccda-546a-4549-8c74-72daa15140bf'::uuid, 'inspection_and_action_records', 'REQUIRED_BY_HUMAN')

  ) AS v(form_schema_id, field_key, req_status)
  WHERE rf.form_schema_id = v.form_schema_id
    AND rf.field_key = v.field_key
    AND rf.status = 'CANDIDATE'
    AND rf.required_status = 'CANDIDATE_ONLY';

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 245 THEN
    RAISE EXCEPTION 'ABORT: [1] field UPDATE affected % rows (expected 245). ROLLBACK.', v_cnt;
  END IF;

  -- POST-ASSERT [1]
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = ANY(v_schema_ids) AND status = 'APPROVED_BY_HUMAN') <> 245 THEN
    RAISE EXCEPTION 'ABORT: [1] not all 245 fields APPROVED_BY_HUMAN. ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = ANY(v_schema_ids) AND required_status = 'CANDIDATE_ONLY') <> 0 THEN
    RAISE EXCEPTION 'ABORT: [1] CANDIDATE_ONLY still present. ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = ANY(v_schema_ids) AND required_status = 'REQUIRED_BY_HUMAN') <> 186 THEN
    RAISE EXCEPTION 'ABORT: [1] REQUIRED_BY_HUMAN count <> 186. ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = ANY(v_schema_ids) AND required_status = 'NOT_REQUIRED') <> 59 THEN
    RAISE EXCEPTION 'ABORT: [1] NOT_REQUIRED count <> 59. ROLLBACK.';
  END IF;

  -- ── [2] runtime_form_schema ×48: CANDIDATE→APPROVED_BY_HUMAN ─────────
  UPDATE runtime_form_schema
  SET status = 'APPROVED_BY_HUMAN', updated_at = now()
  WHERE id = ANY(v_schema_ids) AND status = 'CANDIDATE';

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 48 THEN
    RAISE EXCEPTION 'ABORT: [2] schema APPROVED_BY_HUMAN affected % rows (expected 48). ROLLBACK.', v_cnt;
  END IF;

  -- ── [3] runtime_form_schema ×48: APPROVED_BY_HUMAN→APPROVED_FOR_RUNTIME_USE ──
  UPDATE runtime_form_schema
  SET status = 'APPROVED_FOR_RUNTIME_USE', updated_at = now()
  WHERE id = ANY(v_schema_ids) AND status = 'APPROVED_BY_HUMAN';

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 48 THEN
    RAISE EXCEPTION 'ABORT: [3] schema APPROVED_FOR_RUNTIME_USE affected % rows (expected 48). ROLLBACK.', v_cnt;
  END IF;

  -- ── [4] 체크리스트 불변 확인 ─────────────────────────────────────────
  IF (SELECT count(*) FROM runtime_checklist_item
      WHERE form_schema_id = ANY(v_schema_ids)
        AND status = 'APPROVED_BY_HUMAN') <> 119 THEN
    RAISE EXCEPTION 'ABORT: [4] checklist APPROVED_BY_HUMAN count <> 119. ROLLBACK.';
  END IF;

  -- ── FINAL ASSERTS ────────────────────────────────────────────────────

  -- F1: 48종 전부 APPROVED_FOR_RUNTIME_USE
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = ANY(v_schema_ids)
        AND status = 'APPROVED_FOR_RUNTIME_USE') <> 48 THEN
    RAISE EXCEPTION 'ABORT: F1 final schema not all APPROVED_FOR_RUNTIME_USE. ROLLBACK.';
  END IF;

  -- F2: schema_candidate 불변
  IF (SELECT count(*) FROM document_schema_candidate
      WHERE id = ANY(v_cand_ids) AND status = 'CANDIDATE') <> 48 THEN
    RAISE EXCEPTION 'ABORT: F2 schema_candidate.status changed. ROLLBACK.';
  END IF;

  -- F3: schema version 불변
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = ANY(v_schema_ids) AND version = 1) <> 48 THEN
    RAISE EXCEPTION 'ABORT: F3 schema version changed. ROLLBACK.';
  END IF;

  -- F4: per-doc (schema_id, catalog_document_id, schema_candidate_id) exact triplet 불변
  IF (SELECT count(*) FROM runtime_form_schema rfs
      JOIN (VALUES
      ('2c62ce24-baea-4d39-a5dc-ce030648d0d7'::uuid, '36d1559f-b95e-4f3d-9838-840bce0722ed'::uuid, '2c115735-1623-4194-b9ec-c422074dd52e'::uuid),
      ('f9de138a-138d-4202-a7be-4bb7158d92c4'::uuid, 'e0d058bb-43ac-4d16-900f-1de8d9566324'::uuid, 'd196dcd5-bf0b-48e3-a039-42e96fe5eb54'::uuid),
      ('ecc54b1d-7f3e-4556-9134-94ad4dd3cd97'::uuid, 'c16dbdff-941c-4c7e-a89f-3a2fdc375a69'::uuid, '96707556-53df-458c-8a9d-47308f0983d4'::uuid),
      ('dcea0582-d5eb-4671-a258-b75d142e83f3'::uuid, '615e9ed3-8e0f-4859-8826-8de5e539d9ad'::uuid, '000b3f54-7069-4fa0-9c8a-7622f218f807'::uuid),
      ('ee1e9dde-2b7f-4278-9cf2-a64476d8a014'::uuid, 'ed1c5d1b-1d73-4a15-9a5b-889b8c4874c7'::uuid, '0e7aac32-232e-463e-b6ab-39d2b885a59d'::uuid),
      ('331ab855-e930-434b-9f8c-25f8a6c8988a'::uuid, 'f7976d16-1afa-47ee-ab04-9dd0345686c2'::uuid, 'a115086b-0dd2-4bad-afbf-e38cf449fa43'::uuid),
      ('910ef261-3f3b-46a7-9f0b-d6ced4a92376'::uuid, '7b4e72af-d82d-4bc9-aa59-352feb7a3d00'::uuid, '29e65ed1-63bd-4950-927e-2120ee0e7964'::uuid),
      ('0204725e-c5e8-4cdb-b9a8-ddf8a423ed00'::uuid, '41e18ccf-ea77-4f11-882d-27492d4441ba'::uuid, '236814ee-9a69-4e72-894a-386caf813407'::uuid),
      ('3b246692-a2d2-4b83-978b-11754dfca0ce'::uuid, 'bfe45c4b-d562-4384-af5f-ed3571ec24d5'::uuid, '6df4e1ff-1b90-41ad-8627-d4aafe924935'::uuid),
      ('3214f248-9fce-4169-a243-a4e43f3e81e5'::uuid, '872223d2-63fd-4f66-a348-0a85fb1f0b45'::uuid, 'fe450f3e-7de0-4357-8b5a-d7caa41a78aa'::uuid),
      ('9c34459f-5b82-40f7-a03a-a532cfdefdd4'::uuid, '501fef0d-8c03-4cfe-bed9-44d0ab8bcc3f'::uuid, '8b11c26e-ab5a-4b72-bf53-f10c75f59d19'::uuid),
      ('5d5a2b58-80e3-4924-933a-006b89267d26'::uuid, '44f76f14-0d1e-4288-83aa-3eed329a2671'::uuid, 'dbabd0b1-4632-44b8-be03-17b48b52a3fc'::uuid),
      ('99905f16-9b1e-4b79-8e15-ef2d2d56b5e0'::uuid, '0a178992-7c5f-448c-a512-751df33de955'::uuid, 'e15ba1ce-497a-4a39-88b5-a5e25a6f3355'::uuid),
      ('b3071484-1547-4f1e-8b5f-12ed391f5519'::uuid, 'b46554fd-7d47-42ae-9fb2-551ce0aa594c'::uuid, '4ed7e74f-634f-493d-a480-092888575a84'::uuid),
      ('98b60eca-5a11-4fc5-a386-c62fb67277a4'::uuid, '28aa89db-ace5-4233-9581-31a13038a4f3'::uuid, '3d0192fd-9df7-4538-ae01-e77baf500d20'::uuid),
      ('4bf3ed32-a9b3-4fdc-ba1a-dd9e5a6de27d'::uuid, '5863fee5-1a9d-4c78-beca-3d4b0d677641'::uuid, '01b83c70-8a99-41bf-b504-ae17cb1ee0ac'::uuid),
      ('48b04ae3-4c0e-4f78-949c-fc8a24421c50'::uuid, '8a2ceea6-6725-4880-adff-ed4813651ad9'::uuid, 'da2f0fa4-e9a1-4c0c-9f27-c1176eaf3113'::uuid),
      ('769d94ff-476e-4d2a-9310-acdff418bda0'::uuid, '0175d554-ff5b-4a6b-a0b8-c595cb5c30fa'::uuid, '7c72150b-05ec-48c9-a44c-849160965842'::uuid),
      ('328bcdb1-45cf-401c-99ad-76e131a39be5'::uuid, '218b1a1c-0976-4c61-addd-b7c9509d80e4'::uuid, '05844c28-493e-46f9-87b2-07124c5012f2'::uuid),
      ('5e89caa2-da79-4d20-86f1-cdfe138b5ac7'::uuid, 'ab556daa-7366-45ce-a0be-4f19ab1e7b43'::uuid, '9e414d2c-4653-4210-9753-ea4afae33d10'::uuid),
      ('3ce74995-9679-4cf0-acde-f46fbd940454'::uuid, '30bdb92c-2be3-4652-a471-f77c5bfb19de'::uuid, 'd05bcd57-cd5e-4f57-9928-66fca70ae137'::uuid),
      ('4f783679-c8ab-42f1-98c5-ce429cd38b19'::uuid, '2179484b-9923-4f62-bfb2-5cbeccf5edb5'::uuid, '0c325df0-d5f7-414f-aad0-7283648866be'::uuid),
      ('3ac8db99-aede-460f-b2d5-daa969b29b6b'::uuid, 'afa892b6-c766-4fb0-9a0f-de7785b2791b'::uuid, '40ff1dcc-1ee1-40c8-89c7-e156370dc259'::uuid),
      ('c959e7e9-942b-449a-aead-904996476687'::uuid, '799f409d-762b-4e59-aa08-6c4553e5b4a9'::uuid, '5192356d-f57f-4547-aaac-1b253bd8dc7e'::uuid),
      ('117958e3-f936-4d06-b869-273001ea023d'::uuid, '7789ea55-5adf-4ff7-bbc7-dc2076189ab3'::uuid, 'f9a593b2-56af-449c-a2c8-4e84a468a6ad'::uuid),
      ('b920ccaf-191a-492c-b43f-8c8f785c632c'::uuid, 'e6db9020-c479-4623-bff2-48f1bac28fb4'::uuid, 'a2ec2df5-d9e3-4389-a53e-adc9714be31f'::uuid),
      ('eddf1605-7b4f-469f-947d-a4380ba6a8cc'::uuid, '6a43296b-4950-4805-b41e-3e64f5ad24dc'::uuid, '1ff1dc5f-ab36-44c9-a44c-75e5e1c1d688'::uuid),
      ('8e1aea7d-1220-4352-bfd0-569d6c9478eb'::uuid, '2f17ec34-c1ad-4c42-b142-63b51f252392'::uuid, '69649676-4228-4d1f-95b1-bf83106f875a'::uuid),
      ('b65478e8-d239-41e0-8959-c4d5b3b73347'::uuid, '98c45426-63e7-4649-9e83-8d5a5625f17c'::uuid, '346fb469-3b94-48dd-87fe-c1dd2e9db6a6'::uuid),
      ('2d4a097a-0a5c-47d7-8115-b537218142fd'::uuid, 'a9d3e80e-8fd5-44ed-bbfc-86cdd1200421'::uuid, '34df1592-0c3f-4b81-a6bd-84ae45ebe55f'::uuid),
      ('c0e894c4-f8bc-4f0f-8820-bf633ce81f86'::uuid, '0cbefa24-b862-4a2f-9307-a94a88aca254'::uuid, '6ad7c853-369c-4cb7-ba41-78a713fbb671'::uuid),
      ('91217759-bd5e-44fa-9348-0ee5b68e8abc'::uuid, 'a4a8c008-57d3-4351-b020-2b5f97a1b20a'::uuid, 'a65c6132-085a-4914-ba4c-bb1a9b76ecd7'::uuid),
      ('7758efc8-6cf4-4c4f-9209-3c704813c56c'::uuid, 'ed047fe4-4a0c-443f-9159-b1be0318f779'::uuid, '7b40975e-a32b-4a84-b445-1c62c9990295'::uuid),
      ('e7e367d6-845a-490d-96b4-994dd67f3703'::uuid, '3c4114ef-1dc1-482e-a67b-44fae3a2c2db'::uuid, 'd60144c9-58ae-471c-a0e1-7633785c2fe4'::uuid),
      ('85d3d8e0-421e-46d9-971d-cfda24713402'::uuid, '1814f7c6-85da-4091-bb17-47604937e3bd'::uuid, '3a7d6a0b-5966-4d1b-a74b-fd83eac9e3d6'::uuid),
      ('e71177c7-76e4-4009-a14a-c8d7d0532550'::uuid, 'da7bf5d8-157a-4cb0-9d11-e80361352757'::uuid, 'b2768726-c20d-4f29-9608-24b3c9d9ba22'::uuid),
      ('4c871f98-6a30-4cbb-a89a-5751d829471b'::uuid, '3eb30ecb-23dc-4d63-a85f-d54576f8d4fa'::uuid, 'a44a414e-b564-41b1-b917-b8793cf1a9a9'::uuid),
      ('4781af01-ab18-4e81-b679-6bca175e8c99'::uuid, '5d5ddf0a-a0b6-4fbc-a76d-a1276960d467'::uuid, '5e139474-cea5-4a45-92dc-0e1535215a07'::uuid),
      ('7fee07c5-e992-4000-ac07-dcf4b38013fd'::uuid, '8f17f61d-ed0e-4cf9-89bf-57f517304a3d'::uuid, 'f02c647b-c4c7-432d-a656-5bc74e99ed00'::uuid),
      ('dd8b30a3-4084-4e6f-a2c0-57f4325bdc44'::uuid, 'b87f8767-ba27-4d36-8ed7-7b3a2aaecc60'::uuid, 'a338e637-5bc7-41f8-bb70-2708eb639db7'::uuid),
      ('835ef8bb-9433-4044-97bb-5f8966809ac3'::uuid, 'fe6800b7-1488-4c25-b2bc-c79b78b7ad62'::uuid, '2e0461b6-c83a-4b0b-93dd-0aeca206d3eb'::uuid),
      ('67e1f882-221c-4a6a-9a82-6312f75a548f'::uuid, 'db99e086-4a00-43bc-affc-2a25dbe1b648'::uuid, '2a018727-9a4a-494b-a8a2-ab5abec498d7'::uuid),
      ('65e92560-3823-42b0-88af-45d661801bb1'::uuid, '6a19c356-0560-4296-beac-34b609690a44'::uuid, 'b4f1f6ec-7383-485b-b049-5489a4a7c3a0'::uuid),
      ('59d28560-4a8a-4727-925e-cd9a19e0b585'::uuid, 'c060a7a2-1c90-47c1-b179-e49de27b88a6'::uuid, '045d28e0-a971-4c14-862b-f29666ca3def'::uuid),
      ('1491b3f4-2742-40ac-942b-9f20819f854d'::uuid, '082eb4f4-9129-4ad6-9bf6-223f608eb9f2'::uuid, '6d2549d1-d354-421b-a48c-a80c7527ad61'::uuid),
      ('22c0195f-1719-4858-b653-0af0b3128f38'::uuid, '62718fa4-8021-453d-b13c-076b9285e616'::uuid, 'db086849-2290-421c-a3bd-d71f48d6b7c9'::uuid),
      ('0fd7c6a9-4b79-4f61-86f5-6a2e349deae1'::uuid, 'a05c67c5-73a3-411a-8c2e-49c0975f9cb6'::uuid, '647eaeb5-e444-485a-b644-b2ae8701da83'::uuid),
      ('36d9ccda-546a-4549-8c74-72daa15140bf'::uuid, 'a18932fb-3631-4fb2-ba8e-d8cdc8b2628d'::uuid, 'a43c29c1-2a71-4868-80bf-8ba5ff733204'::uuid)
      ) AS t(sid, cid, did)
        ON rfs.id = t.sid
       AND rfs.catalog_document_id = t.cid
       AND rfs.schema_candidate_id = t.did) <> 48 THEN
    RAISE EXCEPTION 'ABORT: F4 final exact provenance triplet mismatch. ROLLBACK.';
  END IF;

  -- ── AUDIT LOG ×48 ────────────────────────────────────────────────────
  INSERT INTO runtime_form_audit_log
    (source_table, source_id, action, schema_version,
     before_state, after_state, reviewer_id, review_comment,
     rollback_snapshot, rollback_available)
  SELECT
    'runtime_form_schema',
    rfs.id,
    'PROMOTE_TO_RUNTIME_USE',
    rfs.version,
    jsonb_build_object('schema_id', rfs.id, 'schema_status', 'CANDIDATE',
                       'field_count', rfs.field_count, 'doc_id', df.doc_id),
    jsonb_build_object('schema_id', rfs.id, 'schema_status', 'APPROVED_FOR_RUNTIME_USE',
                       'field_count', rfs.field_count, 'doc_id', df.doc_id),
    NULL,
    'WO-TAI-M004-WEB48DOC-ACTIVATION-EXEC-001: WEB 48종 NON_LEGAL batch activation ' ||
      df.doc_id || ' has_legal_form=FALSE. INSPECTION_SOURCE 15종 제외. Step4D B-1. Owner+PRJ authorization required.',
    v_before_all -> rfs.id::text,
    true
  FROM runtime_form_schema rfs
  JOIN document_forms df ON df.id = rfs.catalog_document_id
  WHERE rfs.id = ANY(v_schema_ids);

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 48 THEN
    RAISE EXCEPTION 'ABORT: audit INSERT affected % rows (expected 48). ROLLBACK.', v_cnt;
  END IF;

  IF (SELECT count(*) FROM runtime_form_audit_log
      WHERE source_table = 'runtime_form_schema'
        AND source_id = ANY(v_schema_ids)
        AND action = 'PROMOTE_TO_RUNTIME_USE') <> 48 THEN
    RAISE EXCEPTION 'ABORT: final audit count <> 48. ROLLBACK.';
  END IF;

  RAISE NOTICE 'PROMOTED OK: 48 schemas APPROVED_FOR_RUNTIME_USE | 245 fields APPROVED_BY_HUMAN | 186 REQUIRED_BY_HUMAN | 59 NOT_REQUIRED | 119 checklists unchanged';
END $$;

-- =====================================================================
-- END — !!! NOT EXECUTED. PRJ+Owner 운영 변경 승인 후 실행. !!!
--
-- 실행 직후 VERIFY (독립 실행 — DO 블록 외부, v_schema_ids 사용 불가):
--
-- Q1: schema 승격 확인
--   SELECT count(*) FROM runtime_form_schema
--     WHERE id = ANY(ARRAY[
--       '2c62ce24-baea-4d39-a5dc-ce030648d0d7','f9de138a-138d-4202-a7be-4bb7158d92c4',
--       'ecc54b1d-7f3e-4556-9134-94ad4dd3cd97','dcea0582-d5eb-4671-a258-b75d142e83f3',
--       'ee1e9dde-2b7f-4278-9cf2-a64476d8a014','331ab855-e930-434b-9f8c-25f8a6c8988a',
--       '910ef261-3f3b-46a7-9f0b-d6ced4a92376','0204725e-c5e8-4cdb-b9a8-ddf8a423ed00',
--       '3b246692-a2d2-4b83-978b-11754dfca0ce','3214f248-9fce-4169-a243-a4e43f3e81e5',
--       '9c34459f-5b82-40f7-a03a-a532cfdefdd4','5d5a2b58-80e3-4924-933a-006b89267d26',
--       '99905f16-9b1e-4b79-8e15-ef2d2d56b5e0','b3071484-1547-4f1e-8b5f-12ed391f5519',
--       '98b60eca-5a11-4fc5-a386-c62fb67277a4','4bf3ed32-a9b3-4fdc-ba1a-dd9e5a6de27d',
--       '48b04ae3-4c0e-4f78-949c-fc8a24421c50','769d94ff-476e-4d2a-9310-acdff418bda0',
--       '328bcdb1-45cf-401c-99ad-76e131a39be5','5e89caa2-da79-4d20-86f1-cdfe138b5ac7',
--       '3ce74995-9679-4cf0-acde-f46fbd940454','4f783679-c8ab-42f1-98c5-ce429cd38b19',
--       '3ac8db99-aede-460f-b2d5-daa969b29b6b','c959e7e9-942b-449a-aead-904996476687',
--       '117958e3-f936-4d06-b869-273001ea023d','b920ccaf-191a-492c-b43f-8c8f785c632c',
--       'eddf1605-7b4f-469f-947d-a4380ba6a8cc','8e1aea7d-1220-4352-bfd0-569d6c9478eb',
--       'b65478e8-d239-41e0-8959-c4d5b3b73347','2d4a097a-0a5c-47d7-8115-b537218142fd',
--       'c0e894c4-f8bc-4f0f-8820-bf633ce81f86','91217759-bd5e-44fa-9348-0ee5b68e8abc',
--       '7758efc8-6cf4-4c4f-9209-3c704813c56c','e7e367d6-845a-490d-96b4-994dd67f3703',
--       '85d3d8e0-421e-46d9-971d-cfda24713402','e71177c7-76e4-4009-a14a-c8d7d0532550',
--       '4c871f98-6a30-4cbb-a89a-5751d829471b','4781af01-ab18-4e81-b679-6bca175e8c99',
--       '7fee07c5-e992-4000-ac07-dcf4b38013fd','dd8b30a3-4084-4e6f-a2c0-57f4325bdc44',
--       '835ef8bb-9433-4044-97bb-5f8966809ac3','67e1f882-221c-4a6a-9a82-6312f75a548f',
--       '65e92560-3823-42b0-88af-45d661801bb1','59d28560-4a8a-4727-925e-cd9a19e0b585',
--       '1491b3f4-2742-40ac-942b-9f20819f854d','22c0195f-1719-4858-b653-0af0b3128f38',
--       '0fd7c6a9-4b79-4f61-86f5-6a2e349deae1','36d9ccda-546a-4549-8c74-72daa15140bf'
--     ]::uuid[]) AND status = 'APPROVED_FOR_RUNTIME_USE';
--   -- EXPECTED: 48
--
-- Q2: 필드 승인·필수여부 확인
--   SELECT status, required_status, count(*)
--     FROM runtime_field
--     WHERE form_schema_id = ANY(ARRAY[
--       '2c62ce24-baea-4d39-a5dc-ce030648d0d7','f9de138a-138d-4202-a7be-4bb7158d92c4',
--       'ecc54b1d-7f3e-4556-9134-94ad4dd3cd97','dcea0582-d5eb-4671-a258-b75d142e83f3',
--       'ee1e9dde-2b7f-4278-9cf2-a64476d8a014','331ab855-e930-434b-9f8c-25f8a6c8988a',
--       '910ef261-3f3b-46a7-9f0b-d6ced4a92376','0204725e-c5e8-4cdb-b9a8-ddf8a423ed00',
--       '3b246692-a2d2-4b83-978b-11754dfca0ce','3214f248-9fce-4169-a243-a4e43f3e81e5',
--       '9c34459f-5b82-40f7-a03a-a532cfdefdd4','5d5a2b58-80e3-4924-933a-006b89267d26',
--       '99905f16-9b1e-4b79-8e15-ef2d2d56b5e0','b3071484-1547-4f1e-8b5f-12ed391f5519',
--       '98b60eca-5a11-4fc5-a386-c62fb67277a4','4bf3ed32-a9b3-4fdc-ba1a-dd9e5a6de27d',
--       '48b04ae3-4c0e-4f78-949c-fc8a24421c50','769d94ff-476e-4d2a-9310-acdff418bda0',
--       '328bcdb1-45cf-401c-99ad-76e131a39be5','5e89caa2-da79-4d20-86f1-cdfe138b5ac7',
--       '3ce74995-9679-4cf0-acde-f46fbd940454','4f783679-c8ab-42f1-98c5-ce429cd38b19',
--       '3ac8db99-aede-460f-b2d5-daa969b29b6b','c959e7e9-942b-449a-aead-904996476687',
--       '117958e3-f936-4d06-b869-273001ea023d','b920ccaf-191a-492c-b43f-8c8f785c632c',
--       'eddf1605-7b4f-469f-947d-a4380ba6a8cc','8e1aea7d-1220-4352-bfd0-569d6c9478eb',
--       'b65478e8-d239-41e0-8959-c4d5b3b73347','2d4a097a-0a5c-47d7-8115-b537218142fd',
--       'c0e894c4-f8bc-4f0f-8820-bf633ce81f86','91217759-bd5e-44fa-9348-0ee5b68e8abc',
--       '7758efc8-6cf4-4c4f-9209-3c704813c56c','e7e367d6-845a-490d-96b4-994dd67f3703',
--       '85d3d8e0-421e-46d9-971d-cfda24713402','e71177c7-76e4-4009-a14a-c8d7d0532550',
--       '4c871f98-6a30-4cbb-a89a-5751d829471b','4781af01-ab18-4e81-b679-6bca175e8c99',
--       '7fee07c5-e992-4000-ac07-dcf4b38013fd','dd8b30a3-4084-4e6f-a2c0-57f4325bdc44',
--       '835ef8bb-9433-4044-97bb-5f8966809ac3','67e1f882-221c-4a6a-9a82-6312f75a548f',
--       '65e92560-3823-42b0-88af-45d661801bb1','59d28560-4a8a-4727-925e-cd9a19e0b585',
--       '1491b3f4-2742-40ac-942b-9f20819f854d','22c0195f-1719-4858-b653-0af0b3128f38',
--       '0fd7c6a9-4b79-4f61-86f5-6a2e349deae1','36d9ccda-546a-4549-8c74-72daa15140bf'
--     ]::uuid[])
--   GROUP BY status, required_status;
--   -- EXPECTED: APPROVED_BY_HUMAN/REQUIRED_BY_HUMAN=186, APPROVED_BY_HUMAN/NOT_REQUIRED=59
--
-- Q3: catalog can_create 확인 (임의 1개)
--   GET /document-engine/catalog/DOC-BLD-023 → can_create=true
-- =====================================================================
