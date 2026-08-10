-- 위험성평가 작업자 참여 (산안법 제36조)
--
-- 배경
--   작업자 PWA(/app/risk.html)가 POST /risk-assessments/{id}/participate 를 호출하나
--   서버에 경로가 없어 404 로 실패해 왔다. 참여 서명이 저장되지 않았다.
--
-- 전용 테이블을 택한 근거 (participants_json append 대신)
--   1) 고시 제15조제4항의 "월1회 유해·위험요인 발굴" 을 작업자 extra_json 으로 충족하려면
--      건별 조회·집계가 필요하다. jsonb append 로는 불가능하다.
--   2) review_status 로 작업자 발굴 → 관리자 채택(ADOPTED) → ra_item 승격 워크플로가 성립한다.
--   3) 여러 작업자가 동시에 서명할 때 jsonb append 는 lost update 위험이 있다.
--   4) 서명은 산안법 제36조 기록이므로 행 단위 보존·삭제 관리가 필요하다.
--
-- 명명은 기존 ra_item·ra_control·ra_scale 관례를 따른다.

CREATE TABLE IF NOT EXISTS ra_participation (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id   uuid NOT NULL REFERENCES risk_assessments(id) ON DELETE CASCADE,

  -- 작업자 식별. worker_id 는 users/worker_registry 어느 쪽에도 있을 수 있어 FK 를 걸지 않는다.
  -- phone 은 앱이 항상 보내는 값이라 NOT NULL 로 둔다(worker_check.py 관례와 동일).
  worker_id       uuid,
  phone           text NOT NULL,
  worker_name     text,

  -- 동의한 위험요인 id 목록
  agreed_json     jsonb NOT NULL DEFAULT '[]'::jsonb,
  -- 작업자가 현장에서 발굴한 추가 위험요인 (상시평가 월1회 발굴 요건의 입력원)
  extra_json      jsonb NOT NULL DEFAULT '[]'::jsonb,

  signature_url   text,
  participated_at timestamptz NOT NULL DEFAULT now(),

  -- 관리자 검토 루프. PENDING → ADOPTED(ra_item 승격) | REJECTED
  review_status   text NOT NULL DEFAULT 'PENDING',
  reviewed_by     uuid,
  reviewed_at     timestamptz,
  review_note     text,

  created_by      uuid,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT ra_participation_review_status_chk
    CHECK (review_status IN ('PENDING','ADOPTED','REJECTED'))
);

COMMENT ON TABLE  ra_participation IS '위험성평가 작업자 참여·서명 (산안법 제36조). 작업자 발굴 위험요인의 관리자 검토 루프 포함';
COMMENT ON COLUMN ra_participation.extra_json    IS '작업자가 발굴한 추가 위험요인. 고시 제15조제4항 월1회 발굴 요건의 입력원';
COMMENT ON COLUMN ra_participation.review_status IS 'PENDING=검토대기, ADOPTED=ra_item 승격, REJECTED=반려';

CREATE INDEX IF NOT EXISTS ix_ra_participation_assessment
  ON ra_participation(assessment_id);
CREATE INDEX IF NOT EXISTS ix_ra_participation_phone
  ON ra_participation(phone);
-- 검토 대기 건만 부분 인덱스 — 관리자 화면이 PENDING 만 조회한다
CREATE INDEX IF NOT EXISTS ix_ra_participation_review_pending
  ON ra_participation(review_status)
  WHERE review_status = 'PENDING';

-- 동일 평가에 같은 작업자가 중복 참여하는 것을 막는다.
-- 재서명이 필요하면 기존 행을 UPDATE 한다.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ra_participation_assessment_phone
  ON ra_participation(assessment_id, phone);