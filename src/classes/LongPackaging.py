"""CTR packaging for LONG videos: title lab + description chapters.

Long-form titles were generated with a single LLM call and zero scoring,
while Shorts hooks get 8 scored candidates (RetentionLab.select_best_hook).
This module closes that gap for the two packaging elements that drive CTR
and session time on long videos:

  - Title lab : ask for N candidate titles in ONE call, score them with
    deterministic heuristics (length band, topic anchor, curiosity terms,
    caps discipline, banned cliches), pick the best.
  - Chapters  : the long script keeps its [INTRO]/[SECTION n: title]
    markers until TTS cleaning, and the audio duration is known after
    synthesis. Mapping word-count fractions onto the duration yields
    chapter timestamps accurate to a few seconds — enough for YouTube
    chapters, which need >=3 entries starting at 0:00, >=10s apart.

Stdlib only; the LLM call is injected so everything stays testable.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable

TITLE_SCORE_THRESHOLD = 7.0
_IDEAL_LEN = (35, 65)
_MAX_LEN = 70
_MIN_CHAPTER_GAP_SECONDS = 10
_MIN_CHAPTERS = 3

_SECTION_RE = re.compile(
    r"\[(INTRO|CLOSING|OUTRO|(?:SECTION|SECCION|SECCIÓN)\s*\d+[^\]]*)\]",
    re.IGNORECASE,
)

_CURIOSITY_TERMS = (
    "nadie", "nunca", "jamas", "imposible", "prohibido", "oculto", "oculta",
    "verdad", "real", "olvidado", "olvidada", "perdido", "perdida", "ultimo",
    "ultima", "desaparec", "por que", "como", "error", "destruy", "cambio",
    "salvo", "traicion", "hidden", "forgotten", "impossible", "truth",
)

_BANNED_TITLE_TERMS = ("secreto", "secretos", "no creeras", "te impactara")

_PLACEHOLDER_TITLES = re.compile(r"^(parte\s*\d+|<.*>|titulo|t[ií]tulo)$", re.IGNORECASE)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"[\w'-]+", text or "", flags=re.UNICODE)


# --------------------------------------------------------------------------
# Title lab
# --------------------------------------------------------------------------


def score_title(title: str, topic: str = "") -> dict[str, Any]:
    """Deterministic CTR heuristics for a long-video title."""
    clean = re.sub(r"\s+", " ", (title or "")).strip().strip("\"'")
    issues: list[str] = []
    if not clean:
        return {"title": "", "score": 0.0, "issues": ["empty title"]}

    score = 5.0
    norm = _norm(clean)
    length = len(clean)

    if _IDEAL_LEN[0] <= length <= _IDEAL_LEN[1]:
        score += 1.5
    elif length > _MAX_LEN:
        score -= 2.0
        issues.append(f"title longer than {_MAX_LEN} chars (gets cut in search/suggested)")
    elif length < 20:
        score -= 1.0
        issues.append("title too short to carry a promise")

    if "!" in clean or "?" in clean:
        score -= 1.5
        issues.append("contains exclamation/question marks")
    if "#" in clean:
        score -= 1.0
        issues.append("contains hashtags")

    for banned in _BANNED_TITLE_TERMS:
        if banned in norm:
            score -= 2.0
            issues.append(f"uses overused term '{banned}'")
            break

    caps_words = [w for w in _words(clean) if len(w) > 3 and w.isupper()]
    if len(caps_words) == 1:
        score += 0.8
    elif len(caps_words) > 1:
        score -= 1.2
        issues.append("more than one ALL-CAPS word reads as spam")

    topic_tokens = [t for t in _words(_norm(topic)) if len(t) > 4][:6]
    if topic_tokens and any(tok in norm for tok in topic_tokens):
        score += 1.5
    elif topic_tokens:
        score -= 1.0
        issues.append("title does not name anything from the topic")

    curiosity_hits = sum(1 for term in _CURIOSITY_TERMS if term in norm)
    score += min(1.7, curiosity_hits * 0.85)
    if not curiosity_hits:
        issues.append("no curiosity/tension language")

    return {"title": clean, "score": round(max(0.0, min(10.0, score)), 1), "issues": issues}


def build_title_candidates_prompt(topic: str, language: str, candidates: int = 6) -> str:
    return f"""Genera EXACTAMENTE {candidates} títulos distintos para un video largo de YouTube sobre: {topic}.

REQUISITOS DE CADA TÍTULO:
- Máximo {_MAX_LEN} caracteres (ideal {_IDEAL_LEN[0]}-{_IDEAL_LEN[1]}).
- Puede incluir opcionalmente 1 palabra en MAYÚSCULAS para énfasis (NUNCA, JAMÁS, NADIE, VERDAD, REAL, IMPOSIBLE, PROHIBIDO, OLVIDADO, PERDIDO, OCULTO, BRUTAL, DEFINITIVO, ÚNICO, ÉPICO). PROHIBIDO usar SECRETO o SECRETOS.
- Debe nombrar algo ESPECÍFICO del tema (nombre propio, lugar, fecha, objeto) y despertar curiosidad o prometer una revelación real.
- Varía el ángulo entre candidatos: pregunta implícita, dato imposible, consecuencia, contraste, persona concreta.
- SIN signos de exclamación ni interrogación, SIN emojis, SIN comillas, SIN hashtags.
- ESCRIBE EN {language}.

