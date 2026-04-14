# TAI Fix 설계 세션 — 2026-04-14

## 세션 목적
TAI Fix (시설/안전 서비스 매칭 플랫폼) DB 설계 및 업체 등록 구조 수립

---

## 완료 항목

### 1. 특허 출원 2건 추가
- **제10-2026-0067712** (DAS 8690): 증상 기반 시설 안전 서비스 자동 매칭 및 법령 연계 자격요건 검증 시스템 → TAI Fix 핵심 특허
- **제10-2026-0067716** (DAS CFD4): 관리 데이터 기반 법령 연계 안전 문서 자동 생성 및 신고 처리 시스템 → TAI Safe 문서·자동신고 특허
- patents.html, index.html, about.html, footer.js 모두 8건으로 업데이트
- 푸터 메뉴명 '특허출원중' → 'TAI 기술력' 변경

### 2. TAI Fix DB 스키마 설계 (Supabase 마이그레이션 완료)

#### 분류 체계 (3계층)
```
fix_category (대분류 8개)
 └─ fix_subcategory (중분류 38개 활성, grade A/B)
      └─ connect_service_master (소분류 144개, 확장예정 1000+)
           ├─ service_grade (A=핵심/B=확장/C=제외)
           ├─ pricing_type (FIXED=정형/QUOTE=견적)
           └─ pricing_unit (월/건/회/년)
```

#### 서비스 등급 기준 (A/B/C)
- **A등급 (21개 중분류):** 법정의무 or 자격필수 or 안전직결 → TAI만 할 수 있는 것
- **B등급 (17개 중분류):** 전문성 필요, 잘못 맡기면 손해 → TAI가 하면 더 나은 것
- **C등급 (3개, 비활성):** 숨고 영역 (건물청소, 폐기물분리수거, 네트워크서버)

#### 자격 마스터
```
fix_qualification_master (58개)
  - LICENSE (법정면허): 13개
  - REGISTRATION (등록/신고): 19개
  - CERT (자격증): 13개
  - CAPABILITY (업무역량): 13개
```

#### 업체 테이블
```
fix_providers (업체 프로필)
  ├─ fix_provider_qualifications (인허가 + 인력 통합)
  │    LICENSE/REGISTRATION → headcount=1 (유무)
  │    CERT → headcount=보유인원수 (검색→선택→몇명)
  └─ fix_provider_services (중분류 선택 + 가격)

fix_provider_overview (매칭용 통합 뷰)
```

### 3. 144개 소분류 매핑 완료
- 137개 활성 서비스에 subcategory_id 매핑
- pricing_type (FIXED 45개 / QUOTE 92개) 설정
- service_grade (A 50개 / B 87개 / C 7개) 설정

### 4. 업체 등록 페이지 생성
- 파일: `nexas/provider-register.html`
- 4단계 스텝 폼: 기본정보 → 보유자격 → 제공서비스 → 확인·등록
- 자격 검색 드롭다운 (면허/등록/자격증/역량 색상 구분)
- 중분류 체크 (대분류 탭 전환, A등급 뱃지)
- 지역 선택 (전국 토글)
- API 연동 TODO 마킹

### 5. 카카오 API 완전 제거
- `routers/juso.py`: 카카오 로컬 API → 행안부 도로명주소 API + 좌표제공 API 전면 교체
- 환경변수: JUSO_API_KEY (Fly.io 등록 완료)
- fix_providers에 latitude, longitude 컬럼 추가
- 메모리에 【절대금지】카카오 API 사용금지 등록

### 6. 매칭 파이프라인 검증
테스트 데이터로 전체 흐름 확인:
```
"분전반에서 타는 냄새가 난다"
 → 누전점검, 절연저항측정, 분전반교체 (소분류)
 → 전기점검/진단, 전기수리/보수 (중분류)
 → 대성전기종합안전 매칭 ✅ (인허가3건, 자격인력6명, 검증률67%)
```

---

## 핵심 설계 결정사항

| 결정 | 내용 |
|---|---|
| 업체 유형 구분 | 하지 않음. 중분류 선택이 업체 성격을 결정 |
| 인력 등록 | 실명 없음. 자격 검색→선택→인원수만 |
| 가격 입력 | 등록 시 미수집. 등록 후 별도 |
| 서비스 등급 | A(핵심)+B(확장)만 TAI Fix 범위, C는 제외 |
| 프론트 통합/분리 | 수요자=통합입구, 공급자=분야별 랜딩(추후) |
| 카카오 API | 전면 금지. 주소=행안부, 알림=메세지미 |

---

## 내일 작업 예정 (TAI Fix 계속)

- 업체 등록 페이지 고도화 (행안부 주소검색, 본인인증, 사업자검증, 인허가/인력 탭분리, 완료페이지)
- 업체 등록 백엔드 API (POST /connect/providers)
- fix_service_qualification_map 데이터 채우기 (서비스별 필수 자격 매핑)
- 수요자 UI 설계 시작 (증상 입력 → 매칭 결과)

---

## DB 테이블 현황 (TAI Fix 관련)

| 테이블 | 레코드 | 상태 |
|---|---|---|
| fix_category | 8 | ✅ |
| fix_subcategory | 41 (38 활성) | ✅ |
| fix_qualification_master | 58 | ✅ |
| fix_service_qualification_map | 0 | TODO |
| fix_providers | 0 | 테이블 생성 완료 |
| fix_provider_qualifications | 0 | 테이블 생성 완료 |
| fix_provider_services | 0 | 테이블 생성 완료 |
| connect_service_master | 144 (137 활성) | ✅ 매핑 완료 |
| connect_issue_service_map | 122 | ✅ |
| connection_commission | 6 | 기존 |
| matching_requests | 3 | 기존 |
| matching_results | 0 | 기존 |
| matching_contracts | 0 | 기존 |
