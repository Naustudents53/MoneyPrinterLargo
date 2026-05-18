from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Iterable

from config import ROOT_DIR


SUPPORTED_SOCIAL_PLATFORMS = ("youtube", "tiktok", "facebook")

PLATFORM_PROFILES = {
    "youtube": {
        "name": "YouTube",
        "caption_min": 180,
        "caption_max": 1200,
        "hashtags_min": 2,
        "hashtags_max": 5,
        "tone": "seo_clarity",
    },
    "tiktok": {
        "name": "TikTok",
        "caption_min": 55,
        "caption_max": 260,
        "hashtags_min": 4,
        "hashtags_max": 7,
        "tone": "fast_hook",
    },
    "facebook": {
        "name": "Facebook",
        "caption_min": 90,
        "caption_max": 420,
        "hashtags_min": 2,
        "hashtags_max": 5,
        "tone": "clear_social",
    },
}

_STOPWORDS = {
    "a", "al", "an", "and", "ante", "as", "at", "con", "de", "del", "el",
    "en", "for", "from", "in", "la", "las", "lo", "los", "of", "on", "or",
    "para", "por", "que", "se", "sin", "sobre", "su", "sus", "the", "to",
    "un", "una", "unas", "unos", "y",
}

_TREND_PACKS = {
    "default": [
        "historia real",
        "dato curioso",
        "lo que nadie cuenta",
        "parte 2",
        "viral",
    ],
    "historia": [
        "historia real",
        "documental",
        "datos historicos",
        "misterio historico",
        "antiguo",
    ],
    "ciencia": [
        "ciencia",
        "espacio",
        "universo",
        "descubrimiento",
        "datos curiosos",
    ],
    "finanzas": [
        "dinero",
        "negocios",
        "emprendimiento",
        "finanzas",
        "caso real",
    ],
    "terror": [
        "misterio",
        "caso real",
        "relato",
        "inquietante",
        "nocturno",
    ],
}


def ensure_social_plan(
    video_path: str,
    title: str,
    description: str,
    subject: str = "",
    niche: str = "",
    language: str = "espanol",
    platforms: Iterable[str] = SUPPORTED_SOCIAL_PLATFORMS,
    is_long: bool = False,
    thumbnail_path: str = "",
    account_uuid: str = "",
) -> dict:
    """Build and persist a social optimization package next to the video."""
    sidecar_path = _sidecar_path(video_path)
    sidecar = _read_json(sidecar_path) or {}
    existing = sidecar.get("social_plan") if isinstance(sidecar.get("social_plan"), dict) else None
    selected_platforms = set(platforms or [])
    wanted = [p for p in SUPPORTED_SOCIAL_PLATFORMS if p in selected_platforms]
    if existing and all(p in (existing.get("captions") or {}) for p in wanted):
        return existing

    plan = build_social_plan(
        video_path=video_path,
        title=title,
        description=description,
        subject=subject,
        niche=niche,
        language=language,
        platforms=wanted,
        is_long=is_long,
        thumbnail_path=thumbnail_path,
        existing_titles=_load_existing_titles(account_uuid),
    )
    sidecar["social_plan"] = plan
    _write_json(sidecar_path, sidecar)
    _merge_manifest(video_path, {"social_plan": _compact_plan(plan)})
    return plan


def load_social_plan(video_path: str) -> dict:
    sidecar = _read_json(_sidecar_path(video_path)) or {}
    plan = sidecar.get("social_plan")
    return plan if isinstance(plan, dict) else {}


def choose_caption(plan: dict, platform: str, fallback: str) -> str:
    captions = (plan or {}).get("captions") or {}
    item = captions.get(platform) or {}
    caption = item.get("caption") or fallback
    return str(caption).strip()


