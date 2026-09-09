"""Production data models for Higgsfield Studio."""
from __future__ import annotations
import json
import uuid
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> float:
    return time.time()


# ── Enums ──────────────────────────────────────────────────────────────

class Phase(str, Enum):
    INIT = "init"
    TOPIC_ANALYSIS = "topic_analysis"
    RESEARCH = "research"
    CONCEPT = "concept"
    NARRATIVE = "narrative"
    SCRIPT = "script"
    SEGMENTATION = "segmentation"
    VISUAL_BIBLE = "visual_bible"
    CHARACTER_BIBLE = "character_bible"
    ENVIRONMENT_BIBLE = "environment_bible"
    STORYBOARD = "storyboard"
    SHOT_PLANNING = "shot_planning"
    PROMPT_ENGINEERING = "prompt_engineering"
    REFERENCE_PREP = "reference_prep"
    GENERATION = "generation"
    VIDEO_QC = "video_qc"
    REGENERATION = "regeneration"
    AUDIO = "audio"
    ASSEMBLY = "assembly"
    FINAL_QC = "final_qc"
    METADATA = "metadata"
    THUMBNAIL = "thumbnail"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ProductionMode(str, Enum):
    PLAN = "plan"
    PLAN_PROMPTS = "plan_prompts"
    FULL = "full"
    UPGRADE = "upgrade"
    REGENERATE_FAILED = "regenerate_failed"
    RENDER_ONLY = "render_only"


class DirectorMode(str, Enum):
    AUTO = "auto"
    DIRECTOR = "director"


class QualityMode(str, Enum):
    BUDGET = "budget"
    BALANCED = "balanced"
    QUALITY = "quality"
    CINEMA = "cinema"


class ShotStatus(str, Enum):
    PLANNED = "planned"
    PROMPTING = "prompting"
    QUEUED = "queued"
    GENERATING = "generating"
    QC_PENDING = "qc_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REGENERATING = "regenerating"
    FAILED = "failed"
    SKIPPED = "skipped"


class ShotType(str, Enum):
    ESTABLISHING = "establishing"
    WIDE = "wide"
    MEDIUM = "medium"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"
    DETAIL = "detail"
    AERIAL = "aerial"
    POV = "pov"
    OVER_SHOULDER = "over_shoulder"
    TRACKING = "tracking"
    PAN = "pan"
    STATIC = "static"
    DOLLY = "dolly"
    CRANE = "crane"
    HANDHELD = "handheld"
    B_ROLL = "b_roll"
    TRANSITION = "transition"
    HERO = "hero"
    MACRO = "macro"


class AudioType(str, Enum):
    NARRATION = "narration"
    MUSIC = "music"
    AMBIENCE = "ambience"
    SFX = "sfx"
    SILENCE = "silence"


class NarrativeElement(str, Enum):
    HOOK = "hook"
    COLD_OPEN = "cold_open"
    SETUP = "setup"
    PREMISE = "premise"
    ESCALATION = "escalation"
    EXPOSITION = "exposition"
    DISCOVERY = "discovery"
    CONFLICT = "conflict"
    REVEAL = "reveal"
    CLIMAX = "climax"
    RESOLUTION = "resolution"
    TAKEAWAY = "takeaway"


class RetryStrategy(str, Enum):
    SAME = "retry_same"
    TEMPERATURE = "retry_temperature"
    REWRITE = "retry_rewrite"
    SIMPLIFY = "retry_simplify"
    DIFFERENT_MODEL = "retry_different_model"


# ── Core Data Models ───────────────────────────────────────────────────

@dataclass
class ProjectConfig:
    title: str = ""
    topic: str = ""
    target_duration_min: float = 15.0
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"
    language: str = "es"
    narrator_voice: str = ""
    style: str = "documentary"
    genre: str = "documentary"
    quality: QualityMode = QualityMode.QUALITY
    provider: str = "higgsfield"
    research_mode: str = "light"  # none, light, deep
    director_mode: DirectorMode = DirectorMode.AUTO
    production_mode: ProductionMode = ProductionMode.FULL
    budget_limit: float | None = None
    auto_upload: bool = False
    channel_id: str = ""
    series_id: str = ""
    dry_run: bool = False


@dataclass
class NarrationBlock:
    id: str = field(default_factory=_uid)
    sequence: int = 0
    text: str = ""
    narrative_element: NarrativeElement = NarrativeElement.EXPOSITION
    emotion: str = "neutral"
    delivery: str = "normal"
    visual_intent: str = ""
    word_count: int = 0
    estimated_duration_sec: float = 0.0
    actual_duration_sec: float | None = None
    start_sec: float = 0.0
    end_sec: float = 0.0
    audio_path: str | None = None


