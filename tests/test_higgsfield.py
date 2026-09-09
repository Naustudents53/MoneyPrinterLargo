"""Unit tests for the Higgsfield Studio module and video_providers."""
import sys
import os
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from higgsfield_studio.models import (
    Phase, ShotType, ShotStatus, ProductionProject, ProjectConfig,
    Shot, Scene, NarrationBlock, NarrativeElement, CostEvent,
    CharacterProfile, VisualBible, RhythmMetrics, AudioTrack, AudioType,
    QualityMode, ProductionMode, DirectorMode, GENRE_STYLES,
    _serialize, _deserialize,
)
from higgsfield_studio.storage import ProjectStorage, get_storage
from higgsfield_studio.timeline import build_timeline, format_timecode
from higgsfield_studio.cost import check_budget, record_cost, cost_summary
from higgsfield_studio.rhythm import analyze_rhythm, get_rhythm_warnings
from higgsfield_studio.continuity import check_continuity, _are_contradictory
from video_providers.base import (
    GenerationRequest, GenerationResult, JobStatus, ModelCapabilities, QualityMode as VPQualityMode,
)
from video_providers import register_provider, get_provider, list_providers, _providers
from video_providers.errors import VideoProviderError


# ── Models ────────────────────────────────────────────────────────────

class TestPhaseEnum(unittest.TestCase):
    def test_values(self):
        self.assertEqual(Phase.INIT.value, "init")
        self.assertEqual(Phase.COMPLETED.value, "completed")
        self.assertEqual(Phase.FAILED.value, "failed")

    def test_is_str(self):
        self.assertIsInstance(Phase.INIT, str)
        self.assertEqual(Phase.INIT, "init")


class TestShotTypeEnum(unittest.TestCase):
    def test_all_values_present(self):
        names = [e.name for e in ShotType]
        self.assertIn("ESTABLISHING", names)
        self.assertIn("CLOSE_UP", names)
        self.assertIn("B_ROLL", names)

    def test_value_roundtrip(self):
        self.assertEqual(ShotType("medium"), ShotType.MEDIUM)


class TestProductionProject(unittest.TestCase):
    def _make_project(self):
        cfg = ProjectConfig(title="Test", topic="testing", target_duration_min=5.0)
        p = ProductionProject(id="test123", config=cfg, phase=Phase.SCRIPT)
        p.cost_events = [
            CostEvent(id="c1", estimated=1.5, actual=1.2),
            CostEvent(id="c2", estimated=0.5, actual=None),
        ]
        p.shots = [
            Shot(id="s1", status=ShotStatus.APPROVED),
            Shot(id="s2", status=ShotStatus.FAILED),
            Shot(id="s3", status=ShotStatus.PLANNED),
        ]
        return p

    def test_total_estimated_cost(self):
        p = self._make_project()
        self.assertAlmostEqual(p.total_estimated_cost(), 2.0)

    def test_total_actual_cost(self):
        p = self._make_project()
        self.assertAlmostEqual(p.total_actual_cost(), 1.2)

    def test_completed_shots(self):
        self.assertEqual(self._make_project().completed_shots(), 1)

    def test_failed_shots(self):
        self.assertEqual(self._make_project().failed_shots(), 1)

    def test_estimated_duration_with_narration(self):
        p = self._make_project()
        p.narration_blocks = [
            NarrationBlock(id="n1", start_sec=0, end_sec=30),
            NarrationBlock(id="n2", start_sec=30, end_sec=90),
        ]
        self.assertAlmostEqual(p.estimated_duration_sec(), 90.0)

    def test_estimated_duration_no_narration(self):
        p = self._make_project()
        self.assertAlmostEqual(p.estimated_duration_sec(), 300.0)

    def test_serialization_roundtrip(self):
        p = self._make_project()
        d = p.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["id"], "test123")
        self.assertEqual(d["phase"], "script")

        p2 = ProductionProject.from_dict(d)
        self.assertEqual(p2.id, "test123")
        self.assertEqual(p2.phase, Phase.SCRIPT)

    def test_default_project(self):
        p = ProductionProject()
        self.assertEqual(p.phase, Phase.INIT)
        self.assertEqual(len(p.id), 16)


