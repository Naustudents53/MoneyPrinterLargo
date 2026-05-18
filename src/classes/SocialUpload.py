from __future__ import annotations

import os
import re
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from typing import Iterable

from cache import get_youtube_cache_path, json_write_lock
from config import get_firefox_profile_path, get_headless, get_verbose
from status import error, info, success, warning
from .SocialOptimizer import ensure_social_plan

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager


SUPPORTED_UPLOAD_PLATFORMS = ("youtube", "tiktok", "facebook")
PLATFORM_LABELS = {
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "facebook": "Facebook",
}


def normalize_upload_platforms(value: str | Iterable[str] | None) -> list[str]:
    """Return supported upload platforms in the canonical upload order."""
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = re.split(r"[,;\s]+", value.strip())
    else:
        raw_items = [str(item).strip() for item in value]

    aliases = {
        "yt": "youtube",
        "youtube": "youtube",
        "tiktok": "tiktok",
        "tt": "tiktok",
        "facebook": "facebook",
        "fb": "facebook",
    }
    selected: set[str] = set()
    for item in raw_items:
        if not item:
            continue
        platform = aliases.get(item.lower())
        if platform:
            selected.add(platform)

    return [platform for platform in SUPPORTED_UPLOAD_PLATFORMS if platform in selected]


def format_platforms(platforms: Iterable[str]) -> str:
    labels = [PLATFORM_LABELS.get(p, p) for p in platforms]
    if not labels:
        return "ninguna plataforma"
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " y " + labels[-1]


@dataclass
class VideoUploadPayload:
    video_path: str
    title: str
    description: str
    subject: str = ""
    is_long: bool = False
    thumbnail_path: str = ""
    social_plan: dict | None = None

    @property
    def caption(self) -> str:
        text = f"{self.title}\n\n{self.description}".strip()
        return text[:2200]


