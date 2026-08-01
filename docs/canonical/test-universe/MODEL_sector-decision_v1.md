---
wo: WO-MODEL-001
class: records
type: model
scope: canonical
project: test-universe
title: Sector Decision Model Definition
version: 1
status: active
owner: taiwang
---

# SECTOR DECISION MODEL (FROZEN) — WO-MODEL-001

> sector를 결정하지 않고, 사람이 일관되게 결정할 수 있는 입력 모델을 정의. 정책·매핑·DB 수정 없음. sector는 전부 빈칸.
> Input: A3·B313·C59·Evidence Sheet(368)·Inventory(375), 기존 law_sector_mapping(393).

## 판정: PASSED

## STEP 1-2 — Feature Catalog (입력별 sector 결정 역할, Evidence 기반)
| 입력 | 출처 | 분류 | Evidence(반증/관측 근거) |
|---|---|---|---|
| scope(적용범위 조문) | law_article | **결정 가능(제한)** | 적용범위에 sector 직접명시 시만(건설공사=A 3건). MAPPING-003 |
| applicable_target(적용대상 원문) | Evidence Sheet | **결정 가능(제한)** | 원문이 sector 직접 지시할 때만. MAPPING-002 |
| law_name | law_master | 결정 불가 | 이름 키워드 결정=추론. 고등교육법 오분류. MAPPING-002 Review |
| domain_code | law_master | 결정 불가 | BUILDING이 6가지 sector로 분산. CHG-004 반증 |
| facility(시설) | 원문 추출 | 결정 불가(단독) | 건축물 언급이 소방=전 sector. 번역규칙 필요. MAPPING-001 |
| industry(업종) | 원문 추출 | 결정 불가(단독) | 업종은 sector 표준 아님. 번역규칙 필요. MAPPING-002 |
| related_law(모법/위임) | 원문 본문 | 결정 불가(현재) | 상속 앵커 부재(미매핑에 시행령/규칙 0). POLICY-001 |
| law_type_code | law_master | 보조 | NOTICE/STANDARD/LAW, sector 무관. CHG-004 |
| ministry_name | law_master | 보조 | 부처가 단서이나 sector와 1:1 아님. CHG-004 |
| object(관리 객체) | 원문 추출 | 보조 | 승강기·보일러 등, sector는 별도 판단. MAPPING-001 |
| purpose(목적 조문) | law_article | 보조 | sector 직접 지시 드묾. COVERAGE-001 |

## STEP 3 — Decision Flow (sector 빈칸)
```text
[law_article 원문]
      | 
      v
[applicable_target 추출]  --- Evidence Sheet(368 확보) ---
      |
      +-- scope에 sector 직접명시?  --YES--> [결정 가능] --> sector = ____  (A: 건설공사, 3건)
      |                             --NO-->  |
      v                                      v
[facility/industry/object 식별]        [결정 불가 경로]
      |                                      |
      v                                      v
 [번역 규칙]  <== MISSING               [Policy Decision]  <== 사람 판단
      |                                      |
      v                                      v
  sector = ____ (빈칸)                   sector = ____ (빈칸)
```
- 결정 가능 경로(scope 직접명시)만 자동. 나머지 전부 MISSING/Policy로 귀결. **sector는 어디서도 채우지 않음.**

## STEP 4 — Missing Input (sector 결정 위해 현재 없는 입력)
```text
① 시설→sector 매핑표      없음(도메인 판단)   ← 핵심
② 업종→sector 매핑표      없음(도메인 판단)   ← 핵심
③ sector 경계 정의        없음(운영 기준)     ← 핵심
④ MULTI 허용 규칙         부분(C=MULTI 관측·기존 combos 8종 참고)
⑤ 미확보 7 매핑대상 여부   없음(운영 판단)
```
- **핵심 Missing 3개(①②③)만 사람이 정의하면**, 그 다음은 원문 추출(이미 확보)로 기계 적용 가능. 사람의 판단 지점을 최소화.

## STEP 5 — Existing Data Reuse
- 기존 393 매핑의 method: **auto_regex 331 · web_search_verified 35 · manual_verified 27**. distinct sector 조합 **8종**.
- **재사용 가능성:**
  - auto_regex 331 = **재사용 불가**(domain_code 기반, CHG-004에서 sector 1:1 반증). 미매핑에 재적용하면 같은 불완전성 재생산.
  - manual_verified 27 = 신뢰 기준이나 **규칙 아닌 개별 사례** → 매핑표 일반화엔 여전히 도메인 판단 필요.
  - distinct combos 8종 = **MULTI 규칙(④)의 기존 참고**로 재사용 가능.
- 결론: 부분 재사용(combos 8)만 가능, 핵심 매핑표(①②③)는 DB에 없음.

## STEP 6 — Validation
```text
Sector 결정 안 함     : YES (Flow의 sector 전부 빈칸)
추론 안 함            : YES (Feature 분류는 과거 WO Evidence 근거)
새 Policy 안 만듦     : YES (Missing 식별만, 규칙 작성 0)
```

## STEP 7 — Independent Audit
```text
Decision Flow  : PASS (결정가능 경로만 자동, sector 빈칸 확인)
Feature        : PASS (11 입력 전부 분류+Evidence 출처)
Evidence       : PASS (전부 기존 WO 인용, 새 데이터 0)
Missing Input  : PASS (5개 식별, 핵심 3개)
특기: auto_regex 331 재사용 착시 주의(반증됨), manual 27은 사례이지 규칙 아님.
```

## STEP 8 — Freeze
```text
Decision Model   : 결정가능(scope 직접명시)=자동 / 결정불가=MISSING·Policy → sector 빈칸
Feature Catalog  : 11 입력 (결정가능 2·불가 5·보조 4)
Decision Flow    : 위 (sector 빈칸)
Missing Inputs   : 5 (핵심 ①시설→sector ②업종→sector ③sector경계)
Validation       : PASS
Audit            : PASS
```

## 결론
- Sector Decision Model 확정. **사람이 정의해야 할 것은 정확히 3개**(시설→sector·업종→sector 매핑표 + sector 경계 정의). 이 셋이 서면 372건 대부분이 원문 추출(확보됨)로 일관 결정 가능해짐.
- 이후 정책 결정(WO-MAPPING-004)은 이 Model 위에서 진행 → 사람마다 달라지지 않고 동일 입력 구조 사용.
- sector 미결정·추론 0·새 Policy 0.

## 상태 (Obs-004 커버리지 파이프라인)
```text
① Inventory(375)            ✓ WO-CHG-004
② Evidence Sheet(368)        ✓ WO-COVERAGE-001
③ Mapping Policy(패턴)        ✓ WO-MAPPING-001
④ Sector Draft(A3/B313/C59)   ✓ WO-MAPPING-002
⑤ Policy Validation(경계)      ✓ WO-MAPPING-003
⑥~⑧ Audit 3겹               ✓ WO-AUDIT-001/002/003
⑨ Policy Independent Fix      ✓ WO-CHG-006 (BS-1 RESOLVED)
⑩ Policy Necessity(372)       ✓ WO-POLICY-001 (P1=0)
⑪ Decision Model(입력 구조)    ✓ WO-MODEL-001 (핵심 Missing 3) ← 현재
⑫ Sector 기준표 작성          ← WO-MAPPING-004 (사람이 ①②③ 정의)
⑬ DB 반영 CHG + Verify        ← WO-CHG-005
```
