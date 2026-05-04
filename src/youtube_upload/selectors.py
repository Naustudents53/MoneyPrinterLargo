"""
Centralized Selenium selectors for YouTube Studio's upload dialog.

Each public function takes a driver and returns the WebElement (or None
if the element cannot be found via any fallback). Callers are expected
to wrap these in WebDriverWait when they need explicit timeouts.

The fallback strategy is: try the most stable selector first (CSS by id
or known custom-element), then less stable selectors, then generic
attribute matching. If you change YouTube Studio selectors, do it here
and everywhere benefits.
"""

from __future__ import annotations

import sys
from typing import Iterable, List, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement


# ---------- low-level helpers ----------------------------------------------


def _first_match(driver: WebDriver, locators: Iterable[tuple[str, str]]) -> Optional[WebElement]:
    """Try each (By, selector) pair, return the first element found, else None."""
    for by, sel in locators:
        try:
            els = driver.find_elements(by, sel)
        except Exception:
            els = []
        for el in els:
            if el is not None:
                return el
    return None


def _all_matches(driver: WebDriver, locators: Iterable[tuple[str, str]]) -> List[WebElement]:
    out: List[WebElement] = []
    for by, sel in locators:
        try:
            out.extend(driver.find_elements(by, sel))
        except Exception:
            continue
    return out


# ---------- title / description --------------------------------------------


def title_input(driver: WebDriver) -> Optional[WebElement]:
    """Studio's title field. The first id='textbox' element on the dialog."""
    boxes = driver.find_elements(By.ID, "textbox")
    return boxes[0] if boxes else None


def description_input(driver: WebDriver) -> Optional[WebElement]:
    """Studio's description field. The last id='textbox' element on the dialog."""
    boxes = driver.find_elements(By.ID, "textbox")
    return boxes[-1] if len(boxes) >= 2 else None


def select_all_then_delete(driver: WebDriver, element: WebElement) -> None:
    """Replace whatever is in `element` (typically the auto-filled UUID
    filename) with nothing. Cross-platform: uses Cmd on macOS, Ctrl elsewhere."""
    select_key = Keys.COMMAND if sys.platform == "darwin" else Keys.CONTROL
    element.send_keys(select_key, "a")
    element.send_keys(Keys.DELETE)


# ---------- made-for-kids radio --------------------------------------------


def made_for_kids_radio(driver: WebDriver, *, for_kids: bool) -> Optional[WebElement]:
    name = "VIDEO_MADE_FOR_KIDS_MFK" if for_kids else "VIDEO_MADE_FOR_KIDS_NOT_MFK"
    els = driver.find_elements(By.NAME, name)
    return els[0] if els else None


# ---------- thumbnail ------------------------------------------------------


def thumbnail_input(driver: WebDriver) -> Optional[WebElement]:
    """The hidden file input for custom thumbnails. YouTube changes the
    DOM selector frequently, so we have a long fallback chain."""
    # First: any image-only file input on the page (most generic and robust).
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
    except Exception:
        inputs = []
    for inp in inputs:
        try:
            accept = (inp.get_attribute("accept") or "").lower()
        except Exception:
            accept = ""
        if "image" in accept and "video" not in accept:
            return inp

    # Second: known custom-element selectors.
    return _first_match(driver, [
        (By.CSS_SELECTOR, "ytcp-thumbnails-compact-editor input[type='file']"),
        (By.CSS_SELECTOR, "ytcp-thumbnails-compact-editor-uploader input[type='file']"),
        (By.CSS_SELECTOR, "ytcp-thumbnail-uploader input[type='file']"),
        (By.CSS_SELECTOR, "input#file-loader[accept*='image']"),
    ])


def thumbnail_editor_container(driver: WebDriver) -> Optional[WebElement]:
    return _first_match(driver, [
        (By.CSS_SELECTOR, "ytcp-thumbnails-compact-editor"),
        (By.CSS_SELECTOR, "ytcp-thumbnail-uploader"),
        (By.CSS_SELECTOR, "ytcp-thumbnails-compact-editor-uploader"),
    ])


def thumbnail_preview_imgs(driver: WebDriver) -> List[WebElement]:
    """All <img> elements inside any thumbnail container (used by visual
    verification — we accept the upload when any of these has a src that
    is a blob:, data:, or googleusercontent host)."""
    return _all_matches(driver, [
        (By.CSS_SELECTOR, "ytcp-thumbnails-compact-editor img"),
        (By.CSS_SELECTOR, "ytcp-thumbnail-uploader img"),
        (By.CSS_SELECTOR, "ytcp-thumbnails-compact-editor-uploader img"),
        (By.CSS_SELECTOR, "ytcp-uploads-still img"),
        (By.CSS_SELECTOR, "ytcp-thumbnail-card img"),
        (By.CSS_SELECTOR, "ytcp-thumbnail img"),
    ])


