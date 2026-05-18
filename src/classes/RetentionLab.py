"""Retention diagnostics and pre-render scoring for Shorts.

The lab is deliberately local-only: it learns from the cached channel history
that already lives in .mp/youtube.json and never calls YouTube on its own.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from .NarrationVoice import NarrationVoice
from .MaxRetention import MaxRetentionEngine


class RetentionLab:
    """Analyze local Shorts history and gate scripts before rendering."""

    WINNER_VIEWS = 1000
    WEAK_VIEWS = 100
    SCORE_THRESHOLD = 8.0
    HOOK_SCORE_THRESHOLD = 8.0
    FIRST_IMAGE_SCORE_THRESHOLD = 7.0

    STOPWORDS = {
        "a", "al", "algo", "ante", "antes", "asi", "aun", "cada", "como",
        "con", "contra", "cual", "cuando", "de", "del", "desde", "donde",
        "dos", "el", "ella", "ellos", "en", "entre", "era", "es", "ese",
        "eso", "esta", "este", "esto", "fue", "hace", "hay", "la", "las",
        "lo", "los", "mas", "menos", "muy", "no", "nos", "o", "otra",
        "otro", "para", "pero", "por", "porque", "que", "se", "sin",
        "sobre", "son", "su", "sus", "te", "tu", "un", "una", "uno",
        "unos", "y", "ya",
        "the", "of", "and", "in", "on", "to", "for", "with", "why",
        "how", "what", "this", "that", "from", "into", "about",
        "short", "shorts", "video", "youtube", "viral", "historia",
        "curiosidad", "curiosidades", "misterio", "misterios", "secreto",
        "secretos",
        "ano", "anos", "universo", "cosmos", "cosmico", "cosmica", "espacio",
        "astronomia", "astronomico", "astronomica", "ciencia", "scientific",
        "science", "space",
    }

    @classmethod
    def analyze_accounts(cls, accounts: list[dict[str, Any]]) -> dict[str, Any]:
        channels = [cls.analyze_channel(account) for account in accounts]
        aggregate = {
            "channels": len(channels),
            "shorts": sum(ch["stats"]["shorts"] for ch in channels),
            "known_views": sum(ch["stats"]["known_views"] for ch in channels),
            "unknown_views": sum(ch["stats"]["unknown_views"] for ch in channels),
            "winners": sum(ch["stats"]["winners"] for ch in channels),
            "weak": sum(ch["stats"]["weak"] for ch in channels),
        }
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "aggregate": aggregate,
            "channels": channels,
        }

    @classmethod
    def analyze_channel(cls, account: dict[str, Any]) -> dict[str, Any]:
        videos = account.get("videos") or []
        shorts = [cls._shape_video(v) for v in videos if cls._is_short(v)]
        known = [v for v in shorts if v["views"] is not None]
        winners = sorted(
            [v for v in known if v["views"] >= cls.WINNER_VIEWS],
            key=lambda v: v["views"],
            reverse=True,
        )
        weak = sorted(
            [v for v in known if v["views"] < cls.WEAK_VIEWS],
            key=lambda v: v.get("date") or "",
            reverse=True,
        )
        views = sorted(v["views"] for v in known)
        avg_views = round(sum(views) / len(views), 1) if views else 0
        median_views = cls._median(views)
        term_stats = cls._term_stats(known)

        stats = {
            "videos": len(videos),
            "shorts": len(shorts),
            "known_views": len(known),
            "unknown_views": len(shorts) - len(known),
            "winners": len(winners),
            "weak": len(weak),
            "avg_views": avg_views,
            "median_views": median_views,
        }
        return {
            "channel_id": account.get("id", ""),
            "channel_nickname": account.get("nickname", ""),
            "niche": account.get("niche", ""),
            "language": account.get("language", ""),
            "stats": stats,
            "winners": winners[:8],
            "weak_videos": weak[:8],
            "burned_topics": term_stats["burned"][:10],
            "winning_terms": term_stats["winning"][:10],
            "recommendations": cls._recommendations(stats, term_stats),
        }

    @classmethod
    def burned_topic_directive(cls, videos: list[dict[str, Any]], limit: int = 8) -> str:
        burned = cls.burned_terms(videos, limit=limit)
        if not burned:
            return ""
        lines = []
        for item in burned:
            examples = "; ".join(item.get("examples") or [])
            lines.append(
                f"- {item['term']} ({item['weak_count']} weak / avg {item['avg_views']} views)"
                + (f": {examples[:140]}" if examples else "")
            )
        return (
            "\n\nRETENTION LAB - LOW-VIEW PATTERNS TO AVOID:\n"
            "These local channel patterns repeatedly underperformed. Do not reuse them "
            "unless the new topic has a sharper named object and a clearly different visual hook.\n"
            + "\n".join(lines)
            + "\n"
        )

    @classmethod
    def burned_terms(cls, videos: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
        shaped = [cls._shape_video(v) for v in videos or [] if cls._is_short(v)]
        known = [v for v in shaped if v["views"] is not None]
        return cls._term_stats(known)["burned"][:limit]

    @classmethod
    def topic_burned_reason(cls, topic: str, videos: list[dict[str, Any]]) -> str:
        normalized_topic = cls.normalize(topic)
        if not normalized_topic:
            return ""
        topic_tokens = set(cls._keywords(topic, limit=12))
        for item in cls.burned_terms(videos, limit=12):
            term = str(item.get("term") or "").strip()
            if not term:
                continue
            if " " in term and term in normalized_topic:
                return f"resembles low-view pattern '{term}'"
            if (
                " " not in term
                and len(term) >= 6
                and term in topic_tokens
                and int(item.get("weak_count") or 0) >= 2
            ):
                return f"reuses weak term '{term}'"
        return ""

    @classmethod
    def winning_topic_directive(cls, videos: list[dict[str, Any]], limit: int = 5) -> str:
        shaped = [cls._shape_video(v) for v in videos or [] if cls._is_short(v)]
        known = [v for v in shaped if v["views"] is not None]
        winning = cls._term_stats(known)["winning"][:limit]
        if not winning:
            return ""
        lines = []
        for item in winning:
            examples = "; ".join(item.get("examples") or [])
            lines.append(
                f"- {item['term']} ({item['winner_count']} winners / avg {item['avg_views']} views)"
                + (f": {examples[:140]}" if examples else "")
            )
        return (
            "\n\nRETENTION LAB - WINNING PATTERNS TO ADAPT:\n"
            "Use these as pattern inspiration, but change the exact object or angle.\n"
            + "\n".join(lines)
            + "\n"
        )

    @classmethod
    def select_best_hook(
        cls,
        topic: str,
        niche: str,
        language: str,
        generate_response: Callable[[str], str],
        history_videos: list[dict[str, Any]] | None = None,
        candidates: int = 8,
    ) -> tuple[str, dict[str, Any]]:
        candidates = max(4, min(int(candidates or 8), 10))
        history_videos = history_videos or []
        burned_block = cls.burned_topic_directive(history_videos, limit=5)
        winning_block = cls.winning_topic_directive(history_videos, limit=5)
        prompt = f"""Generate EXACTLY {candidates} first-sentence hooks for a YouTube Short.