class SocialUploader:
    """
    Upload a rendered video to one or more destinations.

    YouTube is delegated to the existing YouTube Selenium flow. TikTok and
    Facebook use the same Firefox profile and reuse the generated title +
    description as the post caption. The Firefox profile must already be
    logged in to each selected service.
    """

    def __init__(
        self,
        account_uuid: str = "",
        account_nickname: str = "",
        fp_profile_path: str = "",
        youtube=None,
    ) -> None:
        self.account_uuid = account_uuid
        self.account_nickname = account_nickname
        self.fp_profile_path = (fp_profile_path or "").strip() or get_firefox_profile_path()
        self.youtube = youtube
        self.payload: VideoUploadPayload | None = None
        self.browser: webdriver.Firefox | None = None
        self.wait: WebDriverWait | None = None
        self._temp_profile_dir = ""
        self._keep_browser_open = False

    @classmethod
    def from_youtube(cls, youtube) -> "SocialUploader":
        uploader = cls(
            account_uuid=getattr(youtube, "_account_uuid", "") or "",
            account_nickname=getattr(youtube, "_account_nickname", "") or "",
            fp_profile_path=getattr(youtube, "_fp_profile_path", "") or "",
            youtube=youtube,
        )
        uploader.load_from_youtube(youtube)
        return uploader

    def load_from_youtube(self, youtube) -> VideoUploadPayload:
        metadata = getattr(youtube, "metadata", None) or {}
        payload = VideoUploadPayload(
            video_path=os.path.abspath(getattr(youtube, "video_path", "") or ""),
            title=(metadata.get("title") or "").strip(),
            description=(metadata.get("description") or "").strip(),
            subject=(getattr(youtube, "subject", "") or "").strip(),
            is_long=bool(getattr(youtube, "_is_long_video", False)),
            thumbnail_path=(getattr(youtube, "thumbnail_path", "") or "").strip(),
        )
        self.payload = payload
        return payload

    def upload(self, platforms: str | Iterable[str]) -> dict[str, bool]:
        selected = normalize_upload_platforms(platforms)
        if not selected:
            info(" => No upload platforms selected.")
            return {}

        payload = self._require_payload()
        payload.social_plan = ensure_social_plan(
            video_path=payload.video_path,
            title=payload.title,
            description=payload.description,
            subject=payload.subject,
            niche=getattr(self.youtube, "_niche", "") if self.youtube is not None else "",
            language=getattr(self.youtube, "_language", "") if self.youtube is not None else "",
            platforms=selected,
            is_long=payload.is_long,
            thumbnail_path=payload.thumbnail_path,
            account_uuid=self.account_uuid,
        )
        info(f" => Upload targets: {format_platforms(selected)}")

        results: dict[str, bool] = {}
        youtube_cleanup_was_deferred = False
        youtube_url = None

        try:
            for platform in selected:
                try:
                    if platform == "youtube":
                        if not self.youtube:
                            error("Cannot upload to YouTube: no YouTube uploader instance was provided.")
                            results[platform] = False
                            self._record_platform_result(platform, False)
                            continue

                        # YouTube.upload_video normally marks the manifest as
                        # uploaded and deletes generated assets. If TikTok/Facebook
                        # still need the .mp4, defer that cleanup until this
                        # distribution run finishes.
                        if len(selected) > 1:
                            setattr(self.youtube, "_defer_upload_cleanup", True)
                            youtube_cleanup_was_deferred = True

                        results[platform] = self._upload_youtube()
                        youtube_url = getattr(self.youtube, "uploaded_video_url", None)
                        self._record_platform_result(platform, results[platform], youtube_url)
                        if not results[platform]:
                            warning(" => YouTube upload failed; remaining selected platforms will still be attempted.")
                        continue

                    if platform == "tiktok":
                        results[platform] = self._upload_tiktok(payload)
                        self._record_platform_result(platform, results[platform])
                        continue

                    if platform == "facebook":
                        results[platform] = self._upload_facebook(payload)
                        self._record_platform_result(platform, results[platform])
                        continue
                except Exception as exc:
                    error(f"{PLATFORM_LABELS.get(platform, platform)} upload failed: {type(exc).__name__}: {exc}")
                    results[platform] = False
                    self._record_platform_result(platform, False)
        finally:
            if youtube_cleanup_was_deferred and self.youtube is not None:
                setattr(self.youtube, "_defer_upload_cleanup", False)
            self._close_social_browser()

        if results and all(results.values()):
            self._mark_distribution_complete(youtube_url)

        for platform, ok in results.items():
            label = PLATFORM_LABELS.get(platform, platform)
            if ok:
                success(f" => {label}: upload flow completed.")
            else:
                warning(f" => {label}: upload flow did not complete.")

        return results

    def _require_payload(self) -> VideoUploadPayload:
        if self.payload is None and self.youtube is not None:
            self.load_from_youtube(self.youtube)
        if self.payload is None:
            raise RuntimeError("No video payload configured for SocialUploader.")
        payload = self.payload
        if not payload.video_path or not os.path.isfile(payload.video_path):
            raise RuntimeError(f"Video file not found: {payload.video_path}")
        if not payload.title:
            raise RuntimeError("Missing video title; cannot upload to social platforms.")
        if not payload.description:
            raise RuntimeError("Missing video description; cannot upload to social platforms.")
        return payload

    def _upload_youtube(self) -> bool:
        if self.youtube is None:
            return False
        return bool(self.youtube.upload_video())

    def _upload_tiktok(self, payload: VideoUploadPayload) -> bool:
        info(" => Starting TikTok upload...")
        driver = self._ensure_social_browser()
        wait = self.wait or WebDriverWait(driver, 45)

        driver.get("https://www.tiktok.com/upload")
        self._wait_page_ready(driver)
        self._send_video_to_first_file_input(driver, wait, payload.video_path)
        time.sleep(3)
        self._dismiss_common_dialogs(driver)

        if not self._fill_first_textbox(driver, payload.caption):
            error(
                "TikTok caption field was not found after selecting the video. "
                "Leaving Firefox open instead of marking this upload as completed."
            )
            self._keep_browser_open = True
            return False

        # TikTok can keep the post button disabled until processing finishes.
        if not self._click_button_by_text(
            driver,
            ["Post", "Publicar", "Publicar video", "Post video"],
            timeout=600,
            css_selectors=[
                "button[data-e2e='post_video_button']",
                "button[data-e2e='post_video_submit_button']",
            ],
        ):
            error("Could not click TikTok Post/Publicar button.")
            return False

        return self._wait_for_success_or_idle(
            driver,
            [
                "posted",
                "published",
                "video published",
                "your video has been uploaded",
                "your video has been published",
                "your post has been published",
                "manage your posts",
                "view post",
                "content under review",
                "publicado",
                "se publicó",
                "subido",
            ],
            timeout=600,
            platform="TikTok",
        )

    def _upload_facebook(self, payload: VideoUploadPayload) -> bool:
        info(" => Starting Facebook upload...")
        driver = self._ensure_social_browser()
        wait = self.wait or WebDriverWait(driver, 45)

        urls = [
            "https://www.facebook.com/reels/create",
            "https://www.facebook.com/creatorstudio/upload",
        ]
        file_selected = False
        for url in urls:
            driver.get(url)
            self._wait_page_ready(driver)
            try:
                self._send_video_to_first_file_input(driver, wait, payload.video_path, timeout=20)
                file_selected = True
                break
            except Exception:
                continue

        if not file_selected:
            error("Could not find a Facebook video file input. Open Facebook once in this Firefox profile and confirm you can create reels/videos.")
            return False

        time.sleep(4)
        if not self._fill_first_textbox(driver, payload.caption):
            warning(" => Facebook caption field was not found. The video was selected but metadata may need manual entry.")

        # Facebook often has a two-step composer. Click Next/Siguiente until a
        # publish/share button appears, then submit.
        for _ in range(3):
            if not self._click_button_by_text(
                driver,
                ["Next", "Siguiente", "Continuar"],
                timeout=8,
                require_enabled=True,
            ):
                break
            time.sleep(2)

        if not self._click_button_by_text(
            driver,
            ["Publish", "Post", "Share", "Publicar", "Compartir"],
            timeout=300,
            require_enabled=True,
        ):
            error("Could not click Facebook Publish/Publicar button.")
            return False

        return self._wait_for_success_or_idle(
            driver,
            [
                "published",
                "posted",
                "shared",
                "your reel has been published",
                "publicado",
                "compartido",
            ],
            timeout=180,
            platform="Facebook",
        )

    def _ensure_social_browser(self) -> webdriver.Firefox:
        if self.browser is not None:
            try:
                _ = self.browser.current_url
                return self.browser
            except Exception:
                self._close_social_browser()

        if not self.fp_profile_path or not os.path.isdir(self.fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {self.fp_profile_path}"
            )

        options = Options()
        options.unhandled_prompt_behavior = "accept"
        options.set_preference("dom.disable_beforeunload", True)
        if get_headless():
            warning(" => Headless mode is enabled; TikTok/Facebook may require a visible browser.")
            options.add_argument("--headless")

        self._temp_profile_dir = tempfile.mkdtemp(prefix="mp_social_firefox_")
        temp_profile = os.path.join(self._temp_profile_dir, "profile")
        shutil.copytree(
            self.fp_profile_path,
            temp_profile,
            ignore=shutil.ignore_patterns(
                "lock",
                ".parentlock",
                "parent.lock",
                "cache2",
                "startupCache",
                "shader-cache",
                "thumbnails",
                "crashes",
            ),
            dirs_exist_ok=False,
        )
        for bad_name in ("sessionstore.jsonlz4", "sessionstore-backups"):
            bad_path = os.path.join(temp_profile, bad_name)
            if os.path.isfile(bad_path):
                os.remove(bad_path)
            elif os.path.isdir(bad_path):
                shutil.rmtree(bad_path, ignore_errors=True)

        options.add_argument("-profile")
        options.add_argument(temp_profile)
        options.add_argument("--no-remote")

        info(" => Connecting Firefox for social upload...")
        service = Service(GeckoDriverManager().install())
        self.browser = webdriver.Firefox(service=service, options=options)
        self.wait = WebDriverWait(self.browser, 45)
        success(" => Firefox connected for social upload.")
        return self.browser

    def _close_social_browser(self) -> None:
        if self._keep_browser_open:
            warning(" => Firefox is staying open so you can verify the social upload manually.")
            return
        if self.browser is not None:
            try:
                self.browser.quit()
            except Exception:
                pass
            self.browser = None
            self.wait = None
        if self._temp_profile_dir:
            shutil.rmtree(self._temp_profile_dir, ignore_errors=True)
            self._temp_profile_dir = ""

    def _wait_page_ready(self, driver) -> None:
        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass

    def _send_video_to_first_file_input(self, driver, wait, video_path: str, timeout: int = 45) -> None:
        end = time.time() + timeout
        last_error = None
        while time.time() < end:
            try:
                inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                for file_input in inputs:
                    accept = (file_input.get_attribute("accept") or "").lower()
                    if accept and "image" in accept and "video" not in accept:
                        continue
                    file_input.send_keys(video_path)
                    info(f" => Selected video file: {video_path}")
                    return
            except Exception as exc:
                last_error = exc
            time.sleep(1)
        raise RuntimeError(f"No usable video file input found: {last_error}")

    def _fill_first_textbox(self, driver, text: str) -> bool:
        selectors = [
            "[data-e2e='caption-input'] div[contenteditable='true']",
            "[data-e2e='caption-input'] [role='textbox']",
            "div.public-DraftEditor-content[contenteditable='true']",
            ".public-DraftEditor-content[contenteditable='true']",
            "textarea",
            "div[contenteditable='true']",
            "[role='textbox']",
            "[aria-label*='caption' i]",
            "[aria-label*='description' i]",
            "[aria-label*='descripcion' i]",
            "[aria-label*='descripci' i]",
        ]
        for _ in range(30):
            self._dismiss_common_dialogs(driver)
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                except Exception:
                    elements = []
                for element in elements:
                    try:
                        if not element.is_displayed():
                            continue
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
                        time.sleep(0.2)
                        element.click()
                        self._clear_element(element)
                        element.send_keys(text)
                        if get_verbose():
                            info(" => Filled caption/description field.")
                        return True
                    except Exception:
                        continue
            time.sleep(1)
        return False

    def _dismiss_common_dialogs(self, driver) -> None:
        labels = ["Got it", "Entendido", "Aceptar", "OK", "Okay"]
        try:
            label_xpath = " or ".join(
                [
                    "contains(translate(normalize-space(.), "
                    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
                    f"{label.lower()!r})"
                    for label in labels
                ]
            )
            xpaths = [
                f"//button[{label_xpath}]",
                f"//*[@role='button'][{label_xpath}]",
            ]
            for xpath in xpaths:
                for element in driver.find_elements(By.XPATH, xpath):
                    if self._try_click(driver, element, require_enabled=False):
                        time.sleep(0.5)
                        return
        except Exception:
            pass

    def _clear_element(self, element) -> None:
        try:
            element.clear()
            return
        except Exception:
            pass
        try:
            from selenium.webdriver.common.keys import Keys

            element.send_keys(Keys.CONTROL, "a")
            element.send_keys(Keys.DELETE)
        except Exception:
            pass

    def _click_button_by_text(
        self,
        driver,
        labels: list[str],
        timeout: int = 45,
        css_selectors: list[str] | None = None,
        require_enabled: bool = True,
    ) -> bool:
        css_selectors = css_selectors or []
        label_xpath = " or ".join(
            [
                f"contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), {label.lower()!r})"
                for label in labels
            ]
        )
        xpaths = [
            f"//button[{label_xpath}]",
            f"//*[@role='button'][{label_xpath}]",
            f"//*[self::span or self::div][{label_xpath}]/ancestor::button[1]",
            f"//*[self::span or self::div][{label_xpath}]/ancestor::*[@role='button'][1]",
        ]

        end = time.time() + timeout
        while time.time() < end:
            for selector in css_selectors:
                try:
                    for element in driver.find_elements(By.CSS_SELECTOR, selector):
                        if self._try_click(driver, element, require_enabled=require_enabled):
                            return True
                except Exception:
                    pass
            for xpath in xpaths:
                try:
                    for element in driver.find_elements(By.XPATH, xpath):
                        if self._try_click(driver, element, require_enabled=require_enabled):
                            return True
                except Exception:
                    pass
            time.sleep(1)
        return False

    def _try_click(self, driver, element, require_enabled: bool = True) -> bool:
        try:
            if not element.is_displayed():
                return False
            if require_enabled and not element.is_enabled():
                return False
            aria_disabled = (element.get_attribute("aria-disabled") or "").lower()
            disabled = element.get_attribute("disabled")
            if require_enabled and (aria_disabled == "true" or disabled is not None):
                return False
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            time.sleep(0.2)
            try:
                element.click()
            except Exception:
                driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False

    def _wait_for_success_or_idle(
        self,
        driver,
        markers: list[str],
        timeout: int,
        platform: str,
    ) -> bool:
        end = time.time() + timeout
        markers_l = [m.lower() for m in markers]
        error_markers = [
            "error",
            "failed",
            "try again",
            "no se pudo",
            "intentalo de nuevo",
            "intente de nuevo",
        ]
        while time.time() < end:
            try:
                body = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
            except Exception:
                body = ""
            if any(marker in body for marker in error_markers):
                warning(f" => {platform} page shows an error marker. Please verify the browser.")
                self._keep_browser_open = True
                return False
            if any(marker in body for marker in markers_l):
                return True
            time.sleep(3)

        warning(
            f" => {platform} publish click was submitted, but no final confirmation was detected. "
            "Please verify the opened account manually."
        )
        self._keep_browser_open = True
        return False

    def _mark_distribution_complete(self, url: str | None = None) -> None:
        try:
            from upload_tracker import cleanup_uploaded, mark_distribution_complete

            payload = self._require_payload()
            if mark_distribution_complete(payload.video_path, url):
                removed = cleanup_uploaded()
                if removed:
                    info(f" => Cleaned up {removed} uploaded asset(s) from .mp/")
        except Exception as exc:
            warning(f"Post-upload distribution cleanup skipped: {exc}")

    def _record_platform_result(self, platform: str, ok: bool, url: str | None = None) -> None:
        payload = self.payload
        if payload is None:
            return
        try:
            from upload_tracker import mark_platform_failed, mark_platform_uploaded

            if ok:
                mark_platform_uploaded(payload.video_path, platform, url)
            else:
                mark_platform_failed(payload.video_path, platform, "upload flow failed")
        except Exception as exc:
            warning(f"Could not update manifest platform status for {platform}: {exc}")

        try:
            self._update_sidecar_platform_status(payload.video_path, platform, ok, url)
            self._update_youtube_cache_platform_status(platform, ok, url)
        except Exception as exc:
            warning(f"Could not update social platform status for {platform}: {exc}")

    def _update_sidecar_platform_status(
        self,
        video_path: str,
        platform: str,
        ok: bool,
        url: str | None = None,
    ) -> None:
        sidecar = os.path.splitext(video_path)[0] + ".meta.json"
        try:
            with open(sidecar, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
        platforms = data.setdefault("platform_uploads", {})
        platforms[platform] = {
            "status": "uploaded" if ok else "failed",
            "url": url,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "error": "" if ok else "upload flow failed",
        }
        with open(sidecar, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _update_youtube_cache_platform_status(self, platform: str, ok: bool, url: str | None = None) -> None:
        if not self.account_uuid or self.payload is None:
            return
        cache_path = get_youtube_cache_path()
        if not os.path.isfile(cache_path):
            return
        with json_write_lock(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
            for account in raw.get("accounts", []) or []:
                if account.get("id") != self.account_uuid:
                    continue
                videos = account.get("videos", []) or []
                for video in reversed(videos):
                    if video.get("title") != self.payload.title:
                        continue
                    statuses = video.setdefault("platform_uploads", {})
                    statuses[platform] = {
                        "status": "uploaded" if ok else "failed",
                        "url": url,
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "error": "" if ok else "upload flow failed",
                    }
                    break
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=4)
