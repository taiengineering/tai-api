/**
 * TAI Rule↔Doc Mapper — Claudeception 매핑 도구
 * 
 * 사용법:
 * 1. claude.ai 아티팩트로 실행 (React JSX)
 * 2. 텍스트 영역에 룰 JSON 붙여넣기: [{"i":"uuid","f":"FIRE","o":"의무내용","t":"NOTIFY"},...]
 * 3. 법 계열 버튼 클릭 → "Claude API 매핑 실행"
 * 4. 결과 검토 (체크박스 승인/거부) → "SQL 생성" → 복사
 * 5. Supabase에서 SQL 실행
 * 
 * 룰 데이터 추출 쿼리:
 * SELECT json_agg(json_build_object(
 *   'i', id, 'f', '<FAMILY>', 'o', LEFT(obligation_summary, 60), 't', obligation_type
 * )) FROM law_rule_drafts
 * WHERE id NOT IN (SELECT rule_id FROM rule_doc_mapping)
 *   AND law_name LIKE '%키워드%'
 *   AND (obligation_summary LIKE '%보고%' OR obligation_summary LIKE '%신고%' ...);
 * 
 * 법 계열 코드:
 * OSH=산안법, OSH_R=안전보건규칙, FIRE=소방법, ELEC=전기안전, ELEV=승강기,
 * CHEM=화학물질, HGAS=고압가스, HZMT=위험물, SERA=중대재해, LPG, UGAS=도시가스,
 * DSMT=재난안전, ETC=기타
 */

// 이 파일은 claude.ai의 아티팩트(React JSX)로 실행됩니다.
// 전체 소스는 docs/HANDOFF_RULE_DOC_MAPPING.md 참조.
// 아티팩트에서 사용할 때는 /mnt/user-data/outputs/rule_doc_mapper.jsx 를 참조하세요.

console.log('Rule Doc Mapper - see HANDOFF_RULE_DOC_MAPPING.md for usage');