def build_social_plan(
    video_path: str,
    title: str,
    description: str,
    subject: str = "",
    niche: str = "",
    language: str = "espanol",
    platforms: Iterable[str] = SUPPORTED_SOCIAL_PLATFORMS,
    is_long: bool = False,
    thumbnail_path: str = "",
    existing_titles: Iterable[str] = (),
) -> dict:
    selected_platforms = set(platforms or [])
    platforms = [p for p in SUPPORTED_SOCIAL_PLATFORMS if p in selected_platforms]
    title = _clean_text(title)
    description = _clean_text(description)
    subject = _clean_text(subject)
    topic_text = " ".join(x for x in (title, subject, niche) if x)
    keywords = _keywords(topic_text, limit=8)
    trend_terms = _trend_terms(niche, topic_text, keywords)
    hashtags = _hashtags(keywords, trend_terms)
    duplicate = _duplicate_title_status(title, existing_titles)
    hook_pack = _hook_pack(title, subject, keywords, duplicate)
    cta = _cta(title, niche, language)
    quality_gate = _quality_gate(video_path, platforms, is_long)
    safe_zone = _safe_zone_scan(quality_gate, hook_pack)
    first_3s = _first_3s_plan(hook_pack, safe_zone)
    cover_plan = _cover_plan(video_path, thumbnail_path, hook_pack, platforms, quality_gate)

    captions = {}
    for platform in platforms:
        variants = _caption_variants(
            platform=platform,
            title=title,
            description=description,
            hooks=hook_pack,
            hashtags=hashtags,
            cta=cta,
            duplicate=duplicate,
        )
        scored = [
            {
                "caption": variant,
                "score": _caption_score(platform, variant, hashtags, hooks=hook_pack),
                "reasons": _caption_reasons(platform, variant, hashtags),
            }
            for variant in variants
        ]
        scored.sort(key=lambda item: item["score"], reverse=True)
        captions[platform] = {
            "profile": PLATFORM_PROFILES[platform],
            "title": _platform_title(platform, title, hooks=hook_pack, duplicate=duplicate),
            "description": description if platform == "youtube" else _shorten(description, 360),
            "caption": scored[0]["caption"],
            "score": scored[0]["score"],
            "variants": scored,
            "hashtags": hashtags[: PLATFORM_PROFILES[platform]["hashtags_max"]],
            "cta": cta,
        }

    return {
        "version": 1,
        "generated_at": _utc_now(),
        "platform_profiles": PLATFORM_PROFILES,
        "platforms": platforms,
        "trend_injector": {
            "terms": trend_terms,
            "source": "local niche trend pack + topic keywords",
        },
        "title_recycle": duplicate,
        "hook_pack": hook_pack,
        "first_3_seconds": first_3s,
        "safe_zone": safe_zone,
        "cover_plan": cover_plan,
        "quality_gate": quality_gate,
        "cta": cta,
        "captions": captions,
    }


def _sidecar_path(video_path: str) -> str:
    return os.path.splitext(video_path)[0] + ".meta.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _manifest_path(video_path: str) -> str:
    base = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(ROOT_DIR, ".mp", f"{base}.manifest.json")


