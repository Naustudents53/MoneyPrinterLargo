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

        self.images = []
        self._used_stock_urls: set = set()
        self.word_timestamps = None
        self.thumbnail_path: str = ""

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

        # ---- 3. Pre-compute past signatures ----
        past_clean = [_strip_markdown(t) for t in past_topics]
        past_norm = [_normalize(t) for t in past_clean]
        past_entities = [_extract_entities(t) for t in past_clean]

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

        def _is_duplicate(candidate: str) -> tuple[bool, str]:
            cand_clean = _strip_markdown(candidate)
            if not cand_clean:
                return False, ""
            cand_norm = _normalize(cand_clean)
            cand_ents = _extract_entities(cand_clean)

            for original, p_norm, p_ents in zip(past_topics, past_norm, past_entities):
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
        forbidden_block = ""
        if past_topics:
            shown = past_clean[-60:]
            all_ents: set = set()
            for ents in past_entities[-60:]:
                all_ents.update(ents)
            entity_list = sorted(e for e in all_ents if len(e) >= 4)[:80]
            forbidden_block = (
                "\n\nIMPORTANT: Do NOT repeat, rephrase, or pick a similar angle "
                "to ANY of these previously made videos:\n"
                + "\n".join(f"- {t}" for t in shown)
            )
            if entity_list:
                forbidden_block += (
                    "\n\nFORBIDDEN keywords/entities (already covered — your topic must NOT "
                    "involve ANY of these people, places, events, or concepts):\n"
                    + ", ".join(entity_list)
                )
            forbidden_block += "\n\nGenerate a COMPLETELY DIFFERENT and ORIGINAL idea."

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

CRITICAL RULE: The topic MUST be directly and obviously related to the niche above. Do NOT generate topics about unrelated subjects like history, politics, celebrities, cinema, or any field outside the niche. If the niche is about the universe and the mind, the topic must be about the universe and the mind — NOT about historical figures, civilizations, or unrelated events.

The topic must be ONE concrete story, event, mystery, or fact — NOT a broad category.

BAD example: "Curiosidades del antiguo Egipto" (too broad, leads to random facts)
GOOD example: "La maldición de la tumba de Tutankamón: ¿qué les pasó a los arqueólogos?" (one specific story)
GOOD example: "¿Por qué los romanos usaban orina para lavar la ropa?" (one specific curiosity)
GOOD example: "El día que un asteroide exterminó al 75% de la vida en la Tierra" (one specific event)

OUTPUT FORMAT (strict):
- Return ONLY the topic as one plain sentence.
- NO markdown (no **, no backticks, no headers).
- NO prefixes like "Topic:", "Tema:", "Title:".
- NO surrounding quotes.
- WRITE ENTIRELY IN {self.language}. Every word must be in {self.language}.{forbidden_block}{extra_reject}

