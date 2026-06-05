-- 20260605_archive_legacy_price_tables.sql
-- 가격 테이블 통합(price_master) 후 구 테이블 격리 스크립트.
--
-- ⚠ 적용 순서 (반드시 지킬 것):
--   1) 본 PR(feat/price-master-unification)의 라우터 변경이 머지·배포되어
--      public_pricing / price_master_admin 이 price_master 만 참조하는 것을 확인.
--   2) 카드(공개 pricing.html)와 admin price-setting 동작 확인.
--   3) 그 다음에 본 스크립트 실행 (운영 무중단 확인 후).
--
-- 격리 방식: 물리 삭제 없음. archive 스키마로 이동(rename)하여 되돌리기 가능.
--   복구가 필요하면: ALTER TABLE archive.<t> SET SCHEMA public;

CREATE SCHEMA IF NOT EXISTS archive;

-- (A) 가격 카드가 더 이상 직접 참조하지 않는 구 카드 테이블.
--     price_master로 데이터가 이관되었으므로 격리.
ALTER TABLE IF EXISTS public.price_diagnosis_report SET SCHEMA archive;
ALTER TABLE IF EXISTS public.price_saas_plan        SET SCHEMA archive;

-- (B) 행이 없고(0건) 카드/주요 라우터 코드 참조가 없는 미사용 테이블.
ALTER TABLE IF EXISTS public.price_quotes        SET SCHEMA archive;
ALTER TABLE IF EXISTS public.price_standard_wage SET SCHEMA archive;

-- ── 격리하지 않는 테이블 (다른 라우터가 사용 중 — 유지) ──
--   price_policy            : routers/price_policy.py, payment
--   price_commission        : routers/matching_commission.py, matching_svc
--   price_repair_brokerage  : routers/price_setting.py (수리중개)
--   price_safety_management : routers/price_setting.py (안전관리대행)
--   price_consulting        : routers/price_setting.py (컨설팅)
--   price_change_log        : 변경 이력 자동 기록
--   price_discount / price_region_surcharge / price_travel_rule :
--      현재 카드 미참조이나 추가 확인 후 별도 차수에서 격리 검토 (이번엔 보류)
