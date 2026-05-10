# Responsive Image Upload UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OCR image upload visibly responsive by showing client upload progress and a clear server OCR wait state.

**Architecture:** Keep the existing synchronous `POST /api/ocr-drafts` backend contract. Replace the OCR upload request with an `XMLHttpRequest` wrapper so the browser can report multipart upload progress, then show an indeterminate OCR state while waiting for the response body.

**Tech Stack:** Plain HTML/CSS/JavaScript, browser `XMLHttpRequest`, existing FastAPI multipart endpoint, pytest static checks.

---

### Task 1: Add Upload Progress Markup And Styles

**Files:**
- Modify: `src/tts_app/static/index.html`
- Modify: `src/tts_app/static/styles.css`
- Modify: `tests/test_frontend_static.py`

- [ ] **Step 1: Add failing static tests**

Add assertions that the HTML contains `id="ocr-upload-progress"`, `id="ocr-upload-bar"`, and `id="cancel-ocr-upload"`, and that CSS contains `.upload-progress`.

- [ ] **Step 2: Run the focused test**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_has_image_input_controls -q
```

Expected: fail until markup and styles are added.

- [ ] **Step 3: Add the progress panel**

Place this after `#image-actions`:

```html
<div id="ocr-upload-progress" class="upload-progress hidden" aria-live="polite">
  <div id="ocr-upload-status" class="upload-status">Preparing images...</div>
  <progress id="ocr-upload-bar" value="0" max="100"></progress>
  <button id="cancel-ocr-upload" class="secondary-action compact-action" type="button">Cancel</button>
</div>
```

- [ ] **Step 4: Add compact mobile styles**

Add CSS for `.upload-progress`, `.upload-status`, and `.upload-progress progress` so it fits inside the existing form panel and keeps the progress bar full width.

### Task 2: Add XHR Upload Progress State

**Files:**
- Modify: `src/tts_app/static/app.js`
- Modify: `tests/test_frontend_static.py`

- [ ] **Step 1: Add failing static tests**

Add tests confirming `extractImageText()` uses an upload helper with `XMLHttpRequest`, `xhr.upload.onprogress`, `xhr.abort()`, and an extracting status after upload reaches 100%.

- [ ] **Step 2: Run the focused static test**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_javascript_uses_ocr_draft_endpoints -q
```

Expected: fail until upload progress code exists.

- [ ] **Step 3: Add state and DOM handles**

Add `ocrUploadXhr` and `ocrUploadActive` to `state`, and query `#ocr-upload-progress`, `#ocr-upload-status`, `#ocr-upload-bar`, and `#cancel-ocr-upload`.

- [ ] **Step 4: Add progress helpers**

Add helpers to show/hide upload progress, set determinate progress percentage, switch to indeterminate OCR/extracting state, disable image controls while active, and clear state after success/error/cancel.

- [ ] **Step 5: Replace OCR upload `fetch()` with XHR helper**

Submit the same `FormData` to `/api/ocr-drafts`. Resolve with parsed JSON for 2xx responses. Reject with parsed `detail` for non-2xx responses. On upload completion, set the UI message to `Extracting text...`.

- [ ] **Step 6: Wire cancel**

The Cancel button aborts the active XHR, marks status as cancelled, and re-enables controls.

### Task 3: Verify Upload UI Behavior

**Files:**
- Test: `tests/test_frontend_static.py`
- Test: `src/tts_app/static/app.js`

- [ ] **Step 1: Run frontend static tests**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py -q
```

Expected: pass.

- [ ] **Step 2: Run full verification**

Run:

```bash
.venv/bin/pytest -q
node --check src/tts_app/static/app.js
```

Expected: all tests pass and JS syntax check has no output.

- [ ] **Step 3: Commit the upload UI work**

Run:

```bash
git add docs/superpowers/plans/2026-05-10-responsive-image-upload-ui.md tests/test_frontend_static.py src/tts_app/static/index.html src/tts_app/static/styles.css src/tts_app/static/app.js
git commit -m "feat: show OCR upload progress"
```