def _read_json(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return None


def _write_json(path: str, data: dict) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _merge_manifest(video_path: str, patch: dict) -> None:
    path = _manifest_path(video_path)
    data = _read_json(path) or {}
    if not data:
        return
    data.update(patch)
    _write_json(path, data)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\n", " ")).strip()


def _keywords(text: str, limit: int = 8) -> list[str]:
    words = re.findall(r"[^\W_]+", text or "", flags=re.UNICODE)
    out = []
    seen = set()
    for word in words:
        clean = _strip_accents(word).lower()
        if len(clean) < 4 or clean in _STOPWORDS or clean in seen:
            continue
        seen.add(clean)
        out.append(word.strip("#"))
        if len(out) >= limit:
            break
    return out


def _strip_accents(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _trend_terms(niche: str, topic_text: str, keywords: list[str]) -> list[str]:
    haystack = _strip_accents(f"{niche} {topic_text}").lower()
    selected = list(_TREND_PACKS["default"])
    for key, terms in _TREND_PACKS.items():
        if key != "default" and key in haystack:
            selected = terms + selected
            break
    selected = keywords[:3] + selected
    deduped = []
    seen = set()
    for term in selected:
        key = _strip_accents(term).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped[:8]


def _hashtags(keywords: list[str], trend_terms: list[str]) -> list[str]:
    tags = []
    for term in [*keywords, *trend_terms]:
        raw = _strip_accents(term)
        raw = re.sub(r"[^A-Za-z0-9]+", "", raw.title())
        if len(raw) < 3:
            continue
        tag = f"#{raw[:28]}"
        if tag.lower() not in {x.lower() for x in tags}:
            tags.append(tag)
        if len(tags) >= 10:
            break
    return tags


def _duplicate_title_status(title: str, existing_titles: Iterable[str]) -> dict:
    title_norm = _norm(title)
    best = {"title": "", "similarity": 0.0}
    for existing in existing_titles:
        existing_norm = _norm(existing)
        if not existing_norm:
            continue
        if existing_norm == title_norm:
            best = {"title": existing, "similarity": 1.0}
            break
        score = SequenceMatcher(None, title_norm, existing_norm).ratio()
        if score > best["similarity"]:
            best = {"title": existing, "similarity": round(score, 3)}
    status = "clear"
    if best["similarity"] >= 0.9:
        status = "rewrite_recommended"
    elif best["similarity"] >= 0.82:
        status = "watch"
    return {
        "status": status,
        "nearest_title": best["title"],
        "similarity": best["similarity"],
    }


def _norm(text: str) -> str:
    text = _strip_accents(text or "").lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _hook_pack(title: str, subject: str, keywords: list[str], duplicate: dict) -> list[dict]:
    anchor = subject or title
    key = keywords[0] if keywords else _shorten(anchor, 42)
    base = _shorten(anchor, 68)
    hooks = [
        ("misterio", f"Nadie cuenta esta parte de {key}"),
        ("shock", f"Esto cambio todo: {base}"),
        ("pregunta", f"Por que {base} importa mas de lo que parece?"),
    ]
    if duplicate.get("status") == "rewrite_recommended":
        hooks.insert(0, ("anti_repetido", f"La version que faltaba: {base}"))
    out = []
    for idx, (mode, text) in enumerate(hooks[:4], 1):
        out.append({
            "id": mode,
            "text": _clean_hook(text),
            "score": max(60, 96 - idx * 7),
        })
    return out


def _clean_hook(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" .")
    return _shorten(text, 82)


def _cta(title: str, niche: str, language: str) -> str:
    haystack = _strip_accents(f"{title} {niche} {language}").lower()
    if "historia" in haystack:
        return "Comenta que historia deberia ir en la parte 2."
    if "ciencia" in haystack or "espacio" in haystack:
        return "Guardalo y dime que misterio del universo sigue."
    if "finanza" in haystack or "dinero" in haystack:
        return "Guardalo antes de tomar tu proxima decision."
    if "terror" in haystack or "misterio" in haystack:
        return "Si quieres parte 2, escribelo en comentarios."
    return "Sigueme para mas historias como esta."


def _caption_variants(
    platform: str,
    title: str,
    description: str,
    hooks: list[dict],
    hashtags: list[str],
    cta: str,
    duplicate: dict,
) -> list[str]:
    hook = hooks[0]["text"] if hooks else title
    second_hook = hooks[1]["text"] if len(hooks) > 1 else hook
    tags = " ".join(hashtags[: PLATFORM_PROFILES[platform]["hashtags_max"]])
    short_desc = _shorten(description, 180)
    if platform == "youtube":
        return [
            f"{title}\n\n{description}\n\n{tags}".strip(),
            f"{title}\n\n{short_desc}\n\n{cta}\n\n{tags}".strip(),
            f"{hook}\n\n{description}\n\n{tags}".strip(),
        ]
    if platform == "tiktok":
        return [
            f"{hook}. {cta} {tags}".strip(),
            f"{second_hook}. {tags}".strip(),
            f"{_platform_title(platform, title, hooks, duplicate)}. {cta} {tags}".strip(),
        ]
    return [
        f"{hook}.\n\n{short_desc}\n\n{cta}\n\n{tags}".strip(),
        f"{_platform_title(platform, title, hooks, duplicate)}\n\n{cta}\n\n{tags}".strip(),
        f"{second_hook}. {short_desc} {tags}".strip(),
    ]


def _platform_title(platform: str, title: str, hooks: list[dict], duplicate: dict) -> str:
    if platform == "youtube":
        return title
    if duplicate.get("status") == "rewrite_recommended" and hooks:
        return hooks[0]["text"]
    return _shorten(title, 78 if platform == "tiktok" else 96)


def _caption_score(platform: str, caption: str, hashtags: list[str], hooks: list[dict]) -> int:
    profile = PLATFORM_PROFILES[platform]
    length = len(caption)
    score = 52
    if profile["caption_min"] <= length <= profile["caption_max"]:
        score += 18
    else:
        score -= min(18, abs(length - profile["caption_max"]) // 20)
    tag_count = len(re.findall(r"#\w+", caption))
    if profile["hashtags_min"] <= tag_count <= profile["hashtags_max"]:
        score += 14
    elif tag_count:
        score += 6
    if hooks and hooks[0]["text"].split()[0].lower() in caption.lower():
        score += 8
    if "comenta" in caption.lower() or "guard" in caption.lower() or "sigue" in caption.lower():
        score += 8
    if re.search(r"\b(descubre|increible|no vas a creer)\b", _strip_accents(caption).lower()):
        score -= 6
    return max(0, min(100, score))


def _caption_reasons(platform: str, caption: str, hashtags: list[str]) -> list[str]:
    reasons = []
    profile = PLATFORM_PROFILES[platform]
    length = len(caption)
    if profile["caption_min"] <= length <= profile["caption_max"]:
        reasons.append("length_fit")
    if len(re.findall(r"#\w+", caption)) >= profile["hashtags_min"]:
        reasons.append("hashtag_density")
    if "comenta" in caption.lower() or "guard" in caption.lower() or "sigue" in caption.lower():
        reasons.append("cta_present")
    return reasons or ["basic"]


def _quality_gate(video_path: str, platforms: list[str], is_long: bool) -> dict:
    checks = []
    width = height = duration = None
    has_audio = None
    file_size_mb = 0.0
    if os.path.isfile(video_path):
        file_size_mb = round(os.path.getsize(video_path) / (1024 * 1024), 1)
    try:
        from moviepy.editor import VideoFileClip

        clip = VideoFileClip(video_path)
        width, height = clip.size
        duration = float(clip.duration or 0)
        has_audio = clip.audio is not None
        clip.close()
    except Exception as exc:
        checks.append(_check("video_probe", "warn", f"Could not inspect video: {type(exc).__name__}"))

    if width and height:
        ratio = width / max(height, 1)
        vertical = height >= width
        if ("tiktok" in platforms or "facebook" in platforms) and not vertical:
            checks.append(_check("vertical_format", "warn", "TikTok/FB perform best with 9:16 vertical video."))
        elif vertical and height >= 1280 and width >= 720:
            checks.append(_check("vertical_format", "pass", "Vertical >= 720x1280."))
        else:
            checks.append(_check("resolution", "warn", f"Resolution detected: {width}x{height}."))
        if vertical and not (0.52 <= ratio <= 0.60):
            checks.append(_check("aspect_ratio", "warn", "Vertical video is not close to 9:16."))
        else:
            checks.append(_check("aspect_ratio", "pass", "Aspect ratio acceptable."))

    if duration is not None:
        if ("tiktok" in platforms or "facebook" in platforms) and duration > 600:
            checks.append(_check("duration", "warn", "Long social upload; consider a short cutdown."))
        elif duration >= 3:
            checks.append(_check("duration", "pass", f"Duration {round(duration, 1)}s."))
        else:
            checks.append(_check("duration", "fail", "Video is shorter than 3 seconds."))

    if has_audio is False:
        checks.append(_check("audio", "fail", "No audio track detected."))
    elif has_audio is True:
        checks.append(_check("audio", "pass", "Audio track detected."))

    if file_size_mb > 0:
        checks.append(_check("file_size", "pass" if file_size_mb < 4096 else "warn", f"{file_size_mb} MB"))

    score = 100
    for check in checks:
        if check["status"] == "warn":
            score -= 12
        elif check["status"] == "fail":
            score -= 35
    status = "pass" if score >= 80 else "warn" if score >= 45 else "fail"
    return {
        "status": status,
        "score": max(0, score),
        "width": width,
        "height": height,
        "duration_seconds": round(duration, 2) if duration is not None else None,
        "file_size_mb": file_size_mb,
        "checks": checks,
    }


def _check(name: str, status: str, message: str) -> dict:
    return {"name": name, "status": status, "message": message}


def _safe_zone_scan(quality_gate: dict, hooks: list[dict]) -> dict:
    width = quality_gate.get("width") or 1080
    height = quality_gate.get("height") or 1920
    vertical = height >= width
    top = round(height * 0.12)
    bottom = round(height * 0.22)
    right = round(width * 0.18)
    overlay_y = round(height * (0.18 if vertical else 0.12))
    return {
        "status": "pass" if vertical else "warn",
        "safe_margins_px": {
            "top": top,
            "bottom": bottom,
            "right": right if vertical else round(width * 0.08),
            "left": round(width * 0.06),
        },
        "recommended_hook_overlay": {
            "text": hooks[0]["text"] if hooks else "",
            "position": "top_center",
            "y_px": overlay_y,
            "max_width_pct": 82 if vertical else 70,
        },
        "notes": [
            "Keep hook text in the upper third.",
            "Avoid bottom caption controls and right-side engagement buttons.",
        ],
    }


def _first_3s_plan(hooks: list[dict], safe_zone: dict) -> dict:
    hook = hooks[0]["text"] if hooks else ""
    return {
        "status": "ready",
        "overlay_text": hook,
        "cut_pattern": ["0.0s hook frame", "0.8s motion/detail", "2.0s reveal"],
        "safe_position": safe_zone.get("recommended_hook_overlay", {}),
    }


def _cover_plan(
    video_path: str,
    thumbnail_path: str,
    hooks: list[dict],
    platforms: list[str],
    quality_gate: dict,
) -> dict:
    hook = hooks[0]["text"] if hooks else ""
    covers = {}
    for platform in platforms:
        covers[platform] = {
            "source": thumbnail_path if platform == "youtube" and thumbnail_path else video_path,
            "overlay_text": _shorten(hook, 44),
            "format": "9:16" if platform in ("tiktok", "facebook") else "16:9",
            "status": "planned",
        }
    return covers


def _shorten(text: str, limit: int) -> str:
    text = _clean_text(text)
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "..."


def _compact_plan(plan: dict) -> dict:
    return {
        "version": plan.get("version"),
        "generated_at": plan.get("generated_at"),
        "quality_gate": plan.get("quality_gate"),
        "safe_zone": plan.get("safe_zone"),
        "trend_terms": (plan.get("trend_injector") or {}).get("terms", []),
        "caption_scores": {
            platform: item.get("score")
            for platform, item in (plan.get("captions") or {}).items()
        },
    }


def _load_existing_titles(account_uuid: str = "") -> list[str]:
    path = os.path.join(ROOT_DIR, ".mp", "youtube.json")
    raw = _read_json(path) or {}
    titles = []
    for account in raw.get("accounts", []) or []:
        if account_uuid and account.get("id") != account_uuid:
            continue
        for video in account.get("videos", []) or []:
            title = video.get("title") or ""
            if title:
                titles.append(title)
    return titles
