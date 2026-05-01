# Local Streaming TTS App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, mobile-first FastAPI web app that turns pasted text or basic HTML page URLs into streamed, cached, replayable text-to-speech audio.

**Architecture:** FastAPI serves one lightweight vanilla HTML/CSS/JS frontend and a JSON/SSE API. SQLite stores generation metadata and text segments; audio segment bytes live on disk. A provider interface keeps generation logic independent from Qwen, with a deterministic fake provider for tests and local development.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, SQLite, httpx, BeautifulSoup4, websockets, pytest, vanilla JavaScript, CSS.

---

## File Structure

- `pyproject.toml`: package metadata, runtime dependencies, dev dependencies, pytest config.
- `.gitignore`: local Python, cache, venv, and generated data exclusions.
- `README.md`: local setup, environment variables, run/test commands.
- `src/tts_app/__init__.py`: package marker.
- `src/tts_app/config.py`: application settings from environment.
- `src/tts_app/models.py`: dataclasses and enum literals shared by storage, services, and API.
- `src/tts_app/storage.py`: SQLite schema creation and repository methods.
- `src/tts_app/segmenter.py`: readable, provider-safe text segmentation.
- `src/tts_app/extractor.py`: basic HTML fetching and readable text extraction.
- `src/tts_app/providers/base.py`: provider protocol, option types, output chunk types, and provider errors.
- `src/tts_app/providers/fake.py`: deterministic provider used by tests and local no-credit runs.
- `src/tts_app/providers/qwen.py`: Qwen provider adapter behind the provider interface.
- `src/tts_app/providers/registry.py`: provider selection from settings.
- `src/tts_app/generation.py`: generation orchestration, audio cache writes, segment status updates.
- `src/tts_app/events.py`: in-process server-sent event broker.
- `src/tts_app/api.py`: FastAPI app factory, API routes, static frontend serving.
- `src/tts_app/static/index.html`: mobile-first UI shell.
- `src/tts_app/static/styles.css`: responsive layout and playback/reading styles.
- `src/tts_app/static/app.js`: lightweight Generate, History, Playback behavior.
- `tests/conftest.py`: temporary app/data fixtures.
- `tests/test_segmenter.py`: segmentation behavior.
- `tests/test_extractor.py`: URL extraction and error behavior.
- `tests/test_storage.py`: SQLite persistence behavior.
- `tests/test_generation.py`: fake-provider generation flow and cached audio.
- `tests/test_api.py`: submit, events, history, detail, audio API behavior.
- `tests/test_frontend_static.py`: static app smoke checks.

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `src/tts_app/__init__.py`
- Create: `src/tts_app/config.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the package and dependency config**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "local-streaming-tts"
version = "0.1.0"
description = "Local mobile-first streaming text-to-speech web app"
requires-python = ">=3.11"
dependencies = [
  "beautifulsoup4>=4.12.3",
  "fastapi>=0.115.0",
  "httpx>=0.27.0",
  "pydantic>=2.8.0",
  "uvicorn[standard]>=0.30.0",
  "websockets>=15.0.1"
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2.0",
  "pytest-asyncio>=0.23.0"
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Add local generated-file exclusions**

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
data/
dist/
*.egg-info/
```

- [ ] **Step 3: Add run and test documentation**

Create `README.md`:

```markdown
# Local Streaming TTS

Local, mobile-first web app for generating streamed text-to-speech audio from pasted text or basic HTML page URLs.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
uvicorn tts_app.api:create_app --factory --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000` locally, or use the machine's Tailscale address when exposing it to your own devices.

## Development Provider

The default provider is `fake`, which writes deterministic small audio-like files and does not call an external API.

```bash
TTS_PROVIDER=fake uvicorn tts_app.api:create_app --factory --reload
```

## Qwen Provider Configuration

```bash
TTS_PROVIDER=qwen
DASHSCOPE_API_KEY=...
QWEN_MODEL=qwen3-tts-flash-realtime
QWEN_REALTIME_URL=wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime
QWEN_VOICE=Cherry
```

## Tests

```bash
pytest
```
```

- [ ] **Step 4: Add package marker and settings**

Create `src/tts_app/__init__.py`:

```python
"""Local streaming TTS app."""
```

Create `src/tts_app/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    audio_dir: Path
    provider_name: str
    qwen_api_key: str | None
    qwen_model: str
    qwen_realtime_url: str
    qwen_voice: str
    default_audio_ext: str
    segment_max_chars: int


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("TTS_DATA_DIR", "data")).resolve()
    return Settings(
        data_dir=data_dir,
        db_path=Path(os.environ.get("TTS_DB_PATH", data_dir / "app.db")).resolve(),
        audio_dir=Path(os.environ.get("TTS_AUDIO_DIR", data_dir / "audio")).resolve(),
        provider_name=os.environ.get("TTS_PROVIDER", "fake"),
        qwen_api_key=os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY"),
        qwen_model=os.environ.get("QWEN_MODEL", "qwen3-tts-flash-realtime"),
        qwen_realtime_url=os.environ.get("QWEN_REALTIME_URL", "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime"),
        qwen_voice=os.environ.get("QWEN_VOICE", "Cherry"),
        default_audio_ext=os.environ.get("TTS_AUDIO_EXT", "mp3"),
        segment_max_chars=int(os.environ.get("TTS_SEGMENT_MAX_CHARS", "550")),
    )
```

- [ ] **Step 5: Add base pytest fixture**

Create `tests/conftest.py`:

```python
from __future__ import annotations

import pytest

from tts_app.config import Settings


@pytest.fixture
def test_settings(tmp_path):
    data_dir = tmp_path / "data"
    return Settings(
        data_dir=data_dir,
        db_path=data_dir / "app.db",
        audio_dir=data_dir / "audio",
        provider_name="fake",
        qwen_api_key=None,
        qwen_model="qwen3-tts-flash-realtime",
        qwen_realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        qwen_voice="Cherry",
        default_audio_ext="mp3",
        segment_max_chars=80,
    )
```

- [ ] **Step 6: Run scaffold check**

Run: `pytest -q`

Expected: pytest runs with no collected tests or all currently collected tests passing.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore README.md src/tts_app/__init__.py src/tts_app/config.py tests/conftest.py
git commit -m "chore: scaffold local tts app"
```

## Task 2: Storage Models And SQLite Repository

**Files:**
- Create: `src/tts_app/models.py`
- Create: `src/tts_app/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Create `tests/test_storage.py`:

```python
from __future__ import annotations

from tts_app.storage import Storage


