import os
import time
import shutil
import tempfile

from status import info, success, warning, error
from config import ROOT_DIR, get_verbose, get_headless, get_imagemagick_path, get_is_for_kids
from utils import build_url as _build_url
from constants import YOUTUBE_TEXTBOX_ID, YOUTUBE_NOT_MADE_FOR_KIDS_NAME, YOUTUBE_MADE_FOR_KIDS_NAME, YOUTUBE_NEXT_BUTTON_ID, YOUTUBE_RADIO_BUTTON_XPATH, YOUTUBE_DONE_BUTTON_ID, YOUTUBE_THUMBNAIL_INPUT_CSS

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service
from webdriver_manager.firefox import GeckoDriverManager
from moviepy.config import change_settings
from termcolor import colored
from datetime import datetime

from compat import find_ffmpeg

change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})


class YouTubeUploader:
    def _init_selenium(self, fp_profile_path):
        from config import get_verbose as _verbose, get_headless as _headless

        self.options = FirefoxOptions()
        self.options.page_load_strategy = "eager"

        for pref_name, pref_value in (
            ("app.update.enabled", False),
            ("app.update.auto", False),
            ("browser.crashReports.unsubmittedCheck.enabled", False),
            ("toolkit.telemetry.enabled", False),
            ("datareporting.healthreport.uploadEnabled", False),
            ("dom.ipc.processCount", 1),
        ):
            try:
                self.options.set_preference(pref_name, pref_value)
            except Exception:
                pass

        if _headless():
            self.options.add_argument("--headless")

        if not os.path.isdir(fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {fp_profile_path}"
            )

        self._temp_profile_dir = tempfile.mkdtemp(prefix="mpv2_firefox_")
        temp_profile = os.path.join(self._temp_profile_dir, "profile")
        if _verbose():
            info(" => Copying Firefox profile to temp dir...")
        shutil.copytree(
            fp_profile_path, temp_profile,
            ignore=shutil.ignore_patterns(
                "lock", ".parentlock", "parent.lock",
                "cache2", "startupCache", "shader-cache",
                "thumbnails", "storage", "crashes",
            ),
            dirs_exist_ok=False,
        )
        for bad_file in ["sessionstore.jsonlz4", "sessionstore-backups"]:
            bad_path = os.path.join(temp_profile, bad_file)
            if os.path.isfile(bad_path):
                os.remove(bad_path)
            elif os.path.isdir(bad_path):
                shutil.rmtree(bad_path, ignore_errors=True)

        self.options.add_argument("-profile")
        self.options.add_argument(temp_profile)
        self.browser = None

    def _ensure_browser(self):
        session_alive = False
        if self.browser is not None:
            try:
                _ = self.browser.current_url
                session_alive = True
            except Exception:
                session_alive = False
                try:
                    self.browser.quit()
                except Exception:
                    pass
                self.browser = None

        if not session_alive:
            info(" => Conectando con Firefox...")
            try:
                info("    [1/3] Instalando/verificando geckodriver...")
                driver_path = GeckoDriverManager().install()
                info(f"    [2/3] geckodriver listo: {driver_path}")
                service = Service(driver_path)
                info("    [3/3] Lanzando Firefox con perfil temporal...")
                self.browser = webdriver.Firefox(service=service, options=self.options)
                try:
                    self.browser.set_page_load_timeout(90)
                    self.browser.set_script_timeout(60)
                except Exception:
                    pass
                success(" => Firefox conectado.")
            except Exception as e:
                import traceback as _tb
                error(f"Failed to launch Firefox: {type(e).__name__}: {e}")
                error("Full traceback:")
                error(_tb.format_exc())
                raise

    def get_channel_id(self):
        from selenium.common.exceptions import WebDriverException, TimeoutException

        attempts = 2
        last_err = None
        for attempt in range(1, attempts + 1):
            try:
                driver = self.browser
                driver.get("https://studio.youtube.com")
                time.sleep(2)
                channel_id = driver.current_url.split("/")[-1]
                self.channel_id = channel_id
                return channel_id
            except (WebDriverException, TimeoutException) as e:
                last_err = e
                msg = str(e)
                if attempt < attempts:
                    warning(f"Navigation to YouTube Studio failed ({type(e).__name__}: {msg[:120]}). Retrying with a fresh browser...")
                    try:
                        if self.browser is not None:
                            self.browser.quit()
                    except Exception:
                        pass
                    self.browser = None
                    self._ensure_browser()
                    continue
                raise

        if last_err:
            raise last_err
        return ""

    def _wait_for_listing_settled(self, driver, listing_tab, kind_label, max_wait_s, poll_interval_s=8, refresh_interval_s=60):
        info(f"\t=> Waiting up to {max_wait_s // 60} min for {kind_label} upload + processing...")
        info("\t   (polling in a SEPARATE tab so the upload tab is never disturbed)")

        deadline = time.time() + max_wait_s
        listing_url = f"https://studio.youtube.com/channel/{self.channel_id}/videos/{listing_tab}"
        target_title = (self.metadata.get("title") or "").strip()
        target_match = target_title[:50] if target_title else ""

        in_progress_markers = (
            "subiendo", "uploading", "procesando", "processing",
            "pendiente", "pending", "verificando", "verificaciones en curso",
            "checking", "checks in progress", "cancelar carga", "cancel upload",
        )
        error_markers = ("subida interrumpida", "carga interrumpida", "upload interrupted")
        studio_error_markers = (
            "oops, something went wrong", "something went wrong",
            "algo salió mal", "algo salio mal", "ha ocurrido un error",
            "se produjo un error", "intenta volver a cargar", "try reloading",
            "try again later", "vuelve a intentarlo",
        )
        max_studio_error_retries = 5

        original_handle = driver.current_window_handle
        status_handle = None
        try:
            existing = set(driver.window_handles)
            driver.execute_script("window.open('about:blank', '_blank');")
            time.sleep(1)
            new_handles = [h for h in driver.window_handles if h not in existing]
            if not new_handles:
                warning("\t=> Could not open status-check tab; falling back to in-place wait.")
                info(f"\t=> Sleeping {min(max_wait_s, 180)}s in place to let upload complete...")
                time.sleep(min(max_wait_s, 180))
                return True
            status_handle = new_handles[0]
            driver.switch_to.window(status_handle)

            try:
                driver.get(listing_url)
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
                row_text = ""
                rows_found = 0
                try:
                    rows = driver.find_elements(By.TAG_NAME, "ytcp-video-row")
                    rows_found = len(rows)
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
                        row_text = chosen_row.text.lower()
                except Exception:
                    row_text = ""

                if rows_found == 0:
                    page_text = ""
                    try:
                        page_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
                    except Exception:
                        page_text = ""
                    if any(m in page_text for m in studio_error_markers):
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
                            driver.get(listing_url)
                            time.sleep(8)
                            last_refresh = time.time()
                        except Exception as e:
                            warning(f"\t=> Re-navigation failed: {e}")
                        consecutive_empty_polls = 0
                        time.sleep(poll_interval_s)
                        continue

                if row_text:
                    studio_error_retries = 0
                    consecutive_empty_polls = 0

                    if any(m in row_text for m in error_markers):
                        error(
                            f"\t=> {kind_label} upload was INTERRUPTED by YouTube. "
                            "Open the original tab and click 'Reanudar carga / Resume upload' manually."
                        )
                        return False

                    present = [m for m in in_progress_markers if m in row_text]
                    if not present:
                        stable_done_count += 1
                        if stable_done_count >= 2:
                            info(f"\t=> {kind_label} upload + processing finished.")
                            return True
                        info(f"\t=> {kind_label} looks done; confirming with one more poll...")
                    else:
                        stable_done_count = 0
                        if "subiendo" in present or "uploading" in present:
                            current_status = "uploading"
                        elif "procesando" in present or "processing" in present:
                            current_status = "processing"
                        elif ("verificando" in present or "checking" in present
                              or "verificaciones en curso" in present
                              or "checks in progress" in present):
                            current_status = "running checks"
                        else:
                            current_status = "pending"
                        now = time.time()
                        if current_status != last_status or (now - last_announce) > 60:
                            info(f"\t=> {kind_label} status: {current_status} — still waiting (upload tab untouched)...")
                            last_status = current_status
                            last_announce = now
                else:
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
                            driver.get(listing_url)
                            time.sleep(8)
                            last_refresh = time.time()
                        except Exception as e:
                            warning(f"\t=> Re-navigation failed: {e}")
                        consecutive_empty_polls = 0
                        time.sleep(poll_interval_s)
                        continue

                now = time.time()
                if now - last_refresh > refresh_interval_s:
                    try:
                        driver.refresh()
                        time.sleep(5)
                        last_refresh = time.time()
                    except Exception:
                        pass

                time.sleep(poll_interval_s)

            warning(
                f"\t=> Hit total wait cap of {max_wait_s // 60} min for {kind_label}. "
                "Firefox will stay open so YT can keep processing — close it manually when done."
            )
            return False
        finally:
            try:
                if status_handle and status_handle in driver.window_handles:
                    driver.switch_to.window(status_handle)
                    driver.close()
            except Exception:
                pass
            try:
                if original_handle in driver.window_handles:
                    driver.switch_to.window(original_handle)
            except Exception:
                pass

    def _resolve_video_url_safe(self, driver, listing_tab):
        if not getattr(self, "channel_id", None):
            return ""
        listing_url = f"https://studio.youtube.com/channel/{self.channel_id}/videos/{listing_tab}"
        target_title = (self.metadata.get("title") or "").strip()
        target_match = target_title[:50] if target_title else ""

        studio_error_markers = (
            "oops, something went wrong", "something went wrong",
            "algo salió mal", "algo salio mal", "ha ocurrido un error",
            "se produjo un error", "intenta volver a cargar", "try reloading",
            "try again later", "vuelve a intentarlo",
        )

        original_handle = driver.current_window_handle
        status_handle = None
        try:
            existing = set(driver.window_handles)
            driver.execute_script("window.open('about:blank', '_blank');")
            time.sleep(1)
            new_handles = [h for h in driver.window_handles if h not in existing]
            if not new_handles:
                return ""
            status_handle = new_handles[0]
            driver.switch_to.window(status_handle)

            videos = []
            for attempt in range(1, 6):
                try:
                    driver.get(listing_url)
                except Exception as e:
                    warning(f"URL-resolve navigation failed (attempt {attempt}): {e}")
                    time.sleep(3)
                    continue
                time.sleep(4 if attempt == 1 else 6)

                try:
                    videos = driver.find_elements(By.TAG_NAME, "ytcp-video-row")
                except Exception:
                    videos = []

                if videos:
                    break

                page_text = ""
                try:
                    page_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
                except Exception:
                    page_text = ""
                if any(m in page_text for m in studio_error_markers):
                    warning(
                        f"URL-resolve listing showed an error page (attempt {attempt}/5). Retrying..."
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
                    try:
                        chosen_href = row.find_element(By.TAG_NAME, "a").get_attribute("href")
                        break
                    except Exception:
                        continue
            if not chosen_href and videos:
                try:
                    chosen_href = videos[0].find_element(By.TAG_NAME, "a").get_attribute("href")
                except Exception:
                    chosen_href = None

            if chosen_href:
                video_id = chosen_href.split("/")[-2]
                return _build_url(video_id)
            return ""
        except Exception as e:
            warning(f"Could not resolve URL via status tab: {e}")
            return ""
        finally:
            try:
                if status_handle and status_handle in driver.window_handles:
                    driver.switch_to.window(status_handle)
                    driver.close()
            except Exception:
                pass
            try:
                if original_handle in driver.window_handles:
                    driver.switch_to.window(original_handle)
            except Exception:
                pass

    def _verify_thumbnail_uploaded(self, driver):
        try:
            imgs = driver.find_elements(
                By.CSS_SELECTOR,
                "ytcp-thumbnails-compact-editor img, "
                "ytcp-thumbnail-uploader img, "
                "ytcp-thumbnails-compact-editor-uploader img, "
                "ytcp-uploads-still img, "
                "ytcp-thumbnail-card img, "
                "ytcp-thumbnail img"
            )
            for img in imgs:
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
            for selector in (
                "[aria-label*='Cambiar miniatura' i]",
                "[aria-label*='Reemplazar miniatura' i]",
                "[aria-label*='Editar miniatura' i]",
                "[aria-label*='Opciones de miniatura' i]",
                "[aria-label*='Replace thumbnail' i]",
                "[aria-label*='Edit thumbnail' i]",
                "[aria-label*='Thumbnail options' i]",
                "ytcp-thumbnail-card-options",
                "ytcp-thumbnails-compact-editor ytcp-thumbnail-card[selected]",
            ):
                try:
                    if driver.find_elements(By.CSS_SELECTOR, selector):
                        return True
                except Exception:
                    continue
            try:
                upload_ctas = driver.find_elements(
                    By.CSS_SELECTOR,
                    "[aria-label*='Subir miniatura' i], "
                    "[aria-label*='Upload thumbnail' i]"
                )
                visible_cta = any(
                    el.is_displayed() for el in upload_ctas if el is not None
                )
                if upload_ctas and not visible_cta:
                    return True
            except Exception:
                pass
        except Exception:
            pass
        return False

    def _find_thumbnail_input(self, driver, wait):
        time.sleep(2)
        try:
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        except Exception:
            file_inputs = []

        for inp in file_inputs:
            try:
                accept = (inp.get_attribute("accept") or "").lower()
            except Exception:
                accept = ""
            if "image" in accept and "video" not in accept:
                return inp

        for sel in (
            "ytcp-thumbnails-compact-editor input[type='file']",
            "ytcp-thumbnails-compact-editor-uploader input[type='file']",
            "ytcp-thumbnail-uploader input[type='file']",
            "input#file-loader[accept*='image']",
        ):
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el is not None:
                    return el
            except Exception:
                continue
        return None

    def upload_video(self):
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys

        if not getattr(self, "video_path", None) or not str(self.video_path).strip():
            error("Cannot upload: no video was generated (video_path is empty).")
            return False
        if not os.path.isfile(self.video_path):
            error(f"Cannot upload: video file not found at '{self.video_path}'.")
            return False
        if not getattr(self, "subject", None) or not str(self.subject).strip():
            error("Cannot upload: subject is empty (pipeline aborted earlier).")
            return False

        self._ensure_browser()
        driver = self.browser
        verbose = get_verbose()
        wait = WebDriverWait(driver, 30)

        try:
            if verbose:
                info("\t=> Getting channel ID...")
            self.get_channel_id()
            if verbose:
                info(f"\t=> Channel ID: {self.channel_id}")

            if verbose:
                info("\t=> Navigating to upload page...")
            driver.get("https://www.youtube.com/upload")
            time.sleep(3)

            if verbose:
                info(f"\t=> Uploading file: {self.video_path}")

            file_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )
            file_input.send_keys(self.video_path)

            if verbose:
                info("\t=> File selected, waiting for upload dialog...")

            time.sleep(8)

            if verbose:
                info("\t=> Setting title...")

            textboxes = wait.until(
                EC.presence_of_all_elements_located((By.ID, YOUTUBE_TEXTBOX_ID))
            )

            if len(textboxes) < 2:
                warning(f"Expected 2+ textboxes, found {len(textboxes)}")

            title_el = textboxes[0]
            driver.execute_script("arguments[0].scrollIntoView(true);", title_el)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", title_el)
            time.sleep(0.5)

            clean_title = self.metadata["title"].replace("\n", " ")[:100]
            title_el.send_keys(clean_title)
            time.sleep(1)

            if verbose:
                info(f"\t=> Title set: {clean_title}")

            if verbose:
                info("\t=> Setting description...")

            description_el = textboxes[-1]
            driver.execute_script("arguments[0].scrollIntoView(true);", description_el)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", description_el)
            time.sleep(0.5)

            clean_desc = self.metadata["description"].replace("\n", " ")[:5000]
            description_el.send_keys(clean_desc)
            time.sleep(1)

            if verbose:
                info("\t=> Description set")

            if verbose:
                info("\t=> Setting 'not made for kids'...")

            try:
                if not get_is_for_kids():
                    not_for_kids = wait.until(
                        EC.element_to_be_clickable((By.NAME, YOUTUBE_NOT_MADE_FOR_KIDS_NAME))
                    )
                    not_for_kids.click()
                else:
                    for_kids = wait.until(
                        EC.element_to_be_clickable((By.NAME, YOUTUBE_MADE_FOR_KIDS_NAME))
                    )
                    for_kids.click()
                time.sleep(1)
            except Exception as e:
                warning(f"Could not set kids option: {e}")

            thumb_path = getattr(self, "thumbnail_path", "")
            self._thumbnail_uploaded = False
            if thumb_path and os.path.isfile(thumb_path):
                abs_thumb = os.path.abspath(thumb_path)

                YT_THUMB_MAX_BYTES = 2 * 1024 * 1024
                try:
                    fsize = os.path.getsize(abs_thumb)
                except Exception:
                    fsize = 0
                if fsize > YT_THUMB_MAX_BYTES:
                    warning(
                        f"\t=> Thumbnail is {fsize/1024/1024:.2f} MB (>2 MB cap); "
                        "re-encoding as JPEG to fit YouTube's limit."
                    )
                    try:
                        from PIL import Image as _PilImage
                        jpg_path = os.path.splitext(abs_thumb)[0] + "_yt.jpg"
                        with _PilImage.open(abs_thumb) as im:
                            im.convert("RGB").save(jpg_path, "JPEG", quality=90, optimize=True)
                        if os.path.getsize(jpg_path) <= YT_THUMB_MAX_BYTES:
                            abs_thumb = jpg_path
                            info(f"\t=> Re-encoded thumbnail: {abs_thumb} ({os.path.getsize(jpg_path)/1024/1024:.2f} MB)")
                        else:
                            warning(f"\t=> Re-encoded JPEG still over 2 MB; YouTube will likely reject it.")
                    except Exception as e:
                        warning(f"\t=> JPEG re-encode failed: {str(e)[:150]}")

                info(f"\t=> Uploading thumbnail: {abs_thumb}")

                try:
                    editor = driver.find_element(
                        By.CSS_SELECTOR,
                        "ytcp-thumbnails-compact-editor, ytcp-thumbnail-uploader, ytcp-thumbnails-compact-editor-uploader",
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor)
                    time.sleep(1)
                except Exception:
                    pass

                VERIFY_TIMEOUT_S = 180
                VERIFY_POLL_S = 2
                RETRY_BACKOFF_S = 30
                MAX_ATTEMPTS = 3
                accepted = False
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    info(f"\t=> Thumbnail upload attempt {attempt}/{MAX_ATTEMPTS}...")
                    try:
                        thumb_input = self._find_thumbnail_input(driver, wait)
                        if thumb_input is None:
                            raise RuntimeError("no thumbnail file input found on Details page")
                        driver.execute_script(
                            "arguments[0].style.display='block';"
                            "arguments[0].style.visibility='visible';"
                            "arguments[0].style.opacity='1';"
                            "arguments[0].removeAttribute('hidden');",
                            thumb_input,
                        )
                        thumb_input.send_keys(abs_thumb)
                        info(f"\t=> send_keys dispatched; polling up to {VERIFY_TIMEOUT_S}s for preview...")
                    except Exception as e:
                        warning(f"\t=> send_keys failed on attempt {attempt}: {str(e)[:200]}")
                        if attempt < MAX_ATTEMPTS:
                            time.sleep(RETRY_BACKOFF_S)
                        continue

                    deadline = time.time() + VERIFY_TIMEOUT_S
                    while time.time() < deadline:
                        if self._verify_thumbnail_uploaded(driver):
                            accepted = True
                            break
                        time.sleep(VERIFY_POLL_S)

                    if accepted:
                        success(f"\t=> Thumbnail visually confirmed (attempt {attempt}).")
                        time.sleep(5)
                        self._thumbnail_uploaded = True
                        break
                    else:
                        warning(
                            f"\t=> Thumbnail preview NOT detected after {VERIFY_TIMEOUT_S}s on attempt {attempt}."
                        )
                        if attempt < MAX_ATTEMPTS:
                            info(f"\t=> Waiting {RETRY_BACKOFF_S}s before re-trying full upload...")
                            time.sleep(RETRY_BACKOFF_S)

                if not accepted:
                    error(
                        f"Thumbnail upload failed: visual verification never succeeded after {MAX_ATTEMPTS} attempts. "
                        f"The thumbnail file is preserved at:\n    {abs_thumb}\n"
                        "Common causes: channel not verified for custom thumbnails, file > 2 MB, "
                        "or YT Studio DOM changed. Open YouTube Studio → your video → Edit → upload it manually."
                    )
                    try:
                        debug_path = os.path.join(
                            ROOT_DIR, "thumbnails",
                            f"upload_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                        )
                        driver.save_screenshot(debug_path)
                        info(f"\t=> Saved upload-page screenshot for debugging: {debug_path}")
                    except Exception:
                        pass
            elif thumb_path:
                warning(f"\t=> Thumbnail file not found on disk: {thumb_path} (skipping)")

            for step_num in range(3):
                if verbose:
                    info(f"\t=> Clicking Next (step {step_num + 1}/3)...")
                try:
                    next_btn = wait.until(
                        EC.element_to_be_clickable((By.ID, YOUTUBE_NEXT_BUTTON_ID))
                    )
                    next_btn.click()
                    time.sleep(2)
                except Exception as e:
                    warning(f"Next button step {step_num + 1} failed: {e}")

            if verbose:
                info("\t=> Setting visibility to Unlisted...")

            time.sleep(2)
            try:
                radio_buttons = driver.find_elements(By.XPATH, YOUTUBE_RADIO_BUTTON_XPATH)
                if len(radio_buttons) >= 3:
                    radio_buttons[2].click()
                elif len(radio_buttons) >= 2:
                    radio_buttons[1].click()
                time.sleep(1)
            except Exception as e:
                warning(f"Could not set visibility: {e}")

            if verbose:
                info("\t=> Clicking Done button...")

            try:
                done_btn = wait.until(
                    EC.element_to_be_clickable((By.ID, YOUTUBE_DONE_BUTTON_ID))
                )
                done_btn.click()
            except Exception as e:
                warning(f"Done button failed: {e}")

            is_long_video = bool(getattr(self, "_is_long_video", False))

            cache_entry = {
                "title": self.metadata["title"],
                "description": self.metadata["description"],
                "subject": self.subject,
                "url": "uploading...",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "thumbnail_path": getattr(self, "thumbnail_path", "") or "",
            }
            try:
                self.add_video(cache_entry)
                if verbose:
                    info("\t=> Cache entry saved (with placeholder URL)")
            except Exception as e:
                warning(f"Could not pre-save cache entry: {e}")

            if not getattr(self, "channel_id", None):
                try:
                    self.get_channel_id()
                except Exception as e:
                    warning(f"Could not resolve channel_id before upload wait: {e}")

            if is_long_video:
                if verbose:
                    info("\t=> Long video — polling listing page in a separate tab...")
                upload_finished = self._wait_for_listing_settled(
                    driver, listing_tab="upload_video", kind_label="long video",
                    max_wait_s=10800, poll_interval_s=15, refresh_interval_s=120,
                )
            else:
                if verbose:
                    info("\t=> Short video — polling listing page in a separate tab...")
                upload_finished = self._wait_for_listing_settled(
                    driver, listing_tab="short", kind_label="Short",
                    max_wait_s=1800, poll_interval_s=8, refresh_interval_s=60,
                )

            if verbose:
                info("\t=> Getting video URL...")

            listing_tab = "upload_video" if is_long_video else "short"
            url = None

            if is_long_video:
                url = self._resolve_video_url_safe(driver, listing_tab) or None
            else:
                try:
                    driver.get(
                        f"https://studio.youtube.com/channel/{self.channel_id}/videos/{listing_tab}"
                    )
                    time.sleep(3)

                    target_title = (self.metadata.get("title") or "").strip()
                    videos_short = driver.find_elements(By.TAG_NAME, "ytcp-video-row")

                    chosen_href = None
                    for row in videos_short[:15]:
                        try:
                            row_text = row.text.strip()
                        except Exception:
                            row_text = ""
                        if target_title and target_title[:50] in row_text:
                            try:
                                chosen_href = row.find_element(By.TAG_NAME, "a").get_attribute("href")
                                break
                            except Exception:
                                continue

                    if not chosen_href and videos_short:
                        try:
                            chosen_href = videos_short[0].find_element(By.TAG_NAME, "a").get_attribute("href")
                        except Exception:
                            chosen_href = None

                    if chosen_href:
                        if verbose:
                            info(f"\t=> Found URL: {chosen_href}")
                        video_id = chosen_href.split("/")[-2]
                        url = _build_url(video_id)
                except Exception as e:
                    warning(f"Could not get video URL: {e}")

            if url:
                self.uploaded_video_url = url
                success(f" => Uploaded Video: {url}")
                try:
                    self._update_last_video_url(cache_entry["date"], url)
                except Exception as e:
                    warning(f"Could not update cache URL: {e}")
            else:
                self.uploaded_video_url = "https://studio.youtube.com"
                warning(" => Could not retrieve video URL — check YouTube Studio manually. "
                        "Cache entry has placeholder URL.")

            if is_long_video:
                info("=" * 60)
                info(" Long video upload finished. Firefox is staying OPEN.")
                info(" → Verify in YouTube Studio that the video shows as Public/Unlisted")
                info("   (NOT 'Subiendo', 'Procesando' or 'Pendiente').")
                info(" → When you're satisfied, close Firefox manually.")
                info("=" * 60)
            else:
                short_confirmed = bool(upload_finished) and bool(url)
                if short_confirmed:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                else:
                    warning("=" * 60)
                    warning(" Short upload could NOT be fully confirmed. Firefox is staying OPEN.")
                    if not upload_finished:
                        warning(" → Wait-for-upload did not complete cleanly within the timeout.")
                    if not url:
                        warning(" → Could not retrieve the public video URL.")
                    warning(" → Verify in YouTube Studio that the short shows as Public/Unlisted,")
                    warning("   then close Firefox manually.")
                    warning("=" * 60)
            return True

        except Exception as e:
            import traceback
            error(f"Upload failed: {e}")
            traceback.print_exc()
            warning("Leaving Firefox open so the upload can finish in the background. "
                    "Close the browser manually after YouTube Studio shows the upload is done.")
            return False

    def _update_last_video_url(self, date_marker, new_url):
        from cache import get_youtube_cache_path
        import json as _json
        cache = get_youtube_cache_path()
        with open(cache, "r", encoding="utf-8") as f:
            data = _json.load(f)
        for account in data.get("accounts", []):
            if account.get("id") != self._account_uuid:
                continue
            for video in account.get("videos", []):
                if video.get("date") == date_marker and video.get("url") in ("uploading...", "", None):
                    video["url"] = new_url
                    break
        with open(cache, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=4, ensure_ascii=False)
