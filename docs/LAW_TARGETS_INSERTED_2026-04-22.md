# law_collection_target_new 생성 완료 — 2026-04-22

> **세션 연장**: 법령엔진 재수집 Kickoff (commit 23c5aa53) 이후 작업
> **단계**: Step 2 완료 (타겟 확정)

---

## 🎯 작업 목표 (8단계 방식 적용)

```
0. 목표 설정: 구매자 만족 + 안전관리의 심장
1. 자료수집: 현재 DB 구조 파악
2. 분석:     중복/고아/개정일 분석
3. 문제파악: 77개 구 타겟 부족, 신규 4개 도메인 필요
4. 해결방안: _new 테이블로 데이터 없이 구조 카피 + 검증
5. 실행:     184개 타겟 INSERT ← 이 문서
6. 검증:     도메인별/API_ID 매칭 확인 완료
7. 반복:     다음 단계 준비
```

---

## ✅ 완료 사항

### 1. `law_collection_target_new` 테이블 생성
- **위치**: Supabase `xntdkrjhgcscmqctdzyo`
- **마이그레이션**: `20260422_create_law_collection_target_new`
- **구조**: 22개 컬럼 (기존 12개 + 신규 10개)

### 2. 신규 추가 컬럼 10개

| 컬럼 | 타입 | 용도 |
|---|---|---|
| `ministry_name` | TEXT | 소관 부처 (유닛 검증용) |
| `law_api_mst_no` | TEXT | 법제처 마스터번호 (개정 추적) |
| `series_category` | TEXT | NFTC/NFPC 카테고리 분류 |
| `added_in_phase` | TEXT | 타겟 추가 단계 (PHASE_1/2/3) |
| `collection_status` | TEXT | 수집 상태 (PENDING/IN_PROGRESS/SUCCESS/FAILED/SKIPPED) |
| `last_collected_at` | TIMESTAMP | 마지막 수집 시각 |
| `last_collection_result` | JSONB | 수집 결과 요약 |
| `expected_article_count` | INTEGER | 예상 조문 수 (이상 감지) |
| `verification_checklist` | JSONB | 유닛 검증 체크리스트 |
| `parent_law_id` | UUID | 모법-시행령-시행규칙 참조 |

### 3. CHECK 제약 조건 6개
```sql
- law_type_code: LAW / ENFORCEMENT_DECREE / ENFORCEMENT_RULE / NOTICE / STANDARD / ADMINISTRATIVE_RULE
- domain_code: 11개 도메인 (BUILDING/CONSTRUCTION/INDUSTRIAL_SAFETY/FIRE/GAS/ELECTRIC/CHEMICAL/ENERGY/ENVIRONMENT/DISASTER/LABOR)
- collection_priority: 1 / 2 / 3
- collection_method: API / MANUAL / CRAWL
- added_in_phase: PHASE_1 / PHASE_2 / PHASE_3
- collection_status: PENDING / IN_PROGRESS / SUCCESS / FAILED / SKIPPED
```

### 4. 인덱스 5개
```sql
- idx_lct_new_law_name
- idx_lct_new_domain
- idx_lct_new_status
- idx_lct_new_api_id
- idx_lct_new_active (partial: is_active=true)
```

---

## 📊 184개 타겟 입력 완료

### Phase 1: 기본 법령 107개

| # | 도메인 | 법령수 | 비고 |
|---|---|---|---|
| 1 | BUILDING | 12 | 건축·시설물·승강기·기계설비 |
| 2 | CONSTRUCTION | 9 | 건설기술·건설산업·주택 🆕 |
| 3 | INDUSTRIAL_SAFETY | 6 | 산안법·중대재해법 (중대재해법 시행규칙 없음 확인) |
| 4 | FIRE 기본 | 12 | 소방시설·위험물·화재예방·다중이용업소 |
| 5 | GAS | 9 | 고압가스·도시가스·LPG |
| 6 | ELECTRIC | 11 | 전기사업·안전·공사+기술기준+KEC |
| 7 | CHEMICAL | 9 | 화관법·화평법·POPs 🆕 |
| 8 | ENERGY | 9 | 에너지이용·집단에너지·탄소중립 🆕 |
| 9 | ENVIRONMENT | 18 | 대기·물·폐기물+소음진동·토양·악취 🆕 분리 |
| 10 | DISASTER | 3 | 재난안전 기본법 🆕 |
| 11 | LABOR | 9 | 근로기준·산재보험·파견근로 🆕 |
| **소계** | | **107** | |

### Phase 2: NFTC/NFPC 기술기준 77개 (FIRE 도메인)

