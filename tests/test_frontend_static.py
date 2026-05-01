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
