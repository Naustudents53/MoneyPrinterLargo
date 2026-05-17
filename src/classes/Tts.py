import os
import asyncio

from config import ROOT_DIR, get_tts_voice, get_tts_provider

# Edge-TTS voice mapping (natural-sounding Microsoft voices).
#
# The first 12 aliases are kept for backward compatibility: existing channels /
# config.json may store them by name. The selector in the webapp stores the full
# voice_id, so the broad Spanish catalogue below is keyed by descriptive
# country-tagged aliases (display only; lookups by voice_id fall through
# unchanged via EDGE_TTS_VOICES.get(value, value)).
EDGE_TTS_VOICES = {
    "Jasper": "en-US-GuyNeural",
    "Bella": "en-US-JennyNeural",
    "Luna": "en-US-AriaNeural",
    "Bruno": "en-US-BrianNeural",
    "Rosie": "en-US-AvaNeural",
    "Hugo": "en-GB-RyanNeural",
    "Kiki": "en-AU-NatashaNeural",
    "Leo": "en-US-ChristopherNeural",
    # Spanish - legacy aliases (do not rename: stored in existing configs)
    "Sofia": "es-MX-DaliaNeural",
    "Carlos": "es-MX-JorgeNeural",
    "Elena": "es-ES-ElviraNeural",
    "Pablo": "es-ES-AlvaroNeural",
    # Spanish - Spain (es-ES)
    "Ximena (ES)": "es-ES-XimenaNeural",
    # Spanish - Argentina (es-AR)
    "Elena (AR)": "es-AR-ElenaNeural",
    "Tomas (AR)": "es-AR-TomasNeural",
    # Spanish - Colombia (es-CO)
    "Gonzalo (CO)": "es-CO-GonzaloNeural",
    "Salome (CO)": "es-CO-SalomeNeural",
    # Spanish - Chile (es-CL)
    "Catalina (CL)": "es-CL-CatalinaNeural",
    "Lorenzo (CL)": "es-CL-LorenzoNeural",
    # Spanish - Peru (es-PE)
    "Alex (PE)": "es-PE-AlexNeural",
    "Camila (PE)": "es-PE-CamilaNeural",
    # Spanish - Venezuela (es-VE)
    "Paola (VE)": "es-VE-PaolaNeural",
    "Sebastian (VE)": "es-VE-SebastianNeural",
    # Spanish - United States (es-US, neutral Latino)
    "Alonso (US)": "es-US-AlonsoNeural",
    "Paloma (US)": "es-US-PalomaNeural",
    # Spanish - Central America & Caribbean
    "Maria (CR)": "es-CR-MariaNeural",
    "Juan (CR)": "es-CR-JuanNeural",
    "Marta (GT)": "es-GT-MartaNeural",
    "Andres (GT)": "es-GT-AndresNeural",
    "Karla (HN)": "es-HN-KarlaNeural",
    "Carlos (HN)": "es-HN-CarlosNeural",
    "Lorena (SV)": "es-SV-LorenaNeural",
    "Rodrigo (SV)": "es-SV-RodrigoNeural",
    "Margarita (PA)": "es-PA-MargaritaNeural",
    "Roberto (PA)": "es-PA-RobertoNeural",
    "Yolanda (NI)": "es-NI-YolandaNeural",
    "Federico (NI)": "es-NI-FedericoNeural",
    "Ramona (DO)": "es-DO-RamonaNeural",
    "Emilio (DO)": "es-DO-EmilioNeural",
    "Karina (PR)": "es-PR-KarinaNeural",
    "Victor (PR)": "es-PR-VictorNeural",
    "Belkys (CU)": "es-CU-BelkysNeural",
    "Manuel (CU)": "es-CU-ManuelNeural",
    # Spanish - South America (remaining)
    "Andrea (EC)": "es-EC-AndreaNeural",
    "Luis (EC)": "es-EC-LuisNeural",
    "Sofia (BO)": "es-BO-SofiaNeural",
    "Marcelo (BO)": "es-BO-MarceloNeural",
    "Tania (PY)": "es-PY-TaniaNeural",
    "Mario (PY)": "es-PY-MarioNeural",
    "Valentina (UY)": "es-UY-ValentinaNeural",
    "Mateo (UY)": "es-UY-MateoNeural",
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
        """
        Synthesize long-form text for documentary-style narration.
        Uses a deep, slow voice with pauses between paragraphs.
        """
        import edge_tts
        import subprocess
        import shutil

        vid = voice_id or EDGE_TTS_VOICES.get(self._voice, self._voice)
        mp3_path = output_file.rsplit(".", 1)[0] + ".mp3"

        # Add natural pauses between paragraphs for documentary feel
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]
        # Join with ellipsis pause markers — edge_tts treats these as natural pauses
        narration_text = " ... ".join(paragraphs)

        async def _generate():
            # Deep narrator: slower rate, lower pitch for gravitas
            communicate = edge_tts.Communicate(
                narration_text, vid,
                rate="-8%", pitch="-15Hz"
            )
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

    def _synthesize_edge_tts(self, text, output_file, voice_id=None):
        """Edge-TTS synthesis (without word timestamps)."""
        path, _ = self._synthesize_edge_tts_with_timestamps(text, output_file, voice_id=voice_id)
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
