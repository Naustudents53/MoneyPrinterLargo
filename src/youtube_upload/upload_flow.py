"""
The actual upload orchestrator. Composes BrowserSession + ListingPoller
+ ThumbnailUploader and applies all the F1/F2 robustness fixes:

F1.3: Ctrl+A / Cmd+A + Delete to clear the auto-filled UUID before
      typing the real title.
F1.4: log + warn when title/description exceed YT's caps, mutate the
      metadata dict so the sidecar reflects what was actually uploaded.
F1.5: preserve `\\n` in description (YouTube accepts multi-line).
F2.1: replace `time.sleep(N)` with explicit waits where there's a
      clear DOM signal.
F2.2: full-page screenshot + page source on any failure path.
F2.3: KeyboardInterrupt during polling marks the cache entry as
      "interrupted" instead of leaving it as "uploading...".
F3.4: shorts and longs share `_resolve_video_url_safe`; no more
      duplicated 35-line block.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Callable, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from status import error, info, success, warning

from . import selectors, upload_config
from .browser_session import BrowserSession
from .failure_capture import capture as capture_failure
from .listing_poller import StudioListingPoller
from .thumbnail_uploader import ThumbnailUploader


class UploadResult:
    __slots__ = ("ok", "url", "interrupted", "stage", "screenshot_dir")

    def __init__(self, ok: bool, url: Optional[str] = None, *,
                 interrupted: bool = False, stage: str = "",
                 screenshot_dir: Optional[str] = None):
        self.ok = ok
        self.url = url
        self.interrupted = interrupted
        self.stage = stage
        self.screenshot_dir = screenshot_dir


class UploadFlow:
    """
    One UploadFlow = one upload. Caller is responsible for keeping the
    BrowserSession alive across multiple uploads (or constructing a new
    one each time).
    """

    def __init__(
        self,
        session: BrowserSession,
        *,
        is_for_kids: bool = False,
        verbose: bool = True,
        on_cache_provisional: Optional[Callable[[dict], None]] = None,
        on_cache_finalize: Optional[Callable[[str, str], None]] = None,
        on_cache_interrupt: Optional[Callable[[str], None]] = None,
    ):
        self.session = session
        self.is_for_kids = is_for_kids
        self.verbose = verbose
        self._on_cache_provisional = on_cache_provisional
        self._on_cache_finalize = on_cache_finalize
        self._on_cache_interrupt = on_cache_interrupt
        self._wait_default = upload_config.default_wait_s()

    # ------- public ------------------------------------------------------

    def upload(
        self,
        *,
        video_path: str,
        metadata: dict,
        subject: str,
        thumbnail_path: str = "",
        is_long_video: bool = False,
        visibility: str = "public",
    ) -> UploadResult:
        """
        Run the upload flow. `metadata` is mutated in place so callers'
        sidecar files reflect what YouTube actually received (post-truncation).
        """
        if not video_path or not str(video_path).strip():
            error("Cannot upload: no video was generated (video_path is empty).")
            return UploadResult(False, stage="precheck")
        if not os.path.isfile(video_path):
            error(f"Cannot upload: video file not found at '{video_path}'.")
            return UploadResult(False, stage="precheck")
        if not subject or not str(subject).strip():
            error("Cannot upload: subject is empty (pipeline aborted earlier).")
            return UploadResult(False, stage="precheck")

        self._truncate_metadata(metadata)
        driver = self.session.ensure_alive()
        wait = WebDriverWait(driver, self._wait_default)

        provisional_marker = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            channel_id = self._resolve_channel_id(driver)
            if self.verbose:
                info(f"\t=> Channel ID: {channel_id}")

            self._open_upload_dialog(driver, wait, video_path)
            self._fill_title_and_description(driver, wait, metadata)
            self._set_made_for_kids(driver, wait)

            thumbnail_uploaded = False
            if thumbnail_path and os.path.isfile(thumbnail_path):
                thumbnail_uploaded = ThumbnailUploader(driver).upload(thumbnail_path)
            elif thumbnail_path:
                warning(f"\t=> Thumbnail file not found on disk: {thumbnail_path} (skipping)")

            self._click_through_wizard(driver, wait)
            self._set_visibility(driver, visibility)
            self._click_done(driver, wait)

            self._emit_provisional_cache(metadata, subject, thumbnail_path, provisional_marker)

            poller = StudioListingPoller(driver, channel_id)
            listing_tab = "upload_video" if is_long_video else "short"

            try:
                cfg = upload_config.long_polling_settings() if is_long_video \
                    else upload_config.short_polling_settings()
                upload_finished = poller.wait_until_settled(
                    listing_tab=listing_tab,
                    kind_label="long video" if is_long_video else "Short",
                    target_title=metadata.get("title", ""),
                    max_wait_s=int(cfg["max_wait_s"]),
                    poll_s=int(cfg["poll_s"]),
                    refresh_s=int(cfg["refresh_s"]),
                    max_studio_error_retries=int(cfg.get("max_studio_error_retries", 5)),
                )
            except KeyboardInterrupt:
                # F2.3: don't leave cache as "uploading..." forever.
                warning(
                    "\nPolling cancelled by user (Ctrl+C). The upload itself may "
                    "still complete in the background — check YouTube Studio "
                    "manually. Cache entry marked as interrupted."
                )
                self._emit_cache_interrupt(provisional_marker)
                return UploadResult(False, interrupted=True, stage="polling")

            url = poller.resolve_video_url(
                listing_tab=listing_tab,
                target_title=metadata.get("title", ""),
            )

            if url:
                success(f" => Uploaded Video: {url}")
                self._emit_cache_finalize(provisional_marker, url)
            else:
                url = "https://studio.youtube.com"
                warning(" => Could not retrieve video URL — check YouTube Studio manually. "
                        "Cache entry has placeholder URL.")

            self._emit_post_banner(is_long_video, upload_finished, bool(url))
            return UploadResult(True, url=url, stage="done")

        except KeyboardInterrupt:
            warning("\nUpload cancelled by user (Ctrl+C).")
            self._emit_cache_interrupt(provisional_marker)
            screenshot_dir = capture_failure(driver, "keyboard_interrupt")
            return UploadResult(False, interrupted=True, stage="upload",
                                screenshot_dir=screenshot_dir)

        except Exception as e:
            import traceback
            error(f"Upload failed: {e}")
            traceback.print_exc()
            warning("Leaving Firefox open so the upload can finish in the background. "
                    "Close the browser manually after YouTube Studio shows the upload is done.")
            screenshot_dir = capture_failure(driver, f"exception_{type(e).__name__}",
                                             extra={"message": str(e)[:300]})
            if screenshot_dir:
                info(f"\t=> Saved upload-failure evidence to {screenshot_dir}")
            return UploadResult(False, stage="upload", screenshot_dir=screenshot_dir)

    # ------- pipeline steps ---------------------------------------------

    def _resolve_channel_id(self, driver) -> str:
        from selenium.common.exceptions import WebDriverException, TimeoutException

        if self.verbose:
            info("\t=> Getting channel ID...")
        attempts = 2
        last_err: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                driver.get("https://studio.youtube.com")
                # Wait until URL becomes the canonical /channel/<id> form.
                try:
                    WebDriverWait(driver, 10).until(
                        lambda d: "/channel/" in d.current_url
                    )
                except Exception:
                    time.sleep(2)
                channel_id = driver.current_url.split("/")[-1]
                return channel_id
            except (WebDriverException, TimeoutException) as e:
                last_err = e
                msg = str(e)
                if attempt < attempts:
                    warning(f"Navigation to YouTube Studio failed ({type(e).__name__}: {msg[:120]}). Retrying with a fresh browser...")
                    self.session.cleanup()
                    self.session.ensure_alive()
                    driver = self.session.driver
                    continue
                raise
        if last_err:
            raise last_err
        return ""

    def _open_upload_dialog(self, driver, wait, video_path: str) -> None:
        if self.verbose:
            info("\t=> Navigating to upload page...")
        driver.get("https://www.youtube.com/upload")

        # F2.1: replace blanket sleep with a wait targeting the file input.
        file_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
        )
        if self.verbose:
            info(f"\t=> Uploading file: {video_path}")
        file_input.send_keys(video_path)

        if self.verbose:
            info("\t=> File selected, waiting for upload dialog to render...")

        # F2.1: instead of sleep(8), wait for the title textbox to appear.
        wait.until(EC.presence_of_element_located((By.ID, "textbox")))

    def _fill_title_and_description(self, driver, wait, metadata: dict) -> None:
        textboxes = wait.until(
            EC.presence_of_all_elements_located((By.ID, "textbox"))
        )
        if len(textboxes) < 2:
            warning(f"Expected 2+ textboxes, found {len(textboxes)}")

        title_el = textboxes[0]
        if self.verbose:
            info("\t=> Setting title...")

        driver.execute_script("arguments[0].scrollIntoView(true);", title_el)
        driver.execute_script("arguments[0].click();", title_el)

        # F1.3: clear any pre-filled value (Studio auto-populates with the
        # filename — a UUID — and `send_keys` would otherwise concatenate).
        selectors.select_all_then_delete(driver, title_el)

        clean_title = metadata["title"]
        title_el.send_keys(clean_title)

        if self.verbose:
            info(f"\t=> Title set: {clean_title}")
            info("\t=> Setting description...")

        description_el = textboxes[-1]
        driver.execute_script("arguments[0].scrollIntoView(true);", description_el)
        driver.execute_script("arguments[0].click();", description_el)
        selectors.select_all_then_delete(driver, description_el)

        # F1.5: preserve newlines — use Keys.RETURN between paragraphs so
        # send_keys actually emits Enter (sending a literal "\n" works in
        # most contenteditable controls but Keys.ENTER is more reliable).
        clean_desc = metadata["description"]
        self._send_multiline(description_el, clean_desc)

        if self.verbose:
            info("\t=> Description set")

    def _send_multiline(self, element, text: str) -> None:
        first = True
        for line in (text or "").split("\n"):
            if not first:
                element.send_keys(Keys.SHIFT, Keys.ENTER)
            element.send_keys(line)
            first = False

    def _set_made_for_kids(self, driver, wait) -> None:
        if self.verbose:
            info("\t=> Setting 'made for kids' choice...")
        try:
            radio = selectors.made_for_kids_radio(driver, for_kids=self.is_for_kids)
            if radio is None:
                warning("Could not find made-for-kids radio")
                return
            wait.until(EC.element_to_be_clickable(radio))
            radio.click()
        except Exception as e:
            warning(f"Could not set kids option: {e}")

    def _click_through_wizard(self, driver, wait) -> None:
        # F2.1: instead of `for step_num in range(3)`, click Next while
        # one is visible. Lets YT add or remove wizard steps without
        # breaking us.
        max_steps = 6  # generous guard against infinite loops
        for step in range(max_steps):
            btn = selectors.next_button(driver)
            if btn is None:
                break
            if self.verbose:
                info(f"\t=> Clicking Next (step {step + 1})...")
            try:
                btn.click()
                # Tiny delay so the next step renders before the next iter.
                time.sleep(1)
            except Exception as e:
                warning(f"Next button step {step + 1} failed: {e}")
                break

    def _set_visibility(self, driver, mode: str) -> None:
        if self.verbose:
            info(f"\t=> Setting visibility to {mode}...")
        try:
            radio = selectors.visibility_radio(driver, mode)
            if radio is None:
                warning(f"Could not resolve visibility radio for mode={mode}")
                return
            radio.click()
        except Exception as e:
            warning(f"Could not set visibility: {e}")

    def _click_done(self, driver, wait) -> None:
        if self.verbose:
            info("\t=> Clicking Done button...")
        try:
            done_btn = wait.until(
                EC.element_to_be_clickable((By.ID, "done-button"))
            )
            done_btn.click()
        except Exception as e:
            warning(f"Done button failed: {e}")

    # ------- helpers -----------------------------------------------------

    def _truncate_metadata(self, metadata: dict) -> None:
        """F1.4: warn + truncate + mutate so sidecar matches reality.
        F1.5: keep newlines in description (only flatten title)."""
        title_max = upload_config.title_max_chars()
        desc_max = upload_config.description_max_chars()

        original_title = (metadata.get("title") or "")
        title = original_title.replace("\n", " ").strip()
        if len(title) > title_max:
            warning(
                f" => Title exceeds {title_max} chars ({len(title)}). "
                f"Truncating: {title[:60]}..."
            )
            title = title[:title_max]
        metadata["title"] = title

        description = metadata.get("description") or ""
        if len(description) > desc_max:
            warning(
                f" => Description exceeds {desc_max} chars ({len(description)}). "
                f"Truncating."
            )
            description = description[:desc_max]
        metadata["description"] = description

    # ------- cache callbacks --------------------------------------------

    def _emit_provisional_cache(self, metadata: dict, subject: str,
                                thumbnail_path: str, provisional_marker: str) -> None:
        if self._on_cache_provisional is None:
            return
        entry = {
            "title": metadata.get("title", ""),
            "description": metadata.get("description", ""),
            "subject": subject,
            "url": "uploading...",
            "date": provisional_marker,
            "last_seen_at": provisional_marker,
            "thumbnail_path": thumbnail_path or "",
        }
        try:
            self._on_cache_provisional(entry)
        except Exception as e:
            warning(f"Could not pre-save cache entry: {e}")

    def _emit_cache_finalize(self, provisional_marker: str, url: str) -> None:
        if self._on_cache_finalize is None:
            return
        try:
            self._on_cache_finalize(provisional_marker, url)
        except Exception as e:
            warning(f"Could not update cache URL: {e}")

    def _emit_cache_interrupt(self, provisional_marker: str) -> None:
        if self._on_cache_interrupt is None:
            return
        try:
            self._on_cache_interrupt(provisional_marker)
        except Exception:
            pass

    def _emit_post_banner(self, is_long: bool, upload_finished: bool, url_resolved: bool) -> None:
        if is_long:
            info("=" * 60)
            info(" Long video upload finished. Firefox is staying OPEN.")
            info(" → Verify in YouTube Studio that the video shows as Public/Unlisted")
            info("   (NOT 'Subiendo', 'Procesando' or 'Pendiente').")
            info(" → When you're satisfied, close Firefox manually.")
            info("=" * 60)
            return

        short_confirmed = bool(upload_finished) and bool(url_resolved)
        if short_confirmed:
            try:
                self.session.cleanup()
            except Exception:
                pass
        else:
            warning("=" * 60)
            warning(" Short upload could NOT be fully confirmed. Firefox is staying OPEN.")
            if not upload_finished:
                warning(" → Wait-for-upload did not complete cleanly within the timeout.")
            if not url_resolved:
                warning(" → Could not retrieve the public video URL.")
            warning(" → Verify in YouTube Studio that the short shows as Public/Unlisted,")
            warning("   then close Firefox manually.")
            warning("=" * 60)
