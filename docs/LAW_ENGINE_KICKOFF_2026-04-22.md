# 법령엔진 재수집 Kickoff — 2026-04-22

> 다음 세션에서 이 문서 하나로 바로 이어서 작업 가능

---

## 🎯 목표 (Goal)

### 1차 목표 (현실적 — 즉시 달성해야 함)
> **"구매한 사람이 누구든 만족감을 가지게 한다"**

### 2차 목표 (장기 — 지속 발전)
> **"안전관리의 심장"**

---

## 💚 목표의 의미 — 심장 비유

```
법령엔진 = 모든 서비스의 심장
├─ 멈추면 (오류): 서비스 전체 죽음
├─ 너무 빠르면 (과도한 의무): 고객 피로
└─ 너무 느리면 (개정 미반영): 구식 서비스

심장의 3가지 조건:
  정확성 — 틀린 판정은 신뢰도 파괴
  완전성 — 빠진 법령은 감독관청 지적
  속도   — 적정한 박동 (과/부족 모두 문제)
```

---

## 📋 작업 방식 — 8단계 (목표 추가)

```
0. 목표 설정 ⭐ 모든 것의 기준
1. 목표에 부합하는 자료수집
2. 목표에 부합하는 분석
3. 목표에 부합하는 문제점 파악
4. 목표에 부합하는 해결방안 강구
5. 실행
6. 목표에 부합하는 검증
7. 이상시 해당 단계부터 재반복
```

**핵심 원칙:** 유닛 단위로 작업 + 검증. 큰 작업 금지. 작은 오류도 누적되면 큰 재작업이 됨.

---

## 🎯 고객 만족 체크리스트

### 레벨 1 — 돈 낸 최소값 (현재 목표)
```
☐ 우리 시설에 걸리는 법령이 다 나온다
☐ 우리 시설에 안 걸리는 법령은 안 나온다
☐ 모든 법령이 현재 시행 중인 것이다 (폐지본 없음)
☐ 중복 없이 한 번씩만 나온다
```

### 레벨 2 — 감사 대응 가능
```
☐ 조문 본문이 법제처 원문과 일치한다
☐ 별표/서식이 제대로 나온다
☐ 개정 이력이 최신까지 반영됐다
☐ 감독관청 지적 시 리포트로 방어 가능
```

### 레벨 3 — 베테랑도 만족 (장기)
```
☐ NFTC/NFPC 등 기술기준까지 다 있다
☐ 조항별 벌칙 금액이 정확하다
☐ 주기/조건이 업종 특성 반영
☐ 판례/행정해석 연결 (미래)
```

---

## 🔴 현재 DB 상태 문제 (2026-04-22 기준)

### 2026-04-22 완료 사항
- ✅ 보안 패치: otp_store RLS (commit 397d1ae6)
- ✅ 범위 v1 확정: 48개 제외 (commit 454202bd)
  - 학교/의료/복지/선박/통신/철도/항공/놀이시설 등
  - `law_master_archive_20260422` (48 rows) 백업
  - `master_rules_archive_20260422` (17 rows) 백업

### 남은 문제
- ⚠️ 중복 80 그룹 (동일 법령 2~10번 반복)
  - A유형: 완전중복 62개 × 2 = 124
  - B유형: 개정버전중복 17개 × 2 = 34
  - C유형: 별개법령 (이름만 같음) 10개 유지
- ⚠️ 고아 191개 (룰 미연결, 대부분 NFTC/NFPC)
- ⚠️ 파싱 실패 조문 없음 58개
- ⚠️ 같은 법령 조문수 3~5배 차이 (파싱 품질 불균일)

---

## 💡 판단: 처음부터 재수집이 맞다

### 이유
```
1. 과거 "부분 수정" 반복 → 오히려 복잡도 증가
2. 현재 DB 상태 너무 꼬임 → 패치 10번보다 깨끗한 재수집 1번이 안정
3. 원본 (law_content_raw) 유지 → 학습한 것들 잃지 않음
4. 개선된 파서 (Pilot 1+2+3) 적용 → 품질 ↑
```

### 리소스 비교
```
방안 A (비교 수집): API 호출 246회, 코드 500줄, 5분
방안 B (전체 재수집): API 호출 82회, 코드 200줄, 3분
→ 방안 B가 3배 효율적
```

---

## 🎯 다음 세션 실행 순서

### Step 0: 목표 문서화
- 이 문서를 기반으로 시작
- 매 단계 "목표에 부합하는가?" 체크

### Step 1: 타겟 확정 ⭐ 최우선
```
대상: law_collection_target (현재 77 active)

유닛 검증 체크리스트:
  ☐ 법령명이 법제처 최신과 일치
  ☐ law_api_id 유효
  ☐ 부처/분류 정확
  ☐ NFTC/NFPC 시리즈 포함 여부 결정
  ☐ 빠진 필수 법령 보완

결과: 최종 타겟 N개 확정 + Git 문서 백업
```

### Step 2: 유닛 단위 수집 구조 설계
```
1 법령 = 1 유닛
각 유닛별 검증:
  ☐ API 호출 성공
  ☐ 원본 XML 저장 (law_content_raw)
  ☐ 파싱 성공 (law_article 생성)
  ☐ 조문수 합리적
  ☐ 별표/서식 수집
  ☐ 개정 이력 최신
  ☐ valid_pct ≥ 30%

실패 유닛은 별도 로그 → 재작업
```

