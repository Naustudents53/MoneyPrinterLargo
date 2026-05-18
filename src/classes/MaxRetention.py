"""Maximum-retention helpers for Shorts generation.

This module is intentionally separate from the normal YouTube pipeline so the
webapp can opt into a more aggressive creative mode without changing the
default behavior.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable

from .NarrationVoice import NarrationVoice


STANDARD_RETENTION_MODE = "standard"
MAX_RETENTION_MODE = "maxima_retencion"

_MODE_ALIASES = {
    "": STANDARD_RETENTION_MODE,
    "normal": STANDARD_RETENTION_MODE,
    "standard": STANDARD_RETENTION_MODE,
    "default": STANDARD_RETENTION_MODE,
    "max": MAX_RETENTION_MODE,
    "maxima": MAX_RETENTION_MODE,
    "maxima_retencion": MAX_RETENTION_MODE,
    "maxima-retencion": MAX_RETENTION_MODE,
    "maximum_retention": MAX_RETENTION_MODE,
}


@dataclass(frozen=True)
class CaptionConfig:
    font_size: int
    max_words_per_group: int
    position_y: int


@dataclass(frozen=True)
class MaxRetentionPreset:
    sentences: int
    words: int
    images: int


class MaxRetentionEngine:
    """Creative rules for the "MAXIMA RETENCION" Shorts mode."""

    # Slightly shorter scripts than the normal preset, but many more visual
    # beats. At Spanish TTS speed this tends to land below the selected ceiling
    # while keeping the Short dense enough for repeat viewing.
    DURATION_PRESETS: dict[int, MaxRetentionPreset] = {
        60: MaxRetentionPreset(sentences=11, words=140, images=12),
        120: MaxRetentionPreset(sentences=20, words=275, images=22),
        180: MaxRetentionPreset(sentences=28, words=405, images=30),
    }

    MUSIC_VOLUME = 0.09
    VOICE_RATE = "+6%"
    VOICE_DRAMA_PITCH = "-4Hz"
    CAPTION_CONFIG = CaptionConfig(
        font_size=86,
        max_words_per_group=3,
        position_y=1245,
    )

    ABSTRACT_TOPIC_PATTERNS = (
        "materia oscura",
        "energia oscura",
        "expansion del universo",
        "universo observable",
        "principio holografico",
        "calendario cosmico",
        "historia del universo",
        "fin del universo",
        "big bang",
    )

    GENERIC_TOPIC_TERMS = (
        "curiosidades",
        "datos curiosos",
        "misterios del universo",
        "secretos del universo",
        "cosas que no sabias",
        "lo que nadie sabe",
    )

    VISUAL_ANCHORS = (
        "gliese", "voyager", "cassini", "jwst", "webb", "hubble", "kepler",
        "m87", "ton 618", "sagittarius", "tabby", "kic", "hoag", "titan",
        "encelado", "europa", "io", "jupiter", "saturno", "marte", "pluton",
        "andromeda", "laniakea", "shapley", "bullet cluster", "el gordo",
        "oort", "wow", "ligo", "pulsar", "magnetar", "quasar", "blazar",
        "nebulosa", "galaxia", "planeta", "estrella", "agujero negro",
        "sonda", "telescopio", "cometa", "supernova", "exoplaneta",
    )

    BANNED_OPENERS = (
        "sabias que",
        "en este video",
        "hoy vamos",
        "hoy descubriras",
        "acompaname",
        "descubre",
        "bienvenido",
    )

    REVELATION_TERMS = (
        "pero", "entonces", "lo inquietante", "lo extrano", "la clave",
        "el giro", "nadie", "no deberia", "cambia", "revela", "oculta",
        "por eso", "sin embargo", "ahi esta",
    )

    VISUAL_TERMS = (
        "luz", "sombra", "anillo", "horizonte", "nube", "plasma", "vidrio",
        "hielo", "cometa", "disco", "chorro", "senal", "telescopio",
        "sonda", "galaxia", "estrella", "planeta", "orbita",
    )

    @classmethod
    def duration_preset(cls, seconds: int | None) -> MaxRetentionPreset | None:
        if seconds is None:
            return None
        return cls.DURATION_PRESETS.get(int(seconds))

    @classmethod
    def topic_generation_directive(cls, niche: str, language: str) -> str:
        return f"""

