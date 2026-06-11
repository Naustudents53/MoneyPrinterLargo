"""Retention gate for LONG-form scripts.

RetentionLab covers Shorts only; long videos were generated from a strong
prompt and then published with zero post-generation retention checks. This
module closes that gap with cheap, deterministic (no-LLM) heuristics over the
structured script ([INTRO] / [SECTION n] / [CLOSING] / [OUTRO] markers), plus
one optional LLM rewrite of the weakest, highest-leverage block: the intro.

Checks map to the known long-form drop-off causes:

  - cold_open  : first sentence hooks (length, banned generic openers, tension)
  - cta_guard  : "like/suscríbete" must NOT appear in the first ~25% of the
                 script (the prompt forbids it before section 3) and the
                 subscribe ask belongs only to the outro.
  - open_loops : the intro must seed unresolved questions/anomalies.
  - cliffhangers: each section should end pulling into the next.
  - pacing     : sentence length + filler density (mid-video dead air).
  - dead_zones : long stretches with zero tension/curiosity markers.

Stdlib only so it stays trivially testable.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable

SCORE_THRESHOLD = 7.0
INTRO_SCORE_THRESHOLD = 7.0

_MARKER_RE = re.compile(r"\[(INTRO|SECTION\s*\d+[^\]]*|CLOSING|OUTRO)\]", re.IGNORECASE)

_BANNED_OPENERS = (
    "sabias que", "imagina que", "hoy vamos", "en este video", "en el video de hoy",
    "bienvenidos", "bienvenido", "hola a todos", "did you know", "welcome",
    "in this video", "today we",
)

_TENSION_TERMS = (
    "pero", "nadie", "nunca", "imposible", "secreto", "oculta", "oculto",
    "misterio", "extrano", "peligro", "prohibido", "desaparec", "no encaja",
    "sin explicacion", "hasta que", "lo que nadie", "demasiado tarde",
)

_LOOP_MARKERS = (
    "pero hay", "y aqui", "lo que", "nadie", "todavia no", "aun no",
    "mas adelante", "no encaja", "?",
)

_LIKE_TERMS = ("me gusta", "dale like", " like ", "pulgar arriba")
_SUBSCRIBE_TERMS = ("suscrib", "campanita", "subscribe", "notification bell")

_FILLER_TERMS = (
    "basicamente", "simplemente", "realmente", "literalmente", "de alguna manera",
    "en realidad", "muy importante", "cabe destacar", "es importante mencionar",
)

_DEAD_ZONE_WINDOW_WORDS = 220


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def split_blocks(script: str) -> list[dict[str, str]]:
    """Split a marker-structured script into labeled blocks.

    Falls back to paragraph blocks when no markers survived, so the scorer
    still works on free-form scripts.
    """
    text = (script or "").strip()
    if not text:
        return []
    matches = list(_MARKER_RE.finditer(text))
    if matches:
        blocks: list[dict[str, str]] = []
        for idx, match in enumerate(matches):
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                blocks.append({"label": match.group(1).upper().strip(), "text": body})
        if blocks:
            return blocks
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [{"label": f"PARA {i + 1}", "text": p} for i, p in enumerate(paragraphs)]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[\w'-]+", text or "", flags=re.UNICODE)


def score_cold_open(intro_text: str) -> dict[str, Any]:
    sentences = _sentences(intro_text)
    first = sentences[0] if sentences else ""
    normalized = normalize(first)
    issues: list[str] = []
    score = 10.0
    if not first:
        return {"score": 0.0, "issues": ["missing intro"], "first_sentence": ""}
    if any(opener in normalized for opener in _BANNED_OPENERS):
        score -= 4.0
        issues.append("intro opens with a banned generic opener")
    n_words = len(_words(first))
    if not 6 <= n_words <= 24:
        score -= 1.5
        issues.append("first sentence length is outside the punchy range (6-24 words)")
    intro_norm = normalize(intro_text)
    if not any(term in intro_norm for term in _TENSION_TERMS):
        score -= 2.0
        issues.append("intro has no tension or mystery language")
    return {"score": max(0.0, round(score, 1)), "issues": issues, "first_sentence": first}


def score_open_loops(intro_text: str) -> dict[str, Any]:
    intro_norm = normalize(intro_text)
    hits = sum(1 for marker in _LOOP_MARKERS if marker in intro_norm)
    hits += intro_text.count("?")
    issues = [] if hits >= 2 else ["intro seeds fewer than 2 open loops"]
    return {"score": min(10.0, 4.0 + hits * 2.0) if hits else 2.0, "loop_hits": hits, "issues": issues}


def score_cta_placement(script: str, intro_text: str = "") -> dict[str, Any]:
    """Early like/subscribe asks are the single most damaging retention leak."""
    words = _words(normalize(script))
    total = len(words)
    issues: list[str] = []
    score = 10.0
    intro_norm = normalize(intro_text)
    if intro_norm and any(term.strip() in intro_norm for term in _LIKE_TERMS + _SUBSCRIBE_TERMS):
        score -= 5.0
        issues.append("like/subscribe ask inside the intro")
    if total:
        early_text = " ".join(words[: max(1, total // 4)])
        full_text = " ".join(words)
        tail_text = " ".join(words[int(total * 0.85):])
        if any(term.strip() in early_text for term in _LIKE_TERMS + _SUBSCRIBE_TERMS):
            score -= 5.0
            issues.append("like/subscribe ask inside the first quarter of the script")
        for term in _SUBSCRIBE_TERMS:
            if term in full_text and term not in tail_text:
                score -= 3.0
                issues.append("subscribe ask appears before the outro")
                break
    return {"score": max(0.0, round(score, 1)), "issues": issues}


def score_cliffhangers(blocks: list[dict[str, str]]) -> dict[str, Any]:
    sections = [b for b in blocks if b["label"].startswith("SECTION") or b["label"].startswith("PARA")]
    if not sections:
        return {"score": 5.0, "issues": ["no sections found"], "weak_endings": []}
    weak: list[str] = []
    for block in sections[:-1]:  # the last section may resolve, that's fine
        sentences = _sentences(block["text"])
        last = normalize(sentences[-1]) if sentences else ""
        has_pull = last.endswith("?") or any(term in last for term in _TENSION_TERMS)
        if not has_pull:
            weak.append(block["label"])
    ratio = 1.0 - (len(weak) / max(1, len(sections) - 1))
    issues = []
    if weak:
        issues.append(f"{len(weak)} section endings do not pull into the next section")
    return {"score": round(10.0 * ratio, 1), "issues": issues, "weak_endings": weak[:6]}


def score_pacing(script: str) -> dict[str, Any]:
    sentences = _sentences(script)
    words = _words(script)
    avg = len(words) / max(1, len(sentences))
    norm = normalize(script)
    filler_hits = sum(norm.count(term) for term in _FILLER_TERMS)
    issues: list[str] = []
    score = 10.0
    if avg > 22:
        score -= 2.5
        issues.append("average sentence length above 22 words")
    allowed_filler = max(2, len(words) // 400)
    if filler_hits > allowed_filler:
        score -= min(3.0, (filler_hits - allowed_filler) * 0.5)
        issues.append(f"{filler_hits} filler phrases detected")
    return {
        "score": max(0.0, round(score, 1)),
        "issues": issues,
        "avg_sentence_words": round(avg, 1),
        "filler_hits": filler_hits,
    }


def find_dead_zones(script: str, window: int = _DEAD_ZONE_WINDOW_WORDS) -> dict[str, Any]:
    """Windows of `window` words with zero curiosity/tension markers."""
    words = _words(normalize(script))
    zones: list[int] = []
    for start in range(0, max(1, len(words) - window + 1), window):
        chunk = " ".join(words[start:start + window])
        if not any(term in chunk for term in _TENSION_TERMS) and "?" not in chunk:
            zones.append(start)
    issues = [f"{len(zones)} dead zones of ~{window} words with no tension markers"] if zones else []
    return {"score": max(0.0, round(10.0 - len(zones) * 2.0, 1)), "issues": issues, "dead_zone_starts": zones[:8]}


def score_long_script(script: str, topic: str = "", language: str = "") -> dict[str, Any]:
    """Full retention report for a long-form script. Deterministic, no LLM."""
    blocks = split_blocks(script)
    intro = next((b["text"] for b in blocks if b["label"].startswith(("INTRO", "PARA 1"))), "")

    cold_open = score_cold_open(intro)
    loops = score_open_loops(intro)
    ctas = score_cta_placement(script, intro_text=intro)
    cliffs = score_cliffhangers(blocks)
    pacing = score_pacing(script)
    dead = find_dead_zones(script)

    components = {
        "cold_open": cold_open,
        "open_loops": loops,
        "cta_guard": ctas,
        "cliffhangers": cliffs,
        "pacing": pacing,
        "dead_zones": dead,
    }
    # Cold open weighs double: most long-form drop-off happens in the first minute.
    weighted = (
        cold_open["score"] * 2 + loops["score"] + ctas["score"] * 1.5
        + cliffs["score"] + pacing["score"] + dead["score"]
    ) / 7.5
    overall = round(min(10.0, max(0.0, weighted)), 1)
    issues = [issue for comp in components.values() for issue in comp.get("issues", [])]
    return {
        "overall_score": overall,
        "accepted": overall >= SCORE_THRESHOLD,
        "intro_score": cold_open["score"],
        "components": components,
        "issues": issues,
        "topic": topic,
        "language": language,
    }


def rewrite_intro(
    script: str,
    report: dict[str, Any],
    topic: str,
    language: str,
    generate_response: Callable[[str], str],
) -> tuple[str, bool]:
    """Rewrite ONLY the intro block when it scored below threshold.

    The intro is the highest-leverage retention element and rewriting just it
    avoids the length/quality risk of regenerating 2200 words. Returns the
    (possibly updated) script and whether a rewrite was applied.
    """
    blocks = split_blocks(script)
    intro_block = next((b for b in blocks if b["label"].startswith("INTRO")), None)
    if intro_block is None:
        return script, False

    intro_issues = (report.get("components", {}).get("cold_open", {}) or {}).get("issues", [])
    loop_issues = (report.get("components", {}).get("open_loops", {}) or {}).get("issues", [])
    issue_block = "\n".join(f"- {i}" for i in intro_issues + loop_issues) or "- Make the hook sharper."

    prompt = f"""Rewrite ONLY this documentary cold open (intro). Keep roughly the same length (100-130 words, 5-6 sentences).

Topic: {topic}
Language: {language}

Problems to fix:
{issue_block}

Rules:
- First sentence: cinematic hook, 6-24 words, no "Sabias que", "Imagina que", "Hoy vamos", "En este video" or welcome language.
- Seed at least 2 unresolved questions or anomalies that the video will answer later.
- Do NOT mention likes or subscribing.
- WRITE ENTIRELY IN {language}. Return ONLY the rewritten intro text, no markers, no markdown.

Current intro:
\"\"\"
{intro_block['text']}
\"\"\""""
    try:
        candidate = (generate_response(prompt) or "").strip().strip('"')
    except Exception:
        return script, False
    if not candidate or len(_words(candidate)) < 40:
        return script, False
    new_report = score_cold_open(candidate)
    if new_report["score"] <= score_cold_open(intro_block["text"])["score"]:
        return script, False
    return script.replace(intro_block["text"], candidate, 1), True
