# TAI 작업내역 — 2026-04-14

---

## 1. taieng.co.kr 이니시스 심사 대응 (tai-admin)

### 완료
- `front-pages/pricing.html` 신규 생성
  - 정기결제 탭: 산업 STARTER 79K / BUSINESS 149K / PRO 249K, 건물 BASIC 59K / STANDARD 99K, 건설 STANDARD 199K / PREMIUM 399K
  - 일반결제 탭: 법령진단 단건 (건물 99K~299K, 산업 99K~249K, 건설 299K)
  - KG이니시스 심사 요건 충족 (일반결제+정기결제 동시 노출)
- `front-pages/refund.html` 신규 생성
  - 환불정책 비교표 포함 (이니시스 심사 필수 페이지)
  - 구독취소/단건구매 각각 조건 명시
- `front-pages/assets/tai-footer.js` v3.2 업데이트
  - 이용안내에 요금제·환불정책 링크 추가
- `home/index.html` v4 업데이트
  - 네비게이션에 요금제 링크 추가

### 이니시스 테스트 계정 생성
- 이메일: `inicis@taieng.co.kr`
- 비밀번호: `TAIreview2026!`
- 로그인 URL: `taieng.co.kr/front-pages/login.html`
- 계정 상태: ACTIVE (로그인 테스트 완료)

### 이니시스 현황
- MID: `taieng4350`, 코드 구현 완료
- 실결제 성공: 0건 (32건 전부 PENDING — 심사 미완료)
- 정기결제 MID: 별도 전자계약 필요

---

## 2. Supabase 스토리지 정비

### 버킷 현황 (총 11개)
| 버킷명 | 공개 | 용도 |
|---|---|---|
| inspection-images | 공개 | 점검 사진 |
| facility-drawings | 공개 | 시설 도면 |
| company-logo | 공개 | 회사 로고 |
| site-assets | **공개 (신규)** | 사이트 배경 이미지 |
| expert-documents | 비공개 | 전문가 서류 |
| contracts | 비공개 | 계약서 |
| final-reports | 비공개 | 최종 리포트 |
| mail-attachments | 비공개 | 메일 첨부 |
| form-originals | 비공개 | 서식 HWP 원본 |
| form-templates | 비공개 | 서식 HTML 템플릿 |
| form-outputs | 비공개 | 생성된 PDF |

### site-assets 버킷 업로드
- `tec_hiro_back.png` (1276×816px) — patents.html 히어로 배경용
- URL: `https://xntdkrjhgcscmqctdzyo.supabase.co/storage/v1/object/public/site-assets/tec_hiro_back.png`

---

## 3. TAI Fix 연결서비스 DB 구축 (Supabase)

### 신규 테이블 생성

#### connect_service_master
- 서비스 마스터 144개 (8대 분류)
- 컬럼: service_name, category, sectors[], license_required, license_detail, is_legal_duty, demand_frequency, price_min, price_max

| 대분류 | 서비스 수 |
|---|---|
| 소방 | 15개 |
| 전기 | 20개 |
| 기계설비 | 30개 |
| 건축토목 | 36개 |
| 환경 | 12개 |
| 안전관리 | 15개 |
| 청소위생 | 14개 |
| IT보안 | 5개 |
| **합계** | **147개** |

#### connect_issue_service_map
- 이슈-서비스 매핑 122개
- 컬럼: issue_no, issue_content, sectors[], related_services[], urgency, created_at
- 긴급 이슈(URGENT): 35건 🔴
- 일반 이슈(NORMAL): 67건 🟡
- 예방 이슈(PREVENTIVE): 20건 🟢

### 데이터 부족 분석 (추가 수집 필요)
| 항목 | 현재 | 목표 |
|---|---|---|
| 서비스 수 | 144개 | 200개+ |
| 이슈 수 | 122개 | 300개+ |
| 계절성 이슈 | 없음 | 30개+ |
| 긴급 대응 이슈 | 35개 | 55개+ |
| 공급자 테이블 | 없음 | 설계 필요 |
| 키워드/태그 | 없음 | 서비스별 5~10개 |

### GPT 추가 수집 프롬프트 작성 완료
- 미션1: 누락 서비스 60개+ 추가
- 미션2: 이슈 180개+ 추가 (카테고리A~E)
- 미션3: 서비스 선후행/연계 관계
- 미션4: 자연어 검색용 키워드 태그

---

## 4. TAI Fix 증상 기반 매칭 설계

### 핵심 아이디어 확정
```
사용자 입력: "분전반에서 타는 냄새가 난다"
         ↓
AI 판단:
- 긴급도: URGENT 🔴
- 필요 서비스: 누전점검, 절연저항 측정, 분전반 교체
- 필요 자격: 전기공사업
- 법정의무: N
- 유사 증상 제시: 차단기 반복 트립, 고압케이블 과열, 접지불량
```

### 숨고/크몽 차별화 포인트
- 숨고: 사용자가 서비스 카테고리 직접 선택
- TAI Fix: 증상 입력 → AI 분류 → 자격 검증된 업체 매칭

### 연결서비스 유형 정의
- 선임연결 / 대행연결 / 수선연결 / 진단연결 / 컨설팅연결

---

## 5. new.taieng.co.kr 작업 (taieng repo)

### patents.html
- 히어로 배경 이미지 적용 시도 (tec_hiro_back.png)
- 오버레이 투명도 조정 테스트 (0.82 → 0.40 → 0.20 순차 테스트)
- **최종: 원복** (다크 네이비 그라디언트 유지)
- 이유: 배경 이미지 선명도 vs 텍스트 가독성 균형 미달

### 네비게이션 문제 확인
- 진입시: 투명 navbar → 흰색 메뉴 텍스트 안 보임
- 스크롤시: Nexas 기본 보라색(--color-primary)으로 변경
- tai-main.css 오버라이드 시도 → **원복**
- **미해결 상태** — 추후 style.css `--color-primary` 변수 수정 또는 header.js 재작성 필요

---

## 6. 잔여 작업

### 즉시 필요
- [ ] GPT 추가 수집 → connect_service_master/issues 보강
- [ ] connect_providers 테이블 설계 (공급자 프로필)
- [ ] connect_service_master.keywords 컬럼 추가
- [ ] new.taieng.co.kr 네비게이션 보라색 → TAI 네이비 수정
- [ ] patents.html 배경 이미지 재검토 (더 어두운 이미지 필요)

### 이니시스
- [ ] 신혜영 담당자에게 회신
  - pricing.html URL: `taieng.co.kr/front-pages/pricing.html`
  - 테스트 계정: `inicis@taieng.co.kr` / `TAIreview2026!`
- [ ] 정기결제 MID 전자계약 진행

---

## 7. 시스템 현황

| 구분 | 상태 |
|---|---|
| api.taieng.co.kr (Fly.io Tokyo) | 정상 |
| taieng.co.kr (Cloudflare Pages) | 정상 |
| safe.taieng.co.kr (Cloudflare Pages) | 정상 |
| new.taieng.co.kr (Cloudflare Pages) | 정상 |
| Supabase DB | 정상 |
| KG이니시스 결제 | PENDING (심사중) |
| 메세지미 SMS | 연결됨 |
