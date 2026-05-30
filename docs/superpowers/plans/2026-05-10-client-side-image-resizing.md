# Client-Side Image Resizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resize oversized OCR images in the browser before upload so phone photos do not exceed upload/OCR limits.

**Architecture:** Keep the existing multipart `POST /api/ocr-drafts` contract. Add a small frontend preprocessing layer that converts oversized selected images to JPEG blobs before building `FormData`; the server stores whatever bytes the client uploads.

**Tech Stack:** Plain HTML/CSS/JavaScript, browser `Image`, `canvas`, `Blob`, FastAPI multipart upload, pytest static checks.

---

### Task 1: Add Static Coverage For Resize Behavior

**Files:**
- Modify: `tests/test_frontend_static.py`

- [ ] **Step 1: Add a failing static test**

Add a test that extracts `app.js` and asserts the image upload path includes:

```python
def test_frontend_resizes_large_ocr_images_before_upload():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    extractor = js.split("async function extractImageText()", 1)[1].split("async function openOcrDraft", 1)[0]

    assert "prepareOcrImagesForUpload" in extractor
    assert "const OCR_IMAGE_MAX_EDGE = 2048" in js
    assert "const OCR_IMAGE_JPEG_QUALITY = 0.85" in js
    assert "canvas.toBlob" in js
    assert "image/jpeg" in js
    assert "Preparing" in js
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_resizes_large_ocr_images_before_upload -q
```

Expected: fail because `prepareOcrImagesForUpload` and resize constants do not exist.

### Task 2: Implement Image Resize Preprocessing

**Files:**
- Modify: `src/tts_app/static/app.js`

- [ ] **Step 1: Add resize constants near the top of `app.js`**

```javascript
const OCR_IMAGE_MAX_EDGE = 2048;
const OCR_IMAGE_JPEG_QUALITY = 0.85;
```

- [ ] **Step 2: Add helper functions before `extractImageText()`**

Add:

```javascript
function resizedImageFilename(file) {
  const stem = (file.name || "image").replace(/\.[^.]*$/, "") || "image";
  return `${stem}.jpg`;
}

function loadImageElement(file) {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("Unable to read image"));
    };
    image.src = objectUrl;
  });
}

function scaledImageSize(width, height) {
  const longestEdge = Math.max(width, height);
  if (longestEdge <= OCR_IMAGE_MAX_EDGE) {
    return { width, height, resized: false };
  }
  const scale = OCR_IMAGE_MAX_EDGE / longestEdge;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
    resized: true,
  };
}

function canvasToJpegBlob(canvas) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("Unable to resize image"));
        }
      },
      "image/jpeg",
      OCR_IMAGE_JPEG_QUALITY,
    );
  });
}

async function resizeOcrImageIfNeeded(file) {
  const image = await loadImageElement(file);
  const size = scaledImageSize(image.naturalWidth || image.width, image.naturalHeight || image.height);
  if (!size.resized) {
    return { file, resized: false };
  }

  const canvas = document.createElement("canvas");
  canvas.width = size.width;
  canvas.height = size.height;
  const context = canvas.getContext("2d");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, size.width, size.height);
  context.drawImage(image, 0, 0, size.width, size.height);
  const blob = await canvasToJpegBlob(canvas);
  const resizedFile = new File([blob], resizedImageFilename(file), { type: "image/jpeg" });
  return { file: resizedFile, resized: true };
}

async function prepareOcrImagesForUpload(images) {
  const prepared = [];
  let resizedCount = 0;
  playerStatus.textContent = `Preparing ${images.length} ${images.length === 1 ? "image" : "images"}...`;
  for (const image of images) {
    const result = await resizeOcrImageIfNeeded(image);
    prepared.push(result.file);
    if (result.resized) {
      resizedCount += 1;
    }
  }
  if (resizedCount > 0) {
    playerStatus.textContent = `Resized ${resizedCount} of ${images.length} ${images.length === 1 ? "image" : "images"}`;
  }
  return prepared;
}
```

- [ ] **Step 3: Use prepared images in `extractImageText()`**

Change the beginning of `extractImageText()` to:

```javascript
async function extractImageText() {
  const images = Array.from(imageInput.files || []);
  if (images.length === 0) {
    return;
  }
  stopPlayback();
  let uploadImages;
  try {
    uploadImages = await prepareOcrImagesForUpload(images);
  } catch {
    playerStatus.textContent = "Unable to prepare image for upload";
    return;
  }
  const formData = new FormData();
  uploadImages.forEach((image) => {
    formData.append("image", image);
  });
```

- [ ] **Step 4: Run the focused test**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_resizes_large_ocr_images_before_upload -q
```

Expected: pass.

### Task 3: Verify The Existing Upload Contract

**Files:**
- Test: `tests/test_api.py`
- Test: `tests/test_frontend_static.py`

- [ ] **Step 1: Run OCR upload API tests**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_create_ocr_draft_stores_images_and_returns_ordered_text tests/test_api.py::test_create_ocr_draft_still_accepts_single_image -q
```

Expected: pass, because the server still accepts normal multipart `image` fields.

- [ ] **Step 2: Run all frontend static tests**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py -q
```

Expected: pass.

- [ ] **Step 3: Run full verification**

Run:

```bash
.venv/bin/pytest -q
node --check src/tts_app/static/app.js
```

Expected: all tests pass and JS syntax check has no output.

- [ ] **Step 4: Commit the resizing work**

Run:

```bash
git add docs/superpowers/plans/2026-05-10-client-side-image-resizing.md tests/test_frontend_static.py src/tts_app/static/app.js
git commit -m "feat: resize OCR images before upload"
```
