"""
Two-tab polling against YouTube Studio's video listing.

Studio cancels the upload if you refresh or navigate the tab where the
upload is happening. So we open a separate tab, poll there, and never
touch the upload tab. Same trick is used for resolving the public URL
of the freshly-uploaded video.

This module also handles transient "Oops, something went wrong" Studio
errors with bounded retries and emits structured progress logs to
`status.info` / `status.warning` / `status.error`.
"""

from __future__ import annotations

import time
from typing import Optional

from selenium.webdriver.common.by import By

from status import error, info, warning
from utils import build_url

from . import selectors
from .status_markers import classify_row, page_shows_studio_error


class StudioListingPoller:
    """
    Stateless helper. Constructed with a driver + channel_id; each call
    is a fresh polling loop. Reuses one polling tab opened beside the
    upload tab.
    """

    def __init__(self, driver, channel_id: str):
        self.driver = driver
        self.channel_id = channel_id

    # ------- shared tab plumbing ----------------------------------------

    def _open_status_tab(self):
        existing = set(self.driver.window_handles)
        self.driver.execute_script("window.open('about:blank', '_blank');")
        time.sleep(1)
        new_handles = [h for h in self.driver.window_handles if h not in existing]
        if not new_handles:
            return None
        return new_handles[0]

    def _switch_back(self, original_handle: str) -> None:
        try:
            if original_handle in self.driver.window_handles:
                self.driver.switch_to.window(original_handle)
        except Exception:
            pass

    def _close_tab(self, handle: str) -> None:
        try:
            if handle and handle in self.driver.window_handles:
                self.driver.switch_to.window(handle)
                self.driver.close()
        except Exception:
            pass

    def _listing_url(self, listing_tab: str) -> str:
        return f"https://studio.youtube.com/channel/{self.channel_id}/videos/{listing_tab}"

    # ------- public: wait for Studio to settle --------------------------

    def wait_until_settled(
        self,
        listing_tab: str,
        kind_label: str,
        target_title: str,
        *,
        max_wait_s: int,
        poll_s: int,
        refresh_s: int,
        max_studio_error_retries: int = 5,
    ) -> bool:
        info(f"\t=> Waiting up to {max_wait_s // 60} min for {kind_label} upload + processing...")
        info("\t   (polling in a SEPARATE tab so the upload tab is never disturbed)")

        deadline = time.time() + max_wait_s
        target_match = (target_title or "").strip()[:50]
        listing_url = self._listing_url(listing_tab)

        original_handle = self.driver.current_window_handle
        status_handle = self._open_status_tab()
        if status_handle is None:
            warning("\t=> Could not open status-check tab; falling back to in-place wait.")
            info(f"\t=> Sleeping {min(max_wait_s, 180)}s in place to let upload complete...")
            time.sleep(min(max_wait_s, 180))
            return True

        self.driver.switch_to.window(status_handle)
        try:
            try:
                self.driver.get(listing_url)
                time.sleep(5)
            except Exception as e:
                warning(f"\t=> Could not navigate status tab to listing: {e}")
                return False

            last_status = ""
            last_announce = 0.0
            last_refresh = time.time()
            stable_done_count = 0
            studio_error_retries = 0
            consecutive_empty_polls = 0

            while time.time() < deadline:
                rows = []
                row_text = ""
                try:
                    rows = selectors.listing_video_rows(self.driver)
                    chosen_row = None
                    if target_match:
                        for r in rows[:15]:
                            try:
                                t = r.text.strip()
                            except Exception:
                                t = ""
                            if target_match in t:
                                chosen_row = r
                                break
                    if chosen_row is None and rows:
                        chosen_row = rows[0]
                    if chosen_row is not None:
                        row_text = chosen_row.text
                except Exception:
                    row_text = ""

                if not rows:
                    if page_shows_studio_error(selectors.listing_body_text(self.driver)):
                        studio_error_retries += 1
                        if studio_error_retries > max_studio_error_retries:
                            warning(
                                f"\t=> YT Studio listing keeps showing an error page after "
                                f"{max_studio_error_retries} retries. Giving up on the polling "
                                "tab — the upload tab itself is untouched and likely fine. "
                                "Verify manually in Studio."
                            )
                            return False
                        warning(
                            f"\t=> YT Studio listing showed an error page "
                            f"(retry {studio_error_retries}/{max_studio_error_retries}). "
                            "Re-navigating the polling tab..."
                        )
                        try:
                            self.driver.get(listing_url)
                            time.sleep(8)
                            last_refresh = time.time()
                        except Exception as e:
                            warning(f"\t=> Re-navigation failed: {e}")
                        consecutive_empty_polls = 0
                        time.sleep(poll_s)
                        continue

                state = classify_row(row_text)

                if state == "interrupted":
                    error(
                        f"\t=> {kind_label} upload was INTERRUPTED by YouTube. "
                        "Open the original tab and click 'Reanudar carga / Resume upload' manually."
                    )
                    return False

                if state == "done":
                    studio_error_retries = 0
                    consecutive_empty_polls = 0
                    stable_done_count += 1
                    if stable_done_count >= 2:
                        info(f"\t=> {kind_label} upload + processing finished.")
                        return True
                    info(f"\t=> {kind_label} looks done; confirming with one more poll...")
                elif state in ("uploading", "processing", "checks", "pending"):
                    studio_error_retries = 0
                    consecutive_empty_polls = 0
                    stable_done_count = 0
                    label = {
                        "uploading": "uploading",
                        "processing": "processing",
                        "checks": "running checks",
                        "pending": "pending",
                    }[state]
                    now = time.time()
                    if label != last_status or (now - last_announce) > 60:
                        info(f"\t=> {kind_label} status: {label} — still waiting (upload tab untouched)...")
                        last_status = label
                        last_announce = now
                else:  # state == "empty"
                    stable_done_count = 0
                    consecutive_empty_polls += 1
                    now = time.time()
                    if (now - last_announce) > 60:
                        info(f"\t=> Waiting for {kind_label} to appear in listing...")
                        last_announce = now
                    if consecutive_empty_polls >= 8:
                        studio_error_retries += 1
                        if studio_error_retries > max_studio_error_retries:
                            warning(
                                "\t=> Polling tab never showed any rows after multiple "
                                "re-navigations. Giving up — verify manually in Studio."
                            )
                            return False
                        warning(
                            f"\t=> Polling tab is empty after {consecutive_empty_polls} polls "
                            f"(retry {studio_error_retries}/{max_studio_error_retries}). Re-navigating..."
                        )
                        try:
                            self.driver.get(listing_url)
                            time.sleep(8)
                            last_refresh = time.time()
                        except Exception as e:
                            warning(f"\t=> Re-navigation failed: {e}")
                        consecutive_empty_polls = 0
                        time.sleep(poll_s)
                        continue

                if time.time() - last_refresh > refresh_s:
                    try:
                        self.driver.refresh()
                        time.sleep(5)
                        last_refresh = time.time()
                    except Exception:
                        pass

                time.sleep(poll_s)

            warning(
                f"\t=> Hit total wait cap of {max_wait_s // 60} min for {kind_label}. "
                "Firefox will stay open so YT can keep processing — close it manually when done."
            )
            return False
        finally:
            self._close_tab(status_handle)
            self._switch_back(original_handle)

    # ------- public: resolve final URL ----------------------------------

    def resolve_video_url(
        self,
        listing_tab: str,
        target_title: str,
        *,
        max_attempts: int = 5,
    ) -> Optional[str]:
        if not self.channel_id:
            return None

        listing_url = self._listing_url(listing_tab)
        target_match = (target_title or "").strip()[:50]

        original_handle = self.driver.current_window_handle
        status_handle = self._open_status_tab()
        if status_handle is None:
            return None
        self.driver.switch_to.window(status_handle)

        try:
            videos = []
            for attempt in range(1, max_attempts + 1):
                try:
                    self.driver.get(listing_url)
                except Exception as e:
                    warning(f"URL-resolve navigation failed (attempt {attempt}): {e}")
                    time.sleep(3)
                    continue
                time.sleep(4 if attempt == 1 else 6)

                videos = selectors.listing_video_rows(self.driver)
                if videos:
                    break

                if page_shows_studio_error(selectors.listing_body_text(self.driver)):
                    warning(
                        f"URL-resolve listing showed an error page (attempt {attempt}/{max_attempts}). Retrying..."
                    )
                    time.sleep(2)
                    continue
                time.sleep(2)

            chosen_href = None
            for row in videos[:15]:
                try:
                    row_text = row.text.strip()
                except Exception:
                    row_text = ""
                if target_match and target_match in row_text:
                    chosen_href = selectors.row_video_href(row)
                    if chosen_href:
                        break
            if not chosen_href and videos:
                chosen_href = selectors.row_video_href(videos[0])

            if chosen_href:
                video_id = chosen_href.split("/")[-2]
                return build_url(video_id)
            return None
        except Exception as e:
            warning(f"Could not resolve URL via status tab: {e}")
            return None
        finally:
            self._close_tab(status_handle)
            self._switch_back(original_handle)
