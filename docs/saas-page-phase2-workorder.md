# SaaS 페이지 Phase 2 보완 작업지시

> 파일: `nexas/service/saas.html` (taieng 레포, Cursor 필수)
> Phase 1 배포 확인 완료. 라이브 페이지 점검 기반.

---

## 현재 라이브 상태 (✅ = 정상, ❌ = 수정 필요)

| 섹션 | 상태 | 내용 |
|---|---|---|
| 히어로 | ✅ | "귀사에 적용되는 안전 법령, 몇 개인지 아십니까?" |
| 공감 | ✅ | 08:00~18:00 타임라인 + SVG |
| AS-IS/TO-BE | ✅ | 인라인 SVG 다이어그램 |
| 핵심 기능 5개 | ❌ | 기능⑤ 내용 변질 (기상→감사대응) |
| 법령엔진 | ✅ | 473/33,845 숫자 + SVG |
| 중대재해처벌법 | ✅ | 유지 |
| 도입 4단계 | ❌ | 세팅 대행 안내 누락 |
| 요금제 | ❌ | 건물 STANDARD 145K 누락 |
| 최종 CTA | ✅ | 정상 |
| PG/결제 | ✅ | spPay + INIStdPay 정상 |
| 총책임자 섹션 | ✅ | 삭제 완료 |
| 카운트업 | ❓ | scope 2개 존재, 실제 동작 확인 필요 |

---

## 수정 항목

### M-1. 건물 요금제: STANDARD 145K 추가 [필수]

현재: STARTER 59K → PRO 249K → ENTERPRISE (**2티어**)
PRICING_FINAL.md: STARTER 59K → STANDARD 145K → PRO 249K → ENTERPRISE (**3티어**)

**STANDARD 카드 추가 (기존 STARTER와 PRO 사이에):**
```
STANDARD
건물 정밀관리
145,000원 /월 · VAT 별도 · 건물 1개

스타터 플랜 전체 포함
소방시설 자체점검 연동
승강기 검사 주기 관리
위반 위험 사전 알림

[결제하기]
```

PRO 카드의 기존 기능에서 STANDARD로 이동한 항목 제거:
- 소방시설 자체점검 연동
- 승강기 검사 주기 관리
- 위반 위험 사전 알림

PRO는 STANDARD 포함 + 석면·에너지 점검 + 법정 서식 자동 생성

**spPay onclick 수정 필요:**
- STANDARD 카드의 결제 버튼: `spPay(event,'SAAS','BUILDING_STANDARD',145000,'건물 정밀관리')`
- 기존 planCode 확인: price_saas_plan 테이블에 BUILDING_STANDARD 행이 있는지 DB 확인 필요

---

### M-2. 기능⑤ 복원: "기상 작업중지 감시" [필수]

현재: 기능⑤ = "감사·감독 앞에서 '여기 있습니다'" (기록 보관 내용)
작업지시서: 기능⑤ = "기상 작업중지 자동 감시"

**변경:**
```
헤드라인: "폭염특보인데
         작업 계속해도 되는 건가?"

해결: 기상청 API 30분 간격 자동 확인
     강풍·폭염·한파 법정 기준 감지 시
     작업중지 권고 알림 자동 발송

포인트:
• 기상청 API 30분 간격 자동 확인
• 강풍·폭염·한파 법정 기준 감지
• 작업중지 이행 기록 자동 보관
```

목업 비주얼: 날씨 대시보드 위젯 (온도·풍속 + 경고 상태)

현재 "감사 대응" 내용은 삭제 — AS-IS/TO-BE 섹션과 도입 섹션에서 충분히 전달됨.

---

### M-3. 도입 섹션: 세팅 대행 안내 추가 [권장]