THUMBNAIL_REPLACE_ARIA_SELECTORS: tuple[str, ...] = (
    "[aria-label*='Cambiar miniatura' i]",
    "[aria-label*='Reemplazar miniatura' i]",
    "[aria-label*='Editar miniatura' i]",
    "[aria-label*='Opciones de miniatura' i]",
    "[aria-label*='Replace thumbnail' i]",
    "[aria-label*='Edit thumbnail' i]",
    "[aria-label*='Thumbnail options' i]",
    "ytcp-thumbnail-card-options",
    "ytcp-thumbnails-compact-editor ytcp-thumbnail-card[selected]",
)

THUMBNAIL_UPLOAD_CTA_SELECTORS: tuple[str, ...] = (
    "[aria-label*='Subir miniatura' i]",
    "[aria-label*='Upload thumbnail' i]",
)


# ---------- wizard navigation ----------------------------------------------


def next_button(driver: WebDriver) -> Optional[WebElement]:
    """The 'Next' button on the upload wizard. Returns None when already
    on the last step (= caller knows to stop clicking)."""
    els = driver.find_elements(By.ID, "next-button")
    for el in els:
        try:
            if el.is_displayed() and el.is_enabled():
                return el
        except Exception:
            continue
    return None


def done_button(driver: WebDriver) -> Optional[WebElement]:
    els = driver.find_elements(By.ID, "done-button")
    for el in els:
        try:
            if el.is_displayed() and el.is_enabled():
                return el
        except Exception:
            continue
    return els[0] if els else None


# ---------- visibility radios ----------------------------------------------


VISIBILITY_PUBLIC_ARIA = (
    "[aria-label*='Público' i]",
    "[aria-label*='Public' i]",
    "[name='PUBLIC']",
)
VISIBILITY_UNLISTED_ARIA = (
    "[aria-label*='Oculto' i]",
    "[aria-label*='No listado' i]",
    "[aria-label*='Unlisted' i]",
    "[name='UNLISTED']",
)
VISIBILITY_PRIVATE_ARIA = (
    "[aria-label*='Privado' i]",
    "[aria-label*='Private' i]",
    "[name='PRIVATE']",
)


def visibility_radio(driver: WebDriver, mode: str) -> Optional[WebElement]:
    """
    Return the visibility radio for `mode` ∈ {"public","unlisted","private"}.
    Falls back to positional radio selection if aria-label lookup fails
    (current YT Studio renders 3 radios in this order: Private, Unlisted, Public).
    """
    aria_chains = {
        "public": VISIBILITY_PUBLIC_ARIA,
        "unlisted": VISIBILITY_UNLISTED_ARIA,
        "private": VISIBILITY_PRIVATE_ARIA,
    }
    selectors = aria_chains.get(mode.lower())
    if selectors:
        for sel in selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el is not None:
                    return el
            except Exception:
                continue

    # Positional fallback. As of YT Studio 2025, the order is:
    #   [0] Private, [1] Unlisted, [2] Public.
    radios = driver.find_elements(By.XPATH, "//*[@id=\"radioLabel\"]")
    positional_index = {"private": 0, "unlisted": 1, "public": 2}.get(mode.lower())
    if positional_index is None:
        return None
    if positional_index < len(radios):
        return radios[positional_index]
    if radios:
        return radios[-1]
    return None


# ---------- listing rows (Studio /videos/upload_video or /short) ----------


def listing_video_rows(driver: WebDriver):
    return driver.find_elements(By.TAG_NAME, "ytcp-video-row")


def listing_body_text(driver: WebDriver) -> str:
    try:
        return (driver.find_element(By.TAG_NAME, "body").text or "")
    except Exception:
        return ""


def row_video_href(row: WebElement) -> Optional[str]:
    try:
        return row.find_element(By.TAG_NAME, "a").get_attribute("href")
    except Exception:
        return None


# ---------- file input (main video) ----------------------------------------


def video_file_input(driver: WebDriver) -> Optional[WebElement]:
    """The first `input[type='file']` on `youtube.com/upload`. Used to
    submit the .mp4 itself (not the thumbnail)."""
    try:
        return driver.find_element(By.CSS_SELECTOR, "input[type='file']")
    except Exception:
        return None
