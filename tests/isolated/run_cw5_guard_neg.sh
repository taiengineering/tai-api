#!/usr/bin/env bash
# run_cw5_guard_neg.sh
# WO-TAI-SEC-SEARCHPATH-REM97-CW5-C3-R2-GUARD-CLOSE-001
# 실제 cw5_migration_iso.sql PRE/POST 블록을 실행하여 Guard 부정 테스트 수행

set -uo pipefail

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
MIGRATION_ISO="${TESTS_DIR}/cw5_migration_iso.sql"
SETUP="${TESTS_DIR}/setup_cw5.sql"
LOG_FILE="/tmp/guard_neg_run.log"

PSQL_BASE="PGPASSWORD=test psql -h localhost -p 55434 -U postgres -d cw5_test"
PSQL_STOP="${PSQL_BASE} -v ON_ERROR_STOP=1"

pass=0
fail=0
TOTAL=7  # 1 positive + 6 negative

: > "$LOG_FILE"

log() { echo "$1" | tee -a "$LOG_FILE"; }

run_fresh_setup() {
  eval "${PSQL_BASE} -f '${SETUP}'" >> "$LOG_FILE" 2>&1
  local rc=$?
  if [ $rc -ne 0 ]; then
    log "FATAL: setup_cw5.sql failed (exit $rc)"
    exit 1
  fi
}

check_atomicity() {
  local label="$1"
  # migration STEP2 미적용 확인: 두 대상 함수 모두 migration target proconfig 없음
  local applied
  applied=$(eval "${PSQL_BASE} -t -c \"SELECT COUNT(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname IN ('sieve_executor','diagnose_clauses_common') AND p.proconfig = ARRAY['search_path=pg_catalog, public, pg_temp']::text[]\"" 2>/dev/null | tr -d ' \n')
  if [ "${applied}" = "0" ]; then
    log "  ${label}_ATOMICITY PASS: migration STEP2 not applied (neither function has target proconfig)"
  else
    log "  ${label}_ATOMICITY FAIL: ${applied} function(s) have target proconfig (partial apply!)"
    fail=$((fail+1))
  fi
}

run_neg_test() {
  local name="$1"
  local corrupt_sql_file="$2"
  local expected_pattern="$3"

  log ""
  log "--- NEG-${name} ---"

  run_fresh_setup

  eval "${PSQL_BASE} -f '${corrupt_sql_file}'" >> "$LOG_FILE" 2>&1 || true

  local neg_log="/tmp/guard_neg_${name}.log"
  eval "${PSQL_STOP} -f '${MIGRATION_ISO}'" > "$neg_log" 2>&1
  local exit_code=$?

  if [ $exit_code -ne 0 ]; then
    if grep -qE "${expected_pattern}" "$neg_log"; then
      log "NEG-${name} PASS: migration guard fired (exit=${exit_code})"
      pass=$((pass+1))
    else
      log "NEG-${name} FAIL: migration failed but wrong error (exit=${exit_code})"
      log "  Expected pattern: ${expected_pattern}"
      log "  Actual errors: $(grep -iE 'error|exception' "$neg_log" | head -3)"
      fail=$((fail+1))
    fi
    check_atomicity "NEG-${name}"
  else
    log "NEG-${name} FAIL: migration SUCCEEDED when it should have FAILED"
    fail=$((fail+1))
  fi
}

# ── corrupt SQL 파일 생성 ──────────────────────────────────

cat > /tmp/cw5_neg01_corrupt.sql << 'ENDSQL'
CREATE OR REPLACE FUNCTION public.sieve_executor(p_executor text)
  RETURNS TABLE(class_label text, decision text, rule_id bigint,
                matched_priority integer, match_kind text)
  LANGUAGE sql STABLE AS
$f$ SELECT NULL::text, NULL::text, NULL::bigint, NULL::integer, NULL::text WHERE false; $f$;
ENDSQL

cat > /tmp/cw5_neg02_corrupt.sql << 'ENDSQL'
CREATE OR REPLACE FUNCTION public.diagnose_clauses_common()
  RETURNS TABLE(clause_id uuid, article_id uuid, executor_text text,
                action_text text, condition_text text, cycle_text text,
                content_type text, clause_sector text, sieve_class text,
                sieve_decision text, sieve_rule_id bigint)
  LANGUAGE sql STABLE AS
$f$ SELECT NULL::uuid,NULL::uuid,NULL::text,NULL::text,NULL::text,NULL::text,
           NULL::text,NULL::text,NULL::text,NULL::text,NULL::bigint WHERE false; $f$;