MAXIMA RETENCION TOPIC RULES - mandatory:
- Pick a topic that can be understood in one mobile glance: one object, one mission, one anomaly, one danger, or one visual event.
- Prefer a named cosmic object, mission, telescope, signal, planet, star, galaxy, comet, or exact phenomenon.
- Avoid broad school topics unless tied to a concrete visual anchor. Bad: "materia oscura". Better: "Bullet Cluster: la colision que mostro materia oscura separada de gas".
- The topic must imply a first-second visual hook: something approaching, breaking, bending, burning, vanishing, exploding, hiding, or contradicting intuition.
- Keep it specific enough for a 45-75 second Short in {language}.
"""

    @classmethod
    def topic_rejection_reason(cls, topic: str, niche: str = "") -> str:
        text = cls.normalize(topic)
        if not text:
            return "empty topic"
        if any(term in text for term in cls.GENERIC_TOPIC_TERMS):
            return "generic topic"

        has_anchor = any(anchor in text for anchor in cls.VISUAL_ANCHORS)
        has_number = bool(re.search(r"\d", topic or ""))
        has_capitalized_anchor = len(re.findall(r"\b[A-Z][A-Za-z0-9*+-]{2,}\b", topic or "")) >= 1
        is_abstract = any(pattern in text for pattern in cls.ABSTRACT_TOPIC_PATTERNS)
        if is_abstract and not (has_anchor or has_number or has_capitalized_anchor):
            return "abstract topic without a concrete visual anchor"
        return ""

    @classmethod
    def script_generation_directive(
        cls,
        topic: str,
        niche: str,
        language: str,
        sentence_length: int,
    ) -> str:
        midpoint = max(4, sentence_length // 2)
        return f"""

MAXIMA RETENCION MODE - mandatory:
- Sentence one is the swipe-stopper. It must be 8 to 12 words, direct, visual, and unsettling. No context first.
- Never open with "Sabias que", "En este video", "Hoy vamos", "Descubre", "Acompaname", or any welcome.
- The first three seconds must make one concrete promise about the topic: danger, contradiction, impossible scale, hidden force, or strange consequence.
- Every 2 sentences must add a new reason to keep watching: a twist, a scale jump, a consequence, or a more precise image.
- Structure the Short like this: sentence 1 shock, sentences 2-3 simple setup, sentences 4-{midpoint} escalation, sentences {midpoint + 1}-{max(midpoint + 2, sentence_length - 2)} explanation, final sentences payoff and echo.
- Prefer strong verbs over labels: se acerca, rompe, dobla, arrastra, borra, ilumina, oculta, dispara, devora.
- These structure words are private instructions only. Never say labels like "primera revelacion", "segunda revelacion", "hook", "contexto", "desarrollo", "conclusion", "parte uno", or "seccion dos" in the narration.
- Cut filler. No generic hype, no calls to action, no classroom tone, no slow introductions.
- The final sentence should be short enough to loop cleanly back into the first sentence.
- Write every word in {language}.
{NarrationVoice.short_generation_directive(language)}
"""

    @classmethod
    def optimize_short_script(
        cls,
        script: str,
        topic: str,
        niche: str,
        language: str,
        sentence_length: int,
        generate_response: Callable[[str], str],
        target_words: int | None = None,
    ) -> str:
        target_clause = (
            f"- Aim for about {target_words} spoken words total, plus or minus ten percent.\n"
            if target_words else ""
        )
        prompt = f"""Rewrite this YouTube Short narration for MAXIMA RETENCION.

Topic: {topic}
Channel niche: {niche}
Language: {language}

Current script:
\"\"\"
{script}
\"\"\"

