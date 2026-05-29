# OCR Retry And Diagnostics Implementation Plan

> Historical implementation plan. For the current OCR behavior and data model, read `docs/superpowers/specs/2026-05-03-image-ocr-generation-design.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users retry failed OCR image extraction without reuploading images, and make OCR provider failures diagnosable from application logs.

**Architecture:** The backend adds a per-image OCR retry endpoint that reuses the stored image file, updates the image row's raw `extracted_text`, rebuilds draft `combined_text`, and refreshes the parent draft status through existing storage APIs. The frontend shows `Retry OCR` only for failed, unlinked active-draft images and reuses the existing busy-button feedback pattern. Qwen OCR request failures include the HTTP exception class so empty `httpx` exception messages no longer produce blank errors.

**Tech Stack:** FastAPI, SQLite-backed storage, Qwen OCR provider wrapper, lightweight vanilla JavaScript, pytest API/provider/static frontend tests.

---

## File Structure

- Modify `src/tts_app/api.py`: add per-image retry endpoint and richer OCR failure logging.
- Modify `src/tts_app/ocr_providers/qwen.py`: include HTTP exception type in provider errors.
- Modify `src/tts_app/static/app.js`: render `Retry OCR` for failed active-draft images and call the retry endpoint.
- Modify `src/tts_app/static/styles.css`: add compact layout for OCR image actions.
- Modify `tests/test_api.py`: cover successful retry, linked-draft rejection, and missing image handling.
- Modify `tests/test_ocr_provider.py`: cover empty-message `httpx` failures.
- Modify `tests/test_frontend_static.py`: cover retry button rendering and UI wiring.

## Behavior Contract

Failed OCR image cards show a `Retry OCR` button when:

```text
image.status == "failed"
draft.linked_generation_id is empty
```

The retry call is:

```http
POST /api/ocr-drafts/{draft_id}/images/{image_id}/retry
```

Expected responses:

```text
200 with the updated OCR draft when retry completes or fails again
404 when the draft, image row, or stored image file is missing
409 when the OCR draft is already linked to a generated audio entry
```

Retry must not require a new upload. It reads the saved file from the configured image storage path.

Retry updates per-image OCR diagnostics first, then rebuilds the draft-level `combined_text` from all image-level `extracted_text` values in image order. This can overwrite user edits in the combined review textarea after retry; that tradeoff is intentional for the simplified review model.

---

### Task 1: Qwen OCR Failure Diagnostics

**Files:**
- Modify: `src/tts_app/ocr_providers/qwen.py`
- Test: `tests/test_ocr_provider.py`

- [ ] **Step 1: Write the failing provider test**

Add a fake `httpx.AsyncClient` that raises `httpx.ReadTimeout("")` and assert the provider error includes the exception class:

```python
class FailingAsyncClient:
    def __init__(self, *args, **kwargs):
        self.init_args = args
        self.init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, *, headers, json):
        raise qwen.httpx.ReadTimeout("")


@pytest.mark.asyncio
async def test_qwen_ocr_provider_includes_http_exception_type_when_message_is_empty(monkeypatch):
    monkeypatch.setattr(qwen.httpx, "AsyncClient", FailingAsyncClient)
    provider = QwenOCRProvider(api_key="secret-key", model="qwen-vl-ocr")

    with pytest.raises(OCRProviderError, match="qwen ocr provider request failed: ReadTimeout"):
        await provider.extract_text(b"image", "image/png", OCROptions(language="en"))
```

- [ ] **Step 2: Run the failing provider test**

Run:

```bash
.venv/bin/pytest tests/test_ocr_provider.py::test_qwen_ocr_provider_includes_http_exception_type_when_message_is_empty -q
```

Expected result:

```text
FAILED ... Actual message: 'qwen ocr provider request failed: '
```

- [ ] **Step 3: Add HTTP error formatting**

In `src/tts_app/ocr_providers/qwen.py`, replace the existing `httpx.HTTPError` mapping with:

```python
        except httpx.HTTPError as exc:
            raise OCRProviderError(f"qwen ocr provider request failed: {_http_error_message(exc)}") from exc
```

Add this helper near `_response_error_message(...)`:

```python
def _http_error_message(exc: httpx.HTTPError) -> str:
    detail = str(exc).strip()
    if detail:
        return f"{type(exc).__name__}: {detail}"
    return type(exc).__name__
```

- [ ] **Step 4: Run the provider test again**

Run:

```bash
.venv/bin/pytest tests/test_ocr_provider.py::test_qwen_ocr_provider_includes_http_exception_type_when_message_is_empty -q
```

Expected result:

```text
1 passed
```

---

### Task 2: Retry API Endpoint

**Files:**
- Modify: `src/tts_app/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing retry API tests**

Add a provider that fails once and succeeds on retry:

```python
class FailsOnceOCRProvider:
    name = "fails-once-ocr"

    def __init__(self):
        self.calls: list[tuple[bytes, str, OCROptions]] = []

    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
        self.calls.append((image, mime_type, options))
        if len(self.calls) == 1:
            raise OCRProviderError("temporary ocr outage")
        return "Recovered OCR text"
```

