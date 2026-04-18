# BE-10: 법령진단 통합 백엔드

**작성일**: 2026-04-18  
**작성자**: 기획창  
**선행조건**: BE-08 완료, KG이니시스 통합인증 승인  
**배포**: dev → PR → main  
**참조문서**: docs/PRICING_FINAL.md, docs/DIAGNOSIS_TIER_FINAL.md

---

## 배경

법령진단을 하나의 통합 플로우로 재구성.
- 무료/유료 동일 폼, 동일 API
- 본인인증(CI) 기반 무료 3회 제한
- 가격 자동 판정 (BUILDING: 면적 5000㎡ / CONSTRUCTION: 공사금액 50억)
- 업그레이드 결제 프로세스
- 면책 동의 저장

---

## TASK 1: 본인인증 연동

### 엔드포인트

```
POST /auth/verify-identity
```

### 동작

1. KG이니시스 통합인증 API 호출 (간편인증: 네이버/PASS/토스 등)
2. 인증 성공 시 CI값 수신
3. `diagnosis_auth_log` 테이블에 저장 (ci_hash = SHA256)
4. 이미 존재하는 CI면 기존 레코드 반환
5. 세션 토큰 발급 (이후 진단 API 호출 시 필요)

### 응답

```json
{
  "status": "success",
  "auth_token": "session-token-uuid",
  "free_remaining": 3,
  "is_new": true
}
```

### 에러

| 상황 | HTTP | 메시지 |
|---|---|---|
| 인증 실패 | 401 | "본인인증에 실패했습니다" |
| 인증사 오류 | 502 | "인증 서비스 일시 오류" |

---

## TASK 2: 무료 진단 제한 확인

### 엔드포인트

```
GET /diagnosis/free-limit?auth_token={token}
```

### 동작

1. auth_token으로 CI 조회
2. `diagnosis_auth_log.free_count` 확인
3. free_count >= free_limit 이면 제한 안내

### 응답

```json
{
  "can_use_free": true,
  "free_remaining": 2,
  "free_limit": 3
}
```

---

## TASK 3: 통합 진단 실행 API

### 엔드포인트

```
POST /diagnosis/run
```

### 요청 바디

```json
{
  "auth_token": "session-token-uuid",
  "sector": "BUILDING",
  "tier": "FREE",
  "form_data": {
    "address": "서울 강남구 ...",
    "total_floor_area": 8200,
    "floor_count": 15,
    "worker_count": 30
  },
  "disclaimer_agreed": true,
  "disclaimer_agreed_at": "2026-04-18T12:00:00Z"
}
```

### 동작

1. auth_token 검증
2. tier=FREE 이면 free_count 확인 → 초과 시 402
3. disclaimer_agreed=true 확인 → false면 422
4. 기존 legal_engine diagnose_step1 호출
5. 결과 저장 (factory_diagnosis_results)
6. tier=FREE 이면 free_count + 1 업데이트
7. tier=FREE 이면 결과와 함께 BE-08 추천 엔진 자동 실행

### 응답 (무료)

```json
{
  "status": "success",
  "diagnosis_id": "uuid",
  "result": { ... },
  "free_remaining": 2,
  "recommendation": {
    "has_uncovered_areas": true,
    "uncovered_count": 82,
    "uncovered_laws": [
      {"위험물안전관리법": "위험물 보유 여부 미입력"},
      {"승강기안전관리법": "승강기 대수 미입력"}
    ],
    "max_penalty_krw": 87000000
  }
}
```

### 응답 (유료)

```json
{
  "status": "success",
  "diagnosis_id": "uuid",
  "result": { ... },
  "pdf_status": "generating",
  "pdf_email_to": "user@example.com"
}
```

---

## TASK 4: 가격 자동 판정 API

### 엔드포인트

```
GET /diagnosis/pricing?sector={}&total_floor_area={}&project_amount={}
```

### 로직

