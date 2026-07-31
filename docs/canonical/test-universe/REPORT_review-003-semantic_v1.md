---
wo: WO-REVIEW-003
class: records
type: report
scope: canonical
project: test-universe
title: before_clean 112 전량 정독 Semantic Review
version: 1
status: active
owner: taiwang
---

# REPORT — WO-REVIEW-003 before_clean 112 전량 정독 (Semantic Read-through)

> §12 E2E_REVIEW 준수. 전 112 profile 의무 전문을 정독. 표현은 관측 수준(관측·등록·보류·후순위·분류). 원인·수정·가설 없음. Issue는 누적만. 이 표 확정 전 어떤 CHG도 생성하지 않음(§12.7).

## 정독 범위
제조 46 · 건축 29 · 건설 27 · 특수 10 = 112 전량. 각 sector applicable_count 값별 대표 + 동일입력 편차쌍(예: PF-0020 vs PF-0021)의 의무 전문 정독.

## Issue Inventory (관측 기반)

### Issue-001 — 동일 입력, 다른 출력 (관측)
- 관측: 동일 (site_kind,scale,workers) 그룹 내 의무 집합이 다름. 예) building/medium/50 — PF-0021엔 [KEC 231.5]·[KEC 351.6]·[KEC 503.2.4]·[KEC 605.32.1]·에너지절약형주택 존재, PF-0020엔 없음(차이 4~5건). construction/large/450 — PF-0028엔 에너지절약형주택 존재, PF-0030엔 없음. special/large/300 — PF-0039엔 에너지절약형주택 존재, PF-0038엔 없음.
- 범위: building · construction · special (manufacturing은 동일입력군 내 균일 — 미관측).
- 분류: Engine/Query (미확정, Unknown).
- 영향도: Critical. Confidence: High.

### Issue-002 — 동일 (law, obligation) 다중 등장 (관측)
- 관측: 112/112 profile에서 같은 (법령, 의무)가 2회 이상 등장. 다중도 높음 — 예) 소방 자체점검 결과의 조치 report 6~7회(건축), 건설기술진흥법 안전관리계획 수립 report 3회(건설), 안전보건교육규정·장애인복지법 신고 2회(특수), 중대재해 안전보건교육 다회.
- 범위: 전 sector 112/112.
- 분류: Data/Query (미확정).
- 영향도: High. Confidence: High.

### Issue-003 — 측정 스냅샷이 preview만 저장 (관측)
- 관측: 응답 message="일부 결과만 표시됩니다...", hasFullResult=true, rules_table=rules_preview=12. 이전 Runner 파싱이 preview만 사용. 전체 의무는 *_required 배열(합=applicable_count).
- 범위: 전 측정.
- 분류: Measurement.
- 영향도: Critical. Confidence: High.

### Issue-004 — 특정 도메인 profile에 타 도메인 법령 등장 (관측, 판단 보류)
- 관측(오적용 여부 미확정 — 정책/Rule정의/데이터 가능성 열어둠):
  - '산업안전보건기준에 관한 규칙 | 표면공급식 잠수작업 시 조치' → manufacturing·building·construction 등장.
  - '에너지절약형 친환경주택의 건설기준 | 설계조건' → 4개 sector 전부 등장.
  - '방사선 안전관리 등의 기술기준에 관한 규칙 | 화재방호시설' → building·construction·special 등장.
  - building 일반 profile에 '도로터널 화재안전기준'·'다중이용업소'·'초고층 복합건축물'·'공동주택'·'고층건축물' 동시 등장.
- 범위: 전 sector(항목별 상이).
- 분류: Rule/Data (미확정).
- 영향도: Critical(광범위). Confidence: 등장 사실 High / 오적용 여부 미확정.

### Issue-005 — 의무 category 배치 관측 (관측, 판단 보류)
- 관측: '전기안전관리자 선임'·'승강기 안전관리자'·'안전관리자 선임 등'·'유해화학물질관리자'가 report category에 배치. '안전보건관리규정의 작성'이 산안법(action)·산안법 시행규칙(action)에 분산.
- 범위: 광범위.
- 분류: Query/Engine (category 판정 로직, 미확정).
- 영향도: High. Confidence: Medium (정책 의도 여부 미확정).

### Issue-006 — 동일 의무의 법/시행령/시행규칙 분리 등장 (관측)
- 관측: 같은 사안이 법과 시행규칙으로 나뉘어 각각 등장. 예) '기계설비법 | 선임'+'기계설비법 시행규칙 | 선임', '산업안전보건법 | 안전보건관리규정의 작성'+'산업안전보건법 시행규칙 | 안전보건관리규정의 작성'.
- 범위: 광범위.
- 분류: Data/Rule (미확정).
- 영향도: Medium. Confidence: Medium (이중계상 여부 미확정).

## Issue 영향도 표 (§12.7)

| ID | Issue | 범위 | 영향도 | 분류(미확정) | CHG 여부 |
|---|---|---|---|---|---|
| 003 | Preview만 저장 (측정) | 전체 | Critical | Measurement | 후보 |
| 004 | 타 도메인 법령 등장 | 전 sector | Critical | Rule/Data | 후보 |
| 001 | 동일 입력 다른 출력 | building/construction/special | Critical | Engine/Query | 후보 |
| 002 | 의무 다중 등장(중복) | 112/112 | High | Data/Query | 후보 |
| 005 | category 배치 | 광범위 | High | Query/Engine | 후보 |
| 006 | 법+시행령/규칙 분리 등장 | 광범위 | Medium | Data/Rule | 후보 |

## §12 준수 확인
- Review 중 CHG 생성 없음(§12.1). Issue 누적만(§12.2). 전수 후 분류(§12.3)·영향도(§12.4). 표 완성(§12.7).
- 표현: 관측·등록·보류·후순위·분류만. 'Rule 해석 결론'(오적용/상호배타/이어야 한다)은 판단 보류로 기록.
- 원인·수정·가설 없음. CHG는 별도 WO에서 우선순위 결정 후 생성.

## 다음 (별도 WO)
우선순위·CHG 승격은 별도 WO에서 결정. 관측상 Issue-003(측정 완전성)은 다른 Issue를 전량 기준으로 재현·측정하기 위한 전제 성격. 단 우선순위 확정은 본 Review 범위 밖.
