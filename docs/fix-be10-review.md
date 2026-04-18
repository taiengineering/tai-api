# BE-10 점검 결과 — 즉시 수정 5건

**점검일**: 2026-04-18  
**점검자**: 기획창  
**대상 파일**: `routers/diagnosis_integrated.py` (SHA: e6ede9e)  
**긴급도**: 배포 전 필수 수정

---

## FIX-1: "면접" → "면책" 오타 (전체 파일)

**검색**: `면접` → **치환**: `면책`

해당 위치 (최소 8곳):
```
1. 모듈 docstring: "면접 동의 저장" → "면책 동의 저장"
2. 상수 주석: "# 면접 확정 문구" → "# 면책 확정 문구"
3. 섹션 구분선 주석: "면접 동의 저장" → "면책 동의 저장"
4. save_disclaimer docstring: "면접 동의 저장" → "면책 동의 저장"
5. HTTPException: "면접 동의 시 선택을 확인이 필요합니다." → "면책 동의를 체크해 주세요."
6. DiagnosisRunBody Field: "면접 동의 ID" → "면책 동의 ID"
7. run_diagnosis 주석: "# 2. 면접 동의 검증" → "# 2. 면책 동의 검증"
8. run_diagnosis HTTPException: "면접 동의가 필요합니다." → "면책 동의가 필요합니다."
```

---

## FIX-2: DISCLAIMER_TEXT 확정 문구로 교체

**현재 (삭제)**:
```python
DISCLAIMER_TEXT = (
    "이 진단 결과는 입력하신 사업장 정보를 기반으로 정밀 분석하여 도출된 참고 자료입니다. "
    "최종 법적 해석 및 준수 여부는 담당 안전관리자 또는 전문가와 함께 확인하시기 바랍니다. "
    "TAI Engineering은 이 진단 결과로 인한 직·간접적 손해에 대하여 재임을 지지 않습니다."
)
```

**교체**:
```python
DISCLAIMER_TEXT = (
    "본 진단 결과는 현행 법령과 사업장 정보를 정밀 분석하여 "
    "적용 가능한 법적 의무를 도출한 것입니다. "
    "본 서비스는 법률 상담·자문·의견 제공이 아니며, "
    "개별 사안에 대한 법적 판단이나 해석을 포함하지 않습니다. "
    "실제 행정 처분·감독 기준은 관할 기관의 판단에 따라 "
    "달라질 수 있으므로, 구체적 법률 적용이 필요한 경우 "
    "관할 행정기관 또는 법률 전문가에게 확인하시기 바랍니다."
)
```

**주의**: "참고 자료" 표현 금지 (서비스 질 낮게 표현), "재임" → "책임" 오타

---

## FIX-3: 가격 판정 설명 오타 (4곳)

`get_price_tier` 함수 내:

```python
# 현재 → 수정
"대형건물으로 자동 판정" → "대형건물로 자동 판정"
"소형건물으로 자동 판정" → "소형건물로 자동 판정"
"종합권로 자동 판정"     → "종합으로 자동 판정"
"기본권로 자동 판정"     → "기본으로 자동 판정"
```

---

## FIX-4: callback 주석 인코딩 깨짐

```python
# 현재:
"CI 추출 → diagnosis_auth_log upsert → auth_token HTML로 파씹 후 쿅업 닫기."

# 수정:
"CI 추출 → diagnosis_auth_log upsert → auth_token을 HTML postMessage로 전달 후 팝업 닫기."
```

---

## FIX-5: CI 평문 저장 제거 (보안)

`diagnosis_auth_callback` 함수 내 신규 CI INSERT 부분:

```python
# 현재 (보안 위험):
ins = supabase.table("diagnosis_auth_log").insert({
    "ci":          ci,           # ← 평문 CI 저장
    "ci_hash":     ci_hash,
    ...
}).execute()

# 수정 (CI 평문 제거):
ins = supabase.table("diagnosis_auth_log").insert({
    "ci":          "",           # CI 평문 저장 안 함 (ci_hash만 사용)
    "ci_hash":     ci_hash,
    ...
}).execute()
```

---

## 수정 후 확인

```bash
# 파일 내 "면접" 잔존 확인 (0건이어야 함)
grep -n "면접" routers/diagnosis_integrated.py

# "재임" 잔존 확인 (0건이어야 함)
grep -n "재임" routers/diagnosis_integrated.py

# "으로 자동" 확인 ("건물로", "종합으로", "기본으로"만 있어야 함)
grep -n "자동 판정" routers/diagnosis_integrated.py
```