(Creativity seed: {creativity_seed} — use this to inspire a unique, unexpected angle.)"""
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
        # Spanish examples (content language) — the LLM adapts to self.language.
        hook_styles = [
            ("Classic curiosity question", '"¿Sabías que...?"'),
            ("Invitation to imagine a scene", '"Imagínate esto:" o "Imagina que..."'),
            ("Direct shocking statistic (no question)", '"El 90% de la gente no sabe que..."'),
            ("Hidden secret reveal", '"Hay algo que nadie te contó sobre..."'),
            ("Counterintuitive claim", '"Todo lo que crees sobre X está mal."'),
            ("Negation cliffhanger", '"No vas a creer lo que pasó cuando..."'),
        ]
        hook_style, hook_example = random.choice(hook_styles)

        if get_verbose():
            info(f" => Hook style for this script: {hook_style}")

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
        title = self.generate_response(
            f"Please generate a YouTube Video Title for the following subject: {self.subject}. "
            f"Optionally include 1-2 relevant hashtags at the end (but only if they fit naturally). "
            f"Only return the title, nothing else. Limit the title under 80 characters. Be concise. "
            f"YOU MUST WRITE THE TITLE IN {self.language}. Do NOT wrap the title in quotes. Do NOT start or end with any quote character."
        )

        # Strip any quotes the LLM might add (regular, curly, single)
        title = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', title.strip()).strip()

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

These queries will be searched against Wikipedia articles + Wikimedia Commons + Met Museum + Library of Congress. Tailor the wording for those archives.

CRITICAL: use the CANONICAL ENGLISH NAME (the form Wikipedia uses for the article title) for every person, place, event, or work. Examples:
  - WRONG: "Hipparchus the astronomer of stars"   →   RIGHT: "Hipparchus of Nicaea"
  - WRONG: "Marco Aurelio philosophy book"        →   RIGHT: "Marcus Aurelius" or "Meditations Marcus Aurelius"
  - WRONG: "Roman vestal virgin priestess fire"   →   RIGHT: "Vestal Virgins" or "Temple of Vesta"
  - WRONG: "Alexander conquering Persians battle" →   RIGHT: "Battle of Gaugamela"
  - WRONG: "ancient Egypt cat goddess statue"     →   RIGHT: "Bastet" or "Egyptian cat goddess"
A Wikipedia article should EXIST for the subject of every query. If unsure, prefer the proper noun on its own.

The script has been divided into {n_prompts} sections. Each query must match its section:
{sections_text}
INSTRUCTIONS:
- Query 1 finds a photo for SECTION 1, Query 2 for SECTION 2, etc.
- Use PROPER NOUNS: real names of people, places, buildings, objects, events.
- 3 to 7 words per query. No full sentences.
- FORBIDDEN words: cinematic, dramatic, lighting, 8K, 4K, photorealistic, HD, macro, bokeh, shot, close-up, aerial, style, composition, render, aesthetic. No adjectives describing mood or camera.
- Good examples: "Cosimo I de Medici portrait", "Torre dei Mannelli Florence", "Ponte Vecchio historical engraving", "Giorgio Vasari self-portrait".
- Bad examples: "a dramatic portrait of a duke", "beautiful Italian architecture at golden hour".
- Write in English (Wikimedia/stock sites index in English).

Return ONLY a JSON array of {n_prompts} strings. No markdown, no explanation."""
        else:
            prompt = f"""Generate exactly {n_prompts} image prompts for a video about: {self.subject}

The script has been divided into {n_prompts} sections. Each image MUST match its section:
{sections_text}
INSTRUCTIONS:
- Image 1 MUST illustrate SECTION 1, Image 2 MUST illustrate SECTION 2, etc.
- Describe the LITERAL content of each section as a visual scene.
- Example: if a section says "The ancient Egyptians built massive pyramids", write: "Massive Egyptian pyramids under construction, thousands of workers pulling limestone blocks, desert sand, blue sky, cranes made of wood, cinematic wide angle"
- Be SPECIFIC: name real things (animals, buildings, objects, places, people).
- Include: camera angle, lighting, colors, environment details.
- Write in English. Each prompt: 30-60 words.
- FORBIDDEN: visualization, concept, essence, metaphor, abstract, symbolic, interpretation.

Return ONLY a JSON array of {n_prompts} strings. No markdown, no explanation."""

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        image_prompts = []

        # Try to extract JSON array from the response
        try:
            parsed = json.loads(completion)
            if isinstance(parsed, list):
                image_prompts = [str(p) for p in parsed if isinstance(p, str)]
            elif isinstance(parsed, dict) and "image_prompts" in parsed:
                image_prompts = parsed["image_prompts"]
        except Exception:
            # Try to find a JSON array in the response
            match = re.search(r'\[.*?\]', completion, re.DOTALL)
            if match:
                try:
                    image_prompts = json.loads(match.group())
                except Exception:
                    pass

        # Fallback if parsing failed or too few prompts
        if image_mode == "photos":
            fallback_prompts = [self.subject] * n_prompts
        else:
            fallback_prompts = [
                f"{self.subject}, realistic photograph, wide angle, natural lighting, highly detailed, 8K",
                f"{self.subject}, close-up detail shot, soft natural light, vivid colors, photorealistic",
                f"{self.subject}, panoramic landscape view, golden hour, cinematic composition, detailed",
                f"{self.subject}, historical illustration style, warm earth tones, detailed environment",
                f"{self.subject}, overhead aerial perspective, dramatic clouds, vast scale, ultra detailed",
                f"{self.subject}, documentary photograph, authentic setting, natural atmosphere, 4K quality",
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
        """Try Leonardo AI API (excellent quality, $5 free credit)."""
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
            "prompt": prompt[:1000],
            "modelId": "b24e16ff-06e3-43eb-8d33-4416c2d75876",  # Leonardo Lightning XL
            "width": 576,
            "height": 1024,
            "num_images": 1,
        }
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
        """Wrap a short photo-mode search query with cinematic styling so AI generators render a usable image."""
        out = f"{query}, cinematic photograph, photorealistic, dramatic lighting, highly detailed, 4K"
        return self._apply_channel_style(out)

    def _apply_channel_style(self, prompt: str) -> str:
        """Append the per-channel image_style suffix (if any), capped to keep providers happy."""
        if not self._image_style:
            return prompt
        combined = f"{prompt.rstrip(', .')}, {self._image_style}"
        # Hard cap to ~1000 chars so we don't blow past Leonardo / Pollinations input limits.
        return combined[:1000]

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

        # Relevance filter: alt text must share a keyword with the subject/query.
        relevance_tokens = self._query_tokens(query, self.subject)
        if relevance_tokens:
            relevant = [p for p in photos if relevance_tokens & self._query_tokens(p.get("alt") or "")]
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

        # Relevance filter: Pixabay `tags` is a comma-separated list — require keyword overlap.
        relevance_tokens = self._query_tokens(query, self.subject)
        if relevance_tokens:
            relevant = [h for h in hits if relevance_tokens & self._query_tokens(h.get("tags") or "")]
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

        headers = {"User-Agent": "MoneyPrinterV2/1.0 (research use)"}
        relevance_tokens = self._query_tokens(query, self.subject)

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
                    # Optional relevance check using the article title.
                    if relevance_tokens:
                        if not (relevance_tokens & self._query_tokens(title)):
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

        headers = {"User-Agent": "MoneyPrinterV2/1.0 (https://github.com/; research use)"}
        relevance_tokens = self._query_tokens(query, self.subject)

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
                    # Relevance check: the file's title (e.g. "File:Hipparchus.jpg") should
                    # share at least one significant token with the query/subject.
                    if relevance_tokens:
                        if not (relevance_tokens & self._query_tokens(title)):
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
        headers = {"User-Agent": "MoneyPrinterV2/1.0 (research use)"}

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
        relevance_tokens = self._query_tokens(query, self.subject)

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
                # Relevance check against the object's metadata.
                metadata_blob = " ".join(
                    str(obj.get(k, "")) for k in
                    ("title", "culture", "period", "objectName", "department",
                     "classification", "artistDisplayName", "country", "region")
                )
                if relevance_tokens:
                    blob_tokens = self._query_tokens(metadata_blob)
                    if not (relevance_tokens & blob_tokens):
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
        headers = {"User-Agent": "MoneyPrinterV2/1.0 (research use)"}
        search_url = (
            f"https://www.loc.gov/photos/?q={urllib.parse.quote(query)}&fo=json&c=25"
        )
        resp = requests.get(search_url, headers=headers, timeout=30)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            raise RuntimeError("LoC: no results")

        relevance_tokens = self._query_tokens(query, self.subject)
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
            if relevance_tokens:
                blob_tokens = self._query_tokens(title, str(descr), subj_text)
                if not (relevance_tokens & blob_tokens):
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
                # Tier 1: curated, attribution-friendly historical/educational sources
                # (Wikipedia-style — factual, on-topic). Wikipedia article first because
                # it returns the curated infobox image (more reliable than Commons file search).
                ("Wikipedia article", self._try_wikipedia_article, "stock"),
                ("Wikimedia Commons", self._try_wikimedia, "stock"),
                ("Met Museum", self._try_met_museum, "stock"),
                ("Library of Congress", self._try_loc, "stock"),
                # Tier 2: modern stock (filtered by relevance) — useful for non-historical topics
                ("Pexels", self._try_pexels, "stock"),
                ("Pixabay", self._try_pixabay, "stock"),
                # Tier 3: AI fallback when no real photo matches the topic
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
        self.script = clean_script_for_tts(self.script)
        tts_text, regnal_subs = expand_regnal_numerals_tracked(self.script)

        # Per-channel short voice override (falls back to TTS instance default if empty).
        short_vid = self._resolve_voice(self._short_voice)
        path, word_timestamps = tts_instance.synthesize_with_timestamps(tts_text, path, voice_id=short_vid or None)

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
            info(" [Script] Gemini detected — trying single-call fast path...")
            try:
                full = self._generate_long_script_single_call(lang)
                word_count = len(full.split())
                if word_count >= 2000:
                    full = self._postprocess_long_script(full)
                    self.script = full
                    self._persist_long_script(full)
                    info(f" => Generated long script: {len(full.split())} words (~{len(full.split()) // 165} min)")
                    return full
                warning(f"   Single-call returned only {word_count} words; falling back to per-section.")
            except Exception as e:
                warning(f"   Single-call failed: {str(e)[:200]}; falling back to per-section.")

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
        prompt = f"""Eres un narrador experto de documentales y guionista profesional.
Escribe un GUION COMPLETO de narración cautivador de 15 a 20 minutos sobre el siguiente tema.

Tema: {self.subject}

ESTRUCTURA OBLIGATORIA (usa estos marcadores EXACTOS):
[INTRO]
Gancho inicial poderoso (5-7 oraciones, 120-180 palabras). Empieza con un dato impactante, pregunta provocadora o afirmación audaz.

[SECTION 1: <título corto>]
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
Consecuencias, legado o impacto del tema en la actualidad (10-14 oraciones, 250-350 palabras).

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
- NO acotaciones, NO etiquetas de hablante, NO meta-texto.
- NO markdown, NO viñetas, NO listas numeradas.
- NO URLs, enlaces, citas ni referencias.
- SOLO devuelve el guion completo con los 12 marcadores arriba listados. Sin preámbulo.
"""
        completion = self._clean_llm_script(self.generate_response(prompt))
        return completion

    def _generate_long_script_sectional(self, lang: str) -> str:
        """Per-section generation (12 calls) for providers with low output caps."""

        # Per-section thematic guidance — what role each section plays in the narrative arc.
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