Rules:
- Keep EXACTLY {sentence_length} sentences.
{target_clause}- Sentence one: 8 to 12 words, concrete, visual, unsettling, and tied to the topic.
- No "Sabias que", "En este video", "Hoy vamos", "Descubre", "Acompaname", welcome, or meta commentary.
- Keep one continuous story, but add a new twist or consequence every 2 sentences.
- Never announce the structure. Do not write labels like "primera revelacion", "segunda revelacion", "hook", "contexto", "desarrollo", "conclusion", "parte uno", or "seccion dos".
- Use simple spoken language, short sentences, strong verbs, and concrete cosmic images.
- Reduce textbook explanation. Increase cause -> consequence -> twist.
- End with a memorable line that loops naturally back to the first sentence.
{NarrationVoice.rewrite_guardrail(language)}
- No markdown, no title, no bullets, no stage directions.
- Return ONLY the rewritten narration."""
        try:
            improved = (generate_response(prompt) or "").strip()
        except Exception:
            return script
        improved = re.sub(r"\*", "", improved).strip()
        if not improved:
            return script
        if cls._sentence_count(improved) != sentence_length:
            return script
        if cls.score_script(improved) + 0.15 < cls.score_script(script):
            return script
        return improved

    @classmethod
    def visual_generation_directive(cls, topic: str, niche: str) -> str:
        return """

MAXIMA RETENCION VISUAL ARC:
- Prompt 1 must be the scroll-stopper image that matches sentence 1, not a generic space wallpaper.
- Each prompt must be a new beat, not a slightly different version of the previous image.
- Design for cuts every 4-6 seconds: one clear subject, one readable action, one obvious contrast.
- Use named objects and physically specific features whenever possible: photon ring, glass rain, comet cloud, gravity lens, dust lane, plasma jet, telescope mirror, probe antenna.
- Avoid slow abstract visuals, repeated star fields, generic galaxies, and empty cosmic backgrounds.
- If the narration explains an invisible force, show its visible consequence instead."""

    @classmethod
    def score_script(cls, script: str) -> float:
        sentences = cls._sentences(script)
        if not sentences:
            return 0.0
        text = cls.normalize(script)
        first = cls.normalize(sentences[0])
        last = cls.normalize(sentences[-1])
        first_words = len(first.split())
        avg_words = sum(len(s.split()) for s in sentences) / max(1, len(sentences))

        score = 0.0
        score += 2.0 if 7 <= first_words <= 13 else 0.6 if first_words <= 18 else 0.0
        score += 1.4 if not any(opener in first for opener in cls.BANNED_OPENERS) else -2.0
        score += min(2.2, 0.35 * sum(1 for term in cls.REVELATION_TERMS if term in text))
        score += min(1.8, 0.25 * sum(1 for term in cls.VISUAL_TERMS if term in text))
        score += 1.4 if avg_words <= 17 else 0.6 if avg_words <= 22 else 0.0
        score += 1.2 if len(last.split()) <= 18 else 0.4
        score += 1.0 if any(term in last for term in ("nunca", "realidad", "cielo", "silencio", "destino", "tierra")) else 0.0
        return max(0.0, min(10.0, score))

    @classmethod
    def caption_config(cls) -> CaptionConfig:
        return cls.CAPTION_CONFIG

    @staticmethod
    def normalize(text: str) -> str:
        text = unicodedata.normalize("NFKD", (text or "").lower())
        text = "".join(c for c in text if not unicodedata.combining(c))
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]

    @classmethod
    def _sentence_count(cls, text: str) -> int:
        return len(cls._sentences(text))


def normalize_retention_mode(mode: str | None) -> str:
    key = (mode or "").strip().lower().replace(" ", "_")
    return _MODE_ALIASES.get(key, STANDARD_RETENTION_MODE)


def is_known_retention_mode(mode: str | None) -> bool:
    key = (mode or "").strip().lower().replace(" ", "_")
    return key in _MODE_ALIASES


def is_max_retention(mode: str | None) -> bool:
    return normalize_retention_mode(mode) == MAX_RETENTION_MODE
