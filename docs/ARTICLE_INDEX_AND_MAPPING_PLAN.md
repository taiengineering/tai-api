# 조문 인덱스 + 매핑 단계적 구축 (2026-04-23)

## 배경

**사용자 판단**: 전체 182개 법령 재수집은 무리한 작업.
**실제 상황**: 이미 저장된 데이터에 법제처 공식 조문 코드값이 89.3% 존재.

```
현재 10,974 조문:
  ✅ 법제처 공식 조문키 (9,796건, 89.3%) - 재수집 불필요
  🟡 NFTC/NFPC 생성키 (855건, 7.8%) - raw_xml에서 재파싱만
  🟡 admrul 구버전키 (323건, 2.9%) - raw_xml에서 재파싱만

→ API 호출 0, 순수 DB 작업으로 완성 가능
```

## 법제처 조문키 형식

```
7자리 숫자: AAAA-BB-C
  AAAA: 조문번호 (0001, 0002, ..., 0822)
  BB:   조문의N 구분 (00=장표시, 01=1항, 02=의2, 03=의3)
  C:    본문/부칙 구분 (0=타이틀, 1=본문)

예시:
  0001000  = 제1장 총칙 (전문)
  0001001  = 제1조(목적)
  0004001  = 제4조
  0004021  = 제4조의2
  0004031  = 제4조의3
  0038001  = 제38조(본문)
  0038021  = 제38조의2(개정)
```

## 단계별 실행 (API 호출 없음)

### Phase A: 조문 키 정합성 검증 (DB only)
```
현재 법제처 공식키를 가진 9,796건이 실제로 raw_xml의 조문키와 일치하는지 확인.
SQL로 raw_xml 파싱 가능한지 먼저 검토.
불일치 있으면 정정.
```

### Phase B: NFTC/NFPC 조문키 정규화
```
현재 "admrul-idx-001-sec-1.1" 패턴을 검토:
  - 같은 법령 내에서 유일한가? (이미 UNIQUE 통과 확인됨)
  - 재파싱해도 같은 값 나오는가? (파서 재현성)

결정: 현재 키 유지 (재파싱 불필요)
     - 이미 UNIQUE 제약 통과
     - 파서가 동일 XML에서 동일 순서로 생성
```

### Phase C: 외부 참조 매핑 강화
```
master_building_legal_rules 2,556 룰을 조문 단위로 연결:

현재 (TEXT 기반):
  rule_id: R001
  law_name: "산업안전보건법"
  law_article: "제38조"

목표 (UUID 기반):
  rule_id: R001
  law_id: <UUID>
  article_id: <UUID>
  article_internal_key: "0038001"

매핑 방법:
  1. (law_name, law_article) → law_article 테이블 JOIN
  2. 매칭 성공 2,275건 (89%) → article_id 저장
  3. 매칭 실패 281건 → 별도 테이블 기록 (수동 검토)
```

### Phase D: 매핑 테이블 설계
```sql
-- 룰-조문 매핑 테이블 (신규)
CREATE TABLE rule_article_mapping (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_id TEXT REFERENCES master_building_legal_rules(rule_id),
  law_id UUID REFERENCES law_master(id),
  article_id UUID REFERENCES law_article(id),
  article_internal_key TEXT,  -- 안정 키 (UUID 대비 fallback)
  mapping_source TEXT,         -- 'auto_by_name', 'manual', etc
  confidence_score NUMERIC,    -- 매칭 신뢰도 (0-1)
  created_at TIMESTAMPTZ,
  verified_at TIMESTAMPTZ      -- 수동 검증 일시
);

CREATE INDEX ON rule_article_mapping(rule_id);
CREATE INDEX ON rule_article_mapping(article_id);
CREATE INDEX ON rule_article_mapping(law_id);
```

## 핵심 가치

### 왜 이 접근이 맞는가
```
1. API 호출 0 → 법제처 부담 없음
2. 기존 데이터 유지 → 안전
3. 부분 성공 허용 → 매칭 실패는 별도 관리
4. 점진적 개선 → 한 번에 다 할 필요 없음

vs. 전체 재수집:
   - API 부담 ↑
   - 시간 소요 ↑
   - UUID 변화 위험
   - 이미 완성된 89%를 다시 할 이유 없음
```

## 실행 순서

```
1. Phase A (Phase B 무시 가능):
   현재 9,796건 공식키 신뢰 → 바로 Phase C로
   
2. Phase C (핵심):
   master_building_legal_rules ↔ law_article 매핑
   예상 성공률 89%
   
3. Phase D:
   law_rule_source_map도 조문 UUID로 강화
   (현재 48건만 유효 FK, 나머지 NULL)

4. 검증:
   - 매핑 품질 점검
   - 매칭 실패 건 분석
   - 베테랑 관점에서 "룰 클릭 → 조문 즉시 표시" 확인
```

## 다음 세션 준비

```
이번 세션 완료 시:
  ✅ 182개 법령 Atomic Switch 완료
  ✅ 조문 중심 설계 스키마 (law_id 컬럼, UNIQUE)
  ✅ 조문 공식 키 89% 확보 확인
  
다음 세션:
  1. Phase C 실행: master_building_legal_rules 매핑
  2. Phase D 실행: rule_article_mapping 테이블 구축
  3. API 레벨 통합: "룰 조회 시 조문 함께 반환"
```