Add the successful retry test:

```python
def test_retry_failed_ocr_image_uses_stored_file_and_updates_draft(test_settings, monkeypatch):
    provider = FailsOnceOCRProvider()
    monkeypatch.setattr("tts_app.api.get_ocr_provider", lambda settings: provider)
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        data={"language": "zh"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    image = draft["images"][0]

    response = client.post(f"/api/ocr-drafts/{draft['id']}/images/{image['id']}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["error"] is None
    assert body["combined_text"] == "Recovered OCR text"
    assert body["images"][0]["status"] == "completed"
    assert body["images"][0]["error"] is None
    assert body["images"][0]["extracted_text"] == "Recovered OCR text"
    assert [call[0] for call in provider.calls] == [b"fake-image", b"fake-image"]
    assert provider.calls[1][1] == "image/png"
    assert provider.calls[1][2].language == "zh"
    assert provider.calls[1][2].model == test_settings.ocr_model
```

Add linked and missing-image tests:

```python
def test_retry_ocr_image_on_linked_draft_is_rejected(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    response = client.post(f"/api/ocr-drafts/{draft['id']}/images/{draft['images'][0]['id']}/retry")

    assert response.status_code == 409


def test_retry_missing_ocr_image_is_not_found(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post("/api/ocr-drafts/999/images/888/retry")

    assert response.status_code == 404
```

- [ ] **Step 2: Run the failing API tests**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_retry_failed_ocr_image_uses_stored_file_and_updates_draft tests/test_api.py::test_retry_ocr_image_on_linked_draft_is_rejected tests/test_api.py::test_retry_missing_ocr_image_is_not_found -q
```

Expected result:

```text
FAILED ... assert 404 == 200
FAILED ... assert 404 == 409
1 passed
```

- [ ] **Step 3: Add traceback logging to initial OCR failures**

In `src/tts_app/api.py`, update the existing OCR provider failure logging in `create_ocr_draft(...)`:

```python
                logger.warning("ocr_draft_image_failed draft_id=%s image_id=%s error=%s", draft_id, image_id, exc, exc_info=True)
```

- [ ] **Step 4: Add the retry endpoint**

Add this route after `get_ocr_draft_image(...)` and before `update_ocr_draft(...)`:

```python
    @app.post("/api/ocr-drafts/{draft_id}/images/{image_id}/retry")
    async def retry_ocr_draft_image(draft_id: int, image_id: int):
        try:
            draft = storage.get_ocr_draft(draft_id)
            image = storage.get_ocr_draft_image(draft_id, image_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft image not found") from exc

        if draft["linked_generation_id"] is not None:
            raise HTTPException(status_code=409, detail="ocr draft is linked to generation")

        image_path = _stored_ocr_image_path(active_settings, image)
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="ocr draft image file not found")

        relative_image_path = str(image["image_path"])
        storage.update_ocr_draft_image_ocr_result(
            draft_id,
            image_id,
            image_path=relative_image_path,
            extracted_text="",
            status="running",
            error=None,
        )
        try:
            extracted_text = await ocr_provider.extract_text(
                image_path.read_bytes(),
                str(image["mime_type"]),
                OCROptions(language=str(draft["language"]), model=active_settings.ocr_model),
            )
        except OCRProviderError as exc:
            storage.update_ocr_draft_image_ocr_result(
                draft_id,
                image_id,
                image_path=relative_image_path,
                extracted_text="",
                status="failed",
                error=str(exc),
            )
            logger.warning("ocr_draft_image_failed draft_id=%s image_id=%s error=%s", draft_id, image_id, exc, exc_info=True)
            return storage.get_ocr_draft(draft_id)

        if not extracted_text.strip():
            error = "OCR returned no visible text"
            storage.update_ocr_draft_image_ocr_result(
                draft_id,
                image_id,
                image_path=relative_image_path,
                extracted_text="",
                status="failed",
                error=error,
            )
            logger.warning("ocr_draft_image_failed draft_id=%s image_id=%s error=%s", draft_id, image_id, error)
            return storage.get_ocr_draft(draft_id)

        storage.update_ocr_draft_image_ocr_result(
            draft_id,
            image_id,
            image_path=relative_image_path,
            extracted_text=extracted_text,
            status="completed",
            error=None,
        )
        logger.info("ocr_draft_image_retried draft_id=%s image_id=%s text_chars=%s", draft_id, image_id, len(extracted_text))
        return storage.get_ocr_draft(draft_id)
```

- [ ] **Step 5: Run the API tests again**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_retry_failed_ocr_image_uses_stored_file_and_updates_draft tests/test_api.py::test_retry_ocr_image_on_linked_draft_is_rejected tests/test_api.py::test_retry_missing_ocr_image_is_not_found -q
```

Expected result:

```text
3 passed
```

---

### Task 3: Retry UI

**Files:**
- Modify: `src/tts_app/static/app.js`
- Modify: `src/tts_app/static/styles.css`
- Test: `tests/test_frontend_static.py`

