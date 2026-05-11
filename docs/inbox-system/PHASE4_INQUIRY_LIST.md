# Phase 4: 어드민 inquiry-list 확장 (통합 인박스)

**목적**: `inquiries` 테이블(Phase 1)의 `source`, `inquiry_type`, FEEDBACK 카테고리를 **문의관리 페이지 한 곳**에서 조회·필터·답변 저장까지 처리한다.  
**전제**: Phase 1 DB 적용 완료. Phase 3 notify·트리거는 배포·SQL 적용 상태와 무관하게, 본 Phase는 **어드민 UI + tai-api 관리자 API**가 중심이다.

---

## Cursor에 붙일 작업 시작 지시 (복사)

아래 블록 전체를 새 채팅(또는 Agent) 첫 메시지에 붙인 뒤, **저장소 루트에서** `tai-admin` 작업을 진행한다.

```
작업 범위: tai-admin (필요 시 tai-api 관리자 라우트 추가는 같은 PR 또는 선행 PR로 조율).

1) 컨텍스트로 다음 파일을 반드시 연다:
   - tai-api/docs/inbox-system/PHASE4_INQUIRY_LIST.md (본 지시서 전체)
   - tai-api/docs/inbox-system/README.md (채널·inquiry_type 정의)

2) 터미널에서 inquiry-list.html 위치를 먼저 확인한다. 예:
   find "$(pwd)" -name 'inquiry-list.html' 2>/dev/null
   (또는 tai-admin만: cd tai-admin && find . -name 'inquiry-list.html')

3) 확인된 경로의 inquiry-list.html을 기준으로 본 문서 §1~§7을 구현한다.

4) PR이 올라오면 검증 담당은 본 문서 §8을 따라 직접 브라우저·네트워크 탭으로 확인한다.
```

---

## §1 대상 파일

`find`로 확인한 단일 진입점(템플릿 기준 예시):

- `tai-admin/admin/full-version/html/horizontal-menu-template/inquiry-list.html`

동일 템플릿을 다른 빌드 경로로 복제했다면 **실제 배포 URL과 일치하는 파일**을 수정한다.

---

## §2 데이터·라벨 (README와 동일)

| `source`     | 표시 예        |
|-------------|----------------|
| `direct`    | 어드민 직접    |
| `marketing` | taieng 마케팅  |
| `safe`      | safe 사이트    |

| `inquiry_type` | 의미     | `category` 값 (일부) |
|----------------|----------|----------------------|
| `INQUIRY`      | 도입 문의 | consult, safety, electric, risk, csia, saas, repair, edu, partner, other |
| `FEEDBACK`     | TAI에 바란다 | fb_feature, fb_bug, fb_ux, fb_idea, fb_praise |

카테고리 한글 라벨은 기존 INQUIRY 맵을 확장하고, FEEDBACK 5종에 대한 맵을 **동일 패턴**으로 추가한다.

---

## §3 목록 UI

- **컬럼 추가(또는 재배치)**: 인입 경로(`source`), 유형(`inquiry_type`), 기존 제목·상태·일자 등과 함께 표시.
- **필터**: `source` 전체/개별, `inquiry_type` 전체/INQUIRY/FEEDBACK, 기존 검색·상태 필터와 조합 가능하게.
- **정렬**: 최소한 `created_at` 내림차순 유지; 필요 시 `no`·상태 정렬과 충돌 없게.

---

## §4 상세 패널(사이드)

- 본문·답변 영역 유지.
- **메타 표시**: `source`, `inquiry_type`, `category`(한글 라벨), `page_url`(있을 때만), `email`/`phone` 등 기존 필드.

---

## §5 API 연동 (MOCK 제거)

- `assets/js/tai/api.js`의 `apiCall` + `Bearer` 패턴을 사용한다.
- **필요한 tai-api 엔드포인트**(명칭은 구현 시 일관되게; 예시):
  - `GET /admin/inquiries` — 페이지네이션, `source`·`inquiry_type`·상태·검색 쿼리스트링.
  - `PATCH /admin/inquiries/{id}` — 답변·상태·담당 등 기존 사이드 패널 저장 필드.
- Supabase는 **서버 측 service_role**로만 접근하고, 브라우저에 service 키를 넣지 않는다.
- 기존 페이지의 `MOCK_INQUIRIES` / `MOCK_INQUIRIES_SEED` 및 관련 TODO 주석은 실제 호출로 대체 후 제거한다.

---

## §6 신규 등록(direct)

- README상 `source=direct`는 어드민에서의 신규 등록으로 정의되어 있다.
- UI에 “신규 문의” 등 진입이 있으면 `inquiry_type`·`category`·본문 등을 선택해 **POST**로 저장할 수 있게 한다(엔드포인트는 `POST /admin/inquiries` 등으로 설계).

---

## §7 오류·401

- `api.js`와 동일하게 401 시 로그인 페이지로 리다이렉트.
- 목록/저장 실패 시 사용자에게 메시지 표시(기존 토스트·alert 패턴에 맞출 것).

---

## §8 PR 검증 체크리스트 (직접 확인)

PR 리뷰어·담당은 **스테이징 또는 PR 프리뷰 URL**에서 아래를 순서대로 수행한다.

1. **로그인**: 관리자 계정으로 접속 후 `inquiry-list.html` 진입.
2. **목록 로딩**: 네트워크 탭에서 `GET` 관리자 inquiries 요청이 **200**이고, 응답 JSON에 `items`(또는 동일 역할 배열)가 비어 있거나 DB 행과 일치하는지 확인.
3. **필터**: `source`를 marketing / safe / direct(해당 데이터가 있을 때)로 바꿔 요청 쿼리와 화면 행이 일치하는지 확인.
4. **유형 필터**: `INQUIRY`만, `FEEDBACK`만 선택 시 `inquiry_type`이 맞는 행만 남는지 확인.
5. **FEEDBACK 카테고리**: `fb_*` 행이 있으면 한글 라벨이 슬랙·README 정의와 어긋나지 않는지 확인.
6. **행 클릭**: 상세 패널에 `source`, `inquiry_type`, `category`, `page_url`(있을 때)이 보이는지 확인.
7. **답변 저장**: 패널에서 답변(및 상태 변경이 있으면 함께) 저장 후 `PATCH` **200**, 재조회 시 반영 여부 확인.
8. **신규 등록**(§6 구현 시): `direct` + 선택한 유형·카테고리로 등록 후 목록에 나타나는지 확인.
9. **401**: 토큰 제거·만료 시나리오에서 로그인 페이지로 이동하는지 확인(기존 동작 유지).
10. **콘솔**: 치명적 JS 오류 없이 동작하는지 확인.

---

## 참고

- DB 스키마·RLS: `PHASE1_DB_MIGRATION.md`
- 슬랙·채널: `PHASE2_SLACK_SETUP.md`
- 신규 행 알림·Vault 트리거: `PHASE3_NOTIFY_ENDPOINT.md`, `PHASE3_PATCH_VAULT.md`
