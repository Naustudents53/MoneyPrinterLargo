import os
import sys
import re
import time
import json
import yagmail
import requests
import subprocess
import io
import csv
import glob
import shlex
import zipfile
import platform

from cache import get_cache_path, get_results_cache_path
from status import info, success, warning, error, question, confirm
from config import ROOT_DIR, get_email_credentials, get_google_maps_scraper_zip_url, get_google_maps_scraper_niche, get_scraper_timeout, get_outreach_message_subject, get_outreach_message_body_file, get_verbose, get_first_time_running, get_nanobanana2_api_key, get_nanobanana2_aspect_ratio, get_threads


class Outreach:
    def __init__(self):
        self.email_credentials = get_email_credentials()
        self.scraper_zip_url = get_google_maps_scraper_zip_url()
        self.niche = get_google_maps_scraper_niche()
        self.scraper_timeout = get_scraper_timeout()
        self._scraper_dir = os.path.abspath(
            os.path.join(ROOT_DIR, "google-maps-scraper-0.9.7")
        )
        self._csv_file = os.path.join(self._scraper_dir, "export.csv")

    def start(self):
        info("Starting Outreach process...")
        self._ensure_scraper_exists()
        self._scrape()
        results = self._read_results()
        if not results:
            warning("No results from the scraper.")
            return
        self._extract_emails(results)
        if confirm("Send emails now?", default=True):
            self._send_emails()
        success("Outreach finished.")

    def _ensure_scraper_exists(self):
        if os.path.isdir(self._scraper_dir):
            info("Scraper already downloaded.")
            return
        info("Downloading Google Maps scraper...")
        resp = requests.get(self.scraper_zip_url, timeout=120)
        resp.raise_for_status()
        zip_path = os.path.join(ROOT_DIR, "scraper.zip")
        with open(zip_path, "wb") as f:
            f.write(resp.content)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(ROOT_DIR)
        os.remove(zip_path)
        success("Scraper downloaded and extracted.")

    def _scrape(self):
        info(f"Running scraper for niche: {self.niche}")
        binary = "google-maps-scraper.exe" if platform.system() == "Windows" else "google-maps-scraper"
        bin_path = os.path.join(self._scraper_dir, binary)
        if not os.path.isfile(bin_path):
            raise RuntimeError(f"Scraper binary not found: {bin_path}")
        cmd = [
            bin_path,
            "-input", shlex.quote(self.niche),
            "-depth", "1",
            "-results", "50",
            "-exit-on-inactivity", str(self.scraper_timeout),
            "-language", "en",
        ]
        info(f"Command: {' '.join(cmd)}")
        subprocess.run(cmd, cwd=self._scraper_dir, timeout=self.scraper_timeout + 120)
        success("Scraping complete.")

    def _read_results(self) -> list:
        if not os.path.isfile(self._csv_file):
            warning(f"No CSV found: {self._csv_file}")
            return []
        with open(self._csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def _extract_emails(self, results: list):
        emails = {}
        for row in results:
            raw = row.get("email") or row.get("email_address") or row.get("Email") or ""
            potentials = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", raw)
            for addr in potentials:
                addr_lower = addr.lower()
                if addr_lower not in emails:
                    emails[addr_lower] = row
        out_path = os.path.join(get_cache_path(), "extracted_emails.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"emails": list(emails.keys()), "count": len(emails)}, f, indent=2)
        success(f"Extracted {len(emails)} unique emails -> {out_path}")
        return emails

    def _send_emails(self):
        subject = get_outreach_message_subject()
        body_file = os.path.join(ROOT_DIR, get_outreach_message_body_file())
        if os.path.isfile(body_file):
            with open(body_file, "r", encoding="utf-8") as f:
                body = f.read()
        else:
            body = "<p>Hello, I have a question about your business.</p>"

        email_path = os.path.join(get_cache_path(), "extracted_emails.json")
        if not os.path.isfile(email_path):
            warning("No extracted emails found.")
            return
        with open(email_path, "r") as f:
            data = json.load(f)
        addresses = data.get("emails", [])

        creds = self.email_credentials
        yag = yagmail.SMTP(creds["username"], creds["password"], creds["smtp_server"], creds["smtp_port"])
        sent = 0
        for addr in addresses:
            try:
                yag.send(to=addr, subject=subject, contents=body)
                sent += 1
                info(f"  Sent to: {addr}")
            except Exception as e:
                warning(f"  Failed for {addr}: {e}")
        success(f"Sent {sent}/{len(addresses)} emails.")