- [ ] **Step 1: Write the failing frontend static tests**

Update `test_frontend_renders_thumbnails_and_per_image_review_controls()` with:

```python
    assert "data-action=\"retry-image\"" in renderer
    assert "Retry OCR" in renderer
```

Update `test_frontend_history_and_ocr_actions_pass_buttons_for_feedback()` with:

```python
    assert "retryOcrDraftImage(state.currentOcrDraftId, Number(action.dataset.imageId), action)" in js
    assert "withButtonBusy(button, \"Retrying...\"" in js
    assert "/retry" in js
```

- [ ] **Step 2: Run the failing frontend tests**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_renders_one_combined_ocr_textarea_and_active_thumbnails tests/test_frontend_static.py::test_frontend_history_and_ocr_actions_pass_buttons_for_feedback -q
```

Expected result:

```text
FAILED ... assert 'data-action="retry-image"' in renderer
FAILED ... assert 'retryOcrDraftImage...' in js
```

- [ ] **Step 3: Render retry action for failed unlinked images**

In `renderOcrReview()` in `src/tts_app/static/app.js`, add:

```javascript
      const retryButton =
        image.status === "failed" && !draft.linked_generation_id
          ? `<button class="secondary-action compact-action" type="button" data-action="retry-image" data-image-id="${image.id}">Retry OCR</button>`
          : "";
```

Render retry alongside the optional `Remove` action in the active draft thumbnail card:

```javascript
      const removeButton = !draft.linked_generation_id
        ? `<button class="danger-action compact-action" type="button" data-action="delete-image" data-image-id="${image.id}">Remove</button>`
        : "";
```

Use both buttons in the thumbnail card actions:

```javascript
            <div class="ocr-image-actions">
              ${retryButton}
              ${removeButton}
            </div>
```

- [ ] **Step 4: Add retry function**

In `src/tts_app/static/app.js`, add this function near `deleteOcrDraftImage(...)`:

```javascript
async function retryOcrDraftImage(draftId, imageId, button = null) {
  await withButtonBusy(button, "Retrying...", async () => {
    try {
      const response = await fetch(`/api/ocr-drafts/${draftId}/images/${imageId}/retry`, { method: "POST" });
      if (!response.ok) {
        const error = await response.json();
        playerStatus.textContent = error.detail || "Unable to retry OCR";
        return;
      }
      showOcrDraft(await response.json());
      await loadOcrDrafts();
      playerStatus.textContent = "Retried OCR";
    } catch {
      playerStatus.textContent = "Unable to retry OCR";
    }
  });
}
```

- [ ] **Step 5: Wire retry click handling**

In the `ocrReviewList.addEventListener("click", ...)` handler, replace the delete-only guard with:

```javascript
  if (!action || !state.currentOcrDraftId) {
    return;
  }
  if (action.dataset.action === "delete-image") {
    deleteOcrDraftImage(state.currentOcrDraftId, Number(action.dataset.imageId), action);
    return;
  }
  if (action.dataset.action === "retry-image") {
    retryOcrDraftImage(state.currentOcrDraftId, Number(action.dataset.imageId), action);
  }
```

- [ ] **Step 6: Add compact action layout**

In `src/tts_app/static/styles.css`, add:

```css
.ocr-image-actions { display: grid; gap: 8px; }
```

- [ ] **Step 7: Run the frontend tests again**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_renders_one_combined_ocr_textarea_and_active_thumbnails tests/test_frontend_static.py::test_frontend_history_and_ocr_actions_pass_buttons_for_feedback -q
```

Expected result:

```text
2 passed
```

---

### Task 4: Verification And Commit

**Files:**
- Verify: all modified OCR retry files and this plan.

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_ocr_provider.py tests/test_api.py tests/test_frontend_static.py -q
```

Expected result:

```text
95 passed
```

- [ ] **Step 2: Run JavaScript syntax check**

Run:

```bash
node --check src/tts_app/static/app.js
```

Expected result: no output and exit code `0`.

- [ ] **Step 3: Run full project tests**

Run:

```bash
.venv/bin/pytest -q
```

Expected result:

```text
174 passed
```

- [ ] **Step 4: Check diff hygiene**

Run:

```bash
git diff --check
```

Expected result: no output and exit code `0`.

- [ ] **Step 5: Commit OCR retry/diagnostics separately**

Stage only OCR retry/diagnostics files and the OCR plan:

```bash
git add src/tts_app/api.py src/tts_app/ocr_providers/qwen.py src/tts_app/static/app.js src/tts_app/static/styles.css tests/test_api.py tests/test_ocr_provider.py tests/test_frontend_static.py docs/superpowers/plans/archive/2026-05-28-ocr-retry-diagnostics.md
git commit -m "feat: retry failed OCR images"
```

Expected result: one commit containing the retry endpoint, UI, diagnostics, tests, and this plan.

---

## Self-Review

- Spec coverage: The plan covers the current OCR retry/diagnostics work only.
- Placeholder scan: No placeholders remain.
- Type consistency: Endpoint path, helper names, event names, and test names are consistent across tasks.