class TestGenreStyles(unittest.TestCase):
    def test_documentary_present(self):
        self.assertIn("documentary", GENRE_STYLES)
        self.assertIn("visual_tone", GENRE_STYLES["documentary"])

    def test_all_genres_have_four_keys(self):
        expected = {"visual_tone", "camera_style", "lighting_style", "color_grade"}
        for genre, style in GENRE_STYLES.items():
            self.assertEqual(set(style.keys()), expected, f"Genre {genre} missing keys")


# ── Storage ───────────────────────────────────────────────────────────

class TestProjectStorage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = get_storage(db_dir=self.tmpdir)

    def tearDown(self):
        self.storage.close()

    def _make_project(self, pid="proj1", title="Test"):
        cfg = ProjectConfig(title=title, topic="testing")
        return ProductionProject(id=pid, config=cfg)

    def test_save_and_load(self):
        p = self._make_project()
        self.storage.save_project(p)
        loaded = self.storage.load_project("proj1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, "proj1")
        # config comes back as dict through best-effort deserialization
        cfg = loaded.config
        if isinstance(cfg, dict):
            self.assertEqual(cfg["title"], "Test")
        else:
            self.assertEqual(cfg.title, "Test")

    def test_load_nonexistent(self):
        self.assertIsNone(self.storage.load_project("nope"))

    def test_list_projects(self):
        self.storage.save_project(self._make_project("a", "Alpha"))
        self.storage.save_project(self._make_project("b", "Beta"))
        projects = self.storage.list_projects()
        self.assertEqual(len(projects), 2)
        ids = {p["id"] for p in projects}
        self.assertEqual(ids, {"a", "b"})

    def test_delete_project(self):
        self.storage.save_project(self._make_project())
        self.assertTrue(self.storage.delete_project("proj1"))
        self.assertIsNone(self.storage.load_project("proj1"))

    def test_delete_nonexistent(self):
        self.assertFalse(self.storage.delete_project("nope"))

    def test_save_cost_event(self):
        self.storage.save_project(self._make_project())
        self.storage.save_cost_event("proj1", {
            "id": "ce1", "shot_id": "s1", "provider": "higgsfield",
            "model": "m1", "estimated": 0.5, "actual": 0.4,
            "description": "test cost",
        })
        costs = self.storage.get_project_costs("proj1")
        self.assertEqual(len(costs), 1)
        self.assertEqual(costs[0]["provider"], "higgsfield")

    def test_save_prompt_memory(self):
        self.storage.save_prompt_memory({
            "prompt_hash": "abc123",
            "prompt": "a cat sitting",
            "style": "documentary",
            "shot_type": "close_up",
            "model": "m1",
            "quality_score": 0.9,
            "success": True,
        })
        best = self.storage.get_best_prompts(style="documentary")
        self.assertEqual(len(best), 1)
        self.assertEqual(best[0]["prompt"], "a cat sitting")

    def test_save_version_and_load(self):
        p = self._make_project()
        p.version = 1
        self.storage.save_project(p)
        self.storage.save_version(p)
        versions = self.storage.list_versions("proj1")
        self.assertEqual(len(versions), 1)


# ── Timeline ──────────────────────────────────────────────────────────

class TestFormatTimecode(unittest.TestCase):
    def test_minutes_seconds(self):
        self.assertEqual(format_timecode(65), "01:05")

    def test_hours(self):
        self.assertEqual(format_timecode(3661), "01:01:01")

    def test_zero(self):
        self.assertEqual(format_timecode(0), "00:00")


class TestBuildTimeline(unittest.TestCase):
    def test_no_narration_returns_project(self):
        p = ProductionProject()
        result = build_timeline(p)
        self.assertIs(result, p)

    def test_builds_audio_tracks_from_narration(self):
        p = ProductionProject()
        p.narration_blocks = [
            NarrationBlock(id="n1", start_sec=0, end_sec=10, audio_path="/tmp/a.wav"),
            NarrationBlock(id="n2", start_sec=10, end_sec=20, audio_path="/tmp/b.wav"),
        ]
        p.scenes = [
            Scene(id="sc1", narration_ids=["n1", "n2"], shot_ids=["sh1"]),
        ]
        p.shots = [
            Shot(id="sh1", sequence=0, duration_sec=5.0),
        ]
        result = build_timeline(p)
        narration_tracks = [t for t in result.audio_tracks if t.type == AudioType.NARRATION]
        self.assertEqual(len(narration_tracks), 2)

    def test_scene_timecodes_set(self):
        p = ProductionProject()
        p.narration_blocks = [
            NarrationBlock(id="n1", start_sec=5, end_sec=15),
        ]
        p.scenes = [Scene(id="sc1", narration_ids=["n1"], shot_ids=[])]
        p.shots = []
        build_timeline(p)
        self.assertAlmostEqual(p.scenes[0].timecode_start, 5.0)
        self.assertAlmostEqual(p.scenes[0].timecode_end, 15.0)


# ── Cost ──────────────────────────────────────────────────────────────

class TestCheckBudget(unittest.TestCase):
    def test_no_budget_limit(self):
        p = ProductionProject()
        result = check_budget(p)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["reason"], "no_budget_limit")

    def test_within_budget(self):
        p = ProductionProject()
        p.config.budget_limit = 10.0
        p.cost_events = [CostEvent(actual=3.0)]
        result = check_budget(p, additional_cost=5.0)
        self.assertTrue(result["allowed"])

    def test_budget_exceeded(self):
        p = ProductionProject()
        p.config.budget_limit = 10.0
        p.cost_events = [CostEvent(actual=8.0)]
        result = check_budget(p, additional_cost=5.0)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "budget_exceeded")


