---
wo: WO-CHG-009
class: records
type: deployment
scope: canonical
project: test-universe
title: Pattern Dictionary 운영 DB 반영 (SQL 준비)
version: 1
status: active
owner: taiwang
---

# PATTERN DICTIONARY 운영 DB 반영 — SQL 준비 (WO-CHG-009)

> 검증 완료 Pattern Dictionary·Role Mapping을 운영 DB에 반영하기 위한 SQL 준비.
> **핵심 경계:** 클라우드 샌드박스는 운영 엔진 DB(Supabase) 도달 불가. assistant는 STEP1-3(Snapshot 검증·Dry Run·Apply용 SQL 생성)까지. **STEP4 Apply는 운영자 Mac(~/45cm-test) psql 실행. Post Validation은 운영자 결과를 받아 검증.** Apply 완료를 허위 주장하지 않음.

## 판정: STEP1-3 준비 완료 (Apply/Post는 운영자 실행 대기)

## STEP 1 — Deployment Snapshot Verification
```text
Pattern Dictionary  de58bdca9fb911ce == snapshot  [동일]
Role Pattern (v2)   9968bbf658491284 == snapshot  [동일]
Resolved Dataset    ce885723f9a1fe8f == snapshot  [동일]
Unresolved Queue    b7bc28b86bdf7296 == snapshot  [동일]
```
- 불일치 0 → STOP 조건 아님, 진행. Snapshot FP03-DEPLOY-001 @ 2026-08-01T12:14Z.

## STEP 2 — Dry Run (적용 예정 변경)
기존 스키마에 pattern_dictionary·role_mapping 없음 → CREATE + INSERT.
```text
pattern_dictionary : CREATE TABLE 1 · INSERT 13 · UPDATE 0 · DELETE 0 · UNCHANGED 0
role_mapping       : CREATE TABLE 1 · INSERT 14 · UPDATE 0 · DELETE 0 · UNCHANGED 0
```

## STEP 3 — Change Review (문서와 동일)
```text
예상 INSERT : pattern_dictionary 13 (==문서 13) · role_mapping 14 (==문서 14)
예상 Drift  : 0 (신규 테이블)
Queue 영향  : 0 (Unresolved Queue는 이 CHG 대상 아님)
```
- 주의: 이 테이블들은 **Role 층(규율대상/시설)** 자산. 기존 law_sector_mapping(sector 층)과 별개 — 덮어쓰지 않음.

## Apply용 SQL (chg009_apply.sql, 운영자 Mac 실행)
```text
구조: BEGIN → CREATE TABLE IF NOT EXISTS ×2 → TRUNCATE ×2 → INSERT ×27 → 검증쿼리 → COMMIT
idempotent: 재실행 시 TRUNCATE 후 재삽입(중복 없음).
pattern_dictionary: pattern_id PK·pattern_type·trigger·role·source_wo·deployed_at
role_mapping: id·law_name·value·role·pattern_id·evidence_articles·source_wo·deployed_at
실행: cd ~/45cm-test && psql "$ENGINE_DB_URL" -f chg009_apply.sql
```

## STEP 4 — Apply (운영자 실행 대기)
- **assistant 실행 불가** (샌드박스 운영 DB 도달 불가). 운영자가 Mac에서 chg009_apply.sql 실행.
- 허용 반영: pattern_dictionary·role_mapping. 금지: 새 Pattern/Rule/Exception/Taxonomy/Discovery.

## STEP 5 — Post Apply Validation (운영자 실행 후)
- SQL 말미 검증쿼리 결과(pattern_dictionary 13·role_mapping 14)를 assistant에 전달 → checksum·row count·Drift 0 검증.
- 이 단계는 운영자 실행 결과 수령 후 별도 확인.

## Exit Criteria (현 세션 범위)
```text
[v] STEP1 Snapshot Verification (checksum 동일, STOP 아님)
[v] STEP2 Dry Run (INSERT 13+14, UPDATE/DELETE 0)
[v] STEP3 Change Review (문서와 동일, Drift 0)
[v] Apply용 SQL 생성 (idempotent, DDL+INSERT)
[ ] STEP4 Apply — 운영자 Mac 실행 대기
[ ] STEP5 Post Validation — 운영자 결과 수령 후
[v] 신규 Pattern/Rule/Discovery 0
```

## 결론
- STEP1-3 완료 + Apply용 SQL 준비. **운영 DB 반영은 운영자 Mac 실행이 필요** — assistant는 SQL 생성까지가 정직한 경계.
- Apply 후 운영자가 검증쿼리 결과를 전달하면 Post Validation 수행.
- **주의(R-01 승계):** 이 반영은 Role 층 자산이지 sector 최종 산출이 아님. sector 매핑(law_sector_mapping)은 별도 판단 층.

## 전체 흐름
```text
Discovery → Correction → Acceptance → Deploy(문서) ✓
  → CHG(운영 DB): SQL 준비 ✓ / Apply 운영자 대기 ← 현재
  → Post Validation → Operational Freeze
```
