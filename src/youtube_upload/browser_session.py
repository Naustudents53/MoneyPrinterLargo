"""
Firefox lifecycle for the YouTube upload pipeline.

Wraps the legacy `_init_selenium` / `_ensure_browser` logic but adds:

- F1.1: deterministic cleanup of the cloned profile (context manager,
  explicit `cleanup()`, atexit safety net) so we stop leaking ~200-500 MB
  of `mpv2_firefox_*` folders in %TEMP% per upload.
- F3.5: geckodriver path is resolved once per process instead of every
  `_ensure_browser()` call.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import threading

from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service
from webdriver_manager.firefox import GeckoDriverManager

from status import error, info, success, warning

from . import upload_config


_GECKODRIVER_LOCK = threading.Lock()
_GECKODRIVER_PATH: str | None = None


def _resolve_geckodriver_path() -> str:
    """Resolve geckodriver once per process and reuse afterward."""
    global _GECKODRIVER_PATH
    with _GECKODRIVER_LOCK:
        if _GECKODRIVER_PATH and os.path.isfile(_GECKODRIVER_PATH):
            return _GECKODRIVER_PATH
        info("    [1/3] Instalando/verificando geckodriver...")
        _GECKODRIVER_PATH = GeckoDriverManager().install()
        info(f"    [2/3] geckodriver listo: {_GECKODRIVER_PATH}")
        return _GECKODRIVER_PATH


class BrowserSession:
    """
    Owns one Firefox driver + one cloned profile dir. Always use either
    via `with BrowserSession(profile_path) as bs:` or remember to call
    `cleanup()` explicitly — otherwise the temp profile leaks.
    """

    def __init__(self, fp_profile_path: str, *, headless: bool, verbose: bool):
        if not os.path.isdir(fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {fp_profile_path}"
            )
        self._fp_profile_path = fp_profile_path
        self._headless = headless
        self._verbose = verbose
        self._temp_profile_dir: str | None = None
        self.driver: webdriver.Firefox | None = None
        self._options: FirefoxOptions | None = None
        self._cleanup_registered = False

        self._build_options()

    # ------- profile preparation -----------------------------------------

    def _build_options(self) -> None:
        opts = FirefoxOptions()
        opts.page_load_strategy = "eager"

        for pref_name, pref_value in (
            ("app.update.enabled", False),
            ("app.update.auto", False),
            ("browser.crashReports.unsubmittedCheck.enabled", False),
            ("toolkit.telemetry.enabled", False),
            ("datareporting.healthreport.uploadEnabled", False),
            ("dom.ipc.processCount", 1),
        ):
            try:
                opts.set_preference(pref_name, pref_value)
            except Exception:
                pass

        if self._headless:
            opts.add_argument("--headless")

        self._temp_profile_dir = tempfile.mkdtemp(prefix="mpv2_firefox_")
        temp_profile = os.path.join(self._temp_profile_dir, "profile")
        if self._verbose:
            info(" => Copying Firefox profile to temp dir...")
        shutil.copytree(
            self._fp_profile_path, temp_profile,
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
                try:
                    os.remove(bad_path)
                except Exception:
                    pass
            elif os.path.isdir(bad_path):
                shutil.rmtree(bad_path, ignore_errors=True)

        opts.add_argument("-profile")
        opts.add_argument(temp_profile)
        self._options = opts

        # Safety net: even if cleanup() is never called, atexit will fire.
        if not self._cleanup_registered:
            atexit.register(self._atexit_cleanup)
            self._cleanup_registered = True

    # ------- lifecycle ----------------------------------------------------

    def ensure_alive(self) -> webdriver.Firefox:
        """Spin up the driver if it doesn't exist or has died. Returns
        the live driver."""
        if self.driver is not None:
            try:
                _ = self.driver.current_url
                return self.driver
            except Exception:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

        info(" => Conectando con Firefox...")
        try:
            driver_path = _resolve_geckodriver_path()
            service = Service(driver_path)
            info("    [3/3] Lanzando Firefox con perfil temporal...")
            assert self._options is not None
            self.driver = webdriver.Firefox(service=service, options=self._options)
            try:
                self.driver.set_page_load_timeout(upload_config.page_load_timeout_s())
                self.driver.set_script_timeout(upload_config.script_timeout_s())
            except Exception:
                pass
            success(" => Firefox conectado.")
            return self.driver
        except Exception as e:
            import traceback as _tb
            error(f"Failed to launch Firefox: {type(e).__name__}: {e}")
            error("Full traceback:")
            error(_tb.format_exc())
            raise

    def cleanup(self) -> None:
        """Quit the driver and delete the cloned profile. Idempotent."""
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

        if self._temp_profile_dir and os.path.isdir(self._temp_profile_dir):
            shutil.rmtree(self._temp_profile_dir, ignore_errors=True)
            self._temp_profile_dir = None

    def _atexit_cleanup(self) -> None:
        # Last-resort cleanup, never raises.
        try:
            if self._temp_profile_dir and os.path.isdir(self._temp_profile_dir):
                shutil.rmtree(self._temp_profile_dir, ignore_errors=True)
        except Exception:
            pass

    # ------- context manager ---------------------------------------------

    def __enter__(self) -> "BrowserSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()
