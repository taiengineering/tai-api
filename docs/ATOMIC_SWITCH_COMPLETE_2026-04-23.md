# Atomic Switch Complete - 2026-04-23

## Purpose
Promote _new tables to production law engine tables.

## Result
- Full success, data integrity maintained
- 182 laws / 60,636 records in production

## Execution Summary

### UUID Mapping Table
_migration_uuid_map_20260423 created:
- law_master: 473 to 99 matched (21%)
- law_version: 557 to 95 matched (17%)
- law_article: 30,827 to 4,325 matched (14%)

### Backup (6 tables)
- law_rule_drafts_preswitch_20260423 (3,073)
- law_rule_source_map_preswitch_20260423 (49)
- law_update_tracking_preswitch_20260423 (470)
- law_parsing_result_preswitch_20260423 (469)
- law_change_log_preswitch_20260423 (34)
- law_master_preswitch_20260423 (473)

### Drop 20 External FK Constraints
Affected tables: law_article_diff, law_change_log, law_parsing_result, law_rule_drafts, law_rule_source_map, law_update_tracking

### Atomic Rename
old tables -> _old_20260423
_new tables -> production names

### Relax Constraints
- law_rule_source_map.law_id: DROP NOT NULL
- law_update_tracking.law_id: DROP UNIQUE

### UUID Remapping + article_no Fallback
external FK columns converted via mapping table
law_rule_source_map.article_id: 0 to 48 recovered using article_no based matching

### Recreate FK with SET NULL policy

## Verification

### Forward
- law_master: 182
- law_version: 182
- law_content_raw: 182
- law_article: 10,974
- law_paragraph: 20,125
- law_item: 28,813

### Backward (Orphans)
All 0 - perfect integrity

### External Reference Recovery
- law_rule_drafts: 266/3,073 valid
- law_rule_source_map: 48/49 law, 48/49 article
- law_update_tracking: 99/470 valid
- law_parsing_result: 52/469 valid
- law_change_log: 9/34 valid
- master_building_legal_rules: 2,556 (TEXT-based, no impact)

## Backup Tables (cleanup in 1 week)

Legacy law tables:
- law_master_old_20260423 (473)
- law_article_old_20260423 (30,827)
- (and 6 more)

## Next Steps

### 1-week Monitoring
- Law engine function tests
- factory_diagnosis_results connection
- master_building_legal_rules accuracy
- Error log monitoring

### After 1 Week
- Drop _old_20260423 tables
- Drop _preswitch_20260423 tables
- Drop _migration_uuid_map_20260423

### Phase 3
- Attachment collection (admrul_attachment API)
- NFTC/NFPC fine-grained parsing
- KEC PDF collection system
- Auto-update reactivation

## Lessons

1. Simple rename is destructive with external references - UUID mapping essential
2. article_internal_key varies by parser - stable keys needed
3. Match failures are history, not errors - NULL is the answer
4. Backups provide breathing room
5. Focused office hours beat late-night fatigue
