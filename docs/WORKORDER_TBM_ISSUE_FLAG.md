# Cursor 작업지시서 — TBM 관리감독자 화면 이상 표시 기능

> 작성일: 2026-04-30
> 대상 레포: taiengineering/tai-admin
> 난이도: 하 (소규모 UI 추가)

---

## 배경

TBM 참석자의 건강상태/보호구 이상을 기록하는 기능 추가.
설계 원칙: **이상 시에만 기록** (작업자의 체크 항목을 늘리지 않음).
작업자 서명 = "보호구 착용 완료 + 건강 이상 없음" 확인 포함.

## 완료 상태

### DB
- `tbm_attendees.issue_flag` BOOLEAN DEFAULT false — 이상 여부
- `tbm_attendees.issue_note` TEXT — 이상 사유

### 백엔드 API
```
PATCH /tbm/{tbm_id}/attendees/{attendee_id}/issue
Body: { "issue_flag": true, "issue_note": "건강이상 - 피로 호소" }
```

## 프론트엔드 수정

### 대상 파일
`tadmin/full-version/html/horizontal-menu-template/tbm-setting.html` (46KB)

### 변경 사항

참석자 목록 각 행에 "이상" 버튼 추가:

1. **참석자 테이블 헤더에 "상태" 컨럼 추가**

2. **각 참석자 행에 상태 셀 추가:**
   - issue_flag=false: `<span class="badge bg-label-success">정상</span>`
   - issue_flag=true: `<span class="badge bg-label-danger">이상</span>` + issue_note 표시

3. **"이상" 버튼 클릭 시:**
   - 작은 모달 또는 인라인 입력 표시
   - 이상 사유 입력: 텍스트 입력 (placeholder: "건강이상, 보호구 불량 등")
   - [이상 표시] 버튼 → `PATCH /tbm/{tbm_id}/attendees/{attendee_id}/issue`
   - [정상 복원] 버튼 → issue_flag=false로 PATCH

### UI 예시 (Bootstrap 5 Vuexy)

```html
<!-- 참석자 행 내 상태 셀 -->
<td class="text-center">
  <span class="badge bg-label-success" id="issue-badge-{attendee_id}">정상</span>
  <button class="btn btn-xs btn-outline-danger ms-1" onclick="showIssueInput('{attendee_id}')">
    <i class="ti tabler-alert-circle"></i>
  </button>
</td>

<!-- 이상 입력 (toggle, 기본 숨김) -->
<tr id="issue-row-{attendee_id}" class="d-none">
  <td colspan="6" class="bg-light">
    <div class="d-flex gap-2 align-items-center px-3 py-2">
      <input type="text" class="form-control form-control-sm" id="issue-note-{attendee_id}"
             placeholder="이상 사유: 건강이상, 보호구 불량, 미착용 등">
      <button class="btn btn-danger btn-sm" onclick="markIssue('{tbm_id}','{attendee_id}')">이상 표시</button>
      <button class="btn btn-secondary btn-sm" onclick="cancelIssue('{attendee_id}')">취소</button>
    </div>
  </td>
</tr>
```

### JS 함수 추가 (아래 함수를 JS 파일에 추가)

```javascript
function showIssueInput(attendeeId) {
  document.getElementById('issue-row-' + attendeeId).classList.remove('d-none');
}
function cancelIssue(attendeeId) {
  document.getElementById('issue-row-' + attendeeId).classList.add('d-none');
}
async function markIssue(tbmId, attendeeId) {
  var note = document.getElementById('issue-note-' + attendeeId).value.trim();
  if (!note) { showToast('warning', '이상 사유를 입력해주세요.'); return; }
  var res = await fetch(BASE_URL + '/tbm/' + tbmId + '/attendees/' + attendeeId + '/issue', {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ issue_flag: true, issue_note: note })
  });
  if (res.ok) {
    var badge = document.getElementById('issue-badge-' + attendeeId);
    badge.className = 'badge bg-label-danger';
    badge.textContent = '이상';
    cancelIssue(attendeeId);
    showToast('info', '이상 표시 완료');
  }
}
async function clearIssue(tbmId, attendeeId) {
  var res = await fetch(BASE_URL + '/tbm/' + tbmId + '/attendees/' + attendeeId + '/issue', {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ issue_flag: false })
  });
  if (res.ok) {
    var badge = document.getElementById('issue-badge-' + attendeeId);
    badge.className = 'badge bg-label-success';
    badge.textContent = '정상';
    showToast('info', '정상 복원 완료');
  }
}
```

## 필수 규칙
- BASE_URL = 'https://api.taieng.co.kr'
- 인증: Authorization: Bearer {access_token}
- 카카오 API 전면 금지
- 작업자 화면에는 변경 없음 (관리감독자 화면에만 추가)