Topic: {topic}
Channel niche: {niche}
Language: {language}
{burned_block}{winning_block}
Rules:
- Each hook is one spoken sentence, 8 to 12 words.
- Make it concrete, visual, and slightly unsettling.
- No generic openers: "Sabias que", "En este video", "Hoy vamos", "Descubre", "Acompaname", or welcome language.
- The hook must create one immediate question: danger, contradiction, impossible scale, hidden force, or visible consequence.
- Write every hook in {language}.
- Return only the hooks, one per line. No numbering, bullets, quotes, markdown, or explanations."""
        try:
            raw = generate_response(prompt) or ""
        except Exception:
            raw = ""

        hooks = cls._parse_lines(raw)
        scored = [
            cls.score_hook(hook, topic=topic, niche=niche, language=language)
            for hook in hooks
        ]
        scored = [item for item in scored if item["hook"]]
        scored.sort(key=lambda item: item["score"], reverse=True)
        best = scored[0] if scored else cls.score_hook("", topic, niche, language)
        report = {
            "best_hook": best.get("hook", ""),
            "best_score": best.get("score", 0),
            "accepted": best.get("score", 0) >= cls.HOOK_SCORE_THRESHOLD,
            "candidates": scored[:candidates],
            "candidate_count": len(scored),
        }
        return best.get("hook", ""), report

    @classmethod
    def score_hook(
        cls,
        hook: str,
        topic: str = "",
        niche: str = "",
        language: str = "",
    ) -> dict[str, Any]:
        clean = cls._clean_line(hook)
        normalized = cls.normalize(clean)
        words = cls._words(clean)
        topic_tokens = cls._keywords(topic, limit=6)
        score = 0.0
        issues: list[str] = []

        if not clean:
            return {"hook": "", "score": 0.0, "issues": ["empty hook"], "metrics": {}}
        if 8 <= len(words) <= 12:
            score += 2.4
        elif 7 <= len(words) <= 14:
            score += 1.2
            issues.append("hook length is slightly outside the ideal range")
        else:
            issues.append("hook length is outside the ideal range")

        if any(opener in normalized for opener in MaxRetentionEngine.BANNED_OPENERS):
            score -= 2.5
            issues.append("generic opener")
        else:
            score += 1.4

        reveal_hits = sum(1 for term in MaxRetentionEngine.REVELATION_TERMS if term in normalized)
        visual_hits = sum(1 for term in MaxRetentionEngine.VISUAL_TERMS if term in normalized)
        tension_hits = sum(
            1 for term in (
                "rompe", "devora", "oculta", "arranca", "dobla", "borra",
                "amenaza", "imposible", "invisible", "prohibido", "silencio",
                "nunca", "nadie", "extrano", "peligro", "muerto",
            )
            if term in normalized
        )
        score += min(2.0, visual_hits * 0.55)
        score += min(2.0, (reveal_hits + tension_hits) * 0.5)
        if topic_tokens and any(token in normalized for token in topic_tokens[:4]):
            score += 1.2
        elif topic_tokens:
            issues.append("hook does not clearly name the topic")
        if clean.endswith("?") or any(term in normalized for term in ("pero", "nadie", "nunca", "por eso")):
            score += 1.0

        return {
            "hook": clean,
            "score": round(max(0.0, min(10.0, score)), 1),
            "issues": issues,
            "metrics": {
                "words": len(words),
                "reveal_hits": reveal_hits,
                "visual_hits": visual_hits,
                "tension_hits": tension_hits,
            },
            "topic": topic,
            "niche": niche,
            "language": language,
        }

    @classmethod
    def build_visual_beat_map(
        cls,
        sections: list[str],
        topic: str,
        niche: str,
        language: str,
        generate_response: Callable[[str], str],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        n = len(sections)
        if n <= 0:
            return [], {"accepted": False, "reason": "no sections"}
        sections_block = "\n".join(
            f"{idx + 1}. {section}" for idx, section in enumerate(sections)
        )
        prompt = f"""Create a Visual Beat Map for a YouTube Short image generator.

Topic: {topic}
Niche: {niche}
Narration language: {language}

Script sections:
{sections_block}

