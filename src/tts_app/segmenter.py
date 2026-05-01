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
                _append_with_limit(segments, current, max_chars)
                current = sentence
            else:
                current = candidate
        if current:
            _append_with_limit(segments, current, max_chars)
        return

    words = text.split()
    current_words: list[str] = []
    for word in words:
        if len(word) > max_chars:
            if current_words:
                segments.append(" ".join(current_words))
                current_words = []
            segments.extend(
                word[index : index + max_chars]
                for index in range(0, len(word), max_chars)
            )
            continue

        candidate = " ".join([*current_words, word])
        if current_words and len(candidate) > max_chars:
            segments.append(" ".join(current_words))
            current_words = [word]
        else:
            current_words.append(word)
    if current_words:
        segments.append(" ".join(current_words))
