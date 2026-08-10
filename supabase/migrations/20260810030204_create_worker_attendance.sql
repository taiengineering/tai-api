-- 작업자 출퇴근 / 현장 출입
--
-- 배경
--   작업자 PWA 의 두 화면이 POST /attendance 를 호출하나 서버에 경로도 테이블도 없다.
--     /app/attendance.html  GPS 기반 출퇴근
--     /app/qr_scan.html     현장 QR 출입
--
-- 기존 테이블을 재사용하지 않는 이유
--   equipment_checkins 는 equipment_asset_id 가 NOT NULL 인 설비 점검 체크인용이라
--   사람의 출퇴근과 성격이 다르다. 설비 id 없이 행을 만들 수 없다.

CREATE TABLE IF NOT EXISTS worker_attendance (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- 작업자 식별. worker_id 는 users/worker_registry 어느 쪽에도 있을 수 있어 FK 를 걸지 않는다.
  worker_id     uuid,
  phone         text NOT NULL,
  worker_name   text,

  company_id    uuid,
  factory_id    uuid,
  site_id       uuid,

  entry_type    text NOT NULL,                 -- IN=출근/입장, OUT=퇴근/퇴장
  method        text NOT NULL DEFAULT 'GPS',   -- GPS=위치기반, QR=현장 QR 스캔

  -- 위치. GPS 방식에서 채워지며 QR 방식에서는 비어 있을 수 있다.
  latitude      numeric,
  longitude     numeric,
  location_text text,

  -- QR 스캔 시 읽은 코드 원문. 사후 추적용.
  qr_code       text,

  recorded_at   timestamptz NOT NULL DEFAULT now(),

  created_by    uuid,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT worker_attendance_entry_type_chk CHECK (entry_type IN ('IN','OUT')),
  CONSTRAINT worker_attendance_method_chk     CHECK (method IN ('GPS','QR','MANUAL'))
);

COMMENT ON TABLE  worker_attendance IS '작업자 출퇴근·현장 출입 기록. GPS(attendance.html)와 QR(qr_scan.html) 양쪽이 쓴다';
COMMENT ON COLUMN worker_attendance.method  IS 'GPS=위치기반 버튼, QR=현장 QR 스캔, MANUAL=관리자 수기 등록';
COMMENT ON COLUMN worker_attendance.qr_code IS 'QR 방식에서 스캔한 코드 원문. 사후 추적용';

-- 개인 출입 이력 조회(최근순)가 주 사용 패턴이다
CREATE INDEX IF NOT EXISTS ix_worker_attendance_phone_time
  ON worker_attendance(phone, recorded_at DESC);
-- 현장별 당일 출입 현황 집계용
CREATE INDEX IF NOT EXISTS ix_worker_attendance_site_time
  ON worker_attendance(site_id, recorded_at DESC)
  WHERE site_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_worker_attendance_factory_time
  ON worker_attendance(factory_id, recorded_at DESC)
  WHERE factory_id IS NOT NULL;