def test_create_generation_persists_full_text_and_segments(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    generation_id = storage.create_generation(
        source_type="text",
        title="Manual text",
        url=None,
        full_text="First sentence. Second sentence.",
        provider="fake",
        voice="Test",
        settings={"format": "mp3"},
    )
    storage.create_text_segments(generation_id, ["First sentence.", "Second sentence."])

    detail = storage.get_generation(generation_id)

    assert detail["generation"]["id"] == generation_id
    assert detail["generation"]["full_text"] == "First sentence. Second sentence."
    assert [segment["text"] for segment in detail["text_segments"]] == [
        "First sentence.",
        "Second sentence.",
    ]


def test_audio_segment_round_trip(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    generation_id = storage.create_generation(
        source_type="text",
        title="Manual text",
        url=None,
        full_text="Hello.",
        provider="fake",
        voice="Test",
        settings={},
    )
    text_segment_id = storage.create_text_segments(generation_id, ["Hello."])[0]
    storage.record_audio_segment(
        generation_id=generation_id,
        text_segment_id=text_segment_id,
        segment_index=0,
        file_path="data/audio/abc/segment-0001.mp3",
        mime_type="audio/mpeg",
        duration_ms=None,
        byte_size=12,
        status="completed",
        error=None,
    )

    detail = storage.get_generation(generation_id)

    assert detail["audio_segments"][0]["file_path"].endswith("segment-0001.mp3")
    assert detail["audio_segments"][0]["status"] == "completed"


def test_list_generations_orders_newest_first(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    first = storage.create_generation("text", "First", None, "A", "fake", "Test", {})
    second = storage.create_generation("text", "Second", None, "B", "fake", "Test", {})

    rows = storage.list_generations()

    assert [row["id"] for row in rows] == [second, first]
```

- [ ] **Step 2: Run storage tests to verify failure**

Run: `pytest tests/test_storage.py -q`

Expected: FAIL with `ModuleNotFoundError` or missing `Storage`.

- [ ] **Step 3: Implement shared model types**

Create `src/tts_app/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SourceType = Literal["text", "url"]
Status = Literal["queued", "running", "completed", "failed"]


@dataclass(frozen=True)
class TextSegment:
    id: int
    generation_id: int
    segment_index: int
    text: str
    status: str


@dataclass(frozen=True)
class AudioSegment:
    id: int
    generation_id: int
    text_segment_id: int
    segment_index: int
    file_path: str
    mime_type: str
    duration_ms: int | None
    byte_size: int
    status: str
    error: str | None
```

- [ ] **Step 4: Implement SQLite repository**

Create `src/tts_app/storage.py`:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT,
                    full_text TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    voice TEXT NOT NULL,
                    settings_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS text_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generation_id INTEGER NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
                    segment_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(generation_id, segment_index)
                );

                CREATE TABLE IF NOT EXISTS audio_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generation_id INTEGER NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
                    text_segment_id INTEGER NOT NULL REFERENCES text_segments(id) ON DELETE CASCADE,
                    segment_index INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    duration_ms INTEGER,
                    byte_size INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(generation_id, segment_index)
                );
                """
            )

    def create_generation(
        self,
        source_type: str,
        title: str,
        url: str | None,
        full_text: str,
        provider: str,
        voice: str,
        settings: dict[str, Any],
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO generations
                    (source_type, title, url, full_text, provider, voice, settings_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')
                """,
                (source_type, title, url, full_text, provider, voice, json.dumps(settings, sort_keys=True)),
            )
            return int(cur.lastrowid)

    def create_text_segments(self, generation_id: int, segments: list[str]) -> list[int]:
        ids: list[int] = []
        with self.connect() as conn:
            for index, text in enumerate(segments):
                cur = conn.execute(
                    """
                    INSERT INTO text_segments (generation_id, segment_index, text, status)
                    VALUES (?, ?, ?, 'queued')
                    """,
                    (generation_id, index, text),
                )
                ids.append(int(cur.lastrowid))
        return ids

    def update_generation_status(self, generation_id: int, status: str, error: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE generations
                SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, error, generation_id),
            )

    def update_text_segment_status(self, text_segment_id: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE text_segments
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, text_segment_id),
            )

    def record_audio_segment(
        self,
        generation_id: int,
        text_segment_id: int,
        segment_index: int,
        file_path: str,
        mime_type: str,
        duration_ms: int | None,
        byte_size: int,
        status: str,
        error: str | None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO audio_segments
                    (generation_id, text_segment_id, segment_index, file_path, mime_type, duration_ms, byte_size, status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (generation_id, text_segment_id, segment_index, file_path, mime_type, duration_ms, byte_size, status, error),
            )
            return int(cur.lastrowid)

    def list_generations(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, source_type, title, url, substr(full_text, 1, 180) AS text_preview,
                       provider, voice, status, error, created_at, updated_at
                FROM generations
                ORDER BY datetime(created_at) DESC, id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_generation(self, generation_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            generation = conn.execute(
                "SELECT * FROM generations WHERE id = ?",
                (generation_id,),
            ).fetchone()
            if generation is None:
                raise KeyError(f"generation {generation_id} not found")

            text_segments = conn.execute(
                "SELECT * FROM text_segments WHERE generation_id = ? ORDER BY segment_index",
                (generation_id,),
            ).fetchall()
            audio_segments = conn.execute(
                "SELECT * FROM audio_segments WHERE generation_id = ? ORDER BY segment_index",
                (generation_id,),
            ).fetchall()

        generation_dict = dict(generation)
        generation_dict["settings"] = json.loads(generation_dict.pop("settings_json"))
        return {
            "generation": generation_dict,
            "text_segments": [dict(row) for row in text_segments],
            "audio_segments": [dict(row) for row in audio_segments],
        }
```

- [ ] **Step 5: Run storage tests**

Run: `pytest tests/test_storage.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tts_app/models.py src/tts_app/storage.py tests/test_storage.py
git commit -m "feat: add sqlite generation storage"
```

## Task 3: Text Segmentation

**Files:**
- Create: `src/tts_app/segmenter.py`
- Create: `tests/test_segmenter.py`

- [ ] **Step 1: Write failing segmentation tests**

Create `tests/test_segmenter.py`:

```python
from __future__ import annotations

from tts_app.segmenter import segment_text


def test_segment_text_prefers_paragraph_boundaries():
    text = "First paragraph has one sentence.\n\nSecond paragraph has another sentence."

    assert segment_text(text, max_chars=80) == [
        "First paragraph has one sentence.",
        "Second paragraph has another sentence.",
    ]


def test_segment_text_splits_long_paragraph_on_sentences():
    text = "One sentence is here. Two sentence is here. Three sentence is here."

    segments = segment_text(text, max_chars=35)

    assert segments == [
        "One sentence is here.",
        "Two sentence is here.",
        "Three sentence is here.",
    ]


def test_segment_text_splits_long_sentence_on_words():
    text = "alpha beta gamma delta epsilon zeta eta theta"

    segments = segment_text(text, max_chars=20)

    assert all(len(segment) <= 20 for segment in segments)
    assert " ".join(segments) == text


def test_segment_text_rejects_empty_input():
    try:
        segment_text("   ", max_chars=20)
    except ValueError as exc:
        assert str(exc) == "text is empty"
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run segmentation tests to verify failure**

Run: `pytest tests/test_segmenter.py -q`

Expected: FAIL with missing `tts_app.segmenter`.

- [ ] **Step 3: Implement segmenter**

Create `src/tts_app/segmenter.py`:

```python
from __future__ import annotations

import re

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(re.sub(r"\s+", " ", line))
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs).strip()


def segment_text(text: str, max_chars: int = 550) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        raise ValueError("text is empty")
    if max_chars < 20:
        raise ValueError("max_chars must be at least 20")

    segments: list[str] = []
    for paragraph in normalized.split("\n\n"):
        _append_with_limit(segments, paragraph, max_chars)
    return segments


def _append_with_limit(segments: list[str], text: str, max_chars: int) -> None:
    if len(text) <= max_chars:
        segments.append(text)
        return

    sentence_parts = [part.strip() for part in SENTENCE_RE.split(text) if part.strip()]
    if len(sentence_parts) > 1:
        current = ""
        for sentence in sentence_parts:
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > max_chars:
                segments.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            _append_with_limit(segments, current, max_chars)
        return

    words = text.split()
    current_words: list[str] = []
    for word in words:
        candidate = " ".join([*current_words, word])
        if current_words and len(candidate) > max_chars:
            segments.append(" ".join(current_words))
            current_words = [word]
        else:
            current_words.append(word)
    if current_words:
        segments.append(" ".join(current_words))
```

- [ ] **Step 4: Run segmentation tests**

Run: `pytest tests/test_segmenter.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tts_app/segmenter.py tests/test_segmenter.py
git commit -m "feat: add readable text segmentation"
```

## Task 4: Basic HTML Extraction

**Files:**
- Create: `src/tts_app/extractor.py`
- Create: `tests/test_extractor.py`

- [ ] **Step 1: Write failing extractor tests**

Create `tests/test_extractor.py`:

```python
from __future__ import annotations

import httpx
import pytest

from tts_app.extractor import ExtractionError, extract_readable_text, fetch_and_extract


def test_extract_readable_text_prefers_article_content():
    html = """
    <html>
      <head><title>Example Title</title><style>.x{}</style></head>
      <body>
        <nav>Home About</nav>
        <article>
          <h1>Main Heading</h1>
          <p>First useful paragraph.</p>
          <p>Second useful paragraph.</p>
        </article>
        <script>console.log("skip")</script>
      </body>
    </html>
    """

    result = extract_readable_text(html, "https://example.test/page")

    assert result.title == "Main Heading"
    assert result.text == "Main Heading\n\nFirst useful paragraph.\n\nSecond useful paragraph."


def test_extract_readable_text_rejects_empty_pages():
    with pytest.raises(ExtractionError, match="no readable text found"):
        extract_readable_text("<html><body><script>app()</script></body></html>", "https://example.test")


@pytest.mark.asyncio
async def test_fetch_and_extract_rejects_non_html():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/json"}, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ExtractionError, match="unsupported content type"):
        await fetch_and_extract("https://example.test/data", client=client)

    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_and_extract_returns_extracted_result():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body><article><h1>Hello</h1><p>Readable text.</p></article></body></html>",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await fetch_and_extract("https://example.test/post", client=client)

    assert result.title == "Hello"
    assert result.text == "Hello\n\nReadable text."
    await client.aclose()
```

- [ ] **Step 2: Run extractor tests to verify failure**

Run: `pytest tests/test_extractor.py -q`

Expected: FAIL with missing `tts_app.extractor`.

- [ ] **Step 3: Implement extractor**

Create `src/tts_app/extractor.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup


class ExtractionError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedText:
    title: str
    text: str
    url: str


async def fetch_and_extract(url: str, client: httpx.AsyncClient | None = None) -> ExtractedText:
    if not url.startswith(("http://", "https://")):
        raise ExtractionError("invalid URL")

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=15.0, follow_redirects=True)
    try:
        response = await active_client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ExtractionError("page could not be reached") from exc
    finally:
        if owns_client:
            await active_client.aclose()

    content_type = response.headers.get("content-type", "")
    if content_type and "html" not in content_type.lower():
        raise ExtractionError(f"unsupported content type: {content_type}")

    return extract_readable_text(response.text, str(response.url))


def extract_readable_text(html: str, url: str) -> ExtractedText:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "canvas", "form", "header", "footer", "nav", "aside"]):
        tag.decompose()

    container = soup.find("article") or soup.find("main") or soup.body or soup
    title = _pick_title(soup, container)

    chunks: list[str] = []
    for tag in container.find_all(["h1", "h2", "h3", "p", "li", "blockquote"]):
        text = " ".join(tag.get_text(" ", strip=True).split())
        if len(text) >= 2:
            chunks.append(text)

    if not chunks:
        body_text = " ".join(container.get_text(" ", strip=True).split())
        if body_text:
            chunks.append(body_text)

    seen: set[str] = set()
    unique_chunks: list[str] = []
    for chunk in chunks:
        if chunk not in seen:
            seen.add(chunk)
            unique_chunks.append(chunk)

    text = "\n\n".join(unique_chunks).strip()
    if len(text) < 20:
        raise ExtractionError("no readable text found")

    return ExtractedText(title=title, text=text, url=url)


