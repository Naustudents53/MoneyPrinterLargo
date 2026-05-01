import os
from urllib.parse import urlparse
from typing import Any

from status import info, success, warning, error
from config import ROOT_DIR, get_firefox_profile_path, get_headless, get_verbose
from constants import AMAZON_PRODUCT_TITLE_ID, AMAZON_FEATURE_BULLETS_ID
from llm_provider import generate_text
from .Twitter import Twitter
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager


class AffiliateMarketing:
    def __init__(self, affiliate_link: str, fp_profile_path: str, twitter_uuid: str, twitter_nickname: str = "", twitter_topic: str = ""):
        self.affiliate_link = affiliate_link
        self.fp_profile_path = fp_profile_path
        self.twitter_uuid = twitter_uuid
        self.twitter_nickname = twitter_nickname
        self.twitter_topic = twitter_topic
        self._driver = None
        self.pitch = ""

    def _start_driver(self):
        options = Options()
        options.add_argument("-profile")
        options.add_argument(self.fp_profile_path)
        if get_headless():
            options.add_argument("--headless")
        service = Service(GeckoDriverManager().install())
        self._driver = webdriver.Firefox(service=service, options=options)

    def _scrape_product(self):
        driver = self._driver
        parsed = urlparse(self.affiliate_link)
        domain = parsed.netloc.lower()
        if "amazon" not in domain:
            warning(f"URL does not appear to be Amazon: {self.affiliate_link}")
        driver.get(self.affiliate_link)
        info(f"Loaded: {self.affiliate_link}")
        time = __import__("time")
        time.sleep(3)
        title = ""
        try:
            title_el = driver.find_element(By.ID, AMAZON_PRODUCT_TITLE_ID)
            title = title_el.text.strip()
        except Exception as e:
            warning(f"Could not extract product title: {e}")
        features = ""
        try:
            bullets = driver.find_element(By.ID, AMAZON_FEATURE_BULLETS_ID)
            features = bullets.text.strip()
        except Exception as e:
            warning(f"Could not extract features: {e}")
        return title, features

    def generate_pitch(self):
        try:
            self._start_driver()
            title, features = self._scrape_product()
        finally:
            if self._driver:
                try:
                    self._driver.quit()
                except Exception:
                    pass

        if not title:
            error("No product info; aborting pitch.")
            return

        prompt = (
            f"Write a short, engaging affiliate marketing pitch for this product:\n\n"
            f"Title: {title}\n"
            f"Features: {features}\n\n"
            f"Language: Spanish. 2-3 sentences. Direct. No markdown. Only the pitch text."
        )
        self.pitch = generate_text(prompt).strip()
        success(f"Pitch generated: {self.pitch[:120]}")
        return self.pitch

    def share_pitch(self, platform: str):
        if not self.pitch:
            error("No pitch to share.")
            return
        if platform == "twitter":
            twitter = Twitter(self.twitter_uuid, self.twitter_nickname, self.fp_profile_path, self.twitter_topic)
            info("Sharing pitch on Twitter...")
            prompt = f"Post this as a tweet: {self.pitch}. Under 280 chars."
            tweet_text = generate_text(prompt).strip()[:280]
            try:
                twitter._start_driver()
                driver = twitter._driver
                driver.get("https://x.com")
                time_lib = __import__("time")
                time_lib.sleep(3)
                from constants import TWITTER_TEXTAREA_CLASS, TWITTER_POST_BUTTON_XPATH
                textarea = driver.find_element(By.CLASS_NAME, TWITTER_TEXTAREA_CLASS)
                textarea.click()
                textarea.send_keys(tweet_text)
                time_lib.sleep(1)
                post_btn = driver.find_element(By.XPATH, TWITTER_POST_BUTTON_XPATH)
                post_btn.click()
                time_lib.sleep(3)
                success("Pitch shared!")
            except Exception as e:
                error(f"Failed to share pitch: {e}")
            finally:
                if twitter._driver:
                    try:
                        twitter._driver.quit()
                    except Exception:
                        pass
