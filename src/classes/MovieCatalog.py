"""
Catalog of public-domain feature films available on archive.org.

Uses archive.org's public Advanced Search HTTP API directly, so no extra
dependency is required (just `requests`, already a transitive dep).

Public API:
    cat = MovieCatalog()
    if not cat.is_fresh(): cat.refresh()
    cat.entries()                       # all known movies (sorted by popularity)
    cat.search("nosferatu")             # filter by title
    cat.pending(account, query="")      # entries minus those already summarized
    cat.summarized_identifiers(account) # set of archive IDs already done
"""

import json
import os
import time
from typing import List, Optional

import requests

from config import ROOT_DIR
from .ImdbIndex import ImdbIndex

CATALOG_PATH = os.path.join(ROOT_DIR, ".mp", "movie_catalog.json")

# Public-domain feature-film collections on archive.org.
# Deliberately excludes `silent_films` (no audio for Whisper) and
# `classic_cartoons` (mostly non-verbal slapstick) — Movie Summary's whole
# pipeline relies on spoken dialogue to drive the LLM beat extraction, so
# silent / minimal-speech content always fails downstream.
DEFAULT_COLLECTIONS = [
    "feature_films",
    "publicmovies212",
]

# Minimum runtime to keep a catalog entry. Drops trailers, shorts, and
# Popeye-length cartoons that survived the collection filter. archive.org's
# `runtime` field is messy ("[1:08:17]", "[6:00]", "[89 min]", "59:07", "")
# so we parse defensively and KEEP entries whose runtime is unparseable —
# better to show a few junk entries than hide real movies.
MIN_RUNTIME_SECONDS = 50 * 60

# Catalog is auto-refreshed if older than this. Manual refresh always works.
CATALOG_TTL_SECONDS = 7 * 86400

# Per-collection ceiling so a single huge collection can't dominate the file.
MAX_ITEMS_PER_COLLECTION = 2000

# Page size for the paginated browser UI (10 per page, per user spec).
PAGE_SIZE = 10

ADVANCED_SEARCH_URL = "https://archive.org/advancedsearch.php"


def _parse_runtime_seconds(raw: str) -> Optional[int]:
    """Parse archive.org's free-form runtime field. Returns seconds or None.
    Handles formats like '1:08:17', '01:21:31', '59:07', '6:00', '89 min',
    '108 min.', '108 minutes'. Returns None for empty / unrecognizable values."""
    if not raw:
        return None
    import re as _re
    s = str(raw).strip().lower().rstrip(".")
    # H:MM:SS or HH:MM:SS
    m = _re.match(r"^(\d{1,2}):(\d{2}):(\d{2})$", s)
    if m:
        h, mn, sec = map(int, m.groups())
        return h * 3600 + mn * 60 + sec
    # M:SS or MM:SS  (e.g. "59:07", "6:00")
    m = _re.match(r"^(\d{1,3}):(\d{2})$", s)
    if m:
        mn, sec = map(int, m.groups())
        return mn * 60 + sec
    # "89 min" / "108 minutes"
    m = _re.match(r"^(\d{1,3})\s*(min|minutes|m)\b", s)
    if m:
        return int(m.group(1)) * 60
    return None