def _pick_title(soup: BeautifulSoup, container) -> str:
    heading = container.find(["h1", "h2"])
    if heading:
        heading_text = " ".join(heading.get_text(" ", strip=True).split())
        if heading_text:
            return heading_text
    if soup.title and soup.title.string:
        return " ".join(soup.title.string.split())
    return "Untitled page"
```

- [ ] **Step 4: Run extractor tests**

Run: `pytest tests/test_extractor.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tts_app/extractor.py tests/test_extractor.py
git commit -m "feat: add basic html text extraction"
```

## Task 5: Provider Interface And Fake Provider

**Files:**
- Create: `src/tts_app/providers/base.py`
- Create: `src/tts_app/providers/fake.py`
- Create: `src/tts_app/providers/registry.py`
- Create: `src/tts_app/providers/__init__.py`
- Create: `tests/test_provider.py`

- [ ] **Step 1: Write failing provider tests**

Create `tests/test_provider.py`:

```python
from __future__ import annotations

import pytest

from tts_app.providers.base import TTSOptions
from tts_app.providers.fake import FakeTTSProvider
from tts_app.providers.registry import get_provider


@pytest.mark.asyncio
async def test_fake_provider_streams_deterministic_chunks():
    provider = FakeTTSProvider()

    chunks = [
        chunk
        async for chunk in provider.stream_speech(
            "Hello world.",
            TTSOptions(voice="Test", audio_format="mp3"),
        )
    ]

    assert chunks[0].mime_type == "audio/mpeg"
    assert b"FAKE-TTS" in chunks[0].data
    assert b"Hello world." in chunks[0].data


def test_registry_returns_fake_provider(test_settings):
    provider = get_provider(test_settings)

    assert provider.name == "fake"
```

- [ ] **Step 2: Run provider tests to verify failure**

Run: `pytest tests/test_provider.py -q`

Expected: FAIL with missing provider modules.

- [ ] **Step 3: Implement provider base types**

Create `src/tts_app/providers/__init__.py`:

```python
"""TTS provider adapters."""
```

Create `src/tts_app/providers/base.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class TTSOptions:
    voice: str
    audio_format: str = "mp3"
    language: str = "Auto"
    sample_rate: int = 24000
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0


