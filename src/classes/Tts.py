import os
import asyncio

from config import (
    ROOT_DIR,
    get_tts_voice,
    get_tts_provider,
    get_tts_language,
    get_tts_speaker_wav,
    get_xtts_model,
    get_xtts_device,
    get_openvoice_base_speaker,
    get_openvoice_checkpoints_dir,
)

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


def _resolve_device(pref: str) -> str:
    """Resolve 'auto' / 'cuda' / 'cpu' device preference."""
    if pref and pref != "auto":
        return pref
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


class TTS:
    def __init__(self) -> None:
        self._provider = get_tts_provider()
        self._voice = get_tts_voice()
        self._language = get_tts_language()
        self._speaker_wav = get_tts_speaker_wav()

        # Lazy-loaded model handles
        self._kitten_model = None
        self._kitten_sr = 24000
        self._xtts_model = None
        self._openvoice_base = None
        self._openvoice_converter = None
        self._openvoice_target_se = None

        if self._provider == "kittentts":
            self._init_kitten()

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    def synthesize(self, text, output_file=os.path.join(ROOT_DIR, ".mp", "audio.wav"), voice_id=None):
        if self._provider == "edge_tts":
            return self._synthesize_edge_tts(text, output_file, voice_id=voice_id)
        if self._provider == "xtts_v2":
            return self._synthesize_xtts(text, output_file, voice_id=voice_id)
        if self._provider == "openvoice_v2":
            return self._synthesize_openvoice(text, output_file, voice_id=voice_id)
        return self._synthesize_kitten(text, output_file, voice_id=voice_id)

    def synthesize_long(self, text, output_file, voice_id=None):
        """Long-form narration. Edge-TTS gets paragraph chunking + slowed cadence;
        neural cloners (XTTS / OpenVoice) just synthesize directly."""
        if self._provider == "xtts_v2":
            return self._synthesize_xtts(text, output_file, voice_id=voice_id)
        if self._provider == "openvoice_v2":
            return self._synthesize_openvoice(text, output_file, voice_id=voice_id)
        return self._synthesize_edge_long(text, output_file, voice_id=voice_id)

    def synthesize_with_timestamps(self, text, output_file=os.path.join(ROOT_DIR, ".mp", "audio.wav"), voice_id=None, rate: str = "", pitch: str = ""):
        """Synthesize audio AND return word-level timestamps (Edge-TTS only).

        Other providers fall back to plain synthesis with timestamps=None.
        """
        if self._provider == "edge_tts":
            return self._synthesize_edge_tts_with_timestamps(text, output_file, voice_id=voice_id, rate=rate, pitch=pitch)
        path = self.synthesize(text, output_file, voice_id=voice_id)
        return path, None

    # ------------------------------------------------------------------ #
    # KittenTTS                                                          #
    # ------------------------------------------------------------------ #
    def _init_kitten(self) -> None:
        try:
            import soundfile  # noqa: F401
            from kittentts import KittenTTS as KittenModel
            self._kitten_model = KittenModel("KittenML/kitten-tts-mini-0.8")
        except ImportError:
            print("[WARNING] KittenTTS not available, falling back to edge-tts")
            self._provider = "edge_tts"

    def _synthesize_kitten(self, text, output_file, voice_id=None):
        import soundfile as sf
        voice = voice_id or self._voice
        audio = self._kitten_model.generate(text, voice=voice)
        sf.write(output_file, audio, self._kitten_sr)
        return output_file

    # ------------------------------------------------------------------ #
    # Coqui XTTS v2                                                      #
    # ------------------------------------------------------------------ #
    def _ensure_xtts(self) -> None:
        if self._xtts_model is not None:
            return
        # torchcodec (required by Coqui TTS on torch>=2.9) needs FFmpeg shared
        # libraries (avcodec, avformat, etc.) reachable on Windows. Bundle them
        # under models/ffmpeg/ and register before any TTS import.
        ffmpeg_dll_dir = os.path.join(ROOT_DIR, "models", "ffmpeg")
        if os.path.isdir(ffmpeg_dll_dir):
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(ffmpeg_dll_dir)
                except OSError:
                    pass
            os.environ["PATH"] = ffmpeg_dll_dir + os.pathsep + os.environ.get("PATH", "")
        try:
            from TTS.api import TTS as CoquiTTS
        except ImportError as e:
            raise RuntimeError(
                "XTTS v2 requires the 'TTS' package. Install with: pip install coqui-tts"
            ) from e

        device = _resolve_device(get_xtts_device())
        # XTTS v2 has non-commercial license terms; auto-accept env flag for headless runs.
        os.environ.setdefault("COQUI_TOS_AGREED", "1")
        model = CoquiTTS(get_xtts_model())
        try:
            model.to(device)
        except Exception:
            pass
        self._xtts_model = model

    def _synthesize_xtts(self, text: str, output_file: str, voice_id=None) -> str:
        self._ensure_xtts()
        speaker_wav = voice_id or self._speaker_wav
        if not speaker_wav or not os.path.isfile(speaker_wav):
            raise RuntimeError(
                f"XTTS v2 needs a reference audio file (6-30s). "
                f"Set 'tts_speaker_wav' in config.json. Got: {speaker_wav!r}"
            )

        # XTTS writes WAV natively; if a non-wav target is requested, write WAV then transcode.
        wav_path = output_file if output_file.endswith(".wav") else output_file.rsplit(".", 1)[0] + ".wav"
        self._xtts_model.tts_to_file(
            text=text,
            speaker_wav=speaker_wav,
            language=self._language,
            file_path=wav_path,
            split_sentences=True,
        )

        if wav_path != output_file:
            self._transcode(wav_path, output_file)
            try:
                os.remove(wav_path)
            except OSError:
                pass
        return output_file

    # ------------------------------------------------------------------ #
    # OpenVoice v2 (MeloTTS base + ToneColorConverter)                   #
    # ------------------------------------------------------------------ #
    def _ensure_openvoice(self) -> None:
        if self._openvoice_base is not None and self._openvoice_converter is not None:
            return
        try:
            from melo.api import TTS as MeloTTS
            from openvoice.api import ToneColorConverter
            from openvoice import se_extractor
        except ImportError as e:
            raise RuntimeError(
                "OpenVoice v2 requires 'openvoice' and 'melo'. Install via:\n"
                "  pip install git+https://github.com/myshell-ai/MeloTTS.git\n"
                "  pip install git+https://github.com/myshell-ai/OpenVoice.git\n"
                "  python -m unidic download"
            ) from e

        device = _resolve_device(get_xtts_device())
        ckpt_dir = get_openvoice_checkpoints_dir()
        converter_cfg = os.path.join(ckpt_dir, "converter", "config.json")
        converter_ckpt = os.path.join(ckpt_dir, "converter", "checkpoint.pth")
        if not (os.path.isfile(converter_cfg) and os.path.isfile(converter_ckpt)):
            raise RuntimeError(
                f"OpenVoice converter checkpoints not found under {ckpt_dir}. "
                f"Download from https://huggingface.co/myshell-ai/OpenVoiceV2 "
                f"and place under {ckpt_dir}/converter/."
            )

        speaker_wav = self._speaker_wav
        if not speaker_wav or not os.path.isfile(speaker_wav):
            raise RuntimeError(
                f"OpenVoice v2 needs a reference audio file. "
                f"Set 'tts_speaker_wav' in config.json. Got: {speaker_wav!r}"
            )

        base_lang = self._language.upper() if len(self._language) == 2 else "ES"
        self._openvoice_base = MeloTTS(language=base_lang, device=device)
        self._openvoice_converter = ToneColorConverter(converter_cfg, device=device)
        self._openvoice_converter.load_ckpt(converter_ckpt)

        se_cache_dir = os.path.join(ROOT_DIR, ".mp", "openvoice_se")
        os.makedirs(se_cache_dir, exist_ok=True)
        target_se, _ = se_extractor.get_se(
            speaker_wav, self._openvoice_converter, vad=True
        )
        self._openvoice_target_se = target_se

    def _synthesize_openvoice(self, text: str, output_file: str, voice_id=None) -> str:
        self._ensure_openvoice()
        import tempfile

        base = self._openvoice_base
        speaker_id_str = voice_id or get_openvoice_base_speaker()
        speaker_ids = base.hps.data.spk2id
        if speaker_id_str not in speaker_ids:
            available = ", ".join(speaker_ids.keys())
            raise RuntimeError(
                f"OpenVoice base speaker {speaker_id_str!r} not in MeloTTS model. "
                f"Available: {available}"
            )
        speaker_id = speaker_ids[speaker_id_str]

        # Source SE bundled with OpenVoice for the chosen base language.
        ckpt_dir = get_openvoice_checkpoints_dir()
        source_se_path = os.path.join(
            ckpt_dir, "base_speakers", "ses", f"{speaker_id_str.lower()}.pth"
        )
        if not os.path.isfile(source_se_path):
            raise RuntimeError(
                f"Source speaker embedding not found: {source_se_path}. "
                f"Place base_speakers/ses/*.pth from the OpenVoiceV2 release."
            )
        import torch
        source_se = torch.load(source_se_path, map_location="cpu")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=os.path.join(ROOT_DIR, ".mp")) as tmp:
            tmp_wav = tmp.name
        try:
            base.tts_to_file(text, speaker_id, tmp_wav, speed=1.0)
            wav_path = output_file if output_file.endswith(".wav") else output_file.rsplit(".", 1)[0] + ".wav"
            self._openvoice_converter.convert(
                audio_src_path=tmp_wav,
                src_se=source_se,
                tgt_se=self._openvoice_target_se,
                output_path=wav_path,
                message="@MoneyPrinterLargo",
            )
            if wav_path != output_file:
                self._transcode(wav_path, output_file)
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
        finally:
            try:
                os.remove(tmp_wav)
            except OSError:
                pass
        return output_file

    # ------------------------------------------------------------------ #
    # Edge-TTS                                                           #
    # ------------------------------------------------------------------ #
    def _synthesize_edge_long(self, text, output_file, voice_id=None):
        import edge_tts
        import shutil

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
            if not self._transcode(mp3_path, output_file):
                shutil.move(mp3_path, output_file)
            else:
                try:
                    os.remove(mp3_path)
                except OSError:
                    pass
        else:
            shutil.move(mp3_path, output_file)
        return output_file

    def _synthesize_edge_tts_with_timestamps(self, text, output_file, voice_id=None, rate: str = "", pitch: str = ""):
        """Edge-TTS synthesis capturing word-level boundary events."""
        import edge_tts
        import shutil

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

        if output_file.endswith(".wav"):
            if not self._transcode(mp3_path, output_file):
                shutil.move(mp3_path, output_file)
            else:
                try:
                    os.remove(mp3_path)
                except OSError:
                    pass
        else:
            shutil.move(mp3_path, output_file)
        return output_file, word_timestamps

    def _synthesize_edge_tts(self, text, output_file, voice_id=None):
        path, _ = self._synthesize_edge_tts_with_timestamps(text, output_file, voice_id=voice_id)
        return path

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _transcode(src: str, dst: str) -> bool:
        """Transcode audio via ffmpeg. Returns True on success."""
        import subprocess
        from compat import find_ffmpeg
        ffmpeg_path = find_ffmpeg()
        if not ffmpeg_path:
            return False
        try:
            subprocess.run(
                [ffmpeg_path, "-i", src, "-y", dst],
                capture_output=True, timeout=120,
            )
            return os.path.isfile(dst)
        except Exception:
            return False
