# 이슈 목록 — 2026-04-18 프론트엔드/백엔드 개발 세션

> 검토일: 2026-04-19  
> 이슈 구분: 플로우차단(타타마타) / 경고(주의) / 정보(이후 대응)

---

## ISSUE-01 🟥 [BLOCKER] `for-safety-manager.html` 페이지 미존재

**발생 위치**: `nexas/free-diagnosis-result.html` S7 SaaS 섹션 버튼

```html
<!-- 현재 코드 -->
<a class="btn-saas" href="for-safety-manager.html">TAI Safe 더 알아보기 →</a>
```

**증상**: 버튼 클릭 시 `nexas/for-safety-manager.html` 404 발생

**원인**: 해당 페이지가 아직 제작되지 않았음. 2026-04-12 확정 사이트맵에 포함된 페이지이나 미완성 상태.

**임시조치**: `for-safety-manager.html` 제작 전까지`https://safe.taieng.co.kr`로 다시 연결하거나, 링크에 `target="_blank"` 추가

**우선순위**: 플로우 차단 — 즉시 대응 필요

---

## ISSUE-02 🟡 [WARNING] xhtml2pdf 외부 SVG 렌더링 불가 가능성

**발생 위치**: `templates/diagnosis_report_paid.html` P9 (SECTION 04)

```html
<img
  src="https://xntdkrjhgcscmqctdzyo.supabase.co/storage/v1/object/public/diagrams/11-..."
  style="max-width: 160mm; height: auto;"
>
```

**증상**: xhtml2pdf는 외부 URL에서 SVG를 렌더링하는 데 제약이 있음. PDF 생성 시 P9 다이어그램이 빈 영역으로 레더링되거나 에러 발생 가능성 있음.

**원인**: 
- xhtml2pdf는 외부 리소스 추적 기능이 제한적임
- SVG MIME type 처리가 `image/svg+xml`이라 일부 환경에서 표시 안 됨

**대안**:
1. PNG로 사전 변환하여 Supabase 업로드 후 험페이지에 img 태그 교체
2. 향후 Gotenberg(Chromium 기반) 이전 시 자동 해결예정
3. 임시: 테이블/텍스트 방식으로 대체 (비포애프터 들어가는 입장 설명 텍스트)

**우선순위**: Gotenberg 이전 전 반드시 조치 필요

---

## ISSUE-03 🟡 [WARNING] `/diagnosis/result/{token}` API 엔드포인트 미구현

**발생 위치**: `nexas/free-diagnosis-result.html` fetchResult 함수

```javascript
const r = await fetch(`${API}/diagnosis/result/${token}`);
```

**증상**: 해당 API가 아직 구현되지 않아 404 반환 → MOCK_DATA fallback 모드로 동작

**현재 실제 프로덕션 영향**: MOCK_DATA fallback이 타승 동작하지만 `?token=` 파라미터가 있는 실제 페이지에서 진단 결과가 일치하지 않음

**필요 작업**: `diagnosis_integrated.py` 또는 신규 라우터에 `GET /diagnosis/result/{public_token}` 구현
- `anonymous_diagnosis_results` 테이블에서 `partial_result` 반환 (링크 만료 검증 포함)

**우선순위**: FE-BE 연동 전 반드시 전형

---

## ISSUE-04 🟡 [WARNING] DEV_TOKEN 사용 시 CI 해시 빈 문자열 문제

**발생 위치**: `nexas/free-diagnosis.html` openInicisPopup 함수

```javascript
function openInicisPopup(params) {
  if (typeof INIStdPay !== 'undefined') {
    INIStdPay.pay(params);
  } else {
    // 이니시스 미연동 시 fallback
    onAuthSuccess({ auth_token: 'DEV_TOKEN_' + Date.now() });
  }
}
```

**증상**: DEV_TOKEN으로 `onAuthSuccess` 호출 시:
- `diagnosis_integrated.py`의 `onAuthSuccess` 내에서 `auth/check?auth_token=DEV_TOKEN_...` 요청
- `diagnosis_auth_log` 테이블에 `DEV_TOKEN_...`으로는 레코드가 없으므로 401 반환
- 프론트는 `remaining=3` 기본값 사용하지만 실제 인증 통과 안 됨

