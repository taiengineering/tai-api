# TAI Backend MEMORY — 2026-03-28

## API 버전
- **main.py**: v4.1.0
- **Railway**: 배포 완료

---

## 오늘 완료된 작업

### 1. 국세청 NTS 사업자등록정보 진위확인/상태조회 API ✅
- `routers/biz_verify.py` v1.0.0 (prefix: `/biz-verify`)
  - `POST /biz-verify/validate` — 진위확인 단건
  - `POST /biz-verify/validate/bulk` — 진위확인 배치 (최대 100개)
  - `POST /biz-verify/status` — 상태조회 단건
  - `POST /biz-verify/status/bulk` — 상태조회 배치 (최대 100개)
- `routers/companies.py`에 추가
  - `POST /companies/nts-verify` — 진위확인 (405 오류 수정)
  - `POST /companies/nts-status` — 상태조회
- **NTS 실제 API**: `POST https://api.odcloud.kr/api/nts-businessman/v1/validate` (POST 방식)
- 응답 필드: `valid_yn` (bool), `is_active` (계속사업자), `is_closed` (폐업)
- Railway 환경변수 `NTS_API_KEY` 삽입 완료

### 2. KOSHA 공공 API ✅
- `routers/kosha_apis.py` v1.3.0 (prefix: `/kosha`)

| 엔드포인트 | 실제 외부 URL | 비고 |
|-----------|-------------|------|
| `GET /kosha/law-search` | `B552468/srch/smartSearch` | returnType=json |
| `GET /kosha/accident-cases` | `B552468/disaster_api02/getdisaster_api02` | callApiId 고정 |
| `GET /kosha/safety-materials` | `B552468/selectMediaList01/getselectMediaList01` | |
| `GET /kosha/construction-accidents` | `B552468/constDsstr01/getconstDsstr01` | 2017~2021년 |
| `GET /kosha/msds` | `B552468/msdschem/getChemList` | ✅ 확인됨, type=json |
| `GET /kosha/msds/sections` | (내부) | 섹션 명칭 목록 |
| `GET /kosha/msds/{kmc_no}/detail` | `B552468/msdschem/getChemDetail01~16` | ✅ 확인됨 |
| `GET /kosha/kosha-guide` | `B552468/koshaguide/getKoshaGuide` | ✅ 확인됨, returnType=json |

- **MSDS API data.go.kr 페이지**: `15157612` — End Point: `B552468/msdschem`
- MSDS 섹션 01~16 (화학제품정보→기타참고사항)

### 3. 소방청 위험물 API ✅
- `routers/fire_hazmat.py` v1.0.0 (prefix: `/fire-hazmat`)
  - `GET /fire-hazmat/materials` — `1661000/materialInfoSvc/getMaterialList`
  - `GET /fire-hazmat/materials/{id}` — `1661000/materialInfoSvc/getMaterialInfo`

### 4. 안전정보 게시판 posts ✅
- **Supabase 마이그레이션**: `posts` 테이블 생성
  - 컬럼: id, category, subcategory, title, content, summary, thumbnail_url, external_url, source, source_id, tags(array), attachments(jsonb), status, is_pinned, is_featured, view_count, like_count, author_id, author_name, published_at, created_at, updated_at
  - RLS: published만 SELECT, service_role ALL
  - 인덱스: category, status, published_at, is_pinned, is_featured, title(trgm)
- `routers/posts.py` v1.0.0 (prefix: `/posts`)
  - `GET /posts` — 목록 (category/search/source/sort/page/size 필터)
  - `GET /posts/latest` — 최신글 (인증 불필요, 메인 노출용)
  - `GET /posts/stats/today` — 오늘 통계 (위젯용)
  - `GET /posts/{id}` — 상세 + view_count+1 + 이전/다음글
  - `POST /posts` — 작성
  - `PATCH /posts/{id}` — 수정
  - `DELETE /posts/{id}` — soft delete (status → hidden)
- 카테고리: notice, safety_news, law_update, accident_case, kosha_guide, msds, hazmat, general

### 5. report_forms.py 버그 수정 ✅
- **v2.0.1**: `bylSeq` → `bylseq` (PostgreSQL 컬럼명 소문자 정정) — `/templates` 500 오류 해결

### 6. WeasyPrint → xhtml2pdf 전환 ✅
- **v2.0.2**: Railway 환경에서 `libgobject-2.0-0` GTK 라이브러리 없음 오류 해결
- `requirements.txt`: `weasyprint` → `xhtml2pdf`
- `nixpacks.toml`: GTK 패키지 제거 (불필요)
- `_generate_pdf_bytes()`: xhtml2pdf 전용, UTF-8 인코딩 명시

---

## 현재 라우터 전체 목록 (main.py v4.1.0)

