-- 작업허가서 (Permit-to-Work)
--
-- 배경
--   작업자 PWA(/app/work_request.html)가 POST /work-requests 를 호출하나
--   서버에 경로도 테이블도 없다.
--
-- 실체는 "작업 요청"이 아니라 작업허가서다.
--   유형: height(고소 2m↑) · fire(화기·용접절단) · confined(밀폐공간·산소결핍)
--         · electric(전기·활선) · crane(크레인·양중) · other
--   모두 산안법상 위험작업 사전 허가 대상이며, 화면도 유형별 안전조치 체크리스트를
--   확인시킨 뒤 제출하는 구조다.
--
-- 기존 테이블을 재사용하지 않는 이유
--   repair_requests · fix_service_requests · inspection_requests ·
--   runtime_operational_work_order 는 모두 수리·정비·점검 "요청"이라 의미가 다르다.
--   허가 승인 상태와 안전조치 확인 기록을 담을 구조가 없다.

CREATE TABLE IF NOT EXISTS work_permits (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- 허가번호. 서버가 채번하며 화면에 표시된다(safety_reports·emergency_reports 와 동일 관례).
  permit_number      text NOT NULL,

  company_id         uuid,
  factory_id         uuid,
  site_id            uuid,

  -- 신청자
  requester_id       uuid,
  requester_phone    text NOT NULL,
  requester_name     text,

  work_type          text NOT NULL,
  description        text NOT NULL,
  start_time         timestamptz,
  end_time           timestamptz,

  -- 투입 작업자 명단. 프론트가 이름 배열로 보낸다.
  workers_json       jsonb NOT NULL DEFAULT '[]'::jsonb,
  -- 확인한 안전조치 항목. 유형별 체크리스트에서 체크된 것들.
  safety_checks_json jsonb NOT NULL DEFAULT '[]'::jsonb,

  -- REQUESTED → APPROVED | REJECTED → CLOSED(작업 종료)
  status             text NOT NULL DEFAULT 'REQUESTED',
  approved_by        uuid,
  approved_at        timestamptz,
  reject_reason      text,
  closed_at          timestamptz,

  created_by         uuid,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT work_permits_permit_number_uq UNIQUE (permit_number),
  CONSTRAINT work_permits_work_type_chk
    CHECK (work_type IN ('height','fire','confined','electric','crane','other')),
  CONSTRAINT work_permits_status_chk
    CHECK (status IN ('REQUESTED','APPROVED','REJECTED','CLOSED'))
);

COMMENT ON TABLE  work_permits IS '작업허가서(Permit-to-Work). 산안법상 위험작업 사전 허가';
COMMENT ON COLUMN work_permits.work_type          IS 'height=고소(2m↑), fire=화기, confined=밀폐공간, electric=전기, crane=양중, other=기타 위험작업';
COMMENT ON COLUMN work_permits.safety_checks_json IS '유형별 안전조치 체크리스트에서 확인된 항목. 허가 근거 기록';
COMMENT ON COLUMN work_permits.permit_number      IS '서버 채번. 프론트가 화면에 표시하므로 응답에 반드시 포함해야 한다';

-- 신청자 본인의 허가 이력 조회
CREATE INDEX IF NOT EXISTS ix_work_permits_requester
  ON work_permits(requester_phone, created_at DESC);
-- 관리자 승인 대기 목록 — 부분 인덱스
CREATE INDEX IF NOT EXISTS ix_work_permits_pending
  ON work_permits(status, created_at DESC)
  WHERE status = 'REQUESTED';
CREATE INDEX IF NOT EXISTS ix_work_permits_factory
  ON work_permits(factory_id, created_at DESC)
  WHERE factory_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_work_permits_site
  ON work_permits(site_id, created_at DESC)
  WHERE site_id IS NOT NULL;