**대안**: 개발/테스트 환경에서 DEV 모드 감지 후 `diagnosis_auth_log`에 테스트 레코드 시딩하거나, BE에서 DEV_TOKEN_ 프리픽스 탐지 시 bypass 로직 추가

**우선순위**: KG이니시스 승인 전까지 유지해야 하는 데브 경로이므로 반드시 수정

---

## ISSUE-05 🟢 [INFO] EXTRA-1 selectAddr DOM 의존성

**발생 위치**: `nexas/free-diagnosis.html` selectAddr 함수

```javascript
const addrWrap = document.querySelector(`[data-addr-prefix="${prefix}"]`)?.closest('.addr-wrap');
const addrKey = addrWrap?.dataset?.addrKey || 'address';
```

**내용**: `renderField()`에서 생성된 `.addr-wrap[data-addr-key]` 속성을 `closest()`로 찾는 방식

**위험**: 향후 `renderField()` 내 HTML 구조 변경 시 탐지 실패 가능성이 있음. 현재는 정상 동작.

**대안**: `selectAddr` 호출 시 `addrKey` 인자를 함께 넘기는 방식으로 리팩토링 (베타 세솠 우선)

---

## ISSUE-06 🟢 [INFO] free-diagnosis.html — BUG-5/7/8/9 확인 진행 필요

`nexas/docs/fix-fn08-v2-full-bugs.md` 에서 엘스툅 빠진 BUG 항목:

| # | 내용 | 현황 |
|---|---|---|
| BUG-5 | 주소검색 재확인 | FN-FIX-1로 배열 처리 완료. 테스트 후 쿠시업 |
| BUG-7 | 좌측 패널 동적 분기 (셉터별 문구) | 미적용 — 커틀구조상 좌측은 등록된 셀렉터 없습니다 |
| BUG-8 | 주소 필드 최상단 노출 | 대표님 판단 대기 |
| BUG-9 | CTA 문구 변경 | S6 HTML에서 "현재 진단에서 확인할 수 없는 영역이 있습니다" 이미 적용 |

---

## ISSUE-07 🟢 [INFO] `tri_state` 의무 필드 API 기준 없음

**발생 위치**: `nexas/free-diagnosis.html` BUG-11 수정

**내용**: DB에 `field_type = 'tri_state'`인 필드 58개가 있으나, `/diagnosis/fields` API가 이 field_type을 정상 리턴하는지 확인이 필요함.

**확인 방법**: Supabase SQL로 `SELECT DISTINCT field_type FROM diagnosis_field_master` 조회

---

## ISSUE-08 🟢 [INFO] diagnosis_report.py — `_build_law_groups` Python 3.9 타입 힌트 호환성

**발생 위치**: `routers/diagnosis_report.py`

```python
def _build_law_groups(
    rules: List[Dict[str, Any]],
    max_groups: int = 10,
) -> tuple[List[Dict[str, Any]], int]:  # ← Python 3.9+ 전용
```

**설명**: `tuple[...]` 내장 타입 지정 구문은 Python 3.9+에서만 유효. 3.8 환경이면 `Tuple[...]`을 `from typing import Tuple`로 사용해야 함.

**Fly.io Tokyo 실제 버전 확인 후 판단** — 현재 Fly.io는 Python 3.11 사용 중이므로 실제 플레스함.

---

## 향후 할 일 요약

| 우선순위 | 항목 | 담당 |
|---|---|---|
| 타타마타 | `for-safety-manager.html` 제작 또는 임시 링크 수정 | 프론트엔드창 |
| 타타마타 | `GET /diagnosis/result/{public_token}` BE 구현 | 백엔드창 |
| 경고 | P9 SVG 렌더링 테스트 (xhtml2pdf 실제 실행 후 확인) | 백엔드창 |
| 경고 | DEV_TOKEN bypass 로직 BE 추가 | 백엔드창 |
| 정보 | `tri_state` API 필드 리턴 확인 | Supabase MCP |