| 파일 | prefix | 버전 | 상태 |
|------|--------|------|------|
| auth.py | /auth | - | ✅ |
| users.py | /users | - | ✅ |
| companies.py | /companies | - | ✅ (nts-verify 추가) |
| factories.py | /factories | - | ✅ |
| system_codes.py | /system-codes | v2.0.0 | ✅ |
| legal_engine.py | /legal-engine | v4.1.2 | ✅ |
| ksic_engine.py | /ksic-engine | v3 | ✅ |
| factory_process_v3.py | /factory-process | v3 | ✅ |
| process_management.py | /process-management | v1.1 | ✅ |
| building_register.py | /building-register | v2.3.0 | ✅ |
| quotes.py | /quotes | - | ✅ |
| report_forms.py | /report-forms | v2.0.2 | ✅ |
| contracts.py | - | - | ⚠️ 503 미확인 |
| contacts.py | /contacts | - | ✅ |
| education.py | /education | - | ✅ |
| notifications.py | /notifications | - | ✅ |
| equipment_assets.py | /equipment-assets | v1.2.0 | ✅ |
| engine_equipment.py | /engine-equipment | v1.2.2 | ✅ |
| engine_model.py | /engine-model | v1.0.0 | ✅ |
| personnel.py | /personnel | v1.1.0 | ✅ |
| repair.py | /repair | v1.0.0 | ✅ |
| biz_verify.py | /biz-verify | v1.0.0 | ✅ |
| kosha_apis.py | /kosha | v1.3.0 | ✅ |
| fire_hazmat.py | /fire-hazmat | v1.0.0 | ✅ |
| posts.py | /posts | v1.0.0 | ✅ |
| schedule_engine.py | /schedule-engine | - | ✅ |
| roles.py | /roles | - | ✅ |
| teams.py | /teams | - | ✅ |
| areas.py | /areas | - | ✅ |
| buildings.py | /buildings | - | ✅ |
| inspection_sets.py | /inspection-sets | - | ✅ |
| work_schedules.py | /work-schedules | - | ✅ |
| inspection_checklist.py | /inspection | v1.1.0 | ✅ |
| admin_stats.py | /admin | v1.0.0 | ✅ |

---

## 공공 API 인증키 및 엔드포인트 정리

```
공통 인증키: da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b
환경변수: BUILDING_API_KEY / NTS_API_KEY (Railway 설정 완료)

국세청 NTS: https://api.odcloud.kr/api/nts-businessman/v1
  POST /validate  (진위확인) — body: {businesses: [{b_no, start_dt, p_nm, ...}]}
  POST /status    (상태조회) — body: {b_no: ["번호"]}

KOSHA: https://apis.data.go.kr/B552468
  srch/smartSearch                          ✅ 법령 스마트검색
  disaster_api02/getdisaster_api02          ✅ 국내재해사례
  selectMediaList01/getselectMediaList01    ✅ 안전보건자료 링크
  constDsstr01/getconstDsstr01              ✅ 건설업 중대재해
  msdschem/getChemList                      ✅ MSDS 목록 (data.go.kr: 15157612)
  msdschem/getChemDetail01~16               ✅ MSDS 섹션별 상세
  koshaguide/getKoshaGuide                  ✅ 코샤가이드

소방청: https://apis.data.go.kr/1661000/materialInfoSvc
  getMaterialList  ✅ 위험물 목록
  getMaterialInfo  ✅ 위험물 상세
```

---

## DB 변경사항

### 신규 테이블
- `posts` — 안전정보 게시판

### 수정된 컬럼 인식
- `form_templates.bylseq` (소문자) — 기존 코드 `bylSeq` 오류 수정

---

## 미완료 / PENDING

| 항목 | 내용 |
|------|------|
| contracts 503 | Railway 런타임 로그 확인 필요 |
| 행정안전부 안전정보 통합공개 | 승인됨, URL 미확인 — data.go.kr 로그인 후 확인 필요 |
| MSDS API 정상 응답 확인 | type=json 추가했으나 실제 데이터 반환 여부 미테스트 |
| kosha-guide body 데이터 | returnType=json 추가했으나 빈 body 원인 추가 확인 필요 |

---

## 주요 원칙 / 트러블슈팅 기록

- **PostgreSQL 컬럼명**: 항상 소문자 (bylseq ✓, bylSeq ✗)
- **main.py 수정**: 반드시 단독 `create_or_update_file`로 (push_files와 혼용 시 SHA 충돌)
- **FastAPI 라우팅 순서**: `/msds/sections`를 `/msds/{kmc_no}/detail` 보다 먼저 선언
- **Railway PDF**: WeasyPrint(GTK 의존) 사용 불가 → xhtml2pdf(순수 Python) 사용
- **KOSHA API returnType**: 각 엔드포인트별 명시 필요 (기본값 없음)
- **NTS API**: GET 아닌 POST 방식, serviceKey는 query string, body는 JSON body로 분리
