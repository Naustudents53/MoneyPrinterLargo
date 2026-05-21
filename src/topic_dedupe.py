"""
Topic de-duplication shared by the YouTube pipeline (`generate_topic`) and the
webapp's `/suggest-topics` endpoint.

The earlier dedupe was purely lexical (exact match, token overlap, sequence
similarity). That misses the most common real-world repeat: the same SUBJECT
phrased differently — e.g. "El misterio de Oumuamua: ¿un visitante
interestelar?" vs "Oumuamua, el objeto que desconcertó a la NASA". They share
the subject but few surface words, so overlap fell under the threshold and the
duplicate slipped through.

This module adds a distinctive-entity layer: it extracts the proper nouns /
unique identifiers that anchor a topic to ONE subject (Oumuamua, TRAPPIST-1,
Andrómeda, Dyson, …) and treats two topics as the same if they share one such
anchor, or share two or more distinctive content words.

Stdlib only — safe to import from the FastAPI process without pulling in the
heavy YouTube class (MoviePy, Selenium, etc.).
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable

# --- Stopwords (ES + EN) --------------------------------------------------
_ES_STOP = {
    "el", "la", "los", "las", "de", "del", "que", "y", "o", "u", "en", "un",
    "una", "unos", "unas", "por", "para", "con", "se", "su", "sus", "lo", "al",
    "como", "es", "fue", "era", "ser", "son", "mas", "este", "esta", "esto",
    "estos", "estas", "sobre", "entre", "pero", "si", "no", "ni", "cuando",
    "donde", "quien", "cual", "cuales", "hacia", "desde", "hasta", "sin", "ya",
    "muy", "menos", "todo", "toda", "todos", "todas", "otro", "otra", "otros",
    "otras", "tambien", "solo", "tras", "ante", "bajo",
}
_EN_STOP = {
    "the", "of", "a", "an", "and", "is", "was", "to", "in", "on", "who", "why",
    "how", "what", "were", "are", "be", "been", "have", "has", "had", "with",
    "from", "that", "this", "these", "those", "will", "would", "can", "could",
    "should", "about", "into", "which", "where", "when", "their", "its", "it",
    "by", "at", "as", "or", "but", "for",
}
_STOP = _ES_STOP | _EN_STOP

# --- Generic / non-distinctive vocabulary ---------------------------------
# Words that do NOT pin a topic to a single subject, so they must never count
# as a distinctive anchor. Multi-niche by design: history-flavored terms live
# alongside cosmos/science filler. Adding a real proper noun here would
# silently weaken dedupe, so keep it to genuinely generic words.
_GENERIC = {
    # generic descriptors / framing
    "ancient", "antiguo", "antigua", "antiguos", "antiguas", "old", "viejo",
    "modern", "moderno", "moderna", "history", "historia", "historical",
    "story", "tale", "cuento", "relato", "civilization", "civilizacion",
    "culture", "cultura", "era", "epoca", "period", "periodo",
    "great", "grande", "gran", "famous", "famoso", "famosa", "important",
    "importante", "increible", "incredible", "asombroso", "asombrosa",
    "impactante", "impactantes", "sorprendente", "sorprendentes",
    "misterio", "misterios", "mystery", "mysteries", "misterioso", "misteriosa",
    "secreto", "secretos", "secret", "secrets", "oculto", "oculta", "hidden",
    "descubrimiento", "descubrimientos", "discovery", "fenomeno", "fenomenos",
    "phenomenon", "dato", "datos", "fact", "facts", "curiosidad", "curiosidades",
    "sabias", "verdad", "real", "reales", "increibles", "enigma", "enigmas",
    "mas", "grandes", "extremo", "extrema", "extremos", "extremas",
    "vida", "life", "muerte", "death", "mundo", "world", "tierra", "earth",
    "people", "gente", "person", "persona", "man", "hombre", "woman", "mujer",
    "war", "guerra", "battle", "batalla",
    # cosmos / astronomy generic (the niche itself — not a single subject)
    "cosmos", "cosmico", "cosmica", "universo", "universe", "espacio", "space",
    "espacial", "espaciales", "galaxia", "galaxias", "galaxy", "galaxies",
    "estrella", "estrellas", "star", "stars", "planeta", "planetas", "planet",
    "planets", "sol", "luna", "moon", "sistema", "systema", "system", "solar",
    "agujero", "agujeros", "hole", "holes", "black", "negro", "negra", "negros",
    "objeto", "objetos", "object", "astronomia", "astronomy", "astrofisica",
    "cielo", "sky", "nebula", "nebulosa", "telescopio", "telescope", "sonda",
    "mision", "mission", "fuerza", "energia", "energy", "materia", "matter",
}

# Minimum length for a normalized token to count as "distinctive content".
_MIN_LEN = 4


def _strip_diacritics(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def strip_markdown(s: str) -> str:
    """Remove markdown scaffolding, hashtags and common LLM prefixes/quotes."""
    if not s:
        return ""
    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"`+", "", s)
    s = re.sub(r"#\w+", " ", s, flags=re.UNICODE)
    s = re.sub(r"[*_#]+", "", s)
    s = re.sub(r"^\s*(?:topic|tema|title|t[ií]tulo)\s*:\s*", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip(" \t\"'“”‘’«»").strip()
    return s


def normalize(s: str) -> str:
    """Lowercase, strip diacritics & punctuation, drop stopwords."""
    s = _strip_diacritics((s or "").lower())
    s = re.sub(r"[^\w\s]", " ", s)
    tokens = [t for t in s.split() if t and t not in _STOP and len(t) > 1]
    return " ".join(tokens)


def _content_tokens(norm_text: str) -> set[str]:
    """Distinctive content tokens: long-enough words that aren't generic."""
    out = set()
    for t in norm_text.split():
        if t in _GENERIC or len(t) < _MIN_LEN:
            continue
        out.add(t)
    return out