도입 4단계 하단에 박스 추가:
```html
<div style="background:#f1f5f9; border-radius:12px; padding:20px; margin-top:32px; text-align:center;">
  <p style="font-size:15px; color:#475569; margin:0;">
    직접 세팅이 어려우시면 TAI가 대행합니다.<br>
    <span style="font-size:13px; color:#94a3b8;">기본 20만원 + 설비당 2~3만원 (견적 기반)</span>
  </p>
  <a href="mailto:tai@taieng.co.kr" style="display:inline-block; margin-top:12px; font-size:14px; color:#2563eb;">세팅 대행 문의 →</a>
</div>
```

---

### M-4. 카운트업 동작 확인 [확인]

sp-count-scope가 2개 존재하지만 내부 요소가 감지되지 않음.

확인 방법:
1. 페이지를 열고 스크롤하면서 히어로의 127+가 카운트업 되는지 육안 확인
2. 법령엔진 섹션의 473, 33,845가 카운트업 되는지 확인
3. 안 되면 Cursor에게 IIFE 코드 점검 요청

---

### M-5. 산업 요금제 플랜명 확인 [대표님 확인 필요]

현재 페이지: STARTER 79K → PRO 149K → BUSINESS 249K
PRICING_FINAL.md: STARTER 79K → BUSINESS 149K → PRO 249K

금액은 맞지만 **이름 순서가 반대.**
두 가지 옵션:
- A) 현재 페이지 유지 (PRO=149K, BUSINESS=249K)
- B) PRICING_FINAL.md 기준으로 수정 (BUSINESS=149K, PRO=249K)

→ 대표님 결정 필요.

---

## 삭제 대상

| 삭제 항목 | 이유 |
|---|---|
| 기능⑤ "감사·감독 앞에서" 전체 | → 기상 작업중지로 교체 |

---

## 최종 섹션 순서 (확정)

```
0. 히어로 — "몇 개인지 아십니까?" ✅
1. 공감 — 08:00~18:00 타임라인 ✅
2. AS-IS/TO-BE — SVG 다이어그램 ✅
3. 핵심 기능 5개 — ①캘린더/알림 ②점검 ③TBM ④법령추적 ⑤기상감시(수정)
4. 법령엔진 — 473/33,845 ✅
5. 중대재해처벌법 — 과태료/처벌 ✅
6. 도입 4단계 — "오늘 가입하면 내일 점검" + 세팅대행(수정)
7. 요금제 — 건물 3티어 추가(수정)
8. 최종 CTA ✅
```

---

## Cursor 프롬프트

```
SaaS 페이지 Phase 2 보완 — nexas/service/saas.html

기준 문서: tai-api 레포 docs/saas-page-phase2-workorder.md (dev)

수정 3건:

1. 건물 요금제: STARTER(59K)와 PRO(249K) 사이에 STANDARD 카드 추가
   - STANDARD / 건물 정밀관리 / 145,000원
   - 스타터 플랜 전체 포함 + 소방자체점검 + 승강기 + 위반알림
   - PRO에서 위 3개 항목 제거, PRO = STANDARD 포함 + 석면에너지 + 법정서식
   - 결제 버튼: spPay(event,'SAAS','BUILDING_STANDARD',145000,'건물 정밀관리')

2. 기능⑤ 교체: "감사·감독 앞에서" → "기상 작업중지 감시"
   - 헤드라인: "폭염특보인데 작업 계속해도 되는 건가?"
   - 해결: 기상청 API 30분 간격 자동 확인, 법정 기준 초과 시 작업중지 권고
   - 목업: 날씨 대시보드 위젯 (온도/풍속 + 경고 상태)
   - 좌우 배치: 텍스트 좌, 폰 우 (홈수)

3. 도입 섹션 하단에 세팅 대행 안내 박스 추가
   - "직접 세팅이 어려우시면 TAI가 대행합니다."
   - "기본 20만원 + 설비당 2~3만원 (견적 기반)"

절대 건드리지 마세요:
- spPay() 함수
- sp_inicis_form
- 섹터 탭 전환 IIFE
- 카운트업 IIFE
```
