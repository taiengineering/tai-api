# 법령 _new 테이블 구조 카피 완료 — 2026-04-22

> **세션 연속**: Step 2 (타겟 확정) 이후 Step 3 (수집용 테이블 준비)
> **목적**: 184개 타겟 수집을 위한 빈 구조 테이블 8개 준비

---

## 🎯 작업 목표

```
기존 법령 테이블들을 건드리지 않고, 
_new 버전 8개를 만들어 재수집에 사용한다.
수집 → 검증 완료 후 Atomic Switch로 교체.
```

---

## ✅ 완료된 것

### 1. 8개 _new 테이블 생성

| # | 테이블 | 컬럼 | FK | UNIQUE | 데이터 |
|---|---|---|---|---|---|
| 1 | `law_collection_target_new` | 22 | 1 (self) | 0 | 184 rows |
| 2 | `law_master_new` | 23 | 0 | 1 | 빈 구조 |
| 3 | `law_version_new` | 16 | 1 | 1 | 빈 구조 |
| 4 | `law_content_raw_new` | 12 | 1 | 1 | 빈 구조 |
| 5 | `law_article_new` | 17 | 1 | 2 | 빈 구조 |
| 6 | `law_paragraph_new` | 10 | 1 | 2 | 빈 구조 |
| 7 | `law_item_new` | 12 | 2 | 2 | 빈 구조 |
| 8 | `law_attachment_new` | 11 | 2 | 1 | 빈 구조 |

### 2. 계층 구조 (FK 관계)

```
law_master_new (23컬럼)
  └─ law_version_new (16컬럼) [FK: law_id]
        ├─ law_content_raw_new (12컬럼) [FK: law_version_id]
        ├─ law_article_new (17컬럼) [FK: law_version_id]
        │     ├─ law_paragraph_new (10컬럼) [FK: article_id]
        │     │     └─ law_item_new (12컬럼) [FK: paragraph_id + parent_item_id 자기참조]
        │     └─ law_attachment_new (11컬럼) [FK: parent_article_id]
        └─ law_attachment_new [FK: law_version_id]

law_collection_target_new
  └─ self-ref [FK: parent_law_id] (모법-시행령-시행규칙 관계)
```

### 3. CASCADE 정책
```sql
ON DELETE CASCADE

→ 법령 삭제 시 관련 데이터 모두 자동 정리
→ 재수집 시 기존 데이터 덮어쓰기 쉬움
```

---

## 🔧 개선 사항 (기존 대비)

### ⭐ 중복 방지 UNIQUE 제약 추가 (기존에 없던 것)

| 테이블 | UNIQUE 제약 | 목적 |
|---|---|---|
| law_master_new | `(law_api_id, law_mst_no)` | **중복 80그룹의 근본 원인 제거** |
| law_version_new | `(law_id, version_no)` | 같은 버전 중복 방지 |
| law_content_raw_new | `(law_version_id)` | 버전당 원본 1개만 |
| law_article_new | `(law_version_id, article_no, article_sub_no)` | 조문 중복 방지 |
| law_article_new | `(law_version_id, article_internal_key)` | 안전장치 |
| law_paragraph_new | `(article_id, paragraph_no)` | 항 중복 방지 |
| law_paragraph_new | `(article_id, paragraph_internal_key)` | 안전장치 |
| law_item_new | `(paragraph_id, parent_item_id, item_no)` | 호/목 중복 방지 |
| law_item_new | `(paragraph_id, item_internal_key)` | 안전장치 |
| law_attachment_new | `(law_version_id, attachment_no, attachment_type_code)` | 별표 중복 방지 |

### ⭐ UPSERT 지원 구조
이제 Python 수집 스크립트에서 `ON CONFLICT ... DO UPDATE` 사용 가능:
```sql
INSERT INTO law_master_new (...) VALUES (...)
ON CONFLICT (law_api_id, law_mst_no) 
DO UPDATE SET 
  law_name = EXCLUDED.law_name,
  announcement_date = EXCLUDED.announcement_date,
  updated_at = NOW();
```

---

## 📊 왜 UNIQUE 제약이 중요한가

