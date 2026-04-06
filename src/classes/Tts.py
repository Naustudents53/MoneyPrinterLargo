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

    def synthesize_long(self, text, output_file, voice_id=None):
        """
        Synthesize long-form text with SSML prosody for more natural narration.
        Uses a slower rate and adds pauses between paragraphs for a documentary feel.
        """
        import edge_tts
        import subprocess
        import shutil

        vid = voice_id or EDGE_TTS_VOICES.get(self._voice, self._voice)
        mp3_path = output_file.rsplit(".", 1)[0] + ".mp3"

        # Split into paragraphs and add SSML pauses between them
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]

        # Build SSML with prosody: slightly slower rate for documentary feel
        ssml_parts = []
        for i, para in enumerate(paragraphs):
            # Escape XML special characters
            safe = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            ssml_parts.append(safe)
            if i < len(paragraphs) - 1:
                ssml_parts.append('<break time="800ms"/>')

        ssml_body = " ".join(ssml_parts)
        ssml = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="es-MX">'
            f'<voice name="{vid}">'
            f'<prosody rate="-5%" pitch="+0Hz">'
            f'{ssml_body}'
            f'</prosody></voice></speak>'
        )

        async def _generate():
            communicate = edge_tts.Communicate(ssml, vid)
            await communicate.save(mp3_path)

        asyncio.run(_generate())

        if output_file.endswith(".wav"):
            ffmpeg_path = self._find_ffmpeg()
            if ffmpeg_path:
                try:
                    subprocess.run(
                        [ffmpeg_path, "-i", mp3_path, "-y", output_file],
                        capture_output=True, timeout=120
                    )
                    os.remove(mp3_path)
                except Exception:
                    shutil.move(mp3_path, output_file)
            else:
                shutil.move(mp3_path, output_file)
        else:
            shutil.move(mp3_path, output_file)

        return output_file

    def synthesize_with_timestamps(self, text, output_file=os.path.join(ROOT_DIR, ".mp", "audio.wav")):
        """Synthesize audio AND return word-level timestamps.

        Returns:
            (output_file, word_timestamps) where word_timestamps is a list of
            {"start": float_seconds, "end": float_seconds, "word": str} or None.
        """
        if self._provider == "edge_tts":
            return self._synthesize_edge_tts_with_timestamps(text, output_file)
        # KittenTTS has no word timing — synthesize normally, return None
        self._synthesize_kitten(text, output_file)
        return output_file, None

    def _synthesize_edge_tts_with_timestamps(self, text, output_file):
        """Edge-TTS synthesis capturing word-level boundary events."""
        import edge_tts
        import subprocess
        import shutil

        voice_id = EDGE_TTS_VOICES.get(self._voice, self._voice)
        mp3_path = output_file.rsplit(".", 1)[0] + ".mp3"
        word_timestamps = []

        async def _generate():
            communicate = edge_tts.Communicate(text, voice_id, boundary="WordBoundary")
            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    offset_s = chunk["offset"] / 10_000_000
                    duration_s = chunk["duration"] / 10_000_000
                    word_timestamps.append({
                        "start": offset_s,
                        "end": offset_s + duration_s,
                        "word": chunk["text"],
                    })
            with open(mp3_path, "wb") as f:
                for c in audio_chunks:
                    f.write(c)

        asyncio.run(_generate())

        # Convert mp3 → wav
        if output_file.endswith(".wav"):
            ffmpeg_path = self._find_ffmpeg()
            if ffmpeg_path:
                try:
                    subprocess.run(
                        [ffmpeg_path, "-i", mp3_path, "-y", output_file],
                        capture_output=True, timeout=60,
                    )
                    os.remove(mp3_path)
                except Exception:
                    shutil.move(mp3_path, output_file)
            else:
                shutil.move(mp3_path, output_file)
        else:
            shutil.move(mp3_path, output_file)

        return output_file, word_timestamps

    def _synthesize_edge_tts(self, text, output_file):
        """Edge-TTS synthesis (without word timestamps)."""
        path, _ = self._synthesize_edge_tts_with_timestamps(text, output_file)
        return path

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
