# for-expert 허브 페이지 + nav 매칭

> 허브: `nexas/for-expert.html` — 종합 게이트웨이 (간결, 3장으로 라우팅)
> nav: `nexas/assets/js/header.js` — 서비스 드롭다운 3개 링크 변경 + 역할별 전문가 링크 변경

---

## 1. for-expert.html 허브 페이지

페이지 목적: "나는 어떤 유형인지" 확인 → 해당 상세 페이지로 이동.
길지 않음. 깊지 않음. 빠르게 라우팅.

### 섹션 (5개)

#### §1 히어로 [A 다크]
```
"실력은 있는데,
 부를 데가 없습니다."

TAI는 법적 의무를 인지한 사업장과
검증된 전문가를 연결하는 플랫폼을 준비하고 있습니다.

"어떤 전문가신가요?"
```

#### §2 3가지 유형 [E 카드 그리드 3컬럼]
```
배경: 흰색

카드 3개 — 각 카드에 아이콘 + 한 줄 속마음 + 3줄 설명 + CTA 버튼:

┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
│ 🏢 대행기관·전임    │ │ 🔧 수선·정비 업체    │ │ 📊 안전 컨설턴트    │
│                    │ │                    │ │                    │
│ "점검 나가면서     │ │ "기술은 있는데    │ │ "보고서 한 건 쓰면  │
│  영업까지 하고     │ │  전화가 안 옵니다"  │ │  끝입니다"        │
│  계시죠?"         │ │                    │ │                    │
│                    │ │                    │ │                    │
│ 안전관리 위탁     │ │ 설비 고장 정비     │ │ 안전관리체계 구축 │
│ 정기점검 대행     │ │ 긴급 수선         │ │ 위험성평가 작성   │
│ 전임 안전관리자  │ │ 증상 기반 매칭     │ │ 중대재해법 대응   │
│                    │ │                    │ │                    │
│ [자세히 보기 →]    │ │ [자세히 보기 →]    │ │ [자세히 보기 →]    │
│ for-agency.html  │ │ for-repair.html   │ │ for-consultant.html│
└────────────────────┘ └────────────────────┘ └────────────────────┘

모바일: 1컬럼 세로 스택
카드 호버 시 상승 애니메이션
```

#### §3 매칭 구조 [F 다크 SVG]
```
배경: 다크

"의뢰가 만들어지는 구조입니다."

SVG 프로세스 (간략):
[사업장 법령진단] → [의무 감지] → [전문가 매칭] → [연결·정산]

특허 8건 출원 · patents.html 링크
```

#### §4 비용 + 사전등록 [D 숫자 + CTA]
```
배경: 흰색

0원 등록비 / 0원 구독 / 0원 광고비
"연결 성사 시에만 매칭 서비스료를 정산합니다."

[파트너 사전등록 →] (fix-request.html?from=for-expert&type=general&interest=partner)
```

#### §5 교차링크 [A 다크]
```
"TAI를 쓰는 사업장이 궁금하다면"
[안전관리자용 →] [사업주용 →]
```

### Cursor 프롬프트

```
for-expert 허브 페이지 — nexas/for-expert.html
기준: tai-api docs/for-expert-hub.md (dev)
래퍼: #fe2 · 5개 섹션 (짧고 간결)
핵심: 3가지 전문가 유형 카드 → 각 상세 페이지로 이동
카드에 큰 속마음 1줄 + 3줄 설명 + CTA 버튼
모바일 1컬럼 스택 · 카드 호버 상승
레포: taiengineering/taieng (main)
작업 완료 후 git add . && git commit -m "feat: for-expert 허브 페이지" && git push origin main
```

---

## 2. header.js nav 매칭 변경

### 서비스 드롭다운 변경 (3개 링크)

| 현재 메뉴 | 현재 링크 | 변경 링크 |
|---|---|---|
| 수선 연결 | fix-request.html?from=nav&type=repair | **for-repair.html** |
| 컨설팅 | fix-request.html?from=nav&type=consulting | **for-consultant.html** |
| 선임 연결 | fix-request.html?from=nav&type=appointment | **for-agency.html** |

### 역할별 드롭다운 변경 (1개 링크)

| 현재 메뉴 | 현재 링크 | 변경 링크 |
|---|---|---|
| 전문가 | provider-register | **for-expert** |

### 헤더 변경 전체 diff (정확한 문자열 치환)

```
서비스 드롭다운 안에서:

1) fix-request.html?from=nav&type=repair
   → for-repair.html

2) fix-request.html?from=nav&type=consulting  
   → for-consultant.html

3) fix-request.html?from=nav&type=appointment
   → for-agency.html

역할별 드롭다운 안에서:

4) provider-register
   → for-expert
```

### Cursor 프롬프트 (header.js)

```
nav 메뉴 링크 변경 — nexas/assets/js/header.js

변경 4건:
1. 서비스 > "수선 연결" href: fix-request.html?from=nav&type=repair → for-repair.html
2. 서비스 > "컨설팅" href: fix-request.html?from=nav&type=consulting → for-consultant.html
3. 서비스 > "선임 연결" href: fix-request.html?from=nav&type=appointment → for-agency.html
4. 역할별 > "전문가" href: provider-register → for-expert

나머지는 절대 건드리지 마세요.

레포: taiengineering/taieng (main)
파일: nexas/assets/js/header.js
작업 완료 후 git add . && git commit -m "fix: nav 링크 — 전문가 세부 페이지 연결" && git push origin main
```

---

## 3. 작업 순서 (권장)

1. header.js nav 링크 변경 (1분) — 먼저
2. for-expert.html 허브 페이지 (10분)
3. for-agency.html (30분)
4. for-repair.html (30분)
5. for-consultant.html (30분)

※ header.js를 먼저 변경하면 for-expert/for-agency/for-repair/for-consultant 페이지가 없어서 404가 나지만,
  허브 페이지를 먼저 만들면 해결됩니다.
  따라서 순서: 2→1→3→4→5
