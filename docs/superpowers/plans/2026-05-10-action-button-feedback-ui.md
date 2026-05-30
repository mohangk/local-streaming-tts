# Action Button Feedback UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tap/click actions feel responsive by giving action buttons clear pressed, loading, disabled, success, and failure feedback during background work, including the `Extract text` OCR action.

**Architecture:** Keep the existing FastAPI API and lightweight frontend. Add small reusable JavaScript helpers that wrap async button actions, toggle a visual busy state on the clicked button, and update the shared status text without changing the backend contract.

**Tech Stack:** Plain HTML/CSS/JavaScript, existing history/OCR draft action handlers, pytest static checks.

---

### Task 1: Add Button Feedback Styling

**Files:**
- Modify: `src/tts_app/static/styles.css`
- Modify: `tests/test_frontend_static.py`

- [ ] **Step 1: Add failing static coverage**

Add a frontend static test:

```python
def test_frontend_styles_action_button_feedback_states():
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert "button:active" in css
    assert ".is-busy" in css
    assert ".is-busy::after" in css
    assert "aria-busy" in css
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_styles_action_button_feedback_states -q
```

Expected: fail because the feedback styles do not exist.

- [ ] **Step 3: Add styles**

Add CSS that:

```css
button { transition: transform 120ms ease, opacity 120ms ease, background-color 120ms ease, border-color 120ms ease; }
button:active { transform: translateY(1px) scale(0.99); }
button:disabled { cursor: wait; opacity: 0.68; }
button.is-busy, button[aria-busy="true"] { position: relative; padding-right: 2.25rem; }
button.is-busy::after, button[aria-busy="true"]::after {
  content: "";
  position: absolute;
  right: 0.75rem;
  top: 50%;
  width: 0.85rem;
  height: 0.85rem;
  margin-top: -0.425rem;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 700ms linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
```

- [ ] **Step 4: Verify focused test passes**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_styles_action_button_feedback_states -q
```

Expected: pass.

### Task 2: Add Reusable Async Button Helpers

**Files:**
- Modify: `src/tts_app/static/app.js`
- Modify: `tests/test_frontend_static.py`

- [ ] **Step 1: Add failing static coverage**

Add a frontend static test:

```python
def test_frontend_wraps_async_button_actions_with_busy_state():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "async function withButtonBusy" in js
    assert "button.classList.add(\"is-busy\")" in js
    assert "button.setAttribute(\"aria-busy\", \"true\")" in js
    assert "button.disabled = true" in js
    assert "button.classList.remove(\"is-busy\")" in js
    assert "button.removeAttribute(\"aria-busy\")" in js
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_wraps_async_button_actions_with_busy_state -q
```

Expected: fail because the helper does not exist.

- [ ] **Step 3: Add helper functions near generic UI helpers**

Add:

```javascript
function setButtonBusy(button, busy, label) {
  if (!button) {
    return;
  }
  if (busy) {
    button.dataset.originalLabel = button.textContent;
    if (label) {
      button.textContent = label;
    }
    button.classList.add("is-busy");
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
    return;
  }
  if (button.dataset.originalLabel) {
    button.textContent = button.dataset.originalLabel;
    delete button.dataset.originalLabel;
  }
  button.classList.remove("is-busy");
  button.removeAttribute("aria-busy");
  button.disabled = false;
}

async function withButtonBusy(button, label, operation) {
  setButtonBusy(button, true, label);
  try {
    return await operation();
  } finally {
    setButtonBusy(button, false);
  }
}
```

- [ ] **Step 4: Verify focused test passes**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_wraps_async_button_actions_with_busy_state -q
```

Expected: pass.

### Task 3: Apply Feedback To History And OCR Actions

**Files:**
- Modify: `src/tts_app/static/app.js`
- Modify: `tests/test_frontend_static.py`

- [ ] **Step 1: Add failing static coverage**

Add a frontend static test that checks click handlers pass clicked buttons into async actions:

```python
def test_frontend_history_and_ocr_actions_pass_buttons_for_feedback():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "extractImageTextButton.addEventListener(\"click\", () => extractImageText(extractImageTextButton))" in js
    assert "async function extractImageText(button = null)" in js
    assert "withButtonBusy(button, \"Extracting...\"" in js
    assert "openGeneration(Number(action.dataset.generationId)" in js
    assert "button: action" in js
    assert "deleteGeneration(Number(action.dataset.generationId), action)" in js
    assert "openOcrDraft(Number(action.dataset.draftId), action)" in js
    assert "deleteOcrDraft(Number(action.dataset.draftId), action)" in js
    assert "deleteOcrDraftImage(state.currentOcrDraftId, Number(action.dataset.imageId), action)" in js
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_history_and_ocr_actions_pass_buttons_for_feedback -q
```

