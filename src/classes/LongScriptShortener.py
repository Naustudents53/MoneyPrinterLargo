from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .duration_presets import resolve_short_duration


TextGenerator = Callable[..., str]


SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
HEADER_RE = re.compile(r"^\s*#\s*([^:]+):\s*(.+?)\s*$")
SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$", re.MULTILINE)
CTA_RE = re.compile(
    r"\b("
    r"suscr[ií]bete|subscribe|campanita|like|me gusta|comenta|comment|"
    r"share|compart[ei]|gracias por llegar|hasta la pr[oó]xima"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LongScriptDocument:
    topic: str
    metadata: dict[str, str]
    sections: dict[str, str]
    body: str

    def source_for_short(self, max_chars: int = 16000) -> str:
        """Return the source narration without creator outro/CTA material."""
        usable_sections = []
        for name, text in self.sections.items():
            normalized = name.strip().upper()
            if normalized in {"OUTRO", "CTA"}:
                continue
            if CTA_RE.search(text) and normalized in {"CLOSING", "FINAL"}:
                continue
            usable_sections.append(text.strip())
        source = "\n\n".join(part for part in usable_sections if part)
        if not source:
            source = self.body
        return _remove_structure_labels(source).strip()[:max_chars]


@dataclass(frozen=True)
class ShortenOptions:
    duration_seconds: int = 60
    language: str = "espanol"
    topic: str = ""
    temperature: float = 0.72
    allow_fallback: bool = True


@dataclass(frozen=True)
class ShortScriptResult:
    topic: str
    script: str
    duration_seconds: int
    sentence_target: int
    word_target: int
    image_target: int
    used_llm: bool
    prompt: str = ""

    @property
    def word_count(self) -> int:
        return len(self.script.split())

    @property
    def sentence_count(self) -> int:
        return sentence_count(self.script)


@dataclass(frozen=True)
class WrittenShortScript:
    output_path: Path
    preview_path: Path | None = None
    preview_id: str = ""


def parse_long_script_text(text: str) -> LongScriptDocument:
    metadata: dict[str, str] = {}
    body_lines: list[str] = []
    current_section = ""
    section_lines: list[str] = []
    sections: dict[str, str] = {}

    def flush_section() -> None:
        nonlocal section_lines, current_section
        if not current_section:
            return
        sections[current_section] = "\n".join(section_lines).strip()
        section_lines = []

    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip()
        header = HEADER_RE.match(line)
        if header and not body_lines and not current_section:
            metadata[header.group(1).strip().lower()] = header.group(2).strip()
            continue
        if line.startswith("#"):
            continue

        section = SECTION_RE.match(line)
        if section:
            flush_section()
            current_section = section.group(1).strip()
            body_lines.append(line)
            continue

        body_lines.append(line)
        if current_section:
            section_lines.append(line)

    flush_section()
    body = "\n".join(body_lines).strip()
    topic = metadata.get("topic", "").strip()
    if not topic:
        topic = _infer_topic_from_body(body)
    return LongScriptDocument(
        topic=topic,
        metadata=metadata,
        sections=sections,
        body=body,
    )


def build_shortening_prompt(
    document: LongScriptDocument,
    options: ShortenOptions,
) -> str:
    duration, sentence_target, word_target, _image_target = resolve_short_duration(
        options.duration_seconds
    )
    topic = (options.topic or document.topic or "the source video").strip()
    source = document.source_for_short()
    return f"""Turn this long-form YouTube narration into a high-retention Short.

TOPIC: {topic}
TARGET LANGUAGE: {options.language}
TARGET DURATION: {duration} seconds
TARGET LENGTH: EXACTLY {sentence_target} sentences, about {word_target} spoken words.

Rules:
- Preserve the strongest factual arc from the long script: hook, setup, escalation, reveal, payoff.
- Open with a scroll-stopping first sentence that names or clearly implies the topic.
- Keep the narration self-contained; do not mention "the long video", "the script", or source sections.
- Do not include YouTube outro, greetings, subscribe requests, likes, comments, channel talk, or stage directions.
- Use short spoken sentences with concrete images and clean cause-and-effect.
- No markdown, no title, no bullets, no labels. Return only the final narration.

SOURCE LONG SCRIPT:
\"\"\"
{source}
\"\"\""""


def shorten_long_script(
    text: str,
    options: ShortenOptions | None = None,
    text_generator: TextGenerator | None = None,
) -> ShortScriptResult:
    options = options or ShortenOptions()
    document = parse_long_script_text(text)
    duration, sentence_target, word_target, image_target = resolve_short_duration(
        options.duration_seconds
    )
    topic = (options.topic or document.topic or "Short resumido").strip()
    prompt = build_shortening_prompt(document, options)

    try:
        generator = text_generator or _default_text_generator
        raw = generator(prompt, temperature=options.temperature)
        script = clean_short_script(raw)
        if script:
            return ShortScriptResult(
                topic=topic,
                script=script,
                duration_seconds=duration,
                sentence_target=sentence_target,
                word_target=word_target,
                image_target=image_target,
                used_llm=True,
                prompt=prompt,
            )
    except Exception:
        if not options.allow_fallback:
            raise

    script = fallback_short_script(document, sentence_target=sentence_target)
    return ShortScriptResult(
        topic=topic,
        script=script,
        duration_seconds=duration,
        sentence_target=sentence_target,
        word_target=word_target,
        image_target=image_target,
        used_llm=False,
        prompt=prompt,
    )


def clean_short_script(raw: str) -> str:
    text = _strip_code_fences(raw)
    text = _strip_wrapping_quotes(text)
    text = _remove_structure_labels(text)
    lines = []
    for line in text.splitlines():
        clean = re.sub(r"^\s*[-*•\d.)]+\s*", "", line).strip()
        if clean:
            lines.append(clean)
    return _collapse_spaces(" ".join(lines))


def fallback_short_script(
    document: LongScriptDocument,
    *,
    sentence_target: int,
) -> str:
    source_sentences = [
        sentence
        for sentence in _split_sentences(document.source_for_short())
        if not CTA_RE.search(sentence)
    ]
    selected = _evenly_sample(source_sentences, sentence_target)
    fillers = [
        f"{document.topic} empieza como una pista pequena, pero abre una consecuencia enorme.",
        "La clave esta en mirar el detalle que cambia toda la escala del relato.",
        "Ese giro convierte los datos en una imagen facil de recordar.",
        "Al final, la historia deja una pregunta que sigue pesando despues del cierre.",
    ]
    filler_idx = 0
    while len(selected) < sentence_target:
        selected.append(fillers[filler_idx % len(fillers)])
        filler_idx += 1
    return clean_short_script(" ".join(selected[:sentence_target]))


def sentence_count(text: str) -> int:
    return len(_split_sentences(text))


def write_short_script_files(
    result: ShortScriptResult,
    *,
    output_path: str | Path | None = None,
    preview: bool = False,
    root_dir: str | Path | None = None,
) -> WrittenShortScript:
    root = Path(root_dir) if root_dir else Path(__file__).resolve().parents[2]
    tmp_dir = root / ".mp" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        slug = _slugify(result.topic)
        output = tmp_dir / f"short_{slug}_{result.duration_seconds}s.txt"
    else:
        output = Path(output_path)
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(_format_output(result), encoding="utf-8")

    preview_path = None
    preview_id = ""
    if preview:
        preview_id = uuid4().hex[:12]
        preview_path = tmp_dir / f".preview-{preview_id}.txt"
        preview_path.write_text(
            f"{result.topic}\n\n{result.script.strip()}\n",
            encoding="utf-8",
        )

    return WrittenShortScript(
        output_path=output,
        preview_path=preview_path,
        preview_id=preview_id,
    )


def _default_text_generator(prompt: str, temperature: float = 0.7) -> str:
    from llm_provider import generate_text

    return generate_text(prompt, temperature=temperature)


def _format_output(result: ShortScriptResult) -> str:
    return (
        f"# Topic: {result.topic}\n"
        f"# Source: long script summary\n"
        f"# Target duration: {result.duration_seconds}s\n"
        f"# Target sentences: {result.sentence_target}\n"
        f"# Target words: {result.word_target}\n"
        f"# Actual words: {result.word_count}\n"
        f"# Used LLM: {'yes' if result.used_llm else 'no'}\n"
        "# ============================================================\n\n"
        f"{result.script.strip()}\n"
    )


def _split_sentences(text: str) -> list[str]:
    sentences = []
    for match in SENTENCE_RE.finditer(text or ""):
        sentence = _collapse_spaces(match.group(0))
        if sentence:
            sentences.append(sentence)
    return sentences


def _evenly_sample(items: list[str], count: int) -> list[str]:
    if count <= 0 or not items:
        return []
    if len(items) <= count:
        return list(items)
    if count == 1:
        return [items[0]]
    step = (len(items) - 1) / (count - 1)
    return [items[round(idx * step)] for idx in range(count)]


def _strip_code_fences(value: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _strip_wrapping_quotes(text: str) -> str:
    return re.sub(r'^[\s"\'`]+|[\s"\'`]+$', "", text or "").strip()


def _remove_structure_labels(text: str) -> str:
    cleaned = SECTION_RE.sub("", text or "")
    cleaned = re.sub(r"^\s*\[[^\]]+\]\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(
        r"\b(?:intro|section|closing|outro|final)\s*\d*\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


def _infer_topic_from_body(body: str) -> str:
    for line in (body or "").splitlines():
        clean = line.strip()
        if clean and not clean.startswith("["):
            return clean[:120]
    return "Short resumido"


def _collapse_spaces(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return text.strip()


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text[:70] or "short-resumido"
