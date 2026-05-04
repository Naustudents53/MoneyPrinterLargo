"""
Custom-thumbnail upload with retry + visual verification.

YouTube hides the thumbnail file input, so we make it visible via JS
before `send_keys`. We then poll the DOM for evidence the upload was
accepted (a blob:/data:/lh3 image src, or aria-label changes that mean
"Replace thumbnail"). Up to N attempts with a backoff between each.

This module is also responsible for resizing thumbnails over the 2 MB
YouTube cap to JPEG-90 before submitting.
"""

from __future__ import annotations

import os
import time

from selenium.webdriver.common.by import By

from status import error, info, success, warning

from . import selectors, upload_config
from .failure_capture import capture as capture_failure


class ThumbnailUploader:
    def __init__(self, driver):
        self.driver = driver

    # ------- public ------------------------------------------------------

    def upload(self, thumb_path: str) -> bool:
        """Upload a custom thumbnail. Returns True on visual confirmation,
        False otherwise. Never raises."""
        if not thumb_path or not os.path.isfile(thumb_path):
            warning(f"\t=> Thumbnail file not found on disk: {thumb_path} (skipping)")
            return False

        cfg = upload_config.thumbnail_settings()
        max_bytes = int(cfg.get("max_bytes", 2 * 1024 * 1024))
        max_attempts = int(cfg.get("max_attempts", 3))
        verify_timeout_s = int(cfg.get("verify_timeout_s", 180))
        verify_poll_s = int(cfg.get("verify_poll_s", 2))
        retry_backoff_s = int(cfg.get("retry_backoff_s", 30))

        abs_thumb = self._fit_size(os.path.abspath(thumb_path), max_bytes)

        info(f"\t=> Uploading thumbnail: {abs_thumb}")

        editor = selectors.thumbnail_editor_container(self.driver)
        if editor is not None:
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor)
                time.sleep(1)
            except Exception:
                pass

        for attempt in range(1, max_attempts + 1):
            info(f"\t=> Thumbnail upload attempt {attempt}/{max_attempts}...")
            try:
                thumb_input = selectors.thumbnail_input(self.driver)
                if thumb_input is None:
                    raise RuntimeError("no thumbnail file input found on Details page")
                self.driver.execute_script(
                    "arguments[0].style.display='block';"
                    "arguments[0].style.visibility='visible';"
                    "arguments[0].style.opacity='1';"
                    "arguments[0].removeAttribute('hidden');",
                    thumb_input,
                )
                thumb_input.send_keys(abs_thumb)
                info(f"\t=> send_keys dispatched; polling up to {verify_timeout_s}s for preview...")
            except Exception as e:
                warning(f"\t=> send_keys failed on attempt {attempt}: {str(e)[:200]}")
                if attempt < max_attempts:
                    time.sleep(retry_backoff_s)
                continue

            if self._wait_for_preview(verify_timeout_s, verify_poll_s):
                success(f"\t=> Thumbnail visually confirmed (attempt {attempt}).")
                time.sleep(5)  # let YT settle so subsequent Next click hits the right step
                return True

            warning(f"\t=> Thumbnail preview NOT detected after {verify_timeout_s}s on attempt {attempt}.")
            if attempt < max_attempts:
                info(f"\t=> Waiting {retry_backoff_s}s before re-trying full upload...")
                time.sleep(retry_backoff_s)

        error(
            f"Thumbnail upload failed: visual verification never succeeded after {max_attempts} attempts. "
            f"The thumbnail file is preserved at:\n    {abs_thumb}\n"
            "Common causes: channel not verified for custom thumbnails, file > 2 MB, "
            "or YT Studio DOM changed. Open YouTube Studio → your video → Edit → upload it manually."
        )
        capture_failure(self.driver, "thumbnail_upload_failed", extra={"path": abs_thumb})
        return False

    # ------- internals ---------------------------------------------------

    def _fit_size(self, abs_thumb: str, max_bytes: int) -> str:
        try:
            fsize = os.path.getsize(abs_thumb)
        except Exception:
            return abs_thumb
        if fsize <= max_bytes:
            return abs_thumb

        warning(
            f"\t=> Thumbnail is {fsize/1024/1024:.2f} MB (>{max_bytes/1024/1024:.0f} MB cap); "
            "re-encoding as JPEG to fit YouTube's limit."
        )
        try:
            from PIL import Image as _PilImage
            jpg_path = os.path.splitext(abs_thumb)[0] + "_yt.jpg"
            with _PilImage.open(abs_thumb) as im:
                im.convert("RGB").save(jpg_path, "JPEG", quality=90, optimize=True)
            new_size = os.path.getsize(jpg_path)
            if new_size <= max_bytes:
                info(f"\t=> Re-encoded thumbnail: {jpg_path} ({new_size/1024/1024:.2f} MB)")
                return jpg_path
            warning("\t=> Re-encoded JPEG still over cap; YouTube will likely reject it.")
        except Exception as e:
            warning(f"\t=> JPEG re-encode failed: {str(e)[:150]}")
        return abs_thumb

    def _wait_for_preview(self, timeout_s: int, poll_s: int) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._preview_visible():
                return True
            time.sleep(poll_s)
        return False

    def _preview_visible(self) -> bool:
        try:
            for img in selectors.thumbnail_preview_imgs(self.driver):
                try:
                    src = (img.get_attribute("src") or "").lower()
                except Exception:
                    continue
                if not src:
                    continue
                if "ytimg.com" in src:
                    continue
                if (src.startswith("blob:")
                        or src.startswith("data:image")
                        or "googleusercontent.com" in src
                        or "lh3.google" in src
                        or "yt3.ggpht.com" in src):
                    return True

            for sel in selectors.THUMBNAIL_REPLACE_ARIA_SELECTORS:
                try:
                    if self.driver.find_elements(By.CSS_SELECTOR, sel):
                        return True
                except Exception:
                    continue

            try:
                upload_ctas = []
                for sel in selectors.THUMBNAIL_UPLOAD_CTA_SELECTORS:
                    upload_ctas.extend(self.driver.find_elements(By.CSS_SELECTOR, sel))
                visible_cta = any(el.is_displayed() for el in upload_ctas if el is not None)
                if upload_ctas and not visible_cta:
                    return True
            except Exception:
                pass
        except Exception:
            pass
        return False