Return EXACTLY {n} JSON objects in a JSON array.
Each object must contain:
- beat: 2-4 word label, e.g. "scroll stopper", "hidden force", "scale jump", "payoff".
- visual_goal: one short sentence saying what the viewer must instantly understand.
- must_show: 3 concrete visible nouns or named objects, comma-separated.
- motion: one verb phrase showing what changes or threatens to change.
- avoid: 2 things to avoid, especially generic wallpaper or repeated scenes.

Rules:
- Beat 1 must be the scroll-stopper image for the first sentence.
- Every beat must be visually different from the previous one.
- Show visible consequences of invisible forces.
- No markdown. Return only valid JSON."""
        try:
            raw = generate_response(prompt) or ""
        except Exception:
            raw = ""
        beats = cls._parse_json_list(raw)
        accepted = len(beats) >= n and all(isinstance(beats[idx], dict) for idx in range(n))
        shaped = cls._shape_beats(beats, sections, topic) if accepted else cls._fallback_beats(sections, topic)
        report = {
            "accepted": accepted,
            "count": len(shaped),
            "fallback": not accepted,
        }
        return shaped, report

    @classmethod
    def visual_beat_block(cls, beats: list[dict[str, Any]]) -> str:
        if not beats:
            return ""
        lines = []
        for idx, beat in enumerate(beats, start=1):
            must = beat.get("must_show") or []
            if isinstance(must, list):
                must_text = ", ".join(str(x) for x in must[:4])
            else:
                must_text = str(must)
            lines.append(
                f"BEAT {idx} - {beat.get('beat', 'visual beat')}: "
                f"{beat.get('visual_goal', '')} Must show: {must_text}. "
                f"Motion: {beat.get('motion', '')}. Avoid: {beat.get('avoid', '')}."
            )
        return "\n\nMAXIMA RETENCION VISUAL BEAT MAP:\n" + "\n".join(lines) + "\n"

    @classmethod
    def score_image_prompt(cls, prompt: str, topic: str = "", first_image: bool = False) -> dict[str, Any]:
        normalized = cls.normalize(prompt)
        words = cls._words(prompt)
        topic_tokens = cls._keywords(topic, limit=6)
        generic_terms = (
            "space", "cosmic", "universe", "stars", "starfield", "galaxy",
            "nebula", "background", "wallpaper", "beautiful", "glowing",
        )
        action_terms = (
            "bends", "breaks", "burns", "falls", "drifts", "cracks", "erupts",
            "collides", "tears", "reveals", "hides", "approaches", "escapes",
            "swirls", "cuts", "pierces", "illuminates", "fractures",
        )
        generic_hits = sum(1 for term in generic_terms if term in normalized)
        action_hits = sum(1 for term in action_terms if term in normalized)
        topic_hits = sum(1 for token in topic_tokens[:4] if token in normalized)
        comma_density = prompt.count(",")
        score = 2.0
        score += min(2.0, action_hits * 0.7)
        score += min(1.5, comma_density * 0.25)
        score += 1.5 if topic_hits else 0.0
        score += 1.0 if 35 <= len(words) <= 75 else 0.4
        score -= min(2.2, generic_hits * 0.35)
        if first_image:
            score += 1.2 if action_hits and topic_hits else -0.6
        issues = []
        if not topic_hits:
            issues.append("does not clearly anchor the topic")
        if action_hits == 0:
            issues.append("lacks a visible action or change")
        if generic_hits >= 4:
            issues.append("leans on generic cosmic wallpaper terms")
        return {
            "score": round(max(0.0, min(10.0, score)), 1),
            "issues": issues,
            "generic_hits": generic_hits,
            "action_hits": action_hits,
            "topic_hits": topic_hits,
        }

    @classmethod
    def score_short_script(
        cls,
        script: str,
        topic: str = "",
        niche: str = "",
        language: str = "",
        retention_mode: str = "",
    ) -> dict[str, Any]:
        sentences = cls._sentences(script)
        words = cls._words(script)
        first_sentence = sentences[0] if sentences else ""
        first_words = cls._words(first_sentence)
        avg_sentence_words = len(words) / max(1, len(sentences))
        normalized_text = cls.normalize(script)
        normalized_first = cls.normalize(first_sentence)
        score = MaxRetentionEngine.score_script(script)

        issues: list[str] = []
        strengths: list[str] = []

        if not sentences:
            issues.append("Script is empty or has no sentence boundaries.")
        if first_sentence:
            if len(first_words) < 7:
                issues.append("Opening sentence is too short to create a clear promise.")
            elif len(first_words) > 13:
                issues.append("Opening sentence is too long for the first swipe moment.")
            else:
                strengths.append("Opening sentence has a strong mobile length.")
            if any(opener in normalized_first for opener in MaxRetentionEngine.BANNED_OPENERS):
                issues.append("Opening uses a banned generic opener.")
            else:
                strengths.append("Opening avoids generic intro language.")

        reveal_hits = sum(1 for term in MaxRetentionEngine.REVELATION_TERMS if term in normalized_text)
        visual_hits = sum(1 for term in MaxRetentionEngine.VISUAL_TERMS if term in normalized_text)
        if reveal_hits < max(2, len(sentences) // 4):
            issues.append("Not enough mini-reveals or turns across the script.")
        else:
            strengths.append("Script has repeated curiosity turns.")
        if visual_hits < max(2, len(sentences) // 5):
            issues.append("Narration needs more concrete visual anchors.")
        else:
            strengths.append("Narration contains concrete visual cues.")
        if avg_sentence_words > 20:
            issues.append("Average sentence length is too high for Shorts pacing.")
            score -= 0.6
        elif avg_sentence_words <= 17:
            strengths.append("Pacing is tight enough for fast captions.")

        topic_tokens = cls._keywords(topic, limit=6)
        if topic_tokens and not any(tok in normalized_text for tok in topic_tokens[:4]):
            issues.append("Script drifts away from the selected topic.")
            score -= 0.8

        score = round(max(0.0, min(10.0, score)), 1)
        label = "ready" if score >= cls.SCORE_THRESHOLD and not issues[:1] else "risky"
        if score < 6.5:
            label = "weak"
        return {
            "score": score,
            "label": label,
            "issues": issues,
            "strengths": strengths[:5],
            "first_sentence": first_sentence,
            "metrics": {
                "sentences": len(sentences),
                "words": len(words),
                "first_sentence_words": len(first_words),
                "avg_sentence_words": round(avg_sentence_words, 1),
                "reveal_hits": reveal_hits,
                "visual_hits": visual_hits,
            },
            "topic": topic,
            "niche": niche,
            "language": language,
            "retention_mode": retention_mode,
        }

    @classmethod
    def enforce_pre_render_score(
        cls,
        script: str,
        topic: str,
        niche: str,
        language: str,
        sentence_length: int,
        generate_response: Callable[[str], str],
        target_words: int | None = None,
        threshold: float | None = None,
        max_attempts: int = 2,
    ) -> tuple[str, dict[str, Any]]:
        threshold = float(threshold or cls.SCORE_THRESHOLD)
        best_script = (script or "").strip()
        initial_report = cls.score_short_script(best_script, topic, niche, language, "maxima_retencion")
        best_report = dict(initial_report)
        attempts = 0

        if best_report["score"] < threshold:
            for _ in range(max(0, int(max_attempts))):
                attempts += 1
                issue_block = "\n".join(f"- {i}" for i in (best_report.get("issues") or []))
                target_clause = (
                    f"- Aim for about {target_words} spoken words total, plus or minus ten percent.\n"
                    if target_words else ""
                )
                prompt = f"""Rewrite this YouTube Short narration before render.

