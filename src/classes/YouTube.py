import re
import base64
import json
import time
import os
import requests
import assemblyai as aai

from utils import *
from cache import *
from .Tts import TTS
from llm_provider import generate_text
from config import *
from status import *
from uuid import uuid4
from constants import *
from typing import List
from moviepy.editor import *
from termcolor import colored
from selenium import webdriver
from moviepy.video.fx.all import crop
from moviepy.config import change_settings
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from moviepy.video.tools.subtitles import SubtitlesClip
from webdriver_manager.firefox import GeckoDriverManager
from datetime import datetime

# Set ImageMagick Path
change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})


_PHOTO_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for", "with",
    "about", "from", "by", "is", "was", "were", "are", "be", "been", "being",
    "his", "her", "its", "their", "our", "your", "this", "that", "these", "those",
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "u",
    "sobre", "con", "por", "para", "es", "era", "fue", "su", "sus", "del",
}


# Generic historical/topic words that are NOT distinctive enough to anchor a
# search result on the right subject. A result whose title only matches these
# is considered off-topic — e.g. a video about Nero must NOT accept any photo
# whose only overlap is "roman" or "emperor". The relevance filter requires
# at least one truly distinctive token (proper noun / unique term) on top of
# these. Keep this list conservative — adding a real proper noun here would
# silently disable relevance checks for that subject.
_GENERIC_TOPIC_TOKENS = {
    # Eras / civilizations / generic adjectives
    "ancient", "antiguo", "antigua", "antiguos", "antiguas",
    "old", "viejo", "vieja", "modern", "moderno", "moderna",
    "history", "historia", "historical", "historic", "historico", "historica",
    "story", "tale", "cuento", "relato",
    "civilization", "civilizacion", "culture", "cultura", "era", "epoca", "period", "periodo",
    # Civilizations / nationalities (won't disambiguate one figure from another)
    "roman", "romano", "romana", "romanos", "romanas",
    "greek", "griego", "griega", "griegos", "griegas",
    "egyptian", "egipcio", "egipcia", "egipcios", "egipcias",
    "chinese", "chino", "china", "chinos", "chinas",
    "japanese", "japones", "japonesa", "japoneses", "japonesas",
    "indian", "indio", "india", "indios", "indias",
    "european", "europeo", "europea", "asian", "asiatico", "asiatica",
    "african", "africano", "africana", "american", "americano", "americana",
    # Common roles
    "emperor", "emperador", "emperatriz", "empress",
    "king", "rey", "queen", "reina",
    "prince", "principe", "princess", "princesa",
    "soldier", "soldado", "warrior", "guerrero", "guerrera",
    "priest", "sacerdote", "priestess", "sacerdotisa",
    "people", "gente", "person", "persona", "man", "hombre", "woman", "mujer",
    # Generic places / objects
    "city", "ciudad", "town", "village", "pueblo", "place", "lugar",
    "world", "mundo", "earth", "tierra", "land", "country", "pais",
    "war", "guerra", "battle", "batalla", "fight", "combate",
    "great", "grande", "famous", "famoso", "famosa", "important", "importante",
    "life", "vida", "death", "muerte",
    "scene", "escena", "view", "vista", "image", "imagen", "photo", "foto",
    "art", "arte", "painting", "pintura", "statue", "estatua",
}


# Per-channel hook style presets used by `generate_script`. Each entry is
# (style_name, hook_example). One style is picked at random per script so
# every short doesn't open the same way. Configure on the account JSON via
# `hook_profile` — falls back to "educational" if missing or unknown.
HOOK_PROFILES: dict = {
    "educational": [
        ("Classic curiosity question", '"¿Sabías que...?"'),
        ("Invitation to imagine a scene", '"Imagínate esto:" o "Imagina que..."'),
        ("Direct shocking statistic (no question)", '"El 90% de la gente no sabe que..."'),
        ("Hidden secret reveal", '"Hay algo que nadie te contó sobre..."'),
        ("Counterintuitive claim", '"Todo lo que crees sobre X está mal."'),
        ("Negation cliffhanger", '"No vas a creer lo que pasó cuando..."'),
        ("Time-warp opener", '"Hace dos mil años, en [lugar], [escena breve]..." o "En [siglo o año], [lugar] vivía un día como cualquier otro, hasta que..."'),
        ("Stakes-first pivotal moment", '"Una sola idea, una sola decisión o una sola noche cambió el rumbo de [civilización, era o pueblo]."'),
        ("Cultural lens flip", '"Para nosotros sería [reacción moderna: impensable, una locura, un crimen], pero en [época o civilización] era [normalidad opuesta: lo más natural, una virtud, lo esperado]."'),
        ("Hidden origin reveal", '"Lo que hoy conocemos como [cosa familiar] empezó con algo que casi nadie recuerda: [origen olvidado]."'),
    ],
    # Animated storytelling: epic, horror, mystery, adventure. Hooks designed
    # to be addictive and pull the viewer into the scene immediately.
    "storytelling": [
        ("Dark mystery opener", '"Lo que voy a contarte nadie quiso creerlo." o "Esta historia jamás debió salir a la luz."'),
        ("In medias res scene-set", '"Eran las 3:00 AM cuando la puerta se abrió sola." o "Aquella noche, el silencio era distinto."'),
        ("Time-warp opener", '"Era 1987, y todo cambió esa noche." o "Pasaron veinte años antes de que apareciera el cuerpo."'),
        ("Sole-survivor cliffhanger", '"De los doce que entraron, solo uno regresó. Y este es su relato."'),
        ("Disturbing discovery", '"Lo que encontraron debajo no debía existir." o "Cuando abrieron la caja, ya era tarde."'),
        ("Visceral horror imperative", '"No mires atrás. Eso fue lo último que escuchó antes de..." o "Nunca debió haber bajado a ese sótano."'),
        ("Lost-civilization epic", '"Un imperio entero desapareció en una sola noche, y nadie sabe por qué."'),
        ("Adventure quest twist", '"Buscaban un tesoro perdido. Lo que hallaron fue mucho peor."'),
        ("Forbidden tale", '"Esta historia se contaba en susurros, y los que la conocían solían desaparecer."'),
        ("Last words testimony", '"Las últimas palabras que escribió antes de desaparecer fueron estas..."'),
    ],
}


# Visual context anchoring is now niche-agnostic and computed per-video by
# `_get_context_profile()` — see that method. The LLM is asked once per video
# to derive a setting + visual anchors + things-to-avoid brief from the
# channel niche + topic + script, and that brief is injected into image-prompt
# generation. This replaces the previous hardcoded CIVILIZATIONS dict, which
# only covered ~17 historical eras and pushed every channel toward
# civilization-flavored content. The new approach works for any niche
# (history, science, finance, sports, food, tech, modern stories, etc.).


