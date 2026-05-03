# Image OCR And Voice Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add language-aware voice selection, voice sampling, preferred voices, and image OCR drafts that can be reviewed before creating normal streamed TTS generations.

**Architecture:** Keep TTS, OCR, storage, and frontend state separated behind focused interfaces. SQLite persists voice preferences, OCR drafts, linked image generations, and source image metadata; files store images under `data/images/` and audio under the existing `data/audio/`. FastAPI exposes small JSON/multipart endpoints used by the vanilla mobile-first frontend.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, pytest, vanilla JavaScript, Qwen realtime TTS, Qwen `qwen-vl-ocr`, existing fake providers for no-credit tests.

---

## File Structure

- Modify `src/tts_app/models.py`: add `image` source type and `Language` literal.
- Modify `src/tts_app/config.py`: add OCR/image settings and language defaults.
- Modify `src/tts_app/storage.py`: add OCR drafts and voice preference schema/methods.
- Modify `src/tts_app/providers/options.py`: add language and preferred metadata to voice options.
- Modify `src/tts_app/providers/fake.py`: expose language-tagged test voice options.
- Modify `src/tts_app/providers/qwen.py`: expose English/Chinese voice metadata.
- Create `src/tts_app/ocr_providers/base.py`: OCR provider protocol and errors.
- Create `src/tts_app/ocr_providers/fake.py`: deterministic OCR provider for tests.
- Create `src/tts_app/ocr_providers/qwen.py`: Qwen OCR adapter.
- Create `src/tts_app/ocr_providers/registry.py`: OCR provider selection from settings.
- Modify `src/tts_app/api.py`: add options, preference, voice sample, OCR draft, image generation, and deletion routes.
- Modify `src/tts_app/static/index.html`: add language, star, sample, and image OCR review controls.
- Modify `src/tts_app/static/app.js`: implement language filtering, sampling, preference toggles, OCR draft lifecycle, and image generation.
- Modify `src/tts_app/static/styles.css`: add compact controls for language/voice/sample/image draft UI.
- Modify `README.md` and `AGENTS.md`: document OCR settings, image storage, and test commands.
- Modify `tests/test_storage.py`: storage coverage for OCR drafts and voice preferences.
- Modify `tests/test_api.py`: API coverage for options, samples, OCR drafts, image generation, and deletion.
- Create `tests/test_ocr_provider.py`: fake and Qwen OCR provider tests.
- Modify `tests/test_frontend_static.py`: static checks for the new Generate-page controls and JS endpoints.

## Task 1: Storage And Settings Foundation

