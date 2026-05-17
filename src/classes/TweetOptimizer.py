import json
import math
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional


MAX_TWEET_CHARS = 260
PROMPT_TARGET_CHARS = 240
DEFAULT_CANDIDATE_COUNT = 8


@dataclass(frozen=True)
class TweetScoreBreakdown:
    favorite: float
    reply: float
    repost: float
    click: float
    dwell: float
    follow_author: float
    negative: float
    duplicate_penalty: float
    total: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class TweetSelection:
    tweet: str
    score: TweetScoreBreakdown
    candidates: tuple[str, ...]


class ViralTweetOptimizer:
    """
    Generate and rank X/Twitter posts using the public x-algorithm shape:
    retrieve multiple candidates, hydrate with local context, filter bad fits,
    score several engagement actions, then select the highest scoring post.
    """

    POSITIVE_WEIGHTS = {
        "favorite": 1.00,
        "reply": 1.35,
        "repost": 1.45,
        "click": 0.45,
        "dwell": 0.95,
        "follow_author": 0.55,
    }
    NEGATIVE_WEIGHT = 2.25
    DUPLICATE_WEIGHT = 1.75

    GENERIC_PHRASES = (
        "in today's world",
        "game changer",
        "changing the game",
        "you won't believe",
        "let's talk about",
        "did you know",
        "unlock your potential",
        "en el mundo actual",
        "cambia las reglas del juego",
        "no vas a creer",
        "hablemos de",
        "sabias que",
        "desbloquea tu potencial",
    )

    ENGAGEMENT_BAIT = (
        "like and retweet",
        "please retweet",
        "follow me",
        "follow for more",
        "smash like",
        "share this",
        "dale like",
        "retuitea",
        "sigueme",
        "seguime",
        "comparte esto",
        "comenta abajo",
    )

    TENSION_MARKERS = (
        "but",
        "yet",
        "instead",
        "because",
        "actually",
        "wrong",
        "mistake",
        "secret",
        "problem",
        "truth",
        "pero",
        "aunque",
        "sin embargo",
        "porque",
        "en realidad",
        "error",
        "secreto",
        "problema",
        "verdad",
        "nadie",
        "nunca",
    )

    UTILITY_MARKERS = (
        "how to",
        "why",
        "lesson",
        "rule",
        "framework",
        "checklist",
        "strategy",
        "if you",
        "cuando",
        "como",
        "por que",
        "leccion",
        "regla",
        "estrategia",
        "si ",
    )

    CONVERSATION_MARKERS = (
        "agree",
        "disagree",
        "what would",
        "which one",
        "your take",
        "change my mind",
        "estas de acuerdo",
        "no estas de acuerdo",
        "que harias",
        "cual",
        "tu opinion",
    )

    @classmethod
    def generate(
        cls,
        topic: str,
        language: str,
        recent_posts: Iterable[str],
        generate_response: Callable[[str], Optional[str]],
    ) -> TweetSelection:
        recent = tuple(p for p in recent_posts if p and p.strip())[-12:]
        prompt = cls.build_prompt(topic=topic, language=language, recent_posts=recent)
        raw = generate_response(prompt) or ""
        candidates = cls.parse_candidates(raw)

        if not candidates:
            fallback_prompt = cls.build_fallback_prompt(topic=topic, language=language)
            fallback_raw = generate_response(fallback_prompt) or raw
            candidates = cls.parse_candidates(fallback_raw)

        cleaned = cls.clean_candidates(candidates)
        if not cleaned:
            fallback = cls.clean_tweet(raw)
            if not fallback:
                empty_score = TweetScoreBreakdown(
                    favorite=0.0,
                    reply=0.0,
                    repost=0.0,
                    click=0.0,
                    dwell=0.0,
                    follow_author=0.0,
                    negative=1.0,
                    duplicate_penalty=0.0,
                    total=-cls.NEGATIVE_WEIGHT,
                    reasons=("generation failed",),
                )
                return TweetSelection("", empty_score, ())
            cleaned = (fallback,)

        scored = [
            (candidate, cls.score_tweet(candidate, topic=topic, recent_posts=recent))
            for candidate in cleaned
        ]
        best_tweet, best_score = max(scored, key=lambda item: item[1].total)
        return TweetSelection(best_tweet, best_score, tuple(candidate for candidate, _ in scored))

    @classmethod
    def build_prompt(
        cls,
        topic: str,
        language: str,
        recent_posts: Iterable[str],
        candidate_count: int = DEFAULT_CANDIDATE_COUNT,
    ) -> str:
        recent = "\n".join(f"- {cls.truncate_at_word(p, 170)}" for p in recent_posts)
        if not recent:
            recent = "- No recent local posts yet."

        return f"""
You are writing X/Twitter posts for an account about: {topic}
Language: {language}

Use the public x-algorithm architecture as strategy:
- Retrieval: create {candidate_count} independent candidate posts from different sub-angles of the topic.
- Hydration: adapt to the account topic and avoid repeating recent local posts.
- Scoring: maximize predicted favorite, reply, repost, share/copy-link, dwell, profile-click, and follow-author.
- Filtering: avoid duplicate ideas, old/generic takes, engagement bait, spam, rage bait,
  muted-keyword style phrasing, unsafe claims, and anything likely to trigger not-interested,
  mute, block, or report.
- Selection mindset: each candidate must stand alone; do not rely on the other candidates for context.

Recent local posts to avoid repeating:
{recent}

Write candidates that feel native to X:
- one sharp idea, not a blog intro
- concrete detail in the first 70 characters
- useful tension, contrarian angle, or surprising implication
- optionally a real question that invites thoughtful replies, never a generic "thoughts?"
- no markdown, no numbering inside the tweet, no emojis, no more than one hashtag,
  no URLs unless the topic absolutely requires it
- keep every tweet under {PROMPT_TARGET_CHARS} characters

Return strict JSON only:
{{
  "candidates": [
    {{"tweet": "...", "strategy": "why this should earn replies/reposts/dwell"}}
  ]
}}
""".strip()

    @classmethod
    def build_fallback_prompt(cls, topic: str, language: str) -> str:
        return (
            f"Write one strong X/Twitter post in {language} about {topic}. "
            f"Make it concrete, conversation-worthy, under {PROMPT_TARGET_CHARS} chars, "
            "with no markdown, no URL, no engagement bait, and no more than one hashtag."
        )

    @classmethod
    def parse_candidates(cls, raw: str) -> tuple[str, ...]:
        text = (raw or "").strip()
        if not text:
            return ()

        parsed = cls._parse_json_candidates(text)
        if parsed:
            return parsed

        lines = []
        for line in text.splitlines():
            cleaned = re.sub(r"^\s*(?:[-*]|\d+[\).:-])\s*", "", line).strip()
            cleaned = re.sub(r"^(?:tweet|post|candidate)\s*[:\-]\s*", "", cleaned, flags=re.I)
            if len(cleaned) >= 20:
                lines.append(cleaned)

        if lines:
            return tuple(lines)

        if len(text) <= MAX_TWEET_CHARS + 40:
            return (text,)

        return ()

    @classmethod
    def _parse_json_candidates(cls, text: str) -> tuple[str, ...]:
        payloads = [text]

        fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.I | re.S)
        if fence:
            payloads.append(fence.group(1).strip())

        first_obj = text.find("{")
        last_obj = text.rfind("}")
        if first_obj != -1 and last_obj > first_obj:
            payloads.append(text[first_obj : last_obj + 1])

        first_list = text.find("[")
        last_list = text.rfind("]")
        if first_list != -1 and last_list > first_list:
            payloads.append(text[first_list : last_list + 1])

        for payload in payloads:
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue

            candidates = cls._candidate_texts_from_json(data)
            if candidates:
                return tuple(candidates)

        return ()

    @classmethod
    def _candidate_texts_from_json(cls, data) -> list[str]:
        if isinstance(data, dict):
            for key in ("candidates", "tweets", "posts"):
                if key in data:
                    return cls._candidate_texts_from_json(data[key])
            for key in ("tweet", "post", "text", "content"):
                value = data.get(key)
                if isinstance(value, str):
                    return [value]
            return []

        if isinstance(data, list):
            texts = []
            for item in data:
                texts.extend(cls._candidate_texts_from_json(item))
            return texts

        if isinstance(data, str):
            return [data]

        return []

    @classmethod
    def clean_candidates(cls, candidates: Iterable[str]) -> tuple[str, ...]:
        cleaned = []
        seen = set()
        for candidate in candidates:
            tweet = cls.clean_tweet(candidate)
            key = cls.normalized_key(tweet)
            if not tweet or key in seen:
                continue
            seen.add(key)
            cleaned.append(tweet)
        return tuple(cleaned)

    @classmethod
    def clean_tweet(cls, tweet: str) -> str:
        text = (tweet or "").strip()
        text = re.sub(r"^['\"`]+|['\"`]+$", "", text)
        text = re.sub(r"^(?:tweet|post|candidate)\s*[:\-]\s*", "", text, flags=re.I)
        text = text.replace("*", "")
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip(" \n\"'")
        text = cls.limit_hashtags(text, max_hashtags=1)
        return cls.truncate_at_word(text, MAX_TWEET_CHARS)

    @classmethod
    def score_tweet(
        cls,
        tweet: str,
        topic: str = "",
        recent_posts: Iterable[str] = (),
    ) -> TweetScoreBreakdown:
        text = cls.clean_tweet(tweet)
        lower = cls._fold(text)
        words = re.findall(r"[a-z0-9]+", lower)
        word_count = len(words)
        char_count = len(text)

        length_score = cls._length_score(char_count)
        first_hook = cls._first_hook_score(text)
        specificity = cls._specificity_score(text, words)
        tension = cls._contains_any(lower, cls.TENSION_MARKERS)
        utility = cls._contains_any(lower, cls.UTILITY_MARKERS)
        conversation = cls._conversation_score(text, lower)
        novelty = 1.0 - min(0.75, cls.max_similarity(text, recent_posts))
        topic_fit = cls._topic_fit_score(text, topic)

        favorite = cls._clamp(0.20 + 0.22 * length_score + 0.22 * specificity + 0.18 * topic_fit + 0.18 * novelty)
        reply = cls._clamp(0.12 + 0.45 * conversation + 0.18 * float(tension) + 0.12 * specificity + 0.13 * novelty)
        repost = cls._clamp(
            0.18
            + 0.25 * utility
            + 0.20 * specificity
            + 0.16 * float(tension)
            + 0.13 * first_hook
            + 0.08 * topic_fit
        )
        click = cls._clamp(0.10 + 0.28 * first_hook + 0.22 * float(tension) + 0.18 * specificity + 0.12 * conversation)
        dwell = cls._clamp(0.15 + 0.35 * length_score + 0.20 * first_hook + 0.15 * float(tension) + 0.15 * specificity)
        follow_author = cls._clamp(0.12 + 0.30 * topic_fit + 0.22 * utility + 0.18 * specificity + 0.10 * novelty)

        negative = cls._negative_score(text, lower, word_count)
        duplicate_penalty = max(0.0, cls.max_similarity(text, recent_posts) - 0.34)

        total = (
            favorite * cls.POSITIVE_WEIGHTS["favorite"]
            + reply * cls.POSITIVE_WEIGHTS["reply"]
            + repost * cls.POSITIVE_WEIGHTS["repost"]
            + click * cls.POSITIVE_WEIGHTS["click"]
            + dwell * cls.POSITIVE_WEIGHTS["dwell"]
            + follow_author * cls.POSITIVE_WEIGHTS["follow_author"]
            - negative * cls.NEGATIVE_WEIGHT
            - duplicate_penalty * cls.DUPLICATE_WEIGHT
        )

        reasons = cls._score_reasons(
            text=text,
            specificity=specificity,
            tension=tension,
            conversation=conversation,
            negative=negative,
            duplicate_penalty=duplicate_penalty,
        )

        return TweetScoreBreakdown(
            favorite=favorite,
            reply=reply,
            repost=repost,
            click=click,
            dwell=dwell,
            follow_author=follow_author,
            negative=negative,
            duplicate_penalty=duplicate_penalty,
            total=total,
            reasons=tuple(reasons),
        )

    @classmethod
    def _score_reasons(
        cls,
        text: str,
        specificity: float,
        tension: bool,
        conversation: float,
        negative: float,
        duplicate_penalty: float,
    ) -> list[str]:
        reasons = []
        if cls._first_hook_score(text) > 0.65:
            reasons.append("strong first-line hook")
        if specificity > 0.55:
            reasons.append("specific")
        if tension:
            reasons.append("has tension")
        if conversation > 0.45:
            reasons.append("replyable")
        if negative > 0.30:
            reasons.append("negative-signal risk")
        if duplicate_penalty > 0:
            reasons.append("similar to recent post")
        return reasons

    @staticmethod
    def truncate_at_word(text: str, max_chars: int) -> str:
        text = (text or "").strip()
        if len(text) <= max_chars:
            return text
        cut = text[: max_chars - 3].rsplit(" ", 1)[0].rstrip(".,;:!? ")
        if not cut:
            cut = text[: max_chars - 3].rstrip(".,;:!? ")
        return cut + "..."

    @staticmethod
    def limit_hashtags(text: str, max_hashtags: int = 1) -> str:
        count = 0
        kept = []
        for token in text.split():
            if token.startswith("#"):
                count += 1
                if count > max_hashtags:
                    continue
            kept.append(token)
        return " ".join(kept)

    @classmethod
    def normalized_key(cls, text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", cls._fold(text)))

    @classmethod
    def max_similarity(cls, text: str, others: Iterable[str]) -> float:
        tokens = cls._token_set(text)
        if not tokens:
            return 0.0
        return max((cls._jaccard(tokens, cls._token_set(other)) for other in others), default=0.0)

    @classmethod
    def _length_score(cls, char_count: int) -> float:
        if 80 <= char_count <= 220:
            return 1.0
        if 45 <= char_count < 80:
            return 0.75
        if 220 < char_count <= MAX_TWEET_CHARS:
            return 0.70
        if 25 <= char_count < 45:
            return 0.45
        return 0.20

    @classmethod
    def _first_hook_score(cls, text: str) -> float:
        first = text.strip().split("\n", 1)[0][:85]
        score = 0.15
        if re.search(r"\d", first):
            score += 0.22
        if ":" in first or "?" in first:
            score += 0.18
        if cls._contains_any(cls._fold(first), cls.TENSION_MARKERS):
            score += 0.25
        if len(first) <= 75:
            score += 0.12
        return cls._clamp(score)

    @classmethod
    def _specificity_score(cls, text: str, words: list[str]) -> float:
        score = 0.15
        if re.search(r"\d", text):
            score += 0.22
        if ":" in text or ";" in text:
            score += 0.12
        long_words = [w for w in words if len(w) >= 7]
        if words:
            score += min(0.26, len(long_words) / max(len(words), 1))
        if len(set(words)) >= 10:
            score += 0.15
        if any(len(w) >= 11 for w in words):
            score += 0.10
        return cls._clamp(score)

    @classmethod
    def _conversation_score(cls, text: str, lower: str) -> float:
        score = 0.0
        if "?" in text:
            score += 0.42
        if cls._contains_any(lower, cls.CONVERSATION_MARKERS):
            score += 0.35
        if cls._contains_any(lower, ("vs", "versus", "mejor", "worse", "better", "prefer")):
            score += 0.16
        return cls._clamp(score)

    @classmethod
    def _topic_fit_score(cls, text: str, topic: str) -> float:
        topic_tokens = cls._token_set(topic)
        if not topic_tokens:
            return 0.65
        tweet_tokens = cls._token_set(text)
        overlap = len(topic_tokens & tweet_tokens) / max(len(topic_tokens), 1)
        return cls._clamp(0.45 + overlap * 0.55)

    @classmethod
    def _negative_score(cls, text: str, lower: str, word_count: int) -> float:
        score = 0.0
        if len(text) > MAX_TWEET_CHARS:
            score += 0.45
        if word_count < 5:
            score += 0.35
        if re.search(r"https?://|www\.", lower):
            score += 0.22
        if len(re.findall(r"#\w+", text)) > 1:
            score += 0.20
        if len(re.findall(r"@\w+", text)) > 0:
            score += 0.10
        if text.count("!") > 1:
            score += 0.16
        if cls._all_caps_ratio(text) > 0.22:
            score += 0.18
        if cls._contains_any(lower, cls.GENERIC_PHRASES):
            score += 0.28
        if cls._contains_any(lower, cls.ENGAGEMENT_BAIT):
            score += 0.45
        if lower.count("ai") >= 3 and word_count < 28:
            score += 0.12
        if cls._repeated_word_ratio(lower) > 0.28:
            score += 0.16
        return cls._clamp(score)

    @staticmethod
    def _all_caps_ratio(text: str) -> float:
        letters = [ch for ch in text if ch.isalpha()]
        if not letters:
            return 0.0
        caps = [ch for ch in letters if ch.upper() == ch and ch.lower() != ch]
        return len(caps) / len(letters)

    @classmethod
    def _repeated_word_ratio(cls, lower: str) -> float:
        words = re.findall(r"[a-z0-9]+", lower)
        if not words:
            return 0.0
        return 1.0 - (len(set(words)) / len(words))

    @staticmethod
    def _contains_any(text: str, markers: Iterable[str]) -> bool:
        return any(marker in text for marker in markers)

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        if math.isnan(value):
            return low
        return max(low, min(high, value))

    @classmethod
    def _token_set(cls, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", cls._fold(text)))

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    @staticmethod
    def _fold(text: str) -> str:
        folded = (text or "").lower()
        replacements = {
            "\u00e1": "a",
            "\u00e9": "e",
            "\u00ed": "i",
            "\u00f3": "o",
            "\u00fa": "u",
            "\u00fc": "u",
            "\u00f1": "n",
        }
        for src, dst in replacements.items():
            folded = folded.replace(src, dst)
        return folded
