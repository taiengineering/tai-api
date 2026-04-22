# 조문 중심 설계 전환 계획 (2026-04-23)

## 배경

**질문**: "조문을 기본 유닛으로 봐야 하지 않을까요?"

**답**: 예. 베테랑이 실제로 다루는 최소 의미 단위는 조문이다.

```
사용자 행동:
  "산안법 제38조에 따라..." (조문 인용)
  "KEC 241.17.3에 의하면..." (조문 인용)
  "별표 1의 제3호..." (조문 인용)

→ 법령은 파일 캐비닛. 조문은 실제 도구.
→ 조문이 곧 의미의 원자(atom).
```

## 현재 설계의 한계

### 법령 단위 upsert의 부작용
```
재수집마다:
  1. law_version 새로 생성 (새 UUID)
  2. law_article DELETE + INSERT (새 UUID)
  3. 외부 참조 (룰, 매핑) 끊어짐

오늘 겪은 일:
  - Atomic Switch에서 UUID 매핑 테이블 필요
  - 매핑 성공률 14~20%
  - 외부 참조 재매핑 3시간
```

### 조문 단위 설계의 효과
```
재수집마다:
  1. law_master UPSERT (UUID 유지)
  2. law_version: 버전번호 같으면 UUID 유지
  3. law_article: (law_id, article_internal_key) UPSERT로 UUID 영구 유지
  4. 외부 참조 안 끊어짐

기대 효과:
  - UUID 매핑 테이블 불필요
  - Atomic Switch도 단순 rename으로 끝
  - 룰 매칭이 DB 레벨에서 견고
```

## 설계 원칙 3가지

### 원칙 1: article_internal_key는 법령 생애 전반 고유
```
기존: (law_version_id, article_internal_key) UNIQUE
     → version 바뀌면 다른 조문 취급

신규: (law_id, article_internal_key) UNIQUE
     → 같은 법령의 같은 조문은 영구적으로 같은 UUID
     → version 바뀌어도 조문은 "제38조"로 동일
```

### 원칙 2: 조문 UPSERT (DELETE+INSERT 폐기)
```python
# 기존 (UUID 파괴적)
DELETE FROM law_article WHERE law_version_id = ?;
INSERT INTO law_article (...) VALUES (...);

# 신규 (UUID 보존)
INSERT INTO law_article (law_id, article_internal_key, ...)
VALUES (...)
ON CONFLICT (law_id, article_internal_key)
DO UPDATE SET
  article_text = EXCLUDED.article_text,
  article_title = EXCLUDED.article_title,
  law_version_id = EXCLUDED.law_version_id,  -- 최신 버전 추적
  updated_at = NOW();
```

### 원칙 3: 조문 변경 이력은 law_article_history
```sql
-- 조문이 버전 간 어떻게 바뀌었는지 추적
CREATE TABLE law_article_history (
  id UUID PK,
  article_id UUID REFERENCES law_article(id),  -- 조문 자체는 동일
  law_version_id UUID REFERENCES law_version(id),  -- 어느 버전인가
  content_hash TEXT,
  article_text TEXT,
  created_at TIMESTAMPTZ
);
-- 같은 article_id 밑에 여러 버전의 content 보관
```

## 단계적 구현

### Phase 2A: 즉시 적용 가능 (오늘)
```
1. law_article에 law_id 컬럼 추가 (denormalized FK)
2. 기존 10,974 조문의 law_id 채우기
3. UNIQUE 제약 변경:
   OLD: (law_version_id, article_internal_key)
   NEW: (law_id, article_internal_key)
4. collect_v2.py의 save_law_to_new_db() UPSERT 방식으로 수정
```

### Phase 2B: NFTC internal_key 안정화
```
현재: "admrul-idx-NNN-sec-X.Y" (idx가 파싱 순서 의존)
개선: "admrul-mst{law_mst_no}-sec{X.Y}-pos{NNN}"
      → law_mst_no 포함으로 법령 간 충돌 방지
      → pos는 여전히 파서 결정론에 의존하되 더 명시적
```

### Phase 2C: law_article_history 추가 (다음 세션)
```
조문 변경 이력 테이블
같은 article_id의 버전별 content 누적
```

## 롤백 가능성

```
현재 law_article 10,974개는 모두 UUID 보유 중
law_id 컬럼 추가는 비파괴적 (NULL 허용)
UNIQUE 변경은 데이터 손실 없음
→ 모든 단계 롤백 가능
```

## 성공 지표

```
Phase 2A 완료 시:
  - law_article에 law_id 컬럼 채워짐 100%
  - (law_id, article_internal_key) UNIQUE 활성화
  - collect_v2.py 재실행 시 UUID 변화 없음
  - 외부 참조 (master_building_legal_rules, law_rule_source_map) 무결성 유지

궁극 목표:
  - 법령 재수집 후에도 조문 UUID 영구 유지
  - Atomic Switch 같은 고통스러운 작업 불필요
  - 룰-조문 매칭이 DB 제약으로 자동 보장
```

## 다음 작업 순서

1. law_article에 law_id 컬럼 추가 (DDL)
2. 기존 조문의 law_id 백필 (DML)
3. 기존 UNIQUE 제거 + 신규 UNIQUE 추가
4. collect_v2.py save_law_to_new_db() 재설계
5. 테스트 재수집 (산업안전보건법 1건)
6. 검증 (UUID 유지 확인)
7. 문제 없으면 Git 커밋