def distinctive_anchors(text: str) -> set[str]:
    """Proper nouns / unique identifiers that pin a topic to ONE subject.

    A token qualifies as an anchor when it is non-generic and looks like a
    proper noun: capitalized in the original text, ALL-CAPS (NASA, TRAPPIST),
    or carrying a digit (TRAPPIST-1, 55 Cancri). Hyphen compounds are split so
    "TRAPPIST-1" yields the anchor "trappist".
    """
    cleaned = strip_markdown(text)
    if not cleaned:
        return set()
    words = re.findall(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*|\w*\d\w*", cleaned, flags=re.UNICODE)
    anchors: set[str] = set()
    for w in words:
        has_digit = any(ch.isdigit() for ch in w)
        is_upper = w.isupper() and len(w) >= 2
        is_cap = bool(w[:1].isupper())
        if not (has_digit or is_upper or is_cap):
            continue
        for part in re.split(r"[-’']", w):
            core = _strip_diacritics(part.lower())
            core = re.sub(r"[^\w]", "", core)
            if not core or core in _STOP or core in _GENERIC:
                continue
            part_digit = any(ch.isdigit() for ch in core)
            if len(core) >= _MIN_LEN or (part_digit and len(core) >= 2):
                anchors.add(core)
    return anchors


def find_duplicate(candidate: str, past_topics: Iterable[str]) -> str:
    """Return the first past topic the candidate duplicates, or "" if unique.

    Layers, strictest first: distinctive-anchor overlap (same proper noun),
    two-or-more shared distinctive content words, exact normalized match,
    high token overlap, and sequence similarity.
    """
    cand_clean = strip_markdown(candidate)
    cn = normalize(cand_clean)
    if not cn:
        return ""

    cand_tokens = set(cn.split())
    cand_content = _content_tokens(cn)
    cand_anchors = distinctive_anchors(candidate)

    for past in past_topics:
        if not past:
            continue
        pn = normalize(past)
        if not pn:
            continue

        # 1. Exact normalized match.
        if cn == pn:
            return past

        # 2. Shared proper-noun anchor → same subject, regardless of phrasing.
        if cand_anchors:
            past_anchors = distinctive_anchors(past)
            if cand_anchors & past_anchors:
                return past

        past_content = _content_tokens(pn)

        # 3. Two or more shared distinctive content words → same subject.
        if len(cand_content & past_content) >= 2:
            return past

        # 4. High token overlap (same subject heavily rephrased).
        past_tokens = set(pn.split())
        if cand_tokens and past_tokens:
            overlap = len(cand_tokens & past_tokens) / max(len(cand_tokens), len(past_tokens))
            if overlap >= 0.65:
                return past

        # 5. Near-identical phrasing.
        if SequenceMatcher(None, cn, pn).ratio() >= 0.72:
            return past

    return ""


def is_duplicate(candidate: str, past_topics: Iterable[str]) -> bool:
    return bool(find_duplicate(candidate, past_topics))
