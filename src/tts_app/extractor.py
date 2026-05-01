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
