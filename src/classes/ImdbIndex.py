"""
Local IMDb rating index, built from IMDb's free non-commercial datasets.

Downloads `title.ratings.tsv.gz` (~7 MB) and `title.basics.tsv.gz` (~190 MB)
from https://datasets.imdbws.com/, filters to feature films, joins on tconst,
and stores a compact JSON map of `(normalized_title, year) -> {rating, votes}`
in `.mp/imdb_index.json`.

Public API:
    idx = ImdbIndex()
    if not idx.is_fresh(): idx.refresh()
    hit = idx.lookup("Nosferatu", "1922")    # -> {"rating": 7.9, "votes": 117432}
"""

import gzip
import io
import json
import os
import re
import time
from typing import Optional

import requests

from config import ROOT_DIR

INDEX_PATH = os.path.join(ROOT_DIR, ".mp", "imdb_index.json")

# Refresh once a month; IMDb dumps update daily but our use-case is stable.
TTL_SECONDS = 30 * 86400

RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
BASICS_URL = "https://datasets.imdbws.com/title.basics.tsv.gz"

# Don't index niche titles — keep the file small and matches more confident.
MIN_VOTES = 50

_NORMALIZE_REMOVE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_ARTICLES = {"the", "a", "an", "el", "la", "los", "las", "un", "una", "le", "les", "il", "lo", "de", "du"}


def _norm_title(s: str) -> str:
    """Lowercase, strip parens/subtitles/punctuation/articles. Used on both sides
    of the lookup so 'The Kid (1921)' matches 'kid'."""
    if not s:
        return ""
    s = str(s).lower()
    # Strip anything in parentheses or square brackets
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    # Cut off subtitle after the first ':' or ' - '
    s = re.split(r"[:–—]| - ", s, maxsplit=1)[0]
    # Drop punctuation
    s = _NORMALIZE_REMOVE.sub(" ", s)
    # Drop articles
    tokens = [t for t in s.split() if t and t not in _ARTICLES]
    return " ".join(tokens).strip()


def _norm_year(y) -> str:
    """Extract a 4-digit year from any string/list. '' if none."""
    if isinstance(y, list):
        y = y[0] if y else ""
    m = re.search(r"\b(19|20)\d{2}\b", str(y or ""))
    return m.group(0) if m else ""


class ImdbIndex:
    def __init__(self, path: str = INDEX_PATH):
        self._path = path
        self._by_year: Optional[dict] = None  # {"normtitle|1922": {...}}
        self._by_title: Optional[dict] = None  # {"normtitle": [{...}]}

    # ---------- freshness ----------

    def is_fresh(self) -> bool:
        return (
            os.path.isfile(self._path)
            and (time.time() - os.path.getmtime(self._path)) < TTL_SECONDS
        )

    # ---------- load ----------

    def _load(self) -> None:
        if self._by_year is not None:
            return
        if not os.path.isfile(self._path):
            self._by_year, self._by_title = {}, {}
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._by_year = data.get("by_year", {})
            self._by_title = data.get("by_title", {})
        except Exception:
            self._by_year, self._by_title = {}, {}

    def lookup(self, title: str, year: str = "") -> Optional[dict]:
        """Returns {'rating': float, 'votes': int, 'tconst': str} or None."""
        self._load()
        nt = _norm_title(title)
        if not nt:
            return None
        ny = _norm_year(year)

        # Strict: title + year
        if ny:
            hit = self._by_year.get(f"{nt}|{ny}")
            if hit:
                return hit

        # Fallback: same title, ignore year — pick the most-voted version
        candidates = self._by_title.get(nt)
        if not candidates:
            return None
        best = max(candidates, key=lambda c: c.get("votes", 0))
        return best

    # ---------- refresh ----------

    def refresh(self, progress_cb=None) -> int:
        """Build the index from IMDb's public dumps. Returns total entry count."""

        def _say(msg: str):
            if progress_cb:
                try:
                    progress_cb(msg)
                except Exception:
                    pass

        # Step 1: ratings (small, ~7 MB compressed)
        _say("downloading IMDb ratings (~7 MB)...")
        r = requests.get(RATINGS_URL, timeout=180)
        r.raise_for_status()
        ratings: dict = {}
        with gzip.open(io.BytesIO(r.content), "rt", encoding="utf-8") as f:
            next(f, None)  # header
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                tconst, avg, votes = parts[0], parts[1], parts[2]
                try:
                    rating = float(avg)
                    nvotes = int(votes)
                except ValueError:
                    continue
                if nvotes < MIN_VOTES:
                    continue
                ratings[tconst] = (rating, nvotes)
        _say(f"loaded {len(ratings):,} rated titles (votes >= {MIN_VOTES})")

        # Step 2: basics (large, ~190 MB compressed). Stream-decompress and
        # only keep movies whose tconst is in the ratings dict — that bounds
        # the working set to the size of `ratings`.
        _say("downloading IMDb basics (~190 MB, this is the slow part)...")
        r = requests.get(BASICS_URL, timeout=600)
        r.raise_for_status()
        by_year: dict = {}
        by_title: dict = {}
        scanned = 0
        kept = 0
        with gzip.open(io.BytesIO(r.content), "rt", encoding="utf-8") as f:
            header = next(f, "").rstrip("\n").split("\t")
            # Defensive: locate columns by name (IMDb has been stable but just in case)
            try:
                i_tconst = header.index("tconst")
                i_type = header.index("titleType")
                i_primary = header.index("primaryTitle")
                i_orig = header.index("originalTitle")
                i_year = header.index("startYear")
            except ValueError:
                i_tconst, i_type, i_primary, i_orig = 0, 1, 2, 3
                i_year = 5

            for line in f:
                scanned += 1
                if scanned % 200_000 == 0:
                    _say(f"scanned {scanned:,} basics rows, kept {kept:,}")
                parts = line.rstrip("\n").split("\t")
                if len(parts) <= i_year:
                    continue
                if parts[i_type] != "movie":
                    continue
                tconst = parts[i_tconst]
                rated = ratings.get(tconst)
                if rated is None:
                    continue
                rating, votes = rated
                year_raw = parts[i_year]
                year = "" if year_raw == r"\N" else year_raw
                primary = parts[i_primary]
                original = parts[i_orig]

                entry = {
                    "rating": rating,
                    "votes": votes,
                    "tconst": tconst,
                    "year": year,
                }

                for raw in {primary, original}:
                    nt = _norm_title(raw)
                    if not nt:
                        continue
                    if year:
                        by_year[f"{nt}|{year}"] = entry
                    by_title.setdefault(nt, []).append(entry)
                kept += 1

        _say(f"indexed {kept:,} rated movies (from {scanned:,} basics rows)")

        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({"by_year": by_year, "by_title": by_title}, f, ensure_ascii=False)

        # Reset in-memory cache so subsequent lookups read the new file
        self._by_year = by_year
        self._by_title = by_title
        return kept