class MovieCatalog:
    def __init__(self, path: str = CATALOG_PATH):
        self._path = path
        self._data: Optional[dict] = None

    # ---------- persistence ----------

    def _load(self) -> dict:
        if self._data is not None:
            return self._data
        if os.path.isfile(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {"fetched_at": 0, "entries": []}
        else:
            self._data = {"fetched_at": 0, "entries": []}
        return self._data

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # ---------- freshness ----------

    def is_fresh(self) -> bool:
        d = self._load()
        return (
            bool(d.get("entries"))
            and (time.time() - float(d.get("fetched_at", 0))) < CATALOG_TTL_SECONDS
        )

    def fetched_at(self) -> float:
        return float(self._load().get("fetched_at", 0))

    # ---------- refresh ----------

    def refresh(
        self,
        collections: Optional[List[str]] = None,
        max_per_collection: int = MAX_ITEMS_PER_COLLECTION,
        progress_cb=None,
        enrich_with_imdb: bool = True,
    ) -> int:
        """
        Pull every available feature-film entry from archive.org, paginating
        through the Advanced Search API. Returns the total entry count.
        progress_cb (collection_name, fetched_count, total) is called per page.

        When `enrich_with_imdb` is True, each entry gets `imdb_rating` and
        `imdb_votes` (when a match is found), and entries are sorted with
        IMDb-rated titles first.
        """
        cols = collections or DEFAULT_COLLECTIONS
        all_entries: List[dict] = []
        seen_ids: set = set()

        for col in cols:
            page = 1
            rows = 200
            count = 0
            while True:
                params = {
                    "q": f"collection:({col}) AND mediatype:(movies)",
                    "fl[]": [
                        "identifier",
                        "title",
                        "year",
                        "runtime",
                        "downloads",
                        "language",
                    ],
                    "sort[]": ["downloads desc"],
                    "rows": rows,
                    "page": page,
                    "output": "json",
                }
                try:
                    resp = requests.get(ADVANCED_SEARCH_URL, params=params, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    print(f"[Catalog] '{col}' page {page} failed: {e}")
                    break

                docs = (data.get("response") or {}).get("docs") or []
                num_found = (data.get("response") or {}).get("numFound") or 0
                if not docs:
                    break

                for d in docs:
                    ident = (d.get("identifier") or "").strip()
                    if not ident or ident in seen_ids:
                        continue
                    seen_ids.add(ident)
                    raw_title = d.get("title") or ident
                    if isinstance(raw_title, list):
                        title = " ".join(str(t) for t in raw_title).strip() or ident
                    else:
                        title = str(raw_title).strip() or ident
                    year = d.get("year") or ""
                    if isinstance(year, list):
                        year = year[0] if year else ""
                    year = str(year)
                    runtime = d.get("runtime") or ""
                    if isinstance(runtime, list):
                        runtime = runtime[0] if runtime else ""
                    runtime = str(runtime)
                    lang = d.get("language") or ""
                    if isinstance(lang, list):
                        lang = ", ".join(str(x) for x in lang)
                    # Filter shorts/trailers/cartoons by runtime when parseable.
                    # If runtime can't be parsed we KEEP the entry — better to
                    # let a few junk items through than hide real features.
                    rt_seconds = _parse_runtime_seconds(runtime)
                    if rt_seconds is not None and rt_seconds < MIN_RUNTIME_SECONDS:
                        continue
                    all_entries.append(
                        {
                            "identifier": ident,
                            "title": title,
                            "year": year,
                            "runtime": runtime,
                            "runtime_seconds": rt_seconds,
                            "language": str(lang),
                            "collection": col,
                            "downloads": int(d.get("downloads") or 0),
                        }
                    )
                    count += 1
                    if count >= max_per_collection:
                        break

                if progress_cb:
                    try:
                        progress_cb(col, count, num_found)
                    except Exception:
                        pass

                if count >= max_per_collection:
                    break
                if page * rows >= num_found:
                    break
                page += 1

        # Optionally enrich every entry with IMDb rating + vote count.
        # We only do this on refresh (it walks the full list once) so the
        # browser later sorts off cached fields with zero network cost.
        if enrich_with_imdb:
            try:
                imdb = ImdbIndex()
                if not imdb.is_fresh():
                    print("[Catalog] Building IMDb rating index (one-time, ~2-3 min):")
                    imdb.refresh(progress_cb=lambda msg: print(f"   - {msg}"))
                hit_count = 0
                for e in all_entries:
                    hit = imdb.lookup(e.get("title", ""), e.get("year", ""))
                    if hit:
                        e["imdb_rating"] = float(hit.get("rating") or 0)
                        e["imdb_votes"] = int(hit.get("votes") or 0)
                        e["imdb_tconst"] = hit.get("tconst", "")
                        hit_count += 1
                print(f"[Catalog] Matched {hit_count}/{len(all_entries)} entries with IMDb")
            except Exception as e:
                # Never fail the catalog refresh because of IMDb hiccups.
                print(f"[Catalog] IMDb enrichment failed: {e}")

        # Sort: rated entries first (rating desc, then votes desc),
        # unrated entries afterwards by archive.org download count.
        def _sort_key(entry):
            r = entry.get("imdb_rating")
            v = int(entry.get("imdb_votes") or 0)
            d = int(entry.get("downloads") or 0)
            if r is None:
                return (1, 0, 0, -d)  # bucket 1: unrated
            return (0, -float(r), -v, -d)  # bucket 0: rated

        all_entries.sort(key=_sort_key)

        self._data = {"fetched_at": time.time(), "entries": all_entries}
        self._save()
        return len(all_entries)

    # ---------- read ----------

    def entries(self) -> List[dict]:
        return list(self._load().get("entries", []))

    def search(self, query: str) -> List[dict]:
        q = (query or "").strip().lower()
        if not q:
            return self.entries()
        return [e for e in self.entries() if q in e["title"].lower()]

    @staticmethod
    def summarized_identifiers(account: dict) -> set:
        out = set()
        for v in account.get("summarized_movies", []) or []:
            ident = (v.get("identifier") or "").strip()
            if ident:
                out.add(ident)
        return out

    def pending(self, account: dict, query: str = "") -> List[dict]:
        done = self.summarized_identifiers(account)
        return [e for e in self.search(query) if e["identifier"] not in done]

    # ---------- pagination helper ----------

    @staticmethod
    def paginate(items: List[dict], page: int, page_size: int = PAGE_SIZE) -> List[dict]:
        if page < 1:
            page = 1
        start = (page - 1) * page_size
        return items[start : start + page_size]

    @staticmethod
    def total_pages(items: List[dict], page_size: int = PAGE_SIZE) -> int:
        if not items:
            return 1
        return (len(items) + page_size - 1) // page_size