@dataclass
class Chapter:
    id: str = field(default_factory=_uid)
    sequence: int = 0
    title: str = ""
    description: str = ""
    hook: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    narration_ids: list[str] = field(default_factory=list)
    scene_ids: list[str] = field(default_factory=list)


@dataclass
class CharacterProfile:
    id: str = field(default_factory=_uid)
    name: str = ""
    age_range: str = ""
    appearance: str = ""
    hair: str = ""
    skin: str = ""
    body: str = ""
    wardrobe: str = ""
    accessories: str = ""
    personality: str = ""
    physical_traits: str = ""
    reference_images: list[str] = field(default_factory=list)
    continuity_rules: list[str] = field(default_factory=list)


@dataclass
class LocationProfile:
    id: str = field(default_factory=_uid)
    name: str = ""
    description: str = ""
    architecture: str = ""
    materials: str = ""
    lighting: str = ""
    weather: str = ""
    time_period: str = ""
    color_palette: list[str] = field(default_factory=list)
    props: list[str] = field(default_factory=list)
    camera_constraints: str = ""
    reference_images: list[str] = field(default_factory=list)


@dataclass
class VisualBible:
    style: dict[str, str] = field(default_factory=dict)
    camera: dict[str, Any] = field(default_factory=dict)
    lighting: dict[str, str] = field(default_factory=dict)
    color: dict[str, str] = field(default_factory=dict)
    film_language: dict[str, str] = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)


@dataclass
class QCResult:
    visual_quality: float = 0.0
    motion_quality: float = 0.0
    identity_consistency: float = 0.0
    temporal_consistency: float = 0.0
    composition_quality: float = 0.0
    prompt_alignment: float = 0.0
    artifact_score: float = 0.0
    cinematic_score: float = 0.0
    overall_score: float = 0.0
    issues: list[str] = field(default_factory=list)
    passed: bool = False


@dataclass
class ShotVersion:
    version: int = 1
    file_path: str = ""
    qc: QCResult | None = None
    prompt_used: str = ""
    model_used: str = ""
    provider_job_id: str = ""
    cost: float | None = None
    generated_at: float = 0.0
    retry_strategy: RetryStrategy | None = None


@dataclass
class Shot:
    id: str = field(default_factory=_uid)
    scene_id: str = ""
    sequence: int = 0
    duration_sec: float = 5.0
    shot_type: ShotType = ShotType.MEDIUM
    camera: str = ""
    lens: str = ""
    movement: str = ""
    composition: str = ""
    subject: str = ""
    action: str = ""
    environment: str = ""
    lighting: str = ""
    color: str = ""
    atmosphere: str = ""
    emotion: str = ""
    sound: str = ""
    transition: str = ""
    prompt: str = ""
    optimized_prompt: str = ""
    negative_prompt: str = ""
    prompt_quality_score: float = 0.0
    model_id: str = ""
    reference_assets: list[str] = field(default_factory=list)
    reference_shot_ids: list[str] = field(default_factory=list)
    status: ShotStatus = ShotStatus.PLANNED
    selected_version: int = 1
    versions: list[ShotVersion] = field(default_factory=list)
    regeneration_count: int = 0
    max_regenerations: int = 3
    estimated_cost: float | None = None
    actual_cost: float | None = None
    dependency_ids: list[str] = field(default_factory=list)
    importance: float = 0.5  # 0-1, for smart generation prioritization


@dataclass
class Scene:
    id: str = field(default_factory=_uid)
    chapter_id: str = ""
    sequence: int = 0
    timecode_start: float = 0.0
    timecode_end: float = 0.0
    duration_sec: float = 0.0
    narration_ids: list[str] = field(default_factory=list)
    location_id: str = ""
    time_of_day: str = ""
    character_ids: list[str] = field(default_factory=list)
    props: list[str] = field(default_factory=list)
    visual_goal: str = ""
    dramatic_goal: str = ""
    camera_goal: str = ""
    continuity_requirements: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    shot_ids: list[str] = field(default_factory=list)


@dataclass
class AudioTrack:
    id: str = field(default_factory=_uid)
    type: AudioType = AudioType.NARRATION
    start_sec: float = 0.0
    end_sec: float = 0.0
    volume: float = 1.0
    fade_in_sec: float = 0.0
    fade_out_sec: float = 0.0
    ducking: bool = False
    source_path: str = ""