class YouTube:
    """
    Class for YouTube Automation.

    Steps to create a YouTube Short:
    1. Generate a topic [DONE]
    2. Generate a script [DONE]
    3. Generate metadata (Title, Description, Tags) [DONE]
    4. Generate AI Image Prompts [DONE]
    4. Generate Images based on generated Prompts [DONE]
    5. Convert Text-to-Speech [DONE]
    6. Show images each for n seconds, n: Duration of TTS / Amount of images [DONE]
    7. Combine Concatenated Images with the Text-to-Speech [DONE]
    """

    def __init__(
        self,
        account_uuid: str,
        account_nickname: str,
        fp_profile_path: str,
        niche: str,
        language: str,
        image_style: str = "",
        short_voice: str = "",
        long_voice: str = "",
        hook_profile: str = "",
        voice_drama: bool = False,
    ) -> None:
        """
        Constructor for YouTube Class.

        Args:
            account_uuid (str): The unique identifier for the YouTube account.
            account_nickname (str): The nickname for the YouTube account.
            fp_profile_path (str): Path to the firefox profile that is logged into the specificed YouTube Account.
            niche (str): The niche of the provided YouTube Channel.
            language (str): The language of the Automation.
            image_style (str): Optional per-channel style suffix appended to AI image prompts.
            short_voice (str): Optional Edge-TTS voice ID (or alias) for shorts narration.
            long_voice (str): Optional Edge-TTS voice ID (or alias) for long-video narration.
            hook_profile (str): Optional hook profile name (see HOOK_PROFILES). Falls back to "educational".

        Returns:
            None
        """
        self._account_uuid: str = account_uuid
        self._account_nickname: str = account_nickname
        self._fp_profile_path: str = fp_profile_path
        self._niche: str = niche
        self._language: str = language
        self._image_style: str = (image_style or "").strip()
        self._short_voice: str = (short_voice or "").strip()
        self._long_voice: str = (long_voice or "").strip()
        self._hook_profile: str = (hook_profile or "").strip().lower()
        self._voice_drama: bool = bool(voice_drama)

        self.images = []
        self._used_stock_urls: set = set()
        self.word_timestamps = None
        self.thumbnail_path: str = ""
        self.active_series: dict = None

        # Initialize the Firefox profile
        self.options: Options = Options()

        # Set headless state of browser
        if get_headless():
            self.options.add_argument("--headless")

        if not os.path.isdir(self._fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {self._fp_profile_path}"
            )

        # Copy the profile so we can use it even if Firefox is open.
        # We must preserve cookies, logins, and session data for YouTube.
        import shutil
        import tempfile
        self._temp_profile_dir = tempfile.mkdtemp(prefix="mpv2_firefox_")
        temp_profile = os.path.join(self._temp_profile_dir, "profile")
        if get_verbose():
            info(f" => Copying Firefox profile to temp dir...")
        # Exclude lock files and large caches that cause conflicts,
        # but KEEP cookies.sqlite, logins.json, key4.db, etc.
        shutil.copytree(
            self._fp_profile_path, temp_profile,
            ignore=shutil.ignore_patterns(
                "lock", ".parentlock", "parent.lock",
                "cache2", "startupCache", "shader-cache",
                "thumbnails", "storage", "crashes",
            ),
            dirs_exist_ok=False,
        )
        # Remove the session restore files that can cause crashes
        for bad_file in ["sessionstore.jsonlz4", "sessionstore-backups"]:
            bad_path = os.path.join(temp_profile, bad_file)
            if os.path.isfile(bad_path):
                os.remove(bad_path)
            elif os.path.isdir(bad_path):
                shutil.rmtree(bad_path, ignore_errors=True)

        self.options.add_argument("-profile")
        self.options.add_argument(temp_profile)

        # Browser is initialized lazily just before upload (see _ensure_browser)
        self.browser: webdriver.Firefox = None

    @property
    def niche(self) -> str:
        """
        Getter Method for the niche.

        Returns:
            niche (str): The niche
        """
        return self._niche

    @property
    def language(self) -> str:
        """
        Getter Method for the language to use.

        Returns:
            language (str): The language
        """
        return self._language

    def generate_response(self, prompt: str, model_name: str = None) -> str:
        """
        Generates an LLM Response based on a prompt and the user-provided model.

        Args:
            prompt (str): The prompt to use in the text generation.

        Returns:
            response (str): The generated AI Repsonse.
        """
        return generate_text(prompt, model_name=model_name)

    def generate_topic(self) -> str:
        """
        Generates a topic based on the YouTube Channel niche.
        Channel-lifetime duplicate guard: if the LLM cannot produce a topic
        that does not collide with any previously uploaded video, this method
        returns "" (the caller must then abort — we NEVER knowingly publish a
        repeat).

        Detection layers, in order of strictness:
          1. markdown/prefix cleanup (LLMs love wrapping in ** or "Topic:")
          2. language guard (reject English when channel language is Spanish)
          3. shared distinctive-entity match (e.g. "Hammurabi", "Cosimo I",
             "Vasari" appearing in both candidate and a past topic → duplicate,
             regardless of surrounding words)
          4. token-overlap and sequence-similarity fallbacks

        Returns:
            topic (str): The generated topic, or "" if all attempts collided.
        """
        import random
        import unicodedata
        from difflib import SequenceMatcher

        # ---- 1. Collect full channel history ----
        past_topics: List[str] = []
        try:
            videos = self.get_videos()
            for v in videos:
                for key in ("subject", "title"):
                    val = v.get(key)
                    if val and isinstance(val, str):
                        past_topics.append(val.strip())
        except Exception:
            pass

        # ---- 2. Vocab ----
        ES_STOP = {
            "el", "la", "los", "las", "de", "del", "que", "y", "en", "un", "una",
            "por", "para", "con", "se", "su", "sus", "lo", "al", "como", "es",
            "fue", "era", "ser", "son", "mas", "este", "esta", "esto", "estos",
            "estas", "sobre", "entre", "pero", "si", "no", "ni", "cuando",
            "donde", "quien", "que", "como", "cual", "cuales", "hacia", "desde",
            "hasta", "sin", "ya", "muy", "mas", "menos", "todo", "toda", "todos",
            "todas", "otro", "otra", "otros", "otras", "tambien", "solo", "solo",
            "tras", "ante", "bajo",
        }
        EN_STOP = {
            "the", "of", "a", "an", "and", "is", "was", "to", "in", "on", "who",
            "why", "how", "what", "were", "are", "be", "been", "have", "has",
            "had", "with", "from", "that", "this", "these", "those", "will",
            "would", "can", "could", "should", "about", "into", "which", "where",
            "when", "their", "its", "it", "by", "at", "as", "or", "but", "for",
        }
        STOP = ES_STOP | EN_STOP

        def _strip_diacritics(s: str) -> str:
            return "".join(
                c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
            )

        def _strip_markdown(s: str) -> str:
            """Remove markdown scaffolding, hashtags, and common LLM prefixes."""
            if not s:
                return ""
            # Code blocks
            s = re.sub(r"```[\s\S]*?```", " ", s)
            s = re.sub(r"`+", "", s)
            # Hashtags (#Foo, #HistoriaAntigua) — they'd otherwise be captured
            # as distinctive entities, but every historical-channel video
            # shares the same pool of tags so they collide spuriously.
            s = re.sub(r"#\w+", " ", s, flags=re.UNICODE)
            # Bold/italic/headers
            s = re.sub(r"[*_#]+", "", s)
            # Leading "Topic:", "Tema:", "Title:", "Titulo:"
            s = re.sub(r"^\s*(?:topic|tema|title|t[ií]tulo)\s*:\s*", "", s, flags=re.I)
            # Collapse whitespace
            s = re.sub(r"\s+", " ", s).strip()
            # Strip enclosing quotes (regular, curly, guillemets)
            s = s.strip(" \t\"'“”‘’«»").strip()
            return s

        def _normalize(s: str) -> str:
            """Lowercase, strip diacritics & punctuation, drop stopwords."""
            s = _strip_diacritics(s.lower())
            s = re.sub(r"[^\w\s]", " ", s)
            tokens = [t for t in s.split() if t and t not in STOP and len(t) > 1]
            return " ".join(tokens)

        # Common first-word capitalizations that shouldn't count as entities
        SENTENCE_STARTERS = {
            "el", "la", "los", "las", "un", "una", "the", "a", "an", "cuando",
            "como", "donde", "por", "que", "cual", "hay", "esta", "este", "ese",
            "esa", "aquel",
        }

        # Capitalized words that are common nouns/adjectives or broad
        # region/era labels — too generic to count as a distinctive signature
        # (otherwise any two videos set in Rome would share "emperador" or
        # "roma" and get flagged as duplicates).
        COMMON_CAP_NOISE = {
            # Generic nouns/adjectives often capitalized
            "antigua", "antiguo", "antiguos", "antiguas", "historia", "historico",
            "historica", "mundo", "dios", "dioses", "rey", "reina", "emperador",
            "faraon", "sabio", "filosofo", "filosofos", "filosofia", "legado",
            "misterio", "misterios", "secreto", "secretos", "enigma", "leyenda",
            "epoca", "siglo", "era", "anyo", "ano", "anos", "imperio", "reino",
            "templo", "ciudad", "ciudades", "conquista", "batalla", "guerra",
            "muerte", "vida", "revolucion", "civilizacion", "civilizaciones",
            "new", "ancient", "great", "lost", "hidden", "secret", "mysterious",
            "age", "bronze", "iron", "stone", "city", "cities", "temple",
            "empire", "kingdom", "dynasty", "war", "battle",
            # Broad regions/eras used constantly in historical content
            "roma", "grecia", "egipto", "china", "persia", "mesopotamia",
            "babilonia", "india", "japon", "europa", "asia", "africa", "america",
            "italia", "espanya", "francia", "inglaterra", "alemania", "turquia",
            "atenas", "esparta", "alejandria", "constantinopla", "oriente",
            "occidente", "mediterraneo", "nilo", "tigris", "eufrates",
            "renacimiento", "medieval", "barroco", "ilustracion",
        }

        def _extract_entities(original: str) -> set:
            """
            Distinctive signature tokens: proper nouns (capitalized mid-sentence),
            roman numerals, and 4-digit years. Lowercased + diacritics stripped
            so "Hammurabi" == "hammurabi" == "HAMMURABI".

            Deliberately excludes generic capitalized words ("Antigua", "Emperador")
            and long common nouns — those create false-positive collisions across
            unrelated topics (e.g. any two videos set in Rome would share
            "emperador"). A distinctive entity is a *named thing*: a person
            (Hammurabi, Séneca), place (Pelusio, Medina), object or event
            (Pelusio, Antikythera, Tzolk'in).
            """
            text = _strip_markdown(original)
            ents: set = set()
            raw = re.findall(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü0-9']+", text)
            for i, tok in enumerate(raw):
                norm = _strip_diacritics(tok.lower())
                # Skip pure numbers (including years): a shared year between
                # two unrelated events is not a signature — e.g. "hallazgo en
                # 2024" and "desaparición en 2024" are different topics.
                if re.fullmatch(r"\d+", tok):
                    continue
                # Roman numerals length >= 2 (II, III, IV, VI, VIII, XII) —
                # single "I" is too ambiguous to treat as a signature on its
                # own (and pairs with a named person next to it anyway).
                if re.fullmatch(r"[IVXLCDM]{2,}", tok):
                    ents.add(norm)
                    continue
                # Capitalized, not sentence-initial, not an ALL-CAPS acronym,
                # not a known common/generic capitalized word.
                if (
                    tok[0].isupper()
                    and i > 0
                    and norm not in STOP
                    and norm not in SENTENCE_STARTERS
                    and norm not in COMMON_CAP_NOISE
                    and len(tok) >= 3
                    and not tok.isupper()
                ):
                    ents.add(norm)
            return ents

        def _looks_english(s: str) -> bool:
            """Heuristic: reject obvious English when the channel is Spanish."""
            if not s:
                return False
            lang = str(self.language or "").lower()
            if not (lang.startswith("span") or lang.startswith("esp") or lang == "es"):
                return False
            toks = re.findall(r"[A-Za-z]+", s.lower())
            if len(toks) < 4:
                return False
            en_hits = sum(1 for t in toks if t in EN_STOP)
            es_hits = sum(1 for t in toks if t in ES_STOP)
            # Clear English signal: several English stopwords and more EN than ES
            return en_hits >= 3 and en_hits > es_hits

        def _content_bigrams(norm: str) -> set:
            """
            Consecutive non-stopword token pairs from the normalized form.
            Catches lowercase compound subjects ("fuego griego", "biblioteca
            alejandria") that `_extract_entities` misses because it only
            counts capitalized tokens. Bigrams where BOTH tokens are in
            COMMON_CAP_NOISE are dropped — those are generic phrase-noise
            ("antigua grecia", "imperio romano") that two different videos
            can legitimately share without being duplicates.
            """
            toks = norm.split()
            out: set = set()
            for i in range(len(toks) - 1):
                a, b = toks[i], toks[i + 1]
                if a in COMMON_CAP_NOISE and b in COMMON_CAP_NOISE:
                    continue
                out.add(f"{a} {b}")
            return out

        # ---- 3. Pre-compute past signatures ----
        past_clean = [_strip_markdown(t) for t in past_topics]
        past_norm = [_normalize(t) for t in past_clean]
        past_entities = [_extract_entities(t) for t in past_clean]
        past_bigrams = [_content_bigrams(n) for n in past_norm]

        # Frequency-based filter: an entity that shows up in >15% of past
        # topics (with a floor of 3) is effectively a channel-wide theme
        # rather than a distinctive subject — stop treating it as a signature.
        # This keeps the guard from flagging "different Pharaoh" videos as
        # duplicates just because both mention "Nilo".
        from collections import Counter
        _freq: Counter = Counter()
        for _ents in past_entities:
            _freq.update(_ents)
        _common_threshold = max(3, len(past_entities) // 7)
        common_entities = {e for e, c in _freq.items() if c > _common_threshold}

        # Same frequency filter for bigrams: a 2-word phrase appearing across
        # many past videos is a channel-wide theme ("imperio romano" on a Rome
        # channel), not a distinctive subject signature. Dropping these avoids
        # false-positive dedupe when the user wants multiple legit angles on
        # a recurring topic.
        _bg_freq: Counter = Counter()
        for _bgs in past_bigrams:
            _bg_freq.update(_bgs)
        common_bigrams = {b for b, c in _bg_freq.items() if c > _common_threshold}

        def _is_duplicate(candidate: str) -> tuple[bool, str]:
            cand_clean = _strip_markdown(candidate)
            if not cand_clean:
                return False, ""
            cand_norm = _normalize(cand_clean)
            cand_ents = _extract_entities(cand_clean)
            cand_bigrams = _content_bigrams(cand_norm)

            for original, p_norm, p_ents, p_bgs in zip(past_topics, past_norm, past_entities, past_bigrams):
                if not p_norm:
                    continue
                # Exact normalized match
                if cand_norm == p_norm:
                    return True, original
                # Shared distinctive entity → same subject (catches "Hammurabi"
                # x2, "Cosimo I Medici" x2, etc., even when the rest of the
                # sentence is completely reworded). Exclude channel-wide
                # common entities so "two different Pharaoh stories" don't
                # collide on the shared region/era.
                shared = (cand_ents & p_ents) - common_entities
                if shared:
                    return True, original
                # Shared distinctive bigram → same compound subject in
                # lowercase ("fuego griego", "muerte negra"). Excludes
                # channel-wide common bigrams so recurring niche themes
                # don't auto-collide.
                shared_bg = (cand_bigrams & p_bgs) - common_bigrams
                if shared_bg:
                    return True, original
                # Token-overlap fallback (tighter threshold than before)
                a, b = set(cand_norm.split()), set(p_norm.split())
                if a and b:
                    overlap = len(a & b) / max(len(a), len(b))
                    if overlap >= 0.55:
                        return True, original
                # Raw sequence similarity
                if SequenceMatcher(None, cand_norm, p_norm).ratio() >= 0.7:
                    return True, original
            return False, ""

        # ---- 4. Build forbidden block (topics + banned entities) ----
        # IMPORTANT: this block is purely a duplicate-avoidance hint for the LLM.
        # It must NOT push the model out of the niche. With heavy channel history
        # (e.g. 100+ videos) the older wording ("FORBIDDEN entities ... Generate a
        # COMPLETELY DIFFERENT and ORIGINAL idea") read like "abandon the niche",
        # because every entity listed *was* a niche entity. We now (a) cap counts
        # tighter, (b) phrase the avoidance as "still WITHIN the niche", and
        # (c) re-anchor the niche AFTER the avoidance list so the model holds it
        # in working memory while picking a new angle. The cache-side dedupe
        # guard (`_is_duplicate`) is unchanged and still catches collisions.
        forbidden_block = ""
        if past_topics:
            shown = past_clean[-25:]
            all_ents: set = set()
            for ents in past_entities[-25:]:
                all_ents.update(ents)
            entity_list = sorted(e for e in all_ents if len(e) >= 4)[:40]
            forbidden_block = (
                "\n\nALREADY COVERED in this niche (pick a DIFFERENT angle, but stay WITHIN the niche):\n"
                + "\n".join(f"- {t}" for t in shown)
            )
            if entity_list:
                forbidden_block += (
                    "\n\nSpecific subjects already covered — avoid these particular ones, "
                    "but DO NOT leave the niche to avoid them (the niche is huge — pick a different "
                    "person/place/event/concept from the SAME niche):\n"
                    + ", ".join(entity_list)
                )
            forbidden_block += (
                f"\n\nGenerate a fresh angle WITHIN the niche \"{self.niche}\". "
                f"The new topic must still unmistakably belong to this niche — "
                f"only the specific subject should differ from the list above."
            )

        # ---- 4b. Niche validator (second LLM pass that double-checks the candidate) ----
        def _topic_in_niche(candidate: str) -> bool:
            """
            Ask the LLM whether the candidate topic clearly belongs to the channel's
            niche. Returns False if the verdict is anything other than an unambiguous
            FITS, so off-niche or ambiguous topics get rejected and regenerated.

            IMPORTANT: the response MUST be at least ~10 chars long. llm_provider's
            garbage filter (`_is_garbage_response`) treats any reply shorter than 10
            chars as conversational and DISABLES the provider for the whole session.
            We require a short structured line ("VERDICT: FITS — <reason>") that
            clears that bar.
            """
            try:
                verdict = self.generate_response(
                    f"""You are a strict content classifier. Decide if this video topic clearly and unmistakably belongs to the channel's niche.

CHANNEL NICHE: {self.niche}

CANDIDATE TOPIC: {candidate}

Rules for your verdict:
- Answer FITS only if the topic is undeniably part of the niche — a viewer would immediately recognize it as belonging to that niche.
- Answer OFFNICHE if the topic is fictional, made-up, abstract, metaphorical, or drifts toward storytelling/fiction when the niche is factual/educational.
- Answer OFFNICHE if the topic is a generic life lesson or philosophical musing not tied to the niche's actual subject matter.
- Answer OFFNICHE if the topic could fit dozens of different niches — niches require specificity.
- When in doubt, answer OFFNICHE.

OUTPUT FORMAT (strict, exactly one line):
VERDICT: <FITS or OFFNICHE> — <short reason in 5-15 words>

Example outputs:
VERDICT: FITS — clearly a real historical curiosity about ancient Egypt
VERDICT: OFFNICHE — fictional storytelling, not a real subject in the niche

Return ONLY that single line. No other text."""
                )
            except Exception:
                # If the validator call fails, don't block the pipeline — accept the candidate.
                return True
            verdict_up = (verdict or "").strip().upper()
            # Look for the verdict token anywhere in the response (handles wrappers like
            # "**VERDICT: FITS — ...**" or stray quotes around the line).
            if "OFFNICHE" in verdict_up or "OFF-NICHE" in verdict_up or "OFF NICHE" in verdict_up:
                return False
            if "FITS" in verdict_up:
                return True
            # Unparseable response → accept (the cache-side dedupe still guards the run).
            return True

        # ---- 5. Generate with retries ----
        rejected: List[str] = []
        completion = ""
        max_attempts = 8
        for attempt in range(max_attempts):
            creativity_seed = random.randint(1, 100000)
            extra_reject = ""
            if rejected:
                extra_reject = (
                    "\n\nYou already suggested these and they were REJECTED — "
                    "pick a completely unrelated angle:\n"
                    + "\n".join(f"- {t}" for t in rejected[-6:])
                )

            raw_candidate = self.generate_response(
                f"""Generate ONE specific, focused topic for a short video.

YOUR NICHE (you MUST stay strictly within this niche): {self.niche}

CRITICAL RULE: The topic MUST be directly and unmistakably part of the niche above. Anything that does not clearly belong to that niche is FORBIDDEN — including fictional stories, made-up characters, abstract metaphors, generic life lessons, philosophical musings disconnected from the niche, or any unrelated field. ONLY generate topics whose subject matter a viewer would immediately recognize as belonging to "{self.niche}".

The topic must be ONE concrete story, event, mystery, fact, person, place, or phenomenon — NOT a broad category, NOT a fictional scenario.

BAD example: "Curiosidades del antiguo Egipto" (too broad, leads to random facts)
BAD example: "El hombre que camina hacia atrás" (fictional story, not a real subject)
GOOD example: "La maldición de la tumba de Tutankamón: ¿qué les pasó a los arqueólogos?" (one specific real story)
GOOD example: "¿Por qué los romanos usaban orina para lavar la ropa?" (one specific real curiosity)
GOOD example: "El día que un asteroide exterminó al 75% de la vida en la Tierra" (one specific real event)

SELF-CHECK BEFORE ANSWERING: Re-read the niche "{self.niche}". If your topic is not unmistakably part of THAT niche, discard it and pick a different one.

OUTPUT FORMAT (strict):
- Return ONLY the topic as one plain sentence.
- NO markdown (no **, no backticks, no headers).
- NO prefixes like "Topic:", "Tema:", "Title:".
- NO surrounding quotes.
- WRITE ENTIRELY IN {self.language}. Every word must be in {self.language}.{forbidden_block}{extra_reject}

(Creativity seed: {creativity_seed} — use this to inspire a fresh angle WITHIN the niche. "Fresh" means a different specific subject from the same niche, NOT a different field.)"""
            )

            candidate = _strip_markdown(raw_candidate or "")
            if not candidate:
                continue

            if _looks_english(candidate):
                warning(
                    f"Topic is not in {self.language} (attempt {attempt + 1}/{max_attempts}): "
                    f"'{candidate[:80]}' — regenerating."
                )
                rejected.append(candidate)
                continue

            is_dup, matched = _is_duplicate(candidate)
            if is_dup:
                warning(
                    f"Topic collides with past video (attempt {attempt + 1}/{max_attempts}).\n"
                    f"   candidate: {candidate[:100]}\n"
                    f"   past     : {matched[:100]}"
                )
                rejected.append(candidate)
                continue

            if not _topic_in_niche(candidate):
                warning(
                    f"Topic off-niche (attempt {attempt + 1}/{max_attempts}).\n"
                    f"   candidate: {candidate[:100]}\n"
                    f"   niche    : {self.niche[:100]}"
                )
                rejected.append(candidate)
                continue

            completion = candidate
            break

        if not completion:
            # Channel-lifetime duplicate guard: we NEVER knowingly publish a
            # repeat. Return "" so the caller aborts the run.
            error(
                f"Could not generate a unique topic after {max_attempts} attempts — "
                f"refusing to publish a duplicate. Try again later or broaden the niche."
            )
            self.subject = ""
            return ""

        self.subject = completion
        return completion

    def generate_script(self) -> str:
        """
        Generate a script for a video, depending on the subject of the video, the number of paragraphs, and the AI model.

        Returns:
            script (str): The script of the video.
        """
        import random

        sentence_length = get_script_sentence_length()

        # Rotate hook style per run so every short doesn't open the same way.
        # The preset is picked from HOOK_PROFILES by self._hook_profile (set per
        # channel on the account JSON). Falls back to "educational" if the
        # configured profile is missing or unknown.
        profile_name = self._hook_profile or "educational"
        hook_styles = HOOK_PROFILES.get(profile_name) or HOOK_PROFILES["educational"]
        if profile_name not in HOOK_PROFILES and self._hook_profile:
            warning(f"Unknown hook_profile '{self._hook_profile}', falling back to 'educational'.")
            profile_name = "educational"
        hook_style, hook_example = random.choice(hook_styles)

        if get_verbose():
            info(f" => Hook profile: {profile_name} | style: {hook_style}")

        prompt = f"""Write a narration script for a short video in EXACTLY {sentence_length} sentences.

TOPIC: {self.subject}

NARRATIVE STRUCTURE (follow this order):
1. HOOK (sentence 1): The hook MUST use this exact style: {hook_style}. Example (adapt to the topic and to {self.language}): {hook_example}. Do NOT default to any other hook style.
2. CONTEXT (sentences 2-3): Set the scene. When and where does this happen? What's the background?
3. DEVELOPMENT (sentences 4-{sentence_length - 2}): Go deeper into the topic. Reveal details, facts, consequences. Build tension or curiosity. Each sentence should ADVANCE the story, not jump to unrelated facts.
4. CONCLUSION (last 1-2 sentences): End with a powerful thought, a twist, or a mind-blowing takeaway.

CRITICAL RULES:
- Stay on ONE topic throughout. Do NOT list random facts. Tell ONE story from start to finish.
- Every sentence must connect to the previous one. The script must feel like a continuous narrative, not a list.
- EXACTLY {sentence_length} sentences. Short and punchy (under 20 words each).
- NO markdown, NO formatting, NO titles, NO bullet points.
- NO "welcome", NO "voiceover", NO meta-references.
- ABSOLUTELY NO stage directions of any kind. Never write "(image of ...)", "(imagen de ...)", "[B-roll: ...]", "(plano cerrado)", "(music)", "(música suave)", "(emoji)", "(transition)", "(voice over)" or anything similar. Only text a narrator would speak ALOUD.
- NUMBERS: spell numbers out as words, not digits. Examples (in {self.language}): "mil cuatrocientos cincuenta y tres" not "1453"; "four thousand five hundred" not "4,500".
- YEAR vs DURATION — keep them strictly separate. A YEAR is a calendar date; a DURATION is elapsed time. They are different things. To cite a calendar year, say "el año <año>" / "in the year <year>". The phrase "hace <N> años" / "<N> years ago" expresses ONLY duration: <N> is the difference between the current year and the year of the event — it is NOT the year itself. When in doubt, name the year ("el año X") and do NOT use the "hace X años" / "X years ago" phrasing.
- ONLY return the raw script text. Nothing else.
- WRITE ENTIRELY IN {self.language}. Every word must be in {self.language}.
"""
        completion = self.generate_response(prompt)

        # Apply regex to remove *
        completion = re.sub(r"\*", "", completion)

        if not completion:
            error("The generated script is empty.")
            return

        if len(completion) > 5000:
            if get_verbose():
                warning("Generated Script is too long. Retrying...")
            return self.generate_script()

        self.script = completion

        return completion

    def generate_metadata(self) -> dict:
        """
        Generates Video metadata for the to-be-uploaded YouTube Short (Title, Description).

        Returns:
            metadata (dict): The generated metadata.
        """
        # Pass the actual script to the title prompt \u2014 without it, the model
        # invents clickbait promises ("5 curiosidades", "3 secretos") that
        # the script never delivers. The title must reflect what the video
        # actually says.
        title_prompt = f"""Generate a YouTube Short title for this video.

SUBJECT: {self.subject}

ACTUAL SCRIPT (the title must match what THIS script delivers):
\"\"\"
{self.script}
\"\"\"

ABSOLUTE RULES:
- The title must accurately describe what the script says. Do NOT promise content that is not in the script.
- FORBIDDEN: "X curiosidades", "X secretos", "X razones", "X cosas", "X datos", "X hechos", "Top X", "X que..." or ANY list-form promise (in {self.language} or English) UNLESS the script actually presents that exact number of distinct enumerated items. If the script tells ONE continuous story, the title MUST NOT promise a list.
- FORBIDDEN: "no vas a creer", "te volar\u00e1 la cabeza", "el secreto que nadie te cont\u00f3", and similar empty hype that the script does not back up.
- The title can be intriguing, but it must be HONEST \u2014 every promise in the title must be delivered by the script.
- Optionally include 1-2 relevant hashtags at the end (only if they fit naturally).
- Under 80 characters.
- WRITE ENTIRELY IN {self.language}. Do NOT wrap the title in quotes. No leading/trailing quote characters.
- Only return the title text, nothing else."""

        title = self.generate_response(title_prompt)

        # Strip any quotes the LLM might add (regular, curly, single)
        title = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', title.strip()).strip()

        # Belt-and-suspenders enforcement: even with the prompt above, some
        # models still slip in "X <noun>" list promises. If the title makes
        # that promise but the script doesn't enumerate items, regenerate
        # once with a stricter instruction.
        if self._title_promises_list(title) and not self._script_has_enumerated_items(self.script):
            warning(
                f"Title promises a list but script does not enumerate items: '{title}' \u2014 regenerating."
            )
            retry = self.generate_response(
                title_prompt
                + "\n\nPREVIOUS ATTEMPT WAS REJECTED because it promised a numbered list that the script does NOT deliver. "
                + "Your script tells ONE continuous story \u2014 the title must reflect that. "
                + "Do NOT use any number followed by a noun ('5 curiosidades', '3 razones', etc.). "
                + "Do NOT use 'Top N' or 'N que...'. Try again."
            )
            retry = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', retry.strip()).strip()
            if retry and not self._title_promises_list(retry):
                title = retry

        # If truncation would cut a hashtag, remove hashtags instead
        if len(title) > 100:
            if "#" in title:
                title = title[:title.index("#")].strip()
            if len(title) > 100:
                title = title[:100]

        description = self.generate_response(
            f"Please generate a YouTube Video Description for the following script: {self.script}. Only return the description, nothing else. Do NOT wrap the description in quotes. Do NOT start or end with any quote character. YOU MUST WRITE THE DESCRIPTION IN {self.language}."
        )

        # Strip any quotes the LLM might add (regular, curly, single)
        description = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', description.strip()).strip()

        self.metadata = {"title": title, "description": description}

        return self.metadata

    def generate_prompts(self, image_mode: str = "ai") -> List[str]:
        """
        Generates Image Prompts based on the provided Video Script.

        Args:
            image_mode (str): "ai" → cinematic prompts for AI generators.
                              "photos" → short search queries for real-photo sources
                              (Wikimedia Commons, Pexels, Pixabay).

        Returns:
            image_prompts (List[str]): Generated List of image prompts.
        """
        n_prompts = 6

        # Split script into sections so the LLM knows exactly what each image must show
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', self.script) if s.strip()]
        sections = []
        per_section = max(1, len(sentences) // n_prompts)
        for i in range(n_prompts):
            start = i * per_section
            end = start + per_section if i < n_prompts - 1 else len(sentences)
            section_text = ' '.join(sentences[start:end])
            if section_text:
                sections.append(section_text)
        # Pad if we got fewer sections
        while len(sections) < n_prompts:
            sections.append(self.subject)

        sections_text = ""
        for i, sec in enumerate(sections):
            sections_text += f"\nSECTION {i+1}: \"{sec}\"\n"

        if image_mode == "photos":
            prompt = f"""Generate exactly {n_prompts} short SEARCH QUERIES to find REAL historical/documentary/educational images for a video about: {self.subject}

These queries will be searched against Wikidata + Wikipedia + Wikimedia Commons + Europeana + Met Museum + Library of Congress. Tailor the wording for those archives.

ABSOLUTE RULE — SUBJECT ANCHORING:
Every single query MUST contain the canonical English name of the subject (or, if the section is about a specific historical event/place/person tied to the subject, that proper noun directly — e.g. "Domus Aurea" or "Great Fire of Rome" for a Nero video). NEVER write a query that is just a generic concept ("ancient Roman temple", "imperial banquet", "Roman senator portrait") — the search will return random unrelated results. The subject's proper noun, or a proper noun strictly identifying the same exact thing/event/person, MUST be present in every query.

CRITICAL — use the CANONICAL ENGLISH NAME (the form Wikipedia uses for the article title) for every person, place, event, or work:
  - WRONG: "Hipparchus the astronomer of stars"   →   RIGHT: "Hipparchus of Nicaea"
  - WRONG: "Marco Aurelio philosophy book"        →   RIGHT: "Marcus Aurelius" or "Meditations Marcus Aurelius"
  - WRONG: "Roman vestal virgin priestess fire"   →   RIGHT: "Vestal Virgins" or "Temple of Vesta"
  - WRONG: "Alexander conquering Persians battle" →   RIGHT: "Battle of Gaugamela"
  - WRONG: "ancient Egypt cat goddess statue"     →   RIGHT: "Bastet" (specific deity, not a generic "Egyptian cat goddess")
A Wikipedia article should EXIST for the subject of every query.

ANCHORING EXAMPLES — for a video about "Nero":
  - GOOD: "Nero portrait bust", "Nero Domus Aurea", "Great Fire of Rome 64 AD", "Nero Capitoline Museum", "Nero coin denarius", "Tacitus Annals Nero".
  - BAD:  "Roman emperor toga", "ancient Rome fire", "imperial palace Rome", "Roman bust marble". (None mentions Nero or a proper noun strictly tied to him.)

The script has been divided into {n_prompts} sections. Each query must match its section:
{sections_text}
INSTRUCTIONS:
- Query 1 finds a photo for SECTION 1, Query 2 for SECTION 2, etc.
- Each query MUST contain at least one PROPER NOUN strictly identifying the subject (e.g. "Nero", "Domus Aurea", "Great Fire of Rome").
- 3 to 7 words per query. No full sentences.
- FORBIDDEN words: cinematic, dramatic, lighting, 8K, 4K, photorealistic, HD, macro, bokeh, shot, close-up, aerial, style, composition, render, aesthetic. No adjectives describing mood or camera.
- FORBIDDEN as the ONLY proper noun in a query: civilization adjectives ("Roman", "Greek", "Egyptian"), generic roles ("emperor", "king", "soldier"), or generic places ("city", "temple"). They may appear, but never alone.
- Write in English (most archives index in English).

Return ONLY a JSON array of {n_prompts} strings. No markdown, no explanation."""
        else:
            # SOFT setting context — used as background hints only, never as a
            # per-prompt prop/clothing checklist (the previous civilization-
            # focused implementation forced armor enumerations into every
            # prompt and produced repetitive portraits). The brief is derived
            # per-video from the niche + topic + script by the LLM, so it
            # works for any subject — historical, modern, sports, food, tech.
            ctx = self._get_context_profile()
            era_context = ""
            if ctx and (ctx.get("setting") or ctx.get("visual_anchors")):
                bits = []
                if ctx.get("setting"):
                    bits.append(f"the story is set in **{ctx['setting']}**")
                if ctx.get("visual_anchors"):
                    bits.append(f"recurring visual cues for this setting: {ctx['visual_anchors']}")
                if ctx.get("must_avoid"):
                    bits.append(f"avoid: {ctx['must_avoid']}")
                era_context = (
                    "\n\nSETTING CONTEXT (background only, not a checklist): "
                    + ". ".join(bits)
                    + ". Setting-appropriate clothing, architecture and props should appear NATURALLY "
                      "in scenes — never enumerate them as a list. Each prompt still focuses on a "
                      "specific story beat, not a costume description."
                )

            video_title = (self.metadata or {}).get("title", "") if hasattr(self, "metadata") else ""

            # Pass the WHOLE script (not pre-sliced sections) so the LLM can
            # pick {n_prompts} narratively distinct beats by itself. Mechanical
            # sectioning into ~equal sentence chunks gives the LLM uselessly
            # short slices and it falls back to generic character portraits.
            script_block = (self.script or "").strip()

            prompt = f"""Task: write {n_prompts} image prompts for a YouTube Short. The {n_prompts} prompts together must VISUALLY TELL the story narrated in the script — different moments, different actions, different places. NOT {n_prompts} portraits of the same character.{era_context}

VIDEO TITLE: {video_title or self.subject}
TOPIC: {self.subject}

FULL SCRIPT (read it whole — do NOT slice mechanically; pick the {n_prompts} most VISUALLY DISTINCT story beats):
\"\"\"
{script_block}
\"\"\"

WORK IN TWO STEPS (internally — only the final JSON is returned):

STEP 1 — Pick {n_prompts} NARRATIVELY DISTINCT BEATS from the script. A beat is a single concrete action: "X does Y in place Z with object W". Each beat must:
  • have a different VERB from the others ("plows", "addresses senators", "lays down the fasces", "walks home through wheat fields", "wraps a toga at dawn")
  • happen in a different SETTING (a farm, a senate floor, a battlefield, a road, a doorway)
  • feature a different NARRATIVE OBJECT — a CONCRETE thing that belongs to THIS specific story (a wooden plow, the fasces lictoriae, a wax tablet, oxen, a senator's purple-bordered toga, a humble farmhouse door). NOT generic period props.
  • {n_prompts} beats = {n_prompts} different visual moments. If two of your beats look similar, replace one.

STEP 2 — Write each prompt applying ALL these rules:

1. ENGLISH ONLY. Even if the script is in Spanish, every prompt is written in English. Translate proper nouns naturally ("Platón" → "Plato", "Alejandro" → "Alexander"). No Spanish words anywhere.

2. ACTION FIRST. Open with a verb-driven action. The first 6-8 words of the prompt MUST contain the main verb. Examples of correct openings (the openings vary with the setting — historical, modern, sports, domestic, etc.):
     "[subject] grips the wooden handle of a heavy plow…"
     "A messenger runs across a wheat field at dawn…"
     "[subject] slides three monitors aside and dials his broker…"
     "The coach paces the sideline as the clock hits two minutes…"
   FORBIDDEN openings (these produce static portraits regardless of subject): "[Name] standing in [costume]", "[Name] portrait", "A figure looking intently", "[Name] in [outfit] in front of [backdrop]".

3. NARRATIVE OBJECT — MANDATORY. Every prompt names at least one CONCRETE OBJECT specific to THIS story (could be a plow, a wax tablet, a stack of trade tickets, a playbook, a wrench, a cracked phone screen — whatever the script actually contains). Without a story-specific object, the image becomes a generic setting scene and you've failed the task.

4. UNIQUE BEATS. The {n_prompts} prompts must NEVER show the same scene twice. If you find yourself writing two prompts where the same character is doing roughly the same thing in the same place, scrap one and pick a different beat from the script.

5. NAMED PERSON ANCHOR. When a real person appears, give a SHORT physical anchor (one phrase, max ~10 words) so the generator renders the right person — but the action and the object are the FOCUS, not the costume. Example: "[the protagonist], a sun-weathered older man with grey stubble, in a simple work tunic, grips the plow handle…" — the anchor is the brief clause, the action is the rest.

6. SETTING AS BACKGROUND. Setting-appropriate clothing, architecture and props appear NATURALLY in the scene because the story happens there. NEVER write a costume/prop checklist (e.g. "wearing X armor, helmet Y, holding Z sword" or "in a slim grey suit, silk navy tie, gold cufflinks, pocket square"). One or two natural setting cues per prompt is enough.

7. NO ART-STYLE WORDS. Describe scenes only. NEVER write: "painting", "illustration", "cartoon", "anime", "drawing", "vector", "3D render", "ukiyo-e", "fresco", "engraving", "comic", "pixel art", "watercolor", "sketch". The visual style is added downstream.

8. NO CAMERA JARGON. NEVER write: "cinematic", "photograph", "camera", "shot", "lens", "close-up", "4K", "8K", "HD", "render", "bokeh", "macro", "aerial".

9. NO MULTI-IMAGE TRIGGERS (these make generators output collages): "series", "sequence", "scenes" (plural), "panels", "panel", "storyboard", "comic strip", "montage", "collage", "grid", "split screen", "frames", "multiple", "diptych", "triptych", "before-and-after", "side by side".

10. LENGTH. 35-60 English words per prompt.

STRUCTURAL EXAMPLES — these show the PATTERN across different settings; the names, settings and objects below are placeholders. Your actual prompts must use the real subject, objects, and setting of THIS video's script.

   GOOD ✓ (historical) "[subject] grips the wooden handle of a heavy plow behind two yoked oxen at dawn, bare-chested, sweat on his shoulders, freshly turned soil in long furrows, his sandals caked in dark earth, a low farmhouse on the rise behind."
   GOOD ✓ (modern office) "A startup founder stares at a red downward chart on a wide monitor, knuckles white on a coffee mug, sticky notes peeling off the wall behind him, his cofounder pacing in the background phone in hand, dim evening light through floor-to-ceiling windows."
   GOOD ✓ (sports) "The point guard cuts through two defenders and lays the ball off the glass under the rim, scoreboard frozen at 89-89, the home crowd half-standing, a referee's whistle still in mid-blow at the baseline."
   GOOD ✓ (domestic / present-day) "A teenage girl stuffs a hoodie into her backpack on her bed, phone face-down on the duvet, posters peeling off the walls, her mother knocking on the half-open door behind her, late afternoon light through the blinds."

   BAD ✗ "[subject] in elaborate outfit standing in front of [backdrop]." (no verb, no narrative object, generic portrait — exact failure mode)
   BAD ✗ "A figure wearing a full uniform / kit / suit, holding a tool in the location, dramatic side lighting." (costume checklist instead of story; no action specific to the script)
   BAD ✗ "Officials / players / employees in formal clothing in the meeting room." (no specific moment, no story-specific object)
   BAD ✗ "[subject] portrait, weathered face, wearing official outfit, [backdrop] behind him." (forbidden opening — static portrait)

Return ONLY a JSON array of {n_prompts} prompt strings, in chronological order following the script. No markdown, no explanation, no preamble. Just the array.

Example format:
["beat 1 prompt …", "beat 2 prompt …", "beat 3 prompt …", "beat 4 prompt …", "beat 5 prompt …", "beat 6 prompt …"]"""

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        image_prompts = []

        def _extract_prompts(parsed_value):
            """Pull the prompt strings out of a parsed LLM response.
            For AI mode the LLM returns objects {"section", "moment", "prompt"};
            for photos mode (legacy) it returns plain strings. Handle both."""
            out = []
            if isinstance(parsed_value, list):
                for item in parsed_value:
                    if isinstance(item, str):
                        out.append(item)
                    elif isinstance(item, dict):
                        # Prefer the structured "prompt" field; if missing,
                        # combine moment + any description we can find.
                        p = item.get("prompt") or item.get("image_prompt") or ""
                        moment = item.get("moment") or item.get("key_visual_moment") or ""
                        if p:
                            out.append(str(p))
                        elif moment:
                            out.append(str(moment))
            elif isinstance(parsed_value, dict) and "image_prompts" in parsed_value:
                out = parsed_value["image_prompts"]
            return out

        # Try to extract JSON from the response
        try:
            parsed = json.loads(completion)
            image_prompts = _extract_prompts(parsed)
        except Exception:
            # Try to find a JSON array anywhere in the response
            match = re.search(r'\[.*\]', completion, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    image_prompts = _extract_prompts(parsed)
                except Exception:
                    pass

        # Fallback if parsing failed or too few prompts
        if image_mode == "photos":
            fallback_prompts = [self.subject] * n_prompts
        else:
            # Single-image, scene-only fallback prompts. No "illustrated", no
            # "series" / "sequence" / "panels" — those words make Gemini /
            # Nano Banana 2 produce a stacked collage instead of one image.
            fallback_prompts = [
                f"{self.subject}, the central subject in full view, period-accurate setting and clothing, single image",
                f"{self.subject}, detail of the central object or person, period-accurate textures and materials, single image",
                f"{self.subject}, panoramic view of the environment, period-accurate landscape and architecture, single image",
                f"{self.subject}, the historical moment shown directly, period-accurate clothing and architecture, single image",
                f"{self.subject}, several figures interacting in period-accurate context, single image",
                f"{self.subject}, atmospheric historical moment with depth, period-accurate mood and palette, single image",
            ]

        if not image_prompts or not isinstance(image_prompts, list):
            if get_verbose():
                warning("Failed to parse image prompts, using fallback prompts")
            image_prompts = fallback_prompts
        elif len(image_prompts) < n_prompts:
            if get_verbose():
                warning(f"Only got {len(image_prompts)} prompts, padding to {n_prompts}")
            # Pad with fallback prompts to reach n_prompts
            for fp in fallback_prompts:
                if len(image_prompts) >= n_prompts:
                    break
                image_prompts.append(fp)

        # Limit to n_prompts
        image_prompts = image_prompts[:n_prompts]

        # ------------------------------------------------------------------
        # Diversity guard (AI mode only) — detects the failure mode where
        # the LLM returns N near-identical "[name] in armor in front of
        # columns" portraits instead of N narratively distinct beats.
        # If it triggers, regenerate ONCE with a stricter directive.
        # ------------------------------------------------------------------
        if image_mode != "photos" and image_prompts and len(image_prompts) >= 3:

            def _looks_too_generic(prompts: List[str]) -> str:
                """Return a non-empty diagnostic string when prompts look
                like the failure mode, or "" if they pass the heuristic."""
                if not prompts:
                    return "no prompts"

                # 1. STATIC PORTRAIT — opens with a name/title followed by a
                #    pose verb ("standing", "posing", "looking", "stares") or a
                #    costume preposition ("in", "wearing", "with"). Niche-
                #    agnostic: catches the failure mode regardless of subject
                #    matter (history, sports, finance, etc.).
                portrait_re = re.compile(
                    r"^\s*(?:[A-ZÁÉÍÓÚÑ]\w+(?:\s+\w+){0,3}\s+"
                    r"(?:in|wearing|with|stands|stood|standing|posing|portrait|stares?|looks|looking))\b",
                    re.IGNORECASE,
                )
                portrait_count = sum(1 for p in prompts if portrait_re.search(p or ""))
                if portrait_count >= max(2, len(prompts) // 2):
                    return f"{portrait_count}/{len(prompts)} prompts open with a static portrait pattern"

                # 3. LEXICAL DUPLICATION — many prompts share their first 5 words.
                first5 = [" ".join((p or "").lower().split()[:5]) for p in prompts]
                if len(set(first5)) <= max(1, len(prompts) // 2):
                    return f"only {len(set(first5))} unique opening phrases across {len(prompts)} prompts"

                return ""

            diag = _looks_too_generic(image_prompts)
            if diag:
                warning(f"Image prompts look generic ({diag}); regenerating once with stricter directive.")
                stricter = (
                    prompt
                    + "\n\nPREVIOUS ATTEMPT REJECTED — your prompts were "
                    + diag
                    + ". This is exactly the failure mode the rules above forbid. "
                    "Regenerate from scratch. Each of the "
                    f"{n_prompts} prompts MUST: (a) open with a different ACTION verb tied to a "
                    "specific moment of THIS script, (b) name a CONCRETE NARRATIVE OBJECT from "
                    "this story (the plow, the fasces, the wax tablet, the farmhouse, etc., "
                    "depending on what the story actually contains), (c) happen in a different "
                    "setting from the others. NEVER write \"X standing in armor in front of "
                    "columns\" — that is the exact pattern we are rejecting."
                )
                retry_completion = (
                    str(self.generate_response(stricter))
                    .replace("```json", "").replace("```", "").strip()
                )
                retry_prompts: List[str] = []
                try:
                    retry_prompts = _extract_prompts(json.loads(retry_completion))
                except Exception:
                    m = re.search(r"\[.*\]", retry_completion, re.DOTALL)
                    if m:
                        try:
                            retry_prompts = _extract_prompts(json.loads(m.group()))
                        except Exception:
                            pass
                if retry_prompts and len(retry_prompts) >= n_prompts:
                    retry_prompts = retry_prompts[:n_prompts]
                    if not _looks_too_generic(retry_prompts):
                        image_prompts = retry_prompts
                        if get_verbose():
                            info(" => Diversity-guard retry produced acceptable prompts.")
                    else:
                        # Retry also fell into the failure mode — keep the original;
                        # at least it parsed. Nothing more to do here without a third call.
                        warning("   Retry still looked generic; keeping original prompts.")

        if get_verbose():
            info(f" => Generated Image Prompts: {image_prompts}")

        self.image_prompts = image_prompts

        success(f"Generated {len(image_prompts)} Image Prompts.")

        return image_prompts

    def _persist_image(self, image_bytes: bytes, provider_label: str) -> str:
        """
        Writes generated image bytes to a PNG file in .mp.

        Args:
            image_bytes (bytes): Image payload
            provider_label (str): Label for logging

        Returns:
            path (str): Absolute image path
        """
        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")

        with open(image_path, "wb") as image_file:
            image_file.write(image_bytes)

        if get_verbose():
            info(f' => Wrote image from {provider_label} to "{image_path}"')

        self.images.append(image_path)
        return image_path

    def _try_huggingface(self, prompt: str) -> bytes:
        """Try HuggingFace Inference API. Requires free HF token."""
        from config import get_hf_api_key
        hf_token = get_hf_api_key()
        if not hf_token:
            raise RuntimeError("HuggingFace token not configured (hf_api_key in config.json)")

        print(colored(f"    [HuggingFace] Generating...", "cyan"), flush=True)
        headers = {"Authorization": f"Bearer {hf_token}"}

        models = [
            "stabilityai/stable-diffusion-xl-base-1.0",
        ]

        for model in models:
            try:
                resp = requests.post(
                    f"https://router.huggingface.co/hf-inference/models/{model}",
                    headers=headers,
                    json={"inputs": prompt[:300]},
                    timeout=120,
                )
                ct = resp.headers.get("content-type", "")
                if resp.status_code == 200 and ("image" in ct or len(resp.content) > 5000):
                    print(colored("OK", "green"))
                    return resp.content
            except Exception:
                continue
        raise RuntimeError("HuggingFace: all models failed")

    def _try_pollinations(self, prompt: str) -> bytes:
        """Try Pollinations.ai image generation (primary provider - free, no key, best quality with flux model)."""
        import urllib.parse
        short_prompt = prompt[:500]
        encoded = urllib.parse.quote(short_prompt)
        seed = int(time.time())
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&seed={seed}&model=flux"
        print(colored(f"    [Pollinations.ai FLUX] Generating...", "cyan"), flush=True)
        resp = requests.get(url, timeout=180)
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(colored("OK", "green"))
            return resp.content
        raise RuntimeError(f"Pollinations returned status {resp.status_code}")

    def _try_pollinations_turbo(self, prompt: str) -> bytes:
        """Try Pollinations.ai with turbo model (faster, more available than FLUX)."""
        import urllib.parse
        short_prompt = prompt[:500]
        encoded = urllib.parse.quote(short_prompt)
        seed = int(time.time()) + 42
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&seed={seed}&model=turbo"
        print(colored(f"    [Pollinations turbo] Generating...", "cyan"), flush=True)
        resp = requests.get(url, timeout=180)
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(colored("OK", "green"))
            return resp.content
        raise RuntimeError(f"Pollinations turbo returned status {resp.status_code}")

    def _try_pollinations_realism(self, prompt: str) -> bytes:
        """Try Pollinations.ai with flux-realism model (photorealistic style)."""
        import urllib.parse
        short_prompt = prompt[:500]
        encoded = urllib.parse.quote(short_prompt)
        seed = int(time.time()) + 99
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&seed={seed}&model=flux-realism"
        print(colored(f"    [Pollinations flux-realism] Generating...", "cyan"), flush=True)
        resp = requests.get(url, timeout=180)
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(colored("OK", "green"))
            return resp.content
        raise RuntimeError(f"Pollinations flux-realism returned status {resp.status_code}")

    def _try_ideogram(self, prompt: str) -> bytes:
        """Try Ideogram API (very high quality, free tier ~25 images/day)."""
        from config import get_ideogram_api_key
        api_key = get_ideogram_api_key()
        if not api_key:
            raise RuntimeError("Ideogram API key not configured")

        print(colored(f"    [Ideogram] Generating...", "cyan"), flush=True)
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        payload = {
            "image_request": {
                "prompt": prompt[:1000],
                "model": "V_2",
                "aspect_ratio": "ASPECT_9_16",
            }
        }
        resp = requests.post(
            "https://api.ideogram.ai/generate",
            headers=headers, json=payload, timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        images = data.get("data", [])
        if not images:
            raise RuntimeError("Ideogram: no images returned")
        img_url = images[0].get("url", "")
        if not img_url:
            raise RuntimeError("Ideogram: no image URL")
        img_resp = requests.get(img_url, timeout=60)
        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
            print(colored("OK", "green"))
            return img_resp.content
        raise RuntimeError("Ideogram: failed to download image")

    def _try_leonardo(self, prompt: str) -> bytes:
        """Try Leonardo AI API (excellent quality, $5 free credit).
        Uses Phoenix 1.0 by default — it follows long prompts much better
        than Lightning XL, which was averaging out specific subjects (e.g.
        rendering "Plato" as a generic Greek figure)."""
        from config import get_leonardo_api_key
        api_key = get_leonardo_api_key()
        if not api_key:
            raise RuntimeError("Leonardo AI API key not configured")

        print(colored(f"    [Leonardo AI] Generating...", "cyan"), flush=True)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt[:1500],
            "modelId": "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3",  # Leonardo Phoenix 1.0
            "width": 576,
            "height": 1024,
            "num_images": 1,
            "contrast": 3.5,
            "alchemy": True,
        }
        # When the channel forces an artistic style, hint to Leonardo via
        # presetStyle so it applies an aesthetic LoRA on top of the prompt.
        # Detection is keyword-based on the channel's image_style.
        style_text = (self._image_style or "").lower()
        if any(k in style_text for k in ("cartoon", "anime", "illustration", "animated", "cel shading", "hand-drawn")):
            payload["presetStyle"] = "ILLUSTRATION"
        elif any(k in style_text for k in ("cinematic", "film", "movie")):
            payload["presetStyle"] = "CINEMATIC"
        elif self._image_style:
            payload["presetStyle"] = "DYNAMIC"
        resp = requests.post(
            "https://cloud.leonardo.ai/api/rest/v1/generations",
            headers=headers, json=payload, timeout=30,
        )
        resp.raise_for_status()
        gen_id = resp.json().get("sdGenerationJob", {}).get("generationId", "")
        if not gen_id:
            raise RuntimeError("Leonardo: no generation ID returned")

        # Poll for completion
        for _ in range(30):
            time.sleep(5)
            status_resp = requests.get(
                f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}",
                headers=headers, timeout=15,
            )
            status_resp.raise_for_status()
            gen = status_resp.json().get("generations_by_pk", {})
            status = gen.get("status", "")
            if status == "COMPLETE":
                images = gen.get("generated_images", [])
                if images:
                    img_url = images[0].get("url", "")
                    img_resp = requests.get(img_url, timeout=60)
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        print(colored("OK", "green"))
                        return img_resp.content
                raise RuntimeError("Leonardo: no image in result")
            elif status == "FAILED":
                raise RuntimeError("Leonardo: generation failed")
        raise RuntimeError("Leonardo: timeout waiting for generation")

    def _augment_for_ai_fallback(self, query: str) -> str:
        """Wrap a short photo-mode search query with neutral mood cues so AI
        generators render a usable image. We DO NOT inject 'photorealistic'
        / 'cinematic photograph' here anymore — those would override a
        cartoon / illustration channel style. The actual aesthetic is
        decided by `_apply_channel_style` (channel image_style or default
        baseline)."""
        out = f"{query}, dramatic lighting, highly detailed composition"
        return self._apply_channel_style(out)

    def _persist_metadata_sidecar(self, is_long: bool) -> None:
        """Write a `<video_basename>.meta.json` next to the rendered .mp4 with
        subject + metadata + kind, so that a later upload-last invocation
        (which runs in a fresh subprocess and has no in-memory state) can
        recover what to upload. Without this sidecar the user gets
        'subject is empty' when clicking Subir from the dialog after generation.
        """
        try:
            video_path = getattr(self, "video_path", "")
            if not video_path:
                return
            sidecar = os.path.splitext(video_path)[0] + ".meta.json"
            payload = {
                "subject": getattr(self, "subject", "") or "",
                "metadata": getattr(self, "metadata", {}) or {},
                "is_long": bool(is_long),
                "thumbnail_path": getattr(self, "thumbnail_path", "") or "",
            }
            with open(sidecar, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            if get_verbose():
                info(f" => Wrote upload sidecar: {sidecar}")
        except Exception as e:
            if get_verbose():
                warning(f"Could not write upload sidecar: {e}")

    # Default visual baseline applied when a channel has NO `image_style`
    # configured. Goal: keep all images uniform (same realism level) and let
    # the scene description itself carry the period-accurate clothing / setting
    # / objects. We deliberately avoid any "art style" cue (no "cinematic",
    # "painting", "cartoon", "illustration").
    #
    # PROMPTING NOTES:
    # - Lead with strong POSITIVE single-frame phrasing ("one full-bleed
    #   photograph filling the entire frame edge to edge"). Gemini / Nano
    #   Banana 2 respond much better to positive composition anchors than to
    #   "no panels / no collage" negatives, which can backfire via priming.
    # - Include explicit face/skin/hands realism cues so portraits stop looking
    #   plasticky and AI-glossy.
    DEFAULT_BASE_STYLE = (
        "one full-bleed photograph filling the entire frame edge to edge, "
        "one continuous uninterrupted scene captured in a single exposure, "
        "photorealistic, true-to-life realism, natural ambient lighting, "
        "period-accurate clothing architecture weapons and everyday objects, "
        "authentic materials and textures, neutral documentary tone, "
        "anatomically correct human faces with realistic skin texture, visible pores, subtle imperfections, "
        "natural facial proportions, sharp detailed eyes with realistic iris, "
        "accurate hands with five fingers, correct anatomy, "
        "subtle film grain, shallow depth of field, "
        "no cartoon, no illustration, no painting, no anime, no stylization, no plastic skin, no waxy skin"
    )

    # Words that frequently push Gemini / Nano Banana 2 toward producing a
    # multi-panel collage instead of a single image. Stripped from any LLM
    # prompt before it's sent to the image generator. Word-boundary regex.
    _COLLAGE_TRIGGERS = re.compile(
        r"\b("
        r"collage|montage|storyboard|comic[- ]?strip|panels?|grid|split[- ]?screen|"
        r"diptych|triptych|polyptych|side[- ]?by[- ]?side|before[- ]?and[- ]?after|"
        r"sequences?|series of|set of \d+|multiple (?:images|scenes|frames)|"
        r"frames?|stills?|tiled|stacked"
        r")\b",
        re.IGNORECASE,
    )

    @classmethod
    def _sanitize_image_prompt(cls, text: str) -> str:
        """Remove multi-image trigger words from a prompt. Image generators
        (especially Gemini) interpret words like "panels", "sequence",
        "storyboard" as a request for a collage even when context says "one
        image" — so we strip them defensively before sending."""
        if not text:
            return text
        cleaned = cls._COLLAGE_TRIGGERS.sub("", text)
        # Collapse double spaces and stray punctuation left after substitution.
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        cleaned = re.sub(r"\s+,", ",", cleaned)
        cleaned = re.sub(r",\s*,", ",", cleaned)
        return cleaned.strip(" ,")

    def _apply_channel_style(self, prompt: str) -> str:
        """
        Wrap an LLM-produced scene description with the channel's visual
        style + an era anchor so each image is on-topic AND consistent with
        the channel's aesthetic.

        Two modes:

        1) Channel has a custom `image_style` (e.g. cartoon, watercolor,
           anime). The style MUST dominate. We frame the prompt so Gemini
           reads it as: STYLE first, scene second, period items as content
           (NOT as realism cues), STYLE again at the end. The era block uses
           neutral wording ("use these era-appropriate items") instead of
           "period-accurate" / "photorealistic" cues that would fight the
           channel style.

        2) No `image_style` configured → fall back to `DEFAULT_BASE_STYLE`
           (photoreal documentary look) and a stronger era anchor that
           explicitly forbids modern/industrial visuals.

        The split matters: with a cartoon channel we don't want phrases like
        "photorealistic" or "realistic skin" in the prompt because Gemini
        will average between the two and produce neither.
        """
        clean_prompt = self._sanitize_image_prompt(prompt).rstrip(', .')
        ctx = self._get_context_profile()
        custom_style = (self._image_style or "").strip()

        parts: list[str] = []

        if custom_style:
            # Style anchored at front for maximum weight, then scene, then a
            # neutral setting clause, then style repeated at the end as reminder.
            short_style = custom_style if len(custom_style) <= 200 else custom_style[:200].rsplit(",", 1)[0]
            parts.append(f"ART STYLE — render the entire image in this style: {custom_style}")
            parts.append(clean_prompt)
            if ctx and (ctx.get("setting") or ctx.get("visual_anchors")):
                setting_clause = (
                    f"Scene context — the story is set in {ctx['setting']}. " if ctx.get("setting") else ""
                )
                anchors_clause = (
                    f"Include setting-appropriate items naturally in the composition (drawn in the art style above): {ctx['visual_anchors']}. "
                    if ctx.get("visual_anchors") else ""
                )
                avoid_clause = (
                    f"Avoid: {ctx['must_avoid']}." if ctx.get("must_avoid") else ""
                )
                parts.append((setting_clause + anchors_clause + avoid_clause).strip())
            parts.append(
                f"FINAL REMINDER — keep the entire image in the art style described above ({short_style}). "
                f"Do NOT default to photorealism. Do NOT add realistic skin texture or photographic lighting. "
                f"The art style overrides any realism implied by the scene."
            )
        else:
            parts.append(clean_prompt)
            if ctx and (ctx.get("setting") or ctx.get("visual_anchors")):
                setting_clause = (
                    f"Setting: {ctx['setting']}. " if ctx.get("setting") else ""
                )
                anchors_clause = (
                    f"Visual anchors that should appear naturally when relevant — {ctx['visual_anchors']}. "
                    if ctx.get("visual_anchors") else ""
                )
                avoid_clause = (
                    f"Avoid anachronistic / off-setting elements: {ctx['must_avoid']}."
                    if ctx.get("must_avoid") else ""
                )
                parts.append((setting_clause + anchors_clause + avoid_clause).strip())
            parts.append(self.DEFAULT_BASE_STYLE)

        combined = ". ".join(p for p in parts if p)
        # Hard cap to ~1500 chars — Gemini accepts up to ~1900 in our payload
        # cap, so this leaves headroom while preventing prompt explosion.
        return combined[:1500]

    def _get_context_profile(self) -> dict:
        """
        Niche-agnostic context anchor for image-prompt generation.

        Uses the LLM to derive a per-video brief from the channel niche +
        topic + script, returning a dict shaped like:

            {
                "setting": "<short descriptor of where/when/in-what-world the
                            video takes place — e.g. 'Ancient Rome',
                            'Modern Wall Street trading floor',
                            'Pro NFL stadium', 'Tokyo high-end omakase
                            kitchen', 'Suburban American household 2020s'>",
                "visual_anchors": "<comma-separated concrete props, clothing,
                            architecture, objects and environmental cues that
                            should appear naturally in scenes for this video>",
                "must_avoid": "<comma-separated visual elements that would be
                            anachronistic or off-topic for this setting>"
            }

        Replaces the previous hardcoded CIVILIZATIONS keyword-matching system,
        which only covered ~17 historical eras and forced every channel into
        civilization-flavored visuals. The new approach works for any niche —
        history, science, finance, sports, food, tech, modern stories, etc.

        Cached per (subject, len(script)) tuple. Returns {} on parse failure
        or when the LLM declines (in which case no extra anchor is injected
        and the prompt falls back to scene-only content).
        """
        subject = (getattr(self, "subject", "") or "").strip()
        script = (getattr(self, "script", "") or "").strip()
        niche = (getattr(self, "niche", "") or "").strip()
        if not subject and not script:
            return {}

        cache_key = (subject, len(script))
        cached = getattr(self, "_ctx_profile_cached", None)
        if getattr(self, "_ctx_profile_key", None) == cache_key and cached is not None:
            return cached

        script_excerpt = script[:1200]
        prompt = f"""You are a visual research assistant. Read the channel niche, the video topic and the script excerpt, and produce a JSON brief that will anchor image generation for this single video.

CHANNEL NICHE: {niche or "(not specified)"}
VIDEO TOPIC: {subject or "(not specified)"}
SCRIPT EXCERPT:
\"\"\"
{script_excerpt}
\"\"\"

Return ONLY a JSON object with EXACTLY these three string fields:
- "setting": a short descriptor of WHERE and WHEN the story happens — pick the most specific real-world setting that fits the topic and script (e.g. "Ancient Rome, late Republic", "Modern Wall Street trading floor", "Pro NFL stadium, game day", "Tokyo high-end omakase kitchen", "Silicon Valley startup office, 2020s", "Rural American farmhouse, present day", "Open ocean, modern container ship"). Do NOT default to "ancient civilization" unless the topic clearly requires it.
- "visual_anchors": a comma-separated list of CONCRETE props, clothing, architecture, vehicles, tools, environmental details that should appear naturally in scenes from this setting. 8 to 14 items. Be specific (materials, eras, styles).
- "must_avoid": a comma-separated list of visual elements that would be anachronistic, off-topic or break immersion for this setting. 4 to 8 items.

RULES:
- Match the SETTING to the actual subject. A topic about a modern athlete must NOT get a "Greek Olympics" setting just because the channel niche mentions sports history.
- If the topic is abstract or the script is generic, pick the setting that most viewers would picture when reading the topic.
- Output ONLY the JSON object — no markdown, no preamble, no explanation. No code fences.
"""
        try:
            raw = str(self.generate_response(prompt) or "").strip()
        except Exception as e:
            if get_verbose():
                warning(f"Context profile LLM call failed: {e}")
            self._ctx_profile_key = cache_key
            self._ctx_profile_cached = {}
            return {}

        cleaned = raw.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        profile: dict = {}
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                profile = {
                    "setting": str(parsed.get("setting", "")).strip(),
                    "visual_anchors": str(parsed.get("visual_anchors", "")).strip(),
                    "must_avoid": str(parsed.get("must_avoid", "")).strip(),
                }
                # Drop the brief entirely if the LLM produced an empty / useless
                # blob — prevents injecting a placeholder anchor that would
                # confuse the image-prompt model.
                if not profile["setting"] and not profile["visual_anchors"]:
                    profile = {}
        except Exception as e:
            if get_verbose():
                warning(f"Context profile JSON parse failed: {e}")
            profile = {}

        if profile and get_verbose():
            info(f" => Context profile: setting='{profile.get('setting', '')[:80]}'")

        self._ctx_profile_key = cache_key
        self._ctx_profile_cached = profile
        return profile

    def _resolve_voice(self, voice: str) -> str:
        """Resolve a voice alias (e.g. 'Pablo') or raw Edge-TTS ID to its full voice ID."""
        from .Tts import EDGE_TTS_VOICES
        if not voice:
            return ""
        return EDGE_TTS_VOICES.get(voice, voice)

    def _topic_keywords(self) -> List[str]:
        """Key lowercase tokens from self.subject, used to anchor stock searches to the topic."""
        words = re.findall(r"[A-Za-zÀ-ÿ]+", (self.subject or "").lower())
        return [w for w in words if len(w) > 2 and w not in _PHOTO_STOPWORDS]

    def _anchor_query(self, query: str) -> str:
        """Prepend up to 3 subject keywords not already in the query so stock results stay on-topic."""
        keywords = self._topic_keywords()
        if not keywords:
            return query
        q_lower = query.lower()
        anchor = " ".join(kw for kw in keywords[:3] if kw not in q_lower)
        return f"{anchor} {query}".strip() if anchor else query

    def _query_tokens(self, *texts: str) -> set:
        """Extract content-word tokens from the given strings for relevance checks."""
        combined = " ".join(t for t in texts if t).lower()
        tokens = re.findall(r"[a-zà-ÿ]+", combined)
        return {t for t in tokens if len(t) > 2 and t not in _PHOTO_STOPWORDS}

    def _strict_anchor_tokens(self) -> set:
        """Distinctive tokens from the subject — generic words like 'roman' or
        'emperor' are dropped. These act as the must-match anchor when
        validating that a result is actually on-topic."""
        return set(self._topic_keywords()) - _GENERIC_TOPIC_TOKENS

    def _query_proper_nouns(self, query: str) -> set:
        """Capitalized words from the query — usually identify a specific
        person/place/event we want to actually appear in the result.
        Generic tokens (e.g. 'Roman') are stripped so they don't satisfy the
        anchor check on their own."""
        if not query:
            return set()
        nouns = re.findall(r"\b[A-ZÁ-ÚÑ][\wÀ-ſ]{2,}\b", query)
        out = set()
        for n in nouns:
            t = n.lower()
            if t in _PHOTO_STOPWORDS or t in _GENERIC_TOPIC_TOKENS:
                continue
            out.add(t)
        return out

    def _title_promises_list(self, title: str) -> bool:
        """True if the title promises a numbered list of items.
        Catches 'N <noun>' patterns ('5 curiosidades', '3 secretos', '7 razones')
        and 'Top N' constructions in Spanish/English. We trigger only on small
        single-digit lists (the typical clickbait range) — '1989' or 'mil años'
        in a historical title shouldn't false-positive."""
        if not title:
            return False
        t = title.lower()
        # "N + noun" where N is 2-9 (single-digit clickbait counts).
        list_nouns = (
            r"curiosidad(?:es)?|secret[oa]s?|raz(?:ón|on|ones)|cosas?|"
            r"dat[oa]s?|hech[oa]s?|reglas?|tips?|consejos?|trucos?|"
            r"misterios?|claves?|pasos?|errores?|verdades?|mitos?|"
            r"thing|things|reason|reasons|secret|secrets|fact|facts|"
            r"rule|rules|tip|tips|step|steps|truth|truths|myth|myths"
        )
        if re.search(rf"\b[2-9]\s+(?:{list_nouns})\b", t):
            return True
        # "Top N" in Spanish/English.
        if re.search(r"\btop\s+[2-9]\b", t):
            return True
        # "N <noun> que..." — catches "5 curiosidades que te sorprenderán" even
        # when the noun isn't in the list above.
        if re.search(r"\b[2-9]\s+\w{4,}\s+que\b", t):
            return True
        return False

    def _script_has_enumerated_items(self, script: str) -> bool:
        """Crude check: does the script actually list at least 3 enumerated items?
        Looks for explicit ordinal/list markers ('primero', 'segundo', 'tercero',
        'first', 'second', 'third', 'número uno', 'one:', '1.', '2.', etc.).
        If it doesn't find them, we conclude the script tells one story and a
        list-form title is dishonest."""
        if not script:
            return False
        s = script.lower()
        markers = 0
        # Spanish ordinals as words
        for w in ("primero", "primera", "segundo", "segunda", "tercero", "tercera",
                  "cuarto", "cuarta", "quinto", "quinta", "sexto", "sexta",
                  "séptimo", "séptima", "octavo", "octava", "noveno", "novena"):
            if re.search(rf"\b{w}\b", s):
                markers += 1
        # English ordinals
        for w in ("first", "second", "third", "fourth", "fifth", "sixth",
                  "seventh", "eighth", "ninth"):
            if re.search(rf"\b{w}\b", s):
                markers += 1
        # Numbered list markers ("1.", "1)", "1 -")
        markers += len(re.findall(r"(?:^|\s)[1-9][\.\)\-:]\s", s))
        # "número uno/dos/tres" / "number one/two/three"
        for w in ("uno", "dos", "tres", "cuatro", "cinco",
                  "one", "two", "three", "four", "five"):
            if re.search(rf"\bn[uú]mero\s+{w}\b|\bnumber\s+{w}\b", s):
                markers += 1
        return markers >= 3

    def _is_relevant(self, query: str, *result_texts: str) -> bool:
        """Strict relevance check used by every photo provider.

        A result counts as on-topic if it contains AT LEAST ONE distinctive
        anchor token — either from the subject itself or from the query's
        proper nouns. Generic words ('roman', 'emperor', 'history') are NOT
        sufficient on their own. If we can't derive any anchor (rare — e.g.
        the subject is a generic phrase), we fall back to the previous
        any-token overlap so the pipeline doesn't deadlock.
        """
        result_tokens = self._query_tokens(*result_texts)
        if not result_tokens:
            return False
        anchors = self._strict_anchor_tokens() | self._query_proper_nouns(query)
        if anchors:
            return bool(anchors & result_tokens)
        # No anchors at all → fall back to the loose any-token check so we
        # still trim obvious off-topic results.
        loose = self._query_tokens(query, self.subject)
        return bool(loose & result_tokens) if loose else True

    def _extract_search_query(self, prompt: str) -> str:
        """Extract clean search keywords from an AI image prompt for stock photo search."""
        import re
        # Remove common AI style/photography keywords
        style_words = r'\b(cinematic|dramatic|lighting|8K|4K|ultra|HD|macro|bokeh|aerial|drone|cyberpunk|hyper-realistic|vibrant|saturated|documentary|photography|shot|wide|close-up|extreme|detailed|textures?|colors?|film grain|neon|volumetric|fog|aesthetic|digital painting|golden hour|breathtaking|raw|authentic|feel|shallow depth|field|sweeping|portrait|style|composition|render|realistic|illustration|art|scene|view|high quality|resolution|background|foreground|angle|perspective|moody|atmosphere|accent|dark|light)\b'
        cleaned = re.sub(style_words, '', prompt, flags=re.IGNORECASE)
        cleaned = re.sub(r'[,\-:;"\'\(\)]', ' ', cleaned)
        cleaned = ' '.join(cleaned.split())
        # Take meaningful words (3-6) for search
        words = [w for w in cleaned.split() if len(w) > 2][:6]
        query = ' '.join(words) if words else self.subject
        return query

    def _try_pexels(self, prompt: str) -> bytes:
        """Try Pexels stock photos API (free, reliable, HD). Requires free API key."""
        from config import get_pexels_api_key
        api_key = get_pexels_api_key()
        if not api_key:
            raise RuntimeError("Pexels API key not configured")

        import urllib.parse
        import random

        # In photos mode the LLM already generated a clean query — don't strip it further.
        if getattr(self, "_image_mode", "ai") == "photos":
            query = prompt.strip()
        else:
            query = self._extract_search_query(prompt)
        query = self._anchor_query(query)

        print(colored(f"    [Pexels] Searching: {query[:60]}...", "cyan"), flush=True)
        headers = {"Authorization": api_key}
        # Fetch more results and pick a random page for more variety
        page = random.randint(1, 3)
        resp = requests.get(
            f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page=15&page={page}",
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            raise RuntimeError("Pexels: no photos found")

        # Relevance filter: alt text must contain a distinctive anchor token
        # from the subject or one of the query's proper nouns. Generic words
        # ('roman', 'emperor', etc.) alone are NOT enough — see _is_relevant.
        relevant = [p for p in photos if self._is_relevant(query, p.get("alt") or "")]
        if not relevant:
            raise RuntimeError("Pexels: no relevant photos (all off-topic)")
        photos = relevant

        # Filter out already-used images
        available = [p for p in photos if p["src"]["large2x"] not in self._used_stock_urls]
        if not available:
            available = photos  # all used, allow repeats as last resort

        photo = random.choice(available)
        img_url = photo["src"]["large2x"]  # high-res version
        self._used_stock_urls.add(img_url)
        img_resp = requests.get(img_url, timeout=60)
        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
            print(colored("OK", "green"))
            return img_resp.content
        raise RuntimeError("Pexels: failed to download image")

    def _try_pixabay(self, prompt: str) -> bytes:
        """Try Pixabay stock photos API (free, reliable, HD). Requires free API key."""
        from config import get_pixabay_api_key
        api_key = get_pixabay_api_key()
        if not api_key:
            raise RuntimeError("Pixabay API key not configured")

        import urllib.parse
        import random

        if getattr(self, "_image_mode", "ai") == "photos":
            query = prompt.strip()
        else:
            query = self._extract_search_query(prompt)
        query = self._anchor_query(query)

        print(colored(f"    [Pixabay] Searching: {query[:60]}...", "cyan"), flush=True)
        page = random.randint(1, 3)
        resp = requests.get(
            f"https://pixabay.com/api/?key={api_key}&q={urllib.parse.quote(query)}&image_type=photo&per_page=15&page={page}&min_width=1080",
            timeout=30,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            raise RuntimeError("Pixabay: no photos found")

        # Relevance filter: Pixabay `tags` is a comma-separated list — require
        # a distinctive anchor token (proper noun) overlap, not just any word.
        relevant = [h for h in hits if self._is_relevant(query, h.get("tags") or "")]
        if not relevant:
            raise RuntimeError("Pixabay: no relevant photos (all off-topic)")
        hits = relevant

        # Filter out already-used images
        available = [h for h in hits if h.get("largeImageURL", "") not in self._used_stock_urls]
        if not available:
            available = hits

        hit = random.choice(available)
        img_url = hit.get("largeImageURL", hit.get("webformatURL", ""))
        if not img_url:
            raise RuntimeError("Pixabay: no image URL in result")
        self._used_stock_urls.add(img_url)
        img_resp = requests.get(img_url, timeout=60)
        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
            print(colored("OK", "green"))
            return img_resp.content
        raise RuntimeError("Pixabay: failed to download image")

    def _try_wikipedia_article(self, prompt: str) -> bytes:
        """
        Find the Wikipedia article whose title best matches the query and return
        the article's MAIN image (the one in the infobox).

        Why this works better than Commons file-search for historical/educational topics:
          * Wikipedia's article search is fuzzy + redirects-aware (`Hiparco` → `Hipparchus`).
          * The infobox image is curated to represent the topic.
          * Tries the channel's language wiki first, then English as fallback.
        """
        import urllib.parse
        import random

        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        # Channel-language wiki code (e.g. "es", "en") + English as fallback.
        lang_map = {"spanish": "es", "english": "en", "portuguese": "pt", "french": "fr",
                    "german": "de", "italian": "it"}
        ch_lang = lang_map.get((self._language or "").lower(), "en")
        wikis = [ch_lang, "en"] if ch_lang != "en" else ["en"]

        headers = {"User-Agent": "MoneyPrinterPro/1.0 (research use)"}

        for wiki in wikis:
            print(colored(f"    [Wikipedia/{wiki}] Searching: {query[:60]}...", "cyan"), flush=True)
            try:
                # Step 1: search articles by query.
                search_url = (
                    f"https://{wiki}.wikipedia.org/w/api.php"
                    f"?action=query&format=json&list=search"
                    f"&srsearch={urllib.parse.quote(query)}"
                    f"&srlimit=10&srprop=size"
                )
                resp = requests.get(search_url, headers=headers, timeout=20)
                resp.raise_for_status()
                hits = resp.json().get("query", {}).get("search") or []
                if not hits:
                    continue

                # Try the top results until we find one with a usable infobox image.
                for hit in hits[:5]:
                    title = hit.get("title") or ""
                    if not title:
                        continue
                    # Step 2: fetch the article's main image at full resolution.
                    img_url = self._wikipedia_main_image(wiki, title, headers)
                    if not img_url or img_url in self._used_stock_urls:
                        continue
                    # Strict relevance check: the article title must contain
                    # at least one distinctive anchor token from the subject
                    # or query's proper nouns.
                    if not self._is_relevant(query, title):
                        continue
                    try:
                        img_resp = requests.get(img_url, headers=headers, timeout=60)
                        if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                            self._used_stock_urls.add(img_url)
                            print(colored(f"OK ({title[:50]})", "green"))
                            return img_resp.content
                    except Exception:
                        continue
            except Exception:
                continue

        raise RuntimeError("Wikipedia article: no suitable image found")

    def _wikipedia_main_image(self, wiki: str, title: str, headers: dict) -> str:
        """Get the original-resolution main image URL for a Wikipedia article."""
        import urllib.parse
        try:
            url = (
                f"https://{wiki}.wikipedia.org/w/api.php"
                f"?action=query&format=json&prop=pageimages"
                f"&piprop=original&titles={urllib.parse.quote(title)}"
            )
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {}) or {}
            for page in pages.values():
                src = (page.get("original") or {}).get("source") or ""
                if src:
                    return src
        except Exception:
            pass
        return ""

    def _try_wikimedia(self, prompt: str) -> bytes:
        """
        Search Wikimedia Commons file descriptions for matching images.
        Tries multiple query variants so we don't fail just because the LLM's
        query wording doesn't exactly match Commons file descriptions.
        """
        import urllib.parse
        import random

        # In photos mode the prompt is already a clean search query.
        # If it looks like an AI-style prompt (long / has style words), clean it.
        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        # Build a shortlist of query variants — try the original, then progressively
        # shorter / proper-noun-only versions so we recover from over-specific queries.
        words = query.split()
        STOP = {"the", "a", "an", "of", "in", "on", "at", "to", "and", "or",
                "el", "la", "los", "las", "un", "una", "y", "o", "de", "del"}
        proper_nouns = [w for w in words if w[:1].isupper() and w.lower() not in STOP]
        variants = []
        seen = set()
        for v in (query, " ".join(proper_nouns), " ".join(words[:3]), " ".join(proper_nouns[:2])):
            v = v.strip()
            if v and v.lower() not in seen:
                variants.append(v)
                seen.add(v.lower())

        headers = {"User-Agent": "MoneyPrinterPro/1.0 (https://github.com/; research use)"}

        for variant in variants:
            print(colored(f"    [Wikimedia] Searching: {variant[:60]}...", "cyan"), flush=True)
            try:
                api_url = (
                    "https://commons.wikimedia.org/w/api.php"
                    "?action=query&format=json&generator=search&gsrnamespace=6"
                    f"&gsrsearch={urllib.parse.quote(variant)}&gsrlimit=20"
                    "&prop=imageinfo&iiprop=url|size|mime"
                )
                resp = requests.get(api_url, headers=headers, timeout=30)
                resp.raise_for_status()
                pages = resp.json().get("query", {}).get("pages", {})
                if not pages:
                    continue

                candidates = []
                for page in pages.values():
                    info_list = page.get("imageinfo", [])
                    if not info_list:
                        continue
                    info = info_list[0]
                    url = info.get("url", "")
                    mime = info.get("mime", "")
                    w, h = info.get("width", 0), info.get("height", 0)
                    title = page.get("title") or ""
                    if not url or url in self._used_stock_urls:
                        continue
                    if mime not in ("image/jpeg", "image/png", "image/webp"):
                        continue
                    if min(w, h) < 600:
                        continue
                    # Strict relevance check: file title (e.g. "File:Hipparchus.jpg")
                    # must contain a distinctive anchor token from the subject
                    # or query's proper nouns. Generic adjectives don't count.
                    if not self._is_relevant(variant, title):
                        continue
                    candidates.append(url)

                if not candidates:
                    continue
                random.shuffle(candidates)
                for img_url in candidates[:5]:
                    try:
                        img_resp = requests.get(img_url, headers=headers, timeout=60)
                        if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                            self._used_stock_urls.add(img_url)
                            print(colored("OK", "green"))
                            return img_resp.content
                    except Exception:
                        continue
            except Exception:
                continue

        raise RuntimeError("Wikimedia: no suitable images across all query variants")

    def _try_met_museum(self, prompt: str) -> bytes:
        """
        Met Museum Open Access (paintings, sculptures, artifacts, prints).
        No API key required. Best for art, statues, classical artifacts.
        Docs: https://metmuseum.github.io/
        """
        import urllib.parse
        import random

        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        print(colored(f"    [Met Museum] Searching: {query[:60]}...", "cyan"), flush=True)
        headers = {"User-Agent": "MoneyPrinterPro/1.0 (research use)"}

        search_url = (
            "https://collectionapi.metmuseum.org/public/collection/v1/search"
            f"?q={urllib.parse.quote(query)}&hasImages=true"
        )
        resp = requests.get(search_url, headers=headers, timeout=30)
        resp.raise_for_status()
        obj_ids = (resp.json().get("objectIDs") or [])[:30]
        if not obj_ids:
            raise RuntimeError("Met Museum: no results")

        random.shuffle(obj_ids)

        for obj_id in obj_ids[:8]:
            try:
                obj_resp = requests.get(
                    f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{obj_id}",
                    headers=headers, timeout=20,
                )
                obj_resp.raise_for_status()
                obj = obj_resp.json()
                img_url = obj.get("primaryImage") or ""
                if not img_url or img_url in self._used_stock_urls:
                    continue
                # Strict relevance check against the object's metadata —
                # generic culture/period words ("Roman", "Imperial") on their
                # own do not satisfy _is_relevant.
                metadata_blob = " ".join(
                    str(obj.get(k, "")) for k in
                    ("title", "culture", "period", "objectName", "department",
                     "classification", "artistDisplayName", "country", "region")
                )
                if not self._is_relevant(query, metadata_blob):
                    continue
                img_resp = requests.get(img_url, headers=headers, timeout=60)
                if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                    self._used_stock_urls.add(img_url)
                    print(colored("OK", "green"))
                    return img_resp.content
            except Exception:
                continue
        raise RuntimeError("Met Museum: no usable image found")

    def _try_loc(self, prompt: str) -> bytes:
        """
        Library of Congress photo collection (historical photos, prints, maps,
        manuscripts, posters). No API key required.
        Docs: https://www.loc.gov/apis/json-and-yaml/
        """
        import urllib.parse
        import random

        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        print(colored(f"    [LoC] Searching: {query[:60]}...", "cyan"), flush=True)
        headers = {"User-Agent": "MoneyPrinterPro/1.0 (research use)"}
        search_url = (
            f"https://www.loc.gov/photos/?q={urllib.parse.quote(query)}&fo=json&c=25"
        )
        resp = requests.get(search_url, headers=headers, timeout=30)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            raise RuntimeError("LoC: no results")

        candidates = []
        for r in results:
            urls = r.get("image_url") or []
            if not urls:
                continue
            # Largest version is typically the last entry.
            img_url = urls[-1]
            if not img_url or img_url in self._used_stock_urls:
                continue
            title = r.get("title") or ""
            descr = r.get("description") or ""
            if isinstance(descr, list):
                descr = " ".join(str(d) for d in descr)
            subj = r.get("subject") or []
            subj_text = " ".join(subj) if isinstance(subj, list) else str(subj)
            # Strict relevance: at least one distinctive anchor token must
            # appear in title/description/subject metadata.
            if not self._is_relevant(query, title, str(descr), subj_text):
                continue
            candidates.append(img_url)

        if not candidates:
            raise RuntimeError("LoC: no relevant images")

        random.shuffle(candidates)
        for img_url in candidates[:5]:
            try:
                img_resp = requests.get(img_url, headers=headers, timeout=60)
                if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                    self._used_stock_urls.add(img_url)
                    print(colored("OK", "green"))
                    return img_resp.content
            except Exception:
                continue
        raise RuntimeError("LoC: failed to download any candidate")

    def _try_wikidata(self, prompt: str) -> bytes:
        """
        Wikidata-driven image lookup. The flow is:
          1. Search Wikidata entities for the query in the channel language
             (es/en) — returns a Q-id whose label most closely matches.
          2. Fetch that entity's claims:
             * P18 (image) → curated lead image used by every Wikipedia entry.
             * P373 (Commons category) → curated category of related images
               about that exact entity (statues, coins, frescoes, etc.).
          3. Verify the entity's labels actually contain a distinctive anchor
             token from the subject — protects against Q-id collisions
             (e.g. "Nero" → musician vs. emperor).

        Why this works better than fuzzy article search: Wikidata returns a
        deterministic entity ID, not a free-text article match. The image we
        get back is the canonical one Wikipedia uses everywhere — so for
        "Nero", we get the bust from the Capitoline Museums, not a generic
        Roman ruin.
        """
        import urllib.parse
        import random

        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        lang_map = {"spanish": "es", "english": "en", "portuguese": "pt", "french": "fr",
                    "german": "de", "italian": "it"}
        ch_lang = lang_map.get((self._language or "").lower(), "en")
        languages = [ch_lang, "en"] if ch_lang != "en" else ["en"]

        headers = {"User-Agent": "MoneyPrinterPro/1.0 (research use)"}

        for lang in languages:
            print(colored(f"    [Wikidata/{lang}] Searching: {query[:60]}...", "cyan"), flush=True)
            try:
                search_url = (
                    "https://www.wikidata.org/w/api.php"
                    "?action=wbsearchentities&format=json&type=item"
                    f"&language={lang}&uselang={lang}"
                    f"&search={urllib.parse.quote(query)}&limit=8"
                )
                resp = requests.get(search_url, headers=headers, timeout=20)
                resp.raise_for_status()
                entities = resp.json().get("search") or []
                if not entities:
                    continue

                for ent in entities[:5]:
                    qid = ent.get("id") or ""
                    label = ent.get("label") or ""
                    desc = ent.get("description") or ""
                    if not qid:
                        continue

                    # Anchor check: the entity label/description must contain a
                    # distinctive token from the subject or the query's proper
                    # nouns. Filters out unrelated Q-ids that happen to share
                    # a generic word.
                    if not self._is_relevant(query, label, desc):
                        continue

                    # Fetch the entity's claims.
                    ent_url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
                    try:
                        ent_resp = requests.get(ent_url, headers=headers, timeout=20)
                        ent_resp.raise_for_status()
                        claims = (
                            ent_resp.json()
                            .get("entities", {})
                            .get(qid, {})
                            .get("claims", {})
                        )
                    except Exception:
                        continue

                    # Collect candidate Commons filenames.
                    candidates: List[str] = []

                    # P18 = primary image. Curated, single best image.
                    p18 = claims.get("P18") or []
                    for c in p18:
                        try:
                            fname = c["mainsnak"]["datavalue"]["value"]
                            if fname:
                                candidates.append(fname)
                        except Exception:
                            continue

                    # P373 = Commons category. Pull a sample of files from it
                    # so we get variety (busts, coins, paintings, etc.).
                    p373 = claims.get("P373") or []
                    for c in p373[:1]:
                        try:
                            cat_name = c["mainsnak"]["datavalue"]["value"]
                        except Exception:
                            continue
                        if not cat_name:
                            continue
                        try:
                            cat_url = (
                                "https://commons.wikimedia.org/w/api.php"
                                "?action=query&format=json&list=categorymembers"
                                f"&cmtitle=Category:{urllib.parse.quote(cat_name)}"
                                "&cmtype=file&cmlimit=20"
                            )
                            cat_resp = requests.get(cat_url, headers=headers, timeout=20)
                            cat_resp.raise_for_status()
                            members = (
                                cat_resp.json()
                                .get("query", {})
                                .get("categorymembers", [])
                            )
                            for m in members:
                                title = m.get("title") or ""
                                if title.startswith("File:"):
                                    fname = title[5:]
                                    # Skip non-image / generic logos.
                                    if any(fname.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
                                        candidates.append(fname)
                        except Exception:
                            continue

                    if not candidates:
                        continue

                    # Resolve filenames to full-resolution URLs via Special:FilePath.
                    random.shuffle(candidates)
                    for fname in candidates[:8]:
                        img_url = (
                            "https://commons.wikimedia.org/wiki/Special:FilePath/"
                            + urllib.parse.quote(fname.replace(" ", "_"))
                        )
                        if img_url in self._used_stock_urls:
                            continue
                        try:
                            img_resp = requests.get(img_url, headers=headers, timeout=60, allow_redirects=True)
                            if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                                self._used_stock_urls.add(img_url)
                                print(colored(f"OK ({label[:40]} / {qid})", "green"))
                                return img_resp.content
                        except Exception:
                            continue
            except Exception:
                continue

        raise RuntimeError("Wikidata: no suitable entity image found")

    def _try_europeana(self, prompt: str) -> bytes:
        """
        Europeana — aggregator of European cultural-heritage institutions
        (museums, libraries, archives). Free API key required.
        Coverage is similar in quality to Wikipedia for historical/art topics
        and often surfaces material that isn't on Commons (museum scans,
        digitized prints, period engravings).

        Docs: https://pro.europeana.eu/page/intro
        """
        from config import get_europeana_api_key
        api_key = get_europeana_api_key()
        if not api_key:
            raise RuntimeError("Europeana API key not configured")

        import urllib.parse
        import random

        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        print(colored(f"    [Europeana] Searching: {query[:60]}...", "cyan"), flush=True)
        headers = {"User-Agent": "MoneyPrinterPro/1.0 (research use)"}

        # `media=true` → only items with a real media URL we can download.
        # `type=IMAGE` → drops audio/video/text. `reusability=open` would be
        # safer for licensing but excludes too much; we keep results broad
        # since the videos are not commercial in nature.
        search_url = (
            "https://api.europeana.eu/record/v2/search.json"
            f"?wskey={urllib.parse.quote(api_key)}"
            f"&query={urllib.parse.quote(query)}"
            "&type=IMAGE&media=true&thumbnail=true&rows=20&profile=rich"
        )
        resp = requests.get(search_url, headers=headers, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("items") or []
        if not items:
            raise RuntimeError("Europeana: no results")

        candidates = []
        for it in items:
            # Strict relevance: title + dcSubject + dcDescription must contain
            # a distinctive anchor token. Each field can be a list of strings
            # (Europeana returns localised variants), so flatten to a blob.
            def _flat(field) -> str:
                v = it.get(field)
                if not v:
                    return ""
                if isinstance(v, list):
                    return " ".join(str(x) for x in v)
                return str(v)

            blob = " ".join(_flat(f) for f in (
                "title", "dcTitle", "dcSubject", "dcDescription",
                "dcCreator", "edmConceptPrefLabel", "dataProvider",
            ))
            if not self._is_relevant(query, blob):
                continue

            # Prefer the full-resolution media; fall back to the preview.
            img_url = ""
            for k in ("edmIsShownBy", "edmIsShownAt", "edmPreview"):
                v = it.get(k)
                if isinstance(v, list) and v:
                    img_url = str(v[0])
                    break
                if isinstance(v, str) and v:
                    img_url = v
                    break
            if not img_url or img_url in self._used_stock_urls:
                continue
            candidates.append(img_url)

        if not candidates:
            raise RuntimeError("Europeana: no relevant images")

        random.shuffle(candidates)
        for img_url in candidates[:6]:
            try:
                img_resp = requests.get(img_url, headers=headers, timeout=60, allow_redirects=True)
                # Europeana sometimes proxies through HTML pages; require a
                # real image content-type AND a reasonable size.
                ctype = img_resp.headers.get("Content-Type", "").lower()
                if (
                    img_resp.status_code == 200
                    and len(img_resp.content) > 10000
                    and ("image/" in ctype or img_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
                ):
                    self._used_stock_urls.add(img_url)
                    print(colored("OK", "green"))
                    return img_resp.content
            except Exception:
                continue
        raise RuntimeError("Europeana: failed to download any candidate")

    def _try_picsum_stock(self, prompt: str) -> bytes:
        """Fallback: HD stock photo from Picsum (fast, always works)."""
        print(colored(f"    [Picsum HD] Getting image...", "yellow"), flush=True)
        seed = abs(hash(prompt)) % 1000
        url = f"https://picsum.photos/seed/{seed}/1080/1920"
        resp = requests.get(url, timeout=60, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(colored("OK", "green"))
            return resp.content
        raise RuntimeError(f"Picsum returned status {resp.status_code}")

    def _generate_fallback_image(self, prompt: str) -> str:
        """
        Generates a stylish fallback image using Pillow when all API providers fail.
        """
        from PIL import Image, ImageDraw, ImageFont
        import random as rand_mod

        if get_verbose():
            warning("All providers failed. Creating styled fallback image...")

        # Create gradient background
        color_schemes = [
            ((15, 15, 80), (80, 20, 120)),
            ((10, 50, 80), (20, 100, 100)),
            ((60, 10, 60), (120, 30, 80)),
            ((10, 40, 20), (30, 100, 60)),
        ]
        c1, c2 = rand_mod.choice(color_schemes)
        img = Image.new("RGB", (1080, 1920))
        draw = ImageDraw.Draw(img)

        for y in range(1920):
            r = int(c1[0] + (c2[0] - c1[0]) * y / 1920)
            g = int(c1[1] + (c2[1] - c1[1]) * y / 1920)
            b = int(c1[2] + (c2[2] - c1[2]) * y / 1920)
            draw.line([(0, y), (1080, y)], fill=(r, g, b))

        # Add text
        try:
            font_path = os.path.join(get_fonts_dir(), get_font())
            font = ImageFont.truetype(font_path, 52)
        except Exception:
            font = ImageFont.load_default()

        words = prompt.split()
        lines, current_line = [], ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if len(test) > 25:
                lines.append(current_line)
                current_line = word
            else:
                current_line = test
        if current_line:
            lines.append(current_line)

        y_pos = 1920 // 2 - (len(lines) * 70) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            # Shadow
            draw.text(((1080 - w) // 2 + 3, y_pos + 3), line, fill=(0, 0, 0), font=font)
            # Text
            draw.text(((1080 - w) // 2, y_pos), line, fill="white", font=font)
            y_pos += 70

        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
        img.save(image_path)
        self.images.append(image_path)

        if get_verbose():
            info(f' => Wrote fallback image to "{image_path}"')

        return image_path

    def generate_images_batch(self, prompts: List[str], image_mode: str = "ai") -> None:
        """
        Generate ALL images using multiple providers in cascade.

        Args:
            prompts: List of image prompts / search queries.
            image_mode: "ai" → AI generators first, stock photos as fallback (default).
                        "photos" → Wikimedia / stock photos first, AI as last-resort fallback.
        """
        self._image_mode = image_mode
        if image_mode == "photos":
            print(colored(f"\n  [Images] Fetching {len(prompts)} real photos...", "blue"))
            providers = [
                # Tier 1: deterministic entity-based lookup. Wikidata maps the
                # query to a concrete entity (Q-id) and returns the curated
                # lead image (P18) plus a sample of files from its Commons
                # category (P373). Far more precise than fuzzy article search,
                # so it goes first.
                ("Wikidata", self._try_wikidata, "stock"),
                # Tier 2: fuzzy Wikipedia article search (handles redirects,
                # spelling variants) → curated infobox image.
                ("Wikipedia article", self._try_wikipedia_article, "stock"),
                # Tier 3: free-text search across other curated heritage
                # archives. Europeana aggregates European museums/libraries,
                # Wikimedia Commons covers everything else, Met Museum and
                # Library of Congress cover art and historical photos.
                ("Europeana", self._try_europeana, "stock"),
                ("Wikimedia Commons", self._try_wikimedia, "stock"),
                ("Met Museum", self._try_met_museum, "stock"),
                ("Library of Congress", self._try_loc, "stock"),
                # Tier 4: modern stock (filtered by relevance) — useful for
                # non-historical topics where heritage archives are sparse.
                ("Pexels", self._try_pexels, "stock"),
                ("Pixabay", self._try_pixabay, "stock"),
                # Tier 5: AI fallback when no real photo matches the topic.
                ("Leonardo AI", self._try_leonardo, "ai"),
                ("Pollinations FLUX", self._try_pollinations, "ai"),
                ("Pollinations turbo", self._try_pollinations_turbo, "ai"),
            ]
        else:
            print(colored(f"\n  [Images] Generating {len(prompts)} images...", "blue"))
            providers = [
                # Tier 1: High-quality AI generator
                ("Leonardo AI", self._try_leonardo, "ai"),
                # Tier 2: Free unlimited AI generators (no daily limits)
                ("Pollinations FLUX", self._try_pollinations, "ai"),
                ("Pollinations turbo", self._try_pollinations_turbo, "ai"),
                ("Pollinations flux-realism", self._try_pollinations_realism, "ai"),
                ("HuggingFace", self._try_huggingface, "ai"),
                # Tier 3: Stock photos (reliable, always available)
                ("Pexels", self._try_pexels, "stock"),
                ("Pixabay", self._try_pixabay, "stock"),
            ]

        for i, prompt in enumerate(prompts):
            print(colored(f"\n  Image {i+1}/{len(prompts)}", "blue"))
            saved = False
            for name, fn, kind in providers:
                try:
                    # In photos mode the LLM produces short search queries — AI providers need cinematic context to render well.
                    effective_prompt = prompt
                    if image_mode == "photos" and kind == "ai":
                        effective_prompt = self._augment_for_ai_fallback(prompt)
                    elif kind == "ai":
                        # AI mode: append per-channel image style suffix (if any).
                        effective_prompt = self._apply_channel_style(prompt)
                    img_bytes = fn(effective_prompt)
                    if img_bytes and len(img_bytes) > 1000:
                        self._persist_image(img_bytes, name)
                        saved = True
                        break
                except Exception as e:
                    if get_verbose():
                        warning(f"    {name} failed: {str(e)[:100]}")
                    time.sleep(1)
            if not saved:
                self._generate_fallback_image(prompt)

        success(f"All {len(prompts)} images ready!")

    def generate_image(self, prompt: str) -> str:
        """
        Generates an AI Image trying multiple FREE providers in cascade:
        1. HuggingFace (new router URL, needs free token)
        2. Pollinations.ai (free, no key — currently unstable)
        3. AI Horde (free, no key — crowdsourced SD, ~60-90s)
        4. Picsum (HD stock photos, fast)
        5. Pillow gradient fallback

        Args:
            prompt (str): Reference for image generation

        Returns:
            path (str): The path to the generated image.
        """
        providers = [
            ("Pollinations FLUX", self._try_pollinations),
            ("Pollinations turbo", self._try_pollinations_turbo),
            ("Pollinations flux-realism", self._try_pollinations_realism),
            ("HuggingFace", self._try_huggingface),
        ]

        print(colored(f"  [Image] {prompt[:80]}...", "blue"))

        for name, provider_fn in providers:
            try:
                img_bytes = provider_fn(prompt)
                if img_bytes and len(img_bytes) > 1000:
                    success(f"Image generated via {name}!")
                    return self._persist_image(img_bytes, name)
            except Exception as e:
                if get_verbose():
                    warning(f"{name} failed: {str(e)[:100]}")
                time.sleep(1)

        # All providers failed - use Pillow fallback
        return self._generate_fallback_image(prompt)

    def generate_script_to_speech(self, tts_instance: TTS) -> str:
        """
        Converts the generated script into Speech and returns the path to the wav file.
        Also captures word-level timestamps for karaoke subtitles when available.

        Args:
            tts_instance (tts): Instance of TTS Class.

        Returns:
            path_to_wav (str): Path to generated audio (WAV Format).
        """
        path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".wav")

        # Sanitize while keeping punctuation (commas, colons, em-dashes, ¿¡)
        # so Edge-TTS pauses naturally. The script we display keeps Roman
        # numerals intact ("Cosimo I"); only the text fed to TTS expands them
        # ("Cosimo primero") so pronunciation is correct.
        # Strip leaked stage directions ("(imagen de ...)") before any other
        # cleaning so TTS never reads them out loud.
        self.script = strip_stage_directions(self.script)
        self.script = clean_script_for_tts(self.script)
        tts_text, regnal_subs = expand_regnal_numerals_tracked(self.script)
        # Expand digit numbers to Spanish words. Applied to tts_text only so
        # the original self.script (used for subtitle alignment) keeps its
        # short tokens, while what the TTS reads has natural Spanish numbers.
        tts_text = expand_spanish_numbers(tts_text)

        # Per-channel short voice override (falls back to TTS instance default if empty).
        short_vid = self._resolve_voice(self._short_voice)
        # Optional dramatic modulation for narrator-style channels (mystery/horror/storytelling).
        # Lighter than the long-form documentary preset (-8% / -15Hz) so shorts still feel punchy.
        rate = "-5%" if self._voice_drama else ""
        pitch = "-8Hz" if self._voice_drama else ""
        path, word_timestamps = tts_instance.synthesize_with_timestamps(
            tts_text, path, voice_id=short_vid or None, rate=rate, pitch=pitch,
        )

        # Put the Roman numerals back in the word-level timestamps so the
        # karaoke subtitles read "I" / "XIV" while the audio says "primero" /
        # "catorce".
        if word_timestamps:
            word_timestamps = restore_regnal_numerals_in_timestamps(
                word_timestamps, regnal_subs
            )
        self.word_timestamps = word_timestamps

        self.tts_path = path

        if get_verbose():
            ts_info = f" ({len(word_timestamps)} words timed)" if word_timestamps else ""
            info(f' => Wrote TTS to "{path}"{ts_info}')

        return path

    def add_video(self, video: dict) -> None:
        """
        Adds a video to the cache.

        Args:
            video (dict): The video to add

        Returns:
            None
        """
        videos = self.get_videos()
        videos.append(video)

        cache = get_youtube_cache_path()

        with open(cache, "r", encoding="utf-8") as file:
            previous_json = json.loads(file.read())

            # Find our account
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    account["videos"].append(video)

            # Commit changes
            with open(cache, "w", encoding="utf-8") as f:
                f.write(json.dumps(previous_json))

    def generate_subtitles(self, audio_path: str) -> str:
        """
        Generates subtitles from the known script text.
        Uses script-based generation by default (instant, no STT needed since we
        already have the exact text). Falls back to STT only if explicitly configured.

        Args:
            audio_path (str): The path to the audio file.

        Returns:
            path (str): The path to the generated SRT File.
        """
        provider = str(get_stt_provider() or "script").lower()

        # Default: use the script we already have (instant, no extra dependencies)
        if provider not in ("local_whisper", "third_party_assemblyai"):
            return self.generate_subtitles_from_script(audio_path)

        try:
            if provider == "local_whisper":
                return self.generate_subtitles_local_whisper(audio_path)

            if provider == "third_party_assemblyai":
                return self.generate_subtitles_assemblyai(audio_path)
        except Exception as e:
            warning(f"STT subtitles failed ({e}), using script-based subtitles instead.")

        return self.generate_subtitles_from_script(audio_path)

    def generate_subtitles_from_script(self, audio_path: str) -> str:
        """
        Generates subtitles by splitting the script text into sentences
        and distributing them evenly across the audio duration.
        No STT engine required.

        Args:
            audio_path (str): Audio file path (used to get duration)

        Returns:
            path (str): Path to SRT file
        """
        from moviepy.editor import AudioFileClip as _AFC

        duration = _AFC(audio_path).duration
        sentences = re.split(r'(?<=[.!?])\s+', self.script.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            sentences = [self.script.strip()]

        seg_dur = duration / len(sentences)
        lines = []

        for idx, sentence in enumerate(sentences):
            start = self._format_srt_timestamp(idx * seg_dur)
            end = self._format_srt_timestamp(min((idx + 1) * seg_dur, duration))
            lines.append(str(idx + 1))
            lines.append(f"{start} --> {end}")
            lines.append(sentence)
            lines.append("")

        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))

        if get_verbose():
            info(f" => Generated script-based subtitles ({len(sentences)} segments)")

        return srt_path

    def generate_subtitles_assemblyai(self, audio_path: str) -> str:
        """
        Generates subtitles using AssemblyAI.

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        aai.settings.api_key = get_assemblyai_api_key()
        config = aai.TranscriptionConfig()
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_path)
        subtitles = transcript.export_subtitles_srt()

        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")

        with open(srt_path, "w", encoding="utf-8") as file:
            file.write(subtitles)

        return srt_path

    def _format_srt_timestamp(self, seconds: float) -> str:
        """
        Formats a timestamp in seconds to SRT format.

        Args:
            seconds (float): Seconds

        Returns:
            ts (str): HH:MM:SS,mmm
        """
        total_millis = max(0, int(round(seconds * 1000)))
        hours = total_millis // 3600000
        minutes = (total_millis % 3600000) // 60000
        secs = (total_millis % 60000) // 1000
        millis = total_millis % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def generate_subtitles_local_whisper(self, audio_path: str) -> str:
        """
        Generates subtitles using local Whisper (faster-whisper).

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            error(
                "Local STT selected but 'faster-whisper' is not installed. "
                "Install it or switch stt_provider to third_party_assemblyai."
            )
            raise

        whisper_model_name = get_whisper_model()
        print(colored(f"  [Whisper] Loading model '{whisper_model_name}'...", "cyan"), flush=True)
        model = WhisperModel(
            whisper_model_name,
            device=get_whisper_device(),
            compute_type=get_whisper_compute_type(),
        )
        print(colored(f"  [Whisper] Transcribing audio...", "cyan"), flush=True)
        segments, _ = model.transcribe(audio_path, vad_filter=True)

        lines = []
        for idx, segment in enumerate(segments, start=1):
            start = self._format_srt_timestamp(segment.start)
            end = self._format_srt_timestamp(segment.end)
            text = str(segment.text).strip()

            if not text:
                continue

            lines.append(str(idx))
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        subtitles = "\n".join(lines)
        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write(subtitles)

        return srt_path

    def _build_karaoke_subtitles(self, audio_duration: float):
        """
        Build word-by-word karaoke subtitle clip from word_timestamps.
        Shows groups of up to 5 words with multi-line wrapping; the active
        word is highlighted in yellow — modern YouTube Shorts style.
        """
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        words = self.word_timestamps
        if not words:
            return None

        font_path = os.path.join(get_fonts_dir(), "Poppins-Black.ttf").replace("\\", "/")
        font_size = 80
        font = ImageFont.truetype(font_path, font_size)
        canvas_w = 1080
        max_line_width = 920
        word_spacing = 28
        line_spacing = 0  # ascent+descent already provides natural spacing
        max_words_per_group = 5
        max_lines = 3

        # Measure height of a single line using full font metrics (ascent + descent)
        # plus stroke so descenders (g, y, p) and strokes never get clipped
        ascent, descent = font.getmetrics()
        line_h = ascent + descent

        # --- Helper: wrap a list of texts into lines that fit max_line_width ---
        def _wrap_group(texts):
            """Returns list of lines, each line is a list of (text, width) tuples."""
            lines = []
            current_line = []
            current_w = 0
            for t in texts:
                bb = font.getbbox(t)
                tw = bb[2] - bb[0]
                test_w = current_w + tw + (word_spacing if current_line else 0)
                if current_line and test_w > max_line_width:
                    lines.append(current_line)
                    current_line = [(t, tw)]
                    current_w = tw
                else:
                    current_line.append((t, tw))
                    current_w = test_w
            if current_line:
                lines.append(current_line)
            return lines

        # --- Group words (up to 5, but never exceeding max_lines when wrapped) ---
        groups = []
        current_group = []

        for w in words:
            candidate = current_group + [w]
            candidate_texts = [gw["word"].upper() for gw in candidate]
            lines_needed = len(_wrap_group(candidate_texts))
            if len(candidate) > max_words_per_group or lines_needed > max_lines:
                if current_group:
                    groups.append(current_group)
                current_group = [w]
            else:
                current_group = candidate
        if current_group:
            groups.append(current_group)

        # --- Build index: global word index → (group_idx, local_idx) ---
        word_to_group = {}
        gi = 0
        for g_idx, group in enumerate(groups):
            for l_idx in range(len(group)):
                word_to_group[gi] = (g_idx, l_idx)
                gi += 1

        # --- Pre-render one frame per word (group with that word highlighted) ---
        # First pass: determine max canvas height across all groups
        max_num_lines = 1
        for group in groups:
            texts = [gw["word"].upper() for gw in group]
            lines = _wrap_group(texts)
            max_num_lines = max(max_num_lines, len(lines))

        stroke_pad = 6 * 2  # stroke_width extends outward on all sides
        canvas_h = max_num_lines * line_h + (max_num_lines - 1) * line_spacing + stroke_pad + 20

        rendered = {}  # global_word_idx → (rgb np.array, alpha np.array)

        for word_idx, (g_idx, l_idx) in word_to_group.items():
            group = groups[g_idx]
            texts = [gw["word"].upper() for gw in group]
            lines = _wrap_group(texts)

            img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Track which global-in-group index we're drawing
            word_counter = 0
            y = 20
            for line in lines:
                line_total_w = sum(tw for _, tw in line) + word_spacing * (len(line) - 1)
                x = (canvas_w - line_total_w) // 2
                for t, tw in line:
                    if word_counter == l_idx:
                        draw.text((x, y), t, fill=(255, 215, 0), font=font,
                                  stroke_width=6, stroke_fill="black")
                    else:
                        draw.text((x, y), t, fill="white", font=font,
                                  stroke_width=6, stroke_fill="black")
                    x += tw + word_spacing
                    word_counter += 1
                y += line_h + line_spacing

            arr = np.array(img)
            rendered[word_idx] = (arr[:, :, :3], arr[:, :, 3].astype(np.float64) / 255.0)

        # Blank frame for silence gaps
        blank_rgb = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
        blank_alpha = np.zeros((canvas_h, canvas_w), dtype=np.float64)

        # --- Lookup: find active word at time t ---
        def find_active(t):
            for i, w in enumerate(words):
                if w["start"] <= t <= w["end"]:
                    return i
            # Between words: keep showing the last spoken word
            for i in range(len(words) - 1):
                if words[i]["end"] < t < words[i + 1]["start"]:
                    return i
            if words and t >= words[-1]["start"]:
                return len(words) - 1
            return -1

        def make_rgb(t):
            idx = find_active(t)
            if idx < 0 or idx not in rendered:
                return blank_rgb
            return rendered[idx][0]

        def make_mask(t):
            idx = find_active(t)
            if idx < 0 or idx not in rendered:
                return blank_alpha
            return rendered[idx][1]

        clip = VideoClip(make_rgb, duration=audio_duration).set_fps(30)
        mask = VideoClip(make_mask, duration=audio_duration, ismask=True).set_fps(30)
        clip = clip.set_mask(mask)
        clip = clip.set_position(("center", 1300))
        return clip

    def _estimate_word_timestamps(self, audio_duration: float):
        """Estimate word timestamps from script when TTS didn't provide them."""
        words = self.script.split()
        if not words:
            return []
        dur_per_word = audio_duration / len(words)
        return [
            {"start": i * dur_per_word, "end": (i + 1) * dur_per_word, "word": w}
            for i, w in enumerate(words)
        ]

    def combine(self) -> str:
        """
        Combines everything into the final video.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        combined_image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp4")
        threads = get_threads()
        tts_clip = AudioFileClip(self.tts_path)
        max_duration = tts_clip.duration

        print(colored("[+] Combining images...", "blue"))

        # Verify all images exist BEFORE computing duration distribution —
        # stale paths would inflate n_imgs and shrink req_dur, leaving a
        # black tail where clips run out before the TTS does.
        valid_images = [p for p in self.images if os.path.exists(p)]
        if not valid_images:
            raise FileNotFoundError("No valid images found for video combination")
        if len(valid_images) != len(self.images):
            missing = [p for p in self.images if not os.path.exists(p)]
            if get_verbose():
                warning(f"Missing {len(missing)} images, using {len(valid_images)} valid ones")
            self.images = valid_images

        # Crossfade overlap between clips — compensate so the composed total == max_duration
        crossfade = 0.4
        n_imgs = len(self.images)
        total_overlap = crossfade * max(0, n_imgs - 1)
        req_dur = (max_duration + total_overlap) / n_imgs

        clips = []
        tot_dur = 0
        target_total = max_duration + total_overlap
        # Add each image once, distributing duration evenly across the full TTS length
        for idx, image_path in enumerate(self.images):
            # Last clip absorbs any float remainder so composed total == max_duration exactly
            if idx == n_imgs - 1:
                this_dur = target_total - tot_dur
            else:
                this_dur = req_dur
            if this_dur <= 0:
                break
            clip = ImageClip(image_path).set_duration(this_dur).set_fps(30)

            # Not all images are same size,
            # so we need to resize them
            if round((clip.w / clip.h), 4) < 0.5625:
                if get_verbose():
                    info(f" => Resizing Image: {image_path} to 1080x1920")
                clip = crop(
                    clip,
                    width=clip.w,
                    height=round(clip.w / 0.5625),
                    x_center=clip.w / 2,
                    y_center=clip.h / 2,
                )
            else:
                if get_verbose():
                    info(f" => Resizing Image: {image_path} to 1920x1080")
                clip = crop(
                    clip,
                    width=round(0.5625 * clip.h),
                    height=clip.h,
                    x_center=clip.w / 2,
                    y_center=clip.h / 2,
                )
            clip = clip.resize((1080, 1920))

            # Ken Burns: subtle zoom (alternating in/out per image for variety).
            # Pre-scale to 1.06x so zoom never reveals empty edges, then animate scale
            # between 1.00 (fit) and ~1.06 (fill+zoom). We wrap in a fixed-size
            # CompositeVideoClip so the output stays a deterministic 1080x1920 —
            # this is critical: variable-size clips make concatenate_videoclips
            # miscompute timing, which caused all images to play in the first half.
            base = clip.resize(1.06).set_position("center")
            if idx % 2 == 0:
                # Zoom in: 0.943 → 1.000 (relative to the 1.06x base → 1.00 → 1.06 effective)
                kb = base.resize(lambda t, d=this_dur: (1 / 1.06) + (1 - 1 / 1.06) * (t / d))
            else:
                # Zoom out: 1.000 → 0.943
                kb = base.resize(lambda t, d=this_dur: 1 - (1 - 1 / 1.06) * (t / d))
            kb = kb.set_position("center")

            clip = CompositeVideoClip([kb], size=(1080, 1920)).set_duration(this_dur)

            # Subtle crossfade in (except first clip) for smooth transitions
            if idx > 0 and this_dur > crossfade:
                clip = clip.crossfadein(crossfade)

            # Re-assert duration just in case
            clip = clip.set_duration(this_dur)

            clips.append(clip)
            tot_dur += this_dur

        # Negative padding overlaps clips by `crossfade` seconds for smooth blending.
        # Duration was pre-compensated so composed total == max_duration (no black tail).
        padding = -crossfade if len(clips) > 1 else 0
        final_clip = concatenate_videoclips(clips, padding=padding, method="compose")
        final_clip = final_clip.set_fps(30)
        # Trim any float drift so video matches TTS exactly
        if final_clip.duration > max_duration:
            final_clip = final_clip.subclip(0, max_duration)
        random_song = choose_random_song(getattr(self, "subject", ""))

        subtitles = None
        try:
            print(colored("[+] Building karaoke subtitles...", "blue"), flush=True)

            # If TTS didn't provide word timestamps, estimate them
            if not self.word_timestamps:
                self.word_timestamps = self._estimate_word_timestamps(max_duration)

            subtitles = self._build_karaoke_subtitles(max_duration)

            if subtitles is not None:
                print(colored("[+] Karaoke subtitles ready.", "green"), flush=True)
        except Exception as e:
            warning(f"Failed to generate subtitles, continuing without subtitles: {e}")

        print(colored("[+] Mixing audio...", "blue"), flush=True)
        random_song_clip = AudioFileClip(random_song).set_fps(44100)

        # Loop background music if shorter than TTS, then trim to match
        if random_song_clip.duration < tts_clip.duration:
            loops_needed = int(tts_clip.duration // random_song_clip.duration) + 1
            random_song_clip = concatenate_audioclips([random_song_clip] * loops_needed)
        random_song_clip = random_song_clip.subclip(0, tts_clip.duration)

        # Background music at 15% volume (audible but won't overpower voice)
        random_song_clip = random_song_clip.fx(afx.volumex, 0.15)
        comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), random_song_clip])

        final_clip = final_clip.set_audio(comp_audio)
        # Force exact duration match so no black frames can appear at the tail
        final_clip = final_clip.set_duration(max_duration)

        if subtitles is not None:
            # Clamp subtitles to video duration so they can't extend the composite
            # past the last image (which would produce a black tail with subs visible).
            subtitles = subtitles.set_duration(max_duration)
            final_clip = CompositeVideoClip(
                [final_clip, subtitles], size=(1080, 1920)
            ).set_duration(max_duration)

        print(colored("[+] Rendering final video (this may take a minute)...", "blue"), flush=True)
        final_clip.write_videofile(combined_image_path, threads=threads)

        success(f'Wrote Video to "{combined_image_path}"')

        return combined_image_path

    def generate_video(self, tts_instance: TTS, custom_topic: str = "", image_mode: str = "ai") -> str:
        """
        Generates a YouTube Short based on the provided niche and language.

        Args:
            tts_instance (TTS): Instance of TTS Class.
            custom_topic (str): Optional user-provided topic. If given, skips auto topic generation.
            image_mode (str): "ai" (default) uses AI image generators first.
                              "photos" uses real photos (Wikimedia / Pexels / Pixabay) first.

        Returns:
            path (str): The path to the generated MP4 File, or empty string if cancelled.
        """
        # Reset per-video state. Without this, a 2nd run in the same session
        # inherits stale paths from the 1st (whose PNGs were wiped by
        # rem_temp_files()), inflating n_imgs in combine() and leaving half
        # the short as a black tail.
        self.images = []
        self.image_prompts = []
        self.word_timestamps = None
        self.tts_path = None
        self.subtitles_path = None
        self._used_stock_urls = set()
        # Shorts upload fast — no need for the long-video patient wait.
        self._is_long_video = False

        # Generate the Topic (or use the user-provided one)
        if custom_topic and custom_topic.strip():
            self.subject = custom_topic.strip()
            if get_verbose():
                info(f" => Using custom topic: {self.subject}")
        else:
            self.generate_topic()

        # Duplicate guard: generate_topic returns "" when it cannot produce a
        # topic that has not already been used on this channel. We refuse to
        # publish a repeat, so bail out cleanly.
        if not self.subject or not self.subject.strip():
            error(
                "Aborting Short: no unique topic available. "
                "No video will be generated or uploaded."
            )
            self.video_path = ""
            return ""

        # Generate the Script
        self.generate_script()

        # Generate the Metadata
        self.generate_metadata()

        # Generate the Image Prompts (AI-style or search-query-style)
        self.generate_prompts(image_mode=image_mode)

        # Generate the Images (parallel batch for speed)
        self.generate_images_batch(self.image_prompts, image_mode=image_mode)

        # Generate the TTS
        self.generate_script_to_speech(tts_instance)

        # Combine everything
        path = self.combine()

        if get_verbose():
            info(f" => Generated Video: {path}")

        self.video_path = os.path.abspath(path)
        self._persist_metadata_sidecar(is_long=False)

        return path

    # ============================================================
    #  LONG VIDEO PIPELINE (15-20 minutes, 16:9 landscape)
    # ============================================================

    def generate_long_script(self) -> str:
        """
        Generates a structured long-form script for a 15-20 minute video
        (~2700-3500 words at documentary narration speed).

        Two strategies, picked by active LLM provider:
          - Gemini Flash 2.5/3 → SINGLE call (large output window handles 3000+ words).
            Falls back to per-section if the single call returns too short.
          - Pollinations / Ollama / others → ONE LLM CALL PER SECTION (12 calls)
            because free / small models cap output around 400-700 words per call.
        """
        lang = self.language

        # ---- FAST PATH: Gemini can produce the whole script in a single call ----
        try:
            from llm_provider import get_active_provider
            active_provider = get_active_provider()
        except Exception:
            active_provider = ""

        if active_provider == "gemini":
            SINGLE_CALL_ATTEMPTS = 3
            info(f" [Script] Gemini detected — trying single-call fast path (up to {SINGLE_CALL_ATTEMPTS} attempts)...")
            best_short = ""  # remember the longest under-2000-word draft in case all attempts come up short
            for attempt in range(1, SINGLE_CALL_ATTEMPTS + 1):
                try:
                    full = self._generate_long_script_single_call(lang)
                    word_count = len(full.split())
                    if word_count >= 2000:
                        full = self._postprocess_long_script(full)
                        self.script = full
                        self._persist_long_script(full)
                        info(f" => Generated long script: {len(full.split())} words (~{len(full.split()) // 165} min) (single-call attempt {attempt})")
                        return full
                    warning(f"   Single-call attempt {attempt}/{SINGLE_CALL_ATTEMPTS} returned only {word_count} words.")
                    if word_count > len(best_short.split()):
                        best_short = full
                except Exception as e:
                    warning(f"   Single-call attempt {attempt}/{SINGLE_CALL_ATTEMPTS} failed: {str(e)[:200]}")
            warning("   All single-call attempts came up short or failed; falling back to per-section.")

        # ---- DEFAULT PATH: per-section for capped providers ----
        full = self._generate_long_script_sectional(lang)
        full = self._postprocess_long_script(full)
        self.script = full
        self._persist_long_script(full)
        return full

    def _postprocess_long_script(self, script: str) -> str:
        """
        Final sanity pass on a long script:
        - Strip any LLM preamble that survived per-call cleaning ("Por supuesto", "Claro,", etc).
        - Cap total length to ~3700 words (≈ 22 min) to prevent 50-min runaways.
        - Warn (not fail) if the first 200 words don't mention any topic keyword,
          which is a strong hint the LLM went off-topic.
        """
        text = script.strip()

        # Strip leading conversational preamble paragraphs the per-call cleaner can miss.
        preamble_starters = (
            r"^\s*(¡?(por supuesto|claro|desde luego|con gusto|aquí (te|te lo|tienes|está|va)|"
            r"a continuación|sure|of course|certainly|absolutely|here(?:'s| is)|i'?ll|let me))[^\n]*\n+"
        )
        for _ in range(3):  # peel up to 3 preamble lines if stacked
            new = re.sub(preamble_starters, "", text, count=1, flags=re.IGNORECASE)
            if new == text:
                break
            text = new

        # Hard cap so we never exceed ~22 min of narration. Cut on a sentence boundary near the cap.
        WORD_CAP = 3700
        words = text.split()
        if len(words) > WORD_CAP:
            warning(f"   Script {len(words)} words → capping to ~{WORD_CAP} words.")
            cut_text = " ".join(words[:WORD_CAP])
            # Try to end on a sentence boundary so the cap doesn't sound abrupt.
            last_period = max(cut_text.rfind("."), cut_text.rfind("!"), cut_text.rfind("?"))
            if last_period > len(cut_text) * 0.7:
                cut_text = cut_text[: last_period + 1]
            text = cut_text

        # Topic relevance — be strict. The script MUST mention significant tokens
        # from self.subject. If not, abort: a wrong-topic script is worse than no video.
        def _norm(s: str) -> str:
            import unicodedata
            s = unicodedata.normalize("NFKD", s.lower())
            return "".join(c for c in s if not unicodedata.combining(c))

        subj_tokens = {
            _norm(t) for t in re.findall(r"[A-Za-zÀ-ÿ]+", self.subject or "")
            if len(t) > 4
        }
        if subj_tokens:
            full_norm = _norm(text)
            mentions = sum(1 for tok in subj_tokens if tok in full_norm)
            head_norm = _norm(" ".join(text.split()[:300]))
            head_mentions = sum(1 for tok in subj_tokens if tok in head_norm)

            # If the topic appears NOWHERE in the entire script → off-topic, abort.
            if mentions == 0:
                raise RuntimeError(
                    f"Aborting: generated script never mentions any keyword from the topic "
                    f"({', '.join(list(subj_tokens)[:5])}). The LLM drifted entirely. "
                    f"Re-run the generation."
                )
            # If the topic appears in <30% of expected places, warn loudly.
            if mentions < max(1, len(subj_tokens) // 3):
                warning(
                    f"   Topic only mentioned {mentions} of {len(subj_tokens)} keywords — "
                    f"script may be partially off-topic. Inspect before publishing."
                )
            # If the intro never mentions the topic, warn (intro should hook the topic).
            if head_mentions == 0:
                warning(
                    f"   Script intro doesn't mention the topic. Inspect the first paragraph."
                )

        return text.strip()

    def _persist_long_script(self, script: str) -> None:
        """Save the final long script to .mp/script_<uuid>.txt for inspection / debugging."""
        try:
            path = os.path.join(ROOT_DIR, ".mp", f"script_{uuid4()}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Topic: {self.subject}\n")
                f.write(f"# Words: {len(script.split())}\n")
                f.write(f"# Estimated duration: ~{len(script.split()) // 165} min\n")
                f.write("# " + ("=" * 60) + "\n\n")
                f.write(script)
            info(f"   [Script] Saved to: {path}")
        except Exception as e:
            warning(f"   Could not persist script: {e}")

    def _generate_long_script_single_call(self, lang: str) -> str:
        """
        Ask the LLM for the entire 15-20 min script in one call.
        Designed for high-output-window providers (Gemini Flash 2.5/3).
        """
        # Series-aware: when the active series defines a brief / themes, build
        # the structure description from those themes so the single-call prompt
        # gets the same immersive guidance as the sectional path.
        series = getattr(self, "active_series", None) or {}
        script_brief = (series.get("script_brief") or "").strip()
        series_themes = series.get("section_themes") or []

        if script_brief:
            info(f" => Using series narrative brief: {series.get('id', '')}")

        if isinstance(series_themes, list) and len(series_themes) == 10:
            # Build the SECTION block from the series-defined chronological themes.
            sections_block = "\n\n".join(
                f"[SECTION {i+1}: <título corto>]\n{theme} (10-14 oraciones, 250-350 palabras)."
                for i, theme in enumerate(series_themes)
            )
        else:
            # Default documentary structure.
            sections_block = """[SECTION 1: <título corto>]
Aspecto fundacional o más fascinante del tema (10-14 oraciones, 250-350 palabras).

[SECTION 2: <título corto>]
Ángulo distinto o construcción sobre la sección anterior, con anécdotas concretas (10-14 oraciones, 250-350 palabras).

[SECTION 3: <título corto>]
Conexiones sorprendentes o hechos poco conocidos (10-14 oraciones, 250-350 palabras).

[SECTION 4: <título corto>]
Profundización con datos concretos, fechas, lugares o personas reales (10-14 oraciones, 250-350 palabras).

[SECTION 5: <título corto>]
Clímax intermedio — momento más impactante hasta aquí (10-14 oraciones, 250-350 palabras).

[SECTION 6: <título corto>]
Nuevo ángulo o consecuencia que surge de lo anterior (10-14 oraciones, 250-350 palabras).

[SECTION 7: <título corto>]
Detalles narrativos profundos, anécdotas o testimonios (10-14 oraciones, 250-350 palabras).

[SECTION 8: <título corto>]
Conexión inesperada o paralelismo con otro ámbito (10-14 oraciones, 250-350 palabras).

[SECTION 9: <título corto>]
Clímax final — la revelación o giro más fuerte (10-14 oraciones, 250-350 palabras).

[SECTION 10: <título corto>]
Consecuencias, legado o impacto del tema en la actualidad (10-14 oraciones, 250-350 palabras)."""

        brief_block = (
            f"\nDIRECTIVA NARRATIVA DE LA SERIE — OBLIGATORIA EN CADA PALABRA DE TU RESPUESTA:\n{script_brief}\n"
            if script_brief else ""
        )

        prompt = f"""Eres un narrador experto de documentales y guionista profesional.
Escribe un GUION COMPLETO de narración cautivador de 15 a 20 minutos sobre el siguiente tema.

Tema: {self.subject}
{brief_block}
ESTRUCTURA OBLIGATORIA (usa estos marcadores EXACTOS):
[INTRO]
Gancho inicial poderoso (5-7 oraciones, 120-180 palabras). Empieza con un dato impactante, pregunta provocadora o afirmación audaz.

{sections_block}

[CLOSING]
Conclusión memorable (5-7 oraciones, 120-180 palabras). Termina con una reflexión que perdure.

[OUTRO]
Despedida cálida y llamado a la acción para los últimos segundos del video, cuando aparecen las pantallas finales de YouTube (suscribirse, video recomendado). Dura 3-5 oraciones (60-100 palabras).
DEBE incluir, redactado de forma natural y orgánica:
1. Agradecer al espectador por haber visto el video.
2. Pedir que dé "me gusta" si le gustó.
3. Pedir que se SUSCRIBA al canal y active la CAMPANITA para no perderse contenido similar.
4. Una despedida cálida ("Hasta la próxima", "Hasta pronto", "Nos vemos en el siguiente video", o equivalente).
NO uses bullets, NO suene robótico — escríbelo como si lo dijeras hablando, con calidez.

REGLAS DE ESTILO:
- Escribe como un narrador apasionado, NO como un libro de texto. Lenguaje vívido y sensorial.
- Cada oración fluye naturalmente hacia la siguiente.
- Usa preguntas retóricas, comparaciones sorprendentes y ganchos emocionales.
- Oraciones CORTAS (máximo 20 palabras cada una).
- TOTAL OBLIGATORIO: entre 2700 y 3500 palabras.
- Cada sección debe aportar material NUEVO, no repetir.
- ESCRIBE TODO EN {lang}. NO uses inglés.
- NO markdown, NO viñetas, NO listas numeradas.
- NO URLs, enlaces, citas ni referencias.
- ESTRICTAMENTE PROHIBIDO escribir acotaciones de cualquier tipo. Solo texto que un narrador diría EN VOZ ALTA. NUNCA escribas:
    * "(imagen de ...)", "(imágenes de ...)", "[plano cerrado de ...]", "(escena ...)", "(secuencia ...)"
    * "(B-roll: ...)", "(B/O ...)", "(voz en off)", "(narrador:)"
    * "(música suave)", "(sonido de ...)", "(efectos)", "(silencio)"
    * "(emoji ...)", "(emoticono ...)", "(símbolo ...)"
    * "(transición)", "(fundido)", "(zoom)", "(corte)", "(cierre)"
  Si crees que necesitas describir una imagen o un sonido, NO LO HAGAS — el video ya tiene imágenes y música. Solo narra.
- NÚMEROS: escribe TODOS los números con palabras, no con dígitos. Ejemplos:
    * "hace cuatro mil quinientos años" (no "hace 4.500 años")
    * "el año mil cuatrocientos cincuenta y tres" (no "1453")
    * "el siglo dieciséis" (no "el siglo XVI" ni "el siglo 16")
    * "tres coma uno cuatro" (no "3,14")
- AÑO vs DURACIÓN — distínguelos siempre. Un AÑO es una FECHA del calendario; una DURACIÓN es el tiempo transcurrido. Son cosas distintas. Para citar un año, di "el año <año>". La fórmula "hace <N> años" expresa SOLO duración: <N> es la diferencia entre el año actual y el año del evento, NO es el año mismo. Ante la duda, nombra el año ("el año X") y NO uses la fórmula "hace X años".
- SOLO devuelve el guion completo con los 12 marcadores arriba listados. Sin preámbulo.
"""
        completion = self._clean_llm_script(self.generate_response(prompt))
        return completion

    def _generate_long_script_sectional(self, lang: str) -> str:
        """Per-section generation (12 calls) for providers with low output caps."""

        # Series-aware: when a series brief / themes are configured, use them so
        # the script follows the series voice (e.g. immersive 2nd-person POV for
        # "Un día en la historia") instead of the generic documentary structure.
        series = getattr(self, "active_series", None) or {}
        script_brief = (series.get("script_brief") or "").strip()
        series_themes = series.get("section_themes") or []
        if script_brief:
            info(f" => Using series narrative brief: {series.get('id', '')}")

        # Per-section thematic guidance — what role each section plays in the narrative arc.
        # Series-defined themes win when present and are exactly 10 entries.
        if isinstance(series_themes, list) and len(series_themes) == 10:
            section_themes = list(series_themes)
        else:
            section_themes = [
                "Aspecto fundacional o más fascinante del tema. Establece el contexto y captura la atención.",
                "Ángulo distinto o construcción sobre la sección anterior, con anécdotas concretas o ejemplos.",
                "Conexiones sorprendentes o hechos poco conocidos relacionados al tema.",
                "Profundización con datos concretos, fechas, lugares o personas reales.",
                "Clímax intermedio — el momento más impactante hasta este punto.",
                "Consecuencia o nuevo ángulo que surge a partir de lo anterior.",
                "Detalles narrativos profundos, anécdotas o testimonios.",
                "Conexión inesperada o paralelismo con otro ámbito.",
                "Clímax final — la revelación o giro más fuerte del tema.",
                "Consecuencias, legado o impacto del tema en la actualidad.",
            ]

        # Block of narrative directives prepended to every per-call prompt when
        # a series brief is active. Empty string in non-series mode (no-op).
        brief_block = (
            f"\n\nDIRECTIVA NARRATIVA DE LA SERIE — OBLIGATORIA EN CADA PALABRA DE TU RESPUESTA:\n{script_brief}\n\n"
            if script_brief else ""
        )

        def _ask_section(prompt: str, min_words: int) -> str:
            """Call the LLM with retries until we hit min_words AND the content is clean."""
            best = ""
            for attempt in range(4):
                completion = self._clean_llm_script(self.generate_response(prompt))
                # Reject the response entirely if it looks like garbage / metadata.
                if self._looks_like_garbage(completion):
                    warning(f"   chunk looked like garbage / metadata, retry {attempt + 2}/4")
                    continue
                if len(completion.split()) > len(best.split()):
                    best = completion
                if len(best.split()) >= min_words:
                    break
                if attempt < 3:
                    warning(f"   chunk short ({len(best.split())} words), retry {attempt + 2}/4")
            return best

        def _ensure_marker(text: str, marker: str) -> str:
            """Prepend the section marker if the LLM forgot it (or used a wrong one)."""
            text = text.strip()
            if not re.match(r"^\s*\[(INTRO|SECTION|CLOSING|OUTRO)", text, re.IGNORECASE):
                text = f"{marker}\n{text}"
            return text

        parts: List[str] = []
        info(f" [Script] Building 15-20 min script section by section...")

        # ---- INTRO ----
        intro_prompt = f"""Eres un narrador experto de documentales. Escribe SOLO la INTRODUCCIÓN de un guion documental sobre: {self.subject}
{brief_block}
REGLAS:
- 5-7 oraciones (120-180 palabras).
- Empieza con un gancho poderoso: dato impactante, pregunta provocadora o afirmación audaz.
- Lenguaje vívido y sensorial. Oraciones CORTAS (máximo 20 palabras).
- ESCRIBE TODO EN {lang}. NO uses inglés.
- NO uses markdown, viñetas, listas, URLs, ni meta-texto.
- ESTRICTAMENTE PROHIBIDO escribir acotaciones: nada de "(imagen ...)", "[plano ...]", "(B-roll ...)", "(música ...)", "(emoji ...)", "(transición)" etc. Solo texto hablado.
- NÚMEROS: escribe los números con palabras, no con dígitos ("mil cuatrocientos cincuenta y tres", no "1453"; "cuatro mil quinientos", no "4.500").
- AÑO vs DURACIÓN — distínguelos siempre. Un AÑO es una FECHA del calendario; una DURACIÓN es el tiempo transcurrido. Son cosas distintas. Para citar un año, di "el año <año>". La fórmula "hace <N> años" expresa SOLO duración: <N> es la diferencia entre el año actual y el año del evento, NO es el año mismo. Ante la duda, nombra el año ("el año X") y NO uses la fórmula "hace X años".
- Devuelve SOLO el texto, precedido EXACTAMENTE por la línea: [INTRO]
"""
        intro = _ensure_marker(_ask_section(intro_prompt, min_words=80), "[INTRO]")
        parts.append(intro)
        info(f"   [Script] INTRO: {len(intro.split())} words")

        # ---- SECTIONS 1-10 ----
        for i, theme in enumerate(section_themes, start=1):
            prior = "\n\n".join(parts)
            tail = " ".join(prior.split()[-250:]) if prior else ""

            section_prompt = f"""Eres un narrador experto de documentales. Estás escribiendo la SECCIÓN {i} de 10 de un guion sobre: {self.subject}
{brief_block}
Esto es lo último que ya se narró (NO lo repitas, continúa el flujo natural):
\"\"\"
{tail}
\"\"\"

Escribe SOLO la SECCIÓN {i}:
- Foco temático de esta sección: {theme}
- 10-14 oraciones (250-350 palabras).
- Lenguaje vívido y sensorial. Oraciones CORTAS (máximo 20 palabras).
- Aporta material NUEVO, no repitas ideas ya dichas.
- ESCRIBE TODO EN {lang}. NO uses inglés.
- NO uses markdown, viñetas, listas, URLs, ni meta-texto.
- ESTRICTAMENTE PROHIBIDO escribir acotaciones: nada de "(imagen ...)", "[plano ...]", "(B-roll ...)", "(música ...)", "(emoji ...)", "(transición)" etc. Solo texto hablado.
- NÚMEROS: escribe los números con palabras, no con dígitos ("mil cuatrocientos cincuenta y tres", no "1453"; "cuatro mil quinientos", no "4.500").
- AÑO vs DURACIÓN — distínguelos siempre. Un AÑO es una FECHA del calendario; una DURACIÓN es el tiempo transcurrido. Son cosas distintas. Para citar un año, di "el año <año>". La fórmula "hace <N> años" expresa SOLO duración: <N> es la diferencia entre el año actual y el año del evento, NO es el año mismo. Ante la duda, nombra el año ("el año X") y NO uses la fórmula "hace X años".
- Devuelve SOLO el texto de la sección, precedido EXACTAMENTE por una línea con: [SECTION {i}: <título breve descriptivo>]
"""
            section = _ensure_marker(_ask_section(section_prompt, min_words=180), f"[SECTION {i}: parte {i}]")
            parts.append(section)
            info(f"   [Script] SECTION {i}: {len(section.split())} words")

        # ---- CLOSING ----
        prior = "\n\n".join(parts)
        tail = " ".join(prior.split()[-300:])
        closing_prompt = f"""Eres un narrador experto de documentales. Estás escribiendo el CIERRE de un guion sobre: {self.subject}
{brief_block}
Esto es lo último que se narró:
\"\"\"
{tail}
\"\"\"

Escribe SOLO el CIERRE:
- 5-7 oraciones (120-180 palabras).
- Conclusión memorable. Termina con una reflexión que se quede con el espectador.
- Lenguaje vívido. Oraciones CORTAS (máximo 20 palabras).
- ESCRIBE TODO EN {lang}. NO uses inglés.
- NO uses markdown, viñetas, listas, URLs, ni meta-texto.
- ESTRICTAMENTE PROHIBIDO escribir acotaciones: nada de "(imagen ...)", "[plano ...]", "(B-roll ...)", "(música ...)", "(emoji ...)", "(transición)" etc. Solo texto hablado.
- NÚMEROS: escribe los números con palabras, no con dígitos ("mil cuatrocientos cincuenta y tres", no "1453").
- AÑO vs DURACIÓN — distínguelos siempre. Un AÑO es una FECHA del calendario; una DURACIÓN es el tiempo transcurrido. Son cosas distintas. Para citar un año, di "el año <año>". La fórmula "hace <N> años" expresa SOLO duración: <N> es la diferencia entre el año actual y el año del evento, NO es el año mismo. Ante la duda, nombra el año ("el año X") y NO uses la fórmula "hace X años".
- Devuelve SOLO el texto, precedido EXACTAMENTE por la línea: [CLOSING]
"""
        closing = _ensure_marker(_ask_section(closing_prompt, min_words=80), "[CLOSING]")
        parts.append(closing)
        info(f"   [Script] CLOSING: {len(closing.split())} words")

        # ---- OUTRO (CTA + farewell — coincides with YouTube's end screen overlay) ----
        prior = "\n\n".join(parts)
        tail = " ".join(prior.split()[-200:])
        outro_prompt = f"""Eres un narrador experto de documentales. Estás escribiendo la DESPEDIDA FINAL de un guion sobre: {self.subject}

Esto es lo último que se narró:
\"\"\"
{tail}
\"\"\"

Escribe SOLO la DESPEDIDA, pensada para los últimos segundos del video cuando aparecen las pantallas finales de YouTube (suscribirse, video recomendado).

ESTRUCTURA OBLIGATORIA (3-5 oraciones, 60-100 palabras), redactada de forma natural y orgánica como si la dijeras hablando con calidez (NO bullets, NO suene robótico):
1. Agradece al espectador por haber visto el video.
2. Pídele que dé "me gusta" si le gustó.
3. Pídele que se SUSCRIBA al canal y active la CAMPANITA para no perderse contenido similar.
4. Despídete cálidamente ("Hasta la próxima", "Hasta pronto", "Nos vemos en el siguiente video", o equivalente).

REGLAS:
- ESCRIBE TODO EN {lang}. NO uses inglés.
- Tono cálido, cercano, humano — como un amigo, no como una máquina.
- Oraciones CORTAS (máximo 20 palabras).
- NO uses markdown, viñetas, listas, URLs, hashtags ni meta-texto.
- ESTRICTAMENTE PROHIBIDO escribir acotaciones: nada de "(imagen ...)", "[plano ...]", "(B-roll ...)", "(música ...)", "(emoji ...)", "(transición)" etc. Solo texto hablado.
- Devuelve SOLO el texto, precedido EXACTAMENTE por la línea: [OUTRO]
"""
        outro = _ensure_marker(_ask_section(outro_prompt, min_words=40), "[OUTRO]")
        parts.append(outro)
        info(f"   [Script] OUTRO: {len(outro.split())} words")

        full = "\n\n".join(parts).strip()
        word_count = len(full.split())

        if not full or word_count < 600:
            raise RuntimeError(f"Failed to generate long script (only {word_count} words)")

        info(f" => Sectional script built: {word_count} words (~{word_count // 165} min)")
        return full

    def generate_long_metadata(self) -> dict:
        """
        Generates metadata optimized for long-form YouTube videos.
        """
        series = getattr(self, "active_series", None)
        title_template = (series or {}).get("title_template", "").strip()

        if title_template:
            # Series mode: ask the LLM only for the placeholder values, then format
            # the template ourselves. This guarantees every video in the series
            # ends up with the same title shape.
            placeholders = re.findall(r"\{(\w+)\}", title_template)
            if placeholders:
                fields_desc = ", ".join(f'"{p}"' for p in placeholders)
                raw = self.generate_response(
                    f"Vas a producir los datos para el título de un video de la serie "
                    f"\"{series.get('id', '')}\".\n"
                    f"TEMA DEL VIDEO: {self.subject}\n\n"
                    f"Devuelve SOLO un objeto JSON con estos campos exactos: {fields_desc}.\n"
                    f"Cada valor debe ir en {self.language}, en MAYÚSCULAS, sin comillas, "
                    f"sin tildes invertidas, conciso (1-4 palabras por campo), y derivado "
                    f"directamente del tema. Ejemplo de formato: {{\"rol\": \"SAMURÁI\", "
                    f"\"lugar\": \"EL JAPÓN FEUDAL\"}}.\n"
                    f"NO devuelvas markdown, NO devuelvas explicación, SOLO el JSON."
                )
                raw = str(raw).replace("```json", "").replace("```", "").strip()
                values = {}
                try:
                    values = json.loads(raw)
                except Exception:
                    m = re.search(r"\{.*\}", raw, re.DOTALL)
                    if m:
                        try:
                            values = json.loads(m.group())
                        except Exception:
                            values = {}
                # Default each missing placeholder to the subject in upper-case so
                # we never crash on a malformed LLM response.
                fallback = re.sub(r"\s+", " ", self.subject).strip().upper()
                filled = {p: str(values.get(p, fallback)).strip().upper() or fallback
                          for p in placeholders}
                title = title_template.format(**filled)
            else:
                # Template has no placeholders → use it verbatim.
                title = title_template
        else:
            title = self.generate_response(
                f"Genera un título para un video largo de YouTube sobre: {self.subject}.\n"
                f"REQUISITOS DEL TÍTULO:\n"
                f"- Máximo 70 caracteres.\n"
                f"- Clickbait MODERADO: incluye exactamente 1 o 2 palabras clave en MAYÚSCULAS para enfatizar "
                f"(ejemplos: SECRETO, NUNCA, JAMÁS, NADIE, OCULTO, VERDAD, IMPOSIBLE, REAL, PROHIBIDO, INCREÍBLE).\n"
                f"- Despierta curiosidad o promete una revelación.\n"
                f"- SIN signos de exclamación ni de interrogación.\n"
                f"- SIN emojis, SIN comillas, SIN hashtags.\n"
                f"- ESCRIBE EN {self.language}.\n"
                f"Devuelve SOLO el título, sin explicación."
            )

        # Strip any quotes the LLM might add (regular, curly, single)
        title = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', title.strip()).strip()

        # Always strip hashtags from long-video titles \u2014 the LLM ignores the rule sometimes.
        title = re.sub(r"#\w+", "", title)
        title = re.sub(r"\s{2,}", " ", title).strip(" -\u2013\u2014:|")

        if len(title) > 100:
            title = title[:100]

        description = self.generate_response(
            f"""Genera una descripción de YouTube para un video largo con este guion:

{self.script[:2000]}

Incluye:
- Un resumen breve de 2 oraciones del video
- 5-8 hashtags relevantes
- Un llamado a la acción (suscribirse, dar like, comentar)

NO pongas comillas alrededor de la descripción.
ESCRIBE TODO EN {self.language}. Solo devuelve la descripción."""
        )

        # Strip any quotes the LLM might add (regular, curly, single)
        description = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', description.strip()).strip()

        self.metadata = {"title": title, "description": description}
        return self.metadata

    def generate_thumbnail(self) -> str:
        """
        Build a clickbait 1280x720 thumbnail for the long video:
          1. LLM produces a dramatic visual prompt + 2-4 punchy overlay words.
          2. Leonardo AI (fallback Pollinations) renders the background.
          3. Pillow upscales to 1280x720, darkens the bottom for legibility,
             and stamps the overlay text in Impact-style with thick black stroke.
        Sets self.thumbnail_path and returns it. Returns "" if generation fails.
        """
        from PIL import Image, ImageDraw, ImageFont
        import io

        info("Generating thumbnail...")
        self.thumbnail_path = ""

        video_title = (self.metadata or {}).get("title", "") if hasattr(self, "metadata") else ""

        # Series mode: overlay text is pinned, so we skip the entire LLM-overlay
        # path and only ask the LLM for a visual prompt for the background image.
        series = getattr(self, "active_series", None)
        series_overlay = (series or {}).get("thumbnail_overlay", "").strip()

        # Build the set of allowed tokens (lowercased, accent-stripped) from title + topic.
        # Any LLM-generated overlay word must derive from this vocabulary or it gets rejected
        # (this is what catches hallucinations like "TÁQUILAS SE HOJAN").
        def _norm(s: str) -> str:
            import unicodedata
            s = unicodedata.normalize("NFKD", s.lower())
            return "".join(c for c in s if not unicodedata.combining(c))

        title_topic_text = f"{video_title} {self.subject}".lower()
        allowed_tokens = {
            _norm(t) for t in re.findall(r"[A-Za-zÀ-ÿ]+", title_topic_text) if len(t) > 2
        }

        visual_prompt = ""
        overlay_words = ""

        if series_overlay:
            overlay_words = series_overlay.upper()
            # Ask the LLM for a visual prompt only (no overlay words) — keeps the
            # series identity stable while letting the background still match the topic.
            visual_prompt = str(self.generate_response(
                f"Write a SINGLE English image-generation prompt for a YouTube thumbnail "
                f"about: {self.subject}.\n"
                f"REQUIREMENTS:\n"
                f"- 40-70 words.\n"
                f"- Describe a SPECIFIC dramatic scene tied to the topic. Name actual people, "
                f"places, objects, era, clothing, architecture or symbols. Use proper nouns "
                f"when relevant.\n"
                f"- ONE single dramatic scene, not a list of unrelated elements.\n"
                f"- Composition cues only — describe framing, lighting direction, depth, focus, "
                f"mood. Examples: 'dramatic side lighting', 'high contrast', 'shallow depth of "
                f"field', 'low angle', 'intense expression on the subject'. Style-agnostic.\n"
                f"- DO NOT mention rendering style, medium, or technique. NEVER write "
                f"'photorealistic', 'cinematic film look', 'cartoon', 'anime', '3D render', "
                f"'watercolor', '8K', 'photograph', 'illustration', or any similar word that "
                f"locks in a visual style — the channel's art style is added separately.\n"
                f"- End with: no text, no letters, no logos, no watermark.\n"
                f"- Return ONLY the prompt itself. No quotes, no preamble, no explanation."
            )).strip().strip('"\'`')
            info(f"Thumbnail: using series overlay '{overlay_words}'")

        # Step 1: ask LLM for the visual concept + overlay words.
        # Skipped entirely in series mode — overlay is pinned and visual was
        # built above without the JSON ceremony.
        if not series_overlay:
            llm_raw = str(self.generate_response(
                f"""Design a YouTube thumbnail for this video.

VIDEO TITLE: {video_title or "(see topic)"}
TOPIC: {self.subject}

Return ONLY a JSON object with two fields:

- "visual": ENGLISH prompt (40-70 words) for an AI image generator. CRITICAL RULES:
  * The image MUST be visually unmistakable as the topic — name the actual SPECIFIC people, places, objects, clothing, architecture, era, or symbols from the topic. Use proper nouns when relevant.
  * Build ONE single dramatic scene, not a list of unrelated elements.
  * Composition cues only — describe framing, lighting direction, depth, focus, mood. Examples: "dramatic side lighting", "high contrast", "shallow depth of field", "low angle", "intense expression on the subject". Style-agnostic.
  * DO NOT mention rendering style, medium, or technique. NEVER write "photorealistic", "cinematic film look", "cartoon", "anime", "3D render", "watercolor", "8K", "photograph", "illustration", or any similar word that locks in a visual style — the channel's art style is added separately downstream.
  * End the prompt with: "no text, no letters, no logos, no watermark".
  * FORBIDDEN: generic phrases like "person looking", "mysterious figure", "abstract concept" — be SPECIFIC.

- "words": a CLICKBAIT TEASER PHRASE in {self.language}, ALL UPPERCASE, for the thumbnail overlay. ABSOLUTELY CRITICAL RULES:
  * Length: 3 to 6 words forming a COMPLETE PUNCHY PHRASE. NEVER return a single word.
  * It must SOUND like a YouTube clickbait teaser — provoke curiosity, hint at a revelation, or pose a question fragment. It is NOT a label.
  * It must be CLEARLY tied to the video's title or topic — pick the most charged, SPECIFIC words: proper names, places, dates, concrete actions, key objects.
  * EVERY WORD must already appear (literally or as a clear root form) in the VIDEO TITLE or TOPIC above. DO NOT INVENT WORDS. Each word must be a correctly-spelled real word in {self.language}.
  * VARY THE ANGLE between videos — pick the most specific hook from THIS topic. Available patterns (use whichever fits the topic best):
      - Proper-noun reveal: "ANUBIS Y EL JUICIO FINAL", "EL DIARIO DE TUTANKAMÓN".
      - Date/place anchor: "1959, EL PASO DYATLOV", "LA NOCHE DEL MARY CELESTE".
      - Question fragment: "POR QUÉ DESAPARECIERON TODOS", "QUIÉN ENCONTRÓ EL CUERPO".
      - Concrete action: "PLANTÓ UN BOSQUE POR ELLA", "CRUZARON LOS ANDES A PIE".
      - Revelation hook: "LO QUE ENCONTRARON ALLÍ", "NADIE VOLVIÓ A VERLOS".
      - Contrast/twist: "ERA UN ANCIANO CIEGO", "EL ÚLTIMO MENSAJE DE OLOF".
  * ABSOLUTELY FORBIDDEN openings — never start the overlay with any of these, regardless of what the title says: "EL SECRETO", "SECRETO DE", "SECRETO QUE", "EL MISTERIO", "MISTERIO DE", "MISTERIO QUE". Even if the title contains those words, the thumbnail overlay MUST pick a different angle (a name, a place, a date, an action, a question fragment) from the patterns above. The title and the thumbnail overlay should NOT say the same thing — the overlay highlights a different specific hook.
  * BAD examples: "SECRETO" (single word, no teaser), "NADIE LO SABE" (cliché), "INCREÍBLE" (generic), "EL SECRETO DE X" / "EL MISTERIO DE X" (forbidden openings — too generic).
  * AVOID these overused clichés entirely: "NADIE LO SABE", "NUNCA LO SABE", "TE VA A IMPACTAR", "INCREÍBLE", "JAMÁS LO CREERÁS".

Return ONLY the JSON. No markdown, no explanation."""
            )).replace("```json", "").replace("```", "").strip()

            try:
                data = json.loads(llm_raw)
                visual_prompt = str(data.get("visual", "")).strip()
                overlay_words = str(data.get("words", "")).strip().upper()
            except Exception:
                match = re.search(r"\{.*\}", llm_raw, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group())
                        visual_prompt = str(data.get("visual", "")).strip()
                        overlay_words = str(data.get("words", "")).strip().upper()
                    except Exception:
                        pass

            BANNED_OVERLAYS = {
                "NADIE LO SABE", "NUNCA LO SABE", "TE VA A IMPACTAR",
                "INCREÍBLE", "INCREIBLE", "JAMÁS LO CREERÁS", "JAMAS LO CREERAS",
            }

            # The LLM keeps defaulting to "EL SECRETO DE ..." / "EL MISTERIO DE ..."
            # for almost every video. Reject those openings unconditionally —
            # the overlay must pick a more specific angle even when the title
            # itself uses those words.
            FORBIDDEN_OVERLAY_PREFIXES = (
                "el secreto", "secreto de", "secreto que",
                "el misterio", "misterio de", "misterio que",
            )

            def _validate_overlay(candidate: str) -> bool:
                """Reject if too short, banned, lazy-default, or hallucinated."""
                if not candidate:
                    return False
                if candidate in BANNED_OVERLAYS:
                    return False
                norm_cand = _norm(candidate)
                if any(norm_cand.startswith(p) for p in FORBIDDEN_OVERLAY_PREFIXES):
                    return False
                STOP = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "o",
                        "que", "por", "para", "con", "en", "a", "su", "sus", "lo"}
                words = [_norm(w) for w in re.findall(r"[A-Za-zÀ-ÿ]+", candidate)]
                # Reject one-word overlays — clickbait needs a phrase.
                if len(words) < 3:
                    return False
                content_words = [w for w in words if w not in STOP]
                if not content_words:
                    return False
                for w in content_words:
                    if not any(w == a or w in a or a in w for a in allowed_tokens):
                        return False
                return True

            if overlay_words and not _validate_overlay(overlay_words):
                warning(f"Thumbnail: LLM overlay '{overlay_words}' rejected (hallucinated, banned, or lazy default).")
                overlay_words = ""

        if not visual_prompt:
            # Style-neutral fallback — composition cues only. The channel's art
            # style is appended downstream by `_apply_channel_style`, so this
            # prompt MUST NOT lock in a rendering medium ("cinematic",
            # "photorealistic", etc.) that would fight cartoon/anime channels.
            visual_prompt = (
                f"Dramatic close-up related to {self.subject}, "
                f"intense expression on the subject, dramatic side lighting, "
                f"dark moody background, high contrast, no text"
            )

        # Deterministic fallback path (always coherent with title — never hallucinates).
        # Helper used by every fallback path below — strips accents and matches
        # SECRETO/SECRETOS/MISTERIO/MISTERIOS so we can drop those words wherever
        # they appear, regardless of source.
        def _is_secreto_misterio(word: str) -> bool:
            """True for SECRETO/SECRETOS/MISTERIO/MISTERIOS (any case, with or without accents)."""
            w = re.sub(r"[ÁÉÍÓÚÜáéíóúü]", lambda m: {
                "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ü": "U",
                "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u",
            }[m.group()], word).upper()
            return w in {"SECRETO", "MISTERIO", "SECRETOS", "MISTERIOS"}

        if not overlay_words and video_title:
            clean_title = re.sub(r"[¿?¡!,.:;\"'“”‘’]", "", video_title).strip()
            tw = clean_title.split()
            STOP = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "o",
                    "que", "por", "qué", "para", "con", "en", "a", "su", "sus", "lo"}

            # 1. Find UPPERCASE keyword (the title generator always puts 1-2 in caps) and
            #    grab a wider window around it for a proper teaser phrase (3-5 words).
            #    Skip SECRETO / MISTERIO so the overlay doesn't keep defaulting
            #    to "EL SECRETO DE X" — pick the next caps word if there is one.
            CAPS_SKIP = {"SECRETO", "MISTERIO", "SECRETOS", "MISTERIOS"}
            caps_idx = next(
                (i for i, w in enumerate(tw)
                 if re.match(r"^[A-ZÁÉÍÓÚÜÑ]{4,}$", w)
                 and re.sub(r"[ÁÉÍÓÚÜ]", lambda m: {"Á": "A", "É": "E", "Í": "I",
                                                    "Ó": "O", "Ú": "U", "Ü": "U"}[m.group()], w)
                 not in CAPS_SKIP),
                None,
            )

            if caps_idx is not None:
                start = max(0, caps_idx - 2)
                end = min(len(tw), caps_idx + 4)
                chunk = tw[start:end]
                # Drop SECRETO/MISTERIO from the chunk — we never want them on a thumbnail.
                chunk = [w for w in chunk if not _is_secreto_misterio(w)]
                while chunk and chunk[0].lower() in STOP:
                    chunk = chunk[1:]
                while chunk and chunk[-1].lower() in STOP:
                    chunk = chunk[:-1]
                # Cap at 5 words to keep it readable on a thumbnail.
                if len(chunk) > 5:
                    chunk = chunk[:5]
                # Need at least 3 words for a real teaser phrase.
                if len(chunk) >= 3:
                    overlay_words = " ".join(chunk).upper()

            # 2. No usable caps window → take the first 4-5 meaningful words from the title.
            if not overlay_words:
                meaningful = [
                    w for w in tw
                    if w.lower() not in STOP and len(w) > 2
                    and not _is_secreto_misterio(w)
                ]
                if len(meaningful) >= 3:
                    overlay_words = " ".join(meaningful[:5]).upper()

            if overlay_words:
                warning(f"Thumbnail: derived overlay from title: {overlay_words}")

        # Absolute fallback so the thumbnail is never wordless.
        if not overlay_words:
            STOP = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "o",
                    "que", "por", "qué", "para", "con", "en", "a"}
            topic_words = [
                w for w in re.findall(r"[A-Za-zÀ-ÿ]+", self.subject or "")
                if w.lower() not in STOP and len(w) > 3
                and not _is_secreto_misterio(w)
            ][:5]
            overlay_words = " ".join(topic_words).upper() if topic_words else "DESCUBRE LA VERDAD"
            warning(f"Thumbnail: using topic-derived overlay text: {overlay_words}")

        # Step 2: render the background image (Leonardo AI first, then Pollinations).
        # Append the channel's image_style suffix so the thumbnail matches the video's look.
        styled_visual_prompt = self._apply_channel_style(visual_prompt)
        if get_verbose() and styled_visual_prompt != visual_prompt:
            info(" => Thumbnail: applied channel art style")

        bg_bytes = None
        for name, fn in (
            ("Leonardo AI", self._try_leonardo_landscape),
            ("Pollinations FLUX 16:9", self._try_pollinations_landscape),
        ):
            try:
                bg_bytes = fn(styled_visual_prompt)
                if bg_bytes and len(bg_bytes) > 5000:
                    break
                bg_bytes = None
            except Exception as e:
                if get_verbose():
                    warning(f"Thumbnail bg via {name} failed: {str(e)[:120]}")
                bg_bytes = None

        THUMB_W, THUMB_H = 1280, 720

        if bg_bytes:
            bg = Image.open(io.BytesIO(bg_bytes)).convert("RGB").resize(
                (THUMB_W, THUMB_H), Image.LANCZOS
            )
        else:
            warning("Thumbnail providers all failed; using gradient background.")
            bg = Image.new("RGB", (THUMB_W, THUMB_H))
            d = ImageDraw.Draw(bg)
            for y in range(THUMB_H):
                t = y / THUMB_H
                d.line(
                    [(0, y), (THUMB_W, y)],
                    fill=(int(20 + 80 * t), int(10 + 30 * t), int(60 + 90 * t)),
                )

        # Step 3: darken the bottom-LEFT corner so the overlay reads well there.
        # Combine a vertical "bottom darker" gradient with a horizontal "left darker" one,
        # giving a corner-vignette feel that protects the right-side image content.
        import numpy as np
        veil_start_y = int(THUMB_H * 0.45)
        veil_end_x = int(THUMB_W * 0.70)
        ys = np.arange(THUMB_H).reshape(-1, 1).astype(np.float32)
        xs = np.arange(THUMB_W).reshape(1, -1).astype(np.float32)
        v_factor = np.clip((ys - veil_start_y) / max(1, THUMB_H - veil_start_y), 0.0, 1.0)
        h_factor = np.clip(1.0 - (xs / max(1, veil_end_x)), 0.0, 1.0)
        alpha_field = (210.0 * v_factor * h_factor).astype(np.uint8)
        veil_arr = np.zeros((THUMB_H, THUMB_W, 4), dtype=np.uint8)
        veil_arr[..., 3] = alpha_field
        veil = Image.fromarray(veil_arr, "RGBA")
        bg = Image.alpha_composite(bg.convert("RGBA"), veil).convert("RGB")

        # Step 4: stamp overlay text in the BOTTOM-LEFT, left-aligned (Impact font for clickbait look).
        if overlay_words:
            font_path = None
            series_font = (series or {}).get("thumbnail_font", "").strip()
            font_candidates = []
            if series_font:
                # Series-specific font wins. Accept either an absolute path, a
                # bare filename in C:\Windows\Fonts, or a name in fonts/.
                if os.path.isabs(series_font):
                    font_candidates.append(series_font)
                else:
                    font_candidates.append(os.path.join(r"C:\Windows\Fonts", series_font))
                    font_candidates.append(os.path.join(get_fonts_dir(), series_font))
            font_candidates.extend([
                r"C:\Windows\Fonts\impact.ttf",
                r"C:\Windows\Fonts\arialbd.ttf",
                os.path.join(get_fonts_dir(), get_font()),
            ])
            for cand in font_candidates:
                if cand and os.path.isfile(cand):
                    font_path = cand
                    break

            # Wrap the overlay so each line fits within ~55% of the width (left half + a bit).
            margin_left = 60
            margin_right = THUMB_W - int(THUMB_W * 0.42)  # right edge of text area
            max_w = margin_right - margin_left

            def _wrap(text: str, fnt) -> list:
                """Greedy word-wrap so no line exceeds max_w pixels."""
                wrapped, current = [], []
                tmp_draw = ImageDraw.Draw(bg)
                for w in text.split():
                    trial = " ".join(current + [w])
                    if tmp_draw.textbbox((0, 0), trial, font=fnt)[2] <= max_w:
                        current.append(w)
                    else:
                        if current:
                            wrapped.append(" ".join(current))
                        current = [w]
                if current:
                    wrapped.append(" ".join(current))
                return wrapped

            # Pick the largest font size where the wrapped text fits in ≤3 lines.
            font_size = 130
            font = None
            lines = [overlay_words]
            while font_size >= 50:
                try:
                    font = (
                        ImageFont.truetype(font_path, font_size)
                        if font_path else ImageFont.load_default()
                    )
                except Exception:
                    font = ImageFont.load_default()
                lines = _wrap(overlay_words, font)
                if len(lines) <= 3:
                    break
                font_size -= 8

            draw = ImageDraw.Draw(bg)
            line_h = int(font_size * 1.05)
            total_h = line_h * len(lines)
            margin_bottom = 50
            y = THUMB_H - total_h - margin_bottom
            for line in lines:
                draw.text(
                    (margin_left, y), line, font=font,
                    fill=(255, 255, 255),
                    stroke_width=10, stroke_fill=(0, 0, 0),
                )
                y += line_h

        # Save to a persistent directory OUTSIDE .mp/ so rem_temp_files() doesn't wipe it.
        # This way, even if the auto-upload to YT fails, the file is still on disk for
        # manual recovery via YouTube Studio.
        thumbs_dir = os.path.join(ROOT_DIR, "thumbnails")
        os.makedirs(thumbs_dir, exist_ok=True)
        out_path = os.path.join(thumbs_dir, f"thumb_{uuid4()}.png")
        bg.save(out_path, "PNG")
        self.thumbnail_path = out_path
        success(f" Thumbnail: {out_path}")
        return out_path

    def generate_long_prompts(self) -> List[str]:
        """
        Generates ~30 image prompts for a long video, anchored to the script:
        the script is split into N sections and each prompt MUST illustrate its
        section literally, naming the people / places / objects from the topic.
        """
        n_prompts = 30

        # Split the script into N sections so each prompt maps 1:1 to a chunk
        # of narration — this is what keeps the images on-topic.
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', self.script) if s.strip()]
        sections = []
        if sentences:
            per_section = max(1, len(sentences) // n_prompts)
            for i in range(n_prompts):
                start = i * per_section
                end = start + per_section if i < n_prompts - 1 else len(sentences)
                section_text = ' '.join(sentences[start:end])[:400]
                if section_text:
                    sections.append(section_text)
        while len(sections) < n_prompts:
            sections.append(self.subject)

        sections_text = "".join(
            f'\nSECTION {i+1}: "{sec}"\n' for i, sec in enumerate(sections)
        )

        # Setting anchor — names the world/era of THIS video inside the prompt
        # so the LLM doesn't drift into off-setting visuals on abstract script
        # lines. Niche-agnostic: works for history, modern, sports, food, tech,
        # etc. (see `_get_context_profile`).
        ctx = self._get_context_profile()
        era_clause = ""
        if ctx and (ctx.get("setting") or ctx.get("visual_anchors")):
            setting_line = ctx.get("setting") or "(see niche)"
            anchors_line = ctx.get("visual_anchors") or "(infer from topic)"
            avoid_line = ctx.get("must_avoid") or "anything that breaks the setting's immersion"
            era_clause = (
                f"\n\n=== SETTING — NON-NEGOTIABLE ===\n"
                f"This documentary is set in: **{setting_line}**.\n"
                f"Visual anchors that should appear naturally when relevant: {anchors_line}.\n"
                f"FORBIDDEN visual elements (anachronistic / off-setting): {avoid_line}.\n"
                f"REQUIRED in every prompt with a person: clothing, props and architecture that belong to the setting above.\n"
                f"=========================================="
            )

        # Inline guidance string for the PERIOD ACCURACY rule below — kept
        # short to avoid bloating the prompt.
        period_inline = (
            f"Setting is **{ctx['setting']}**. Every prompt with a person MUST name at least 2 specific clothing/prop items that belong to this setting, and AVOID: {ctx.get('must_avoid', '')}. "
            if (ctx and ctx.get("setting")) else ""
        )

        prompt = f"""Task: write {n_prompts} image prompts for a long-form video about "{self.subject}".{era_clause}

You receive {n_prompts} script sections below. Each prompt MUST illustrate the LITERAL content of its matching section — the people, the action, the place, the moment that section describes. Do not invent new events. Do not summarize abstractly. If the section talks about "the team debating in the boardroom at noon", the image is exactly that.

ABSOLUTE RULES (every prompt):
1. ENGLISH ONLY — NON-NEGOTIABLE. Write every prompt entirely in English, even if the script is in Spanish. Image generators are trained on English data and produce wrong subjects when given Spanish prompts. Translate proper nouns naturally. NO Spanish words anywhere in the output.
2. SCENE FIDELITY. Open with a concrete action (subject + verb) drawn from the section text. Whatever the section is talking about, that is what the image shows.
3. NAMED CHARACTER IDENTITY. When the script names a real person, do NOT just write their name — describe them physically (age, hair, beard, build, clothing) so the image generator can render the correct person. The physical description MUST appear every time they're shown.
4. SETTING ACCURACY — STRICT. {period_inline}If a person appears, describe their clothing exactly as it would look in the setting of this video (fabric, cut, color, footwear, headwear). Same for architecture, tools, vehicles and 2-3 supporting objects. If the section names a real person, place or event, use that proper noun.
5. CONSISTENT REALISM. All {n_prompts} prompts describe the SAME world — same realism level, same physical universe. No image should feel like it comes from a different show. Vary action, time of day, framing — but never the level of realism.
6. NO ART STYLE WORDS. Describe SCENES ONLY. Never write "painting", "illustration", "cartoon", "anime", "drawing", "vector", "3D render", "ukiyo-e", "fresco", "engraving", "comic", "pixel art" or any other medium/aesthetic label. The visual look is decided by a suffix appended later — your job is content only.
7. LENGTH. 40-70 English words per prompt. No camera or lens jargon.

Examples of GOOD scene-only prompts (the PATTERN matters — names and props will differ for your topic):
- (Historical setting) "Caesar in a red cloak crosses the shallow Rubicon at dusk on a black warhorse, his legion wading behind him in lorica segmentata armor with rectangular shields and silver eagle standards, low hills on the horizon, determined tense faces."
- (Modern setting) "A young trader leans over three glowing monitors on the floor of the New York Stock Exchange, mouth open mid-shout, paper tickets crumpled on his keyboard, the index ticker spiking red overhead, colleagues running behind him."
- (Sports setting) "A quarterback in a navy and red jersey throws a tight spiral over the defensive line under stadium floodlights, mud streaking his white pants, breath visible in cold air, tens of thousands of blurred fans behind the end zone."
- (Domestic / present-day setting) "A father in a flannel shirt kneels beside an open dishwasher in a small kitchen at night, holding a flashlight, water pooling at his knees, his daughter watching from the hallway in pyjamas, single warm bulb above the sink."

Examples of BAD prompts (DO NOT WRITE THESE):
- "An ancient scene." (too vague, no action, no setting)
- "Stylized cartoon of [subject] doing [action]." (forbidden art-style word)
- "A historical illustration of [subject]." (forbidden art-style word, no action)
- "Symbolic image of [subject]'s power." (no concrete moment)

{sections_text}
Forbidden words (art-style / camera jargon): cinematic, photograph, camera, shot, lens, close-up, 4K, 8K, HD, render, abstract, concept, metaphor, symbolic, visualization, painting, illustration, cartoon, drawing, anime, fresco, engraving, comic, vector, ukiyo-e, sketch.
Forbidden words (multi-image triggers — these make image generators output collages instead of one image): series, sequence, scenes (plural), panels, panel, storyboard, comic strip, montage, collage, grid, split screen, frames, multiple, diptych, triptych, before-and-after, side by side.
Also forbidden unless the topic itself demands it: cosmic/space/nebula imagery, microscopic diagrams, futuristic/sci-fi visuals.

Return ONLY a JSON array of {n_prompts} strings (one prompt per section, in order). Example format:
["scene 1 description...", "scene 2 description...", ...]
No markdown. No explanation. Just the JSON array."""

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        def _extract_prompts_long(parsed_value):
            out = []
            if isinstance(parsed_value, list):
                for item in parsed_value:
                    if isinstance(item, str):
                        out.append(item)
                    elif isinstance(item, dict):
                        p = item.get("prompt") or item.get("image_prompt") or ""
                        moment = item.get("moment") or item.get("key_visual_moment") or ""
                        if p:
                            out.append(str(p))
                        elif moment:
                            out.append(str(moment))
            return out

        image_prompts = []
        try:
            parsed = json.loads(completion)
            image_prompts = _extract_prompts_long(parsed)
        except Exception:
            match = re.search(r'\[.*\]', completion, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    image_prompts = _extract_prompts_long(parsed)
                except Exception:
                    pass

        # Fallback: build a topic-anchored prompt per section so images stay on-topic
        # even when the LLM fails to produce a parseable JSON array.
        if not image_prompts or len(image_prompts) < 4:
            if get_verbose():
                warning("Failed to parse long video prompts, using section-anchored fallback")
            fallback_styles = [
                "wide vista with key subjects centered, dramatic atmosphere",
                "detail of the central object or person, period-accurate textures",
                "low-angle hero composition, epic scale",
                "atmospheric scene with depth and moody shadows",
                "intimate framing of figures interacting in period-accurate context",
                "establishing view of the era's setting, painterly mood",
                "overcast atmosphere, period-accurate detail",
                "warm interior scene, period-accurate furnishings and dress",
            ]
            image_prompts = [
                (
                    f"Scene from \"{sections[i] if i < len(sections) else self.subject}\" "
                    f"in the context of {self.subject}, {fallback_styles[i % len(fallback_styles)]}, "
                    f"period-accurate, 16:9 landscape"
                )
                for i in range(n_prompts)
            ]

        image_prompts = image_prompts[:n_prompts]
        self.image_prompts = image_prompts

        if get_verbose():
            info(f" => Generated {len(image_prompts)} long video image prompts")

        return image_prompts

    def _try_leonardo_landscape(self, prompt: str) -> bytes:
        """Try Leonardo AI API in 16:9 landscape format for long videos."""
        from config import get_leonardo_api_key
        api_key = get_leonardo_api_key()
        if not api_key:
            raise RuntimeError("Leonardo AI API key not configured")

        print(colored(f"    [Leonardo AI 16:9] Generating...", "cyan"), flush=True)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt[:1500],
            "modelId": "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3",  # Leonardo Phoenix 1.0
            "width": 1024,
            "height": 576,
            "num_images": 1,
            "contrast": 3.5,
            "alchemy": True,
        }
        style_text = (self._image_style or "").lower()
        if any(k in style_text for k in ("cartoon", "anime", "illustration", "animated", "cel shading", "hand-drawn")):
            payload["presetStyle"] = "ILLUSTRATION"
        elif any(k in style_text for k in ("cinematic", "film", "movie")):
            payload["presetStyle"] = "CINEMATIC"
        elif self._image_style:
            payload["presetStyle"] = "DYNAMIC"
        resp = requests.post(
            "https://cloud.leonardo.ai/api/rest/v1/generations",
            headers=headers, json=payload, timeout=30,
        )
        resp.raise_for_status()
        gen_id = resp.json().get("sdGenerationJob", {}).get("generationId", "")
        if not gen_id:
            raise RuntimeError("Leonardo: no generation ID returned")

        for _ in range(30):
            time.sleep(5)
            status_resp = requests.get(
                f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}",
                headers=headers, timeout=15,
            )
            status_resp.raise_for_status()
            gen = status_resp.json().get("generations_by_pk", {})
            status = gen.get("status", "")
            if status == "COMPLETE":
                images = gen.get("generated_images", [])
                if images:
                    img_url = images[0].get("url", "")
                    img_resp = requests.get(img_url, timeout=60)
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        print(colored("OK", "green"))
                        return img_resp.content
                raise RuntimeError("Leonardo: no image in result")
            elif status == "FAILED":
                raise RuntimeError("Leonardo: generation failed")
        raise RuntimeError("Leonardo: timeout waiting for generation")

    def generate_long_images(self, prompts: List[str]) -> None:
        """
        Generate images for long video in 16:9 landscape format (1920x1080).
        Cascade: Leonardo AI → Pollinations FLUX → HuggingFace → Pillow fallback.
        """
        print(colored(f"\n  [Long Video] Generating {len(prompts)} images (1920x1080)...", "blue"))

        for i, prompt in enumerate(prompts):
            print(colored(f"\n  Image {i+1}/{len(prompts)}", "blue"))
            saved = False

            # Apply per-channel style suffix to AI prompts.
            styled_prompt = self._apply_channel_style(prompt)

            for name, fn in [
                ("Leonardo AI", lambda p: self._try_leonardo_landscape(p)),
                ("Pollinations.ai FLUX", lambda p: self._try_pollinations_landscape(p)),
                ("HuggingFace", self._try_huggingface),
            ]:
                try:
                    img_bytes = fn(styled_prompt)
                    if img_bytes and len(img_bytes) > 1000:
                        self._persist_image(img_bytes, name)
                        saved = True
                        break
                except Exception as e:
                    if get_verbose():
                        warning(f"    {name} failed: {str(e)[:100]}")
                    time.sleep(1)

            if not saved:
                self._generate_fallback_image_landscape(prompt)

        success(f"All {len(self.images)} long video images ready!")

    def _try_pollinations_landscape(self, prompt: str) -> bytes:
        """Pollinations.ai in 16:9 landscape for long videos."""
        import urllib.parse
        encoded = urllib.parse.quote(prompt[:500])
        seed = int(time.time())
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1920&height=1080&nologo=true&seed={seed}&model=flux"
        print(colored(f"    [Pollinations FLUX 16:9] Generating...", "cyan"), flush=True)
        resp = requests.get(url, timeout=180)
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(colored("OK", "green"))
            return resp.content
        raise RuntimeError(f"Pollinations returned status {resp.status_code}")

    def _generate_fallback_image_landscape(self, prompt: str) -> str:
        """Fallback landscape image (1920x1080) when all providers fail."""
        from PIL import Image, ImageDraw, ImageFont
        import random as rand_mod

        if get_verbose():
            warning("All providers failed. Creating styled fallback image (landscape)...")

        color_schemes = [
            ((15, 15, 80), (80, 20, 120)),
            ((10, 50, 80), (20, 100, 100)),
            ((60, 10, 60), (120, 30, 80)),
            ((10, 40, 20), (30, 100, 60)),
        ]
        c1, c2 = rand_mod.choice(color_schemes)
        img = Image.new("RGB", (1920, 1080))
        draw = ImageDraw.Draw(img)

        for y in range(1080):
            r = int(c1[0] + (c2[0] - c1[0]) * y / 1080)
            g = int(c1[1] + (c2[1] - c1[1]) * y / 1080)
            b = int(c1[2] + (c2[2] - c1[2]) * y / 1080)
            draw.line([(0, y), (1920, y)], fill=(r, g, b))

        try:
            font_path = os.path.join(get_fonts_dir(), get_font())
            font = ImageFont.truetype(font_path, 48)
        except Exception:
            font = ImageFont.load_default()

        words = prompt.split()
        text_lines, current_line = [], ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if len(test) > 45:
                text_lines.append(current_line)
                current_line = word
            else:
                current_line = test
        if current_line:
            text_lines.append(current_line)

        y_pos = 1080 // 2 - (len(text_lines) * 60) // 2
        for line in text_lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            draw.text(((1920 - w) // 2 + 3, y_pos + 3), line, fill=(0, 0, 0), font=font)
            draw.text(((1920 - w) // 2, y_pos), line, fill="white", font=font)
            y_pos += 60

        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
        img.save(image_path)
        self.images.append(image_path)
        return image_path

    # Patterns that mean "this line is metadata / API junk / not narration".
    # If a line matches ANY of these, it gets dropped before TTS.
    _GARBAGE_LINE_PATTERNS = [
        re.compile(r"https?://", re.IGNORECASE),
        re.compile(r"\bwww\.[a-z]", re.IGNORECASE),
        re.compile(r"\b[\w.-]+\.(?:com|org|net|io|ai|gov|edu|co|es)\b", re.IGNORECASE),
        re.compile(r"^\s*[\{\}\[\]<>]+\s*$"),
        re.compile(r"^\s*[#/!*=\-]{3,}\s*$"),
        re.compile(r"^\s*```"),
        re.compile(r"^\s*<[/!?]?[a-z][^>]*>\s*$", re.IGNORECASE),
        re.compile(r"\b(?:guion[\s-]?bajo|barra[\s-]?baja|underscore|forward[\s-]?slash|backslash|asterisk|asterisco)\b", re.IGNORECASE),
        re.compile(r"\b(?:generating|generando|loading|cargando)\s+(?:script|content|response|el\s+\w+)\b", re.IGNORECASE),
        re.compile(r"\b(?:please\s+(?:try\s+again|retry|wait)|por\s+favor\s+(?:intenta|reintente|espere))\b", re.IGNORECASE),
        re.compile(r"\b(?:api[\s_-]?(?:key|token|endpoint|response|error|call))\b", re.IGNORECASE),
        re.compile(r"\b(?:status[\s_-]?code|error[\s_-]?code|http\s*\d{3})\b", re.IGNORECASE),
        re.compile(r"\b(?:404|429|500|502|503)\b\s+(?:not\s+found|error|too\s+many|internal|bad\s+gateway|unavailable)", re.IGNORECASE),
        re.compile(r"\b(?:role|content|model|message|completion|payload|tokens?|prompt)\s*[:=]\s*[\"']?[A-Za-z]"),
        re.compile(r"\{\s*[\"']\w+[\"']\s*:"),
        re.compile(r"^\s*\w+_\w+(?:_\w+)*\s*$"),
        re.compile(r"^\s*[A-Z_]{4,}(?:\s+[A-Z_]{4,}){0,2}\s*$"),
        re.compile(r"\bI\s+(?:am|will|cannot|can'?t)\s+(?:generate|provide|continue|create|write)\b", re.IGNORECASE),
        re.compile(r"\b(?:no\s+puedo|lo\s+siento,)\s+(?:generar|continuar|crear|proveer)\b", re.IGNORECASE),
    ]

    @classmethod
    def _filter_garbage_lines(cls, text: str) -> tuple:
        """Drop lines that look like metadata / URLs / system messages. Returns (clean_text, dropped_count)."""
        kept, dropped = [], 0
        for line in text.split("\n"):
            if line.strip() and any(p.search(line) for p in cls._GARBAGE_LINE_PATTERNS):
                dropped += 1
                continue
            kept.append(line)
        return "\n".join(kept), dropped

    @classmethod
    def _looks_like_garbage(cls, text: str) -> bool:
        """Heuristic: is the LLM response dominated by metadata / non-narration?"""
        if not text or len(text.split()) < 30:
            return True
        # If >25% of non-empty lines are garbage, the output is unusable.
        lines = [ln for ln in text.split("\n") if ln.strip()]
        if not lines:
            return True
        bad = sum(1 for ln in lines if any(p.search(ln) for p in cls._GARBAGE_LINE_PATTERNS))
        return bad / len(lines) > 0.25

    @classmethod
    def _clean_llm_script(cls, text: str) -> str:
        """Clean raw LLM response: strip JSON wrappers, markdown, preambles, garbage lines."""
        if not text:
            return ""
        # Strip JSON wrapper: {"role":"assistant","content":"..."}
        text = re.sub(
            r'^\s*\{?\s*"?role"?\s*:\s*"?\w+"?\s*,?\s*"?content"?\s*:\s*"?',
            '', text
        )
        text = re.sub(r'"\s*\}?\s*$', '', text)
        # Strip code blocks (and their content) and inline backticks.
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`+', '', text)
        # Strip markdown emphasis/headings.
        text = re.sub(r"\*+", "", text)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # Strip LLM preamble lines.
        text = re.sub(
            r'^\s*(Here\'s|Here is|Sure[!,.]?\s*here|Of course|Aquí (está|tienes|te presento)|'
            r'¡?(Por supuesto|Claro|Desde luego|Con gusto)|A continuación)[^\n]*\n',
            '', text, flags=re.IGNORECASE
        )
        # Strip trailing notes.
        text = re.sub(
            r'\n\s*(Note:|Nota:|---|\*\*\*|This script|Este guion|Espero que|I hope this)[^\n]*$',
            '', text, flags=re.IGNORECASE
        )
        # Final pass: drop any line that looks like metadata / URL / API junk.
        text, dropped = cls._filter_garbage_lines(text)
        if dropped > 0:
            warning(f"   [Clean] dropped {dropped} garbage line(s) from LLM output.")
        return text.strip()

    @classmethod
    def _clean_script_for_tts(cls, script: str) -> str:
        """Last-line-of-defense cleaner: only spoken narration survives."""
        text = script

        # Strip stage-direction artifacts the LLM leaks ("(imagen de ...)",
        # "[B-roll: ...]", "Música: ...") BEFORE the section-marker pass so
        # nothing falls through.
        text = strip_stage_directions(text)

        # Strip section markers in any language / case.
        text = re.sub(r'\[(INTRO|INTRODUCCIÓN|INTRODUCCION|CLOSING|CIERRE|OUTRO|DESPEDIDA)\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[(SECTION|SECCIÓN|SECCION)\s*\d+\s*:?[^\]]*\]', '', text, flags=re.IGNORECASE)

        # Some LLMs write the markers WITHOUT brackets — strip those too.
        text = re.sub(r'^\s*(INTRO|INTRODUCCIÓN|INTRODUCCION|CLOSING|CIERRE|OUTRO|DESPEDIDA)\s*:?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        text = re.sub(r'^\s*(SECTION|SECCIÓN|SECCION)\s*\d+\s*:[^\n]*$', '', text, flags=re.IGNORECASE | re.MULTILINE)

        # Strip JSON / code artifacts.
        text = re.sub(r'"role"\s*:\s*"[^"]*"', '', text)
        text = re.sub(r'"content"\s*:\s*"', '', text)
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`+', '', text)

        # Strip URLs / bare domains so the TTS never reads one out loud.
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'\bwww\.\S+', '', text)
        text = re.sub(r'\b[\w.-]+\.(?:com|org|net|io|ai|gov|edu|co|es|app|dev|tv)(?:/\S*)?', '', text, flags=re.IGNORECASE)

        # Strip markdown artifacts.
        text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*+', '', text)

        # Strip stray JSON braces and quotes at start/end.
        text = re.sub(r'^\s*[\{\}]\s*', '', text)
        text = re.sub(r'\s*[\{\}]\s*$', '', text)

        # Drop garbage lines (URLs, identifiers, "guion bajo ...", error messages).
        text, _ = cls._filter_garbage_lines(text)

        # Drop snake_case / kebab identifiers that survived (`user_role`, `api-key`).
        text = re.sub(r'\b\w+(?:[_-]\w+){1,}\b', '', text)

        # Collapse whitespace.
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        return text.strip()

    def combine_long(self) -> str:
        """
        Combines images and audio into a long-form 16:9 landscape video.
        No subtitles, cinematic Ken Burns effect (slow zoom/pan), smooth transitions.
        """
        combined_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp4")
        threads = get_threads()
        tts_clip = AudioFileClip(self.tts_path)
        max_duration = tts_clip.duration

        t_total = time.time()
        print(colored(f"[+] Combining {len(self.images)} images into long video ({max_duration:.0f}s)...", "blue"), flush=True)

        valid_images = [p for p in self.images if os.path.exists(p)]
        if not valid_images:
            raise FileNotFoundError("No valid images found")
        self.images = valid_images

        clips = []
        tot_dur = 0
        clip_idx = 0
        n_total = len(self.images)

        # Compensate req_dur for the crossfade overlap so the VISIBLE duration matches
        # the audio exactly. Each of the (n-1) crossfades eats CROSSFADE_DUR seconds, so
        # we extend each clip a bit. Without this, the last ~23s of audio play over a
        # black screen because the visible video ends early.
        # Also reserve EXTRA_TAIL extra seconds on the last clip so it can fade out gracefully.
        CROSSFADE_DUR = 0.8
        EXTRA_TAIL = 1.5  # the last clip lingers 1.5s for the fade-out
        overlap_total = CROSSFADE_DUR * (n_total - 1) if n_total > 1 else 0
        req_dur = (max_duration + overlap_total + EXTRA_TAIL) / n_total

        t_phase = time.time()
        from itertools import cycle
        # Safety cap so a malformed image list (e.g. one image looping with tiny req_dur)
        # cannot spin forever; in practice the clip_dur < 0.5 break exits well before this.
        max_iterations = max(n_total * 4, 200)
        target_total = max_duration + overlap_total + EXTRA_TAIL
        for iteration, image_path in enumerate(cycle(self.images)):
            if iteration >= max_iterations:
                warning(f"    [Build] safety cap hit at {iteration} iterations; stopping.")
                break
            if tot_dur >= target_total - 0.01:  # float-tolerant termination
                break

            clip_dur = min(req_dur, target_total - tot_dur)
            if clip_dur < 0.5:
                break

            try:
                clip_idx += 1
                print(colored(f"    [Build] Clip {clip_idx}/{n_total} ({clip_dur:.1f}s)...", "cyan"), flush=True)
                img_clip = ImageClip(image_path).set_duration(clip_dur)

                # Resize to 1920x1080
                w, h = img_clip.size
                aspect = w / h
                target_aspect = 1920 / 1080

                if aspect > target_aspect:
                    img_clip = img_clip.resize(height=1080)
                    img_clip = crop(img_clip, x_center=img_clip.w / 2, y_center=540, width=1920, height=1080)
                else:
                    img_clip = img_clip.resize(width=1920)
                    img_clip = crop(img_clip, x_center=960, y_center=img_clip.h / 2, width=1920, height=1080)

                # Ken Burns: gentle slow zoom (1.0x → 1.08x over clip duration)
                # Use default arg to capture clip_dur in the closure
                img_clip = img_clip.resize(lambda t, d=clip_dur: 1 + 0.08 * (t / d))

                # Crossfade between images
                if clip_dur > 2.0:
                    img_clip = img_clip.crossfadein(0.8)

                img_clip = img_clip.set_fps(24)
                clips.append(img_clip)
                tot_dur += clip_dur

            except Exception as e:
                if get_verbose():
                    warning(f"Skipping image {image_path}: {e}")
                continue
        print(colored(f"    [Build] {len(clips)} clips ready in {time.time() - t_phase:.1f}s", "green"), flush=True)

        if not clips:
            raise RuntimeError("No clips could be created from images")

        # Concatenate with crossfade overlap between clips
        print(colored("[+] Applying transitions...", "blue"), flush=True)
        t_phase = time.time()
        padding = -CROSSFADE_DUR if len(clips) > 1 else 0
        final_clip = concatenate_videoclips(clips, padding=padding, method="compose")
        final_clip = final_clip.set_fps(24)

        # The video should now last about (audio + EXTRA_TAIL); cap to (audio + EXTRA_TAIL)
        # so we have a small visual tail beyond the last narration word that fades out.
        target_visual_duration = max_duration + EXTRA_TAIL
        if final_clip.duration > target_visual_duration:
            final_clip = final_clip.subclip(0, target_visual_duration)

        # Smooth fade-to-black at the very end so the closing doesn't cut abruptly.
        final_clip = final_clip.fadeout(EXTRA_TAIL)
        print(colored(f"    [Transitions] done in {time.time() - t_phase:.1f}s", "green"), flush=True)

        # Audio: TTS + background music
        print(colored("[+] Mixing audio...", "blue"), flush=True)
        t_phase = time.time()
        random_song = choose_random_song(getattr(self, "subject", ""))
        music_clip = AudioFileClip(random_song).set_fps(44100)

        # Total audio runs slightly past the narration so the closing fade has music under it.
        total_dur = max_duration + EXTRA_TAIL

        # Loop music if shorter than the full timeline (narration + fade tail)
        if music_clip.duration < total_dur:
            loops_needed = int(total_dur // music_clip.duration) + 1
            music_clip = concatenate_audioclips([music_clip] * loops_needed)
        music_clip = music_clip.subclip(0, total_dur)

        # Background music at 10% volume for long videos (subtle ambient)
        music_clip = music_clip.fx(afx.volumex, 0.10)

        # Music fades in over 3s at start; fades out across the EXTRA_TAIL closing window
        # in sync with the visual fade-to-black.
        music_clip = music_clip.audio_fadein(3.0).audio_fadeout(EXTRA_TAIL + 1.0)

        comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), music_clip])

        # Set audio THEN duration — order matters for MoviePy
        final_clip = final_clip.set_duration(total_dur)
        final_clip = final_clip.set_audio(comp_audio)
        print(colored(f"    [Audio] mixed in {time.time() - t_phase:.1f}s", "green"), flush=True)

        print(colored("[+] Rendering long video (ffmpeg)...", "blue"), flush=True)
        t_phase = time.time()
        final_clip.write_videofile(
            combined_path,
            threads=threads,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            audio=True,
            logger="bar",
        )
        print(colored(f"    [Render] done in {time.time() - t_phase:.1f}s", "green"), flush=True)
        print(colored(f"[+] Total combine_long: {time.time() - t_total:.1f}s", "blue"), flush=True)

        success(f'Wrote long video to "{combined_path}"')
        return combined_path

    def generate_long_video(self, tts_instance: TTS, custom_topic: str = "") -> str:
        """
        Full pipeline for generating a long-form YouTube video (15-20 minutes).
        16:9 landscape, documentary style, no subtitles.

        Args:
            tts_instance (TTS): Instance of TTS Class.
            custom_topic (str): Optional user-provided topic. If given, skips auto topic generation.

        Returns:
            path (str): Path to the generated MP4 file.
        """
        info("=" * 50)
        info("  LONG VIDEO GENERATION PIPELINE")
        info("=" * 50)

        # Mark this as a long video so upload_video knows to wait longer for the upload to finish.
        self._is_long_video = True

        # Step 1: Generate Topic (or use the user-provided one)
        info("\n[1/7] Generating topic...")
        if custom_topic and custom_topic.strip():
            self.subject = custom_topic.strip()
            info(f" => Using custom topic: {self.subject}")
        else:
            self.generate_topic()
        if not self.subject or not self.subject.strip():
            error(
                "Aborting long video: no unique topic available. "
                "No video will be generated or uploaded."
            )
            self.video_path = ""
            return ""

        # Series detection: if subject starts with "[series_id] ...", strip the
        # prefix and remember which series this video belongs to. generate_long_metadata
        # and generate_thumbnail use the series template/overlay instead of asking
        # the LLM to invent a title or overlay text.
        self.active_series, self.subject = resolve_series(self.subject)
        if self.active_series:
            info(f" => Series: {self.active_series.get('id', '')}")

        success(f" Topic: {self.subject}")

        # Step 2: Generate long script with chapters
        info("\n[2/7] Generating long-form script...")
        self.generate_long_script()

        # Step 3: Generate metadata
        info("\n[3/7] Generating title & description...")
        self.generate_long_metadata()
        success(f" Title: {self.metadata['title']}")

        # Step 4: Generate clickbait thumbnail (1280x720)
        info("\n[4/7] Generating thumbnail...")
        try:
            self.generate_thumbnail()
        except Exception as e:
            warning(f"Thumbnail generation failed: {str(e)[:200]} (will upload without custom thumbnail)")
            self.thumbnail_path = ""

        # Step 5: Generate image prompts
        info("\n[5/7] Generating image prompts...")
        self.images = []  # Reset images
        self.generate_long_prompts()

        # Step 6: Generate images (landscape 1920x1080)
        info("\n[6/7] Generating images...")
        self.generate_long_images(self.image_prompts)

        # Step 7: Generate TTS with natural voice
        info("\n[7/7] Generating narration audio...")
        path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".wav")

        # Clean script for TTS: remove ALL non-narration content
        tts_script = self._clean_script_for_tts(self.script)

        # Fallback: if cleaning wiped everything, use the raw script
        if not tts_script or len(tts_script.split()) < 50:
            warning("TTS cleaning removed too much content, using raw script")
            tts_script = re.sub(r'\[.*?\]', '', self.script).strip()

        # Expand spoken symbols ("90%" -> "90 por ciento") so TTS verbalizes them.
        tts_script = expand_spoken_symbols(tts_script)

        # Expand regnal numerals ("Luis XIV" -> "Luis catorce") for correct TTS pronunciation
        tts_script = expand_regnal_numerals(tts_script)

        # Expand digit numbers to Spanish words ("4.500" -> "cuatro mil quinientos",
        # "1453" -> "mil cuatrocientos cincuenta y tres") so the TTS doesn't read
        # them digit-by-digit ("4 punto 5 0 0").
        tts_script = expand_spanish_numbers(tts_script)

        if get_verbose():
            info(f" => TTS script preview (first 200 chars): {tts_script[:200]}")

        # Per-channel long-video voice (or fall back to the default deep narrator).
        from .Tts import LONG_VIDEO_NARRATOR
        long_vid = self._resolve_voice(self._long_voice) or LONG_VIDEO_NARRATOR
        info(f" => Using long-video voice: {long_vid}")
        tts_instance.synthesize_long(tts_script, path, voice_id=long_vid)
        self.tts_path = path

        if os.path.exists(path) and os.path.getsize(path) > 1000:
            audio_dur = AudioFileClip(path).duration
            info(f" => Audio duration: {audio_dur:.0f} seconds ({audio_dur/60:.1f} min)")
        else:
            raise RuntimeError(f"TTS failed to generate audio file at {path}")

        # Step 7: Combine everything
        info("\n[+] Assembling final video...")
        video_path = self.combine_long()

        self.video_path = os.path.abspath(video_path)
        self._persist_metadata_sidecar(is_long=True)
        success(f"\n=> Long video generated: {video_path}")

        return video_path

    def _verify_thumbnail_uploaded(self, driver) -> bool:
        """
        After send_keys(thumbnail.png), confirm YouTube actually accepted it.
        Multiple signals because YT Studio's DOM varies by locale and rollout.
        Returns True if any custom-thumbnail signal is detected.
        """
        try:
            # Primary signal: scoped <img> elements inside the thumbnail editor whose
            # src is NOT an i.ytimg.com auto-generated URL.
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
                # Auto-generated thumbnails from YT come from i.ytimg.com / i9.ytimg.com.
                # Anything else inside the editor area (blob:, data:, googleusercontent,
                # lh3.google, or a YT-internal upload URL) means a custom upload rendered.
                if "ytimg.com" in src:
                    continue
                if (src.startswith("blob:")
                        or src.startswith("data:image")
                        or "googleusercontent.com" in src
                        or "lh3.google" in src
                        or "yt3.ggpht.com" in src):
                    return True
            # Alternative signal: any control that only renders once a custom
            # thumbnail is in place (Replace / Edit / Options menu).
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
            # Last resort: the uploader's "Upload thumbnail" CTA disappears once a
            # custom thumbnail is present. If we previously saw it and now it's gone,
            # treat that as a positive signal.
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
        """
        Locate YouTube Studio's thumbnail file input across UI variants.

        Strategy (most reliable first):
          1. Find every `input[type=file]` and pick the one whose `accept` attribute
             names an image type — that filters out the video upload input itself.
          2. Fall back to known CSS selectors for older YT Studio versions.
        Returns the WebElement or None.
        """
        # Give YT Studio a moment to finish rendering the Details panel.
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

        # Legacy / variant-specific selectors as fallback.
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

    def _ensure_browser(self) -> None:
        """
        Ensures the Firefox browser is running and connected.
        Launches (or re-launches) the browser if it is None or the session has died.
        Called lazily just before upload so a browser crash during video generation
        does not discard the finished video.
        """
        session_alive = False
        if self.browser is not None:
            try:
                # A simple property access will raise if the session is dead
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
            service = Service(GeckoDriverManager().install())
            self.browser = webdriver.Firefox(service=service, options=self.options)
            success(" => Firefox conectado.")

    def get_channel_id(self) -> str:
        """
        Gets the Channel ID of the YouTube Account.

        Returns:
            channel_id (str): The Channel ID.
        """
        driver = self.browser
        driver.get("https://studio.youtube.com")
        time.sleep(2)
        channel_id = driver.current_url.split("/")[-1]
        self.channel_id = channel_id

        return channel_id

    def _wait_for_listing_settled(
        self,
        driver,
        listing_tab: str,
        kind_label: str,
        max_wait_s: int,
        poll_interval_s: int = 8,
        refresh_interval_s: int = 60,
    ) -> bool:
        """
        Wait for an upload (Short or long video) to finish transferring + processing,
        WITHOUT touching the original tab where the upload runs in the background.

        IMPORTANT: navigating or refreshing the upload tab while the HTTP file
        transfer is in flight CANCELS the upload (YouTube shows
        "Upload interrupted" / "Subida interrumpida"). We therefore open a SECOND
        tab, do all polling there, close it, and return to the original tab
        untouched.

        Strategy:
          1. Open a new browser tab via JS.
          2. Switch to it and navigate to /videos/<listing_tab>.
          3. Poll the row matching our title until ALL in-progress markers
             disappear (Subiendo / Uploading / Pendiente / Pending / Procesando /
             Processing / Verificando / Checking / Cancelar carga).
          4. If we see an explicit "Subida interrumpida / Upload interrupted"
             marker, abort early and tell the user.
          5. ALWAYS close the new tab and switch back to the original tab.

        Args:
            listing_tab: "short" for Shorts, "upload_video" for long videos.
            kind_label: human-readable label used only in log lines.
            max_wait_s: hard total cap.
            poll_interval_s: time between row reads.
            refresh_interval_s: time between status-tab refreshes.

        Returns:
            True when the row settles cleanly, False on timeout or detected
            interruption.
        """
        info(f"\t=> Waiting up to {max_wait_s // 60} min for {kind_label} upload + processing...")
        info("\t   (polling in a SEPARATE tab so the upload tab is never disturbed)")

        deadline = time.time() + max_wait_s
        listing_url = f"https://studio.youtube.com/channel/{self.channel_id}/videos/{listing_tab}"
        target_title = (self.metadata.get("title") or "").strip()
        target_match = target_title[:50] if target_title else ""

        in_progress_markers = (
            "subiendo", "uploading",
            "procesando", "processing",
            "pendiente", "pending",
            "verificando", "verificaciones en curso",
            "checking", "checks in progress",
            "cancelar carga", "cancel upload",
        )
        # Hard-fail markers: YouTube has explicitly interrupted the transfer.
        error_markers = (
            "subida interrumpida",
            "carga interrumpida",
            "upload interrupted",
        )
        # YT Studio "Oops, something went wrong" / "Algo salió mal" page.
        # When this shows up, the listing tab is broken — refresh() alone
        # often can't recover, so we re-navigate to the URL.
        studio_error_markers = (
            "oops, something went wrong",
            "something went wrong",
            "algo salió mal",
            "algo salio mal",
            "ha ocurrido un error",
            "se produjo un error",
            "intenta volver a cargar",
            "try reloading",
            "try again later",
            "vuelve a intentarlo",
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
                # Safer fallback: blind wait on the current page (don't navigate).
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
            stable_done_count = 0  # require 2 consecutive "no markers" reads to call it done
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

                # Detect YT Studio's generic error page (no rows + "oops" text in body).
                # When it shows up, plain refresh() often can't rescue it — re-navigate.
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
                    # If many polls in a row return zero rows (no error text either —
                    # could be a slow render, ghost spinner, or a blank Studio page),
                    # force a hard re-navigation rather than waiting for the next refresh.
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
            # ALWAYS clean up: close the status tab and return to the upload tab.
            # If we don't, subsequent driver.get() calls will run on the wrong tab.
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

    def _resolve_video_url_safe(self, driver, listing_tab: str) -> str:
        """
        Resolve the public URL of the just-uploaded video using a SEPARATE tab,
        so the original upload tab is never navigated. Same status-tab pattern
        as `_wait_for_listing_settled`. Returns "" if it can't find a match.
        """
        if not getattr(self, "channel_id", None):
            return ""
        listing_url = f"https://studio.youtube.com/channel/{self.channel_id}/videos/{listing_tab}"
        target_title = (self.metadata.get("title") or "").strip()
        target_match = target_title[:50] if target_title else ""

        studio_error_markers = (
            "oops, something went wrong",
            "something went wrong",
            "algo salió mal",
            "algo salio mal",
            "ha ocurrido un error",
            "se produjo un error",
            "intenta volver a cargar",
            "try reloading",
            "try again later",
            "vuelve a intentarlo",
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

            # Retry the navigation if YT Studio greets us with the "Oops"
            # error page or with an empty listing. Up to 5 attempts, each
            # gives the page a few seconds to render.
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
                # No rows, no error — listing might just be slow. Retry anyway.
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
                return build_url(video_id)
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

    def _robust_click(self, driver, element, label: str = "") -> bool:
        """
        Click an element in YouTube Studio in a way that survives the two
        failure modes we keep seeing:

          (a) ElementClickInterceptedException — another node (hashtag tooltip,
              tutorial overlay, sticky header) sits on top of the target. The
              standard `.click()` aims at the visual coordinates and hits the
              overlay instead.
          (b) ElementNotInteractableException — the element is in the DOM but
              hasn't been scrolled into view yet (long Details panel, the
              visibility radios live way below the fold).

        Strategy: scroll the element to the center of the viewport, try a
        normal click, and if that fails for any reason fall back to a JS click
        which dispatches the event directly on the node and ignores overlays.
        Returns True on success, False if both attempts blow up.
        """
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                element,
            )
            time.sleep(0.4)
        except Exception:
            pass
        try:
            element.click()
            return True
        except Exception as e:
            if get_verbose() and label:
                warning(
                    f"\t=> {label}: standard click intercepted ({type(e).__name__}); "
                    "falling back to JS click."
                )
            try:
                driver.execute_script("arguments[0].click();", element)
                return True
            except Exception as e2:
                if label:
                    warning(f"\t=> {label}: JS click also failed: {str(e2)[:160]}")
                return False

    def upload_video(self) -> bool:
        """
        Uploads the video to YouTube via Selenium.
        Uses explicit waits and robust element selection for YouTube Studio 2025+.

        Returns:
            success (bool): Whether the upload was successful or not.
        """
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys

        # Guard: refuse to upload if the generation pipeline aborted (e.g.
        # duplicate-topic guard fired).
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
            # Step 1: Get channel ID
            if verbose:
                info("\t=> Getting channel ID...")
            self.get_channel_id()
            if verbose:
                info(f"\t=> Channel ID: {self.channel_id}")

            # Step 2: Navigate to upload page
            if verbose:
                info("\t=> Navigating to upload page...")
            driver.get("https://www.youtube.com/upload")
            time.sleep(3)

            # Step 3: Upload the video file
            if verbose:
                info(f"\t=> Uploading file: {self.video_path}")

            # Find the file input (hidden input inside the upload picker)
            file_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )
            file_input.send_keys(self.video_path)

            if verbose:
                info("\t=> File selected, waiting for upload dialog...")

            # Wait for the upload dialog to appear (title textbox)
            time.sleep(8)

            # Step 4: Set title
            if verbose:
                info("\t=> Setting title...")

            # YouTube Studio uses contenteditable divs with id="textbox"
            textboxes = wait.until(
                EC.presence_of_all_elements_located((By.ID, YOUTUBE_TEXTBOX_ID))
            )

            if len(textboxes) < 2:
                warning(f"Expected 2+ textboxes, found {len(textboxes)}")

            title_el = textboxes[0]
            # Use JavaScript click to bypass overlay dialogs (dialog-scrim, social-suggestions)
            # that YouTube Studio renders on top of the title field.
            driver.execute_script("arguments[0].scrollIntoView(true);", title_el)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", title_el)
            time.sleep(0.5)
            title_el.send_keys(Keys.CONTROL + "a")
            time.sleep(0.3)
            title_el.send_keys(Keys.DELETE)
            time.sleep(0.3)

            # Type the new title character by character to avoid issues
            clean_title = self.metadata["title"].replace("\n", " ")[:100]
            title_el.send_keys(clean_title)
            time.sleep(1)

            if verbose:
                info(f"\t=> Title set: {clean_title}")

            # Step 5: Set description
            if verbose:
                info("\t=> Setting description...")

            description_el = textboxes[-1]
            # Use JavaScript click to bypass the "Suggested hashtags" panel
            # that YouTube Studio renders between title and description fields.
            # A normal .click() fails with ElementClickInterceptedException.
            driver.execute_script("arguments[0].scrollIntoView(true);", description_el)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", description_el)
            time.sleep(0.5)
            description_el.send_keys(Keys.CONTROL + "a")
            time.sleep(0.3)
            description_el.send_keys(Keys.DELETE)
            time.sleep(0.3)

            clean_desc = self.metadata["description"].replace("\n", " ")[:5000]
            description_el.send_keys(clean_desc)
            time.sleep(1)

            if verbose:
                info("\t=> Description set")

            # Step 6: Set "Not made for kids"
            if verbose:
                info("\t=> Setting 'not made for kids'...")

            try:
                if not get_is_for_kids():
                    not_for_kids = wait.until(
                        EC.presence_of_element_located((By.NAME, YOUTUBE_NOT_MADE_FOR_KIDS_NAME))
                    )
                    self._robust_click(driver, not_for_kids, "kids radio (not for kids)")
                else:
                    for_kids = wait.until(
                        EC.presence_of_element_located((By.NAME, YOUTUBE_MADE_FOR_KIDS_NAME))
                    )
                    self._robust_click(driver, for_kids, "kids radio (made for kids)")
                time.sleep(1)
            except Exception as e:
                warning(f"Could not set kids option: {e}")

            # Step 6.5: Upload custom thumbnail (long videos only — set by generate_thumbnail()).
            # Strategy: send_keys() returning without exception is NOT proof that YouTube
            # accepted the file. Empirically, the file can fail to register (busy uploader
            # widget, oversized file, channel not verified, stale input element) while
            # send_keys silently succeeds, and clicking Next then publishes with the
            # auto-generated thumbnail. So: visual verification is REQUIRED before we
            # leave the Details panel; if we can't verify, we retry the whole upload.
            thumb_path = getattr(self, "thumbnail_path", "")
            self._thumbnail_uploaded = False
            if thumb_path and os.path.isfile(thumb_path):
                abs_thumb = os.path.abspath(thumb_path)

                # Pre-flight: YouTube silently rejects thumbnails over 2 MB. If we're
                # over the limit, re-encode as JPEG (quality 90) into a sibling path
                # so the original PNG is preserved for manual recovery.
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

                # Scroll the thumbnail editor into view (it's below title/description).
                try:
                    editor = driver.find_element(
                        By.CSS_SELECTOR,
                        "ytcp-thumbnails-compact-editor, ytcp-thumbnail-uploader, ytcp-thumbnails-compact-editor-uploader",
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor)
                    time.sleep(1)
                except Exception:
                    pass

                VERIFY_TIMEOUT_S = 180         # YT can take a while to render the preview
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
                        # Force the (usually hidden) input to be interactable.
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
                        # Give YouTube Studio a few seconds to commit the upload to its
                        # internal video draft state. Empirically, navigating away too
                        # fast can cause the thumbnail to revert to the auto-generated one.
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

            # Step 7: Click Next 3 times (Details → Video elements → Checks → Visibility)
            for step_num in range(3):
                if verbose:
                    info(f"\t=> Clicking Next (step {step_num + 1}/3)...")
                try:
                    next_btn = wait.until(
                        EC.presence_of_element_located((By.ID, YOUTUBE_NEXT_BUTTON_ID))
                    )
                    if not self._robust_click(driver, next_btn, f"Next step {step_num + 1}/3"):
                        warning(f"Next button step {step_num + 1} could not be clicked.")
                    time.sleep(2)
                except Exception as e:
                    warning(f"Next button step {step_num + 1} failed: {e}")

            # Step 8: Set visibility to Unlisted (radio button index 2)
            if verbose:
                info("\t=> Setting visibility to Unlisted...")

            time.sleep(2)
            try:
                radio_buttons = driver.find_elements(By.XPATH, YOUTUBE_RADIO_BUTTON_XPATH)
                if len(radio_buttons) >= 3:
                    self._robust_click(driver, radio_buttons[2], "visibility radio")  # 0=Private, 1=Unlisted, 2=Public
                elif len(radio_buttons) >= 2:
                    self._robust_click(driver, radio_buttons[1], "visibility radio (fallback idx 1)")
                time.sleep(1)
            except Exception as e:
                warning(f"Could not set visibility: {e}")

            # Step 9: Click Done
            if verbose:
                info("\t=> Clicking Done button...")

            try:
                done_btn = wait.until(
                    EC.presence_of_element_located((By.ID, YOUTUBE_DONE_BUTTON_ID))
                )
                if not self._robust_click(driver, done_btn, "Done button"):
                    warning("Done button could not be clicked.")
            except Exception as e:
                warning(f"Done button failed: {e}")

            is_long_video = bool(getattr(self, "_is_long_video", False))

            # CRITICAL: persist the cache entry RIGHT NOW with a placeholder URL.
            # Even if Firefox crashes / network drops mid-upload, the title, description,
            # subject and date are saved so nothing is lost.
            cache_entry = {
                "title": self.metadata["title"],
                "description": self.metadata["description"],
                "subject": self.subject,
                "url": "uploading...",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "thumbnail_path": getattr(self, "thumbnail_path", "") or "",
                "is_short": not is_long_video,
            }
            try:
                self.add_video(cache_entry)
                if verbose:
                    info("\t=> Cache entry saved (with placeholder URL)")
            except Exception as e:
                warning(f"Could not pre-save cache entry: {e}")

            # Step 9.5: Wait for the file transfer to actually finish.
            # Both long videos and Shorts now use the SAME strategy: poll the
            # channel listing in a SEPARATE tab so the upload tab is never
            # navigated/refreshed (which would cancel the upload). The only
            # differences are the listing URL and the timeouts.
            if not getattr(self, "channel_id", None):
                try:
                    self.get_channel_id()
                except Exception as e:
                    warning(f"Could not resolve channel_id before upload wait: {e}")

            if is_long_video:
                if verbose:
                    info("\t=> Long video — polling listing page in a separate tab...")
                upload_finished = self._wait_for_listing_settled(
                    driver,
                    listing_tab="upload_video",
                    kind_label="long video",
                    max_wait_s=10800,        # 3h total cap (HD 30+ min videos can take a while to encode)
                    poll_interval_s=15,
                    refresh_interval_s=120,  # refresh status tab every 2 min
                )
            else:
                if verbose:
                    info("\t=> Short video — polling listing page in a separate tab...")
                upload_finished = self._wait_for_listing_settled(
                    driver,
                    listing_tab="short",
                    kind_label="Short",
                    max_wait_s=1800,         # 30 min total cap
                    poll_interval_s=8,
                    refresh_interval_s=60,
                )

            # Step 10: Get the video URL.
            # For long videos we ALWAYS resolve via a separate tab — even when
            # the wait succeeded, navigating the original tab is risky if any
            # background processing is still in flight, and the user has asked
            # that the upload tab never be touched programmatically.
            if verbose:
                info("\t=> Getting video URL...")

            listing_tab = "upload_video" if is_long_video else "short"
            url = None

            if is_long_video:
                url = self._resolve_video_url_safe(driver, listing_tab) or None
            else:
                # Shorts: original behavior (navigate the same tab — Firefox is
                # about to be closed anyway when the short upload is confirmed).
                try:
                    driver.get(
                        f"https://studio.youtube.com/channel/{self.channel_id}/videos/{listing_tab}"
                    )
                    time.sleep(3)

                    target_title = (self.metadata.get("title") or "").strip()
                    videos = driver.find_elements(By.TAG_NAME, "ytcp-video-row")

                    chosen_href = None
                    for row in videos[:15]:
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

                    if not chosen_href and videos:
                        try:
                            chosen_href = videos[0].find_element(By.TAG_NAME, "a").get_attribute("href")
                        except Exception:
                            chosen_href = None

                    if chosen_href:
                        if verbose:
                            info(f"\t=> Found URL: {chosen_href}")
                        video_id = chosen_href.split("/")[-2]
                        url = build_url(video_id)
                except Exception as e:
                    warning(f"Could not get video URL: {e}")

            if url:
                self.uploaded_video_url = url
                success(f" => Uploaded Video: {url}")
                # Update the placeholder cache entry with the real URL.
                try:
                    self._update_last_video_url(cache_entry["date"], url)
                except Exception as e:
                    warning(f"Could not update cache URL: {e}")
            else:
                self.uploaded_video_url = "https://studio.youtube.com"
                warning(" => Could not retrieve video URL — check YouTube Studio manually. "
                        "Cache entry has placeholder URL.")

            # CRITICAL: never auto-close Firefox for long videos. The user has explicitly
            # asked that the browser stay open through upload + processing + verification
            # so they can manually confirm everything before closing it.
            #
            # For shorts: only close Firefox if we BOTH (a) saw the wait-for-upload
            # finish cleanly AND (b) successfully retrieved the public URL. Otherwise
            # leave it open so the user can confirm manually — same philosophy as long
            # videos, just less verbose.
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
            # DO NOT quit the driver on exception — the upload may still be in flight
            # in the background and closing Firefox would abort it. Keep the browser
            # open in BOTH long-video and short modes so the user can confirm what
            # actually made it to YouTube before closing manually.
            warning("Leaving Firefox open so the upload can finish in the background. "
                    "Close the browser manually after YouTube Studio shows the upload is done.")
            return False

    def _update_last_video_url(self, date_marker: str, new_url: str) -> None:
        """Update the URL field of the cache entry that matches `date_marker`."""
        cache = get_youtube_cache_path()
        with open(cache, "r", encoding="utf-8") as f:
            data = json.load(f)
        for account in data.get("accounts", []):
            if account.get("id") != self._account_uuid:
                continue
            for video in account.get("videos", []):
                if video.get("date") == date_marker and video.get("url") in ("uploading...", "", None):
                    video["url"] = new_url
                    break
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_videos(self) -> List[dict]:
        """
        Gets the uploaded videos from the YouTube Channel.

        Returns:
            videos (List[dict]): The uploaded videos.
        """
        if not os.path.exists(get_youtube_cache_path()):
            # Create the cache file
            with open(get_youtube_cache_path(), "w", encoding="utf-8") as file:
                json.dump({"videos": []}, file, indent=4)
            return []

        videos = []
        # Read the cache file
        with open(get_youtube_cache_path(), "r", encoding="utf-8") as file:
            previous_json = json.loads(file.read())
            # Find our account
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    videos = account["videos"]

        return videos
