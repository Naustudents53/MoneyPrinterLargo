import re
import sys
import time
import os
import json

from cache import get_accounts, add_account, remove_account, get_cache_path
from config import ROOT_DIR, get_firefox_profile_path, get_headless, get_verbose, get_twitter_language
from status import info, success, warning, error
from llm_provider import generate_text
from typing import List, Optional
from datetime import datetime
from termcolor import colored
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service
from webdriver_manager.firefox import GeckoDriverManager
from constants import TWITTER_TEXTAREA_CLASS, TWITTER_POST_BUTTON_XPATH


class Twitter:
    def __init__(self, account_uuid: str, account_nickname: str, fp_profile_path: str, topic: str):
        self._account_uuid = account_uuid
        self._account_nickname = account_nickname
        self._fp_profile_path = fp_profile_path
        self._topic = topic
        self.browser = None
        self._driver = None

    def _start_driver(self):
        options = FirefoxOptions()
        options.add_argument("-profile")
        options.add_argument(self._fp_profile_path)
        if get_headless():
            options.add_argument("--headless")
        service = Service(GeckoDriverManager().install())
        self._driver = webdriver.Firefox(service=service, options=options)

    def post(self):
        try:
            self._start_driver()
            driver = self._driver
            driver.get("https://x.com")
            time.sleep(3)

            lang = get_twitter_language()
            topic = self._topic
            prompt = f"Write a short, engaging tweet about: {topic}. Language: {lang}. Under 280 chars. Only the tweet text."
            tweet_text = generate_text(prompt)
            tweet_text = tweet_text.strip()[:280]

            textarea = driver.find_element(By.CLASS_NAME, TWITTER_TEXTAREA_CLASS)
            textarea.click()
            textarea.send_keys(tweet_text)
            time.sleep(1)

            post_btn = driver.find_element(By.XPATH, TWITTER_POST_BUTTON_XPATH)
            post_btn.click()
            time.sleep(3)

            accounts = get_accounts("twitter")
            for acc in accounts:
                if acc["id"] == self._account_uuid:
                    posts = acc.setdefault("posts", [])
                    posts.append({
                        "content": tweet_text,
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    remove_account("twitter", self._account_uuid)
                    add_account("twitter", acc)
                    break

            success("Tweet posted!")
            return True
        except Exception as e:
            error(f"Post failed: {e}")
            return False
        finally:
            if self._driver:
                try:
                    self._driver.quit()
                except Exception:
                    pass

    def get_posts(self) -> list:
        accounts = get_accounts("twitter")
        for acc in accounts:
            if acc["id"] == self._account_uuid:
                return acc.get("posts", [])
        return []
