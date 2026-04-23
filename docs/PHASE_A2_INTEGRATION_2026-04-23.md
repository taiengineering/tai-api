# Phase A-2 완료: 조문 본문 통합 (v5.8.0) — 2026-04-23

## 작업 분배

```
🤖 Claude (완료)           👤 Cursor (다음 작업)
━━━━━━━━━━━━━━━━━━━      ━━━━━━━━━━━━━━━━━━━
✅ 코드 수정 4파일         ⏳ git pull + import 확인
✅ 엔진 버전 5.8.0 반영    ⏳ 로컬 API 호출 테스트
✅ 하위 호환 유지            ⏳ DB 저장 검증
✅ Cursor 체크리스트 문서     ⏳ 배포 결정
```

## 통합 내역

### 1. services/legal_runtime.py

`_save_diagnosis_result` 수정:
```diff
+ from services.legal_article_loader import fetch_article_contexts

  def _save_diagnosis_result(supabase, factory_id, sector, stage, input_data, matched_rules):
+     # v5.8.0: 조문 본문 배치 조회
+     rule_ids = [r.get("rule_id") for r in matched_rules if r.get("rule_id")]
+     article_ctx = fetch_article_contexts(supabase, rule_ids) if rule_ids else {}
      
      rules_with_article = []
      for r in matched_rules:
+         art = article_ctx.get(mapping_key) or {}
          rules_with_article.append({
              # ... 기존 필드 ...
+             "article_id":            art.get("article_id"),
+             "article_internal_key":  art.get("article_internal_key", ""),
+             "article_title":         art.get("article_title", ""),
+             "article_text":          art.get("article_text", ""),
+             "article_type":          art.get("article_type", ""),
+             "law_system":            art.get("law_system", "NOT_MAPPED"),
+             "has_article_text":      bool(art.get("article_text")),
          })
```

`run_apply_engine_runtime`, `run_apply_quote_runtime` 수정:
- `build_result(..., supabase=supabase)` 전달

### 2. services/legal_step1_builder.py

`build_step1_result_data` 수정:
```diff
  def build_step1_result_data(..., construction_summary_fn, supabase=None):
+     # v5.8.0: 조문 본문 배치 조회
+     article_ctx = None
+     if supabase is not None:
+         rule_ids = [r.get("rule_id") for r in applicable if r.get("rule_id")]
+         if rule_ids:
+             article_ctx = fetch_article_contexts(supabase, rule_ids)
+     
+     try:
+         classify_rules_db_fn(applicable, triggered, article_ctx)
+     except TypeError:
+         classify_rules_db_fn(applicable, triggered)

+     # 매핑 통계
+     result_data["article_mapping_stats"] = {
+         "total_rules": total_applicable,
+         "mapped_rules": mapped_count,
+         "coverage_pct": ...
+     }
```

### 3. services/legal_engine_svc.py

- `ENGINE_VERSION = "5.8.0"`
- `run_diagnose_step1`: `build_step1_result_data(..., supabase=supabase)`
- `run_diagnose_step2/3`: 응답에 `article_mapping_stats` 포함

### 4. routers/legal_engine.py

- `ENGINE_VERSION = "5.8.0"`

## 새 엔진 응답 구조

### factory_diagnosis_results.result_data.rules[i]

```json
{
  "rule_code": "OSHSTD-008-MFG",
  "rule_name": "안전조치 의무",
  "law_name": "산업안전보건기준에 관한 규칙",
  "law_article": "제50조",
  "obligation": "의무 (..제50조)",
  "rule_type": "APPOINTMENT",
  "stage": 1,
  
  // ⭐ v5.8.0 신규 필드
  "article_id": "e287bdbc-...",
  "article_internal_key": "0050001",
  "article_title": "관리감독자의 유해・위험 방지 업무",
  "article_text": "제50조(관리감독자의...) ① 사업주는...",
  "article_type": "본칙",
  "law_system": "LEGAL",
  "has_article_text": true
}
```

### factory_diagnosis_results.result_data.article_mapping_stats

```json
{
  "total_rules": 15,
  "mapped_rules": 13,
  "coverage_pct": 86.7
}
```

## 상위 호환성

- `supabase=None` 전달 시 기존 동작 (article 필드 빈 값)
- `classify_rules_db_fn` TypeError 폴백으로 구 버전 호환
- 기존 진단 결과 43건 영향 없음 (열엄 JSON 추가만)

## 결론

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Phase A-2 구현 완료
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  코드 작업: ✅ 4파일 수정 + 커밋
  테스트: ⏳ Cursor에서 실행 필요
  배포: ⏳ 테스트 통과 후
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 다음으로

CURSOR_TASKS_2026-04-23.md 참고.