| 시리즈 | 카테고리 | NFTC | NFPC | 비고 |
|---|---|---|---|---|
| 100번대 | 소화설비 | 14 | 13 | NFPC 106 없음 |
| 200번대 | 경보설비 | 6 | 6 | |
| 300번대 | 피난설비 | 4 | 4 | |
| 400번대 | 소화용수설비 | 2 | 2 | |
| 500번대 | 소화활동설비 | 6 | 6 | |
| 600번대 | 기타시설별 | 8 | 6 | NFPC 608, 609 없음 |
| **합계** | | **40** | **37** | **77개** |

### 총계

```
Phase 1:   107개
Phase 2:    77개
─────────────────
총 타겟:   184개
```

---

## 🔍 API_ID 보유 현황

| 구분 | 개수 |
|---|---|
| ✅ law_api_id 확보 | 161개 (88%) |
| ❌ law_api_id 없음 (신규 수집 필요) | 23개 (12%) |

### 신규 수집 필요 23개 상세

**CONSTRUCTION (3):**
- 주택법, 주택법 시행령, 주택법 시행규칙

**CHEMICAL (3):**
- 잔류성오염물질 관리법 (법/시행령/시행규칙)

**ENERGY (3):**
- 기후위기 대응을 위한 탄소중립ㆍ녹색성장 기본법 (법/시행령/시행규칙)

**ENVIRONMENT (6):**
- 소음ㆍ진동관리법 시행령/시행규칙
- 토양환경보전법 시행령/시행규칙
- 악취방지법 시행령/시행규칙

**DISASTER (3):**
- 재난 및 안전관리 기본법 (법/시행령/시행규칙)

**ELECTRIC (1):**
- 한국전기설비규정(KEC)

**LABOR (4):**
- 근로기준법 시행규칙
- 파견근로자 보호 등에 관한 법률 (법/시행령/시행규칙)

---

## 🎯 다음 단계 (Step 3)

### Step 3-A: 다른 _new 테이블 구조 카피
```
law_master_new
law_version_new
law_content_raw_new
law_article_new
law_paragraph_new
law_item_new
law_attachment_new
```

### Step 3-B: 개선 사항 반영
- `law_master_new`에 `last_amended_at` 컬럼 추가 검토
- FK 관계 재설계 (중복 방지 UNIQUE 제약)
- UPSERT 지원 구조

### Step 3-C: Python 수집 스크립트 작성
- 기반: `scripts/all_laws_recollect.py` 개선
- 184개 유닛 단위 수집
- verification_checklist 자동 기록

### Step 3-D: 수집 실행 + 검증
- 161개 기존 법령 재수집 (UPSERT)
- 23개 신규 법령 신규 수집
- 각 유닛별 검증 통과 후 다음 진행

### Step 3-E: Atomic Switch
- 기존 테이블 → `_old_20260423`로 RENAME
- `_new` 테이블 → 정식 테이블로 승격
- 서비스 영향 0

---

## 💾 기존 `law_collection_target` (구)

```
현재 유지 (건드리지 않음):
  - 77 active rows
  - 서비스에 영향 없음
  - Python 수집 스크립트 전환 시 함께 대체 예정
```

---

## 🤝 설계 원칙 준수 확인

### ✅ 8단계 방식 적용
```
0. 목표: 구매자 만족 → 모든 판단 기준
1. 수집: DB 구조 분석 완료
2. 분석: 중복/고아/개정일 처리 방안 확정
3. 문제: "부분 수정"의 부작용 인지
4. 해결: 처음부터 재수집, _new 테이블 방식
5. 실행: 184개 타겟 INSERT 완료
6. 검증: 도메인별/API_ID 매칭 OK
7. 반복: 다음 단계(_new 테이블들) 준비
```

### ✅ 유닛 단위 작업
- 22개 컬럼 구조 생성 → 검증 → INSERT
- INSERT 3배치로 분할 (39개 + 38개 + 37개)
- 각 배치 후 검증 쿼리 실행

### ✅ 원본 보존
- 기존 `law_collection_target` 유지
- 데이터 손실 위험 0

---

## 📌 주의 사항 (다음 세션)

### ⚠️ 이름 표기 주의
```
DB에서 발견된 특이 표기:
- "비상방송설비의 화재안전성능기준(NFPC202)"  ← 공백 없음!
- "고층건축물의 화재안전성능기준 (NFPC 604)"  ← 괄호 앞 공백 있음!

→ 타겟 테이블에 있는 그대로 유지 (DB 매칭을 위해)
→ 수집 시 이름 정규화 단계에서 처리 필요
```

### ⚠️ NFTC vs NFPC 구분
```
NFTC (기술기준): 국립소방연구원, STANDARD 유형, 총 40개
NFPC (성능기준): 소방청, NOTICE 유형, 총 37개

→ 둘은 별개 법령
→ 이름 유사해도 독립적으로 수집
```

### ⚠️ NFPC 106 없음 확인
```
NFTC 106: 이산화탄소소화설비의 화재안전기술기준 ✅ 존재
NFPC 106: 존재하지 않음 ❌ (이산화탄소는 성능기준 없음)
```
