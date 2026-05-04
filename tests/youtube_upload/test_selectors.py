"""
Tests for `youtube_upload.selectors`. We only test the pure helpers
that don't require a real driver: aria-label chains, positional
fallback for visibility radios, etc. The full selector resolution
against a live DOM is exercised in integration tests (not here).
"""

from unittest.mock import MagicMock

import pytest

from youtube_upload import selectors


class FakeElement:
    def __init__(self, *, displayed=True, enabled=True, attrs=None, text=""):
        self._displayed = displayed
        self._enabled = enabled
        self._attrs = attrs or {}
        self.text = text

    def is_displayed(self) -> bool:
        return self._displayed

    def is_enabled(self) -> bool:
        return self._enabled

    def get_attribute(self, name: str) -> str:
        return self._attrs.get(name, "")


class FakeDriver:
    """Driver double that returns canned find_elements results."""

    def __init__(self, table: dict[tuple[str, str], list]):
        self._table = table

    def find_elements(self, by, sel):
        return self._table.get((by, sel), [])

    def find_element(self, by, sel):
        els = self.find_elements(by, sel)
        if not els:
            raise Exception("no such element")
        return els[0]


def test_thumbnail_input_prefers_image_only_input():
    from selenium.webdriver.common.by import By

    image_input = FakeElement(attrs={"accept": "image/png,image/jpeg"})
    video_input = FakeElement(attrs={"accept": "video/mp4"})

    driver = FakeDriver({
        (By.CSS_SELECTOR, "input[type='file']"): [video_input, image_input],
    })
    assert selectors.thumbnail_input(driver) is image_input


def test_thumbnail_input_falls_back_to_known_selectors():
    from selenium.webdriver.common.by import By

    fallback_input = FakeElement(attrs={})
    driver = FakeDriver({
        (By.CSS_SELECTOR, "input[type='file']"): [],
        (By.CSS_SELECTOR, "ytcp-thumbnails-compact-editor input[type='file']"): [fallback_input],
    })
    assert selectors.thumbnail_input(driver) is fallback_input


def test_visibility_radio_aria_chain_first():
    from selenium.webdriver.common.by import By

    public_radio = FakeElement(attrs={"aria-label": "Público"})
    driver = FakeDriver({
        (By.CSS_SELECTOR, "[aria-label*='Público' i]"): [public_radio],
    })
    assert selectors.visibility_radio(driver, "public") is public_radio


def test_visibility_radio_falls_back_to_position():
    """When aria-label doesn't match, fall back to the positional
    XPath. Order is [private, unlisted, public]."""
    from selenium.webdriver.common.by import By

    radios = [
        FakeElement(text="Privado"),
        FakeElement(text="Oculto"),
        FakeElement(text="Público"),
    ]
    driver = FakeDriver({
        (By.XPATH, "//*[@id=\"radioLabel\"]"): radios,
    })
    assert selectors.visibility_radio(driver, "public") is radios[2]
    assert selectors.visibility_radio(driver, "unlisted") is radios[1]
    assert selectors.visibility_radio(driver, "private") is radios[0]


def test_visibility_radio_unknown_mode_returns_none():
    driver = FakeDriver({})
    assert selectors.visibility_radio(driver, "secret") is None


def test_next_button_only_returns_visible_enabled():
    from selenium.webdriver.common.by import By

    hidden = FakeElement(displayed=False, enabled=True)
    disabled = FakeElement(displayed=True, enabled=False)
    good = FakeElement(displayed=True, enabled=True)
    driver = FakeDriver({(By.ID, "next-button"): [hidden, disabled, good]})
    assert selectors.next_button(driver) is good


def test_next_button_returns_none_when_no_visible_match():
    from selenium.webdriver.common.by import By

    hidden = FakeElement(displayed=False, enabled=True)
    driver = FakeDriver({(By.ID, "next-button"): [hidden]})
    assert selectors.next_button(driver) is None


def test_made_for_kids_radio_matches_correct_name():
    from selenium.webdriver.common.by import By

    yes_el = FakeElement()
    no_el = FakeElement()
    driver = FakeDriver({
        (By.NAME, "VIDEO_MADE_FOR_KIDS_MFK"): [yes_el],
        (By.NAME, "VIDEO_MADE_FOR_KIDS_NOT_MFK"): [no_el],
    })
    assert selectors.made_for_kids_radio(driver, for_kids=True) is yes_el
    assert selectors.made_for_kids_radio(driver, for_kids=False) is no_el


def test_select_all_then_delete_uses_correct_keys(monkeypatch):
    """On non-macOS, should use Ctrl. On macOS, Cmd."""
    from selenium.webdriver.common.keys import Keys

    sent_keys = []
    fake_el = MagicMock()
    fake_el.send_keys.side_effect = lambda *args: sent_keys.append(args)

    # Simulate Linux/Windows
    monkeypatch.setattr(selectors.sys, "platform", "linux")
    selectors.select_all_then_delete(MagicMock(), fake_el)
    assert sent_keys[0] == (Keys.CONTROL, "a")
    assert sent_keys[1] == (Keys.DELETE,)

    sent_keys.clear()
    monkeypatch.setattr(selectors.sys, "platform", "darwin")
    selectors.select_all_then_delete(MagicMock(), fake_el)
    assert sent_keys[0] == (Keys.COMMAND, "a")
    assert sent_keys[1] == (Keys.DELETE,)
