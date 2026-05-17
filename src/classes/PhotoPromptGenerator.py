from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

from .MaxRetention import MaxRetentionEngine, is_max_retention, normalize_retention_mode
from .Retention import CosmicRetentionEngine


PHOTO_PROMPT_ASPECT_RATIOS: dict[str, str] = {
    "9:16": "vertical short / reels",
    "16:9": "wide YouTube thumbnail or cinematic frame",
    "1:1": "square social image",
    "4:5": "portrait feed image",
    "3:2": "classic photo frame",
}


# Kept for API compatibility with the first UI version. The project-mode
# generator no longer lets this override the channel's image_style.
PHOTO_PROMPT_STYLES: dict[str, dict[str, str]] = {
    "project_channel": {
        "label": "Project channel style",
        "description": "Use the same scene-first prompts and channel image_style as the render pipeline.",
    },
}


PROJECT_NEGATIVE = (
    "low quality, low resolution, blurry, noisy, pixelated, jpeg artifacts, watermark, "
    "signature, logo, username, captions, subtitles, readable text, UI elements, collage, "
    "montage, storyboard, split screen, multiple panels, duplicate subject, bad anatomy, "
    "extra fingers, missing fingers, extra limbs, distorted face, front-facing portrait, "
    "selfie, beauty shot, identifiable celebrity likeness, plastic skin, waxy skin, AI gloss, "
    "generic stock image, off-topic subject, fictional sci-fi object unless explicitly in topic"
)


FACE_SAFE_COMPOSITION = (
    "Face-safe composition: avoid identifiable faces. If humans appear, show hands, backs, "
    "silhouettes, over-the-shoulder angles, side profiles in shadow, or faces obscured by "
    "helmets, hoods, documents, smoke, tools or foreground objects. Use posture, gesture, "
    "clothing, props and environment to convey emotion."
)


DEFAULT_BASE_STYLE = (
    "one full-bleed cinematic photograph filling the entire frame edge to edge, one continuous "
    "uninterrupted scene captured in a single real exposure, ultra-photorealistic, true-to-life "
    "documentary realism, motivated naturalistic lighting, rich filmic color grading, subtle "
    "volumetric haze, authentic textures with visible wear and micro-detail, human presence shown "
    "through realistic hands, clothing folds, posture, silhouettes, tools and environmental "
    "interaction, faces not visible or not identifiable, accurate hands with exactly five fingers, "
    "fine film grain, neutral documentary tone, no front-facing faces, no portraits, no selfies, "
    "no beauty shots, no detailed eyes, no recognizable likeness, no cartoon, no illustration, "
    "no painting, no anime, no stylization, no cel-shading, no plastic skin, no AI gloss"
)


COSMIC_BASE_STYLE = (
    "ultra-realistic astrophotography and documentary science aesthetic, James Webb, Hubble, "
    "Cassini and Voyager image-reference quality, true-to-data nebula colors and cosmic dust "
    "textures, physically faithful gas, plasma, ice, shadow and gravitational light effects, "
    "sharp star fields with natural diffraction, accurate galaxy structures, photographic realism "
    "in observatories, probes, antenna dishes, gold thermal foil and solar panels, scientifically "
    "grounded planetary surfaces and atmospheres, no fictional planets, no fantasy nebulae, "
    "no sci-fi spaceship art, no cartoon, no anime, no painterly stylization"
)


COLLAGE_TRIGGERS = re.compile(
    r"\b("
    r"collage|montage|storyboard|comic[- ]?strip|panels?|grid|split[- ]?screen|"
    r"diptych|triptych|polyptych|side[- ]?by[- ]?side|before[- ]?and[- ]?after|"
    r"sequences?|series of|set of \d+|multiple (?:images|scenes|frames)|"
    r"frames?|stills?|tiled|stacked"
    r")\b",
    re.IGNORECASE,
)