Expected: fail until handlers pass clicked buttons through.

- [ ] **Step 3: Update action functions**

Update these functions to accept an optional button and wrap their visible work. For `extractImageText`, keep the empty-file early return before the busy wrapper, then move the current preprocessing, `FormData`, upload, response handling, and error handling into the wrapped operation:

```javascript
async function extractImageText(button = null) {
  const images = Array.from(imageInput.files || []);
  if (images.length === 0) {
    return;
  }
  await withButtonBusy(button, "Extracting...", async () => {
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
    formData.append("language", currentLanguage());
    playerStatus.textContent = "Extracting image text";
    try {
      const response = await fetch("/api/ocr-drafts", {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const error = await response.json();
        playerStatus.textContent = error.detail || "Image text extraction failed";
        await loadOcrDrafts();
        return;
      }
      const draft = await response.json();
      showOcrDraft(draft);
      await loadOcrDrafts();
    } catch {
      playerStatus.textContent = "Image text extraction failed";
    }
  });
}
```

For the other actions, keep the confirmation prompt before setting the button busy and wrap the network work after confirmation:

```javascript
async function deleteGeneration(generationId, button = null) {
  if (!window.confirm("Delete this history entry and cached audio?")) {
    return;
  }
  await withButtonBusy(button, "Deleting...", async () => {
    const response = await fetch(`/api/generations/${generationId}`, { method: "DELETE" });
    if (!response.ok) {
      playerStatus.textContent = "Unable to delete history entry";
      return;
    }
    if (state.currentGenerationId === generationId) {
      resetPlaybackState("Deleted generation");
    }
    await loadHistory();
  });
}

async function openOcrDraft(draftId, button = null) {
  await withButtonBusy(button, "Opening...", async () => {
    stopPlayback();
    try {
      const response = await fetch(`/api/ocr-drafts/${draftId}`);
      if (!response.ok) {
        playerStatus.textContent = "Unable to load image draft";
        return;
      }
      showOcrDraft(await response.json());
    } catch {
      playerStatus.textContent = "Unable to load image draft";
    }
  });
}

async function deleteOcrDraft(draftId, button = null) {
  if (!window.confirm("Delete this image draft?")) {
    return;
  }
  await withButtonBusy(button, "Deleting...", async () => {
    const response = await fetch(`/api/ocr-drafts/${draftId}`, { method: "DELETE" });
    if (!response.ok) {
      playerStatus.textContent = "Unable to delete image draft";
      return;
    }
    if (state.currentOcrDraftId === draftId) {
      state.currentOcrDraftId = null;
      state.currentOcrDraft = null;
      ocrReviewList.innerHTML = "";
      ocrReviewList.classList.add("hidden");
      generateOcrAudioButton.classList.add("hidden");
    }
    await loadOcrDrafts();
    playerStatus.textContent = "Deleted image draft";
  });
}

async function deleteOcrDraftImage(draftId, imageId, button = null) {
  if (!window.confirm("Remove this image from the draft?")) {
    return;
  }
  await withButtonBusy(button, "Removing...", async () => {
    const response = await fetch(`/api/ocr-drafts/${draftId}/images/${imageId}`, { method: "DELETE" });
    if (!response.ok) {
      playerStatus.textContent = "Unable to remove image";
      return;
    }
    await openOcrDraft(draftId);
    await loadOcrDrafts();
    playerStatus.textContent = "Removed image";
  });
}
```

- [ ] **Step 4: Update delegated click handlers**

Pass the clicked `action` button into:

```javascript
extractImageTextButton.addEventListener("click", () => extractImageText(extractImageTextButton));
openGeneration(Number(action.dataset.generationId), { subscribe: true, autoplay: true, button: action });
deleteGeneration(Number(action.dataset.generationId), action);
openOcrDraft(Number(action.dataset.draftId), action);
deleteOcrDraft(Number(action.dataset.draftId), action);
deleteOcrDraftImage(state.currentOcrDraftId, Number(action.dataset.imageId), action);
```

- [ ] **Step 5: Extend `openGeneration` for optional button feedback**

Accept `button` in the options object and wrap the load path in `withButtonBusy(button, "Opening...", async () => { ... })`. Keep existing playback behavior unchanged.

- [ ] **Step 6: Verify focused test passes**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_history_and_ocr_actions_pass_buttons_for_feedback -q
```

Expected: pass.

### Task 4: Final Verification

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

- [ ] **Step 3: Commit the action feedback UI work**

Run:

```bash
git add docs/superpowers/plans/2026-05-10-action-button-feedback-ui.md tests/test_frontend_static.py src/tts_app/static/app.js src/tts_app/static/styles.css
git commit -m "feat: show action button feedback"
```
