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

# Deep narrator voice for long-form documentary videos (Spain, neutral & authoritative)
LONG_VIDEO_NARRATOR = "es-ES-AlvaroNeural"


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

    def synthesize(self, text, output_file=os.path.join(ROOT_DIR, ".mp", "audio.wav"), voice_id=None):
        if self._provider == "edge_tts":
            return self._synthesize_edge_tts(text, output_file, voice_id=voice_id)
        return self._synthesize_kitten(text, output_file, voice_id=voice_id)

    def _synthesize_kitten(self, text, output_file, voice_id=None):
        import soundfile as sf
        voice = voice_id or self._voice
        audio = self._kitten_model.generate(text, voice=voice)
        sf.write(output_file, audio, self._kitten_sr)
        return output_file

    def synthesize_long(self, text, output_file, voice_id=None):
        import edge_tts
        import subprocess
        import shutil

        from compat import find_ffmpeg

        vid = voice_id or EDGE_TTS_VOICES.get(self._voice, self._voice)
        mp3_path = output_file.rsplit(".", 1)[0] + ".mp3"

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]
        narration_text = " ... ".join(paragraphs)

        async def _generate():
            communicate = edge_tts.Communicate(
                narration_text, vid,
                rate="-8%", pitch="-15Hz"
            )
            await communicate.save(mp3_path)

        asyncio.run(_generate())

        if output_file.endswith(".wav"):
            ffmpeg_path = find_ffmpeg()
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

    def synthesize_with_timestamps(self, text, output_file=os.path.join(ROOT_DIR, ".mp", "audio.wav"), voice_id=None, rate: str = "", pitch: str = ""):
        """Synthesize audio AND return word-level timestamps.

        Args:
            rate: Edge-TTS rate string (e.g. "-5%"). Empty → no modulation.
            pitch: Edge-TTS pitch string (e.g. "-8Hz"). Empty → no modulation.

        Returns:
            (output_file, word_timestamps) where word_timestamps is a list of
            {"start": float_seconds, "end": float_seconds, "word": str} or None.
        """
        if self._provider == "edge_tts":
            return self._synthesize_edge_tts_with_timestamps(text, output_file, voice_id=voice_id, rate=rate, pitch=pitch)
        # KittenTTS has no word timing — synthesize normally, return None
        self._synthesize_kitten(text, output_file, voice_id=voice_id)
        return output_file, None

    def _synthesize_edge_tts_with_timestamps(self, text, output_file, voice_id=None, rate: str = "", pitch: str = ""):
        """Edge-TTS synthesis capturing word-level boundary events."""
        import edge_tts
        import subprocess
        import shutil

        # Per-call voice override → fall back to instance voice → fall back to mapping.
        voice_id = voice_id or EDGE_TTS_VOICES.get(self._voice, self._voice)
        mp3_path = output_file.rsplit(".", 1)[0] + ".mp3"
        word_timestamps = []

        async def _generate():
            kwargs = {"boundary": "WordBoundary"}
            if rate:
                kwargs["rate"] = rate
            if pitch:
                kwargs["pitch"] = pitch
            communicate = edge_tts.Communicate(text, voice_id, **kwargs)
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

        from compat import find_ffmpeg
        if output_file.endswith(".wav"):
            ffmpeg_path = find_ffmpeg()
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

    def _synthesize_edge_tts(self, text, output_file, voice_id=None):
        """Edge-TTS synthesis (without word timestamps)."""
        path, _ = self._synthesize_edge_tts_with_timestamps(text, output_file, voice_id=voice_id)
        return path


