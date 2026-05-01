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


def test_segment_text_splits_oversized_sentence_before_short_sentence():
    text = "alpha beta gamma delta epsilon zeta eta theta. short."

    segments = segment_text(text, max_chars=20)

    assert all(len(segment) <= 20 for segment in segments)
    assert " ".join(segments) == text


def test_segment_text_splits_single_oversized_token():
    text = "x" * 25

    segments = segment_text(text, max_chars=20)

    assert all(len(segment) <= 20 for segment in segments)
    assert "".join(segments) == text


def test_segment_text_rejects_empty_input():
    try:
        segment_text("   ", max_chars=20)
    except ValueError as exc:
        assert str(exc) == "text is empty"
    else:
        raise AssertionError("expected ValueError")


def test_segment_text_rejects_too_small_max_chars():
    try:
        segment_text("hello", max_chars=19)
    except ValueError as exc:
        assert str(exc) == "max_chars must be at least 20"
    else:
        raise AssertionError("expected ValueError")
