# TAI 작업내역 — 2026-04-18

---

## 1. GPT 추가수집 데이터 DB 반영

### 미션1 — 신규 서비스 71개 추가
- connect_service_master: 144개 → **215개**
- 신규 대분류 2개 추가: **스마트/IoT**, **인력공급**
- 대분류별 추가 서비스:
  - 소방: 소화기충약및교체, 방염처리시공, 내화충전, 소방호스교체, 가스계소화설비충전, 소방펌프성능시험, 피난구유도선설치, 소방전원배터리교체 등
  - 전기: 피뢰설비점검, 피뢰침설치, 인버터점검, PLC제어반, 콘덴서뱅크교체, 변압기오일시험, 변압기교체, 차단기교체, 전력계측기설치, 비상조명회로보수
  - 기계설비: 정수기, 연수기, 자동문, 셔터게이트, 에어드라이어, 칠러세관, 열교환기세관, 코일세척, 덕트누설보수, 클린룸FFU, 냉각수배관스케일제거
  - 건축토목: 주차장차선도색, 카스토퍼, 미끄럼방지, 조경유지관리, 수목전정, 간판, 차양막, 창호교체, 도로차선도색, 코어천공, 비파괴시험, 지내력시험
  - 환경: 건설폐기물, 토양오염, 석면비산농도, 유해화학물질, 오일펜스, 집수정, 정화조
  - 안전관리: 비상대피훈련, 안전보건감사, 협력업체안전평가, 밀폐공간, 안전보호구평가, 사고조사
  - 청소위생: 에어컨분해세척, 주방후드, HACCP, 매트리스살균, 화장실소모품
  - IT보안: 화재감지시스템, 비상콜, 주차유도
  - 스마트/IoT: 원격검침, 설비원격모니터링, 누수원격감시, EMS구축
  - 인력공급: 경비용역, 주차관리용역, 시설관리인력도급

### 미션2 — 이슈 110개 추가
- connect_issue_service_map: 122개 → **232개**
- 계절성 이슈 분류:
  - 봄(123~152): 봄철 에어컨세척, 해빙기동파, 황사필터, 벌레방제 등 30건
  - 여름(153~172): 폭우침수, 냉각탑레지오넬라, 수배전반과열, 태풍복구 등 20건
  - 연중(173~232): 법령감사대응, 긴급민원, 신축증설, 임차인민원 등 60건
- season 컬럼 전체 업데이트 완료

### 미션3 — 선행/연계 관계 40건
- connect_service_relations 신규 생성 및 데이터 입력
  - PREDECESSOR(선행) 20건: 석면조사→철거, 누수탐지→방수, 수질분석→폐수처리 등
  - LINKED(연계) 20건: 냉각탑청소+수질관리, 저수조청소+수질검사, 누전+절연측정 등
  - service_a_id / service_b_id FK 컬럼 추가 → ID 연결 완료(40/40)

### 미션4 — 키워드 태그
- connect_service_master.keywords 컬럼 추가
- 기존 144개 → GPT 수집 데이터로 업데이트
- 오늘 추가된 71개도 즉시 키워드 등록
- **최종: 215/215개 키워드 100% 완료**

---

## 2. 데이터 정규화 완료

### connect_issue_service_links (신규 중간 테이블)
- issue_id FK ↔ service_id FK N:M 정규화
- 기존 TEXT[] related_services → ID 기반으로 전환
- 결과: **385개 링크**, 232개 이슈 전체 매핑(100%)

### connect_service_relations FK 연결
- service_a_id / service_b_id 컬럼 추가
- TEXT 기반 서비스명 → ID FK 자동 업데이트
- 결과: **40/40건 ID 연결 완료**

### 검증 쿼리 (동작 확인)
```sql
-- 증상 → 서비스 → 자격요건 → 단가 한 번에 JOIN
SELECT i.issue_no, i.issue_content, s.service_name,
       s.license_detail, s.price_min, s.price_max
FROM connect_issue_service_map i
JOIN connect_issue_service_links l ON l.issue_id = i.id
JOIN connect_service_master s ON s.id = l.service_id
WHERE i.issue_no = 1;
-- 결과: 분전반 타는냄새 → 누전점검/절연저항측정/분전반교체 정상 반환
```

---

## 3. 공급자 테이블 설계 및 API 구현

### DB 테이블 신규 생성

#### connect_providers
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID PK | 공급자 고유 ID |
| user_id | UUID FK | users.id 연결 |
| company_name | TEXT | 업체명 |
| biz_no | TEXT | 사업자등록번호 |
| ceo_name | TEXT | 대표자 |
| repair_fields | TEXT[] | 전문분야 배열 |
| regions | TEXT[] | 활동지역 배열 |
| license_construction | TEXT | 건설면허번호 |
| license_electric | TEXT | 전기면허번호 |
| max_amount_code | TEXT | 최대처리금액 코드 |
| status | TEXT | PENDING/APPROVED/REJECTED |
| approved_at | TIMESTAMPTZ | 승인일시 |

