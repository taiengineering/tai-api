-- users.sector 컬럼 기본값 오타 수정
--
-- 증상
--   sector 를 명시하지 않은 모든 users INSERT 가 23514 로 실패한다.
--
-- 원인
--   컬럼 기본값이 'INDUSTRY' 인데 users_sector_check 제약은
--     BUILDING | INDUSTRIAL | CONSTRUCTION | SPECIAL_FACILITY | COMMON  (또는 NULL)
--   만 허용한다. 기본값에 'AL' 이 빠져 있어 자기 자신이 제약을 통과하지 못한다.
--
--   재현:
--     INSERT INTO users (email, phone, name) VALUES (...);   -- sector 미지정
--     ERROR: 23514 new row for relation "users" violates check constraint
--            "users_sector_check"  (실패 행의 sector = INDUSTRY)
--
-- 영향 범위
--   POST /auth/register, verify-otp 의 계정 자동 생성 등 sector 를 넣지 않는
--   모든 경로. 기존 users 22행은 전원 sector 가 채워져 있어(16행 INDUSTRIAL)
--   이미 만들어진 데이터에는 영향이 없다.
--
-- 조치
--   기본값을 제약이 허용하는 'INDUSTRIAL' 로 바로잡는다.
--   NULL 도 제약이 허용하므로 기본값을 NULL 로 두는 선택지도 있으나,
--   기존 데이터가 전부 값을 갖고 있고 화면이 sector 로 업종을 분기하므로
--   다수값인 INDUSTRIAL 을 유지한다.

ALTER TABLE users ALTER COLUMN sector SET DEFAULT 'INDUSTRIAL';

COMMENT ON COLUMN users.sector IS
  '업종. users_sector_check 허용값: BUILDING|INDUSTRIAL|CONSTRUCTION|SPECIAL_FACILITY|COMMON 또는 NULL';