```python
if sector == 'BUILDING':
    if total_floor_area >= 5000:
        return {'code': 'BUILDING_LARGE_V2', 'price': 249000, 'label': '대형건물'}
    else:
        return {'code': 'BUILDING_V2', 'price': 99000, 'label': '소형건물'}

if sector == 'CONSTRUCTION':
    if project_amount >= 5_000_000_000:
        return {'code': 'CONSTRUCTION_PREMIUM', 'price': 299000, 'label': '종합'}
    else:
        return {'code': 'CONSTRUCTION', 'price': 145000, 'label': '기본'}

if sector == 'INDUSTRY':
    # 사용자 선택 — 자동 판정 없음
    return {'tiers': [
        {'code': 'INDUSTRY_V2', 'price': 79000, 'label': '기본'},
        {'code': 'INDUSTRY_STANDARD', 'price': 149000, 'label': '정밀'},
        {'code': 'INDUSTRY_PREMIUM', 'price': 249000, 'label': '종합'}
    ]}
```

---

## TASK 5: 업그레이드 결제 API

### 엔드포인트

```
POST /diagnosis/{diagnosis_id}/upgrade
```

### 동작

1. 기존 진단 결과 조회
2. 현재 등급 vs 상위 등급 차액 계산
   - BUILDING: 249,000 - 99,000 = **150,000원**
   - CONSTRUCTION: 299,000 - 145,000 = **154,000원**
3. KG이니시스 결제 처리 (차액만)
4. 결제 완료 → 동일 데이터로 엔진 재실행
5. 결과 업데이트

### 응답

```json
{
  "status": "success",
  "upgraded_from": "BUILDING_V2",
  "upgraded_to": "BUILDING_LARGE_V2",
  "additional_paid": 150000,
  "diagnosis_id": "uuid",
  "result": { ... }
}
```

---

## TASK 6: 면책 동의 저장

### 동의 문구 (확정)

```
본 진단 결과는 현행 법령과 사업장 정보를 정밀 분석하여
적용 가능한 법적 의무를 도출한 것입니다.

본 서비스는 법률 상담·자문·의견 제공이 아니며,
개별 사안에 대한 법적 판단이나 해석을 포함하지 않습니다.

실제 행정 처분·감독 기준은 관할 기관의 판단에 따라
달라질 수 있으므로, 구체적 법률 적용이 필요한 경우
관할 행정기관 또는 법률 전문가에게 확인하시기 바랍니다.
```

### DB 저장

`factory_diagnosis_results` 또는 별도 `diagnosis_disclaimers` 테이블에:
- ci_hash
- agreed_at
- agreed_version ("v1.0")
- ip_address

---

## TASK 7: BE-09 익명 플랜 추천 (기존 작업지시 유지)

`GET /anonymous-diagnosis/{token}/recommend-plan`

기존 `docs/workorder-be09-anon-recommend.md` 참조.

다만 **추천 응답에 가격을 포함하지 않는다.**
필요성(uncovered_laws, uncovered_count, max_penalty)만 반환.
사용자가 "이 영역까지 진단받기" 버튼을 눌러야 가격이 보임.

---

## DB 변경 요약

| 테이블 | 상태 | 내용 |
|---|---|---|
| `diagnosis_auth_log` | ✅ 생성 완료 | CI 기반 인증 + 무료 제한 |
| `diagnosis_input_fields` | ✅ 마이그레이션 완료 | tier 재구조화 |
| `price_diagnosis_report` | ✅ 업데이트 완료 | CONSTRUCTION_PREMIUM 299K |
| `factory_diagnosis_results` | 변경 없음 | 기존 구조 유지 |

---

## 금지

- CI 원본 평문 저장 금지 (암호화 저장, 조회는 ci_hash로)
- 무료 제한 우회 허용 금지 (IP/브라우저 기반 폴백 없음)
- 결과 인위적 제한 금지
- 전문가 상담 버튼 금지
- 가격 하드코딩 금지
- main 직접 커밋 금지