class TestRecordCost(unittest.TestCase):
    def test_records_event(self):
        p = ProductionProject()
        event = record_cost(p, "s1", "higgsfield", "model-x", 1.0, 0.8, "gen")
        self.assertEqual(len(p.cost_events), 1)
        self.assertEqual(event.provider, "higgsfield")
        self.assertAlmostEqual(event.actual, 0.8)


class TestCostSummary(unittest.TestCase):
    def test_summary(self):
        p = ProductionProject()
        p.config.budget_limit = 50.0
        p.cost_events = [CostEvent(estimated=2.0, actual=1.5)]
        p.shots = [Shot(status=ShotStatus.APPROVED), Shot(status=ShotStatus.FAILED)]
        s = cost_summary(p)
        self.assertAlmostEqual(s["total_estimated"], 2.0)
        self.assertAlmostEqual(s["total_actual"], 1.5)
        self.assertEqual(s["completed_shots"], 1)
        self.assertEqual(s["failed_shots"], 1)
        self.assertEqual(s["budget_limit"], 50.0)


# ── Rhythm ────────────────────────────────────────────────────────────

class TestAnalyzeRhythm(unittest.TestCase):
    def test_empty_shots(self):
        p = ProductionProject()
        result = analyze_rhythm(p)
        self.assertIs(result, p)

    def test_varied_shots(self):
        p = ProductionProject()
        p.shots = [
            Shot(sequence=i, shot_type=st, camera=f"cam{i}")
            for i, st in enumerate([ShotType.WIDE, ShotType.CLOSE_UP, ShotType.MEDIUM, ShotType.AERIAL])
        ]
        analyze_rhythm(p)
        self.assertGreater(p.rhythm.shot_variety, 50)

    def test_monotonous_shots(self):
        p = ProductionProject()
        p.shots = [Shot(sequence=i, shot_type=ShotType.MEDIUM) for i in range(10)]
        analyze_rhythm(p)
        self.assertLess(p.rhythm.shot_variety, 20)


class TestGetRhythmWarnings(unittest.TestCase):
    def test_no_shots_no_warnings(self):
        p = ProductionProject()
        self.assertEqual(get_rhythm_warnings(p), [])

    def test_consecutive_same_type_warning(self):
        p = ProductionProject()
        p.shots = [Shot(sequence=i, shot_type=ShotType.WIDE) for i in range(6)]
        analyze_rhythm(p)
        warnings = get_rhythm_warnings(p)
        self.assertTrue(any("consecutive" in w for w in warnings))

    def test_low_variety_warning(self):
        p = ProductionProject()
        p.shots = [Shot(sequence=i, shot_type=ShotType.STATIC) for i in range(10)]
        analyze_rhythm(p)
        warnings = get_rhythm_warnings(p)
        self.assertTrue(any("variety" in w.lower() for w in warnings))


# ── Continuity ────────────────────────────────────────────────────────