@dataclass(frozen=True)
class AudioChunk:
    data: bytes
    mime_type: str
    extension: str


class TTSProvider(Protocol):
    name: str

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        ...
```

- [ ] **Step 4: Implement fake provider and registry**

Create `src/tts_app/providers/fake.py`:

```python
from __future__ import annotations

import asyncio
import hashlib
from typing import AsyncIterator

from tts_app.providers.base import AudioChunk, TTSOptions


class FakeTTSProvider:
    name = "fake"

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        await asyncio.sleep(0)
        digest = hashlib.sha256(f"{options.voice}:{text}".encode("utf-8")).hexdigest()[:16]
        data = f"FAKE-TTS\nvoice={options.voice}\ndigest={digest}\ntext={text}\n".encode("utf-8")
        yield AudioChunk(data=data, mime_type="audio/mpeg", extension="mp3")
```

Create `src/tts_app/providers/registry.py`:

```python
from __future__ import annotations

from tts_app.config import Settings
from tts_app.providers.base import TTSProvider
from tts_app.providers.fake import FakeTTSProvider
from tts_app.providers.qwen import QwenTTSProvider


def get_provider(settings: Settings) -> TTSProvider:
    if settings.provider_name == "fake":
        return FakeTTSProvider()
    if settings.provider_name == "qwen":
        return QwenTTSProvider(
            api_key=settings.qwen_api_key,
            model=settings.qwen_model,
            realtime_url=settings.qwen_realtime_url,
        )
    raise ValueError(f"unknown TTS provider: {settings.provider_name}")
```

- [ ] **Step 5: Add temporary Qwen class so registry imports are stable**

Create `src/tts_app/providers/qwen.py`:

```python
from __future__ import annotations

from typing import AsyncIterator

from tts_app.providers.base import AudioChunk, ProviderError, TTSOptions


class QwenTTSProvider:
    name = "qwen"

    def __init__(self, api_key: str | None, model: str, realtime_url: str):
        self.api_key = api_key
        self.model = model
        self.realtime_url = realtime_url

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        if not self.api_key:
            raise ProviderError("QWEN_API_KEY is required for qwen provider")
        raise ProviderError("qwen realtime provider is added in Task 9")
        yield AudioChunk(data=b"", mime_type="audio/mpeg", extension="mp3")
```

- [ ] **Step 6: Run provider tests**

Run: `pytest tests/test_provider.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/tts_app/providers tests/test_provider.py
git commit -m "feat: add tts provider interface"
```

## Task 6: Generation Service And Event Broker

**Files:**
- Create: `src/tts_app/events.py`
- Create: `src/tts_app/generation.py`
- Create: `tests/test_generation.py`

- [ ] **Step 1: Write failing generation tests**

Create `tests/test_generation.py`:

```python
from __future__ import annotations

import pytest

from tts_app.events import EventBroker
from tts_app.generation import GenerationService
from tts_app.providers.fake import FakeTTSProvider
from tts_app.storage import Storage