FACE_PROMPT_REWRITES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\btight close[- ]up of a single face\b", re.IGNORECASE),
     "tight close detail of hands, clothing and the story object, face outside the frame"),
    (re.compile(r"\b(?:extreme |tight )?close[- ]up of (?:a |the |his |her |their )?face\b", re.IGNORECASE),
     "close detail of hands, clothing and the story object, face outside the frame"),
    (re.compile(r"\bfront[- ]facing (?:face|portrait|person|subject)\b", re.IGNORECASE),
     "subject turned away from camera"),
    (re.compile(r"\bportrait of\b", re.IGNORECASE),
     "non-identifiable view of"),
    (re.compile(r"\bsharp detailed eyes?\b", re.IGNORECASE),
     "hands and material details"),
)


@dataclass(frozen=True)
class ChannelPromptContext:
    channel_id: str = ""
    nickname: str = ""
    niche: str = ""
    language: str = "espanol"
    image_style: str = ""
    videos: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_account(cls, account: dict[str, Any] | None, language: str = "espanol") -> "ChannelPromptContext":
        account = account or {}
        return cls(
            channel_id=str(account.get("id") or ""),
            nickname=str(account.get("nickname") or ""),
            niche=str(account.get("niche") or ""),
            language=str(account.get("language") or language or "espanol"),
            image_style=str(account.get("image_style") or ""),
            videos=list(account.get("videos") or []),
        )


@dataclass(frozen=True)
class PhotoPromptResult:
    topic: str
    generated_topic: bool
    style: str
    aspect_ratio: str
    count: int
    text: str
    filename: str
    channel_id: str = ""
    channel_nickname: str = ""
    script: str = ""
    prompts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "generated_topic": self.generated_topic,
            "style": self.style,
            "aspect_ratio": self.aspect_ratio,
            "count": self.count,
            "text": self.text,
            "filename": self.filename,
            "channel_id": self.channel_id,
            "channel_nickname": self.channel_nickname,
            "script": self.script,
            "prompts": self.prompts,
        }