class TestAreContradictory(unittest.TestCase):
    def test_day_night(self):
        self.assertTrue(_are_contradictory("bright daylight", "dark night"))

    def test_same_lighting(self):
        self.assertFalse(_are_contradictory("warm sunset", "warm sunset"))

    def test_interior_exterior(self):
        self.assertTrue(_are_contradictory("interior office", "exterior garden"))

    def test_no_contradiction(self):
        self.assertFalse(_are_contradictory("soft blue", "soft green"))


class TestCheckContinuity(unittest.TestCase):
    def test_no_issues_different_scenes(self):
        p = ProductionProject()
        s1 = Shot(id="s1", scene_id="a", sequence=0, lighting="day", environment="forest")
        s2 = Shot(id="s2", scene_id="b", sequence=1, lighting="night", environment="city")
        p.shots = [s1, s2]
        issues = check_continuity(p, s2)
        self.assertEqual(issues, [])

    def test_lighting_contradiction_same_scene(self):
        p = ProductionProject()
        s1 = Shot(id="s1", scene_id="a", sequence=0, lighting="bright day")
        s2 = Shot(id="s2", scene_id="a", sequence=1, lighting="dark night")
        p.shots = [s1, s2]
        issues = check_continuity(p, s2)
        self.assertTrue(any("Lighting" in i for i in issues))

    def test_environment_change_same_scene(self):
        p = ProductionProject()
        s1 = Shot(id="s1", scene_id="a", sequence=0, environment="forest")
        s2 = Shot(id="s2", scene_id="a", sequence=1, environment="desert")
        p.shots = [s1, s2]
        issues = check_continuity(p, s2)
        self.assertTrue(any("Environment" in i for i in issues))

    def test_shot_not_in_project(self):
        p = ProductionProject()
        p.shots = [Shot(id="s1")]
        issues = check_continuity(p, Shot(id="unknown"))
        self.assertEqual(issues, [])


# ── Video Providers Base ──────────────────────────────────────────────

class TestGenerationRequest(unittest.TestCase):
    def test_defaults(self):
        r = GenerationRequest(prompt="a cat")
        self.assertEqual(r.prompt, "a cat")
        self.assertEqual(r.duration_sec, 5.0)
        self.assertEqual(r.aspect_ratio, "16:9")
        self.assertIsNone(r.seed)

    def test_custom_fields(self):
        r = GenerationRequest(prompt="x", duration_sec=10, resolution="4k", seed=42)
        self.assertEqual(r.duration_sec, 10)
        self.assertEqual(r.seed, 42)


class TestGenerationResult(unittest.TestCase):
    def test_creation(self):
        r = GenerationResult(
            job_id="j1", status=JobStatus.COMPLETED,
            provider="test", model_id="m1",
            output_path="/out.mp4", cost=1.5,
        )
        self.assertEqual(r.status, JobStatus.COMPLETED)
        self.assertEqual(r.cost, 1.5)
        self.assertIsNone(r.error)


class TestModelCapabilities(unittest.TestCase):
    def test_defaults(self):
        mc = ModelCapabilities(model_id="m1", name="Model One")
        self.assertEqual(mc.max_duration_sec, 10.0)
        self.assertFalse(mc.supports_audio)


# ── Video Providers Registry ─────────────────────────────────────────

class TestProviderRegistry(unittest.TestCase):
    def setUp(self):
        self._backup = dict(_providers)

    def tearDown(self):
        _providers.clear()
        _providers.update(self._backup)

    def test_register_and_get(self):
        from video_providers.base import VideoGenerationProvider

        class FakeProvider(VideoGenerationProvider):
            @property
            def name(self): return "fake"
            async def authenticate(self): return True
            async def list_models(self): return []
            async def generate(self, r): pass
            async def get_job_status(self, j): pass
            async def wait_for_job(self, j, t=600): pass
            async def cancel_job(self, j): return True
            async def download_output(self, j, d): return d

        register_provider("fake", FakeProvider)
        p = get_provider("fake")
        self.assertEqual(p.name, "fake")

    @patch("video_providers._discover_providers")
    def test_get_unknown_raises(self, mock_discover):
        _providers.clear()
        with self.assertRaises(VideoProviderError):
            get_provider("nonexistent")

    @patch("video_providers._discover_providers")
    def test_list_providers(self, mock_discover):
        _providers.clear()
        _providers["alpha"] = MagicMock
        _providers["beta"] = MagicMock
        result = list_providers()
        self.assertIn("alpha", result)
        self.assertIn("beta", result)


if __name__ == "__main__":
    unittest.main()