FORMATO: devuelve SOLO los {candidates} títulos, uno por línea, sin numerar, sin viñetas, sin explicación."""


def select_best_title(
    topic: str,
    language: str,
    generate_response: Callable[[str], str],
    candidates: int = 6,
) -> tuple[str, dict[str, Any]]:
    """One LLM call for N candidates, deterministic scoring, best wins.

    Returns ("", report) when nothing usable came back so the caller can fall
    back to the legacy single-call path.
    """
    candidates = max(3, min(int(candidates or 6), 10))
    try:
        raw = generate_response(build_title_candidates_prompt(topic, language, candidates)) or ""
    except Exception:
        raw = ""

    scored: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        clean = re.sub(r"^[\s\-\*\d\.\)\:]+", "", line).strip().strip("\"'")
        if not clean or len(_words(clean)) < 3:
            continue
        key = _norm(clean)
        if key in seen:
            continue
        seen.add(key)
        scored.append(score_title(clean, topic))

    scored.sort(key=lambda item: item["score"], reverse=True)
    best = scored[0] if scored else {"title": "", "score": 0.0, "issues": ["no candidates parsed"]}
    report = {
        "best_title": best["title"],
        "best_score": best["score"],
        "accepted": best["score"] >= TITLE_SCORE_THRESHOLD,
        "candidate_count": len(scored),
        "candidates": scored[:candidates],
        "threshold": TITLE_SCORE_THRESHOLD,
    }
    return best["title"], report


# --------------------------------------------------------------------------
# Chapters
# --------------------------------------------------------------------------


def extract_sections(script: str) -> list[dict[str, Any]]:
    """Split a marker-structured long script into (title, word_count) sections."""
    text = (script or "").strip()
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return []
    sections: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        marker = match.group(1).strip()
        upper = marker.upper()
        if upper.startswith(("SECTION", "SECCION")):
            kind = "section"
            title = marker.split(":", 1)[1].strip() if ":" in marker else ""
        else:
            kind = upper  # INTRO / CLOSING / OUTRO
            title = ""
        sections.append({
            "kind": kind,
            "title": title,
            "words": len(_words(body)),
        })
    return sections


def _chapter_title(section: dict[str, Any], index: int, language: str) -> str:
    title = (section.get("title") or "").strip().strip(".")
    if title and not _PLACEHOLDER_TITLES.match(title):
        return title[:60]
    english = "en" in _norm(language) and "espan" not in _norm(language)
    return f"Chapter {index}" if english else f"Capítulo {index}"


def format_timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def build_chapters(
    script: str,
    audio_duration_seconds: float,
    language: str = "",
) -> list[dict[str, Any]]:
    """Chapter list mapped by word-count fraction onto the real audio length.

    INTRO becomes the mandatory 0:00 chapter; CLOSING+OUTRO collapse into a
    final chapter. Chapters closer than YouTube's 10-second minimum to the
    previous one are dropped. Returns [] when the script has no markers or
    the result would not satisfy YouTube's >=3 chapter rule.
    """
    try:
        duration = float(audio_duration_seconds)
    except (TypeError, ValueError):
        return []
    sections = extract_sections(script)
    if not sections or duration <= 0:
        return []

    total_words = sum(s["words"] for s in sections)
    if total_words <= 0:
        return []

    english = "en" in _norm(language) and "espan" not in _norm(language)
    chapters: list[dict[str, Any]] = []
    cumulative = 0
    section_index = 0
    closing_done = False
    for section in sections:
        start = duration * (cumulative / total_words)
        cumulative += section["words"]
        kind = section["kind"]
        if kind == "INTRO":
            title = "Introduction" if english else "Introducción"
            start = 0.0
        elif kind == "section":
            section_index += 1
            title = _chapter_title(section, section_index, language)
        elif kind in ("CLOSING", "OUTRO"):
            if closing_done:
                continue  # merge OUTRO into the CLOSING chapter
            closing_done = True
            title = "Conclusion" if english else "Conclusión"
        else:
            continue
        if chapters and start - chapters[-1]["seconds"] < _MIN_CHAPTER_GAP_SECONDS:
            continue
        chapters.append({"seconds": round(start, 1), "title": title})

    if len(chapters) < _MIN_CHAPTERS or chapters[0]["seconds"] != 0.0:
        return []
    return chapters


def chapters_block(chapters: list[dict[str, Any]], language: str = "") -> str:
    """Render chapters as the description block YouTube parses. "" if empty."""
    if not chapters:
        return ""
    english = "en" in _norm(language) and "espan" not in _norm(language)
    header = "Chapters:" if english else "Capítulos:"
    lines = [f"{format_timestamp(c['seconds'])} {c['title']}" for c in chapters]
    return f"\n\n{header}\n" + "\n".join(lines)
