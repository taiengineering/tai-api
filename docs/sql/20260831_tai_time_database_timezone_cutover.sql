-- TAI TIME PHASE 2 STEP D artifact.
-- EXECUTE = 0. Do not run against TAI Supabase vwlahtguyggrhvslabax.
-- POST: SHOW timezone;  → Asia/Seoul

ALTER DATABASE postgres SET timezone TO 'Asia/Seoul';

-- POSTCHECK (operator, after approved execution — not this commit):
--   SHOW timezone;
--   -- expected: Asia/Seoul
