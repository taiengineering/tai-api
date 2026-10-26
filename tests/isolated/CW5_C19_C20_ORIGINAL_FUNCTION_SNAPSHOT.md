# C-W5 Original Function Snapshot
# WO-TAI-SEC-SEARCHPATH-REM97-CW5-C3-SOURCE-001
# PRE 스냅샷 — 운영 DB 읽기 전용 확보 (2026-10-26)
# 이 파일은 증거 보존용이며 재실행하지 않는다.
#
# DDL 형상관리 갭:
#   C19·C20 최초 CREATE FUNCTION Migration이 tai-api git에 없음.
#   기원 커밋: 015ce894 (legal_sieve_rule), 7f37fe80 (diagnose_clauses_common)
#   Author: TAI Engineering <tai@taieng.co.kr>, 2026-06-14~15
#   갭 복원은 별도 작업 대상.

## C20 — public.sieve_executor(text)

| 항목 | 값 |
|------|----|
| OID | 78511 |
| Schema | public |
| Args | p_executor text |
| Returns | TABLE(class_label text, decision text, rule_id bigint, matched_priority integer, match_kind text) |
| Language | sql |
| Volatility | STABLE (s) |
| Parallel | UNSAFE (u) |
| Security | INVOKER (prosecdef=false) |
| Owner | postgres |
| proconfig | NULL |
| body_md5 | 79c50e3985bf489f80b1b11ec516aac6 |
| proacl | {=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres} |

```sql
CREATE OR REPLACE FUNCTION public.sieve_executor(p_executor text)
 RETURNS TABLE(class_label text, decision text, rule_id bigint, matched_priority integer, match_kind text)
 LANGUAGE sql
 STABLE
AS $function$
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
$function$
```

## C19 — public.diagnose_clauses_common()

| 항목 | 값 |
|------|----|
| OID | 78515 |
| Schema | public |
| Args | (none) |
| Returns | TABLE(clause_id uuid, article_id uuid, executor_text text, action_text text, condition_text text, cycle_text text, content_type text, clause_sector text, sieve_class text, sieve_decision text, sieve_rule_id bigint) |
| Language | sql |
| Volatility | STABLE (s) |
| Parallel | UNSAFE (u) |
| Security | INVOKER (prosecdef=false) |
| Owner | postgres |
| proconfig | NULL |
| body_md5 | f205550a5412f9111ac3a5449468ac7b |
| proacl | {=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres} |

```sql
CREATE OR REPLACE FUNCTION public.diagnose_clauses_common()
 RETURNS TABLE(clause_id uuid, article_id uuid, executor_text text, action_text text, condition_text text, cycle_text text, content_type text, clause_sector text, sieve_class text, sieve_decision text, sieve_rule_id bigint)
 LANGUAGE sql
 STABLE
AS $function$
  SELECT
    s.id, s.source_article_id, s.executor_text, s.action_text,
    s.condition_text, s.cycle_text, s.content_type, s.sector,
    COALESCE(v.class_label, 'AMBIGUOUS') AS sieve_class,
    COALESCE(v.decision, 'KEEP_REVIEW')  AS sieve_decision,
    v.rule_id
  FROM semantic_clause_fix s
  LEFT JOIN LATERAL sieve_executor(s.executor_text) v ON true
  WHERE s.content_type IN ('OBLIGATION','PROHIBITION')
    AND COALESCE(v.decision, 'KEEP_REVIEW') <> 'DROP';  -- DROP 제외, KEEP+보류만
$function$
```

## RC — public.run_common_sieve() (간접 호출자, 변경 금지)

| 항목 | 값 |
|------|----|
| OID | 78513 |
| Schema | public |
| Args | (none) |
| Returns | TABLE(class_label text, decision text, cnt bigint, pct numeric) |
| Language | sql |
| Volatility | STABLE (s) |
| Parallel | UNSAFE (u) |
| Security | INVOKER (prosecdef=false) |
| Owner | postgres |
| proconfig | NULL (변경 금지) |
| body_md5 | fbaf7f9a900d09f748ea02a1c6cc9bc6 |
| proacl | {=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres} |

```sql
CREATE OR REPLACE FUNCTION public.run_common_sieve()
 RETURNS TABLE(class_label text, decision text, cnt bigint, pct numeric)
 LANGUAGE sql
 STABLE
AS $function$
  WITH ob AS (
    SELECT executor_text
    FROM semantic_clause_fix
    WHERE content_type IN ('OBLIGATION','PROHIBITION')
      AND executor_text IS NOT NULL AND trim(executor_text) <> ''
  ),
  judged AS (
    SELECT COALESCE(s.class_label, '(보류)') AS cls,
           COALESCE(s.decision, 'KEEP_REVIEW') AS dec
    FROM ob
    LEFT JOIN LATERAL sieve_executor(ob.executor_text) s ON true
  )
  SELECT cls, dec, COUNT(*) AS cnt,
         ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(), 1) AS pct
  FROM judged
  GROUP BY cls, dec
  ORDER BY cnt DESC;
$function$
```

## 의존 테이블

| 테이블 | 참조 컬럼 |
|--------|-----------|
| public.legal_sieve_rule | id, sieve_group, target_field, match_type, pattern, verdict, class_label, priority, enabled, stage |
| public.semantic_clause_fix | id, source_article_id, executor_text, action_text, condition_text, cycle_text, content_type, sector |

운영 active rule 수: 2,219건 (2026-10-26 기준)