### Before (기존 law_master)
```
PRIMARY KEY(id) 만 있음
UNIQUE(law_key) 있지만 law_key가 NULL이면 무시

→ 같은 법령(예: NFTC 606)이 2번 수집되어도 
   id가 달라서 INSERT 성공
→ 결과: 중복 80 그룹, 레코드 낭비 88개
```

### After (law_master_new)
```
UNIQUE(law_api_id, law_mst_no) 추가

→ 같은 (api_id, mst_no) INSERT 시도 시 충돌
→ UPSERT로 안전하게 덮어쓰기
→ 중복 발생 불가능
```

---

## 🎯 마이그레이션 이력

```
1. 20260422_create_law_collection_target_new     — 타겟 테이블
2. 20260422_create_law_tables_new_structure      — 7개 테이블 구조 카피
3. 20260422_add_fk_to_law_new_tables             — FK 관계 복원 (CASCADE)
4. 20260422_add_unique_to_law_new_tables_v2      — UNIQUE 제약 추가
```

---

## 💾 기존 테이블은 그대로 유지

```
현재 운영 중인 서비스 테이블:
  - law_master (350 active)
  - law_version (557)
  - law_content_raw (557)
  - law_article (33,644)
  - law_paragraph (51,118)
  - law_item (37,631)
  - law_attachment (4,907)

→ 서비스 영향 0
→ Python 재수집은 _new 테이블에만 진행
→ 검증 완료 후 Atomic Switch로 교체
```

---

## 🎯 다음 단계

### Step 4: Python 수집 스크립트 작성
```
기반: scripts/all_laws_recollect.py 개선
읽기: law_collection_target_new (184개 타겟)
쓰기: law_master_new → law_version_new → ... (UPSERT)

유닛 단위 흐름:
  1. 타겟 하나 읽기
  2. 법제처 API 호출
  3. 원본 XML → law_content_raw_new
  4. 파싱 → law_master_new/version_new/article_new/...
  5. 검증 체크리스트 실행
  6. collection_status 업데이트
  7. 다음 유닛
```

### Step 5: 수집 실행
```
- 161개 API_ID 확보된 법령 → 자동 수집
- 23개 API_ID 없는 법령 → 법령명 기반 검색 후 수집
- 유닛별 검증 결과 law_collection_target_new.verification_checklist에 기록
```

### Step 6: Atomic Switch
```sql
BEGIN;
  -- 백업용 rename
  ALTER TABLE law_master RENAME TO law_master_old_20260423;
  ALTER TABLE law_version RENAME TO law_version_old_20260423;
  -- ... 나머지 6개
  
  -- _new를 정식으로 승격
  ALTER TABLE law_master_new RENAME TO law_master;
  ALTER TABLE law_version_new RENAME TO law_version;
  -- ... 나머지 6개
  
  -- FK 이름도 정리
  ALTER TABLE law_version 
    RENAME CONSTRAINT law_version_new_law_id_fkey TO law_version_law_id_fkey;
  -- ...
COMMIT;

-- 1주일 후 _old 테이블 정리
```

---

## 📌 참고

### `LIKE ... INCLUDING ALL` 동작
```
CREATE TABLE law_master_new (LIKE law_master INCLUDING ALL)

복사되는 것:
  ✅ 컬럼 (이름, 타입, NOT NULL)
  ✅ 기본값
  ✅ CHECK 제약
  ✅ 인덱스 (PRIMARY KEY 포함)
  ✅ 코멘트

복사 안 되는 것:
  ❌ FK 제약 (수동 추가 필요) ← 별도 마이그레이션으로 추가함
  ❌ 트리거
  ❌ RLS 정책
  ❌ 시퀀스 소유권
```

### 법제처 API 오류 처리 방안
```
Python 수집 시 예상 오류:
  1. API_ID 무효 → law_collection_target_new.remarks 업데이트
  2. 네트워크 오류 → 재시도 로직
  3. XML 파싱 실패 → law_content_raw_new에는 저장 (원본 보존)
  4. 부분 파싱 성공 → valid_pct 기록
```