### Step 3: Python 전체 수집 스크립트
```python
# 기반: scripts/all_laws_recollect.py (기존 체크포인트 스크립트)
# 개선점: UPSERT 로직 추가, 유닛별 검증

for law in targets:
    result = collect_one_law(law)
    verify = verify_one_law(result)
    if not verify.ok:
        log_failure(law, verify.issues)
        continue
    save_to_db_upsert(result)
    print(f"✅ {law}: {verify.article_count} articles, {verify.valid_pct}%")
```

### Step 4: 실패 유닛만 재작업
```
실패 분류:
  - API 오류: 재시도
  - 파싱 실패: 파서 패치 후 재실행
  - 데이터 이상: 수동 확인

→ 처음부터 다시 돌리지 않음
→ 유닛 단위 = 부분 재작업 가능
```

### Step 5: 검증 + Atomic Switch
```
검증 쿼리:
  - 수집 건수 = 타겟 수
  - 각 법령 valid_pct ≥ 30%
  - 중복 0
  - 구버전 0
  - 고아 법령 확인

Atomic Switch:
  BEGIN;
    ALTER TABLE law_master RENAME TO law_master_old_20260423;
    ALTER TABLE law_master_new RENAME TO law_master;
    -- master_building_legal_rules는 law_name 기반이므로 영향 없음
  COMMIT;

1주일 후 _old 테이블 정리
```

### Step 6: 법령엔진 무결성 테스트
```
python tests/test_legal_engine.py
→ 26건 전부 통과 필수 (정방향 11 + 역방향 11 + 규모 2 + 섹터격리 2)
```

---

## 🔑 필수 참조 문서

### 이번 세션 생성
- `docs/SECURITY_2026-04-22_RLS_AUDIT.md` — 보안 감사
- `docs/LAW_SCOPE_V1_2026-04-22.md` — 범위 v1 확정 (48개 제외)
- `docs/LAW_ENGINE_KICKOFF_2026-04-22.md` — 이 문서

### 어제 세션 (2026-04-22 오전)
- `docs/SESSION_2026-04-22_PILOT_1_2_3_COMPLETE.md` — Pilot 1+2+3
- `docs/ISSUE_37_XML_ANALYSIS.md` — 파싱 버그 원인 분석
- `docs/WORK_ORDER_VALIDATION_PIPELINE.md`

### 법령엔진 무결성 기준
- `docs/ENGINE_INTEGRITY.md` — 26건 테스트 기준점

### 가격/서비스 기획
- `docs/PRICING_FINAL.md` — Single Source of Truth
- `docs/DIAGNOSIS_REPORT_STRUCTURE.md` — 리포트 구조
- `docs/TAI_서비스_장점_기획전달용.md` — 서비스 차별점

---

## 🗄️ 주요 DB 식별자

### Supabase
- 프로젝트: `xntdkrjhgcscmqctdzyo`
- URL: `https://xntdkrjhgcscmqctdzyo.supabase.co`

### 법령 테이블
- `law_collection_target` — 77 active (수집 대상 확정본)
- `law_master` — 350 active (범위 정리 후)
- `law_version` — 557
- `law_content_raw` — 557 (원본 보존)
- `law_article` — 33,644
- `law_paragraph` — 51,118
- `law_item` — 37,631
- `law_attachment` — 4,907

### 룰/진단
- `master_building_legal_rules` — 1,385 active
- `law_rule_drafts` — 3,073 (AI 초안)
- `factory_diagnosis_results` — 43 (실제 사용 이력)

### 백업 (2026-04-22)
- `law_master_archive_20260422` — 48 (범위 외)
- `master_rules_archive_20260422` — 17 (비활성 룰)
- `law_quality_snapshot_20260422` — 324 (baseline)
- `law_article_key_map` — 6,328 (Pilot 이력)

### 법제처 API
- OC: `taieng` (115.68.227.222 등록 IP에서만 호출)
- Railway 미등록 (DATA_GOV_SERVICE_KEY 필요)

---

## 🤝 협업 구조

- **기획창 (Claude Opus)**: MCP로 진단·검증·판정·PR 관리
- **작업창 (Cursor)**: 로컬에서 코드 작성·테스트·커밋
- **사용자**: 로컬 실행(`~/dev/tai-api/`) · 의사결정 · 검토

---

## 🔴 다음 세션 시작 시 첫 질문

```
1. 이 kickoff 문서 보고 이어서 시작하면 됩니다
2. 오늘 완료: 보안 패치, 범위 v1 확정 (48개 제외)
3. 다음 단계: Step 1 (타겟 확정) 부터 시작
4. 핵심 원칙: 유닛 단위 작업 + 검증
5. 큰 작업 금지
```

---

## 📊 시간 투자 관점

### "지금까지 투자한 시간이 아깝다"는 인식
- ❌ 실패한 시간
- ✅ 학습한 시간

### 실제 학습 성과
- 법제처 API 구조 파악 완료
- XML 파싱 로직 3차 개선 (Pilot 1+2+3, 평균 37% valid)
- Cascade FK 11개 테이블 발견 + 처리
- PostgREST URL 한계 발견 + chunking 적용
- "정상 비-조문 요소" 3가지 패턴 파악
- 법령 범위 v1 확정 (48개 제외)
- 중복/고아 구조 완전히 이해
- 법제처 OC=taieng IP 등록 완료

**→ 재수집 시 출발선이 훨씬 높음**
