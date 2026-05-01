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
