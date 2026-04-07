# 법령엔진 작업지시서 — inspection_set_items 자동 매핑
**날짜: 2026-04-07 | 담당: 법령엔진 창 | 저장소: tai-api**

---

## 배경

현재 `inspection_sets` 296건이 있으나 `inspection_set_items`는 0건.
점검 일정이 잡혀 있어도 "뭘 점검하라는 건지" 항목이 없어서,
안전관리자가 점검 화면에 들어가면 빈 화면을 보게 됨.

법령엔진에 룰(obligation_summary, law_name, law_article)이 이미 있으므로
이를 기반으로 점검 항목을 자동 생성하는 API 작성.

---

## 작업: inspection_set_items 자동생성 API

### 엔드포인트
```
POST /inspection-sets/{set_id}/generate-items
```

또는 전체 일괄 처리:
```
POST /inspection-sets/generate-all-items
```

### 로직
1. `inspection_sets` 조회 (legal_rule_id가 있는 것)
2. 해당 legal_rule_id로 `master_building_legal_rules`에서 룰 정보 조회
3. 룰 1건당 `inspection_set_items` 1건 생성:
   ```
   {
     inspection_set_id: set.id,
     item_name: rule.obligation_summary,
     item_description: f"{rule.law_name} {rule.law_article}",
     check_type: 'PASS_FAIL',  -- 기본값
     is_required: true,
     sort_order: 1
   }
   ```
4. 이미 items가 있는 set_id는 스킵
5. 생성 건수 반환

### 파일 위치
`routers/inspection_sets.py` 또는 관련 라우터 파일 확인 후 추가

---

## 추가 작업: inspection_set_items 테이블 컬럼 확인

작업 전 반드시 실행:
```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'inspection_set_items'
ORDER BY ordinal_position;
```

컬럼 구조 확인 후 INSERT 필드 맞춰서 작성.

---

## 점검 항목 기본 템플릿 (법령별)

룰의 obligation_type 기준으로 check_type 분기:

| obligation_type | check_type | 설명 |
|---|---|---|
| INSPECT | PASS_FAIL | 정상/이상 |
| APPOINT | CHECK | 선임 여부 확인 |
| REPORT | DATE | 제출일 기록 |
| ACTION | PASS_FAIL | 조치 완료 여부 |

---

## 검증 방법

```sql
-- 실행 전
SELECT count(*) FROM inspection_set_items; -- 0

-- API 호출 후
SELECT count(*) FROM inspection_set_items; -- 양수

-- 샘플 확인
SELECT isi.item_name, is2.inspection_set_name
FROM inspection_set_items isi
JOIN inspection_sets is2 ON isi.inspection_set_id = is2.id
LIMIT 10;
```

---

## 주의사항
- `inspection_sets`에 `legal_rule_id`가 NULL인 경우 스킵 (MANUAL 등록 건)
- 법령엔진 master_building_legal_rules의 is_active=True 조건 필수
- 한 inspection_set에 items가 이미 있으면 덮어쓰지 않음
