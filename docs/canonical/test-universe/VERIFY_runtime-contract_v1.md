---
wo: WO-WIRING-002
class: records
type: verification
scope: canonical
project: test-universe
title: Runtime Contract Verification
version: 1
status: active
owner: taiwang
---

# RUNTIME CONTRACT VERIFICATION — WO-WIRING-002

> _load_sector_allowed_draft_ids()가 law_sector_mapping을 어떤 계약(Contract)으로 사용하는지 복원. **Pattern 주입 위치 논의 없음. 코드 수정 0.** Runtime이 기대하는 입력만 확인.
> 엔진 코드 taiengineering/tai-api.

## 판정: Contract Complete

## STEP 1 — _load_sector_allowed_draft_ids() 정독
```text
파일 : services/anonymous_factory_service.py
입력 : (supabase, sector_value: str)
출력 : Optional[Set[str]]   # 허용 draft_id 집합, None이면 필터 미적용(전체평가) 폴백

SELECT 순서:
 (0) key = to_mapping_sector(sector_value)  # 빈값이면 return None
 (1) fetch_executable_draft_articles [engine_isolated.executable_draft]
       SELECT id, article_id · WHERE article_id NOT NULL · ORDER id · RANGE(page)
       → draft_article[draft]=article, 빈결과면 return None
 (2) law_article.select("id, law_id").in_("id", chunk)  [public.law_article]
       → article_law[article]=law_id
 (3) law_sector_mapping.select("law_id, sectors").in_("law_id", chunk)  [public.law_sector_mapping] ★
       → law_sectors[law_id]=[sectors 대문자], 비면 return None(폴백)
 (4) draft별 통과 판정:
       law_id 없음 → 통과(연결 끊김 보수적) · sectors 없음(미매핑) → 통과(누락방지)
       key ∈ sectors → 통과 · else → 제외(타 sector 전용)
RETURN : allowed(Set[draft_id])

WHERE : article_id NOT NULL · id IN(chunk) · law_id IN(chunk)
JOIN(수동): executable_draft.article_id→law_article.id, law_article.law_id→law_sector_mapping.law_id
ORDER : executable_draft.id (페이지네이션 결정성)
```

## STEP 2 — law_sector_mapping 실제 사용 컬럼
```text
SELECT: law_id, sectors  (딱 2개)
  law_id  : 조인 키 (law_article.law_id ← law_sector_mapping.law_id)
  sectors : 문자열 배열, key 포함 여부로 통과 판정
표준값 : BUILDING / INDUSTRIAL / CONSTRUCTION / SPECIAL_FACILITY
안 읽음 : enabled·priority·draft_id 등 (이 함수는 law_id·sectors만)
```

## STEP 3 — Contract
```text
Input site_kind (건설/제조/건물/기타)
  ↓ SECTOR_BY_KIND
sector (CONSTRUCTION/MANUFACTURING/BUILDING/SPECIAL_FACILITY)
  ↓ create_temp_factory: normalize_sector_db → factories.sector
  ↓ evaluate_single_factory: sector_value = factory["sector"]
  ↓ to_mapping_sector → key
law_sector_mapping  [key ∈ sectors 인 law_id 통과]
  ↓ executable_draft → law_article → law_sector_mapping (3단 수동 조인)
allowed_draft_ids (Set)
  ↓ _load_draft_slot_groups
compiler (evaluate_draft_for_facility → fetch_compiler_candidates)

★ 계약 핵심 단위: law_sector_mapping = 'law_id → sectors[]'
  계약이 기대하는 것은 '법령(law_id) 단위의 sector 배열'.
```

## STEP 4 — Dependency (allowed_draft_ids 끝까지)
```text
allowed_draft_ids (producer: _load_sector_allowed_draft_ids)
 → _load_draft_slot_groups: draft_id not in allowed → continue(제외)
 → evaluate_draft_for_facility [facility_applicability_eval] → MATCH/POSSIBLE
 → insert_facility_applicability [engine_isolated.facility_applicability]
 → fetch_compiler_candidates → _compiler_result_to_step1_format → 응답
소비 끝점: 진단 응답의 rules/obligations
```

## STEP 5 — Runtime Contract
```text
Producer     : law_sector_mapping (law_id, sectors[]) DB 데이터
               + _load_sector_allowed_draft_ids (allowed_draft_ids 생성)
Consumer     : _load_draft_slot_groups → evaluate_draft_for_facility → compiler → 응답
Ownership    : law_sector_mapping = public 스키마 (법령분류 표준, CHG 이력 존재)
               draft/slot/applicability = engine_isolated 스키마 (compiler_engine_gateway 전용)
Update Point : law_sector_mapping 행 추가/수정 (law_id ↔ sectors)
               → 사업장 sector에 걸리는 법령 집합이 바뀜
```

## STEP 6 — 판정: Contract Complete
```text
계약 완전 복원:
  Input → sector → key → law_sector_mapping(law_id→sectors[]) → allowed_draft_ids
  → draft 평가 → compiler → 응답
  기대 단위: law_id 단위 sectors[] · 컬럼: law_id, sectors
```

## 관측된 계약 사실 (판단·제안 아님)
- law_sector_mapping이 기대하는 것: **법령(law_id)에 sector 배열 매핑.**
- Runtime 규칙: 사업장 sector key가 그 배열에 있으면 그 법령의 draft를 통과.
- 스키마 경계: 법령분류(public) ↔ compiler 자산(engine_isolated) 분리. gateway가 유일 접점.

## Exit Criteria 점검
```text
[v] _load_sector_allowed_draft_ids 정독 (입력·출력·SELECT·WHERE·JOIN·ORDER·RETURN)
[v] law_sector_mapping 사용 컬럼 (law_id, sectors)
[v] Contract 작성 (site_kind→sector→law_sector_mapping→allowed_draft_ids→compiler)
[v] Dependency (allowed_draft_ids 소비 끝점까지)
[v] Runtime Contract (Producer·Consumer·Ownership·Update Point)
[v] 판정 (Contract Complete)
```

## 규율 준수
- Pattern 주입 위치 미논의 · Injection Point 미작성 · Wiring Plan 미작성 · 코드 수정 0.
- 다음(별도): 계약 확정됨 → 이후에야 어디를 수정할지(Injection Point) 논의 가능.

## 상태
```text
STEP1 무엇을 읽는가       ✓ WO-WIRING-001 STEP1
STEP2 무엇을 기대하는가   ✓ WO-WIRING-002 (Contract Complete: law_id→sectors[]) ← 현재
다음(별도)               : Injection Point Discovery
```