ENDSQL

cat > /tmp/cw5_neg03_corrupt.sql << 'ENDSQL'
ALTER FUNCTION public.sieve_executor(text)
  SET search_path = pg_catalog, public;
ENDSQL

cat > /tmp/cw5_neg04_corrupt.sql << 'ENDSQL'
REVOKE EXECUTE ON FUNCTION public.sieve_executor(text) FROM anon;
ENDSQL

cat > /tmp/cw5_neg05_corrupt.sql << 'ENDSQL'
CREATE OR REPLACE FUNCTION public.run_common_sieve()
  RETURNS TABLE(class_label text, decision text, cnt bigint, pct numeric)
  LANGUAGE sql STABLE AS
$f$ SELECT NULL::text, NULL::text, NULL::bigint, NULL::numeric WHERE false; $f$;
ENDSQL

# NEG-06: 원본과 동일한 body(MD5 일치)이지만 인자 수 증가 → pronargs 검사 트리거
# prosrc MD5: 79c50e3985bf489f80b1b11ec516aac6 (운영 기준선과 동일)
cat > /tmp/cw5_neg06_corrupt.sql << 'ENDSQL'
DROP FUNCTION public.sieve_executor(text);
CREATE FUNCTION public.sieve_executor(p_executor text, p_extra text)
  RETURNS TABLE(class_label text, decision text, rule_id bigint,
                matched_priority integer, match_kind text)
  LANGUAGE sql STABLE AS
$func$
  WITH ex AS (SELECT trim(coalesce(p_executor,'')) AS v)
  SELECT r.class_label,
         CASE WHEN r.verdict='KEEP' THEN 'KEEP' ELSE 'DROP' END AS decision,
         r.id, r.priority, r.match_type
  FROM legal_sieve_rule r, ex
  WHERE r.enabled = true
    AND r.stage IN ('common','common_value')
    AND r.target_field = 'executor_text'
    AND ex.v <> ''
    AND (
      (r.match_type='exact'    AND ex.v = r.pattern) OR
      (r.match_type='contains' AND ex.v LIKE '%'||r.pattern||'%') OR
      (r.match_type='regex'    AND ex.v ~ r.pattern)
    )
  ORDER BY r.priority,
           CASE r.match_type WHEN 'exact' THEN 0 WHEN 'contains' THEN 1 ELSE 2 END
  LIMIT 1;
$func$;
GRANT EXECUTE ON FUNCTION public.sieve_executor(text, text)
  TO postgres, anon, authenticated, service_role, PUBLIC;
ENDSQL

# ── 테스트 실행 ───────────────────────────────────────────

log "=== C-W5 Guard Tests START ==="
log "LOG: ${LOG_FILE}"
log "ISO migration: ${MIGRATION_ISO}"
log ""

# POS-00: 정상 기준선 migration 성공
log "--- POS-00: happy path ---"
run_fresh_setup
eval "${PSQL_STOP} -f '${MIGRATION_ISO}'" > /tmp/guard_pos_00.log 2>&1
pos_exit=$?
if [ $pos_exit -eq 0 ]; then
  log "POS-00 PASS: migration ISO succeeded on clean setup (exit=0)"
  pass=$((pass+1))
else
  log "POS-00 FAIL: migration ISO FAILED on clean setup (exit=${pos_exit})"
  log "  $(grep -iE 'error|exception' /tmp/guard_pos_00.log | head -5)"
  fail=$((fail+1))
fi

run_neg_test "01_c20_md5"       "/tmp/cw5_neg01_corrupt.sql" "C-W5 PRE C20 MD5"
run_neg_test "02_c19_md5"       "/tmp/cw5_neg02_corrupt.sql" "C-W5 PRE C19 MD5"
run_neg_test "03_proconfig"     "/tmp/cw5_neg03_corrupt.sql" "C-W5 PRE C20 proconfig not NULL"
run_neg_test "04_acl_mismatch"  "/tmp/cw5_neg04_corrupt.sql" "C-W5 PRE C20 proacl baseline"
run_neg_test "05_rc_md5"        "/tmp/cw5_neg05_corrupt.sql" "C-W5 PRE RC MD5"
run_neg_test "06_signature"     "/tmp/cw5_neg06_corrupt.sql" "C-W5 PRE C20 pronargs"

log ""
log "=== C-W5 Guard Tests COMPLETE: ${pass}/${TOTAL} PASS ==="
if [ $fail -gt 0 ]; then
  log "FAIL COUNT: ${fail}"
  exit 1
fi
exit 0