@dataclass
class CostEvent:
    id: str = field(default_factory=_uid)
    shot_id: str = ""
    provider: str = ""
    model: str = ""
    estimated: float | None = None
    actual: float | None = None
    timestamp: float = field(default_factory=_now)
    description: str = ""


@dataclass
class RhythmMetrics:
    shot_variety: float = 0.0
    camera_variety: float = 0.0
    composition_variety: float = 0.0
    motion_variety: float = 0.0
    location_variety: float = 0.0


@dataclass
class ProductionOutputs:
    master_video: str = ""
    preview_video: str = ""
    thumbnail: str = ""
    captions_srt: str = ""
    captions_vtt: str = ""
    metadata_json: str = ""
    manifest_json: str = ""


@dataclass
class ProductionProject:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    version: int = 1
    config: ProjectConfig = field(default_factory=ProjectConfig)
    phase: Phase = Phase.INIT
    progress: float = 0.0
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    # Narrative
    concept: str = ""
    research: str = ""
    script_raw: str = ""
    narration_blocks: list[NarrationBlock] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)

    # Visual world
    visual_bible: VisualBible = field(default_factory=VisualBible)
    characters: list[CharacterProfile] = field(default_factory=list)
    locations: list[LocationProfile] = field(default_factory=list)

    # Production
    scenes: list[Scene] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    audio_tracks: list[AudioTrack] = field(default_factory=list)
    cost_events: list[CostEvent] = field(default_factory=list)
    rhythm: RhythmMetrics = field(default_factory=RhythmMetrics)
    outputs: ProductionOutputs = field(default_factory=ProductionOutputs)

    # Job tracking
    job_id: str = ""
    error: str = ""
    retry_count: int = 0
    logs: list[str] = field(default_factory=list)

    def total_estimated_cost(self) -> float:
        return sum(e.estimated or 0 for e in self.cost_events)

    def total_actual_cost(self) -> float:
        return sum(e.actual or 0 for e in self.cost_events)

    def completed_shots(self) -> int:
        return sum(1 for s in self.shots if s.status == ShotStatus.APPROVED)

    def failed_shots(self) -> int:
        return sum(1 for s in self.shots if s.status == ShotStatus.FAILED)

    def estimated_duration_sec(self) -> float:
        if self.narration_blocks:
            last = max(self.narration_blocks, key=lambda n: n.end_sec)
            return last.end_sec
        return self.config.target_duration_min * 60

    def to_dict(self) -> dict:
        return _serialize(self)

    @classmethod
    def from_dict(cls, data: dict) -> ProductionProject:
        return _deserialize(cls, data)


# ── Serialization ──────────────────────────────────────────────────────

def _serialize(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, '__dataclass_fields__'):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


def _deserialize(cls, data: dict) -> Any:
    """Best-effort deserialization from dict to dataclass."""
    if not isinstance(data, dict):
        return data
    import dataclasses
    if not dataclasses.is_dataclass(cls):
        return data
    fields = {f.name: f for f in dataclasses.fields(cls)}
    kwargs = {}
    for name, fld in fields.items():
        if name not in data:
            continue
        val = data[name]
        ftype = fld.type
        # Handle string enum types
        origin = getattr(ftype, '__origin__', None)
        if isinstance(ftype, type) and issubclass(ftype, Enum):
            try:
                kwargs[name] = ftype(val)
            except (ValueError, KeyError):
                kwargs[name] = val
        elif isinstance(ftype, type) and dataclasses.is_dataclass(ftype):
            kwargs[name] = _deserialize(ftype, val) if isinstance(val, dict) else val
        elif origin is list or (isinstance(ftype, str) and ftype.startswith('list[')):
            # For lists of dataclasses, try to infer the inner type
            kwargs[name] = val  # keep as-is for simplicity
        else:
            kwargs[name] = val
    return cls(**kwargs)


# ── Prompt Library Templates ───────────────────────────────────────────