@pytest.mark.asyncio
async def test_generation_service_persists_segments_and_audio(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    broker = EventBroker()
    service = GenerationService(
        storage=storage,
        provider=FakeTTSProvider(),
        broker=broker,
        audio_dir=test_settings.audio_dir,
        segment_max_chars=20,
    )

    generation_id = await service.create_from_text("Hello world. Second sentence.", title="Manual text")
    await service.run_generation(generation_id)

    detail = storage.get_generation(generation_id)

    assert detail["generation"]["status"] == "completed"
    assert len(detail["text_segments"]) == 2
    assert len(detail["audio_segments"]) == 2
    for audio in detail["audio_segments"]:
        assert test_settings.audio_dir in (test_settings.data_dir / audio["file_path"]).parents


@pytest.mark.asyncio
async def test_event_broker_replays_generation_events(test_settings):
    broker = EventBroker()
    await broker.publish(7, {"type": "segment_completed", "segment_index": 0})

    events = []
    async for event in broker.subscribe(7):
        events.append(event)
        break

    assert events == [{"type": "segment_completed", "segment_index": 0}]
```

- [ ] **Step 2: Run generation tests to verify failure**

Run: `pytest tests/test_generation.py -q`

Expected: FAIL with missing `EventBroker` or `GenerationService`.

- [ ] **Step 3: Implement event broker**

Create `src/tts_app/events.py`:

```python
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator


class EventBroker:
    def __init__(self):
        self._history: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self._subscribers: dict[int, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    async def publish(self, generation_id: int, event: dict[str, Any]) -> None:
        self._history[generation_id].append(event)
        for queue in list(self._subscribers[generation_id]):
            await queue.put(event)

    async def subscribe(self, generation_id: int) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[generation_id].append(queue)
        try:
            for event in self._history[generation_id]:
                yield event
            while True:
                yield await queue.get()
        finally:
            self._subscribers[generation_id].remove(queue)
```

- [ ] **Step 4: Implement generation service**

Create `src/tts_app/generation.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from tts_app.events import EventBroker
from tts_app.providers.base import ProviderError, TTSOptions, TTSProvider
from tts_app.segmenter import segment_text
from tts_app.storage import Storage


class GenerationService:
    def __init__(
        self,
        storage: Storage,
        provider: TTSProvider,
        broker: EventBroker,
        audio_dir: Path,
        segment_max_chars: int,
    ):
        self.storage = storage
        self.provider = provider
        self.broker = broker
        self.audio_dir = Path(audio_dir)
        self.segment_max_chars = segment_max_chars

    async def create_from_text(
        self,
        text: str,
        title: str,
        source_type: str = "text",
        url: str | None = None,
        voice: str = "Test",
        settings: dict[str, Any] | None = None,
    ) -> int:
        segments = segment_text(text, max_chars=self.segment_max_chars)
        generation_id = self.storage.create_generation(
            source_type=source_type,
            title=title,
            url=url,
            full_text=text,
            provider=self.provider.name,
            voice=voice,
            settings=settings or {},
        )
        self.storage.create_text_segments(generation_id, segments)
        await self.broker.publish(generation_id, {"type": "generation_created", "generation_id": generation_id})
        return generation_id

    async def run_generation(self, generation_id: int, voice: str = "Test") -> None:
        detail = self.storage.get_generation(generation_id)
        self.storage.update_generation_status(generation_id, "running")
        await self.broker.publish(generation_id, {"type": "generation_started", "generation_id": generation_id})

        try:
            for text_segment in detail["text_segments"]:
                await self._run_segment(generation_id, text_segment, voice)
        except ProviderError as exc:
            self.storage.update_generation_status(generation_id, "failed", str(exc))
            await self.broker.publish(generation_id, {"type": "generation_failed", "error": str(exc)})
            return

        self.storage.update_generation_status(generation_id, "completed")
        await self.broker.publish(generation_id, {"type": "generation_completed", "generation_id": generation_id})

    async def _run_segment(self, generation_id: int, text_segment: dict[str, Any], voice: str) -> None:
        segment_index = int(text_segment["segment_index"])
        self.storage.update_text_segment_status(int(text_segment["id"]), "running")
        await self.broker.publish(
            generation_id,
            {"type": "segment_started", "segment_index": segment_index, "text_segment_id": text_segment["id"]},
        )

        data_parts: list[bytes] = []
        mime_type = "audio/mpeg"
        extension = "mp3"
        async for chunk in self.provider.stream_speech(text_segment["text"], TTSOptions(voice=voice)):
            data_parts.append(chunk.data)
            mime_type = chunk.mime_type
            extension = chunk.extension

        data = b"".join(data_parts)
        relative_path = Path("audio") / str(generation_id) / f"segment-{segment_index + 1:04d}.{extension}"
        absolute_path = self.audio_dir.parent / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_bytes(data)

        self.storage.update_text_segment_status(int(text_segment["id"]), "completed")
        audio_id = self.storage.record_audio_segment(
            generation_id=generation_id,
            text_segment_id=int(text_segment["id"]),
            segment_index=segment_index,
            file_path=str(relative_path),
            mime_type=mime_type,
            duration_ms=None,
            byte_size=len(data),
            status="completed",
            error=None,
        )
        await self.broker.publish(
            generation_id,
            {
                "type": "segment_completed",
                "generation_id": generation_id,
                "segment_index": segment_index,
                "text_segment_id": text_segment["id"],
                "audio_segment_id": audio_id,
                "audio_url": f"/api/audio/{generation_id}/{audio_id}",
            },
        )
```

- [ ] **Step 5: Run generation tests**

Run: `pytest tests/test_generation.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tts_app/events.py src/tts_app/generation.py tests/test_generation.py
git commit -m "feat: add streaming generation service"
```

## Task 7: FastAPI Routes And Static Serving

**Files:**
- Create: `src/tts_app/api.py`
- Create: `src/tts_app/static/index.html`
- Modify: `src/tts_app/storage.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from tts_app.api import create_app


def test_submit_text_starts_generation_and_history_returns_item(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    response = client.post("/api/generations/text", json={"text": "Hello world. Another sentence.", "title": "Note"})

    assert response.status_code == 200
    generation_id = response.json()["generation_id"]

    history = client.get("/api/generations")
    assert history.status_code == 200
    assert history.json()[0]["id"] == generation_id
    assert history.json()[0]["title"] == "Note"


def test_generation_detail_contains_audio_after_background_task(test_settings):
    app = create_app(settings=test_settings, run_background_inline=True)
    client = TestClient(app)

    generation_id = client.post(
        "/api/generations/text",
        json={"text": "Hello world. Another sentence.", "title": "Note"},
    ).json()["generation_id"]

    detail = client.get(f"/api/generations/{generation_id}")

    assert detail.status_code == 200
    assert detail.json()["generation"]["id"] == generation_id
    assert len(detail.json()["audio_segments"]) >= 1


def test_audio_endpoint_serves_cached_segment(test_settings):
    app = create_app(settings=test_settings, run_background_inline=True)
    client = TestClient(app)

    generation_id = client.post("/api/generations/text", json={"text": "Hello world.", "title": "Note"}).json()["generation_id"]
    detail = client.get(f"/api/generations/{generation_id}").json()
    audio_id = detail["audio_segments"][0]["id"]

    audio = client.get(f"/api/audio/{generation_id}/{audio_id}")

    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/")
    assert b"FAKE-TTS" in audio.content


def test_root_serves_frontend(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Local TTS" in response.text
```

- [ ] **Step 2: Run API tests to verify failure**

Run: `pytest tests/test_api.py -q`

Expected: FAIL with missing `tts_app.api`.

- [ ] **Step 3: Add audio lookup method to storage**

Modify `src/tts_app/storage.py` by adding this method to `Storage`:

```python
    def get_audio_segment(self, generation_id: int, audio_segment_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM audio_segments
                WHERE generation_id = ? AND id = ?
                """,
                (generation_id, audio_segment_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"audio segment {audio_segment_id} not found")
        return dict(row)
```

- [ ] **Step 4: Add minimal frontend file**

Create `src/tts_app/static/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Local TTS</title>
  </head>
  <body>
    <main id="app">
      <h1>Local TTS</h1>
    </main>
  </body>
</html>
```

- [ ] **Step 5: Implement API app factory**

Create `src/tts_app/api.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from tts_app.config import Settings, load_settings
from tts_app.events import EventBroker
from tts_app.extractor import ExtractionError, fetch_and_extract
from tts_app.generation import GenerationService
from tts_app.providers.registry import get_provider
from tts_app.storage import Storage


class TextGenerationRequest(BaseModel):
    text: str = Field(min_length=1)
    title: str = "Manual text"
    voice: str = "Test"
    autoplay: bool = True


class UrlGenerationRequest(BaseModel):
    url: str = Field(min_length=1)
    voice: str = "Test"
    autoplay: bool = True


def create_app(settings: Settings | None = None, run_background_inline: bool = False) -> FastAPI:
    active_settings = settings or load_settings()
    storage = Storage(active_settings.db_path)
    storage.init_schema()
    broker = EventBroker()
    provider = get_provider(active_settings)
    service = GenerationService(
        storage=storage,
        provider=provider,
        broker=broker,
        audio_dir=active_settings.audio_dir,
        segment_max_chars=active_settings.segment_max_chars,
    )
    app = FastAPI(title="Local Streaming TTS")
    app.state.settings = active_settings
    app.state.storage = storage
    app.state.broker = broker
    app.state.service = service

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")

    @app.post("/api/generations/text")
    async def submit_text(payload: TextGenerationRequest, background_tasks: BackgroundTasks):
        generation_id = await service.create_from_text(
            text=payload.text,
            title=payload.title,
            voice=payload.voice,
            settings={"autoplay": payload.autoplay},
        )
        _schedule_generation(service, generation_id, payload.voice, background_tasks, run_background_inline)
        return {"generation_id": generation_id}

    @app.post("/api/generations/url")
    async def submit_url(payload: UrlGenerationRequest, background_tasks: BackgroundTasks):
        try:
            extracted = await fetch_and_extract(payload.url)
        except ExtractionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        generation_id = await service.create_from_text(
            text=extracted.text,
            title=extracted.title,
            source_type="url",
            url=extracted.url,
            voice=payload.voice,
            settings={"autoplay": payload.autoplay},
        )
        _schedule_generation(service, generation_id, payload.voice, background_tasks, run_background_inline)
        return {"generation_id": generation_id}

    @app.get("/api/generations")
    async def list_generations():
        return storage.list_generations()

    @app.get("/api/generations/{generation_id}")
    async def get_generation(generation_id: int):
        try:
            return storage.get_generation(generation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc

    @app.get("/api/audio/{generation_id}/{audio_segment_id}")
    async def get_audio(generation_id: int, audio_segment_id: int):
        try:
            audio = storage.get_audio_segment(generation_id, audio_segment_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audio not found") from exc
        path = active_settings.data_dir / audio["file_path"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="audio file not found")
        return FileResponse(path, media_type=audio["mime_type"])

    @app.get("/api/generations/{generation_id}/events")
    async def generation_events(generation_id: int):
        async def stream():
            async for event in broker.subscribe(generation_id):
                yield f"data: {json.dumps(event)}\n\n"
        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def _schedule_generation(
    service: GenerationService,
    generation_id: int,
    voice: str,
    background_tasks: BackgroundTasks,
    run_background_inline: bool,
) -> None:
    background_tasks.add_task(service.run_generation, generation_id, voice)
```

- [ ] **Step 6: Run API tests**

Run: `pytest tests/test_api.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/tts_app/api.py src/tts_app/static/index.html src/tts_app/storage.py tests/test_api.py
git commit -m "feat: add fastapi generation api"
```

## Task 8: Mobile Frontend Generate, History, And Playback

**Files:**
- Replace: `src/tts_app/static/index.html`
- Create: `src/tts_app/static/styles.css`
- Create: `src/tts_app/static/app.js`
- Modify: `src/tts_app/api.py`
- Create: `tests/test_frontend_static.py`

- [ ] **Step 1: Write failing frontend static tests**

Create `tests/test_frontend_static.py`:

```python
from __future__ import annotations

from pathlib import Path


STATIC_DIR = Path("src/tts_app/static")


def test_frontend_has_generate_history_and_playback_views():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="generate-view"' in html
    assert 'id="history-view"' in html
    assert 'id="playback-view"' in html
    assert 'id="autoplay"' in html


def test_frontend_javascript_uses_history_and_event_endpoints():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/api/generations/text" in js
    assert "/api/generations/url" in js
    assert "EventSource" in js
    assert "scrollIntoView" in js


def test_frontend_css_is_mobile_first():
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert "bottom-nav" in css
    assert "@media (min-width: 800px)" in css
    assert "active-segment" in css
```

- [ ] **Step 2: Run frontend tests to verify failure**

Run: `pytest tests/test_frontend_static.py -q`

Expected: FAIL because frontend files are minimal or missing.

- [ ] **Step 3: Replace HTML shell**

Replace `src/tts_app/static/index.html` with:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Local TTS</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <main class="app-shell">
      <section id="generate-view" class="view active-view" aria-labelledby="generate-title">
        <h1 id="generate-title">Local TTS</h1>
        <div class="mode-tabs" role="tablist" aria-label="Input mode">
          <button id="text-mode" class="mode-tab active" type="button">Text</button>
          <button id="url-mode" class="mode-tab" type="button">URL</button>
        </div>
        <form id="generate-form" class="panel">
          <label id="text-label" class="field-label" for="text-input">Text</label>
          <textarea id="text-input" rows="9" aria-label="Text to read aloud"></textarea>
          <label id="url-label" class="field-label hidden" for="url-input">URL</label>
          <input id="url-input" class="hidden" type="url" aria-label="Page URL" />
          <label class="toggle-row">
            <input id="autoplay" type="checkbox" checked />
            <span>Auto-play segments</span>
          </label>
          <button class="primary-action" type="submit">Generate</button>
        </form>
      </section>

      <section id="history-view" class="view" aria-labelledby="history-title">
        <h1 id="history-title">History</h1>
        <input id="history-search" class="search-input" type="search" aria-label="Search history" />
        <div id="history-list" class="history-list"></div>
      </section>

      <section id="playback-view" class="view playback-view" aria-labelledby="playback-title">
        <header class="playback-header">
          <button id="back-to-history" class="secondary-action" type="button">Back</button>
          <h1 id="playback-title">Playback</h1>
        </header>
        <div class="player-bar">
          <button id="play-pause" class="primary-action" type="button">Play</button>
          <div>
            <div id="player-status">No segment selected</div>
            <label class="toggle-row compact">
              <input id="scroll-follow" type="checkbox" checked />
              <span>Follow text</span>
            </label>
          </div>
        </div>
        <article id="reading-pane" class="reading-pane"></article>
      </section>
    </main>

    <nav class="bottom-nav" aria-label="Primary">
      <button data-view="generate-view" class="nav-button active" type="button">Generate</button>
      <button data-view="history-view" class="nav-button" type="button">History</button>
    </nav>

    <audio id="audio-player"></audio>
    <script src="/static/app.js" defer></script>
  </body>
</html>
```

- [ ] **Step 4: Add mobile-first CSS**

Create `src/tts_app/static/styles.css`:

```css
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #f7f8fa;
  color: #16181d;
}

button,
input,
textarea {
  font: inherit;
}

.app-shell {
  max-width: 760px;
  min-height: 100vh;
  margin: 0 auto;
  padding: 18px 14px 84px;
}

.view {
  display: none;
}

.active-view {
  display: block;
}

h1 {
  margin: 0 0 16px;
  font-size: 1.55rem;
}

.panel {
  display: grid;
  gap: 12px;
}

.mode-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 12px;
}

.mode-tab,
.secondary-action,
.nav-button {
  min-height: 44px;
  border: 1px solid #c8ced8;
  border-radius: 8px;
  background: #ffffff;
  color: #242833;
}

.mode-tab.active,
.nav-button.active {
  border-color: #1d6fdc;
  color: #0f4fa8;
  background: #eaf2ff;
}

.field-label {
  font-weight: 650;
}

textarea,
input[type="url"],
.search-input {
  width: 100%;
  border: 1px solid #c8ced8;
  border-radius: 8px;
  background: #ffffff;
  padding: 12px;
}

textarea {
  resize: vertical;
  min-height: 220px;
}

.hidden {
  display: none;
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toggle-row.compact {
  font-size: 0.9rem;
  color: #596171;
}

.primary-action {
  min-height: 46px;
  border: 0;
  border-radius: 8px;
  background: #1769d1;
  color: #ffffff;
  font-weight: 700;
}

.history-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.history-item {
  width: 100%;
  border: 1px solid #d8dde6;
  border-radius: 8px;
  background: #ffffff;
  padding: 12px;
  text-align: left;
}

.history-item-title {
  font-weight: 700;
}

.history-item-meta,
.history-item-preview {
  margin-top: 4px;
  color: #596171;
  font-size: 0.92rem;
}

.playback-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.playback-header h1 {
  margin: 0;
}

.player-bar {
  position: sticky;
  top: 0;
  z-index: 2;
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 12px;
  align-items: center;
  margin: 14px -14px 10px;
  padding: 10px 14px;
  background: #ffffff;
  border-bottom: 1px solid #d8dde6;
}

.reading-pane {
  display: grid;
  gap: 10px;
  line-height: 1.6;
  font-size: 1.05rem;
}

.text-segment {
  border-left: 4px solid transparent;
  padding: 8px 10px;
  background: #ffffff;
  border-radius: 8px;
}

.text-segment.pending {
  color: #6b7280;
}

.text-segment.active-segment {
  border-left-color: #1769d1;
  background: #eef5ff;
}

.bottom-nav {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 10px;
  background: #ffffff;
  border-top: 1px solid #d8dde6;
}

@media (min-width: 800px) {
  .app-shell {
    padding-bottom: 28px;
  }

  .bottom-nav {
    position: static;
    max-width: 760px;
    margin: 0 auto 24px;
    border: 0;
    background: transparent;
  }
}
```

- [ ] **Step 5: Add frontend JavaScript**

Create `src/tts_app/static/app.js`:

```javascript
const state = {
  inputMode: "text",
  currentGeneration: null,
  currentDetail: null,
  currentSegmentIndex: 0,
  eventSource: null,
  autoplay: true
};

const views = {
  generate: document.getElementById("generate-view"),
  history: document.getElementById("history-view"),
  playback: document.getElementById("playback-view")
};

const audio = document.getElementById("audio-player");

document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.view));
});

document.getElementById("text-mode").addEventListener("click", () => setInputMode("text"));
document.getElementById("url-mode").addEventListener("click", () => setInputMode("url"));
document.getElementById("generate-form").addEventListener("submit", submitGeneration);
document.getElementById("history-search").addEventListener("input", loadHistory);
document.getElementById("back-to-history").addEventListener("click", () => {
  showView("history-view");
  loadHistory();
});
document.getElementById("play-pause").addEventListener("click", togglePlayPause);

audio.addEventListener("ended", () => {
  playSegment(state.currentSegmentIndex + 1);
});

loadHistory();

function showView(viewId) {
  Object.values(views).forEach((view) => view.classList.remove("active-view"));
  document.getElementById(viewId).classList.add("active-view");
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewId);
  });
}

function setInputMode(mode) {
  state.inputMode = mode;
  document.getElementById("text-mode").classList.toggle("active", mode === "text");
  document.getElementById("url-mode").classList.toggle("active", mode === "url");
  document.getElementById("text-input").classList.toggle("hidden", mode !== "text");
  document.getElementById("text-label").classList.toggle("hidden", mode !== "text");
  document.getElementById("url-input").classList.toggle("hidden", mode !== "url");
  document.getElementById("url-label").classList.toggle("hidden", mode !== "url");
}

async function submitGeneration(event) {
  event.preventDefault();
  state.autoplay = document.getElementById("autoplay").checked;
  const endpoint = state.inputMode === "text" ? "/api/generations/text" : "/api/generations/url";
  const payload = state.inputMode === "text"
    ? { text: document.getElementById("text-input").value, title: "Manual text", autoplay: state.autoplay }
    : { url: document.getElementById("url-input").value, autoplay: state.autoplay };

  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const error = await response.json();
    alert(error.detail || "Generation failed");
    return;
  }

  const data = await response.json();
  await openGeneration(data.generation_id);
  subscribeToEvents(data.generation_id);
}

async function loadHistory() {
  const response = await fetch("/api/generations");
  const rows = await response.json();
  const query = document.getElementById("history-search").value.toLowerCase();
  const list = document.getElementById("history-list");
  list.innerHTML = "";
  rows
    .filter((row) => `${row.title} ${row.url || ""} ${row.text_preview}`.toLowerCase().includes(query))
    .forEach((row) => {
      const button = document.createElement("button");
      button.className = "history-item";
      button.type = "button";
      button.innerHTML = `
        <div class="history-item-title">${escapeHtml(row.title)}</div>
        <div class="history-item-meta">${escapeHtml(row.source_type)} · ${escapeHtml(row.status)} · ${escapeHtml(row.created_at)}</div>
        <div class="history-item-preview">${escapeHtml(row.text_preview || "")}</div>
      `;
      button.addEventListener("click", () => openGeneration(row.id));
      list.appendChild(button);
    });
}

async function openGeneration(generationId) {
  state.currentGeneration = generationId;
  const response = await fetch(`/api/generations/${generationId}`);
  state.currentDetail = await response.json();
  renderPlayback();
  showView("playback-view");
}

function renderPlayback() {
  const pane = document.getElementById("reading-pane");
  pane.innerHTML = "";
  const audioByIndex = new Map(state.currentDetail.audio_segments.map((segment) => [segment.segment_index, segment]));

  state.currentDetail.text_segments.forEach((segment) => {
    const block = document.createElement("button");
    const audioSegment = audioByIndex.get(segment.segment_index);
    block.type = "button";
    block.className = `text-segment ${audioSegment ? "" : "pending"}`;
    block.dataset.segmentIndex = segment.segment_index;
    block.textContent = segment.text;
    block.addEventListener("click", () => playSegment(segment.segment_index));
    pane.appendChild(block);
  });
}

function subscribeToEvents(generationId) {
  if (state.eventSource) {
    state.eventSource.close();
  }
  state.eventSource = new EventSource(`/api/generations/${generationId}/events`);
  state.eventSource.onmessage = async (message) => {
    const event = JSON.parse(message.data);
    if (event.type === "segment_completed" || event.type === "generation_completed") {
      await openGeneration(generationId);
      if (state.autoplay && event.type === "segment_completed" && audio.paused) {
        playSegment(event.segment_index);
      }
    }
  };
}

function playSegment(segmentIndex) {
  const audioSegment = state.currentDetail.audio_segments.find((segment) => segment.segment_index === segmentIndex);
  if (!audioSegment) {
    return;
  }
  state.currentSegmentIndex = segmentIndex;
  audio.src = `/api/audio/${state.currentGeneration}/${audioSegment.id}`;
  audio.play().catch(() => {
    document.getElementById("player-status").textContent = "Tap Play to continue";
  });
  updateActiveSegment();
}

function togglePlayPause() {
  if (audio.paused) {
    playSegment(state.currentSegmentIndex);
  } else {
    audio.pause();
  }
}

function updateActiveSegment() {
  document.querySelectorAll(".text-segment").forEach((segment) => {
    segment.classList.toggle("active-segment", Number(segment.dataset.segmentIndex) === state.currentSegmentIndex);
  });
  document.getElementById("player-status").textContent = `Segment ${state.currentSegmentIndex + 1}`;
  const active = document.querySelector(".active-segment");
  if (active && document.getElementById("scroll-follow").checked) {
    active.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
```

- [ ] **Step 6: Serve static CSS and JS**

Modify `src/tts_app/api.py` imports:

```python
from fastapi.staticfiles import StaticFiles
```

Inside `create_app`, after `app = FastAPI(title="Local Streaming TTS")`, add:

```python
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
```

- [ ] **Step 7: Run frontend and API tests**

Run: `pytest tests/test_frontend_static.py tests/test_api.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/tts_app/static src/tts_app/api.py tests/test_frontend_static.py
git commit -m "feat: add mobile playback frontend"
```

## Task 9: Qwen Provider Transport

**Files:**
- Modify: `src/tts_app/providers/qwen.py`
- Create: `tests/test_qwen_provider.py`

- [ ] **Step 1: Write failing Qwen provider tests with mocked WebSocket transport**

Create `tests/test_qwen_provider.py`:

```python
from __future__ import annotations

import base64
import json

import pytest

from tts_app.providers.base import ProviderError, TTSOptions
from tts_app.providers.qwen import QwenTTSProvider


@pytest.mark.asyncio
async def test_qwen_provider_requires_api_key():
    provider = QwenTTSProvider(
        api_key=None,
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
    )

    with pytest.raises(ProviderError, match="API key is required"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass


@pytest.mark.asyncio
async def test_qwen_provider_sends_realtime_events_and_yields_audio():
    websocket = FakeWebSocket(
        [
            {"type": "session.created"},
            {"type": "session.updated"},
            {"type": "input_text_buffer.committed"},
            {"type": "response.created"},
            {"type": "response.audio.delta", "delta": base64.b64encode(b"abc").decode("ascii")},
            {"type": "response.audio.delta", "delta": base64.b64encode(b"def").decode("ascii")},
            {"type": "response.done"},
        ]
    )
    captured = {}

    async def connect(url, additional_headers):
        captured["url"] = url
        captured["headers"] = additional_headers
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    chunks = [chunk async for chunk in provider.stream_speech("hello", TTSOptions(voice="Cherry"))]

    assert [chunk.data for chunk in chunks] == [b"abc", b"def"]
    assert all(chunk.mime_type == "audio/mpeg" for chunk in chunks)
    assert captured["url"] == "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime?model=qwen3-tts-flash-realtime"
    assert captured["headers"] == {"Authorization": "Bearer key"}
    assert [event["type"] for event in websocket.sent_events] == [
        "session.update",
        "input_text_buffer.append",
        "input_text_buffer.commit",
        "session.finish",
    ]
    assert websocket.sent_events[0]["session"]["voice"] == "Cherry"
    assert websocket.sent_events[0]["session"]["mode"] == "commit"
    assert websocket.sent_events[1]["text"] == "hello"


@pytest.mark.asyncio
async def test_qwen_provider_turns_server_error_into_provider_error():
    websocket = FakeWebSocket([{"type": "error", "error": {"message": "bad voice"}}])

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="bad voice"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Missing")):
            pass


class FakeWebSocket:
    def __init__(self, events):
        self.events = [json.dumps(event) for event in events]
        self.sent_events = []
        self.closed = False

    async def send(self, message):
        self.sent_events.append(json.loads(message))

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.events:
            raise StopAsyncIteration
        return self.events.pop(0)

    async def close(self):
        self.closed = True
```

- [ ] **Step 2: Run Qwen tests to verify failure**

Run: `pytest tests/test_qwen_provider.py -q`

Expected: FAIL because the current Qwen provider does not implement WebSocket transport.

- [ ] **Step 3: Implement Qwen WebSocket transport**

Replace `src/tts_app/providers/qwen.py` with:

```python
from __future__ import annotations

import base64
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import websockets

from tts_app.providers.base import AudioChunk, ProviderError, TTSOptions

QwenConnect = Callable[..., Awaitable[object]]


class QwenTTSProvider:
    name = "qwen"

    def __init__(
        self,
        api_key: str | None,
        model: str,
        realtime_url: str,
        connect: QwenConnect | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.realtime_url = realtime_url
        self.connect = connect or websockets.connect

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        if not self.api_key:
            raise ProviderError("API key is required for qwen provider")
        url = self._build_url()
        websocket = await self.connect(url, additional_headers={"Authorization": f"Bearer {self.api_key}"})
        try:
            await self._send_event(
                websocket,
                {
                    "type": "session.update",
                    "session": {
                        "voice": options.voice,
                        "mode": "commit",
                        "language_type": options.language,
                        "response_format": options.audio_format,
                        "sample_rate": options.sample_rate,
                    },
                },
            )
            await self._send_event(websocket, {"type": "input_text_buffer.append", "text": text})
            await self._send_event(websocket, {"type": "input_text_buffer.commit"})
            await self._send_event(websocket, {"type": "session.finish"})

            async for message in websocket:
                event = json.loads(message)
                event_type = event.get("type")
                if event_type == "error":
                    error = event.get("error") or {}
                    raise ProviderError(error.get("message") or json.dumps(error))
                if event_type == "response.audio.delta":
                    data = base64.b64decode(event.get("delta", ""))
                    yield AudioChunk(
                        data=data,
                        mime_type=_mime_type(options.audio_format),
                        extension=_extension(options.audio_format),
                    )
                if event_type in {"response.done", "session.finished"}:
                    break
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"qwen provider failed: {exc}") from exc
        finally:
            close = getattr(websocket, "close", None)
            if close is not None:
                await close()

    def _build_url(self) -> str:
        separator = "&" if "?" in self.realtime_url else "?"
        return f"{self.realtime_url}{separator}model={self.model}"

    async def _send_event(self, websocket: object, event: dict) -> None:
        event["event_id"] = f"event_{uuid.uuid4().hex}"
        await websocket.send(json.dumps(event))


def _mime_type(audio_format: str) -> str:
    if audio_format == "mp3":
        return "audio/mpeg"
    if audio_format == "wav":
        return "audio/wav"
    if audio_format == "opus":
        return "audio/ogg"
    return "application/octet-stream"


def _extension(audio_format: str) -> str:
    if audio_format in {"mp3", "wav", "opus"}:
        return audio_format
    return "bin"
```

- [ ] **Step 4: Run Qwen provider tests**

Run: `pytest tests/test_qwen_provider.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tts_app/providers/qwen.py tests/test_qwen_provider.py
git commit -m "feat: add qwen realtime provider"
```

## Task 10: End-To-End Verification And Local Run

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add verification checklist to README**

Append to `README.md`:

```markdown
## Verification Checklist

1. Run `pytest`.
2. Run `TTS_PROVIDER=fake uvicorn tts_app.api:create_app --factory --host 0.0.0.0 --port 8000`.
3. Open `http://127.0.0.1:8000`.
4. Paste text with multiple sentences and generate audio.
5. Confirm segments appear in Playback.
6. Tap a text segment and confirm playback jumps to that segment.
7. Open History and confirm the generation is listed.
8. Reopen the item from History and confirm cached segments are still available.
9. Try a basic HTML URL and confirm extracted text appears in Playback.
```

- [ ] **Step 2: Run full test suite**

Run: `pytest -q`

Expected: PASS.

- [ ] **Step 3: Start local dev server**

Run: `TTS_PROVIDER=fake uvicorn tts_app.api:create_app --factory --host 0.0.0.0 --port 8000`

Expected: server starts and logs that Uvicorn is running on `http://0.0.0.0:8000`.

- [ ] **Step 4: Commit verification docs**

```bash
git add README.md
git commit -m "docs: add local verification checklist"
```

## Self-Review Notes

- Spec coverage: scaffold, storage, segmentation, extraction, provider abstraction, fake provider, generation streaming, SSE events, API, mobile UI, history, playback highlighting, tap-to-jump, and cached audio are each covered by tasks.
- Qwen coverage: the plan creates the provider boundary, Qwen configuration, and the WebSocket event transport for Alibaba Cloud Model Studio real-time TTS. The fake provider remains the default for local tests so verification does not require API credits.
- Scope: JavaScript-heavy extraction and single-file audio export remain out of v1.
