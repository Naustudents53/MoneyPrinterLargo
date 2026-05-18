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
