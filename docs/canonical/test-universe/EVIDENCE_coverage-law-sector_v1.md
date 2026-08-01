---
wo: WO-COVERAGE-001
class: records
type: evidence
scope: canonical
project: test-universe
title: law_sector_mapping Coverage Evidence Sheet
version: 1
status: active
owner: taiwang
---

# EVIDENCE SHEET (FROZEN) — law_sector_mapping Coverage

> WO-COVERAGE-001. Unmapped 375 각 법령의 원문에서 '적용 대상이 명시된 조문'을 원문 그대로 추출·기록. **sector 결정·Draft·UNRESOLVED·판단 없음.** Evidence → (별도) Decision 순서 유지.
> Input: Unmapped Inventory(375, WO-CHG-004), law_article.article_text 원문.
> 전량 산출물: evidence_sheet_coverage.md (7,563줄, 368 법령 × 적용대상 조문), evidence_missing.txt (7 법령), unmapped_law_inventory.csv (375).

## 범위
- Unmapped 375 중 **368개**가 적용대상 후보 조문(목적/정의/적용범위/'이 법은…') 확보. 총 **6,087 조문** 원문 그대로 기록.
- **7개**는 적용대상 후보 조문 미확보(원문 근거 못 찾음). sector 판단 안 함, 사실만 기록:
  - (한국전통문화대학교) 제3종시설물의 지정고시 · 2025년 학교안전공제료 산정기준 고시 · 터널설계기준(KDS 27) · 교량 내진설계기준(KDS 24 17 11) · 교량 내진설계기준(KDS 24 17 12) · 군형법 · 난민법.

## Evidence Sheet 구조 (각 법령)
```text
law_id
law_name
근거 조문 / 적용 대상(원문 그대로 인용):
  - 제N조(제목): <원문 발췌>
```
- 원문 그대로만. 요약·추론·sector 귀속 없음.

## 대표 발췌 (원문 그대로)
- (국토교통부) 건축용 고효율에너지기자재 보급촉진 고시
  - 제1조(목적): "이 고시는 「에너지이용 합리화법」…제22조제1항에 따라 건축물에 고정되어 설치·이용되는 고효율에너지인증대상기자재의 인증에 필요한 사항을 규정함을 목적으로 한다."
  - 제2조(용어의 정의): "…「건축법」제2조제1항의 건축물에 고정되어 설치·이용되는 고효율에너지인증대상기자재로…"

(이하 368 법령 전량은 산출물 evidence_sheet_coverage.md 참조. 적용 대상 표현이 원문에 그대로 담김: '건축물', '사업주', '의료기관', '학교', '건설공사', '승강기' 등.)

## Evidence Freeze
- 이 WO는 Evidence Sheet 작성까지. 여기서 종료(Freeze).
- **다음 WO(별도 Mapping WO)**: Evidence → sector 정책 → Draft. 즉 '적용 대상 원문'을 sector로 귀속하는 정책은 별도 WO에서 근거 기준을 세운 뒤 수행. 본 WO는 sector를 적지 않는다.

## 규율 준수
- law_name/ministry/domain_code/제목 기반 sector 판단 없음('자명' 판단 포함 금지).
- 원문에 명시된 적용 대상만 그대로 인용. DB 수정·Draft·UNRESOLVED 작성 없음.
- Evidence 수집 → (별도) Decision 순서 유지 — Evidence에서 Draft로 건너뛰지 않음.
- 관측(판단 아님): 미확보 7개 중 군형법·난민법 등은 산업안전 도메인과 무관해 보이나, 이 역시 sector 판단이 아니라 '원문 근거 미확보' 사실 기록일 뿐. 정오는 다음 WO.

## 상태
```text
Obs-003 : RESOLVED
Obs-001 : RESOLVED
Obs-002 : RESOLVED
Obs-004 : ANALYZED → Coverage Evidence Sheet 확보(368/375) → 다음: Mapping WO(sector 정책→Draft)
Obs-005 : ANALYZED (정상)
Obs-006 : ANALYZED (정상)
법령 원문 근거: 368 확보 / 7 미확보(기록만)
```