#### connect_provider_services
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID PK | |
| provider_id | UUID FK | connect_providers.id |
| service_id | INTEGER FK | connect_service_master.id |
| price_min | INTEGER | 최소 단가 |
| price_max | INTEGER | 최대 단가 |
| price_unit | TEXT | 건당/대당/m²당 등 |
| note | TEXT | 메모 (출장비 별도 등) |
| is_available | BOOLEAN | 제공 가능 여부 |
| UNIQUE | (provider_id, service_id) | |

### API 라우터 신규 (tai-api dev 브랜치)
**파일:** `routers/connect_provider.py`

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | /connect/provider/profile | 내 공급자 프로필 (없으면 자동생성) |
| GET | /connect/services | 전체 서비스 목록 (대분류 그룹핑) |
| GET | /connect/provider/services | 내 서비스 가격 목록 |
| POST | /connect/provider/services/upsert | 서비스 단건 저장/수정 |
| POST | /connect/provider/services/batch | 서비스 일괄 저장 |
| DELETE | /connect/provider/services/{id} | 서비스 가격 삭제 |

**main.py v5.22.0** — connect_provider_router 등록

---

## 4. 마이페이지 서비스관리 프론트

### 신규 파일
**`site/full-version/html/front-pages/mypage-provider-services.html`**

기능:
- 10개 대분류 탭 (소방/전기/기계설비/건축토목/환경/안전관리/청소위생/IT보안/스마트IoT/인력공급)
- 전체 215개 서비스 카드 표시
- 서비스별 최소금액/최대금액/단가단위/메모 입력
- 저장 버튼 클릭 시 즉시 API 반영 (upsert)
- 가격 입력된 카드: 초록색 테두리 + "입력완료" 배지
- 상단 요약: 전체/입력됨/미입력 카운트
- 대분류명 검색 기능
- 공급자 승인 상태 표시 (검토중/승인됨/거절됨)

### mypage.html 수정
- 공급자(repair) 로그인 시 "🔧 공급자 메뉴" 섹션 자동 표시
- API 호출로 공급자 여부 확인 후 동적 노출
- 서비스관리 링크 → mypage-provider-services.html

---

## 5. 완성된 TAI Fix 데이터 구조

```
[사용자 증상 입력]
        ↓
connect_issue_service_map  (232개 이슈)
        ↓ JOIN (connect_issue_service_links 385개)
connect_service_master     (215개 서비스, 키워드 100%)
        ↓
connect_service_relations  (선행20 + 연계20 = 40개)
        ↓
connect_providers          (공급자 프로필)
        ↓ JOIN (connect_provider_services)
공급자별 가격 → 매칭 후보 리스트
```

---

## 6. DB 현황 (2026-04-18 기준)

| 테이블 | 레코드 | 완성도 |
|---|---|---|
| connect_service_master | 215개 | 키워드 100% ✅ |
| connect_issue_service_map | 232개 | season 100% ✅ |
| connect_issue_service_links | 385개 | FK 정규화 100% ✅ |
| connect_service_relations | 40개 | ID FK 100% ✅ |
| connect_providers | 0건 | 테이블 생성 ✅ |
| connect_provider_services | 0건 | 테이블 생성 ✅ |
| connect_registrations | 0건 | 수요자 요청서 |
| connect_pre_registration | 0건 | 사전등록 |
| connection_commission | 6건 | 수수료 설정 |

---

## 7. 잔여 작업

### 즉시 필요
- [ ] tai-api dev → main PR 머지 (v5.22.0)
- [ ] 공급자 프로필 어드민 관리 화면 (승인/거절)
- [ ] apply-repair.html 가입 후 자동으로 connect_providers 레코드 생성 연동

### 추후
- [ ] 공급자 자격증 업로드 기능
- [ ] 공급자 위치/거리 기반 필터 (PostGIS 또는 위경도 계산)
- [ ] 증상 입력 → 서비스 자동 매칭 → 공급자 추천 API
- [ ] 공급자 평점/리뷰 시스템
- [ ] 수요자(사업장) 의뢰 → 공급자 연결 → 성사 수수료 정산

---

## 8. 시스템 현황

| 구분 | 상태 |
|---|---|
| api.taieng.co.kr (Fly.io) | 정상 |
| taieng.co.kr (Cloudflare) | 정상 |
| safe.taieng.co.kr | 정상 |
| Supabase DB | 정상 |
| tai-api dev 브랜치 | v5.22.0 배포 대기 |
