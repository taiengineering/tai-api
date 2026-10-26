# REF-C001 Body Structure Evidence / WO-REF01-059-B3-A2
Date: 2026-10-09
WO: WO-REF01-059-B3-A2
Investigator: Claude Code (collect/evidence only — no DB writes, no implementation)
Basis: GPT B-3-A 독립검증 결과 SOURCE_REQUIRED 판정 → B-3-A2 지시

---

## S0 PREFLIGHT

| Item | Value |
|---|---|
| Source file | 활용 서식 모음_'중대재해처벌법 따라하기' 안내서.hwp |
| File path | /Users/taiwangsim/Downloads/활용 서식 모음_'중대재해처벌법 따라하기' 안내서.hwp |
| SHA256 | e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe |
| SHA256 match | MATCH (WO-047 baseline 동일) |
| File size | 897,024 bytes |
| Parser | olefile 0.47 + manual HWP5 tag parser (tag 66/67) |
| Section | BodyText/Section0 (raw-deflate, 60,732→320,173 bytes) |
| Target | HWP-01: Para 1–15 ("안전보건 경영방침 작성 예시") |
| DB mutations this WO | 0 |

---

## S1 PARA 1–15 FULL TEXT EXTRACTION

Parser: HWP5 tag ID 67 (PARA_TEXT), UTF-16-LE decode, control chars (< U+0020) stripped.

| Para | Raw decoded text | Notes |
|---|---|---|
| 1 | 漠杳 안전보건 경영방침 작성 예시 | Section heading. 漠杳 = HWP section-heading control prefix |
| 2 | U+000B U+6C20 U+7462 U+0000 U+0000 U+0000 U+0000 U+000B U+000D | HWP table/frame cell boundary control sequence — no visible text |
| 3 | 안 전 보 건 경 영 방 침 | Form title (space-separated = center-formatted large font in HWP) |
| 4 | ○○기업은 경영활동 전반에 전 사원의 안전과 보건을 기업의 최우선 가치로 인식하고, 법규 및 기준을 준수하는 안전보건관리체계를 구축하여 전 직원이 안전하고 쾌적한 환경에서 근무할 수 있도록 최선을 다한다. | Opening company statement. ○○기업 = company name placeholder |
| 5 | 이를 위해 다음과 같은 안전보건활동을 통해 지속적으로 안전보건환경을 개선한다. | Policy list introduction |
| 6 | 1. 경영책임자는 '근로자의 생명 보호'와 '안전한 작업환경 조성'을 기업경영활동의 최우선 목표로 삼는다. | Policy item 1 (numbered list) |
| 7 | 2. 경영책임자는 사업장에 안전보건관리체계를 구축하여 사업장의 위험요인 제거·통제를 위한 충분한 인적·물적 자원을 제공한다. | Policy item 2 |
| 8 | 3. 안전보건 목표를 설정하고, 이를 달성하기 위한 세부적인 실행계획을 수립하여 이행한다. | Policy item 3 |
| 9 | 4. 안전보건 관계 법령 및 관련 규정을 준수하는 내부규정을 수립하여 충실히 이행한다. | Policy item 4 |
| 10 | 5. 근로자의 참여를 통해 위험요인을 파악하고, 파악된 위험요인은 반드시 개선하고, 교육을 통해 공유한다. | Policy item 5 |
| 11 | 6. 모든 구성원이 자신의 직무와 관련된 위험요인을 알도록 하고, 위험요인 제거·대체 및 통제기법에 관해 교육·훈련을 실시한다. | Policy item 6 |
| 12 | 7. 모든 공급자와 계약자가 우리의 안전보건 방침과 안전 요구사항을 준수하도록 한다. | Policy item 7 |
| 13 | 8. 모든 구성원은 안전보건활동에 대한 책임과 의무를 성실히 준수토록 한다. | Policy item 8 |
| 14 | ○○○○년 ○○ 월 ○○ 일 | Date placeholder (연·월·일) |
| 15 | ○○ 기업 대표이사  (서명) | CEO signature line placeholder |

Para 2 추가 해석: U+000B = HWP inline 객체 시작/종료 마커(셀 경계), U+000D = 단락 내 줄 바꿈. 이 제어 시퀀스는 Para 3 제목이 텍스트 박스 또는 단독 표 셀(1×1 table) 내부에 있음을 시사함. 시각적으로 Para 2는 빈 줄 또는 불가시 프레임 경계로 렌더링됨.

---

## S2 BODY STRUCTURE ANALYSIS (NATIVE_PARAGRAPH_ONLY)

### 2-1 문서 유형

| 속성 | 관측값 | 신뢰도 |
|---|---|---|
| 총 단락 수 | 15 (Para 1 포함) | NATIVE_PARAGRAPH_ONLY |
| 표/열 구조 | 없음 (tabular columns 없음) | NATIVE_PARAGRAPH_ONLY |
| 콘텐츠 성격 | 예시 텍스트 중심 (writing example) | NATIVE_PARAGRAPH_ONLY |
| 빈칸 필드 수 | 3개 (기업명 × 2, 날짜, 서명) | NATIVE_PARAGRAPH_ONLY |
| 페이지 방향 | UNVERIFIED (DOCX 생성 전 미확인) — 15 단락 분량으로 A4 세로 1페이지 추정 | INFERRED |

