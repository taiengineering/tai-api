---
title: TASK_GUIDE Channel and Search Contract
status: FROZEN
version: 1
governed_by: WO-DOC-ARCHREC-002
date: 2026-10-08
---

# TASK_GUIDE Channel and Search Contract

## 1. Current Production Facts

### safe_help_content type allowed values (DB constraint confirmed)
```
PAGE_GUIDE
TASK_GUIDE
FAQ
```

### Current row counts (2026-10-08)
| type | count |
|------|-------|
| FAQ | 264 |
| PAGE_GUIDE | 58 |
| TASK_GUIDE | 0 |

TASK_GUIDE rows = 0. The slot exists but has not been used.

---

## 2. Channel Definition

```
document_forms
= operational document / form catalog
= "이 문서가 있다"

safe_help_content TASK_GUIDE
= safety-manager handbook / how-to content
= "이 문서를 어떻게 작성하고 관리하는가"
```

These two must not be merged. TASK_GUIDE is NOT added to `document_forms`.

---

## 3. TASK_GUIDE Content Contract

Each TASK_GUIDE entry covers one document form and includes:

1. 이 문서는 무엇인가 (definition)
2. 언제 작성하는가 (trigger conditions)
3. 누가 작성하는가 (responsible person)
4. 필수 기재항목 (required fields)
5. 작성 순서 (writing sequence)
6. 주의사항 (cautions)
7. 관련 법령 (related law)
8. TAI에서 작성하는 방법 (how to use TAI)
9. 관련 서식 (related forms)

---

## 4. TASK_GUIDE Boundary

TASK_GUIDE content:
- Explains how to write/manage a document
- May reference document_forms (e.g. doc_id link)
- Accessible publicly (SEO indexable)

TASK_GUIDE does NOT:
- Determine legal obligation status (that belongs to LEG / diagnosis engine)
- Replace the actual document/form
- Include regulatory compliance CTA (belongs to free/paid diagnosis flow)

---

## 5. Shared Search Domain Connection

`safe_help_content` is currently connected to Shared Search as:
- Domain: KNOWLEDGE_CENTER
- Visibility: PUBLIC + SAAS + PAID

When TASK_GUIDE rows are created, they automatically become:
- Indexed in TAI unified search
- Eligible for Google/Naver SEO
- Linked from document catalog to guidance content

---

## 6. Search Acquisition Path

```
Google / Naver 검색
  → "밀폐공간 작업허가서 작성방법" 등
  → TAI 안전정보 통합검색 결과
  → TASK_GUIDE 페이지
  → 관련 수동서식 (document_forms 링크)
  → 무료 법령진단 CTA / SaaS 전환
```

---

## 7. Example TASK_GUIDE Candidates

| doc_id | document_name | candidate_guide_title |
|--------|---------------|-----------------------|
| DOC-OSH-047 | 밀폐공간 작업허가서 | 밀폐공간 작업허가서 작성·관리 방법 |
| DOC-OSH-056 | TBM 기록 | TBM 기록 작성방법 |
| DOC-OSH-007 | 안전점검일지 | 안전점검일지 작성방법 |
| DOC-OSH-046 | 보호구 착용 점검기록 | 보호구 지급·점검 기록 작성방법 |
| DOC-OSH-002 | 위험성평가서 | 위험성평가서 작성방법 |
| DOC-OSH-003 | 산업재해조사표 | 산업재해조사표 작성 및 제출방법 |

Implementation of TASK_GUIDE content = separate WO (not this ARCH-REC-02 scope).
