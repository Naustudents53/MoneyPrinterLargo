import re
import unicodedata
from dataclasses import dataclass
from typing import Callable

from .NarrationVoice import NarrationVoice


@dataclass(frozen=True)
class RetentionScore:
    hook_strength: int
    mystery: int
    visual_potential: int
    pacing: int
    ending_strength: int

    @property
    def average(self) -> float:
        return (
            self.hook_strength
            + self.mystery
            + self.visual_potential
            + self.pacing
            + self.ending_strength
        ) / 5


class CosmicRetentionEngine:
    """Narrative retention helpers for astronomy / universe videos."""

    COSMIC_KEYWORDS = {
        "universo", "universe", "cosmos", "cosmico", "cosmica", "cosmic",
        "espacio", "space", "astronomia", "astronomy", "astrofisica",
        "astrophysics", "galaxia", "galaxy", "galaxias", "galaxies",
        "agujero negro", "black hole", "estrella", "star", "planeta",
        "planet", "big bang", "materia oscura", "dark matter",
        "energia oscura", "dark energy", "multiverso", "multiverse",
        "nebulosa", "nebula", "supernova", "quasar", "pulsar",
        "magnetar", "gravedad", "gravity", "relatividad", "relativity",
        "telescopio", "telescope", "jwst", "webb", "hubble", "voyager",
        "cassini", "saturno", "saturn", "marte", "mars", "jupiter",
        "encelado", "enceladus", "exoplaneta", "exoplanet",
    }

    MYSTERY_TERMS = {
        "misterio", "mystery", "extrano", "strange", "imposible",
        "impossible", "no encaja", "no deberia", "nadie", "silencio",
        "senal", "signal", "frontera", "borde", "oculto", "inquietante",
    }

    VISUAL_TERMS = {
        "luz", "sombra", "horizonte", "galaxia", "estrella", "nebulosa",
        "disco", "orbita", "telescopio", "sonda", "planeta", "anillo",
        "black hole", "accretion", "hubble", "jwst", "voyager",
    }

    @classmethod
    def normalize(cls, text: str) -> str:
        text = unicodedata.normalize("NFKD", (text or "").lower())
        text = "".join(c for c in text if not unicodedata.combining(c))
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def is_cosmic_context(cls, topic: str, niche: str = "") -> bool:
        haystack = cls.normalize(f"{topic} {niche}")
        return any(keyword in haystack for keyword in cls.COSMIC_KEYWORDS)

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
        if not cls.is_cosmic_context(topic, niche):
            return script

        target_clause = (
            f"- Aim for {target_words} words total, plus or minus ten percent.\n"
            if target_words else ""
        )
        prompt = f"""Rewrite this short-video narration script for maximum audience retention.

TOPIC: {topic}
LANGUAGE: {language}
CURRENT SCRIPT:
\"\"\"
{script}
\"\"\"

Use the COSMIC RETENTION structure:
1. Sentence one: a disturbing cosmic question, impossible claim, or reality-bending fact.
2. Sentences two and three: explain the idea simply, without sounding like a class.
3. Middle sentences: escalate with scale, consequence, and a scientific twist.
4. Last sentence: end with a memorable thought that leaves awe or unease.

Rules:
- Keep EXACTLY {sentence_length} sentences.
{target_clause}- Every sentence must be short, direct, and spoken aloud naturally.
- Add at least two mini-revelations. Each one should make the viewer feel the idea got bigger.
- Use mystery, scale, and scientific consequence. Avoid generic hype.
- No markdown, no title, no bullets, no stage directions.
- No "welcome", no "today we will talk about", no meta commentary.
- Write every word in {language}.
{NarrationVoice.rewrite_guardrail(language)}
- Return ONLY the rewritten narration script."""
        try:
            improved = (generate_response(prompt) or "").strip()
        except Exception:
            return script

        improved = re.sub(r"\*", "", improved).strip()
        if not improved:
            return script

        if cls._sentence_count(improved) != sentence_length:
            return script

        original_score = cls.score_script(script)
        improved_score = cls.score_script(improved)
        if improved_score.average + 0.25 < original_score.average:
            return script

        return improved

    @classmethod
    def score_script(cls, script: str) -> RetentionScore:
        text = cls.normalize(script)
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", script.strip()) if s.strip()]
        first = cls.normalize(sentences[0] if sentences else "")
        last = cls.normalize(sentences[-1] if sentences else "")

        hook_strength = 4
        if "?" in (sentences[0] if sentences else ""):
            hook_strength += 2
        if any(term in first for term in cls.MYSTERY_TERMS):
            hook_strength += 2
        if len(first.split()) <= 22:
            hook_strength += 1

        mystery = 3 + min(5, sum(1 for term in cls.MYSTERY_TERMS if term in text))
        visual_potential = 3 + min(5, sum(1 for term in cls.VISUAL_TERMS if term in text))
        avg_sentence_len = (sum(len(s.split()) for s in sentences) / len(sentences)) if sentences else 99
        pacing = 9 if avg_sentence_len <= 18 else 7 if avg_sentence_len <= 24 else 5
        ending_strength = 4
        if any(term in last for term in ("tal vez", "quizas", "nunca", "futuro", "realidad", "destino")):
            ending_strength += 3
        if len(last.split()) <= 24:
            ending_strength += 1

        return RetentionScore(
            hook_strength=min(10, hook_strength),
            mystery=min(10, mystery),
            visual_potential=min(10, visual_potential),
            pacing=min(10, pacing),
            ending_strength=min(10, ending_strength),
        )

    @classmethod
    def short_generation_directive(cls, topic: str, niche: str, language: str) -> str:
        if not cls.is_cosmic_context(topic, niche):
            return ""
        return f"""

COSMIC RETENTION PROFILE - mandatory because this is universe / astronomy content:
- Do not sound like a school explanation. Sound like a revelation about reality.
- Use the emotional engine: mystery -> simple explanation -> scale shock -> scientific twist -> memorable ending.
- Prefer lines like "Lo inquietante es..." or "Pero aqui la fisica cambia..." over generic facts.
- Every two or three sentences must create a new reason to keep watching.
- The final sentence should feel like awe, unease, or a changed perception of the universe.
- Write in {language}."""

    @classmethod
    def long_generation_directive(cls, topic: str, niche: str, language: str) -> str:
        if not cls.is_cosmic_context(topic, niche):
            return ""
        return f"""

COSMIC RETENTION PROFILE - mandatory:
- This video is about the universe, so retention comes from awe, mystery, scale, and consequence.
- Avoid textbook flow. Every section must feel like a discovery unfolding.
- Open loops with real scientific tension: an anomaly, boundary, impossible scale, hidden force, or unanswered signal.
- Pay off loops with clear explanations, but leave emotional awe after each answer.
- Use concrete cosmic imagery: light bending, horizons, probes, telescopes, star fields, gravity, dust, radiation, silence.
- Escalate scale regularly: Earth -> Sun -> Solar System -> galaxy -> observable universe, when relevant.
- Keep all claims scientific and grounded; do not invent fictional sci-fi events.
- Write in {language}."""

    @classmethod
    def long_section_themes(cls, base_themes: list[str], topic: str, niche: str) -> list[str]:
        if not cls.is_cosmic_context(topic, niche):
            return list(base_themes)

        return [
            "Pregunta imposible: abre con una imagen cosmica inquietante y una pregunta que parezca romper la intuicion. No expliques demasiado; deja una grieta mental abierta.",
            "Escala emocional: compara el objeto o fenomeno con la Tierra, el Sol, el Sistema Solar o la galaxia para que el espectador sienta tamano, distancia o tiempo.",
            "Primera revelacion parcial con like-break natural al inicio: entrega una respuesta pequena, pero abre una pregunta mas profunda sobre lo que significa fisicamente.",
            "Mecanismo invisible: explica la fisica esencial con lenguaje simple y visual, como si el espectador pudiera ver gravedad, luz, radiacion o expansion actuando.",
            "Giro cientifico: destruye una intuicion popular sobre el tema y reemplazala con una idea mas extrana, pero real.",
            "La frontera: presenta el limite fisico o conceptual del tema: horizonte, borde observable, energia, tiempo, silencio, distancia o medicion.",
            "El elemento humano: conecta la inmensidad con una sonda, telescopio, cientifico, observatorio o decision humana concreta.",
            "Consecuencia existencial: explica por que ese fenomeno cambia nuestra idea del futuro, la vida, el tiempo o el lugar de la Tierra.",
            "Climax: paga el misterio principal con la revelacion mas fuerte, clara y visual del video. Debe sentirse inevitable y enorme.",
            "Eco final: no abras misterios nuevos; convierte lo aprendido en una imagen memorable sobre nuestra posicion en el universo.",
        ]

    @classmethod
    def visual_retention_directive(cls, topic: str, niche: str) -> str:
        if not cls.is_cosmic_context(topic, niche):
            return ""
        return """

VISUAL RETENTION ARC FOR COSMIC CONTENT:
- Prompt 1 must create instant awe or unease, not generic space wallpaper.
- Each later prompt should visually escalate: closer detail, larger scale, hidden mechanism, observing instrument, consequence.
- Prefer physically specific features: photon ring, accretion disk, tidal plume, ring shadow, mirror segment, plasma jet, gravitational lensing, dust lane.
- Avoid repeated star fields. If stars appear, they must support a specific cosmic event or object."""

    @staticmethod
    def _sentence_count(text: str) -> int:
        return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()])