GENRE_STYLES: dict[str, dict[str, str]] = {
    "documentary": {
        "visual_tone": "cinematic realism with documentary gravitas",
        "camera_style": "steady, observational, motivated movement",
        "lighting_style": "natural, motivated, atmospheric",
        "color_grade": "desaturated earth tones, deep shadows, warm highlights",
    },
    "true_crime": {
        "visual_tone": "dark, suspenseful, noir-influenced realism",
        "camera_style": "slow push-ins, static with tension, surveillance-like",
        "lighting_style": "low-key, harsh practicals, deep shadows",
        "color_grade": "cold blues, desaturated, high contrast",
    },
    "science": {
        "visual_tone": "clean, precise, awe-inspiring scale",
        "camera_style": "smooth orbits, macro to cosmic scale shifts",
        "lighting_style": "clinical white, cosmic ambience, volumetric",
        "color_grade": "cool neutral, deep space blacks, electric accents",
    },
    "history": {
        "visual_tone": "period-accurate, painterly, archival feel",
        "camera_style": "slow, contemplative, static establishing shots",
        "lighting_style": "warm candle-like, overcast daylight, era-appropriate",
        "color_grade": "warm sepia undertones, aged film look",
    },
    "mystery": {
        "visual_tone": "atmospheric, layered, visually ambiguous",
        "camera_style": "slow reveals, shallow DOF, hidden compositions",
        "lighting_style": "chiaroscuro, fog, silhouettes",
        "color_grade": "muted, green-grey undertones, selective warmth",
    },
    "horror": {
        "visual_tone": "dread-inducing, claustrophobic, visceral",
        "camera_style": "handheld tension, sudden stillness, dutch angles",
        "lighting_style": "under-lit, single-source, strobing",
        "color_grade": "desaturated, sickly greens, blood reds",
    },
    "space": {
        "visual_tone": "vast, silent, sublime cosmic beauty",
        "camera_style": "slow drifting, orbital, extreme scale",
        "lighting_style": "single sun source, rim lighting, lens flares",
        "color_grade": "deep blacks, nebula colors, star-white highlights",
    },
    "technology": {
        "visual_tone": "sleek, precise, futuristic realism",
        "camera_style": "smooth tracking, macro detail, product-shot precision",
        "lighting_style": "studio softbox, LED accent, screen glow",
        "color_grade": "cool blues, metallic highlights, clean whites",
    },
    "nature": {
        "visual_tone": "breathtaking, immersive, patient observation",
        "camera_style": "aerial sweeps, time-lapse, wildlife telephoto",
        "lighting_style": "golden hour, storm light, dappled forest",
        "color_grade": "rich greens, golden warmth, vivid but natural",
    },
    "cinematic_essay": {
        "visual_tone": "artistic, contemplative, visually metaphorical",
        "camera_style": "composed frames, slow dolly, deliberate movement",
        "lighting_style": "moody, expressive, symbolic",
        "color_grade": "stylized but restrained, thematic palette",
    },
    "travel": {
        "visual_tone": "vibrant, immersive, wanderlust-inducing",
        "camera_style": "gimbal walk-through, aerials, golden hour tracking",
        "lighting_style": "warm natural, blue hour, market-light practicals",
        "color_grade": "saturated warmth, blue skies, rich earth tones",
    },
    "sports": {
        "visual_tone": "dynamic, high-energy, heroic",
        "camera_style": "slow-motion, tracking, low-angle hero shots",
        "lighting_style": "stadium floods, backlit silhouettes, sweat glisten",
        "color_grade": "punchy contrast, vivid team colors, golden highlights",
    },
    "business": {
        "visual_tone": "polished, authoritative, cinematic corporate",
        "camera_style": "smooth dolly, portrait close-ups, skyline establishes",
        "lighting_style": "professional, window light, modern office ambience",
        "color_grade": "neutral warm, deep navy, gold accents",
    },
    "fiction": {
        "visual_tone": "narrative-driven, genre-appropriate, immersive world",
        "camera_style": "story-motivated, genre-conventional, character-focused",
        "lighting_style": "motivated by world, time, and mood",
        "color_grade": "world-appropriate palette, story-driven shifts",
    },
    "explainer": {
        "visual_tone": "clear, engaging, visually instructive",
        "camera_style": "clean compositions, smooth transitions, focus pulls",
        "lighting_style": "bright, even, studio-quality",
        "color_grade": "clean, slightly warm, accessible",
    },
    "war": {
        "visual_tone": "gritty, visceral, somber",
        "camera_style": "embedded handheld, long lens compression, static memorial",
        "lighting_style": "overcast, smoke-filtered, harsh flash",
        "color_grade": "bleached, desaturated, olive-mud palette",
    },
    "architecture": {
        "visual_tone": "geometric, contemplative, structural beauty",
        "camera_style": "slow tilt-ups, symmetrical frames, parallax",
        "lighting_style": "dramatic shadows, golden hour raking light",
        "color_grade": "concrete neutrals, sky blues, material-true",
    },
}
