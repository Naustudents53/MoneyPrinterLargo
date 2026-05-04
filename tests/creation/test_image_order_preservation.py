"""
Tests for the parallelized image-generation orchestrator.

When workers complete out of order (which they will, because some
prompts hit slow providers and others hit fast ones), the final
self.images list MUST still be in prompt order — otherwise combine()
distributes durations to the wrong images.
"""

import time
from unittest.mock import patch

import pytest


def _make_youtube_no_init():
    """Bypass Selenium-firing __init__."""
    from classes.YouTube import YouTube
    obj = YouTube.__new__(YouTube)
    obj.images = []
    obj._used_stock_urls = set()
    obj.subject = "test subject"
    obj._image_style = ""
    obj._account_uuid = "test-acc"
    return obj


def test_parallel_images_preserve_prompt_order(tmp_path, monkeypatch):
    """
    Submit 6 prompts. Provider returns FAST for even indices and SLOW
    for odd indices, so workers complete out of order. self.images must
    still be in [0,1,2,3,4,5] order, not in finishing order.
    """
    from classes.YouTube import YouTube

    yt = _make_youtube_no_init()

    # Stub _persist_image to return a path encoding the prompt label
    # (the orchestrator passes provider_label as the second arg, but
    # bytes carry the prompt for tracing — see fake provider below).
    def fake_persist(image_bytes, label, append=True):
        # bytes payload is "<prompt>:<padding...>" — split on ':'
        prompt = image_bytes.split(b":", 1)[0].decode()
        path = f"img_{prompt}.png"
        if append:
            yt.images.append(path)
        return path

    monkeypatch.setattr(yt, "_persist_image", fake_persist)

    # Provider that finishes at different speeds AND embeds the prompt
    # into its bytes so we can verify that worker N produced image N.
    def fake_provider(prompt: str) -> bytes:
        idx = int(prompt[1:])  # "p3" → 3
        if idx % 2 == 0:
            time.sleep(0.01)
        else:
            time.sleep(0.05)  # odd workers finish later — out-of-order completion
        # Embed prompt + pad past the 1000-byte minimum
        return prompt.encode() + b":" + (b"x" * 1500)

    # Patch every provider to the same stub so cascade order doesn't matter.
    for name in [
        "_try_nanobanana2", "_try_leonardo",
        "_try_pollinations", "_try_pollinations_turbo",
        "_try_pollinations_realism", "_try_huggingface",
        "_try_pexels", "_try_pixabay",
    ]:
        monkeypatch.setattr(yt, name, fake_provider)

    monkeypatch.setattr(yt, "_apply_channel_style", lambda p: p)
    monkeypatch.setattr(yt, "_augment_for_ai_fallback", lambda p: p)

    # Force PARALLEL mode (>=2 threads) so workers race to complete.
    monkeypatch.setattr("classes.YouTube.get_threads", lambda: 4)
    monkeypatch.setattr("classes.YouTube.get_verbose", lambda: False)

    prompts = [f"p{i}" for i in range(6)]
    yt.generate_images_batch(prompts, image_mode="ai")

    # Verify order: even though odd workers finished AFTER even ones,
    # self.images is in the original prompt order [p0, p1, p2, p3, p4, p5].
    assert len(yt.images) == 6
    for i, path in enumerate(yt.images):
        assert path == f"img_p{i}.png", f"Position {i}: got {path}"


def test_parallel_images_empty_results_filtered(monkeypatch):
    """If a worker returns "" (every provider failed AND fallback
    couldn't produce anything either), that slot is dropped from
    self.images."""
    from classes.YouTube import YouTube

    yt = _make_youtube_no_init()

    monkeypatch.setattr(yt, "_apply_channel_style", lambda p: p)
    monkeypatch.setattr(yt, "_augment_for_ai_fallback", lambda p: p)
    monkeypatch.setattr("classes.YouTube.get_threads", lambda: 1)
    monkeypatch.setattr("classes.YouTube.get_verbose", lambda: False)

    # Make every provider raise, and make fallback raise too
    for name in [
        "_try_nanobanana2", "_try_leonardo",
        "_try_pollinations", "_try_pollinations_turbo",
        "_try_pollinations_realism", "_try_huggingface",
        "_try_pexels", "_try_pixabay",
    ]:
        monkeypatch.setattr(yt, name, lambda p: (_ for _ in ()).throw(RuntimeError("nope")))

    def raise_fallback(prompt):
        raise RuntimeError("fallback also broken")
    monkeypatch.setattr(yt, "_generate_fallback_image", raise_fallback)

    yt.generate_images_batch(["p0", "p1", "p2"], image_mode="ai")

    # All workers returned "" → self.images should be empty (no None entries)
    assert yt.images == []