REGLAS:
- 5-7 oraciones (120-180 palabras).
- Empieza con un gancho poderoso: dato impactante, pregunta provocadora o afirmación audaz.
- Lenguaje vívido y sensorial. Oraciones CORTAS (máximo 20 palabras).
- ESCRIBE TODO EN {lang}. NO uses inglés.
- NO uses markdown, viñetas, listas, URLs, ni meta-texto.
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
- Devuelve SOLO el texto de la sección, precedido EXACTAMENTE por una línea con: [SECTION {i}: <título breve descriptivo>]
"""
            section = _ensure_marker(_ask_section(section_prompt, min_words=180), f"[SECTION {i}: parte {i}]")
            parts.append(section)
            info(f"   [Script] SECTION {i}: {len(section.split())} words")

        # ---- CLOSING ----
        prior = "\n\n".join(parts)
        tail = " ".join(prior.split()[-300:])
        closing_prompt = f"""Eres un narrador experto de documentales. Estás escribiendo el CIERRE de un guion sobre: {self.subject}

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

        # Step 1: ask LLM for the visual concept + overlay words.
        llm_raw = str(self.generate_response(
            f"""Design a YouTube thumbnail for this video.

VIDEO TITLE: {video_title or "(see topic)"}
TOPIC: {self.subject}

Return ONLY a JSON object with two fields:

- "visual": ENGLISH prompt (40-70 words) for an AI image generator. CRITICAL RULES:
  * The image MUST be visually unmistakable as the topic — name the actual SPECIFIC people, places, objects, clothing, architecture, era, or symbols from the topic. Use proper nouns when relevant.
  * Build ONE single dramatic scene, not a list of unrelated elements.
  * Include: dramatic side lighting, high contrast, shallow depth of field, cinematic composition, photorealistic.
  * End the prompt with: "no text, no letters, no logos, no watermark".
  * FORBIDDEN: generic phrases like "person looking", "mysterious figure", "abstract concept" — be SPECIFIC.

- "words": a CLICKBAIT TEASER PHRASE in {self.language}, ALL UPPERCASE, for the thumbnail overlay. ABSOLUTELY CRITICAL RULES:
  * Length: 3 to 6 words forming a COMPLETE PUNCHY PHRASE. NEVER return a single word.
  * It must SOUND like a YouTube clickbait teaser — provoke curiosity, hint at a revelation, or pose a question fragment. It is NOT a label.
  * It must be CLEARLY tied to the video's title or topic — pick the most charged real words from the title/topic and arrange them.
  * EVERY WORD must already appear (literally or as a clear root form) in the VIDEO TITLE or TOPIC above. DO NOT INVENT WORDS. Each word must be a correctly-spelled real word in {self.language}.
  * Good examples (assuming the title contained those words):
      Title "El patrón OCULTO de la historia" → "EL PATRÓN OCULTO DE LA HISTORIA" or "EL PATRÓN QUE OCULTARON".
      Title "¿Por qué COLAPSAN las civilizaciones?" → "POR QUÉ COLAPSAN TODAS" or "EL FIN DE LAS CIVILIZACIONES".
      Title "El SECRETO de Anubis" → "EL SECRETO DE ANUBIS" or "ANUBIS Y SU SECRETO".
  * BAD examples: "SECRETO" (single word, no teaser), "NADIE LO SABE" (cliché), "INCREÍBLE" (generic).
  * AVOID these overused clichés entirely: "NADIE LO SABE", "NUNCA LO SABE", "TE VA A IMPACTAR", "INCREÍBLE", "JAMÁS LO CREERÁS".

Return ONLY the JSON. No markdown, no explanation."""
        )).replace("```json", "").replace("```", "").strip()

        visual_prompt = ""
        overlay_words = ""
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

        def _validate_overlay(candidate: str) -> bool:
            """Reject if too short, banned, or any content word is hallucinated."""
            if not candidate:
                return False
            if candidate in BANNED_OVERLAYS:
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
            warning(f"Thumbnail: LLM overlay '{overlay_words}' rejected (hallucinated or banned).")
            overlay_words = ""

        if not visual_prompt:
            visual_prompt = (
                f"Dramatic cinematic close-up related to {self.subject}, "
                f"intense expression, golden rim lighting, dark moody background, "
                f"high contrast, ultra-detailed, no text"
            )

        # Deterministic fallback path (always coherent with title — never hallucinates).
        if not overlay_words and video_title:
            clean_title = re.sub(r"[¿?¡!,.:;\"'“”‘’]", "", video_title).strip()
            tw = clean_title.split()
            STOP = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "o",
                    "que", "por", "qué", "para", "con", "en", "a", "su", "sus", "lo"}

            # 1. Find UPPERCASE keyword (the title generator always puts 1-2 in caps) and
            #    grab a wider window around it for a proper teaser phrase (3-5 words).
            caps_idx = next(
                (i for i, w in enumerate(tw)
                 if re.match(r"^[A-ZÁÉÍÓÚÜÑ]{4,}$", w)),
                None,
            )
            if caps_idx is not None:
                start = max(0, caps_idx - 2)
                end = min(len(tw), caps_idx + 4)
                chunk = tw[start:end]
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
                meaningful = [w for w in tw if w.lower() not in STOP and len(w) > 2]
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
            ][:5]
            overlay_words = " ".join(topic_words).upper() if topic_words else "DESCUBRE LA VERDAD"
            warning(f"Thumbnail: using topic-derived overlay text: {overlay_words}")

        # Step 2: render the background image (Leonardo first, Pollinations fallback).
        bg_bytes = None
        for name, fn in (
            ("Leonardo AI", self._try_leonardo_landscape),
            ("Pollinations FLUX 16:9", self._try_pollinations_landscape),
        ):
            try:
                bg_bytes = fn(visual_prompt)
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
            for cand in (
                r"C:\Windows\Fonts\impact.ttf",
                r"C:\Windows\Fonts\arialbd.ttf",
                os.path.join(get_fonts_dir(), get_font()),
            ):
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

        prompt = f"""Generate exactly {n_prompts} image prompts for a long-form documentary video.

TOPIC: {self.subject}

The narration is divided into {n_prompts} sections. Each image must illustrate ITS section.
{sections_text}
CRITICAL RULES:
- Image N MUST illustrate SECTION N. Read the section text and describe the LITERAL scene, person, object or event it talks about.
- Every prompt must be visually unmistakable as the TOPIC. Name the actual SPECIFIC people, places, objects, era, clothing, architecture, or symbols from the section text. Use proper nouns when relevant.
- Be CONCRETE: describe exactly what appears (subjects, setting, lighting, colors, composition).
- 30-60 words per prompt.
- All images are 16:9 landscape, photorealistic, cinematic. Vary camera angles and lighting (wide shot, close-up, low angle, golden hour, candlelight, overcast, etc.) but DO NOT change the subject matter to fit a style.
- ABSOLUTELY FORBIDDEN: cosmic / space / nebula imagery (unless the topic is astronomy), microscopic / scientific diagrams (unless the topic is biology/chemistry), futuristic holographic / sci-fi visuals (unless the topic is futurism), abstract geometric / fractal patterns, generic "concept" or "metaphor" visualizations. NEVER swap topical content for these styles.
- ALSO FORBIDDEN words: visualization, concept, essence, metaphor, abstract, symbolic, interpretation.
- Write in English.

Return ONLY a JSON array of {n_prompts} strings. No markdown, no explanation."""

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        image_prompts = []
        try:
            parsed = json.loads(completion)
            if isinstance(parsed, list):
                image_prompts = [str(p) for p in parsed if isinstance(p, str)]
        except Exception:
            match = re.search(r'\[.*\]', completion, re.DOTALL)
            if match:
                try:
                    image_prompts = json.loads(match.group())
                except Exception:
                    pass

        # Fallback: build a topic-anchored prompt per section so images stay on-topic
        # even when the LLM fails to produce a parseable JSON array.
        if not image_prompts or len(image_prompts) < 4:
            if get_verbose():
                warning("Failed to parse long video prompts, using section-anchored fallback")
            fallback_styles = [
                "cinematic wide shot, dramatic side lighting, film grain",
                "close-up detail, shallow depth of field, soft natural light",
                "low angle hero shot, golden hour, epic scale",
                "atmospheric scene, volumetric light, moody shadows",
                "documentary photography, available light, candid framing",
                "intimate medium shot, rim lighting, warm tones",
                "establishing wide vista, overcast diffuse light, painterly",
                "candlelit interior, warm shadows, period-accurate set",
            ]
            image_prompts = [
                (
                    f"Scene from \"{sections[i] if i < len(sections) else self.subject}\" "
                    f"in the context of {self.subject}, {fallback_styles[i % len(fallback_styles)]}, "
                    f"photorealistic, 8K, 16:9 landscape"
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
            "prompt": prompt[:1000],
            "modelId": "b24e16ff-06e3-43eb-8d33-4416c2d75876",  # Leonardo Lightning XL
            "width": 1024,
            "height": 576,
            "num_images": 1,
        }
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
        success(f"\n=> Long video generated: {video_path}")

        return video_path

    def _verify_thumbnail_uploaded(self, driver) -> bool:
        """
        After send_keys(thumbnail.png), confirm YouTube actually accepted it.
        Multiple signals because YT Studio's DOM varies by locale and rollout.
        Returns True if any custom-thumbnail signal is detected.
        """
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
                # Auto-generated thumbnails from YT come from i.ytimg.com / i9.ytimg.com.
                # A custom upload renders as a blob:, data:, or googleusercontent URL.
                if (src.startswith("blob:")
                        or src.startswith("data:image")
                        or "googleusercontent.com" in src
                        or "lh3.google" in src):
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

    def _wait_for_short_upload_complete(self, driver, max_wait_s: int) -> bool:
        """
        Wait for a Short to finish uploading + processing WITHOUT touching the
        original tab (where the upload is happening in the background).

        IMPORTANT: navigating the upload tab to a different URL while the file
        transfer is still in flight CANCELS the upload (YouTube shows "Upload
        interrupted"). So we open a SECOND tab, do the status polling there,
        close it, and return to the original tab untouched.

        Strategy:
          1. Open a new browser tab via JS.
          2. Switch to it and navigate to /videos/short.
          3. Poll the row matching our title until in-progress markers disappear
             (Subiendo / Uploading / Pendiente / Pending / Procesando / Processing /
             Verificando / Checking / Cancelar carga).
          4. ALWAYS close the new tab and switch back to the original tab.

        Returns True when the row settles, False on hard timeout / error.
        """
        info(f"\t=> Waiting up to {max_wait_s // 60} min for Short upload + processing...")
        info("\t   (polling in a SEPARATE tab so the upload tab is never disturbed)")

        deadline = time.time() + max_wait_s
        listing_url = f"https://studio.youtube.com/channel/{self.channel_id}/videos/short"
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

            while time.time() < deadline:
                row_text = ""
                try:
                    rows = driver.find_elements(By.TAG_NAME, "ytcp-video-row")
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

                if row_text:
                    present = [m for m in in_progress_markers if m in row_text]
                    if not present:
                        stable_done_count += 1
                        if stable_done_count >= 2:
                            info("\t=> Short upload + processing finished.")
                            return True
                        info("\t=> Short looks done; confirming with one more poll...")
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
                            info(f"\t=> Short status: {current_status} — still waiting (upload tab untouched)...")
                            last_status = current_status
                            last_announce = now
                else:
                    stable_done_count = 0
                    now = time.time()
                    if (now - last_announce) > 60:
                        info("\t=> Waiting for Short to appear in listing...")
                        last_announce = now

                now = time.time()
                if now - last_refresh > 60:
                    try:
                        driver.refresh()
                        time.sleep(5)
                        last_refresh = time.time()
                    except Exception:
                        pass

                time.sleep(8)

            warning(
                f"\t=> Hit total wait cap of {max_wait_s // 60} min for Short. "
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

    def _wait_for_upload_complete(self, driver, max_wait_s: int) -> bool:
        """
        Two-phase wait. For long videos this NEVER prematurely declares "done":
          PHASE 1 — File transfer waits until %% reaches 99-100, no matter how long
                    the upload sits at 95/96/97/98%.
          PHASE 2 — YouTube-side processing: keeps waiting until ALL in-progress
                    markers (subiendo / procesando / pendiente / verificando) are
                    gone from the page. No "stuck for 20 min, give up" shortcut.

        Returns True only when YouTube is fully done. Returns False on hard total cap.
        """
        info(f"\t=> Waiting up to {max_wait_s // 60} min for upload + YouTube processing...")
        info("\t   (For long videos, Firefox WILL stay open until everything finishes.)")
        deadline = time.time() + max_wait_s

        # ---------- PHASE 1 — File transfer ----------
        upload_done = False
        last_pct_reported = -1

        while time.time() < deadline:
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            except Exception:
                body_text = ""

            m = re.search(r"(?:subiendo|uploading)[^\d%]{0,15}(\d{1,3})\s*%", body_text)
            if m:
                pct = int(m.group(1))
                if pct != last_pct_reported:
                    info(f"\t=> Upload progress: {pct}%")
                    last_pct_reported = pct
                if pct >= 99:
                    info("\t=> File transfer complete (100%). Now YouTube takes over.")
                    upload_done = True
                    break
                # NO frozen-at-X% shortcut: keep waiting for the % to actually reach 99/100.
                # Slow connections sometimes sit at 97-98% for many minutes; that's fine.
            else:
                # No "Subiendo X%" anywhere → file likely already transferred.
                upload_done = True
                info("\t=> No upload progress indicator visible — assuming file already on YT servers.")
                break

            time.sleep(10)

        if not upload_done:
            warning(f"\t=> Upload phase hit hard cap of {max_wait_s}s.")
            return False

        # ---------- PHASE 2 — YouTube processing ----------
        info("\t=> File on YouTube servers. Waiting for processing + verification to finish...")
        info("\t   (encoding to multiple resolutions + Content ID + policy checks — can take 30+ min)")
        # Refresh so we see the post-upload status, not stale dialog state.
        try:
            driver.refresh()
            time.sleep(8)
        except Exception:
            pass

        in_progress_markers = (
            "subiendo", "uploading",
            "procesando", "processing",
            "pendiente", "pending",
            "verificando", "verificaciones en curso",
            "checking", "checks in progress",
        )

        last_status = ""
        last_announce = 0.0
        last_refresh = time.time()

        while time.time() < deadline:
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            except Exception:
                body_text = ""

            present_markers = [m for m in in_progress_markers if m in body_text]

            if not present_markers:
                info("\t=> YouTube finished processing + verification.")
                return True

            # Identify the current stage for the progress log.
            if any(m in present_markers for m in ("subiendo", "uploading")):
                current_status = "still uploading"
            elif any(m in present_markers for m in ("procesando", "processing")):
                current_status = "processing (encoding/checks)"
            elif any(m in present_markers for m in ("verificando", "verificaciones en curso", "checking", "checks in progress")):
                current_status = "running verification checks"
            else:
                current_status = "pending"

            now = time.time()
            if current_status != last_status or (now - last_announce) > 120:
                info(f"\t=> YouTube status: {current_status} — still waiting (Firefox stays open)...")
                last_status = current_status
                last_announce = now

            # Periodically refresh so the page state doesn't go stale and we don't
            # falsely think "the markers disappeared" because of a JS error.
            if now - last_refresh > 300:  # every 5 min
                try:
                    driver.refresh()
                    time.sleep(5)
                    last_refresh = time.time()
                except Exception:
                    pass

            time.sleep(10)

        # Hit the absolute cap. Firefox will stay open because of the caller's logic.
        warning(
            f"\t=> Hit total wait cap of {max_wait_s // 60} min. "
            "Firefox will stay open so YT can keep processing — close it manually when done."
        )
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

            # Step 6.5: Upload custom thumbnail (long videos only — set by generate_thumbnail()).
            thumb_path = getattr(self, "thumbnail_path", "")
            self._thumbnail_uploaded = False
            if thumb_path and os.path.isfile(thumb_path):
                abs_thumb = os.path.abspath(thumb_path)
                info(f"\t=> Uploading thumbnail: {abs_thumb}")

                # Try to scroll the thumbnail editor into view (it's below title/description).
                try:
                    editor = driver.find_element(
                        By.CSS_SELECTOR,
                        "ytcp-thumbnails-compact-editor, ytcp-thumbnail-uploader, ytcp-thumbnails-compact-editor-uploader",
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor)
                    time.sleep(1)
                except Exception:
                    pass

                # Empirically, send_keys() on the file input always succeeds in uploading
                # the thumbnail — what was failing before was the visual verification.
                # So the strategy is:
                #   1. Find the input + send_keys (this is the actual upload trigger).
                #   2. If send_keys raises → it's a real failure → retry once after 120s.
                #   3. If send_keys succeeds → wait for upload to complete and try to
                #      verify visually for logging/UX. Verify failure is NOT treated
                #      as upload failure — we trust send_keys.
                VERIFY_TIMEOUT_S = 90
                VERIFY_POLL_S = 2
                RETRY_BACKOFF_S = 120
                MAX_SENDKEYS_ATTEMPTS = 2
                send_ok = False
                for attempt in range(1, MAX_SENDKEYS_ATTEMPTS + 1):
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
                        send_ok = True
                        info(f"\t=> Thumbnail send_keys OK (attempt {attempt}/{MAX_SENDKEYS_ATTEMPTS}).")
                        break
                    except Exception as e:
                        warning(f"\t=> Thumbnail send_keys attempt {attempt}/{MAX_SENDKEYS_ATTEMPTS} failed: {str(e)[:200]}")
                        if attempt < MAX_SENDKEYS_ATTEMPTS:
                            info(f"\t=> Waiting {RETRY_BACKOFF_S}s before retry...")
                            time.sleep(RETRY_BACKOFF_S)

                if send_ok:
                    # Trust the upload happened. Try to confirm visually for nicer logs,
                    # but don't fail the run if we can't detect the preview.
                    info(f"\t=> Polling up to {VERIFY_TIMEOUT_S}s for thumbnail preview (informational)...")
                    deadline = time.time() + VERIFY_TIMEOUT_S
                    accepted = False
                    while time.time() < deadline:
                        if self._verify_thumbnail_uploaded(driver):
                            accepted = True
                            break
                        time.sleep(VERIFY_POLL_S)
                    self._thumbnail_uploaded = True
                    if accepted:
                        success("\t=> Thumbnail visually confirmed on the page.")
                    else:
                        warning(
                            f"\t=> Thumbnail preview not detected after {VERIFY_TIMEOUT_S}s, "
                            "but send_keys succeeded — assuming upload OK and continuing."
                        )
                        # Save a screenshot so you can verify it actually went through
                        # if there's any doubt.
                        try:
                            debug_path = os.path.join(
                                ROOT_DIR, "thumbnails",
                                f"upload_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                            )
                            driver.save_screenshot(debug_path)
                            info(f"\t=> Saved screenshot for visual confirmation: {debug_path}")
                        except Exception:
                            pass
                else:
                    error(
                        f"Thumbnail upload failed: send_keys errored on all {MAX_SENDKEYS_ATTEMPTS} attempts. "
                        f"The thumbnail file is preserved at:\n    {abs_thumb}\n"
                        "Open YouTube Studio → your video → Edit → upload it manually."
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
                        EC.element_to_be_clickable((By.ID, YOUTUBE_NEXT_BUTTON_ID))
                    )
                    next_btn.click()
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
                    radio_buttons[2].click()  # 0=Private, 1=Unlisted, 2=Public — but YT may reorder
                elif len(radio_buttons) >= 2:
                    radio_buttons[1].click()  # Try unlisted
                time.sleep(1)
            except Exception as e:
                warning(f"Could not set visibility: {e}")

            # Step 9: Click Done
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
            }
            try:
                self.add_video(cache_entry)
                if verbose:
                    info("\t=> Cache entry saved (with placeholder URL)")
            except Exception as e:
                warning(f"Could not pre-save cache entry: {e}")

            # Step 9.5: Wait for the file transfer to actually finish.
            # Long videos (100-300 MB) take several minutes AFTER Done is clicked.
            # Shorts use a DIFFERENT wait strategy: by the time Done is clicked the
            # upload dialog is already being dismissed, so its "Subiendo X%" text is
            # gone — we navigate to the channel's Shorts listing and poll the row
            # there until the in-progress markers (Subiendo / Pendiente / Procesando /
            # Cancelar carga) disappear.
            if is_long_video:
                upload_finished = self._wait_for_upload_complete(driver, max_wait_s=7200)  # 120 min total cap
            else:
                if verbose:
                    info("\t=> Short video — polling listing page for upload + processing...")
                # Make sure we know our channel ID before navigating to /videos/short.
                if not getattr(self, "channel_id", None):
                    try:
                        self.get_channel_id()
                    except Exception as e:
                        warning(f"Could not resolve channel_id before short wait: {e}")
                upload_finished = self._wait_for_short_upload_complete(driver, max_wait_s=1800)  # 30 min total cap

            # Step 10: Get the video URL
            if verbose:
                info("\t=> Getting video URL...")

            url = None
            try:
                # Long videos live under /videos/upload_video; shorts under /videos/short.
                # Hardcoding /videos/short for a long upload would grab the wrong row.
                listing_tab = "upload_video" if is_long_video else "short"
                driver.get(
                    f"https://studio.youtube.com/channel/{self.channel_id}/videos/{listing_tab}"
                )
                time.sleep(3)

                # Match by exact title to avoid grabbing the wrong row when a recent
                # upload of another kind shows up at the top.
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
                    # Fallback: take the first row (most recent).
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