### 2-2 구조 레이아웃 (순서)

```
[Para 1]  섹션 헤딩         : 안전보건 경영방침 작성 예시
[Para 2]  프레임/박스 경계  : (불가시 제어 문자)
[Para 3]  폼 제목           : 안 전 보 건 경 영 방 침  (중앙 정렬, 대형)
[Para 4]  본문 오프닝       : ○○기업은 경영활동 전반에...
[Para 5]  정책 목록 도입부  : 이를 위해 다음과 같은...
[Para 6]  정책항목 1        : 1. 경영책임자는 '근로자의 생명 보호'...
[Para 7]  정책항목 2        : 2. 경영책임자는 사업장에...
[Para 8]  정책항목 3        : 3. 안전보건 목표를 설정하고...
[Para 9]  정책항목 4        : 4. 안전보건 관계 법령 및...
[Para 10] 정책항목 5        : 5. 근로자의 참여를 통해...
[Para 11] 정책항목 6        : 6. 모든 구성원이 자신의 직무...
[Para 12] 정책항목 7        : 7. 모든 공급자와 계약자가...
[Para 13] 정책항목 8        : 8. 모든 구성원은 안전보건활동에...
[Para 14] 날짜              : ○○○○년 ○○ 월 ○○ 일
[Para 15] 서명란            : ○○ 기업 대표이사  (서명)
```

### 2-3 입력 필드 (○○ 자리표시)

| 위치 | 플레이스홀더 | 필드 유형 | 등장 단락 |
|---|---|---|---|
| 본문 오프닝 | ○○기업 | 회사명 | Para 4 |
| 날짜 | ○○○○년 ○○ 월 ○○ 일 | 작성일 (연·월·일) | Para 14 |
| 서명란 | ○○ 기업 대표이사 (서명) | 회사명 + 직책 + 서명 | Para 15 |

### 2-4 예시 텍스트 vs. 빈 영역

**예시 텍스트 (pre-written)**: Para 3 제목, Para 4 오프닝, Para 5 도입부, Para 6–13 정책항목 8개.
이 텍스트들은 "작성 예시" 안내이므로 실제 기업이 그대로 사용하거나 내용을 수정하여 작성한다.

**빈 영역/플레이스홀더**: 회사명(Para 4 + 15), 날짜(Para 14), 서명(Para 15).
빈 표 행이나 반복 가능한 데이터 입력 행은 없음.

### 2-5 구현 관련 시사점

| 항목 | 관측값 |
|---|---|
| 반복 행(repeat_table) | 없음 — 고정 레이아웃 |
| 열 구조(columns/widths) | 없음 — 단일 단락 흐름 |
| 서명 박스 | NATIVE_PARAGRAPH_ONLY 한계: 별도 서명 박스/테두리 여부 미확인 |
| 날짜 배치 | Para 14 단독 줄 (우측 정렬 가능성 있으나 미확인) |
| 기업명 위치 | 본문(Para 4)과 서명란(Para 15) 두 곳 |
| 제목 박스 | Para 2 제어 문자 → Para 3 제목이 1×1 표 셀 또는 텍스트 박스 안에 있을 가능성 |

---

## S3 PDF CROSS-CHECK (PDF 84쪽)

Source: 최종_경영책임자와 관리자가 알아야 할 중대재해처벌법 따라하기 안내서.pdf
SHA256: a73ce4c67dfcb4a1b27f647ad346496f1bc7421666653da516c9ca92a46c60ff
PDF physical page 84 = HWP-01 (안전보건 경영방침 작성 예시) — WO-047 S3에서 교차 확인됨.

PDF 텍스트 재추출은 이 WO 범위 외 (WO-047에서 이미 pdfplumber로 확인됨).
기존 PDF 교차 참조: Para 1 제목 "안전보건 경영방침 작성 예시" = PDF 84쪽 섹션 제목과 일치.

---

## S4 STOP

DB mutations: 0.
Source mutations: 0.
Branch: docs/tai-reference-forms-charter-obj-20261008 (변경 없음).

**보고 요약 (GPT 제출용):**
- HWP-01 Para 1–15 전문 추출 완료 (NATIVE_PARAGRAPH_ONLY)
- 문서 구조: 제목 + 정책 본문(8항목) + 날짜 + 서명 (단일 페이지 레이아웃)
- 빈칸: 회사명 × 2 / 날짜 / 서명 (○○ 플레이스홀더)
- 반복 행/표 구조 없음 (tabular form이 아닌 policy document template)
- 제목 Para 3가 텍스트 박스/1×1 표 셀 내부일 가능성 있음 (Para 2 제어 문자 기준)
- 페이지 방향: PORTRAIT 추정 (미검증)

FINAL: EVIDENCE_READY_FOR_GPT_REVIEW. No DB writes performed.
