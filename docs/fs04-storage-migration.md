# FS-04 사진 업로드 → Supabase Storage 교체 가이드

**작성일:** 2026-04-16  
**버킷:** `inspections` (public, 10MB 제한, JPEG/PNG/WEBP/HEIC)  
**Migration:** `create_inspections_storage_bucket_rls` 적용 완료

---

## RLS 정책 요약

| 작업 | 대상 | 조건 |
|---|---|---|
| SELECT | 누구나 | `bucket_id = 'inspections'` |
| INSERT | 인증 사용자 | `auth.role() = 'authenticated'` + `path prefix = auth.uid()` |
| DELETE | 본인 소유만 | `owner = auth.uid()` |

---

## 파일 업로드 경로 규칙

```
inspections/{user_id}/{site_id}/{timestamp}_{filename}
```

예시:
```
inspections/abc123/site456/1713200000_photo.jpg
```

---

## 프론트엔드 교체 코드 스니펫

### 1. Supabase Storage 클라이언트 초기화

```javascript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  'https://xntdkrjhgcscmqctdzyo.supabase.co',
  '<SUPABASE_ANON_KEY>'
)
```

### 2. 사진 업로드 함수

```javascript
/**
 * 점검 사진을 Supabase Storage에 업로드
 * @param {File} file - 업로드할 이미지 파일
 * @param {string} siteId - 건설현장 ID
 * @param {string} userId - 현재 로그인 사용자 ID
 * @returns {Promise<string>} 공개 URL
 */
async function uploadInspectionPhoto(file, siteId, userId) {
  const timestamp = Date.now()
  const ext = file.name.split('.').pop()
  const filePath = `${userId}/${siteId}/${timestamp}_${file.name}`

  const { data, error } = await supabase.storage
    .from('inspections')
    .upload(filePath, file, {
      cacheControl: '3600',
      upsert: false,
      contentType: file.type,
    })

  if (error) throw new Error(`업로드 실패: ${error.message}`)

  // 공개 URL 반환
  const { data: { publicUrl } } = supabase.storage
    .from('inspections')
    .getPublicUrl(filePath)

  return publicUrl
}
```

### 3. 점검 저장 시 사진 URL 포함

```javascript
/**
 * 점검 결과 저장 (사진 포함)
 */
async function saveInspectionWithPhotos(siteId, checklistItems, photoFiles) {
  const userId = (await supabase.auth.getUser()).data.user?.id
  if (!userId) throw new Error('로그인 필요')

  // 사진 업로드 (병렬)
  const photoUrls = await Promise.all(
    photoFiles.map(file => uploadInspectionPhoto(file, siteId, userId))
  )

  // POST /construction/sites/{site_id}/inspections
  const response = await fetch(
    `https://api.taieng.co.kr/construction/sites/${siteId}/inspections`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${(await supabase.auth.getSession()).data.session?.access_token}`,
      },
      body: JSON.stringify({
        inspection_type: 'BEFORE_WORK',
        checklist_items: checklistItems,
        photo_urls: photoUrls,   // ← Storage URL 배열
      }),
    }
  )

  return response.json()
}
```

### 4. 기존 Base64 업로드에서 교체 포인트

```javascript
// BEFORE (Base64 방식 — 삭제)
// const base64 = await toBase64(file)
// body.photo_data = base64

// AFTER (Storage URL 방식)
const photoUrl = await uploadInspectionPhoto(file, siteId, userId)
body.photo_urls = [photoUrl]
```

### 5. 사진 표시

```html
<!-- construction_inspections.photo_urls 배열의 각 URL을 직접 사용 -->
<img src="https://xntdkrjhgcscmqctdzyo.supabase.co/storage/v1/object/public/inspections/{path}"
     alt="점검 사진"
     style="max-width: 200px;" />
```

---

## 파일 삭제 (정비 완료 후)

```javascript
async function deleteInspectionPhoto(filePath) {
  const { error } = await supabase.storage
    .from('inspections')
    .remove([filePath])  // 예: 'abc123/site456/1713200000_photo.jpg'

  if (error) throw new Error(`삭제 실패: ${error.message}`)
}
```

---

## 주의사항

1. **파일 경로 prefix는 반드시 `auth.uid()`** — RLS INSERT 정책 위반 시 403
2. **최대 파일 크기 10MB** — 초과 시 업로드 거부
3. **허용 MIME 타입**: `image/jpeg`, `image/png`, `image/webp`, `image/heic`, `image/heif`
4. `photo_urls` 필드는 `TEXT[]` 배열 — 단건도 배열로 감싸서 전송
5. HEIC(아이폰 기본 포맷) 허용 — 필요 시 클라이언트에서 JPEG 변환 권장 (용량 절감)