class PhotoPromptGenerator:
    """Generate project-aligned image prompts without rendering images."""

    def __init__(self, text_generator: Callable[..., str] | None = None):
        self._text_generator = text_generator

    def generate(
        self,
        *,
        topic: str = "",
        count: int = 6,
        style: str = "project_channel",
        aspect_ratio: str = "9:16",
        language: str = "espanol",
        llm_provider: str = "",
        llm_model: str = "",
        channel: dict[str, Any] | None = None,
        retention_mode: str = "",
    ) -> PhotoPromptResult:
        count = max(1, min(int(count or 6), 30))
        aspect_key = aspect_ratio if aspect_ratio in PHOTO_PROMPT_ASPECT_RATIOS else "9:16"
        mode = normalize_retention_mode(retention_mode)
        channel_ctx = ChannelPromptContext.from_account(channel, language=language)
        lang = channel_ctx.language or language or "espanol"

        cleaned_topic = _clean_topic(topic)
        generated_topic = False
        if not cleaned_topic:
            generated_topic = True
            cleaned_topic = self._generate_topic(
                channel=channel_ctx,
                language=lang,
                llm_provider=llm_provider,
                llm_model=llm_model,
                retention_mode=mode,
            )

        script = self._generate_reference_script(
            topic=cleaned_topic,
            channel=channel_ctx,
            language=lang,
            count=count,
            llm_provider=llm_provider,
            llm_model=llm_model,
            retention_mode=mode,
        )
        sections = _split_sections(script, count, fallback=cleaned_topic)
        context_profile = self._generate_context_profile(
            topic=cleaned_topic,
            script=script,
            channel=channel_ctx,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
        visual_beat_block = self._visual_beat_block(
            sections=sections,
            topic=cleaned_topic,
            channel=channel_ctx,
            language=lang,
            llm_provider=llm_provider,
            llm_model=llm_model,
            retention_mode=mode,
        )
        scene_prompts = self._generate_project_scene_prompts(
            topic=cleaned_topic,
            script=script,
            sections=sections,
            channel=channel_ctx,
            context_profile=context_profile,
            visual_beat_block=visual_beat_block,
            count=count,
            llm_provider=llm_provider,
            llm_model=llm_model,
            retention_mode=mode,
        )

        text = self._format_pack(
            topic=cleaned_topic,
            generated_topic=generated_topic,
            script=script,
            scene_prompts=scene_prompts,
            channel=channel_ctx,
            context_profile=context_profile,
            aspect_ratio=aspect_key,
            retention_mode=mode,
        )

        return PhotoPromptResult(
            topic=cleaned_topic,
            generated_topic=generated_topic,
            style="project_channel",
            aspect_ratio=aspect_key,
            count=len(scene_prompts),
            text=text,
            filename=f"prompts_fotos_{_slugify(cleaned_topic)}.txt",
            channel_id=channel_ctx.channel_id,
            channel_nickname=channel_ctx.nickname,
            script=script,
            prompts=scene_prompts,
        )

    def _generate_topic(
        self,
        *,
        channel: ChannelPromptContext,
        language: str,
        llm_provider: str,
        llm_model: str,
        retention_mode: str,
    ) -> str:
        recent = _recent_topics(channel.videos, limit=35)
        recent_block = ""
        if recent:
            recent_block = (
                "\n\nALREADY COVERED BY THIS CHANNEL - avoid repeating these subjects:\n"
                + "\n".join(f"- {item}" for item in recent)
            )
        retention_block = (
            MaxRetentionEngine.topic_generation_directive(channel.niche, language)
            if is_max_retention(retention_mode)
            else ""
        )
        prompt = f"""Generate ONE specific, focused topic for a YouTube Short.

CHANNEL: {channel.nickname or "(selected channel)"}
CHANNEL NICHE: {channel.niche or "(not specified)"}
LANGUAGE: {language}
{retention_block}

Rules:
- The topic MUST clearly belong to the channel niche. Do not drift into a generic photo idea.
- The topic must be one concrete real object, mission, anomaly, event, discovery, place, person or phenomenon.
- If the niche is universe / astronomy, prefer a named object, telescope, mission, signal, planet, galaxy, star, nebula, comet or exact scientific event.
- Avoid broad topics like "misterios del universo", "materia oscura" or "curiosidades".
- Output exactly one plain sentence, no markdown, no prefix, no quotes.
- Write entirely in {language}.
{recent_block}
"""
        try:
            raw = self._call_llm(
                prompt,
                temperature=0.95,
                llm_provider=llm_provider,
                llm_model=llm_model,
            )
            topic = _clean_topic(raw)
            if topic:
                return topic[:180].strip()
        except Exception:
            pass

        if CosmicRetentionEngine.is_cosmic_context("", channel.niche):
            return "Voyager 1: la nave que sigue hablando desde el borde del sistema solar"
        return f"Un tema especifico dentro de {channel.niche or 'el canal'}"

    def _generate_reference_script(
        self,
        *,
        topic: str,
        channel: ChannelPromptContext,
        language: str,
        count: int,
        llm_provider: str,
        llm_model: str,
        retention_mode: str,
    ) -> str:
        sentence_count = max(count, 8)
        cosmic = CosmicRetentionEngine.short_generation_directive(topic, channel.niche, language)
        max_block = (
            MaxRetentionEngine.script_generation_directive(topic, channel.niche, language, sentence_count)
            if is_max_retention(retention_mode)
            else ""
        )
        prompt = f"""Write a reference narration script only to derive image prompts for this channel.

CHANNEL NICHE: {channel.niche or "(not specified)"}
TOPIC: {topic}
{cosmic}
{max_block}

Rules:
- EXACTLY {sentence_count} short sentences.
- Keep one continuous story from hook to payoff.
- Every sentence must contain a concrete visual anchor: named object, mission, place, instrument, material, physical consequence, or visible action.
- Do not list random facts. Do not introduce unrelated researchers, desks, meetings or telescopes unless the topic/script actually needs them.
- No markdown, no title, no bullets, no stage directions.
- Write entirely in {language}.
- Return only the raw narration text."""
        try:
            raw = self._call_llm(
                prompt,
                temperature=0.78,
                llm_provider=llm_provider,
                llm_model=llm_model,
            )
            script = re.sub(r"\*", "", _strip_code_fences(raw)).strip()
            if len(script) > 80:
                return script
        except Exception:
            pass
        return _fallback_script(topic, channel, sentence_count, language)

    def _generate_context_profile(
        self,
        *,
        topic: str,
        script: str,
        channel: ChannelPromptContext,
        llm_provider: str,
        llm_model: str,
    ) -> dict[str, str]:
        prompt = f"""You are a visual research assistant for the MoneyPrinter image pipeline.

CHANNEL NICHE: {channel.niche or "(not specified)"}
VIDEO TOPIC: {topic}
SCRIPT:
\"\"\"
{script[:3000]}
\"\"\"

Return ONLY a JSON object with EXACTLY these string fields:
- "setting": the specific real setting/world for this video.
- "visual_anchors": 10 to 16 concrete objects, places, materials, instruments, environments or visual evidence that belong to this exact topic and channel.
- "must_avoid": 4 to 8 off-topic or immersion-breaking visual elements.

Rules:
- Do not default to generic scientists, random observatories, desks, laptops or meetings unless the topic/script is actually about those.
- If this is astronomy, include the named object/mission/telescope/phenomenon from the topic as the strongest visual anchor.
- Output only JSON. No markdown."""
        try:
            raw = self._call_llm(
                prompt,
                temperature=0.45,
                llm_provider=llm_provider,
                llm_model=llm_model,
            )
            data = _extract_json_object(raw)
            if data:
                return {
                    "setting": str(data.get("setting") or "").strip(),
                    "visual_anchors": str(data.get("visual_anchors") or "").strip(),
                    "must_avoid": str(data.get("must_avoid") or "").strip(),
                }
        except Exception:
            pass
        return {}

    def _visual_beat_block(
        self,
        *,
        sections: list[str],
        topic: str,
        channel: ChannelPromptContext,
        language: str,
        llm_provider: str,
        llm_model: str,
        retention_mode: str,
    ) -> str:
        if not is_max_retention(retention_mode):
            return ""
        try:
            from .RetentionLab import RetentionLab

            beats, _report = RetentionLab.build_visual_beat_map(
                sections=sections,
                topic=topic,
                niche=channel.niche,
                language=language,
                generate_response=lambda prompt: self._call_llm(
                    prompt,
                    temperature=0.75,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                ),
            )
            return RetentionLab.visual_beat_block(beats)
        except Exception:
            return ""

    def _generate_project_scene_prompts(
        self,
        *,
        topic: str,
        script: str,
        sections: list[str],
        channel: ChannelPromptContext,
        context_profile: dict[str, str],
        visual_beat_block: str,
        count: int,
        llm_provider: str,
        llm_model: str,
        retention_mode: str,
    ) -> list[str]:
        sections_text = "\n".join(
            f'SECTION {idx + 1}: "{section}"' for idx, section in enumerate(sections)
        )
        era_context = ""
        if context_profile and (context_profile.get("setting") or context_profile.get("visual_anchors")):
            bits = []
            if context_profile.get("setting"):
                bits.append(f"the story is set in {context_profile['setting']}")
            if context_profile.get("visual_anchors"):
                bits.append(f"visual anchors that must appear naturally: {context_profile['visual_anchors']}")
            if context_profile.get("must_avoid"):
                bits.append(f"forbidden off-topic elements: {context_profile['must_avoid']}")
            era_context = "\n\nPROJECT CONTEXT PROFILE - mandatory: " + ". ".join(bits) + "."

        visual_retention = CosmicRetentionEngine.visual_retention_directive(topic, channel.niche)
        max_visual = (
            MaxRetentionEngine.visual_generation_directive(topic, channel.niche)
            if is_max_retention(retention_mode)
            else ""
        )
        proper_noun_rule = (
            "- Because this channel is astronomy/universe-related, every prompt must name the exact cosmic object, mission, telescope, signal or phenomenon from the topic/section. Do not replace it with generic 'galaxy', 'space', 'stars' or 'scientists'.\n"
            if CosmicRetentionEngine.is_cosmic_context(topic, channel.niche)
            else ""
        )

        prompt = f"""Task: write exactly {count} MoneyPrinter project image prompts for a YouTube Short.

This must follow the same logic as the project's YouTube.generate_prompts flow: one scene prompt per script section, section-faithful, scene-only, then the channel style is applied downstream.

CHANNEL: {channel.nickname or "(selected channel)"}
CHANNEL NICHE: {channel.niche or "(not specified)"}
TOPIC: {topic}
{era_context}
{visual_retention}
{max_visual}

SCRIPT DIVIDED INTO {count} SECTIONS:
{sections_text}
{visual_beat_block}

ABSOLUTE RULES:
1. SECTION FIDELITY: prompt N must illustrate SECTION N literally. Do not invent a random gallery.
2. CHANNEL FIT: every prompt must feel like it belongs to this channel niche, not a generic stock-photo pack.
3. TOPIC ANCHOR: every prompt must include a concrete anchor from the topic or section: proper noun, mission, object, place, instrument, material, physical phenomenon or visible consequence.
{proper_noun_rule}4. NO RANDOM SCIENCE STOCK: do not use generic researchers at screens, messy desks, team meetings, radio telescopes, observatory domes or laser guide stars unless the section/topic directly calls for that exact visual.
5. Prefer no people. If people are necessary, avoid identifiable faces; use backs, silhouettes, hands, tools, documents or environmental occlusion.
6. English only. Translate from Spanish naturally.
7. Describe scenes only. Do not write art-style words: painting, illustration, cartoon, anime, drawing, render, photorealistic, cinematic, 4K, 8K, lens, camera.
8. No multi-image triggers: collage, montage, panels, storyboard, grid, split screen, multiple frames.
9. 45 to 75 English words per prompt.

Return ONLY a JSON array of {count} strings. No markdown, no explanation."""

        try:
            raw = self._call_llm(
                prompt,
                temperature=0.72,
                llm_provider=llm_provider,
                llm_model=llm_model,
            )
            parsed = _extract_json_array(raw)
            prompts = [self._sanitize_scene_prompt(str(item)) for item in parsed if str(item).strip()]
        except Exception:
            prompts = []

        if len(prompts) < count:
            prompts.extend(
                self._fallback_scene_prompts(
                    topic=topic,
                    sections=sections,
                    channel=channel,
                    context_profile=context_profile,
                    count=count - len(prompts),
                    offset=len(prompts),
                )
            )
        return prompts[:count]

    def _fallback_scene_prompts(
        self,
        *,
        topic: str,
        sections: list[str],
        channel: ChannelPromptContext,
        context_profile: dict[str, str],
        count: int,
        offset: int = 0,
    ) -> list[str]:
        anchors = context_profile.get("visual_anchors") or topic
        setting = context_profile.get("setting") or channel.niche or "the video's real-world setting"
        out = []
        for idx in range(count):
            section = sections[(offset + idx) % len(sections)] if sections else topic
            out.append(self._sanitize_scene_prompt(
                f"{topic} shown through the literal visual consequence described in this narration section: "
                f"{section}. The scene takes place in {setting}, anchored by {anchors}, with one clear subject, "
                f"one readable action, physical materials and environment tied to the channel niche, no generic "
                f"research desk, no random team meeting, no off-topic observatory unless named in the section."
            ))
        return out

    def _format_pack(
        self,
        *,
        topic: str,
        generated_topic: bool,
        script: str,
        scene_prompts: list[str],
        channel: ChannelPromptContext,
        context_profile: dict[str, str],
        aspect_ratio: str,
        retention_mode: str,
    ) -> str:
        lines = [
            "MONEYPRINTER PHOTO PROMPT PACK",
            f"CANAL: {channel.nickname or 'sin canal seleccionado'}",
            f"NICHO DEL CANAL: {channel.niche or 'sin niche'}",
            f"TEMA: {topic}",
            f"TEMA GENERADO POR LLM: {'si' if generated_topic else 'no'}",
            f"FORMATO: {aspect_ratio}",
            f"MODO RETENCION: {retention_mode}",
            "METODO: prompts basados en el flujo del proyecto: tema -> guion base -> secciones -> prompt por seccion -> estilo del canal.",
            "",
        ]
        if channel.image_style.strip():
            lines.append(f"IMAGE_STYLE DEL CANAL: {channel.image_style.strip()}")
        else:
            lines.append("IMAGE_STYLE DEL CANAL: default project documentary/cosmic style")
        if context_profile:
            lines.extend([
                f"SETTING: {context_profile.get('setting', '')}",
                f"VISUAL_ANCHORS: {context_profile.get('visual_anchors', '')}",
                f"MUST_AVOID: {context_profile.get('must_avoid', '')}",
            ])
        lines.extend([
            "",
            "GUION BASE USADO PARA ALINEAR LAS FOTOS:",
            script.strip(),
            "",
            f"NEGATIVE UNIVERSAL: {PROJECT_NEGATIVE}",
            "",
        ])

        for idx, scene_prompt in enumerate(scene_prompts, 1):
            positive = self._apply_project_style(
                scene_prompt,
                channel=channel,
                context_profile=context_profile,
                aspect_ratio=aspect_ratio,
                topic=topic,
            )
            negative = self._negative_prompt(scene_prompt, channel, topic)
            lines.extend([
                f"PROMPT {idx:02d}",
                f"Project scene prompt: {scene_prompt}",
                f"Positive prompt: {positive}",
                f"Negative prompt: {negative}",
                "",
            ])
        return "\n".join(lines).strip() + "\n"

    def _apply_project_style(
        self,
        scene_prompt: str,
        *,
        channel: ChannelPromptContext,
        context_profile: dict[str, str],
        aspect_ratio: str,
        topic: str,
    ) -> str:
        clean = self._sanitize_scene_prompt(scene_prompt).rstrip(", .")
        parts: list[str] = []
        custom_style = _usable_style(channel.image_style)

        if custom_style:
            short_style = custom_style if len(custom_style) <= 200 else custom_style[:200].rsplit(",", 1)[0]
            parts.append(f"ART STYLE - render the entire image in this style: {custom_style}")
            parts.append(clean)
            context = self._context_clause(context_profile, custom=True)
            if context:
                parts.append(context)
            parts.append(
                f"FINAL REMINDER - keep the entire image in the art style described above ({short_style}). "
                f"Do not default to photorealism if the channel style says otherwise. {FACE_SAFE_COMPOSITION}"
            )
        else:
            parts.append(clean)
            context = self._context_clause(context_profile, custom=False)
            if context:
                parts.append(context)
            if CosmicRetentionEngine.is_cosmic_context(topic, channel.niche):
                parts.append(COSMIC_BASE_STYLE)
            else:
                parts.append(DEFAULT_BASE_STYLE)
            parts.append(FACE_SAFE_COMPOSITION)

        parts.append(f"Aspect ratio {aspect_ratio}, one single image, no text, no letters, no logos, no watermark")
        return _collapse_spaces(". ".join(p for p in parts if p))[:1800]

    def _context_clause(self, profile: dict[str, str], *, custom: bool) -> str:
        if not profile:
            return ""
        parts = []
        if profile.get("setting"):
            parts.append(f"PROJECT CONTEXT - this scene takes place in {profile['setting']}")
        if profile.get("visual_anchors"):
            parts.append(f"required visual anchors to weave in naturally: {profile['visual_anchors']}")
        if profile.get("must_avoid"):
            parts.append(f"forbidden off-topic elements: {profile['must_avoid']}")
        return ". ".join(parts)

    def _negative_prompt(self, scene_prompt: str, channel: ChannelPromptContext, topic: str) -> str:
        extras = []
        if CosmicRetentionEngine.is_cosmic_context(topic, channel.niche):
            extras.append(
                "generic star wallpaper, random observatory, random scientist at monitor, fake constellation map, "
                "fictional spaceship, neon fantasy planet, unrelated telescope"
            )
        if channel.image_style.strip():
            extras.append("style drift away from channel image_style")
        return PROJECT_NEGATIVE + (", " + ", ".join(extras) if extras else "")

    def _sanitize_scene_prompt(self, text: str) -> str:
        cleaned = _strip_code_fences(text or "")
        cleaned = COLLAGE_TRIGGERS.sub("", cleaned)
        for pattern, replacement in FACE_PROMPT_REWRITES:
            cleaned = pattern.sub(replacement, cleaned)
        return _collapse_spaces(cleaned).strip(" ,")

    def _call_llm(
        self,
        prompt: str,
        *,
        temperature: float,
        llm_provider: str,
        llm_model: str,
    ) -> str:
        if self._text_generator is not None:
            return self._text_generator(prompt, temperature=temperature)

        from llm_provider import force_provider, generate_text, is_user_override, set_user_override

        provider = (llm_provider or _infer_provider_from_model(llm_model) or "").strip().lower()
        model = (llm_model or "").strip()

        if not provider:
            return generate_text(prompt, model_name=model or None, temperature=temperature)

        prev_override = is_user_override()
        set_user_override(True)
        try:
            with force_provider(provider, model or None):
                return generate_text(prompt, model_name=model or None, temperature=temperature)
        finally:
            set_user_override(prev_override)


def _fallback_script(topic: str, channel: ChannelPromptContext, sentence_count: int, language: str) -> str:
    if CosmicRetentionEngine.is_cosmic_context(topic, channel.niche):
        base = [
            f"{topic} no parece grande hasta que imaginas su escala real.",
            "La primera pista visible esta en la luz que deja atras.",
            "Esa luz revela una estructura que no se comporta como esperamos.",
            "El instrumento que la observa convierte una senal debil en evidencia.",
            "Cada medicion acerca el misterio a una consecuencia fisica concreta.",
            "La comparacion con nuestro sistema solar vuelve el fenomeno inquietante.",
            "Lo importante no es solo verlo, sino entender que cambia nuestra idea del cielo.",
            "Y cuando el dato encaja, el universo parece menos familiar que antes.",
        ]
    else:
        base = [
            f"{topic} empieza con un detalle que casi nadie mira.",
            "Ese detalle revela un problema mas grande dentro del tema.",
            "El entorno muestra por que esta historia importa para el canal.",
            "Un objeto concreto permite entender el conflicto sin explicarlo demasiado.",
            "La tension sube cuando aparece la consecuencia visible.",
            "El giro cambia la manera de interpretar la escena inicial.",
            "La ultima evidencia conecta todo con una idea simple.",
            "Y el cierre deja una imagen clara de lo que estaba en juego.",
        ]
    while len(base) < sentence_count:
        base.append(base[-1])
    return " ".join(base[:sentence_count])


def _split_sections(script: str, count: int, fallback: str) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", script or "") if s.strip()]
    if not sentences:
        return [fallback] * count
    sections: list[str] = []
    per_section = max(1, len(sentences) // count)
    for idx in range(count):
        start = idx * per_section
        end = start + per_section if idx < count - 1 else len(sentences)
        chunk = " ".join(sentences[start:end]).strip()
        sections.append(chunk or fallback)
    while len(sections) < count:
        sections.append(fallback)
    return sections[:count]


def _recent_topics(videos: list[dict[str, Any]], limit: int = 35) -> list[str]:
    out = []
    for video in list(videos or [])[-limit:]:
        value = str(video.get("subject") or video.get("title") or "").strip()
        if value:
            out.append(value)
    return out


def _clean_topic(value: str) -> str:
    text = _strip_code_fences(value or "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    first = lines[0]
    first = re.sub(r"^\s*(?:topic|tema|title|titulo|título)\s*:\s*", "", first, flags=re.I)
    first = re.sub(r"^[\s\-*#>\d.)]+", "", first).strip()
    first = first.strip("\"'` ")
    first = re.sub(r"\s+", " ", first)
    return first[:180].strip()


def _strip_code_fences(value: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fences(text)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        parsed = json.loads(cleaned)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_json_array(text: str) -> list[Any]:
    cleaned = _strip_code_fences(text)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        pass
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text[:70] or "tema-generado"


def _collapse_spaces(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s+\.", ".", text)
    return text.strip()


def _usable_style(value: str) -> str:
    style = (value or "").strip()
    if not style:
        return ""
    words = re.findall(r"[A-Za-zÀ-ÿ]{3,}", style)
    if len(style) < 8 or len(words) < 2 or style.lower() in {"default", "test", "tbd", "todo", "n/a", "na", "none"}:
        return ""
    return style


def _infer_provider_from_model(model: str) -> str:
    m = (model or "").strip().lower()
    if not m:
        return ""
    if m.startswith(("gemini-", "gemma-")):
        return "gemini"
    if m.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    if m in {"openai", "openai-large", "deepseek", "llama", "mistral"}:
        return "pollinations"
    return "ollama"
