-- 건설 공정별 점검항목 마스터
--
-- 배경
--   /app/construction_inspect.html 에 PROCESS_DATA 로 22개 항목이 하드코딩되어 있다.
--   현장별 조정이 불가능하고, 항목이 한국어 고정이라 외국인 근로자가 읽을 수 없다.
--
-- 기존 inspection_sets/inspection_set_items 를 재사용하지 않는 이유
--   1) 그 테이블은 source='LEGAL_ENGINE' 전용이다. 실측 결과 318건 전부 법령 엔진이
--      회사별로 생성한 행이며, company_id/factory_id 가 없는 전역 행은 0건이다.
--   2) cycle_unit/cycle_value 가 NOT NULL 이고 대부분 PENDING_ANCHOR/ACTIVE 로
--      work_schedules 스케줄 파이프라인을 탄다. 건설 공정 점검을 여기 넣으면
--      기한이 생겨 미이행 배너에 잡힌다. 공정 점검은 "작업할 때 하는 것"이지
--      기한이 정해진 법정 정기점검이 아니다.
--   3) 다국어를 담을 컬럼이 없다.
--
-- 다국어는 jsonb 로 담는다. 언어를 추가해도 스키마 변경이 필요 없다.
--   {"ko":"...","en":"...","zh":"...","vi":"...","ne":"...","km":"...","tl":"..."}

CREATE TABLE IF NOT EXISTS construction_check_templates (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- 공정 구분. 프론트 PROC_KEYS 와 동일하다.
  process_key  text NOT NULL,
  -- 화면 표시 순서
  item_seq     integer NOT NULL,
  -- 기존 프론트 항목 id(g1·t1·k1·m1·s1…). 이관 추적과 결과 대조에 쓴다.
  item_code    text NOT NULL,

  -- 다국어 본문. ko 는 필수이며 나머지 언어가 없으면 프론트가 ko 로 폴백한다.
  name_i18n    jsonb NOT NULL,
  desc_i18n    jsonb NOT NULL DEFAULT '{}'::jsonb,
  risk_i18n    jsonb NOT NULL DEFAULT '{}'::jsonb,

  -- 법적 근거를 달 수 있게 둔다. 지금은 비어 있고 추후 법령 엔진과 연결할 여지.
  law_name     text,
  law_article  text,

  is_active    boolean NOT NULL DEFAULT true,

  created_by   uuid,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT construction_check_templates_process_chk
    CHECK (process_key IN ('temp','earth','struct','finish','mep')),
  -- ko 없이 저장되면 화면에 빈 항목이 뜬다. 최소한 한국어는 강제한다.
  CONSTRAINT construction_check_templates_name_ko_chk
    CHECK (name_i18n ? 'ko'),
  CONSTRAINT construction_check_templates_code_uq
    UNIQUE (process_key, item_code)
);

COMMENT ON TABLE  construction_check_templates IS '건설 공정별 점검항목 마스터. construction_inspect.html 하드코딩 이관분';
COMMENT ON COLUMN construction_check_templates.process_key IS 'temp=가설공사, earth=토공사, struct=골조공사, finish=마감공사, mep=설비공사';
COMMENT ON COLUMN construction_check_templates.item_code   IS '이관 전 프론트 항목 id. 기존 점검 결과와의 대조에 쓴다';
COMMENT ON COLUMN construction_check_templates.name_i18n   IS '언어코드 → 문자열. ko 필수, 나머지는 프론트에서 ko 로 폴백';

CREATE INDEX IF NOT EXISTS ix_construction_check_templates_process
  ON construction_check_templates(process_key, item_seq)
  WHERE is_active = true;