**Files:**
- Modify: `src/tts_app/models.py`
- Modify: `src/tts_app/config.py`
- Modify: `src/tts_app/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Add tests to `tests/test_storage.py`:

```python
def test_ocr_draft_round_trip(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    draft_id = storage.create_ocr_draft(
        image_path="images/1/source.jpg",
        original_filename="page.jpg",
        mime_type="image/jpeg",
        byte_size=123,
        ocr_model="qwen-vl-ocr",
        language="zh",
        extracted_text="你好\nni hao",
        status="completed",
    )

    draft = storage.get_ocr_draft(draft_id)
    assert draft["id"] == draft_id
    assert draft["image_path"] == "images/1/source.jpg"
    assert draft["language"] == "zh"
    assert draft["extracted_text"] == "你好\nni hao"
    assert storage.list_ocr_drafts()[0]["id"] == draft_id


def test_update_ocr_draft_text_and_language(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    draft_id = storage.create_ocr_draft("images/1/source.png", None, "image/png", 10, "fake-ocr", "en", "raw", "completed")

    storage.update_ocr_draft(draft_id, extracted_text="reviewed text", language="zh")

    draft = storage.get_ocr_draft(draft_id)
    assert draft["extracted_text"] == "reviewed text"
    assert draft["language"] == "zh"


def test_delete_unlinked_ocr_draft(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    draft_id = storage.create_ocr_draft("images/1/source.png", None, "image/png", 10, "fake-ocr", "en", "text", "completed")

    storage.delete_ocr_draft(draft_id)

    with pytest.raises(KeyError, match=f"ocr draft {draft_id} not found"):
        storage.get_ocr_draft(draft_id)


def test_delete_linked_ocr_draft_is_blocked(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    draft_id = storage.create_ocr_draft("images/1/source.png", None, "image/png", 10, "fake-ocr", "en", "text", "completed")
    generation_id = storage.create_generation("image", "Image text", None, "text", "fake", "Test", {"ocr_draft_id": draft_id})
    storage.link_ocr_draft_generation(draft_id, generation_id)

    with pytest.raises(ValueError, match="linked to generation"):
        storage.delete_ocr_draft(draft_id)


def test_voice_preference_round_trip(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    storage.set_voice_preference("Cherry", True)
    assert storage.list_voice_preferences() == {"Cherry": True}

    storage.set_voice_preference("Cherry", False)
    assert storage.list_voice_preferences() == {"Cherry": False}
```

- [ ] **Step 2: Run storage tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_storage.py::test_ocr_draft_round_trip tests/test_storage.py::test_update_ocr_draft_text_and_language tests/test_storage.py::test_delete_unlinked_ocr_draft tests/test_storage.py::test_delete_linked_ocr_draft_is_blocked tests/test_storage.py::test_voice_preference_round_trip -q
```

Expected: fail because OCR draft and voice preference storage methods do not exist.

- [ ] **Step 3: Add image source type and settings**

Update `src/tts_app/models.py`:

```python
SourceType = Literal["text", "url", "image"]
Language = Literal["en", "zh"]
```

Update `src/tts_app/config.py` by extending `Settings`:

```python
image_dir: Path
ocr_provider_name: str
qwen_ocr_model: str
max_image_bytes: int
default_english_voice: str
default_chinese_voice: str
```

Update `load_settings()`:

```python
image_dir=Path(os.environ.get("TTS_IMAGE_DIR", data_dir / "images")).resolve(),
ocr_provider_name=os.environ.get("OCR_PROVIDER", "fake"),
qwen_ocr_model=os.environ.get("QWEN_OCR_MODEL", "qwen-vl-ocr"),
max_image_bytes=int(os.environ.get("TTS_MAX_IMAGE_BYTES", "10485760")),
default_english_voice=os.environ.get("TTS_DEFAULT_ENGLISH_VOICE", os.environ.get("QWEN_VOICE", "Jennifer")),
default_chinese_voice=os.environ.get("TTS_DEFAULT_CHINESE_VOICE", "Cherry"),
```

Update all test `Settings(...)` fixtures in `tests/conftest.py` with matching fields.

- [ ] **Step 4: Add storage schema and methods**

In `Storage.init_schema()`, allow `image` in the `generations.source_type` check for new databases:

```sql
source_type TEXT NOT NULL CHECK (source_type IN ('text', 'url', 'image')),
```

Add schema:

```sql
CREATE TABLE IF NOT EXISTS ocr_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_path TEXT NOT NULL,
    original_filename TEXT,
    mime_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    ocr_model TEXT NOT NULL,
    language TEXT NOT NULL,
    extracted_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    error TEXT,
    linked_generation_id INTEGER REFERENCES generations(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS voice_preferences (
    voice TEXT PRIMARY KEY,
    preferred INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Add methods:

```python
def create_ocr_draft(
    self,
    image_path: str,
    original_filename: str | None,
    mime_type: str,
    byte_size: int,
    ocr_model: str,
    language: str,
    extracted_text: str,
    status: Status,
    error: str | None = None,
) -> int:
    raise NotImplementedError


def get_ocr_draft(self, draft_id: int) -> dict[str, Any]:
    raise NotImplementedError


def list_ocr_drafts(self) -> list[dict[str, Any]]:
    raise NotImplementedError


def update_ocr_draft(self, draft_id: int, *, extracted_text: str, language: str) -> None:
    raise NotImplementedError


def update_ocr_draft_ocr_result(
    self,
    draft_id: int,
    *,
    image_path: str,
    extracted_text: str,
    status: Status,
    error: str | None,
) -> None:
    raise NotImplementedError


def update_ocr_draft_status(self, draft_id: int, status: Status, error: str | None = None) -> None:
    raise NotImplementedError


def link_ocr_draft_generation(self, draft_id: int, generation_id: int) -> None:
    raise NotImplementedError


def delete_ocr_draft(self, draft_id: int) -> dict[str, Any]:
    raise NotImplementedError


def force_delete_ocr_draft(self, draft_id: int) -> dict[str, Any]:
    raise NotImplementedError


def get_ocr_draft_for_generation(self, generation_id: int) -> dict[str, Any] | None:
    raise NotImplementedError


def set_voice_preference(self, voice: str, preferred: bool) -> None:
    raise NotImplementedError


def list_voice_preferences(self) -> dict[str, bool]:
    raise NotImplementedError
```

`delete_ocr_draft()` must load the row first, raise `ValueError("ocr draft is linked to generation")` when `linked_generation_id` is not null, delete the row, and return the deleted row so callers can remove its image directory.

- [ ] **Step 5: Run storage tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_storage.py -q
```

Expected: all storage tests pass.

Commit:

```bash
git add src/tts_app/models.py src/tts_app/config.py src/tts_app/storage.py tests/conftest.py tests/test_storage.py
git commit -m "feat: add ocr draft storage"
```

## Task 2: Language-Aware Voice Options And Preferences

**Files:**
- Modify: `src/tts_app/providers/options.py`
- Modify: `src/tts_app/providers/fake.py`
- Modify: `src/tts_app/providers/qwen.py`
- Modify: `src/tts_app/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Add to `tests/test_api.py`:

```python
def test_options_returns_language_and_preferred_voice_metadata(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    client.put("/api/voices/Cherry/preference", json={"preferred": True})

    response = client.get("/api/options")

    assert response.status_code == 200
    body = response.json()
    assert body["default_language"] == "en"
    assert body["default_voices"]["en"]
    assert body["default_voices"]["zh"]
    cherry = next(voice for voice in body["voices"] if voice["value"] == "Cherry")
    assert cherry["language"] in {"en", "zh"}
    assert cherry["preferred"] is True


def test_voice_preference_endpoint_updates_preference(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.put("/api/voices/Jennifer/preference", json={"preferred": True})

    assert response.status_code == 200
    assert response.json() == {"voice": "Jennifer", "preferred": True}
    options = client.get("/api/options").json()
    assert next(voice for voice in options["voices"] if voice["value"] == "Jennifer")["preferred"] is True
```

- [ ] **Step 2: Run API tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_options_returns_language_and_preferred_voice_metadata tests/test_api.py::test_voice_preference_endpoint_updates_preference -q
```

Expected: fail because voice preference endpoint and language/preferred option fields do not exist.

- [ ] **Step 3: Extend voice option metadata**

Update `src/tts_app/providers/options.py`:

```python
@dataclass(frozen=True)
class SelectOption:
    value: str | float
    label: str
    language: str | None = None
```

Update fake and Qwen voice option lists so each voice has a language. Keep current English voice values stable by assigning `language="en"` to the existing `QWEN_ENGLISH_VOICES` entries. Add a new `QWEN_CHINESE_VOICES` tuple with initial values:

```python
QWEN_CHINESE_VOICES: tuple[SelectOption, ...] = (
    SelectOption("Cherry", "Cherry - Chinese female", language="zh"),
    SelectOption("Serena", "Serena - Chinese female", language="zh"),
    SelectOption("Ethan", "Ethan - Chinese male", language="zh"),
)
```

Use the same tuples for fake provider tests so local behavior matches production option shape.

- [ ] **Step 4: Add preference API**

In `src/tts_app/api.py`, add:

```python
class VoicePreferenceRequest(BaseModel):
    preferred: bool

@app.put("/api/voices/{voice}/preference")
async def update_voice_preference(voice: str, payload: VoicePreferenceRequest):
    storage.set_voice_preference(voice, payload.preferred)
    logger.info("voice_preference_updated voice=%s preferred=%s", voice, payload.preferred)
    return {"voice": voice, "preferred": payload.preferred}
```

Update `/api/options` to:

- read `preferences = storage.list_voice_preferences()`
- include `language` and `preferred`
- sort preferred voices before unpreferred voices within a language
- return `default_language`, `default_voices`, and existing speed data

- [ ] **Step 5: Run API tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_options_returns_language_and_preferred_voice_metadata tests/test_api.py::test_voice_preference_endpoint_updates_preference tests/test_api.py::test_options_returns_voice_and_speed_choices -q
```

Expected: selected API tests pass.

Commit:

```bash
git add src/tts_app/providers/options.py src/tts_app/providers/fake.py src/tts_app/providers/qwen.py src/tts_app/api.py tests/test_api.py
git commit -m "feat: add language-aware voice preferences"
```

## Task 3: Voice Sample Endpoint

**Files:**
- Modify: `src/tts_app/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing voice sample tests**

Add to `tests/test_api.py`:

```python
def test_voice_sample_returns_audio_without_creating_history(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post("/api/voice-sample", json={"voice": "Jennifer", "speed": 1.25, "language": "en"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    assert response.content
    assert client.get("/api/generations").json() == []


def test_voice_sample_uses_chinese_script(test_settings, caplog):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post("/api/voice-sample", json={"voice": "Cherry", "speed": 1.0, "language": "zh"})

    assert response.status_code == 200
    assert response.content
```

- [ ] **Step 2: Run voice sample tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_voice_sample_returns_audio_without_creating_history tests/test_api.py::test_voice_sample_uses_chinese_script -q
```

Expected: fail because `/api/voice-sample` does not exist.

- [ ] **Step 3: Add request model and route**

Add to `src/tts_app/api.py`:

```python
class VoiceSampleRequest(BaseModel):
    voice: str
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = "en"

SAMPLE_TEXT = {
    "en": "This is a short Readvox voice sample. Use it to check the voice, pacing, clarity, and listening comfort before generating the full article.",
    "zh": "这是一个简短的 Readvox 语音示例。请用它来检查声音、语速、清晰度和听感是否适合长时间收听。",
}
```

Add route:

```python
@app.post("/api/voice-sample")
async def voice_sample(payload: VoiceSampleRequest):
    text = SAMPLE_TEXT.get(payload.language, SAMPLE_TEXT["en"])

    async def stream():
        async for chunk in provider.stream_speech(text, TTSOptions(voice=payload.voice, speed=payload.speed)):
            yield chunk.data

    return StreamingResponse(stream(), media_type="audio/mpeg")
```

Import `TTSOptions` from `tts_app.providers.base`. If the provider can return non-MP3 chunks, capture the first chunk media type in a small helper or keep `audio/mpeg` until provider format support is broadened.

- [ ] **Step 4: Run voice sample tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_voice_sample_returns_audio_without_creating_history tests/test_api.py::test_voice_sample_uses_chinese_script -q
```

Expected: voice sample tests pass.

Commit:

```bash
git add src/tts_app/api.py tests/test_api.py
git commit -m "feat: add voice sample endpoint"
```

## Task 4: OCR Provider Interface

**Files:**
- Create: `src/tts_app/ocr_providers/base.py`
- Create: `src/tts_app/ocr_providers/fake.py`
- Create: `src/tts_app/ocr_providers/qwen.py`
- Create: `src/tts_app/ocr_providers/registry.py`
- Test: `tests/test_ocr_provider.py`

- [ ] **Step 1: Write failing OCR provider tests**

Create `tests/test_ocr_provider.py`:

```python
import pytest

from tts_app.ocr_providers.base import OCROptions, OCRProviderError
from tts_app.ocr_providers.fake import FakeOCRProvider
from tts_app.ocr_providers.qwen import QwenOCRProvider


@pytest.mark.asyncio
async def test_fake_ocr_provider_returns_deterministic_text():
    provider = FakeOCRProvider()

    text = await provider.extract_text(b"image", "image/png", OCROptions(language="zh"))

    assert "Fake OCR text" in text


@pytest.mark.asyncio
async def test_qwen_ocr_provider_requires_api_key():
    provider = QwenOCRProvider(api_key=None, model="qwen-vl-ocr")

    with pytest.raises(OCRProviderError, match="API key is required"):
        await provider.extract_text(b"image", "image/png", OCROptions(language="en"))
```

- [ ] **Step 2: Run OCR provider tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_ocr_provider.py -q
```

Expected: fail because OCR provider modules do not exist.

- [ ] **Step 3: Add OCR provider modules**

Create `src/tts_app/ocr_providers/base.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class OCRProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class OCROptions:
    language: str
    model: str | None = None


class OCRProvider(Protocol):
    name: str

    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
        raise NotImplementedError
```

Create `src/tts_app/ocr_providers/fake.py`:

```python
from __future__ import annotations

from tts_app.ocr_providers.base import OCROptions


class FakeOCRProvider:
    name = "fake-ocr"

    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
        return "Fake OCR text. 你好 ni hao." if options.language == "zh" else "Fake OCR text."
```

Create `src/tts_app/ocr_providers/qwen.py` with API-key validation first. Add request implementation in the next task when API shape is integrated.

Create `src/tts_app/ocr_providers/registry.py`:

```python
from tts_app.config import Settings
from tts_app.ocr_providers.fake import FakeOCRProvider
from tts_app.ocr_providers.qwen import QwenOCRProvider


def get_ocr_provider(settings: Settings):
    if settings.ocr_provider_name == "qwen":
        return QwenOCRProvider(api_key=settings.qwen_api_key, model=settings.qwen_ocr_model)
    return FakeOCRProvider()
```

- [ ] **Step 4: Run OCR provider tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_ocr_provider.py -q
```

Expected: OCR provider tests pass.

Commit:

```bash
git add src/tts_app/ocr_providers tests/test_ocr_provider.py
git commit -m "feat: add ocr provider interface"
```

## Task 5: OCR Draft API And Image Generation

**Files:**
- Modify: `src/tts_app/api.py`
- Modify: `pyproject.toml` if multipart support is missing
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing OCR draft API tests**

Add to `tests/test_api.py`:

```python
def test_create_ocr_draft_stores_image_and_returns_text(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post(
        "/api/ocr-drafts",
        data={"language": "zh"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "zh"
    assert "Fake OCR text" in body["extracted_text"]
    assert (test_settings.data_dir / body["image_path"]).exists()


def test_update_ocr_draft_and_create_generation(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        data={"language": "en"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()

    update = client.put(f"/api/ocr-drafts/{draft['id']}", json={"language": "en", "extracted_text": "Reviewed text."})
    assert update.status_code == 200

    generation = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"text": "Reviewed text.", "voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    assert generation.status_code == 200
    detail = client.get(f"/api/generations/{generation.json()['generation_id']}").json()
    assert detail["generation"]["source_type"] == "image"
    assert detail["generation"]["full_text"] == "Reviewed text."
    assert detail["generation"]["settings"]["ocr_draft_id"] == draft["id"]


def test_delete_linked_ocr_draft_is_rejected_by_api(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        data={"language": "en"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"text": "Reviewed text.", "voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    response = client.delete(f"/api/ocr-drafts/{draft['id']}")

    assert response.status_code == 409
```

- [ ] **Step 2: Run OCR draft API tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_create_ocr_draft_stores_image_and_returns_text tests/test_api.py::test_update_ocr_draft_and_create_generation tests/test_api.py::test_delete_linked_ocr_draft_is_rejected_by_api -q
```

Expected: fail because OCR draft endpoints do not exist.

- [ ] **Step 3: Add multipart dependency if needed**

If FastAPI multipart tests fail with `python-multipart` missing, add to `pyproject.toml`:

```toml
"python-multipart>=0.0.9",
```

Then install in the local environment:

```bash
.venv/bin/pip install -e ".[dev]"
```

- [ ] **Step 4: Add OCR draft routes**

In `create_app()`, instantiate:

```python
ocr_provider = get_ocr_provider(active_settings)
app.state.ocr_provider = ocr_provider
```

Add request model:

```python
class OcrDraftUpdateRequest(BaseModel):
    language: str
    extracted_text: str


class OcrDraftGenerationRequest(BaseModel):
    text: str = Field(min_length=1)
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = "en"
    autoplay: bool = True
```

Add routes for create/list/get/update/delete/generate. Use `UploadFile` and `File`/`Form`.

For image storage:

```python
draft_id = storage.create_ocr_draft(
    image_path="pending",
    original_filename=image.filename,
    mime_type=image.content_type,
    byte_size=len(image_bytes),
    ocr_model=active_settings.qwen_ocr_model,
    language=language,
    extracted_text="",
    status="running",
)
image_dir = active_settings.image_dir / str(draft_id)
image_dir.mkdir(parents=True, exist_ok=True)
relative_path = Path("images") / str(draft_id) / f"source{extension}"
```

After OCR:

```python
text = await ocr_provider.extract_text(image_bytes, image.content_type, OCROptions(language=language, model=active_settings.qwen_ocr_model))
storage.update_ocr_draft_ocr_result(draft_id, image_path=str(relative_path), extracted_text=text, status="completed", error=None)
```

If the current `create_ocr_draft()` requires `image_path`, create the row after reading the upload and before OCR with a final path derived from the new ID, or add a focused method that updates image metadata after ID allocation.

- [ ] **Step 5: Run OCR draft API tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_create_ocr_draft_stores_image_and_returns_text tests/test_api.py::test_update_ocr_draft_and_create_generation tests/test_api.py::test_delete_linked_ocr_draft_is_rejected_by_api -q
```

Expected: OCR draft API tests pass.

Commit:

```bash
git add pyproject.toml src/tts_app/api.py tests/test_api.py
git commit -m "feat: add ocr draft api"
```

## Task 6: Frontend Generate Page

**Files:**
- Modify: `src/tts_app/static/index.html`
- Modify: `src/tts_app/static/app.js`
- Modify: `src/tts_app/static/styles.css`
- Test: `tests/test_frontend_static.py`

- [ ] **Step 1: Write failing frontend static tests**

Add to `tests/test_frontend_static.py`:

```python
def test_frontend_has_image_language_sample_and_preference_controls():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="image-mode"' in html
    assert 'id="language-select"' in html
    assert 'id="voice-star"' in html
    assert 'id="voice-sample"' in html
    assert 'id="image-input"' in html
    assert 'accept="image/*"' in html
    assert 'id="ocr-review-text"' in html
    assert 'id="ocr-drafts-list"' in html


def test_frontend_javascript_uses_voice_sample_and_preference_endpoints():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/api/voice-sample" in js
    assert "/preference" in js
    assert "preferred" in js
    assert "languageSelect" in js


def test_frontend_javascript_uses_ocr_draft_endpoints():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/api/ocr-drafts" in js
    assert "FormData" in js
    assert "ocr-review-text" in js
    assert "/generation" in js
```

- [ ] **Step 2: Run frontend tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_has_image_language_sample_and_preference_controls tests/test_frontend_static.py::test_frontend_javascript_uses_voice_sample_and_preference_endpoints tests/test_frontend_static.py::test_frontend_javascript_uses_ocr_draft_endpoints -q
```

Expected: fail because controls and JS do not exist.

- [ ] **Step 3: Add HTML controls**

Update `index.html`:

- add Image tab button with `id="image-mode"`
- add `language-select` near voice/speed controls
- add star button `id="voice-star"` beside `voice-select`
- add sample button `id="voice-sample"`
- add Image mode panel with:

```html
<input id="image-input" class="hidden" type="file" accept="image/*" capture="environment" aria-label="Image to OCR" />
<button id="extract-image-text" class="secondary-action hidden" type="button">Extract text</button>
<textarea id="ocr-review-text" class="hidden" rows="9" aria-label="Reviewed OCR text"></textarea>
<button id="generate-ocr-audio" class="primary-action hidden" type="button">Generate audio</button>
<div id="ocr-drafts-list" class="history-list"></div>
```

- [ ] **Step 4: Add JavaScript behavior**

Update `app.js`:

- add `inputMode === "image"` support in `setInputMode`
- render language-aware voice options from `/api/options`
- maintain selected voice when filtering/sorting
- toggle selected voice preference via `PUT /api/voices/${voice}/preference`
- call `/api/voice-sample` and play returned `Blob` URL
- upload image with `FormData` to `/api/ocr-drafts`
- show OCR review textarea with returned draft text
- generate audio from `/api/ocr-drafts/${draftId}/generation`
- list recent drafts from `GET /api/ocr-drafts`
- delete drafts with `DELETE /api/ocr-drafts/${draftId}`
- call `stopPlayback()` before sample playback, generation submission, navigation, and opening draft/generation paths that play audio

- [ ] **Step 5: Add CSS**

Update `styles.css` with compact controls:

```css
.voice-row,
.image-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.icon-action {
  min-width: 2.75rem;
  min-height: 2.75rem;
}

.ocr-review {
  width: 100%;
}
```

Adapt names to existing CSS patterns instead of adding conflicting styles.

- [ ] **Step 6: Run frontend checks and commit**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py -q
node --check src/tts_app/static/app.js
```

Expected: frontend static tests pass and JavaScript syntax check exits 0.

Commit:

```bash
git add src/tts_app/static/index.html src/tts_app/static/app.js src/tts_app/static/styles.css tests/test_frontend_static.py
git commit -m "feat: add image and voice controls"
```

## Task 7: Delete Integration, Docs, And Full Verification

**Files:**
- Modify: `src/tts_app/api.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Test: `tests/test_api.py`
- Test: `tests/test_docs.py`

- [ ] **Step 1: Write failing deletion integration test**

Add to `tests/test_api.py`:

```python
def test_delete_image_generation_removes_linked_ocr_draft_and_image(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        data={"language": "en"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    image_path = test_settings.data_dir / draft["image_path"]
    generation_id = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"text": "Reviewed text.", "voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    ).json()["generation_id"]

    response = client.delete(f"/api/generations/{generation_id}")

    assert response.status_code == 204
    assert not image_path.exists()
    assert client.get(f"/api/ocr-drafts/{draft['id']}").status_code == 404
```

- [ ] **Step 2: Run deletion test and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_delete_image_generation_removes_linked_ocr_draft_and_image -q
```

Expected: fail until generation deletion removes linked OCR draft and image files.

- [ ] **Step 3: Update generation deletion**

In `DELETE /api/generations/{generation_id}`:

1. Load generation detail before deleting.
2. Load linked OCR draft with `storage.get_ocr_draft_for_generation(generation_id)`.
3. Delete generation and audio directory.
4. If linked draft exists, remove image directory and delete draft through a force/internal method or delete it after clearing link.

Use `shutil.rmtree(active_settings.image_dir / str(draft["id"]), ignore_errors=True)`.

- [ ] **Step 4: Update docs**

Update `README.md` with:

- OCR/image mode summary
- OCR env vars:
  - `OCR_PROVIDER`
  - `QWEN_OCR_MODEL`
  - `TTS_IMAGE_DIR`
  - `TTS_MAX_IMAGE_BYTES`
  - `TTS_DEFAULT_ENGLISH_VOICE`
  - `TTS_DEFAULT_CHINESE_VOICE`
- note that images are stored under `data/images/`
- note that voice samples do not create History entries

Update `AGENTS.md` with:

- image data retention rule
- OCR provider module paths
- reminder to preserve visible Chinese/pinyin only
- reminder to avoid committing stored images or generated audio

- [ ] **Step 5: Run full verification**

Run:

```bash
.venv/bin/pytest -q
node --check src/tts_app/static/app.js
```

Expected:

- pytest exits 0 with all tests passing
- node exits 0 with no syntax output

- [ ] **Step 6: Commit final integration**

Commit:

```bash
git add src/tts_app/api.py README.md AGENTS.md tests/test_api.py tests/test_docs.py
git commit -m "feat: finalize image generation lifecycle"
```

## Final Checklist

- [ ] `git status -sb` shows only intentional changes or a clean tree.
- [ ] `.venv/bin/pytest -q` passes.
- [ ] `node --check src/tts_app/static/app.js` passes.
- [ ] Manual local smoke test with fake provider:

```bash
TTS_PROVIDER=fake OCR_PROVIDER=fake .venv/bin/uvicorn tts_app.api:create_app --factory --host 127.0.0.1 --port 8001
```

Verify:

- Text generation still works.
- URL generation still works.
- Voice sample plays and does not appear in History.
- Starred voice stays preferred after reload.
- Image upload creates an OCR draft.
- OCR draft review can create audio generation.
- Linked draft deletion is blocked.
- Deleting image generation removes linked image draft.
