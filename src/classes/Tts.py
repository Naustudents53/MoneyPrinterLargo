import os
import asyncio

from config import ROOT_DIR, get_tts_voice, get_tts_provider

# Edge-TTS voice mapping (natural-sounding Microsoft voices)
EDGE_TTS_VOICES = {
    "Jasper": "en-US-GuyNeural",
    "Bella": "en-US-JennyNeural",
    "Luna": "en-US-AriaNeural",
    "Bruno": "en-US-DavisNeural",
    "Rosie": "en-US-SaraNeural",
    "Hugo": "en-GB-RyanNeural",
    "Kiki": "en-AU-NatashaNeural",
    "Leo": "en-US-ChristopherNeural",
    # Spanish voices
    "Sofia": "es-MX-DaliaNeural",
    "Carlos": "es-MX-JorgeNeural",
    "Elena": "es-ES-ElviraNeural",
    "Pablo": "es-ES-AlvaroNeural",
}


class TTS:
    def __init__(self) -> None:
        self._provider = get_tts_provider()
        self._voice = get_tts_voice()

        if self._provider == "kittentts":
            try:
                import soundfile  # noqa: F401
                from kittentts import KittenTTS as KittenModel
                self._kitten_model = KittenModel("KittenML/kitten-tts-mini-0.8")
                self._kitten_sr = 24000
            except ImportError:
                print("[WARNING] KittenTTS not available, falling back to edge-tts")
                self._provider = "edge_tts"

    def synthesize(self, text, output_file=os.path.join(ROOT_DIR, ".mp", "audio.wav")):
        if self._provider == "edge_tts":
            return self._synthesize_edge_tts(text, output_file)
        return self._synthesize_kitten(text, output_file)

    def _synthesize_kitten(self, text, output_file):
        import soundfile as sf
        audio = self._kitten_model.generate(text, voice=self._voice)
        sf.write(output_file, audio, self._kitten_sr)
        return output_file

    def _synthesize_edge_tts(self, text, output_file):
        import edge_tts
        import subprocess
        import shutil

        # Map voice name to edge-tts voice ID
        voice_id = EDGE_TTS_VOICES.get(self._voice, self._voice)

        # edge-tts outputs MP3
        mp3_path = output_file.rsplit(".", 1)[0] + ".mp3"

        async def _generate():
            communicate = edge_tts.Communicate(text, voice_id)
            await communicate.save(mp3_path)

        asyncio.run(_generate())

        # Convert mp3 to wav for compatibility with the rest of the pipeline
        if output_file.endswith(".wav"):
            ffmpeg_path = self._find_ffmpeg()
            if ffmpeg_path:
                try:
                    subprocess.run(
                        [ffmpeg_path, "-i", mp3_path, "-y", output_file],
                        capture_output=True, timeout=60
                    )
                    os.remove(mp3_path)
                except Exception:
                    shutil.move(mp3_path, output_file)
            else:
                # No ffmpeg, just rename - moviepy can handle mp3 too
                shutil.move(mp3_path, output_file)
        else:
            shutil.move(mp3_path, output_file)

        return output_file

    @staticmethod
    def _find_ffmpeg() -> str | None:
        """Finds ffmpeg in common Windows locations."""
        import shutil as sh
        path = sh.which("ffmpeg")
        if path:
            return path

        # Check common winget installation path
        common_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"),
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
        ]
        for base in common_paths:
            if not os.path.isdir(base):
                continue
            for root, dirs, files in os.walk(base):
                if "ffmpeg.exe" in files:
                    return os.path.join(root, "ffmpeg.exe")
        return None