Topic: {topic}
Channel niche: {niche}
Language: {language}
Current retention score: {best_report['score']}/10
Minimum score required: {threshold}/10

Problems to fix:
{issue_block or "- Make the hook, visual beats, and reveals stronger."}

Rules:
- Keep EXACTLY {sentence_length} sentences.
{target_clause}- Sentence one must be 8 to 12 words, visual, direct, and unsettling.
- No generic openers like "Sabias que", "En este video", "Hoy vamos", "Descubre", or welcome language.
- Add a small reveal, contrast, or consequence every two sentences.
- Use concrete visible images, not abstract textbook labels.
- Keep the final sentence short and loopable.
{NarrationVoice.rewrite_guardrail(language)}
- Return ONLY the narration. No markdown, title, bullets, or stage directions.

Current narration:
\"\"\"
{best_script}
\"\"\""""
                try:
                    candidate = cls._clean_script(generate_response(prompt) or "")
                except Exception:
                    continue
                if not candidate:
                    continue
                if sentence_length and len(cls._sentences(candidate)) != int(sentence_length):
                    continue
                candidate_report = cls.score_short_script(
                    candidate,
                    topic,
                    niche,
                    language,
                    "maxima_retencion",
                )
                if candidate_report["score"] > best_report["score"] + 0.05:
                    best_script = candidate
                    best_report = candidate_report
                if best_report["score"] >= threshold:
                    break

        final_report = dict(best_report)
        final_report.update({
            "initial_score": initial_report["score"],
            "final_score": best_report["score"],
            "threshold": threshold,
            "attempts": attempts,
            "rewritten": best_script.strip() != (script or "").strip(),
            "accepted": best_report["score"] >= threshold,
            "initial_issues": initial_report.get("issues", []),
        })
        return best_script, final_report

    @classmethod
    def build_retention_plan(
        cls,
        script: str,
        topic: str = "",
        niche: str = "",
        language: str = "",
        retention_mode: str = "",
        video_path: str = "",
        retention_preflight: dict[str, Any] | None = None,
        retention_hook_lab: dict[str, Any] | None = None,
        visual_beat_map: list[dict[str, Any]] | None = None,
        visual_beat_report: dict[str, Any] | None = None,
        visual_preflight: dict[str, Any] | None = None,
        history_videos: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build the Retencion Pro package stored next to generated Shorts."""
        clean_script = cls._clean_script(script)
        sentences = cls._sentences(clean_script)
        preflight = retention_preflight if isinstance(retention_preflight, dict) else {}
        hook_lab = retention_hook_lab if isinstance(retention_hook_lab, dict) else {}
        beat_map = visual_beat_map if isinstance(visual_beat_map, list) else []
        beat_report = visual_beat_report if isinstance(visual_beat_report, dict) else {}
        first_image = visual_preflight if isinstance(visual_preflight, dict) else {}

        score_report = preflight or cls.score_short_script(
            clean_script,
            topic=topic,
            niche=niche,
            language=language,
            retention_mode=retention_mode,
        )
        pre_score = cls._score_value(score_report, "final_score", "score", "initial_score")
        best_hook = cls._clean_line(str(hook_lab.get("best_hook") or (sentences[0] if sentences else "")))
        hook_score = cls._score_value(hook_lab, "best_score", "score")
        if not hook_score and best_hook:
            hook_score = float(cls.score_hook(best_hook, topic, niche, language).get("score") or 0)

        intro_guard = cls._intro_guard(sentences, topic)
        micro_hooks = cls._micro_hooks(sentences, topic)
        filler = cls._filler_compression(clean_script, sentences)
        visual_pacing = cls._visual_pacing(sentences, beat_map, beat_report, first_image)
        loop_ending = cls._loop_ending(sentences, topic)
        hot_words = cls.hot_words(clean_script, topic, limit=18)
        ab_tests = cls._hook_ab_tests(
            hook_lab,
            first_sentence=sentences[0] if sentences else "",
            topic=topic,
            niche=niche,
            language=language,
        )
        analytics = cls._analytics_feedback(history_videos or [], niche=niche, language=language)

        status_weights = {
            "pass": 1.0,
            "ready": 1.0,
            "warn": 0.55,
            "risky": 0.45,
            "fail": 0.0,
            "weak": 0.0,
        }
        component_scores = [
            pre_score,
            hook_score,
            10.0 * status_weights.get(intro_guard.get("status", ""), 0.5),
            10.0 * status_weights.get(filler.get("status", ""), 0.5),
            10.0 * status_weights.get(visual_pacing.get("status", ""), 0.5),
            10.0 * status_weights.get(loop_ending.get("status", ""), 0.5),
        ]
        overall = round(sum(component_scores) / max(1, len(component_scores)), 1)
        if overall >= 8.0:
            status = "pass"
        elif overall >= 6.5:
            status = "warn"
        else:
            status = "fail"

        return {
            "version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "status": status,
            "overall_score": overall,
            "retention_mode": retention_mode,
            "video_path": video_path,
            "topic": topic,
            "niche": niche,
            "language": language,
            "hook_0_3s": {
                "status": "pass" if hook_score >= cls.HOOK_SCORE_THRESHOLD else "warn",
                "text": best_hook,
                "score": round(float(hook_score or 0), 1),
                "first_3s_pattern": ["0.0s shock frame", "0.8s visible consequence", "2.0s unresolved question"],
            },
            "intro_guard": intro_guard,
            "micro_hooks": micro_hooks,
            "filler_compression": filler,
            "visual_pacing": visual_pacing,
            "loop_ending": loop_ending,
            "hot_words": hot_words,
            "pre_render_score": score_report,
            "hook_ab_tests": ab_tests,
            "analytics_feedback": analytics,
            "platform_focus": {
                "youtube": "strong first sentence plus searchable metadata",
                "tiktok": "fast hook, hot words, and loopable ending",
                "facebook": "clear topic promise and short caption",
            },
        }

    @classmethod
    def persist_retention_plan(cls, video_path: str, plan: dict[str, Any]) -> None:
        if not video_path or not plan:
            return
        sidecar_path = os.path.splitext(video_path)[0] + ".meta.json"
        manifest_path = os.path.splitext(video_path)[0] + ".manifest.json"
        sidecar = cls._read_json(sidecar_path) or {}
        sidecar["retention_plan"] = plan
        cls._write_json(sidecar_path, sidecar)

        manifest = cls._read_json(manifest_path) or {}
        manifest["retention_plan"] = cls.compact_retention_plan(plan)
        cls._write_json(manifest_path, manifest)

    @staticmethod
    def compact_retention_plan(plan: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(plan, dict):
            return {}
        analytics = plan.get("analytics_feedback") if isinstance(plan.get("analytics_feedback"), dict) else {}
        return {
            "version": plan.get("version"),
            "generated_at": plan.get("generated_at"),
            "status": plan.get("status"),
            "score": plan.get("overall_score"),
            "hook": (plan.get("hook_0_3s") or {}).get("text"),
            "hook_score": (plan.get("hook_0_3s") or {}).get("score"),
            "intro_status": (plan.get("intro_guard") or {}).get("status"),
            "loop_status": (plan.get("loop_ending") or {}).get("status"),
            "hot_words": (plan.get("hot_words") or [])[:8],
            "micro_hooks_count": len(plan.get("micro_hooks") or []),
            "visual_status": (plan.get("visual_pacing") or {}).get("status"),
            "analytics": {
                "winning_terms": [x.get("term") for x in (analytics.get("winning_terms") or [])[:3] if x.get("term")],
                "burned_terms": [x.get("term") for x in (analytics.get("burned_terms") or [])[:3] if x.get("term")],
            },
        }

    @classmethod
    def hot_words(cls, script: str, topic: str = "", limit: int = 18) -> list[str]:
        normalized = cls.normalize(f"{topic} {script}")
        seeds = (
            "devora", "rompe", "quema", "traga", "borra", "explota", "oculta",
            "secreto", "nunca", "nadie", "imposible", "peligro", "muerto",
            "invisible", "prohibido", "colapso", "amenaza", "desaparece",
            "seconds", "secret", "never", "impossible", "danger", "hidden",
            "collapse", "vanishes", "burns", "breaks",
        )
        out: list[str] = []
        seen: set[str] = set()
        for term in list(MaxRetentionEngine.REVELATION_TERMS) + list(MaxRetentionEngine.VISUAL_TERMS) + list(seeds):
            clean = cls.normalize(term)
            if clean and clean in normalized and clean not in seen:
                out.append(clean)
                seen.add(clean)
            if len(out) >= limit:
                return out
        for token in cls._keywords(topic, limit=8) + cls._keywords(script, limit=60):
            if token not in seen:
                out.append(token)
                seen.add(token)
            if len(out) >= limit:
                break
        return out

    @classmethod
    def _intro_guard(cls, sentences: list[str], topic: str) -> dict[str, Any]:
        first = sentences[0] if sentences else ""
        normalized = cls.normalize(first)
        words = cls._words(first)
        issues: list[str] = []
        strengths: list[str] = []
        if not first:
            issues.append("missing opening sentence")
        if any(opener in normalized for opener in MaxRetentionEngine.BANNED_OPENERS):
            issues.append("generic opener detected")
        else:
            strengths.append("no generic intro")
        if first and not (7 <= len(words) <= 13):
            issues.append("opening is outside the 7-13 word swipe window")
        elif first:
            strengths.append("opening has mobile-safe length")
        topic_tokens = cls._keywords(topic, limit=5)
        if topic_tokens and not any(token in normalized for token in topic_tokens[:3]):
            issues.append("opening does not name the core topic")
        tension_hits = sum(
            1 for term in (
                "pero", "nunca", "nadie", "imposible", "secreto", "rompe",
                "devora", "traga", "oculta", "peligro", "colapso",
            )
            if term in normalized
        )
        if tension_hits:
            strengths.append("opening creates tension")
        else:
            issues.append("opening needs a sharper tension word")
        if not issues:
            status = "pass"
        elif len(issues) <= 2:
            status = "warn"
        else:
            status = "fail"
        return {
            "status": status,
            "first_sentence": first,
            "word_count": len(words),
            "issues": issues,
            "strengths": strengths,
        }

    @classmethod
    def _micro_hooks(cls, sentences: list[str], topic: str) -> list[dict[str, Any]]:
        if len(sentences) <= 2:
            return []
        topic_tokens = cls._keywords(topic, limit=4)
        topic_hint = topic_tokens[0] if topic_tokens else "esto"
        hooks: list[dict[str, Any]] = []
        for idx in range(1, len(sentences), 2):
            sentence = sentences[idx]
            normalized = cls.normalize(sentence)
            if any(term in normalized for term in ("pero", "entonces", "nadie", "nunca", "por eso")):
                text = cls._clean_line(sentence)
            else:
                text = f"Pero aqui {topic_hint} cambia de forma."
            hooks.append({
                "after_sentence": idx,
                "approx_second": 3 + ((idx + 1) // 2) * 6,
                "text": cls._shorten(text, 92),
                "purpose": "reset attention with a small reveal",
            })
        return hooks[:8]

    @classmethod
    def _filler_compression(cls, script: str, sentences: list[str]) -> dict[str, Any]:
        normalized = cls.normalize(script)
        words = cls._words(script)
        avg_sentence_words = round(len(words) / max(1, len(sentences)), 1)
        fillers = (
            "basicamente", "simplemente", "realmente", "literalmente",
            "cosas", "algo", "interesante", "muy importante", "en realidad",
            "podria", "puede ser", "de alguna manera",
        )
        hits = []
        for term in fillers:
            count = normalized.count(term)
            if count:
                hits.append({"term": term, "count": count})
        long_sentences = [
            {"sentence": idx + 1, "words": len(cls._words(sentence)), "text": cls._shorten(sentence, 120)}
            for idx, sentence in enumerate(sentences)
            if len(cls._words(sentence)) > 20
        ][:5]
        allowed_hits = max(1, len(words) // 90)
        status = "pass" if len(hits) <= allowed_hits and avg_sentence_words <= 18.5 else "warn"
        if avg_sentence_words > 23 or len(hits) > allowed_hits + 3:
            status = "fail"
        return {
            "status": status,
            "filler_hits": hits,
            "avg_sentence_words": avg_sentence_words,
            "long_sentence_targets": long_sentences,
            "recommendation": "cut filler and split long sentences before render" if status != "pass" else "pacing is tight",
        }

    @classmethod
    def _visual_pacing(
        cls,
        sentences: list[str],
        beat_map: list[dict[str, Any]],
        beat_report: dict[str, Any],
        visual_preflight: dict[str, Any],
    ) -> dict[str, Any]:
        beat_count = len(beat_map)
        sentence_count = len(sentences)
        target_beats = max(3, min(8, (sentence_count + 1) // 2))
        first_score = cls._score_value(visual_preflight, "score")
        status = "pass" if beat_count >= target_beats and (not first_score or first_score >= 7.0) else "warn"
        if beat_count < max(2, target_beats - 2):
            status = "fail"
        return {
            "status": status,
            "beat_count": beat_count,
            "target_beats": target_beats,
            "fallback": bool(beat_report.get("fallback")),
            "first_image_score": first_score,
            "target_scene_seconds": 2.5,
            "beats": [
                {
                    "beat": item.get("beat"),
                    "visual_goal": item.get("visual_goal"),
                    "motion": item.get("motion"),
                }
                for item in beat_map[:8]
                if isinstance(item, dict)
            ],
        }

    @classmethod
    def _loop_ending(cls, sentences: list[str], topic: str) -> dict[str, Any]:
        if not sentences:
            return {"status": "fail", "last_sentence": "", "reason": "missing script"}
        first = sentences[0]
        last = sentences[-1]
        normalized_first = cls.normalize(first)
        normalized_last = cls.normalize(last)
        topic_tokens = cls._keywords(topic, limit=5)
        overlap = [
            token for token in topic_tokens
            if token in normalized_first and token in normalized_last
        ]
        last_words = len(cls._words(last))
        loop_terms = ("por eso", "ahora", "vuelve", "otra vez", "primer", "mismo")
        has_loop_term = any(term in normalized_last for term in loop_terms)
        status = "pass" if (overlap or has_loop_term) and last_words <= 15 else "warn"
        if last_words > 22:
            status = "fail"
        return {
            "status": status,
            "last_sentence": last,
            "word_count": last_words,
            "topic_overlap": overlap,
            "loop_term": has_loop_term,
            "rewrite_hint": "" if status == "pass" else "make the last sentence shorter and echo the first threat",
        }

    @classmethod
    def _hook_ab_tests(
        cls,
        hook_lab: dict[str, Any],
        first_sentence: str,
        topic: str,
        niche: str,
        language: str,
    ) -> list[dict[str, Any]]:
        candidates: list[str] = []
        for item in hook_lab.get("candidates") or []:
            if isinstance(item, dict) and item.get("hook"):
                candidates.append(str(item["hook"]))
        if first_sentence:
            candidates.append(first_sentence)
        clean_topic = cls._shorten(topic, 42) or "esto"
        if "en" in cls.normalize(language) and "espan" not in cls.normalize(language):
            fallback = [
                f"{clean_topic} changes in the first second.",
                f"The smallest detail makes {clean_topic} impossible.",
                f"This is why {clean_topic} starts to break.",
            ]
        else:
            fallback = [
                f"{clean_topic} cambia en el primer segundo.",
                f"El detalle mas pequeno vuelve imposible a {clean_topic}.",
                f"Por esto {clean_topic} empieza a romperse.",
            ]
        candidates.extend(fallback)
        scored = []
        seen: set[str] = set()
        for hook in candidates:
            clean = cls._clean_line(hook)
            key = cls.normalize(clean)
            if not clean or key in seen:
                continue
            seen.add(key)
            report = cls.score_hook(clean, topic=topic, niche=niche, language=language)
            scored.append({
                "variant": chr(65 + min(len(scored), 25)),
                "hook": report.get("hook"),
                "score": report.get("score"),
                "issues": report.get("issues", []),
            })
            if len(scored) >= 4:
                break
        return scored

    @classmethod
    def _analytics_feedback(
        cls,
        history_videos: list[dict[str, Any]],
        niche: str = "",
        language: str = "",
    ) -> dict[str, Any]:
        if not history_videos:
            return {
                "status": "empty",
                "stats": {"shorts": 0, "known_views": 0, "winners": 0, "weak": 0},
                "winning_terms": [],
                "burned_terms": [],
                "recommendations": ["No local analytics yet; publish variants and sync views."],
            }
        analysis = cls.analyze_channel({
            "id": "",
            "nickname": "",
            "niche": niche,
            "language": language,
            "videos": history_videos,
        })
        return {
            "status": "ready" if analysis["stats"]["known_views"] else "needs_views",
            "stats": analysis["stats"],
            "winning_terms": analysis.get("winning_terms", [])[:6],
            "burned_terms": analysis.get("burned_topics", [])[:6],
            "recommendations": analysis.get("recommendations", [])[:4],
        }

    @staticmethod
    def _score_value(data: dict[str, Any], *keys: str) -> float:
        if not isinstance(data, dict):
            return 0.0
        for key in keys:
            value = data.get(key)
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                continue
        return 0.0

    @staticmethod
    def _shorten(text: str, limit: int) -> str:
        clean = re.sub(r"\s+", " ", text or "").strip()
        if len(clean) <= limit:
            return clean
        return clean[: max(1, limit - 3)].rstrip() + "..."

    @staticmethod
    def _read_json(path: str) -> dict[str, Any] | None:
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    @staticmethod
    def _write_json(path: str, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)

    @classmethod
    def _recommendations(cls, stats: dict[str, Any], term_stats: dict[str, Any]) -> list[str]:
        recs: list[str] = []
        if stats["unknown_views"]:
            recs.append("Sincroniza metricas para leer el patron completo de los Shorts.")
        if stats["known_views"] and stats["weak"] >= max(2, stats["winners"]):
            recs.append("Usa MAXIMA RETENCION y preview de guion antes de renderizar.")
        if term_stats["burned"]:
            first = term_stats["burned"][0]["term"]
            recs.append(f"Evita repetir '{first}' hasta probar un angulo mas concreto.")
        if term_stats["winning"]:
            first = term_stats["winning"][0]["term"]
            recs.append(f"Replica el patron ganador alrededor de '{first}', cambiando el objeto visual.")
        if not recs:
            recs.append("Aun no hay suficiente historial con vistas para detectar patrones fuertes.")
        return recs

    @classmethod
    def _term_stats(cls, videos: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "views": [],
            "examples": [],
            "winner_count": 0,
            "weak_count": 0,
            "latest_date": "",
            "latest_views": None,
        })
        for video in videos:
            views = video.get("views")
            if views is None:
                continue
            terms = cls._terms_for_video(video)
            for term in terms:
                bucket = buckets[term]
                bucket["views"].append(views)
                if len(bucket["examples"]) < 3:
                    bucket["examples"].append(video["title"] or video["subject"])
                if views >= cls.WINNER_VIEWS:
                    bucket["winner_count"] += 1
                if views < cls.WEAK_VIEWS:
                    bucket["weak_count"] += 1
                if (video.get("date") or "") >= bucket["latest_date"]:
                    bucket["latest_date"] = video.get("date") or ""
                    bucket["latest_views"] = views

        burned: list[dict[str, Any]] = []
        winning: list[dict[str, Any]] = []
        for term, bucket in buckets.items():
            views = bucket["views"]
            if len(views) < 2:
                continue
            avg_views = round(sum(views) / len(views), 1)
            item = {
                "term": term,
                "count": len(views),
                "avg_views": avg_views,
                "latest_views": bucket["latest_views"],
                "winner_count": bucket["winner_count"],
                "weak_count": bucket["weak_count"],
                "examples": bucket["examples"],
            }
            if bucket["weak_count"] >= 2 or (avg_views < 300 and len(views) >= 2):
                item["reason"] = "repeated low-view pattern"
                burned.append(item)
            if bucket["winner_count"] >= 1 and avg_views >= cls.WINNER_VIEWS:
                winning.append(item)

        burned.sort(key=lambda item: (item["weak_count"], -item["avg_views"]), reverse=True)
        winning.sort(key=lambda item: (item["avg_views"], item["winner_count"]), reverse=True)
        return {"burned": burned, "winning": winning}

    @classmethod
    def _terms_for_video(cls, video: dict[str, Any]) -> set[str]:
        text = f"{video.get('subject') or ''} {video.get('title') or ''}"
        tokens = cls._keywords(text, limit=10)
        terms = set(tokens[:6])
        for i in range(max(0, len(tokens) - 1)):
            terms.add(f"{tokens[i]} {tokens[i + 1]}")
        return {term for term in terms if len(term) >= 4}

    @classmethod
    def _shape_video(cls, video: dict[str, Any]) -> dict[str, Any]:
        views = cls._views(video)
        return {
            "title": video.get("title", "") or "",
            "subject": video.get("subject", "") or "",
            "url": video.get("url", "") or "",
            "date": video.get("date", "") or "",
            "views": views,
            "likes": cls._number_or_none(video.get("like_count")),
            "comments": cls._number_or_none(video.get("comment_count")),
            "stats_synced_at": video.get("stats_synced_at", "") or "",
            "performance": cls._performance(views),
        }

    @classmethod
    def _performance(cls, views: int | None) -> str:
        if views is None:
            return "unknown"
        if views >= cls.WINNER_VIEWS:
            return "winner"
        if views < cls.WEAK_VIEWS:
            return "weak"
        return "normal"

    @staticmethod
    def _is_short(video: dict[str, Any]) -> bool:
        if "is_short" in video:
            return bool(video.get("is_short"))
        text = f"{video.get('title') or ''} {video.get('description') or ''} {video.get('url') or ''}".lower()
        return "#short" in text or "/shorts/" in text

    @classmethod
    def _views(cls, video: dict[str, Any]) -> int | None:
        return cls._number_or_none(video.get("view_count"))

    @staticmethod
    def _number_or_none(value: Any) -> int | None:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number >= 0 else None

    @staticmethod
    def _median(values: list[int]) -> float:
        if not values:
            return 0
        mid = len(values) // 2
        if len(values) % 2:
            return float(values[mid])
        return round((values[mid - 1] + values[mid]) / 2, 1)

    @classmethod
    def _keywords(cls, text: str, limit: int = 12) -> list[str]:
        normalized = cls.normalize(text)
        tokens = [
            tok for tok in re.findall(r"[a-z0-9]+", normalized)
            if len(tok) > 2 and not tok.isdigit() and tok not in cls.STOPWORDS
        ]
        out: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            if token in seen:
                continue
            seen.add(token)
            out.append(token)
            if len(out) >= limit:
                break
        return out

    @classmethod
    def _parse_lines(cls, text: str) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        for line in (text or "").splitlines():
            clean = cls._clean_line(line)
            if not clean:
                continue
            key = cls.normalize(clean)
            if key in seen:
                continue
            seen.add(key)
            lines.append(clean)
        return lines

    @staticmethod
    def _clean_line(text: str) -> str:
        text = re.sub(r"^[\s\-\*\d\.\)\:]+", "", text or "").strip()
        text = text.strip("\"'")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _parse_json_list(text: str) -> list[Any]:
        clean = (text or "").replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(clean)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            match = re.search(r"\[.*\]", clean, re.DOTALL)
            if not match:
                return []
            try:
                parsed = json.loads(match.group())
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []

    @classmethod
    def _shape_beats(
        cls,
        beats: list[Any],
        sections: list[str],
        topic: str,
    ) -> list[dict[str, Any]]:
        shaped: list[dict[str, Any]] = []
        for idx, section in enumerate(sections):
            raw = beats[idx] if idx < len(beats) else {}
            if not isinstance(raw, dict):
                raw = {}
            must_show = raw.get("must_show") or raw.get("must") or raw.get("objects") or []
            if isinstance(must_show, str):
                must_show = [x.strip() for x in must_show.split(",") if x.strip()]
            if not isinstance(must_show, list):
                must_show = []
            shaped.append({
                "beat": cls._clean_line(str(raw.get("beat") or cls._fallback_beat_label(idx, len(sections)))),
                "section": section,
                "visual_goal": cls._clean_line(str(raw.get("visual_goal") or raw.get("goal") or section)),
                "must_show": [cls._clean_line(str(x)) for x in must_show[:4] if cls._clean_line(str(x))],
                "motion": cls._clean_line(str(raw.get("motion") or raw.get("action") or "visible change")),
                "avoid": cls._clean_line(str(raw.get("avoid") or "generic cosmic wallpaper")),
                "topic": topic,
            })
        return shaped

    @classmethod
    def _fallback_beats(cls, sections: list[str], topic: str) -> list[dict[str, Any]]:
        return [
            {
                "beat": cls._fallback_beat_label(idx, len(sections)),
                "section": section,
                "visual_goal": section,
                "must_show": [topic, "visible consequence", "clear contrast"],
                "motion": "the scene changes in a readable way",
                "avoid": "generic wallpaper, repeated star fields",
                "topic": topic,
            }
            for idx, section in enumerate(sections)
        ]

    @staticmethod
    def _fallback_beat_label(index: int, total: int) -> str:
        labels = [
            "scroll stopper",
            "simple setup",
            "first turn",
            "scale jump",
            "hidden force",
            "visible consequence",
            "final payoff",
        ]
        if total <= 1:
            return labels[0]
        if index == 0:
            return labels[0]
        if index == total - 1:
            return labels[-1]
        mapped = 1 + int((index / max(1, total - 1)) * (len(labels) - 3))
        return labels[max(1, min(len(labels) - 2, mapped))]

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]

    @staticmethod
    def _words(text: str) -> list[str]:
        return re.findall(r"[\w'-]+", text or "", flags=re.UNICODE)

    @staticmethod
    def _clean_script(text: str) -> str:
        text = re.sub(r"```[\s\S]*?```", " ", text or "")
        text = re.sub(r"[*_`#]+", "", text)
        text = re.sub(r"^\s*(?:script|guion|narration)\s*:\s*", "", text, flags=re.I)
        return text.strip().strip("\"'").strip()

    @staticmethod
    def normalize(text: str) -> str:
        text = unicodedata.normalize("NFKD", (text or "").lower())
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = re.sub(r"https?://\S+", " ", text)
        text = re.sub(r"#(\w+)", r"\1", text)
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()
