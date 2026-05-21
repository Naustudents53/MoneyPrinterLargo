import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes import PhotoVideo as photo_video  # noqa: E402
import llm_provider  # noqa: E402


def _make_image(path: Path, size=(64, 48), mode="RGBA") -> None:
    if path.suffix.lower() in {".jpg", ".jpeg"} and mode == "RGBA":
        mode = "RGB"
    img = Image.new(mode, size, (10, 20, 30, 255) if mode == "RGBA" else 128)
    img.save(path)


class PhotoVideoTests(unittest.TestCase):
    def test_collect_photo_paths_expands_directories_and_filters_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            folder = tmp_path / "photos"
            folder.mkdir()
            _make_image(folder / "b.png")
            _make_image(folder / "a.jpg")
            (folder / "notes.txt").write_text("ignore me", encoding="utf-8")

            cwd = os.getcwd()
            try:
                os.chdir(tmp_path)
                paths = photo_video.collect_photo_paths(str(folder))
            finally:
                os.chdir(cwd)

            self.assertEqual([Path(p).name for p in paths], ["a.jpg", "b.png"])

    def test_prepare_photo_assets_normalizes_to_rgb_jpegs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_root = photo_video.ROOT_DIR
            photo_video.ROOT_DIR = str(tmp_path)
            try:
                source = tmp_path / "source.png"
                _make_image(source, size=(80, 120), mode="RGBA")

                generator = photo_video.PhotoVideoGenerator.__new__(photo_video.PhotoVideoGenerator)
                prepared = photo_video.PhotoVideoGenerator.prepare_photo_assets(generator, [str(source)])
            finally:
                photo_video.ROOT_DIR = old_root

            self.assertEqual(len(prepared), 1)
            out = Path(prepared[0])
            self.assertEqual(out.parent, tmp_path / ".mp" / "tmp")
            self.assertEqual(out.suffix, ".jpg")
            with Image.open(out) as img:
                self.assertEqual(img.mode, "RGB")
                self.assertEqual(img.size, (80, 120))

    def test_extract_json_object_handles_code_fences(self):
        raw = """```json
{"topic": "Tema", "story_angle": "Angulo", "photo_notes": ["uno", "dos"]}
```"""

        parsed = photo_video._extract_json_object(raw)

        self.assertEqual(parsed["topic"], "Tema")
        self.assertEqual(parsed["photo_notes"], ["uno", "dos"])

    def test_analyze_photos_honors_requested_vision_provider(self):
        class FakeYoutube:
            niche = "viajes"
            language = "espanol"

            def generate_response(self, _prompt):
                raise AssertionError("metadata fallback should not be used")

        generator = photo_video.PhotoVideoGenerator(FakeYoutube())
        with (
            patch.object(
                photo_video.PhotoVideoGenerator,
                "_analyze_with_codex_cli_vision",
                return_value='{"topic":"Tema Codex","story_angle":"Angulo","photo_notes":["nota"]}',
            ) as codex,
            patch.object(photo_video.PhotoVideoGenerator, "_analyze_with_gemini_vision") as gemini,
        ):
            analysis = generator.analyze_photos(
                kind="short",
                photo_paths=["missing.jpg"],
                vision_provider="codex",
            )

        self.assertEqual(analysis.topic, "Tema Codex")
        codex.assert_called_once()
        gemini.assert_not_called()

    def test_auto_photo_vision_prefers_codex_when_openai_uses_codex_cli(self):
        class FakeYoutube:
            niche = "viajes"
            language = "espanol"

        generator = photo_video.PhotoVideoGenerator(FakeYoutube())
        with (
            patch.object(llm_provider, "get_active_provider", return_value="openai"),
            patch.object(photo_video, "get_openai_use_codex_cli", return_value=True),
        ):
            labels = [label for label, _ in generator._photo_vision_providers("auto")]

        self.assertEqual(labels[0], "Codex CLI vision")

    def test_codex_cli_vision_attaches_uploaded_images(self):
        class FakeYoutube:
            niche = "viajes"
            language = "espanol"

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        captured = {}

        def fake_run(args, input, **kwargs):
            captured["args"] = args
            captured["input"] = input
            captured["kwargs"] = kwargs
            output_path = Path(args[args.index("--output-last-message") + 1])
            output_path.write_text(
                '{"topic":"Tema","story_angle":"Angulo","photo_notes":["uno"]}',
                encoding="utf-8",
            )
            return Completed()

        generator = photo_video.PhotoVideoGenerator(FakeYoutube())
        with (
            patch.object(photo_video, "get_codex_cli_command", return_value="codex"),
            patch.object(photo_video, "get_codex_cli_model", return_value=""),
            patch.object(photo_video, "get_codex_cli_sandbox", return_value="read-only"),
            patch.object(photo_video, "get_codex_cli_timeout_seconds", return_value=123),
            patch.object(photo_video, "get_openai_reasoning_effort", return_value="high"),
            patch.object(llm_provider, "get_active_provider", return_value="openai"),
            patch.object(llm_provider, "get_active_model", return_value="gpt-test"),
            patch.object(photo_video.subprocess, "run", side_effect=fake_run),
        ):
            text = generator._analyze_with_codex_cli_vision(
                "Return JSON.",
                ["one.jpg", "two.png"],
            )

        self.assertIn('"topic":"Tema"', text)
        self.assertEqual(captured["args"].count("--image"), 2)
        self.assertLess(
            captured["args"].index("--ask-for-approval"),
            captured["args"].index("exec"),
        )
        self.assertEqual(captured["args"][captured["args"].index("--ask-for-approval") + 1], "never")
        self.assertEqual(captured["args"][captured["args"].index("--model") + 1], "gpt-test")
        self.assertEqual(captured["args"][captured["args"].index("--sandbox") + 1], "read-only")
        self.assertEqual(captured["kwargs"]["timeout"], 123)
        self.assertIn("attached images", captured["input"])

    def test_generate_short_from_manual_topic_and_script_uses_uploaded_photos(self):
        class FakeYoutube:
            niche = "historia"
            language = "espanol"

            def __init__(self, root: Path) -> None:
                self.root = root
                self.calls = []
                self._used_stock_urls = set()

            def generate_metadata(self):
                self.calls.append("metadata")
                self.metadata = {"title": "Titulo", "description": "Descripcion"}

            def generate_script_to_speech(self, tts):
                self.calls.append("tts")
                self.tts_path = str(self.root / "audio.wav")

            def combine(self):
                self.calls.append("combine")
                out = self.root / "video.mp4"
                out.write_bytes(b"video")
                return str(out)

            def _persist_metadata_sidecar(self, is_long: bool):
                self.calls.append(f"sidecar:{is_long}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_root = photo_video.ROOT_DIR
            photo_video.ROOT_DIR = str(tmp_path)
            try:
                source = tmp_path / "source.png"
                _make_image(source)
                fake = FakeYoutube(tmp_path)
                request = photo_video.PhotoVideoRequest(
                    kind="short",
                    photo_paths=[str(source)],
                    topic="Tema manual",
                    script="Guion manual.",
                )

                with patch.object(photo_video, "record_generation", return_value=None):
                    path = photo_video.PhotoVideoGenerator(fake).generate(object(), request)
            finally:
                photo_video.ROOT_DIR = old_root

            self.assertEqual(Path(path).name, "video.mp4")
            self.assertEqual(fake.subject, "Tema manual")
            self.assertEqual(fake.script, "Guion manual.")
            self.assertEqual(fake.calls, ["metadata", "tts", "combine", "sidecar:False"])
            self.assertEqual(len(fake.images), 1)
            self.assertEqual(Path(fake.images[0]).suffix, ".jpg")


if __name__ == "__main__":
    unittest.main()
