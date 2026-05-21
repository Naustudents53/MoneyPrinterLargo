import re
import base64
import json
import time
import os
import subprocess
import requests
import assemblyai as aai

# Pillow 10+ removed Image.ANTIALIAS, but moviepy 1.0.3 still references it.
# Patch the alias before moviepy is imported, otherwise resize() / write_videofile()
# raise AttributeError and the long-video combine pipeline fails.
from PIL import Image as _PIL_Image
if not hasattr(_PIL_Image, "ANTIALIAS"):
    _PIL_Image.ANTIALIAS = _PIL_Image.LANCZOS

from utils import *
from cache import *
from .Tts import TTS
from .Retention import CosmicRetentionEngine
from .MaxRetention import MaxRetentionEngine, is_max_retention, normalize_retention_mode
from .RetentionLab import RetentionLab
from .NarrationVoice import NarrationVoice
from llm_provider import generate_text
from config import *
from status import *
from uuid import uuid4
from constants import *
from typing import List
from moviepy.editor import *
from termcolor import colored
from selenium import webdriver
from moviepy.video.fx.all import crop
from moviepy.config import change_settings
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from moviepy.video.tools.subtitles import SubtitlesClip
from webdriver_manager.firefox import GeckoDriverManager
from datetime import datetime

# Set ImageMagick Path
change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})


_PHOTO_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for", "with",
    "about", "from", "by", "is", "was", "were", "are", "be", "been", "being",
    "his", "her", "its", "their", "our", "your", "this", "that", "these", "those",
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "u",
    "sobre", "con", "por", "para", "es", "era", "fue", "su", "sus", "del",
}


_UNICODE_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_UNICODE_TOKEN_RE = re.compile(r"[\w'-]+", re.UNICODE)

LONG_VIDEO_TARGET_MIN_WORDS = 2000
LONG_VIDEO_TARGET_MAX_WORDS = 2200
LONG_VIDEO_ESTIMATED_WPM = 140


def _unicode_words(text: str) -> list[str]:
    """Return alphabetic words, including accented characters, without fragile ranges."""
    return _UNICODE_WORD_RE.findall(text or "")


def _unicode_tokens(text: str) -> list[str]:
    """Return word-like tokens that may include digits, apostrophes or hyphens."""
    return _UNICODE_TOKEN_RE.findall(text or "")


def _capitalized_unicode_tokens(text: str) -> list[str]:
    return [
        tok for tok in _unicode_tokens(text)
        if len(tok) > 2 and tok[0].isupper()
    ]


# Generic science/topic words that are NOT distinctive enough to anchor a
# search result on the right subject. A result whose title only matches these
# is considered off-topic â€” e.g. a video about TON 618 must NOT accept any
# photo whose only overlap is "black hole" or "galaxy". The relevance filter
# requires at least one truly distinctive token (proper noun / unique term)
# on top of these. Keep this list conservative â€” adding a real proper noun
# here would silently disable relevance checks for that subject.
_GENERIC_TOPIC_TOKENS = {
    # Generic science / cosmos adjectives and qualifiers
    "ciencia", "cientifico", "cientifica", "cientificos", "cientificas",
    "science", "scientific",
    "universo", "universe", "cosmos", "cosmico", "cosmica", "cosmic",
    "espacio", "space", "espacial", "spatial",
    "astronomia", "astronomy", "astronomico", "astronomica", "astronomical",
    "astrofisica", "astrophysics", "astrofisico", "astrophysical",
    "fisica", "physics", "fisico", "physical",
    "matematicas", "mathematics", "matematico",
    # Generic celestial bodies (alone they don't identify a target)
    "estrella", "estrellas", "star", "stars",
    "planeta", "planetas", "planet", "planets",
    "galaxia", "galaxias", "galaxy", "galaxies",
    "luna", "lunas", "moon", "moons",
    "asteroide", "asteroides", "asteroid", "asteroids",
    "cometa", "cometas", "comet", "comets",
    "nebulosa", "nebulosas", "nebula", "nebulae",
    "constelacion", "constelaciones", "constellation", "constellations",
    "agujero", "agujeros", "hole", "holes",   # "agujero negro" is the phrase; alone, generic
    "negro", "negra", "black",
    # Generic phenomena / scales
    "explosion", "explosiones", "explosion", "explosions",
    "luz", "light", "energia", "energy", "fuerza", "force",
    "gravedad", "gravity", "tiempo", "time",
    "materia", "matter", "antimateria", "antimatter",
    "onda", "ondas", "wave", "waves", "particula", "particulas", "particle", "particles",
    "atomo", "atomos", "atom", "atoms", "molecula", "molecules",
    # Generic instruments / agents
    "telescopio", "telescopios", "telescope", "telescopes",
    "sonda", "sondas", "probe", "probes", "satelite", "satelites", "satellite", "satellites",
    "nave", "naves", "spacecraft", "rocket", "cohete", "cohetes",
    "astronauta", "astronautas", "astronaut", "astronauts",
    "cientifico", "scientist", "investigador", "researcher",
    # Generic places / scales
    "mundo", "world", "tierra", "earth", "sistema", "system",
    "via", "lactea",   # alone too short; "VÃ­a LÃ¡ctea" is the proper noun (kept distinctive elsewhere)
    "orbita", "orbit", "atmosfera", "atmosphere",
    # Sizes / qualifiers
    "grande", "great", "gigante", "giant", "enorme", "huge", "masivo", "massive",
    "supermasivo", "supermassive",
    "pequeno", "small", "diminuto", "tiny",
    "antiguo", "antigua", "ancient", "old", "primitivo", "primordial",
    "moderno", "modern", "nuevo", "new",
    "vida", "life", "muerte", "death",
    # Visual/image meta-terms
    "imagen", "image", "foto", "photo", "vista", "view", "escena", "scene",
    "render", "ilustracion", "illustration",
}


# Per-channel hook style presets used by `generate_script`. Each entry is
# (style_name, hook_example). One style is picked at random per script so
# every short doesn't open the same way. Configure on the account JSON via
# `hook_profile` â€” falls back to "educational" if missing or unknown.
HOOK_PROFILES: dict = {
    "educational": [
        ("You-are-there immersion", 'Abre con una escena inmersiva en segunda persona que coloca al espectador en el momento exacto: "En este preciso instante, hace [tiempo], [lugar concreto]. [Escena sensorial breve: quÃ© se ve, quÃ© se escucha, quÃ© ocurre]. Nada de lo que conoces hoy existirÃ­a si esto hubiera salido distinto."'),
        ("Impossible true fact", 'Arranca con un hecho que suena falso pero es 100% real, enunciado como afirmaciÃ³n rotunda sin pregunta: "[Hecho completamente contraintuitivo sobre el tema, enunciado como verdad absoluta]. No es ficciÃ³n. OcurriÃ³ de verdad."'),
        ("Scale of time awe", 'Usa la escala del tiempo para crear vÃ©rtigo existencial: "Si comprimieras toda la historia de [la Tierra / la humanidad / la civilizaciÃ³n] en [una hora / un aÃ±o / un dÃ­a], [el evento del video] ocurrirÃ­a exactamente en [momento preciso]. Todo lo que vino despuÃ©s cambiÃ³ en segundos."'),
        ("Survival on the edge", 'Perfecto para prehistoria y eventos de extinciÃ³n: "Hubo un momento en que [especie / civilizaciÃ³n / grupo] Ã©ramos menos de [nÃºmero pequeÃ±o]. Un solo error, una sola tormenta, una sola mala decisiÃ³n, y esta historia no existirÃ­a. Nosotros tampoco."'),
        ("The consequence chain", 'Revela la cadena de consecuencias de un solo evento: "Sin [evento o decisiÃ³n del tema], [cosa completamente familiar hoy] no existirÃ­a. El mundo entero serÃ­a diferente. Y todo empezÃ³ con algo que casi nadie recuerda."'),
        ("Time-warp scene drop", 'Suelta al espectador directamente en el momento histÃ³rico sin preÃ¡mbulo: "[AÃ±o o Ã©poca exacta], [lugar preciso]. [Escena de dos frases: lo que ocurre, lo que estÃ¡ en juego]. Nadie en ese momento sabÃ­a que estaban cambiando el mundo."'),
        ("The reversal", 'Destruye una creencia popular con una afirmaciÃ³n directa: "Durante [siglos / dÃ©cadas / toda la historia], todos creyeron que [idea popular sobre el tema]. Estaban completamente equivocados. La realidad era algo que nadie querÃ­a aceptar."'),
        ("Discovery shock", 'Arranca desde el momento del descubrimiento arqueolÃ³gico o cientÃ­fico: "Cuando [arqueÃ³logos / cientÃ­ficos / exploradores] abrieron [lugar o hallazgo del tema], lo que encontraron dentro contradecÃ­a todo lo que creÃ­amos saber. Algunos de ellos nunca volvieron a ser los mismos."'),
        ("The forgotten turning point", 'Rescata un momento decisivo que la historia olvidÃ³: "La historia recuerda [evento famoso o persona famosa]. Pero olvidÃ³ por completo el momento en que [evento clave del tema] lo hizo posible. Sin eso, nada de lo que siguiÃ³ habrÃ­a ocurrido."'),
        ("Cultural lens flip", '"Para nosotros serÃ­a [reacciÃ³n moderna: impensable, una locura, un crimen]. Pero en [Ã©poca o civilizaciÃ³n], era exactamente lo contrario: [normalidad opuesta]. Y tenÃ­an razones que hoy casi nadie conoce."'),
        ("Lost world reveal", 'Abre describiendo un mundo radicalmente diferente al nuestro: "Hace [tiempo], existÃ­a un mundo tan distinto al nuestro que si pudieras verlo hoy no reconocerÃ­as ni el cielo. [Detalle concreto impactante del tema]. Ese mundo desapareciÃ³, y lo que lo destruyÃ³ tambiÃ©n creÃ³ todo lo que somos."'),
        ("The specific moment", 'Ultra-precisiÃ³n temporal para crear sensaciÃ³n de inevitabilidad: "El [fecha o momento exacto], en [lugar especÃ­fico], [persona o grupo] tomÃ³ [decisiÃ³n o acciÃ³n concreta]. En ese instante, sin saberlo, decidiÃ³ el destino de [civilizaciÃ³n / especie / era]."'),
    ],
    # Cosmic mystery / awe-driven storytelling. Designed to pull the viewer in
    # with an unsolved cosmic puzzle, an eerie astronomical observation, or a
    # mind-bending consequence of physics.
    "storytelling": [
        ("Cosmic anomaly opener", '"Detectaron una seÃ±al que nadie pudo explicar." o "Lo que vieron en aquella imagen del Webb no deberÃ­a existir."'),
        ("In medias res observation", '"Eran las 3:14 AM cuando el detector se disparÃ³." o "Aquella noche en el observatorio, el cielo cambiÃ³ y ningÃºn protocolo lo habÃ­a previsto."'),
        ("Time-warp cosmic opener", '"Era el aÃ±o 1977, y un mensaje del cosmos llegÃ³ a la Tierra." o "Hace 13.800 millones de aÃ±os, en menos de un segundo, todo cambiÃ³."'),
        ("Sole-survivor probe cliffhanger", '"De las dos sondas que cruzaron el sistema solar, solo una sigue enviando seÃ±ales. Esta es su historia."'),
        ("Disturbing discovery", '"Lo que detectaron en el centro de la galaxia no deberÃ­a estar ahÃ­." o "Cuando analizaron los datos, ya era demasiado tarde para fingir que no existÃ­a."'),
        ("Visceral cosmic imperative", '"No apartes la mirada del cielo. Eso fue lo Ãºltimo que dijo antes de..." o "Nunca debieron apuntar el telescopio a esa coordenada."'),
        ("Lost-signal epic", '"Una seÃ±al entera apareciÃ³ una sola vez, durÃ³ 72 segundos, y nunca volviÃ³ a escucharse."'),
        ("Cosmic quest twist", '"Buscaban un planeta habitable. Lo que encontraron fue infinitamente mÃ¡s extraÃ±o."'),
        ("Forbidden observation", '"Estos datos se discutÃ­an en susurros entre astrÃ³nomos, y quienes los publicaban se quedaban sin financiaciÃ³n."'),
        ("Last transmission testimony", '"Las Ãºltimas palabras que enviÃ³ la sonda antes de cruzar el horizonte fueron estas..."'),
    ],
}


# Narrative roles for the 10 sections of a long-form documentary. Designed to
# front-load engagement (sections 1-2 act as the "first 5 min hook engine")
# and manage open loops across the rest of the video. Series-defined themes
# (via `series.section_themes` of exactly 10 entries) override these defaults.
#
# Index -> minute (approx, at 140 wpm and ~175 words/section):
#   S1  about min 1-2   immersive vignette (closes nothing, opens visual hook)
#   S2  about min 2-4   mystery pivot (plants the MAIN loop, paid off at S9)
#   S3  about min 4-5   first partial revelation + LIKE-BREAK at the opening
#   S4  about min 5-7   backstory / how-we-got-here
#   S5  about min 7-8   escalation / second hook
#   S6  about min 8-10  reversal (kills a popular belief)
#   S7  about min 10-11 human element (anecdote, slower beat)
#   S8  about min 11-13 unexpected modern connection
#   S9  about min 13-14 climax, pays off the MAIN loop from S2
#   S10 about min 14-15 legacy / consequences
LONG_VIDEO_SECTION_THEMES: list[str] = [
    # S1
    "ViÃ±eta inmersiva: una escena SENSORIAL concreta del momento o lugar mÃ¡s cinematogrÃ¡fico del tema. Mete al espectador DENTRO de la escena con detalles concretos (quÃ© se ve, quÃ© se oye, quÃ© se huele, quiÃ©n estÃ¡ ahÃ­). NO expliques aÃºn el contexto general â€” la escena habla sola. Termina dejando una imagen visual potente que enganche.",
    # S2
    "Pivote misterio â€” siembra el LOOP PRINCIPAL del video. Introduce UNA contradicciÃ³n especÃ­fica, anomalÃ­a o pregunta sin respuesta que el espectador no podrÃ¡ dejar pasar (algo no encaja, alguien hizo algo inexplicable, un detalle que rompe la versiÃ³n oficial). Plantea la pregunta con claridad, promÃ©tele al espectador que la respuesta llega mÃ¡s adelante, y NO la respondas todavÃ­a. Puedes sembrar 1 loop secundario adicional mÃ¡s pequeÃ±o.",
    # S3
    "Respuesta parcial CON LIKE-BREAK al inicio. ABRE con 1-2 oraciones cÃ¡lidas y orgÃ¡nicas pidiendo al espectador que dÃ© 'me gusta' si estÃ¡ disfrutando el video â€” debe sonar natural, no a publicidad ni a lista de instrucciones, como un narrador que confÃ­a y agradece. DESPUÃ‰S, cierra un loop SECUNDARIO pequeÃ±o (NUNCA el loop principal sembrado en la secciÃ³n anterior â€” ese debe quedar abierto hasta el clÃ­max) y aprovecha la energÃ­a para abrir un nuevo loop mÃ¡s profundo.",
    # S4
    "Backstory cinemÃ¡tica: cÃ³mo se llegÃ³ hasta el momento que abriÃ³ el video. Una escena concreta del ORIGEN (fecha exacta, lugar especÃ­fico, personaje real) que explica por quÃ© pasÃ³ lo que pasÃ³. MantÃ©n el tono narrativo y sensorial, NO expositivo de libro de texto. Sigue sin tocar el loop principal.",
    # S5
    "Escalada â€” segundo gancho de retenciÃ³n. Las apuestas suben. Aparecen complicaciones, obstÃ¡culos, o un giro intermedio inesperado. Este es el punto donde se reactiva al espectador que estaba perdiendo interÃ©s: un nuevo elemento sorprendente, una tensiÃ³n que no veÃ­a venir, o el cierre dramÃ¡tico de un loop secundario. Si abres otra pregunta aquÃ­, serÃ¡ respondida pronto, no al final.",
    # S6
    "Reversal: destruye una creencia popular que el espectador probablemente trajo al video. 'Durante aÃ±os todos creyeron X. Estaban equivocados. La realidad era Y.' Una idea fuerte, contraintuitiva, bien sostenida con un hecho concreto, nombre, fecha o cita. El espectador debe sentir que aprendiÃ³ algo que cambia su mapa mental.",
    # S7
    "Elemento humano: baja el ritmo deliberadamente. Una anÃ©cdota Ã­ntima, un testimonio, un detalle personal de alguien involucrado en la historia. Apela a la emociÃ³n â€” miedo, asombro, dolor, esperanza, vergÃ¼enza. Un respiro narrativo antes del clÃ­max, pero cargado de carga emocional. El espectador debe sentir que conoce a alguien.",
    # S8
    "ConexiÃ³n inesperada con el presente: un paralelismo con algo familiar HOY. Por quÃ© esto le importa al espectador en su vida actual. Una resonancia moderna â€” costumbre que sigue, palabra que usamos, tecnologÃ­a que heredamos, error que repetimos. Cierra preparando el terreno para el clÃ­max: el lector debe sentir que la respuesta del loop principal estÃ¡ cerca.",
    # S9
    "ClÃ­max â€” PAGO DEL LOOP PRINCIPAL. Por fin la respuesta a la pregunta sembrada en la secciÃ³n 2. Este es el momento mÃ¡s impactante de toda la narraciÃ³n. Construye tensiÃ³n en las primeras 2-3 oraciones, revela el dato/giro/verdad concreta en el medio, y deja al espectador procesando en las Ãºltimas. AsegÃºrate de cerrar de forma satisfactoria el loop principal â€” no dejes la pregunta abierta.",
    # S10
    "Legado y consecuencias: quÃ© quedÃ³ despuÃ©s, quÃ© cambiÃ³, quÃ© seguimos viendo hoy gracias a (o por culpa de) lo que pasÃ³. Conecta el pasado del tema con el presente del espectador. Prepara emocionalmente al espectador para el cierre â€” esta secciÃ³n NO debe abrir loops nuevos, debe asentar lo aprendido.",
]


# Visual context anchoring is now niche-agnostic and computed per-video by
# `_get_context_profile()` â€” see that method. The LLM is asked once per video
# to derive a setting + visual anchors + things-to-avoid brief from the
# channel niche + topic + script, and that brief is injected into image-prompt
# generation. This replaces the previous hardcoded CIVILIZATIONS dict, which
# only covered ~17 historical eras and pushed every channel toward
# civilization-flavored content. The new approach works for any niche
# (history, science, finance, sports, food, tech, modern stories, etc.).


# Fallback visual style for Shorts when the channel has no `image_style` configured.
# Long videos still use domain detection + per-channel style; this only kicks
# in for shorts that would otherwise have no style at all.
SHORTS_FIXED_STYLE: str = (
    "ultra-realistic astrophotography aesthetic, James Webb / Hubble / Cassini / Voyager "
    "deep-space imagery quality, true-to-data nebula colors and cosmic dust textures, "
    "physically faithful gas, plasma and ice rendering, sharp star fields with diffraction spikes, "
    "accurate galaxy structures and rotation, photographic realism in instruments and probes "
    "(gold thermal foil, antenna dishes, solar panels), real EMU/ACES astronaut suits, "
    "scientifically grounded planetary surfaces and atmospheres, "
    "no fictional planets or moons, no neon fantasy nebulae, no sci-fi spaceship art, "
    "no anime, no cartoon, no painterly stylization, no chromatic-aberration filters"
)


class YouTube:
    """
    Class for YouTube Automation.

    Steps to create a YouTube Short:
    1. Generate a topic [DONE]
    2. Generate a script [DONE]
    3. Generate metadata (Title, Description, Tags) [DONE]
    4. Generate AI Image Prompts [DONE]
    4. Generate Images based on generated Prompts [DONE]
    5. Convert Text-to-Speech [DONE]
    6. Show images each for n seconds, n: Duration of TTS / Amount of images [DONE]
    7. Combine Concatenated Images with the Text-to-Speech [DONE]
    """

    def __init__(
        self,
        account_uuid: str,
        account_nickname: str,
        fp_profile_path: str,
        niche: str,
        language: str,
        image_style: str = "",
        short_voice: str = "",
        long_voice: str = "",
        hook_profile: str = "",
        voice_drama: bool = False,
        target_duration_seconds: int | None = None,
        retention_mode: str = "",
    ) -> None:
        """
        Constructor for YouTube Class.

        Args:
            account_uuid (str): The unique identifier for the YouTube account.
            account_nickname (str): The nickname for the YouTube account.
            fp_profile_path (str): Path to the firefox profile that is logged into the specificed YouTube Account.
            niche (str): The niche of the provided YouTube Channel.
            language (str): The language of the Automation.
            image_style (str): Optional per-channel style suffix appended to AI image prompts.
            short_voice (str): Optional Edge-TTS voice ID (or alias) for shorts narration.
            long_voice (str): Optional Edge-TTS voice ID (or alias) for long-video narration.
            hook_profile (str): Optional hook profile name (see HOOK_PROFILES). Falls back to "educational".
            retention_mode (str): Optional per-run creative mode. "maxima_retencion" enables tighter Shorts.

        Returns:
            None
        """
        self._account_uuid: str = account_uuid
        self._account_nickname: str = account_nickname
        # Fall back to the global default in config.json when the per-account
        # profile is missing â€” re-uploads from old accounts left this empty.
        if not fp_profile_path or not str(fp_profile_path).strip():
            try:
                fp_profile_path = get_firefox_profile_path() or ""
            except Exception:
                fp_profile_path = ""
            if fp_profile_path:
                info(f" => Using global firefox_profile from config.json: {fp_profile_path}")
        self._fp_profile_path: str = fp_profile_path
        self._niche: str = niche
        self._language: str = language
        self._image_style: str = (image_style or "").strip()
        self._short_voice: str = (short_voice or "").strip()
        self._long_voice: str = (long_voice or "").strip()
        self._hook_profile: str = (hook_profile or "").strip().lower()
        self._voice_drama: bool = bool(voice_drama)
        self._retention_mode: str = normalize_retention_mode(retention_mode)

        # Target Short duration â†’ drives sentence count, target word count,
        # and image count. Resolved through a single source of truth so we
        # never have to keep two preset tables in sync.
        from classes.duration_presets import resolve_short_duration
        if target_duration_seconds is not None:
            d, s, w, n = resolve_short_duration(target_duration_seconds)
        else:
            d, s, w, n = (None, None, None, None)
        if is_max_retention(self._retention_mode):
            max_preset = MaxRetentionEngine.duration_preset(d or 60)
            if max_preset:
                d = d or 60
                s, w, n = max_preset.sentences, max_preset.words, max_preset.images
        self._target_duration_seconds: int | None = d
        self._sentence_length_override: int | None = s
        self._target_word_count: int | None = w
        self._n_prompts_override: int | None = n

        self.images = []
        self._used_stock_urls: set = set()
        self.word_timestamps = None
        self.thumbnail_path: str = ""
        self.active_series: dict = None
        self.retention_preflight: dict = {}
        self.retention_hook_lab: dict = {}
        self.visual_beat_map: list = []
        self.visual_beat_report: dict = {}
        self.visual_preflight: dict = {}
        self.retention_plan: dict = {}

        # Initialize the Firefox profile
        self.options: Options = Options()

        # YouTube's upload page fires a beforeunload `confirmEx` ("Leave page? â€”
        # changes you made may not be saved") whenever Selenium navigates while
        # an upload is in progress. Default driver policy is "dismiss and notify"
        # which raises UnexpectedAlertPresentException mid-upload. Tell the
        # driver to silently accept any such dialog so navigation/clicks keep
        # flowing.
        self.options.unhandled_prompt_behavior = "accept"
        # Belt-and-braces: also disable the prompt at the Firefox layer so the
        # confirmEx never fires in the first place.
        self.options.set_preference("dom.disable_beforeunload", True)

        # Set headless state of browser
        if get_headless():
            self.options.add_argument("--headless")

        if not os.path.isdir(self._fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {self._fp_profile_path}"
            )

        # Copy the profile so we can use it even if Firefox is open.
        # We must preserve cookies, logins, and session data for YouTube.
        import shutil
        import tempfile
        self._temp_profile_dir = tempfile.mkdtemp(prefix="mpv2_firefox_")
        temp_profile = os.path.join(self._temp_profile_dir, "profile")
        if get_verbose():
            info(f" => Copying Firefox profile to temp dir...")
        # Exclude lock files and large caches that cause conflicts,
        # but KEEP cookies.sqlite, logins.json, key4.db, etc.
        shutil.copytree(
            self._fp_profile_path, temp_profile,
            ignore=shutil.ignore_patterns(
                "lock", ".parentlock", "parent.lock",
                "cache2", "startupCache", "shader-cache",
                "thumbnails", "crashes",
            ),
            dirs_exist_ok=False,
        )
        # Remove the session restore files that can cause crashes
        for bad_file in ["sessionstore.jsonlz4", "sessionstore-backups"]:
            bad_path = os.path.join(temp_profile, bad_file)
            if os.path.isfile(bad_path):
                os.remove(bad_path)
            elif os.path.isdir(bad_path):
                shutil.rmtree(bad_path, ignore_errors=True)

        self.options.add_argument("-profile")
        self.options.add_argument(temp_profile)
        # Allow multiple Firefox instances simultaneously (each job uses its
        # own temp profile, so --no-remote lets geckodriver launch a fresh
        # process without attaching to an already-running Firefox window).
        self.options.add_argument("--no-remote")

        # Browser is initialized lazily just before upload (see _ensure_browser)
        self.browser: webdriver.Firefox = None

    @property
    def niche(self) -> str:
        """
        Getter Method for the niche.

        Returns:
            niche (str): The niche
        """
        return self._niche

    @property
    def language(self) -> str:
        """
        Getter Method for the language to use.

        Returns:
            language (str): The language
        """
        return self._language

    def generate_response(self, prompt: str, model_name: str = None, temperature: float = 0.7) -> str:
        """
        Generates an LLM Response based on a prompt and the user-provided model.

        Args:
            prompt (str): The prompt to use in the text generation.

        Returns:
            response (str): The generated AI Repsonse.
        """
        return generate_text(prompt, model_name=model_name, temperature=temperature)

    def generate_topic(self) -> str:
        """
        Generates a topic based on the YouTube Channel niche.
        Channel-lifetime duplicate guard: if the LLM cannot produce a topic
        that does not collide with any previously uploaded video, this method
        returns "" (the caller must then abort â€” we NEVER knowingly publish a
        repeat).

        Detection layers, in order of strictness:
          1. markdown/prefix cleanup (LLMs love wrapping in ** or "Topic:")
          2. language guard (reject English when channel language is Spanish)
          3. shared distinctive-entity match (e.g. "Hammurabi", "Cosimo I",
             "Vasari" appearing in both candidate and a past topic â†’ duplicate,
             regardless of surrounding words)
          4. token-overlap and sequence-similarity fallbacks

        Returns:
            topic (str): The generated topic, or "" if all attempts collided.
        """
        import random
        import unicodedata
        from difflib import SequenceMatcher

        # ---- 1. Collect full channel history ----
        past_topics: List[str] = []
        past_videos: List[dict] = []
        try:
            videos = self.get_videos()
            past_videos = videos or []
            for v in videos:
                for key in ("subject", "title"):
                    val = v.get(key)
                    if val and isinstance(val, str):
                        past_topics.append(val.strip())
        except Exception:
            pass

        # ---- 2. Vocab ----
        ES_STOP = {
            "el", "la", "los", "las", "de", "del", "que", "y", "en", "un", "una",
            "por", "para", "con", "se", "su", "sus", "lo", "al", "como", "es",
            "fue", "era", "ser", "son", "mas", "este", "esta", "esto", "estos",
            "estas", "sobre", "entre", "pero", "si", "no", "ni", "cuando",
            "donde", "quien", "que", "como", "cual", "cuales", "hacia", "desde",
            "hasta", "sin", "ya", "muy", "mas", "menos", "todo", "toda", "todos",
            "todas", "otro", "otra", "otros", "otras", "tambien", "solo", "solo",
            "tras", "ante", "bajo",
        }
        EN_STOP = {
            "the", "of", "a", "an", "and", "is", "was", "to", "in", "on", "who",
            "why", "how", "what", "were", "are", "be", "been", "have", "has",
            "had", "with", "from", "that", "this", "these", "those", "will",
            "would", "can", "could", "should", "about", "into", "which", "where",
            "when", "their", "its", "it", "by", "at", "as", "or", "but", "for",
        }
        STOP = ES_STOP | EN_STOP

        def _strip_diacritics(s: str) -> str:
            return "".join(
                c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
            )

        def _strip_markdown(s: str) -> str:
            """Remove markdown scaffolding, hashtags, and common LLM prefixes."""
            if not s:
                return ""
            # Code blocks
            s = re.sub(r"```[\s\S]*?```", " ", s)
            s = re.sub(r"`+", "", s)
            # Hashtags (#Foo, #HistoriaAntigua) â€” they'd otherwise be captured
            # as distinctive entities, but every historical-channel video
            # shares the same pool of tags so they collide spuriously.
            s = re.sub(r"#\w+", " ", s, flags=re.UNICODE)
            # Bold/italic/headers
            s = re.sub(r"[*_#]+", "", s)
            # Leading "Topic:", "Tema:", "Title:", "Titulo:"
            s = re.sub(r"^\s*(?:topic|tema|title|t[iÃ­]tulo)\s*:\s*", "", s, flags=re.I)
            # Collapse whitespace
            s = re.sub(r"\s+", " ", s).strip()
            # Strip enclosing quotes (regular, curly, guillemets)
            s = s.strip(" \t\"'â€œâ€â€˜â€™Â«Â»").strip()
            return s

        def _normalize(s: str) -> str:
            """Lowercase, strip diacritics & punctuation, drop stopwords."""
            s = _strip_diacritics(s.lower())
            s = re.sub(r"[^\w\s]", " ", s)
            tokens = [t for t in s.split() if t and t not in STOP and len(t) > 1]
            return " ".join(tokens)

        def _looks_english(s: str) -> bool:
            """Heuristic: reject obvious English when the channel is Spanish."""
            if not s:
                return False
            lang = str(self.language or "").lower()
            if not (lang.startswith("span") or lang.startswith("esp") or lang == "es"):
                return False
            toks = re.findall(r"[A-Za-z]+", s.lower())
            if len(toks) < 4:
                return False
            en_hits = sum(1 for t in toks if t in EN_STOP)
            es_hits = sum(1 for t in toks if t in ES_STOP)
            # Clear English signal: several English stopwords and more EN than ES
            return en_hits >= 3 and en_hits > es_hits

        # ---- 3. Pre-compute past signatures ----
        past_clean = [_strip_markdown(t) for t in past_topics]

        def _is_duplicate(candidate: str) -> tuple[bool, str]:
            # Distinctive-entity + lexical dedupe lives in topic_dedupe so the
            # webapp's /suggest-topics endpoint shares the exact same logic.
            # This catches same-subject rephrasings (e.g. "El misterio de
            # Oumuamua" vs "Oumuamua, el visitante interestelar") that the old
            # purely-lexical check missed.
            from topic_dedupe import find_duplicate
            matched = find_duplicate(candidate, past_topics)
            return (bool(matched), matched)

        # ---- 4. Build forbidden block (recent topics as avoidance hint for the LLM) ----
        forbidden_block = ""
        if past_topics:
            # Show the most recent 80 so the LLM has enough channel history to avoid
            # repeats. 40 was too narrow for established channels -- the model would
            # propose subjects from older history that the dedupe layer then had to
            # reject, burning attempts.
            shown = past_clean[-80:]
            forbidden_block = (
                "\n\nALREADY COVERED in this niche (do NOT repeat, do NOT rephrase, "
                "do NOT pick the same subject from a different angle -- pick a DIFFERENT "
                "subject entirely, but stay WITHIN the niche):\n"
                + "\n".join(f"- {t}" for t in shown)
                + f"\n\nGenerate a fresh angle WITHIN the niche \"{self.niche}\". "
                f"The new topic must still unmistakably belong to this niche â€” "
                f"only the specific subject should differ from the list above."
            )
        if is_max_retention(getattr(self, "_retention_mode", "")):
            forbidden_block += RetentionLab.burned_topic_directive(past_videos)
            forbidden_block += RetentionLab.winning_topic_directive(past_videos)

        # ---- 4b. Niche validator (second LLM pass that double-checks the candidate) ----
        def _topic_in_niche(candidate: str) -> bool:
            """
            Ask the LLM whether the candidate topic clearly belongs to the channel's
            niche. Returns False if the verdict is anything other than an unambiguous
            FITS, so off-niche or ambiguous topics get rejected and regenerated.

            IMPORTANT: the response MUST be at least ~10 chars long. llm_provider's
            garbage filter (`_is_garbage_response`) treats any reply shorter than 10
            chars as conversational and DISABLES the provider for the whole session.
            We require a short structured line ("VERDICT: FITS â€” <reason>") that
            clears that bar.
            """
            try:
                verdict = self.generate_response(
                    f"""You are a strict content classifier. Decide if this video topic clearly and unmistakably belongs to the channel's niche.

CHANNEL NICHE: {self.niche}

CANDIDATE TOPIC: {candidate}

Rules for your verdict:
- Answer FITS only if the topic is undeniably part of the niche â€” a viewer would immediately recognize it as belonging to that niche.
- Answer OFFNICHE if the topic is fictional, made-up, abstract, metaphorical, or drifts toward storytelling/fiction when the niche is factual/educational.
- Answer OFFNICHE if the topic is a generic life lesson or philosophical musing not tied to the niche's actual subject matter.
- Answer OFFNICHE if the topic could fit dozens of different niches â€” niches require specificity.
- When in doubt, answer OFFNICHE.

OUTPUT FORMAT (strict, exactly one line):
VERDICT: <FITS or OFFNICHE> â€” <short reason in 5-15 words>

Example outputs:
VERDICT: FITS â€” clearly a real astronomical phenomenon within the niche
VERDICT: OFFNICHE â€” fictional sci-fi storytelling, not a real scientific subject

Return ONLY that single line. No other text."""
                )
            except Exception:
                # If the validator call fails, don't block the pipeline â€” accept the candidate.
                return True
            verdict_up = (verdict or "").strip().upper()
            # Look for the verdict token anywhere in the response (handles wrappers like
            # "**VERDICT: FITS â€” ...**" or stray quotes around the line).
            if "OFFNICHE" in verdict_up or "OFF-NICHE" in verdict_up or "OFF NICHE" in verdict_up:
                return False
            if "FITS" in verdict_up:
                return True
            # Unparseable response â†’ accept (the cache-side dedupe still guards the run).
            return True

        # ---- 5. Generate with retries ----
        rejected: List[str] = []
        completion = ""
        max_attempts = 15
        for attempt in range(max_attempts):
            creativity_seed = random.randint(1, 100000)
            max_retention_topic = (
                MaxRetentionEngine.topic_generation_directive(self.niche, self.language)
                if is_max_retention(getattr(self, "_retention_mode", ""))
                else ""
            )
            extra_reject = ""
            if rejected:
                extra_reject = (
                    "\n\nYou already suggested these and they were REJECTED as duplicates "
                    "of previously published videos -- pick a COMPLETELY unrelated subject "
                    "(different person, different event, different place):\n"
                    + "\n".join(f"- {t}" for t in rejected[-12:])
                )

            raw_candidate = self.generate_response(
                f"""Generate ONE specific, focused topic for a short video.

YOUR NICHE (you MUST stay strictly within this niche): {self.niche}

CRITICAL RULE: The topic MUST be directly and unmistakably part of the niche above. Anything that does not clearly belong to that niche is FORBIDDEN â€” including fictional stories, made-up characters, abstract metaphors, generic life lessons, philosophical musings disconnected from the niche, or any unrelated field. ONLY generate topics whose subject matter a viewer would immediately recognize as belonging to "{self.niche}".

The topic must be ONE concrete story, event, mystery, fact, person, place, or phenomenon â€” NOT a broad category, NOT a fictional scenario.

BAD example: "Curiosidades del universo" (too broad, leads to random facts)
BAD example: "Un planeta donde todo es al revÃ©s" (fictional fantasy, not a real subject)
GOOD example: "TON 618: el agujero negro 66 mil millones de veces mÃ¡s masivo que el Sol" (one specific real cosmic object)
GOOD example: "Â¿Por quÃ© Voyager 1 sigue enviando datos 47 aÃ±os despuÃ©s de su lanzamiento?" (one specific real mission detail)
GOOD example: "El dÃ­a que LIGO detectÃ³ dos agujeros negros fusionÃ¡ndose por primera vez" (one specific real event)
GOOD example: "EncÃ©lado: la luna de Saturno que escupe agua lÃ­quida al espacio" (one specific real phenomenon)
{max_retention_topic}

SELF-CHECK BEFORE ANSWERING: Re-read the niche "{self.niche}". If your topic is not unmistakably part of THAT niche, discard it and pick a different one.

OUTPUT FORMAT (strict):
- Return ONLY the topic as one plain sentence.
- NO markdown (no **, no backticks, no headers).
- NO prefixes like "Topic:", "Tema:", "Title:".
- NO surrounding quotes.
- WRITE ENTIRELY IN {self.language}. Every word must be in {self.language}.{forbidden_block}{extra_reject}

(Creativity seed: {creativity_seed} â€” use this to inspire a fresh angle WITHIN the niche. "Fresh" means a different specific subject from the same niche, NOT a different field.)""",
                temperature=0.95,
            )

            candidate = _strip_markdown(raw_candidate or "")
            if not candidate:
                continue

            if _looks_english(candidate):
                warning(
                    f"Topic is not in {self.language} (attempt {attempt + 1}/{max_attempts}): "
                    f"'{candidate[:80]}' â€” regenerating."
                )
                rejected.append(candidate)
                continue

            is_dup, matched = _is_duplicate(candidate)
            if is_dup:
                warning(
                    f"Topic collides with past video (attempt {attempt + 1}/{max_attempts}).\n"
                    f"   candidate: {candidate[:100]}\n"
                    f"   past     : {matched[:100]}"
                )
                rejected.append(candidate)
                continue

            if not _topic_in_niche(candidate):
                warning(
                    f"Topic off-niche (attempt {attempt + 1}/{max_attempts}).\n"
                    f"   candidate: {candidate[:100]}\n"
                    f"   niche    : {self.niche[:100]}"
                )
                rejected.append(candidate)
                continue

            if is_max_retention(getattr(self, "_retention_mode", "")):
                weak_reason = MaxRetentionEngine.topic_rejection_reason(candidate, self.niche)
                if weak_reason:
                    warning(
                        f"Topic weak for MAXIMA RETENCION ({weak_reason}) "
                        f"(attempt {attempt + 1}/{max_attempts}).\n"
                        f"   candidate: {candidate[:100]}"
                    )
                    rejected.append(candidate)
                    continue
                burned_reason = RetentionLab.topic_burned_reason(candidate, past_videos)
                if burned_reason:
                    warning(
                        f"Topic weak in Retention Lab ({burned_reason}) "
                        f"(attempt {attempt + 1}/{max_attempts}).\n"
                        f"   candidate: {candidate[:100]}"
                    )
                    rejected.append(candidate)
                    continue

            completion = candidate
            break

        if not completion:
            # Channel-lifetime duplicate guard: we NEVER knowingly publish a
            # repeat. Return "" so the caller aborts the run.
            error(
                f"Could not generate a unique topic after {max_attempts} attempts â€” "
                f"refusing to publish a duplicate. Try again later or broaden the niche."
            )
            self.subject = ""
            return ""

        self.subject = completion
        return completion

    def _run_max_retention_preflight(
        self,
        script: str,
        sentence_length: int | None = None,
        allow_rewrite: bool = True,
    ) -> str:
        """Score MAXIMA RETENCION scripts before expensive render steps."""
        if not is_max_retention(getattr(self, "_retention_mode", "")):
            return script

        resolved_sentence_length = sentence_length or self._sentence_length_override or get_script_sentence_length()
        if allow_rewrite:
            improved, report = RetentionLab.enforce_pre_render_score(
                script=script,
                topic=getattr(self, "subject", "") or "",
                niche=self.niche,
                language=self.language,
                sentence_length=resolved_sentence_length,
                target_words=self._target_word_count,
                generate_response=self.generate_response,
            )
        else:
            report = RetentionLab.score_short_script(
                script=script,
                topic=getattr(self, "subject", "") or "",
                niche=self.niche,
                language=self.language,
                retention_mode=getattr(self, "_retention_mode", ""),
            )
            report.update({
                "initial_score": report.get("score", 0),
                "final_score": report.get("score", 0),
                "threshold": RetentionLab.SCORE_THRESHOLD,
                "attempts": 0,
                "rewritten": False,
                "accepted": report.get("score", 0) >= RetentionLab.SCORE_THRESHOLD,
                "approved_script": True,
            })
            improved = script

        self.retention_preflight = report
        if get_verbose():
            status = "OK" if report.get("accepted") else "RIESGO"
            rewritten = " | rewritten" if report.get("rewritten") else ""
            info(
                " => MAXIMA RETENCION preflight: "
                f"{report.get('final_score', report.get('score', 0))}/10 "
                f"({status}{rewritten})"
            )
        return improved

    def _hook_lab_max_attempts(self) -> int:
        raw = os.environ.get("MP_HOOK_LAB_MAX_ATTEMPTS", "12").strip()
        try:
            return max(1, min(int(raw), 30))
        except ValueError:
            return 12

    def _select_max_retention_hook(
        self,
        candidates: int = 8,
        educational_anchor: bool = False,
    ) -> tuple[str, dict]:
        return RetentionLab.select_best_hook(
            topic=self.subject,
            niche=self.niche,
            language=self.language,
            generate_response=self.generate_response,
            history_videos=self.get_videos(),
            candidates=candidates,
            max_rounds=self._hook_lab_max_attempts(),
            educational_anchor=educational_anchor,
        )

    @staticmethod
    def _hook_sentence_for_script(hook: str) -> str:
        clean = RetentionLab._clean_line(hook)
        if clean and clean[-1] not in ".!?":
            clean += "."
        return clean

    def _replace_first_sentence(self, script: str, hook: str) -> str:
        sentences = MaxRetentionEngine._sentences(script)
        clean_hook = self._hook_sentence_for_script(hook)
        if not sentences or not clean_hook:
            return script
        sentences[0] = clean_hook
        return " ".join(sentences)

    def _enforce_final_hook_lab(self, script: str, educational_anchor: bool = False) -> str:
        sentences = MaxRetentionEngine._sentences(script)
        if not sentences:
            return script

        final_hook_report = RetentionLab.score_hook(
            sentences[0],
            topic=self.subject,
            niche=self.niche,
            language=self.language,
            require_subject_anchor=educational_anchor,
        )
        accepted = final_hook_report.get("score", 0) >= RetentionLab.HOOK_SCORE_THRESHOLD

        if not accepted:
            if get_verbose():
                warning(
                    "Final Hook Lab is still in RIESGO; retrying hook generation "
                    "before render."
                )
            best_hook = ""
            hook_lab = getattr(self, "retention_hook_lab", {}) or {}
            if hook_lab.get("accepted"):
                best_hook = str(hook_lab.get("best_hook") or "")
            if not best_hook:
                best_hook, hook_lab = self._select_max_retention_hook(
                    candidates=8,
                    educational_anchor=educational_anchor,
                )
                self.retention_hook_lab = hook_lab
            if not hook_lab.get("accepted"):
                raise RuntimeError(
                    "Hook Lab could not produce an accepted hook after "
                    f"{hook_lab.get('rounds', self._hook_lab_max_attempts())} attempts "
                    f"(best {hook_lab.get('best_score', 0)}/10)."
                )
            script = self._replace_first_sentence(script, best_hook)
            sentences = MaxRetentionEngine._sentences(script)
            final_hook_report = RetentionLab.score_hook(
                sentences[0] if sentences else "",
                topic=self.subject,
                niche=self.niche,
                language=self.language,
                require_subject_anchor=educational_anchor,
            )
            accepted = final_hook_report.get("score", 0) >= RetentionLab.HOOK_SCORE_THRESHOLD
            if not accepted:
                raise RuntimeError(
                    "Hook Lab repaired the script, but the final hook still scored "
                    f"{final_hook_report.get('score', 0)}/10."
                )

        self.retention_hook_lab.update({
            "final_hook": final_hook_report.get("hook", ""),
            "final_score": final_hook_report.get("score", 0),
            "final_accepted": accepted,
            "final_issues": final_hook_report.get("issues", []),
        })
        if get_verbose():
            info(
                " => Final Hook Lab: "
                f"{final_hook_report.get('score', 0)}/10 "
                f"{'OK' if accepted else 'RIESGO'}"
            )
        return script

    def generate_script(self) -> str:
        """
        Generate a script for a video, depending on the subject of the video, the number of paragraphs, and the AI model.

        Returns:
            script (str): The script of the video.
        """
        import random

        sentence_length = self._sentence_length_override or get_script_sentence_length()
        target_words = self._target_word_count
        target_seconds = self._target_duration_seconds

        # Word count is the load-bearing instruction: LLMs hit word counts
        # much more reliably than sentence counts, and final TTS duration
        # tracks word count almost linearly. Sentence count is kept as a
        # secondary structural guide.
        if target_words and target_seconds:
            duration_clause = (
                f"TARGET DURATION: ~{target_seconds} seconds of narration. "
                f"Aim for {target_words} words total (Â±10%). Average sentence "
                f"length: ~{max(8, target_words // max(1, sentence_length))} words. "
                f"DO NOT undershoot â€” a script that comes in short produces a "
                f"video noticeably below {target_seconds}s, which is worse than "
                f"running slightly long."
            )
        else:
            duration_clause = ""

        # Rotate hook style per run so every short doesn't open the same way.
        # The preset is picked from HOOK_PROFILES by self._hook_profile (set per
        # channel on the account JSON). Falls back to "educational" if the
        # configured profile is missing or unknown.
        is_cosmic_video = CosmicRetentionEngine.is_cosmic_context(self.subject, self.niche)
        profile_name = self._hook_profile or ("storytelling" if is_cosmic_video else "educational")
        hook_styles = HOOK_PROFILES.get(profile_name) or HOOK_PROFILES["educational"]
        if profile_name not in HOOK_PROFILES and self._hook_profile:
            warning(f"Unknown hook_profile '{self._hook_profile}', falling back to 'educational'.")
            profile_name = "educational"
        hook_style, hook_example = random.choice(hook_styles)

        # Per-job override (set by the webapp's "hook style" selector). Format:
        # MP_HOOK_STYLE_OVERRIDE = "<profile>::<style_name>" â€” both pieces must
        # match a key in HOOK_PROFILES. Falls back silently to the random pick
        # above if the override doesn't resolve, so a stale env var never
        # crashes the pipeline.
        override = os.environ.get("MP_HOOK_STYLE_OVERRIDE", "").strip()
        if override and "::" in override:
            ov_profile, ov_style = override.split("::", 1)
            ov_profile = ov_profile.strip().lower()
            ov_style = ov_style.strip()
            candidates = HOOK_PROFILES.get(ov_profile) or []
            for s_name, s_example in candidates:
                if s_name == ov_style:
                    profile_name = ov_profile
                    hook_style, hook_example = s_name, s_example
                    if get_verbose():
                        info(f" => Hook style override: {ov_profile} / {ov_style}")
                    break

        if get_verbose():
            info(f" => Hook profile: {profile_name} | style: {hook_style}")

        hook_lab_directive = ""
        educational_opening_directive = ""
        if profile_name == "educational":
            educational_opening_directive = f"""

EDUCATIONAL OPENING ANCHOR - mandatory:
- Sentence 1 must name the main subject naturally before using vague pronouns or mystery phrasing.
- If the subject name is not self-explanatory, immediately add what it is: star, planet, black hole, comet, probe, galaxy, mission, person, place, event, or phenomenon.
- Do NOT force every opening into "La estrella..." or "El planeta..."; vary it naturally. Good patterns: "TON seis dieciocho es un agujero negro...", "SS Leonis Minoris es una estrella vampiro...", "La estrella de Tabby perdió...", "Voyager uno es una sonda...".
- For short catalog names, write them in a speakable form when needed. Prefer "TON seis dieciocho" over spelling letters one by one, and "Voyager uno" over raw digits.
- Bad educational opening: "Nadie ve cómo esta estrella..." before naming the star. Better: "SS Leonis Minoris es una estrella vampiro que...".
"""
        if is_max_retention(getattr(self, "_retention_mode", "")):
            try:
                best_hook, hook_report = self._select_max_retention_hook(
                    candidates=8,
                    educational_anchor=profile_name == "educational",
                )
            except Exception as e:
                best_hook, hook_report = "", {"accepted": False, "error": str(e)[:200]}
            self.retention_hook_lab = hook_report
            if best_hook and hook_report.get("accepted"):
                hook_lab_directive = f"""

MAXIMA RETENCION HOOK LAB - mandatory:
- Sentence 1 must be this hook exactly, unless grammar requires a tiny correction:
"{best_hook}"
- Sentence 2 must immediately explain the visual consequence promised by that hook.
"""
            elif best_hook and get_verbose():
                warning(
                    "Hook Lab best candidate is below threshold; "
                    "not forcing it into the script."
                )
            if get_verbose() and hook_report:
                repaired = " | repaired" if hook_report.get("fallback_used") else ""
                info(
                    " => Hook Lab: "
                    f"{hook_report.get('best_score', 0)}/10 "
                    f"{'OK' if hook_report.get('accepted') else 'RIESGO'} "
                    f"(rounds {hook_report.get('rounds', 1)}/{hook_report.get('max_rounds', 1)}{repaired})"
                )
            if not hook_report.get("accepted"):
                raise RuntimeError(
                    "Hook Lab could not produce an accepted hook after "
                    f"{hook_report.get('rounds', self._hook_lab_max_attempts())} attempts "
                    f"(best {hook_report.get('best_score', 0)}/10)."
                )

        cosmic_directive = CosmicRetentionEngine.short_generation_directive(
            self.subject,
            self.niche,
            self.language,
        )
        max_retention_directive = (
            MaxRetentionEngine.script_generation_directive(
                self.subject,
                self.niche,
                self.language,
                sentence_length,
            )
            if is_max_retention(getattr(self, "_retention_mode", ""))
            else ""
        )
        voice_directive = NarrationVoice.short_generation_directive(self.language)

        prompt = f"""Write a narration script for a short video in EXACTLY {sentence_length} sentences.
{duration_clause}

TOPIC: {self.subject}
{cosmic_directive}
{max_retention_directive}
{voice_directive}
{educational_opening_directive}
{hook_lab_directive}

NARRATIVE STRUCTURE (follow this order):
1. HOOK (sentence 1): The hook MUST use this exact style: {hook_style}. Example (adapt to the topic and to {self.language}): {hook_example}. Do NOT default to any other hook style.
2. CONTEXT (sentences 2-3): Set the scene. When and where does this happen? What's the background?
3. DEVELOPMENT (sentences 4-{sentence_length - 2}): Go deeper into the topic. Reveal details, facts, consequences. Build tension or curiosity. Each sentence should ADVANCE the story, not jump to unrelated facts.
4. CONCLUSION (last 1-2 sentences): End with a powerful thought, a twist, or a mind-blowing takeaway.

CRITICAL RULES:
- Stay on ONE topic throughout. Do NOT list random facts. Tell ONE story from start to finish.
- Every sentence must connect to the previous one. The script must feel like a continuous narrative, not a list.
- EXACTLY {sentence_length} sentences. Short and punchy (under 20 words each).
- NO markdown, NO formatting, NO titles, NO bullet points.
- NO "welcome", NO "voiceover", NO meta-references.
- NEVER announce the structure. Do not write labels the narrator would say aloud, such as "primera revelacion", "segunda revelacion", "hook", "contexto", "desarrollo", "conclusion", "parte uno", or "seccion dos".
- ABSOLUTELY NO stage directions of any kind. Never write "(image of ...)", "(imagen de ...)", "[B-roll: ...]", "(plano cerrado)", "(music)", "(mÃºsica suave)", "(emoji)", "(transition)", "(voice over)" or anything similar. Only text a narrator would speak ALOUD.
- NUMBERS: spell numbers out as words, not digits. Examples (in {self.language}): "mil cuatrocientos cincuenta y tres" not "1453"; "four thousand five hundred" not "4,500".
- YEAR vs DURATION â€” keep them strictly separate. A YEAR is a calendar date; a DURATION is elapsed time. They are different things. To cite a calendar year, say "el aÃ±o <aÃ±o>" / "in the year <year>". The phrase "hace <N> aÃ±os" / "<N> years ago" expresses ONLY duration: <N> is the difference between the current year and the year of the event â€” it is NOT the year itself. When in doubt, name the year ("el aÃ±o X") and do NOT use the "hace X aÃ±os" / "X years ago" phrasing.
- ONLY return the raw script text. Nothing else.
- WRITE ENTIRELY IN {self.language}. Every word must be in {self.language}.
"""
        completion = self.generate_response(prompt)

        # Apply regex to remove *
        completion = re.sub(r"\*", "", completion)
        completion = strip_narration_structure_labels(completion)

        if not completion:
            error("The generated script is empty.")
            return

        if len(completion) > 5000:
            if get_verbose():
                warning("Generated Script is too long. Retrying...")
            return self.generate_script()

        completion = CosmicRetentionEngine.optimize_short_script(
            script=completion,
            topic=self.subject,
            niche=self.niche,
            language=self.language,
            sentence_length=sentence_length,
            target_words=target_words,
            generate_response=self.generate_response,
        )
        completion = strip_narration_structure_labels(completion)

        if is_max_retention(getattr(self, "_retention_mode", "")):
            completion = MaxRetentionEngine.optimize_short_script(
                script=completion,
                topic=self.subject,
                niche=self.niche,
                language=self.language,
                sentence_length=sentence_length,
                target_words=target_words,
                generate_response=self.generate_response,
            )
            completion = strip_narration_structure_labels(completion)
            completion = self._run_max_retention_preflight(
                completion,
                sentence_length=sentence_length,
                allow_rewrite=True,
            )
            completion = strip_narration_structure_labels(completion)
            completion = self._enforce_final_hook_lab(
                completion,
                educational_anchor=profile_name == "educational",
            )
            completion = strip_narration_structure_labels(completion)

        if is_cosmic_video and get_verbose():
            score = CosmicRetentionEngine.score_script(completion)
            info(
                " => Cosmic retention score: "
                f"{score.average:.1f}/10 "
                f"(hook {score.hook_strength}, mystery {score.mystery}, "
                f"visual {score.visual_potential}, pacing {score.pacing}, "
                f"ending {score.ending_strength})"
            )

        self.script = strip_narration_structure_labels(completion)

        return completion

    def generate_metadata(self) -> dict:
        """
        Generates Video metadata for the to-be-uploaded YouTube Short (Title, Description).

        Returns:
            metadata (dict): The generated metadata.
        """
        # Pass the actual script to the title prompt \u2014 without it, the model
        # invents clickbait promises ("5 curiosidades", "3 secretos") that
        # the script never delivers. The title must reflect what the video
        # actually says.
        title_prompt = f"""Generate a YouTube Short title for this video.

SUBJECT: {self.subject}

ACTUAL SCRIPT (the title must match what THIS script delivers):
\"\"\"
{self.script}
\"\"\"

ABSOLUTE RULES:
- The title must accurately describe what the script says. Do NOT promise content that is not in the script.
- FORBIDDEN BASIC/CLICH\u00c9 WORDS (do NOT use ANY of these, in any form, accented or not, singular or plural): "secreto", "secretos", "misterio", "misterios", "sab\u00edas que", "sabias que", "no vas a creer", "te volar\u00e1 la cabeza", "incre\u00edble", "impactante", "te sorprender\u00e1", "nadie sabe", "nadie te cont\u00f3", "lo que no te dicen", "esto te dejar\u00e1", "loco", "alucinante", "flipante", "shocking", "you won't believe", "mind-blowing", "secret", "mystery", "did you know". These are overused, obvious, and lazy clickbait \u2014 NEVER use them.
- FORBIDDEN: "X curiosidades", "X secretos", "X razones", "X cosas", "X datos", "X hechos", "Top X", "X que..." or ANY list-form promise (in {self.language} or English) UNLESS the script actually presents that exact number of distinct enumerated items. If the script tells ONE continuous story, the title MUST NOT promise a list.
- INSTEAD, write SPECIFIC, CONCRETE titles that name the actual subject, action, place, person, date, or fact from the script. The hook should come from the specificity of the content itself \u2014 a surprising name, a striking number, an unexpected place, a precise event \u2014 NOT from generic hype words.
- Good title patterns: a concrete claim ("Voyager 1 cruz\u00f3 la heliopausa y nadie estaba listo"), a specific question about the subject ("\u00bfPor qu\u00e9 la luz no escapa de un agujero negro?"), a precise paradox or contrast, a striking astronomical fact, a named cosmic object/mission/scientist + specific phenomenon.
- The title can be intriguing, but it must be HONEST and SPECIFIC \u2014 every promise must be delivered by the script, and the intrigue must come from real content, not empty hype words.
- Optionally include 1-2 relevant hashtags at the end (only if they fit naturally).
- Under 80 characters.
- WRITE ENTIRELY IN {self.language}. Do NOT wrap the title in quotes. No leading/trailing quote characters.
- Only return the title text, nothing else."""

        title = self.generate_response(title_prompt)

        # Strip any quotes the LLM might add (regular, curly, single)
        title = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', title.strip()).strip()

        # Belt-and-suspenders enforcement: even with the prompt above, some
        # models still slip in "X <noun>" list promises. If the title makes
        # that promise but the script doesn't enumerate items, regenerate
        # once with a stricter instruction.
        if self._title_promises_list(title) and not self._script_has_enumerated_items(self.script):
            warning(
                f"Title promises a list but script does not enumerate items: '{title}' \u2014 regenerating."
            )
            retry = self.generate_response(
                title_prompt
                + "\n\nPREVIOUS ATTEMPT WAS REJECTED because it promised a numbered list that the script does NOT deliver. "
                + "Your script tells ONE continuous story \u2014 the title must reflect that. "
                + "Do NOT use any number followed by a noun ('5 curiosidades', '3 razones', etc.). "
                + "Do NOT use 'Top N' or 'N que...'. Try again."
            )
            retry = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', retry.strip()).strip()
            if retry and not self._title_promises_list(retry):
                title = retry

        # Reject overused clickbait words ("secreto", "sab\u00edas que", "incre\u00edble"\u2026)
        # \u2014 the LLM keeps defaulting to them even though the prompt forbids
        # them. Try up to 2 regenerations with progressively stronger language.
        cliche_attempts = 0
        while self._title_uses_cliche(title) and cliche_attempts < 2:
            cliche_attempts += 1
            warning(
                f"Title uses banned clickbait words: '{title}' \u2014 regenerating ({cliche_attempts}/2)."
            )
            retry = self.generate_response(
                title_prompt
                + "\n\nPREVIOUS ATTEMPT WAS REJECTED for using forbidden basic/clich\u00e9 words "
                + "(such as 'secreto', 'misterio', 'sab\u00edas que', 'incre\u00edble', 'no vas a creer', "
                + "'nadie sabe', 'impactante', 'alucinante', 'shocking', 'mystery', 'secret', etc). "
                + "These are LAZY hooks. Write a SPECIFIC, CONCRETE title that names the actual "
                + "subject, action, place, person, date, or fact from the script. The hook must "
                + "come from real content, not generic hype. Try again."
            )
            retry = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', retry.strip()).strip()
            if retry and not self._title_promises_list(retry):
                title = retry

        # If truncation would cut a hashtag, remove hashtags instead
        if len(title) > 100:
            if "#" in title:
                title = title[:title.index("#")].strip()
            if len(title) > 100:
                title = title[:100]

        description = self.generate_response(
            f"Please generate a YouTube Video Description for the following script: {self.script}. Only return the description, nothing else. Do NOT wrap the description in quotes. Do NOT start or end with any quote character. YOU MUST WRITE THE DESCRIPTION IN {self.language}."
        )

        # Strip any quotes the LLM might add (regular, curly, single)
        description = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', description.strip()).strip()

        self.metadata = {"title": title, "description": description}

        return self.metadata

    def generate_prompts(self, image_mode: str = "ai") -> List[str]:
        """
        Generates Image Prompts based on the provided Video Script.

        Args:
            image_mode (str): "ai" â†’ cinematic prompts for AI generators.
                              "photos" â†’ short search queries for real-photo sources
                              (Wikimedia Commons, Pexels, Pixabay).

        Returns:
            image_prompts (List[str]): Generated List of image prompts.
        """
        n_prompts = self._n_prompts_override or 6

        # Split script into sections so the LLM knows exactly what each image must show
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', self.script) if s.strip()]
        sections = []
        per_section = max(1, len(sentences) // n_prompts)
        for i in range(n_prompts):
            start = i * per_section
            end = start + per_section if i < n_prompts - 1 else len(sentences)
            section_text = ' '.join(sentences[start:end])
            if section_text:
                sections.append(section_text)
        # Pad if we got fewer sections
        while len(sections) < n_prompts:
            sections.append(self.subject)

        sections_text = ""
        for i, sec in enumerate(sections):
            sections_text += f"\nSECTION {i+1}: \"{sec}\"\n"

        visual_beat_block = ""
        if is_max_retention(getattr(self, "_retention_mode", "")):
            try:
                beats, beat_report = RetentionLab.build_visual_beat_map(
                    sections=sections[:n_prompts],
                    topic=self.subject,
                    niche=self.niche,
                    language=self.language,
                    generate_response=self.generate_response,
                )
            except Exception as e:
                beats, beat_report = [], {"accepted": False, "error": str(e)[:200]}
            self.visual_beat_map = beats
            self.visual_beat_report = beat_report
            visual_beat_block = RetentionLab.visual_beat_block(beats)
            if get_verbose() and beat_report:
                status = "OK" if beat_report.get("accepted") else "fallback"
                info(f" => Visual Beat Map: {beat_report.get('count', 0)} beats ({status})")

        if image_mode == "photos":
            prompt = f"""Generate exactly {n_prompts} short SEARCH QUERIES to find REAL scientific / astronomical / space-mission images for a video about: {self.subject}

These queries will be searched against NASA Image Library + ESA archive + Wikipedia + Wikimedia Commons + Hubble/JWST/Cassini/Voyager photo archives. Tailor the wording for those archives.

ABSOLUTE RULE â€” SUBJECT ANCHORING:
Every single query MUST contain the canonical English name of the subject (or, if the section is about a specific cosmic object/mission/scientist tied to the subject, that proper noun directly â€” e.g. "Pillars of Creation" or "Cassini Saturn flyby" for a Saturn-rings video). NEVER write a query that is just a generic concept ("a black hole image", "a galaxy in space", "a star exploding") â€” the search will return random unrelated results. The subject's proper noun, or a proper noun strictly identifying the same exact thing/object/event/mission, MUST be present in every query.

CRITICAL â€” use the CANONICAL ENGLISH NAME (the form Wikipedia / NASA uses) for every cosmic object, mission, or scientist:
  - WRONG: "huge black hole in big galaxy"        â†’   RIGHT: "TON 618" or "Sagittarius A* black hole"
  - WRONG: "NASA probe leaving solar system"      â†’   RIGHT: "Voyager 1 heliopause" or "Voyager 1 Pale Blue Dot"
  - WRONG: "telescope picture of nebula"          â†’   RIGHT: "JWST Carina Nebula" or "Pillars of Creation Hubble"
  - WRONG: "moon with water on Saturn"            â†’   RIGHT: "Enceladus plumes Cassini"
  - WRONG: "Einstein theory of light bending"     â†’   RIGHT: "Eddington 1919 eclipse" or "Einstein ring SDSS"
A Wikipedia / NASA article should EXIST for the subject of every query.

ANCHORING EXAMPLES â€” for a video about "TON 618":
  - GOOD: "TON 618 quasar", "TON 618 size comparison", "supermassive black hole accretion disk simulation", "EHT M87 black hole", "quasar host galaxy Hubble", "TON 618 hyperluminous quasar".
  - BAD:  "huge black hole space", "biggest object universe", "supermassive accretion disk", "galaxy with black hole". (None names TON 618 or a proper noun strictly tied to it.)

The script has been divided into {n_prompts} sections. Each query must match its section:
{sections_text}
{visual_beat_block}
INSTRUCTIONS:
- Query 1 finds a photo for SECTION 1, Query 2 for SECTION 2, etc.
- If a Visual Beat Map is present, each query must satisfy its matching BEAT number.
- Each query MUST contain at least one PROPER NOUN strictly identifying the subject (e.g. "TON 618", "Voyager 1", "JWST Carina Nebula", "Cassini Enceladus").
- Prefer objects, places, missions, artifacts, landscapes, documents, spacecraft, buildings, maps, tools and environmental evidence over people. Avoid queries that will return portraits or clear faces. If a person is essential, query for hands, back view, silhouette, statue, document, artifact, crowd from behind, or the location/object associated with them.
- 3 to 7 words per query. No full sentences.
- FORBIDDEN words: cinematic, dramatic, lighting, 8K, 4K, photorealistic, HD, macro, bokeh, shot, close-up, portrait, face, facial, selfie, headshot, aerial, style, composition, render, aesthetic. No adjectives describing mood or camera.
- FORBIDDEN as the ONLY proper noun in a query: generic body types ("black hole", "galaxy", "nebula", "star"), generic missions ("NASA", "ESA", "telescope"), or generic places ("space", "universe", "sky"). They may appear, but never alone.
- Write in English (most archives index in English).

Return ONLY a JSON array of {n_prompts} strings. No markdown, no explanation."""
        else:
            ctx = self._get_context_profile()
            era_context = ""
            if ctx and (ctx.get("setting") or ctx.get("visual_anchors")):
                bits = []
                if ctx.get("setting"):
                    bits.append(f"the story is set in **{ctx['setting']}**")
                if ctx.get("visual_anchors"):
                    bits.append(f"period-accurate elements that MUST appear naturally: {ctx['visual_anchors']}")
                if ctx.get("must_avoid"):
                    bits.append(f"FORBIDDEN (anachronistic or off-era): {ctx['must_avoid']}")
                era_context = (
                    "\n\nERA & SETTING â€” MANDATORY FOR PERIOD ACCURACY: "
                    + ". ".join(bits)
                    + ". Every prompt MUST be visually faithful to this era. All clothing, "
                      "architecture, objects, lighting conditions and environments must belong "
                      "to this specific time and place. A viewer must immediately recognize the "
                      "correct historical period just by looking at the image. "
                      "Do not enumerate props as a costume checklist â€” weave them into the action naturally."
                )

            video_title = (self.metadata or {}).get("title", "") if hasattr(self, "metadata") else ""
            visual_retention = CosmicRetentionEngine.visual_retention_directive(
                self.subject,
                self.niche,
            )
            max_visual_retention = (
                MaxRetentionEngine.visual_generation_directive(self.subject, self.niche)
                if is_max_retention(getattr(self, "_retention_mode", ""))
                else ""
            )

            prompt = f"""Task: write exactly {n_prompts} image prompts for a YouTube Short. The script has been divided into {n_prompts} sections â€” write ONE image prompt per section. Each image must visually represent what is being narrated in THAT EXACT SECTION: the specific action happening, the environment where it takes place, and the atmosphere or emotion of that moment.{era_context}

VIDEO TITLE: {video_title or self.subject}
TOPIC: {self.subject}
{visual_retention}
{max_visual_retention}

SCRIPT DIVIDED INTO {n_prompts} SECTIONS (prompt N must illustrate section N):
{sections_text}
{visual_beat_block}

RULES FOR EACH PROMPT:

1. SECTION FIDELITY â€” MANDATORY. Read your assigned section carefully. The image must show what is LITERALLY happening in those sentences: the action described, the place mentioned, the object referenced, the emotion conveyed. Do NOT invent a scene unrelated to the section. If the section describes a landscape or a phenomenon with no people, depict that landscape or phenomenon.

1B. VISUAL BEAT MAP â€” MANDATORY WHEN PRESENT. Prompt N must satisfy BEAT N. Beat 1 is the first-frame scroll-stopper, so it must show one clear subject, one readable action, and one obvious contrast in the first glance.

2. FULL SCENE DESCRIPTION. Every prompt must describe THREE things together:
   a) THE ACTION or main subject â€” what is happening or what is being shown
   b) THE ENVIRONMENT â€” where it takes place, time of day, weather, architecture, terrain
   c) THE ATMOSPHERE â€” lighting, mood, emotional tone that matches what the narrator is describing

3. ENGLISH ONLY. Even if the script is in Spanish, every prompt is in English. Translate proper nouns naturally ("PlatÃ³n" â†’ "Plato", "Alejandro" â†’ "Alexander"). No Spanish words anywhere.

4. ACTION OR SCENE FIRST. If people appear, open with a verb-driven action. If the section describes a place, landscape, or phenomenon, open with that environment vividly described.
   FORBIDDEN openings: "[Name] standing in [costume]", "[Name] portrait", "A figure looking intently", "[Name] in [outfit] in front of [backdrop]".

5. PEOPLE WITHOUT IDENTIFIABLE FACES. Prefer scenes with no people when the section allows it. When people are necessary, show them from behind, in profile silhouette, over the shoulder, with the face turned away, cropped outside the frame, hidden by shadow, helmet, veil, hood, hands, tools, documents, or environmental occlusion. Communicate emotion through posture, gesture, clothing, hands, distance between bodies, and the surrounding scene. NEVER request a clear front-facing face, portrait, selfie, beauty shot, detailed eyes, or recognizable likeness.

6. CONCRETE OBJECTS. Name at least one specific object from the section (a tool, weapon, structure, artifact, natural element). Generic props are forbidden â€” use only what the script actually references.

7. UNIQUE SCENES. No two prompts may show the same scene. Each of the {n_prompts} sections happens at a different moment â€” use that to ensure visual variety.

8. NO ART-STYLE WORDS. Describe scenes only. NEVER write: "painting", "illustration", "cartoon", "anime", "drawing", "vector", "3D render", "ukiyo-e", "fresco", "engraving", "comic", "pixel art", "watercolor", "sketch". The visual style is added downstream.

9. NO CAMERA JARGON. NEVER write: "cinematic", "photograph", "camera", "shot", "lens", "close-up", "4K", "8K", "HD", "render", "bokeh", "macro", "aerial".

10. NO MULTI-IMAGE TRIGGERS: "series", "sequence", "scenes" (plural), "panels", "panel", "storyboard", "montage", "collage", "grid", "split screen", "frames", "multiple", "diptych", "triptych", "side by side".

11. LENGTH. 40-65 English words per prompt.

EXAMPLES â€” pattern only, not templates to copy:
   GOOD âœ“ (person + action + emotion, no visible face) "An exhausted soldier drops to his knees on a smoldering battlefield at dusk, clutching a broken spear with both hands, helmet tilted forward hiding his face, shoulders collapsed in grief, enemy fortifications burning in the distance behind him, smoke rising into an orange sky."
   GOOD âœ“ (landscape / no people) "A vast primeval forest stretches to the horizon under a hazy amber sky, enormous ferns and cycad trees towering over a muddy river delta, volcanic mountains smoking faintly in the far background, the air thick with mist at dawn."
   GOOD âœ“ (phenomenon) "A massive wall of glacial ice advances slowly across a flat tundra plain under a pale grey sky, uprooting ancient trees in its path, frozen mammoths visible beneath the translucent surface, a herd of woolly rhinoceroses fleeing in the foreground."
   GOOD âœ“ (discovery moment) "An archaeologist kneels in a narrow underground chamber, trembling hand holding a torch over a perfectly preserved golden death mask resting on stone, dust particles floating in the warm light, rough-hewn rock walls pressing close on all sides."

STRUCTURAL EXAMPLES â€” these show the PATTERN only (action-first, named anchor, concrete feature, narrative beat). Each GOOD example below is about a DIFFERENT cosmic subject on purpose: your {n_prompts} prompts must use the actual subject, named objects and concrete features from THIS video's script â€” NOT the subjects in the examples.

   GOOD âœ“ (supermassive black hole) "Light bends around the photon ring of TON 618, an orange-white accretion disk swirling at relativistic speeds, gravitationally lensed background galaxies smeared into arcs, deep cosmic blackness beyond, the faint glow of distant quasars sprinkling the field."
   GOOD âœ“ (deep-space mission)     "Voyager 1 drifts past the rings of Saturn at golden hour, its dish antenna angled back toward the inner Solar System, the gold-plated record glinting on its flank, ring shadows striping the spacecraft's body, the pale crescent of Titan in the distance."
   GOOD âœ“ (neutron star)            "A magnetar's twin magnetic-field lines arc thousands of kilometres above its glowing crust, X-ray flares ripple outward in violent pulses, the millisecond-pulsar surface cracks with starquake fissures, surrounding nebular gas glowing blue from the radiation bath."
   GOOD âœ“ (observatory)             "JWST's hexagonal gold mirror unfolds against the blackness of L2, the Carina Nebula reflected in its segments, the sun-shield's silver layers tilted away from the Sun, distant stars dotting the deep-cold backdrop, the spacecraft's struts catching faint sunlight."

   BAD âœ— "A big black hole in deep space with stars around it." (no verb, no concrete feature, generic wallpaper â€” exact failure mode)
   BAD âœ— "A supermassive black hole with accretion disk, glowing brightly, with galaxies in the background." (checklist instead of story; no specific action or comparison)
   BAD âœ— "Outer space with a planet and stars." (no specific moment, no story-specific feature, no named object)
   BAD âœ— "[subject] portrait, glowing in the void, with stars behind it." (forbidden opening â€” static stock image)

Return ONLY a JSON array of {n_prompts} prompt strings, in chronological order following the script. No markdown, no explanation, no preamble. Just the array.

Example format:
["section 1 prompt â€¦", "section 2 prompt â€¦", "section 3 prompt â€¦", "section 4 prompt â€¦", "section 5 prompt â€¦", "section 6 prompt â€¦"]"""

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        image_prompts = []

        def _extract_prompts(parsed_value):
            """Pull the prompt strings out of a parsed LLM response.
            For AI mode the LLM returns objects {"section", "moment", "prompt"};
            for photos mode (legacy) it returns plain strings. Handle both."""
            out = []
            if isinstance(parsed_value, list):
                for item in parsed_value:
                    if isinstance(item, str):
                        out.append(item)
                    elif isinstance(item, dict):
                        # Prefer the structured "prompt" field; if missing,
                        # combine moment + any description we can find.
                        p = item.get("prompt") or item.get("image_prompt") or ""
                        moment = item.get("moment") or item.get("key_visual_moment") or ""
                        if p:
                            out.append(str(p))
                        elif moment:
                            out.append(str(moment))
            elif isinstance(parsed_value, dict) and "image_prompts" in parsed_value:
                out = parsed_value["image_prompts"]
            return out

        # Try to extract JSON from the response
        try:
            parsed = json.loads(completion)
            image_prompts = _extract_prompts(parsed)
        except Exception:
            # Try to find a JSON array anywhere in the response
            match = re.search(r'\[.*\]', completion, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    image_prompts = _extract_prompts(parsed)
                except Exception:
                    pass

        # Fallback if parsing failed or too few prompts
        if image_mode == "photos":
            fallback_prompts = [self.subject] * n_prompts
        else:
            # Single-image, scene-only fallback prompts. No "illustrated", no
            # "series" / "sequence" / "panels" â€” those words make Gemini /
            # Nano Banana 2 produce a stacked collage instead of one image.
            fallback_prompts = [
                f"{self.subject}, the central cosmic subject in full view, scientifically accurate scale and palette, single image",
                f"{self.subject}, close detail of the key feature, true-to-data textures and surface, single image",
                f"{self.subject}, wide cosmic view of the surrounding region, faithful astronomical context, single image",
                f"{self.subject}, the phenomenon shown directly with realistic physics, single image",
                f"{self.subject}, the relevant instrument or spacecraft observing it, engineering-accurate detail, single image",
                f"{self.subject}, atmospheric deep-space moment with depth, true-to-mission mood and palette, single image",
            ]

        if not image_prompts or not isinstance(image_prompts, list):
            if get_verbose():
                warning("Failed to parse image prompts, using fallback prompts")
            image_prompts = fallback_prompts
        elif len(image_prompts) < n_prompts:
            if get_verbose():
                warning(f"Only got {len(image_prompts)} prompts, padding to {n_prompts}")
            # Pad with fallback prompts to reach n_prompts
            for fp in fallback_prompts:
                if len(image_prompts) >= n_prompts:
                    break
                image_prompts.append(fp)

        # Limit to n_prompts
        image_prompts = image_prompts[:n_prompts]

        self.visual_preflight = {}
        if is_max_retention(getattr(self, "_retention_mode", "")) and image_prompts:
            first_image_report = RetentionLab.score_image_prompt(
                image_prompts[0],
                topic=self.subject,
                first_image=True,
            )
            self.visual_preflight["first_image"] = first_image_report
            if get_verbose():
                info(
                    " => First image score: "
                    f"{first_image_report.get('score', 0)}/10"
                )

        # ------------------------------------------------------------------
        # Diversity guard (AI mode only) â€” detects the failure mode where
        # the LLM returns N near-identical "[name] in armor in front of
        # columns" portraits instead of N narratively distinct beats.
        # If it triggers, regenerate ONCE with a stricter directive.
        # ------------------------------------------------------------------
        if image_mode != "photos" and image_prompts and len(image_prompts) >= 3:

            def _looks_too_generic(prompts: List[str]) -> str:
                """Return a non-empty diagnostic string when prompts look
                like the failure mode, or "" if they pass the heuristic."""
                if not prompts:
                    return "no prompts"

                # 1. STATIC WALLPAPER â€” opens with generic stock framing like
                #    "A black hole in space", "A galaxy with stars",
                #    "A nebula floating", "A planet in the cosmos".
                portrait_re = re.compile(
                    r"^\s*(?:(?:A |An )?(?:black hole|galaxy|nebula|star|planet|moon|"
                    r"asteroid|comet|telescope|cosmic|space|universe)\s+"
                    r"(?:in|with|floating|drifting|sitting|surrounded|standing)"
                    r"|(?:A |An )?(?:Cosmic|Space|Galactic|Stellar|Planetary)\s+\w+\s+"
                    r"(?:scene|view|portrait|image|landscape))",
                    re.IGNORECASE,
                )
                portrait_count = sum(1 for p in prompts if portrait_re.search(p or ""))
                if portrait_count >= max(2, len(prompts) // 2):
                    return f"{portrait_count}/{len(prompts)} prompts open with a generic cosmic-wallpaper pattern"

                # 2. CHECKLIST â€” many prompts pile up >= 3 generic cosmic
                #    objects without a specific feature ("stars + nebula +
                #    galaxy + planet + moon" generic-space-art mode).
                generic_terms = {"stars", "nebula", "galaxy", "galaxies", "planet",
                                 "planets", "moon", "moons", "asteroid", "asteroids",
                                 "comet", "comets", "constellation", "constellations",
                                 "cosmic dust", "cosmic background", "starfield"}
                def _generic_hits(p: str) -> int:
                    low = (p or "").lower()
                    return sum(1 for t in generic_terms if t in low)
                heavy_generic = sum(1 for p in prompts if _generic_hits(p) >= 4)
                if heavy_generic >= max(2, len(prompts) // 2):
                    return f"{heavy_generic}/{len(prompts)} prompts read as generic-cosmos checklists"

                # 3. LEXICAL DUPLICATION â€” many prompts share their first 5 words.
                first5 = [" ".join((p or "").lower().split()[:5]) for p in prompts]
                if len(set(first5)) <= max(1, len(prompts) // 2):
                    return f"only {len(set(first5))} unique opening phrases across {len(prompts)} prompts"

                return ""

            diag = _looks_too_generic(image_prompts)
            first_image_report = self.visual_preflight.get("first_image") or {}
            if (
                not diag
                and is_max_retention(getattr(self, "_retention_mode", ""))
                and first_image_report
                and first_image_report.get("score", 10) < RetentionLab.FIRST_IMAGE_SCORE_THRESHOLD
            ):
                issues = ", ".join(first_image_report.get("issues") or [])
                diag = (
                    "first image prompt is weak "
                    f"({first_image_report.get('score')}/10"
                    + (f": {issues}" if issues else "")
                    + ")"
                )
            if diag:
                warning(f"Image prompts look generic ({diag}); regenerating once with stricter directive.")
                stricter = (
                    prompt
                    + "\n\nPREVIOUS ATTEMPT REJECTED â€” your prompts were "
                    + diag
                    + ". This is exactly the failure mode the rules above forbid. "
                    "Regenerate from scratch. Each of the "
                    f"{n_prompts} prompts MUST: (a) open with a different ACTION verb tied to a "
                    "specific moment of THIS script, (b) name a CONCRETE NARRATIVE OBJECT from "
                    "this story (the plow, the fasces, the wax tablet, the farmhouse, etc., "
                    "depending on what the story actually contains), (c) happen in a different "
                    "setting from the others. NEVER write \"X standing in armor in front of "
                    "columns\" â€” that is the exact pattern we are rejecting."
                )
                try:
                    retry_completion = (
                        str(self.generate_response(stricter))
                        .replace("```json", "").replace("```", "").strip()
                    )
                except Exception:
                    warning("   Stricter retry failed (all LLM providers unavailable); keeping original prompts.")
                    retry_completion = ""
                retry_prompts: List[str] = []
                try:
                    retry_prompts = _extract_prompts(json.loads(retry_completion))
                except Exception:
                    m = re.search(r"\[.*\]", retry_completion, re.DOTALL)
                    if m:
                        try:
                            retry_prompts = _extract_prompts(json.loads(m.group()))
                        except Exception:
                            pass
                if retry_prompts and len(retry_prompts) >= n_prompts:
                    retry_prompts = retry_prompts[:n_prompts]
                    if not _looks_too_generic(retry_prompts):
                        image_prompts = retry_prompts
                        if get_verbose():
                            info(" => Diversity-guard retry produced acceptable prompts.")
                    else:
                        # Retry also fell into the failure mode â€” keep the original;
                        # at least it parsed. Nothing more to do here without a third call.
                        warning("   Retry still looked generic; keeping original prompts.")

        if is_max_retention(getattr(self, "_retention_mode", "")) and image_prompts:
            self.visual_preflight["first_image"] = RetentionLab.score_image_prompt(
                image_prompts[0],
                topic=self.subject,
                first_image=True,
            )

        if get_verbose():
            info(f" => Generated Image Prompts: {image_prompts}")

        self.image_prompts = image_prompts

        success(f"Generated {len(image_prompts)} Image Prompts.")

        return image_prompts

    def _persist_image(self, image_bytes: bytes, provider_label: str) -> str:
        """
        Writes generated image bytes to a PNG file in the .mp scratch folder.

        Args:
            image_bytes (bytes): Image payload
            provider_label (str): Label for logging

        Returns:
            path (str): Absolute image path
        """
        image_path = os.path.join(get_temp_cache_path(), str(uuid4()) + ".png")

        with open(image_path, "wb") as image_file:
            image_file.write(image_bytes)

        if get_verbose():
            info(f' => Wrote image from {provider_label} to "{image_path}"')

        self.images.append(image_path)
        return image_path

    def _should_use_codex_cli_images(self) -> bool:
        try:
            from llm_provider import get_active_provider
            return (
                get_image_provider() == "auto"
                and
                get_active_provider() == "openai"
                and get_openai_use_codex_cli()
                and get_codex_cli_generate_images()
            )
        except Exception:
            return False

    def _ai_image_provider_choice(self) -> str:
        try:
            return get_image_provider()
        except Exception:
            return "auto"

    def _ai_image_providers(self, width: int = 1080, height: int = 1920) -> list[tuple[str, object, str]]:
        """Return AI image providers in the order selected for this job."""
        provider = self._ai_image_provider_choice()
        if provider == "openai":
            return [("OpenAI Codex Image", lambda p: self._try_codex_cli_image(p, width, height), "ai")]
        if provider == "gemini":
            return [("Gemini Nano Banana", lambda p: self._try_gemini_image(p, width, height), "ai")]
        if provider == "leonardo":
            if width > height:
                return [("Leonardo AI", lambda p: self._try_leonardo_landscape(p), "ai")]
            return [("Leonardo AI", self._try_leonardo, "ai")]

        providers = []
        if self._should_use_codex_cli_images():
            providers.append(("Codex CLI Image", lambda p: self._try_codex_cli_image(p, width, height), "ai"))
        if width > height:
            providers.append(("Leonardo AI", lambda p: self._try_leonardo_landscape(p), "ai"))
        else:
            providers.append(("Leonardo AI", self._try_leonardo, "ai"))
        providers.append(("Gemini Nano Banana", lambda p: self._try_gemini_image(p, width, height), "ai"))
        if width <= height:
            providers.append(("HuggingFace", self._try_huggingface, "ai"))
        return providers

    def _try_codex_cli_image(self, prompt: str, width: int = 1080, height: int = 1920) -> bytes:
        """Ask the locally authenticated Codex CLI to create a visual asset."""
        from codex_image_provider import generate_image_bytes_with_codex
        from llm_provider import get_active_model, get_active_provider

        print(colored(f"    [Codex CLI Image] Generating...", "cyan"), flush=True)
        active_model = get_active_model() if get_active_provider() == "openai" else ""
        return generate_image_bytes_with_codex(
            prompt,
            width=width,
            height=height,
            model=active_model if isinstance(active_model, str) else "",
        )

    def _try_gemini_image(self, prompt: str, width: int = 1080, height: int = 1920) -> bytes:
        """Generate a visual with Gemini Nano Banana."""
        from gemini_image_provider import generate_image_bytes_with_gemini

        print(colored(f"    [Gemini Nano Banana] Generating...", "cyan"), flush=True)
        return generate_image_bytes_with_gemini(prompt, width=width, height=height)

    def _try_huggingface(self, prompt: str) -> bytes:
        """Try HuggingFace Inference API. Requires free HF token."""
        from config import get_hf_api_key
        hf_token = get_hf_api_key()
        if not hf_token:
            raise RuntimeError("HuggingFace token not configured (hf_api_key in config.json)")

        print(colored(f"    [HuggingFace] Generating...", "cyan"), flush=True)
        headers = {"Authorization": f"Bearer {hf_token}"}

        models = [
            "stabilityai/stable-diffusion-xl-base-1.0",
        ]

        for model in models:
            try:
                resp = requests.post(
                    f"https://router.huggingface.co/hf-inference/models/{model}",
                    headers=headers,
                    json={"inputs": prompt[:300]},
                    timeout=120,
                )
                ct = resp.headers.get("content-type", "")
                if resp.status_code == 200 and ("image" in ct or len(resp.content) > 5000):
                    print(colored("OK", "green"))
                    return resp.content
            except Exception:
                continue
        raise RuntimeError("HuggingFace: all models failed")

    def _try_ideogram(self, prompt: str) -> bytes:
        """Try Ideogram API (very high quality, free tier ~25 images/day)."""
        from config import get_ideogram_api_key
        api_key = get_ideogram_api_key()
        if not api_key:
            raise RuntimeError("Ideogram API key not configured")

        print(colored(f"    [Ideogram] Generating...", "cyan"), flush=True)
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        payload = {
            "image_request": {
                "prompt": prompt[:1000],
                "model": "V_2",
                "aspect_ratio": "ASPECT_9_16",
            }
        }
        resp = requests.post(
            "https://api.ideogram.ai/generate",
            headers=headers, json=payload, timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        images = data.get("data", [])
        if not images:
            raise RuntimeError("Ideogram: no images returned")
        img_url = images[0].get("url", "")
        if not img_url:
            raise RuntimeError("Ideogram: no image URL")
        img_resp = requests.get(img_url, timeout=60)
        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
            print(colored("OK", "green"))
            return img_resp.content
        raise RuntimeError("Ideogram: failed to download image")

    def _try_leonardo(self, prompt: str) -> bytes:
        """Try Leonardo AI API (excellent quality, $5 free credit).
        Uses Phoenix 1.0 by default â€” it follows long prompts much better
        than Lightning XL, which was averaging out specific subjects (e.g.
        rendering "Plato" as a generic Greek figure)."""
        from config import get_leonardo_api_key
        api_key = get_leonardo_api_key()
        if not api_key:
            raise RuntimeError("Leonardo AI API key not configured")

        print(colored(f"    [Leonardo AI] Generating...", "cyan"), flush=True)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt[:1500],
            "modelId": "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3",  # Leonardo Phoenix 1.0
            "width": 576,
            "height": 1024,
            "num_images": 1,
            "contrast": 3.5,
            "alchemy": True,
        }
        # When the channel forces an artistic style, hint to Leonardo via
        # presetStyle so it applies an aesthetic LoRA on top of the prompt.
        # Detection is keyword-based on the channel's image_style.
        style_text = (self._image_style or "").lower()
        if any(k in style_text for k in ("cartoon", "anime", "illustration", "animated", "cel shading", "hand-drawn")):
            payload["presetStyle"] = "ILLUSTRATION"
        elif any(k in style_text for k in ("cinematic", "film", "movie")):
            payload["presetStyle"] = "CINEMATIC"
        elif self._image_style:
            payload["presetStyle"] = "DYNAMIC"
        resp = requests.post(
            "https://cloud.leonardo.ai/api/rest/v1/generations",
            headers=headers, json=payload, timeout=30,
        )
        resp.raise_for_status()
        gen_id = resp.json().get("sdGenerationJob", {}).get("generationId", "")
        if not gen_id:
            raise RuntimeError("Leonardo: no generation ID returned")

        # Poll for completion
        for _ in range(30):
            time.sleep(5)
            status_resp = requests.get(
                f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}",
                headers=headers, timeout=15,
            )
            status_resp.raise_for_status()
            gen = status_resp.json().get("generations_by_pk", {})
            status = gen.get("status", "")
            if status == "COMPLETE":
                images = gen.get("generated_images", [])
                if images:
                    img_url = images[0].get("url", "")
                    img_resp = requests.get(img_url, timeout=60)
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        print(colored("OK", "green"))
                        return img_resp.content
                raise RuntimeError("Leonardo: no image in result")
            elif status == "FAILED":
                raise RuntimeError("Leonardo: generation failed")
        raise RuntimeError("Leonardo: timeout waiting for generation")

    def _augment_for_ai_fallback(self, query: str) -> str:
        """Wrap a short photo-mode search query with neutral mood cues so AI
        generators render a usable image. We DO NOT inject 'photorealistic'
        / 'cinematic photograph' here anymore â€” those would override a
        cartoon / illustration channel style. The actual aesthetic is
        decided by `_apply_channel_style` (channel image_style or default
        baseline)."""
        out = f"{query}, dramatic lighting, highly detailed composition"
        return self._apply_channel_style(out)

    @staticmethod
    def load_metadata_sidecar(video_path: str) -> dict | None:
        """Read a `<video>.meta.json` and return a flat dict
        ``{title, description, subject, thumbnail_path, is_long}``.

        Handles both sidecar formats currently in the wild:

        * Nested (the format ``_persist_metadata_sidecar`` writes today)::

              {"subject": ..., "metadata": {"title": ..., "description": ...},
               "is_long": ..., "thumbnail_path": ...}

        * Flat (older / refactor-branch format)::

              {"title": ..., "description": ..., "subject": ...,
               "thumbnail_path": ...}

        Returns ``None`` if the sidecar is missing or unreadable.
        """
        sidecar = os.path.splitext(video_path)[0] + ".meta.json"
        if not os.path.isfile(sidecar):
            return None
        try:
            with open(sidecar, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
        except Exception:
            return None

        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else None
        title = (meta or raw).get("title", "") or ""
        description = (meta or raw).get("description", "") or ""
        return {
            "title": title,
            "description": description,
            "subject": raw.get("subject", "") or "",
            "thumbnail_path": raw.get("thumbnail_path", "") or "",
            "is_long": bool(raw.get("is_long", False)),
        }

    def _transcribe_video_audio(self, video_path: str) -> str:
        """Run faster-whisper over the audio of a rendered .mp4 and return the
        concatenated transcript. Used as a metadata-recovery fallback when
        re-uploading an orphan video that lost its sidecar.
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise RuntimeError(
                "faster-whisper is required for transcript-based metadata "
                "recovery. Install it (`pip install faster-whisper`) or "
                "provide the topic manually."
            ) from e

        info(f"  [Whisper] Loading model '{get_whisper_model()}'...")
        model = WhisperModel(
            get_whisper_model(),
            device=get_whisper_device(),
            compute_type=get_whisper_compute_type(),
        )
        info("  [Whisper] Transcribing audio (this may take a minute)...")
        segments, _ = model.transcribe(video_path, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments if s.text and s.text.strip())
        return text.strip()

    def reupload_video(
        self,
        video_path: str,
        subject: str | None = None,
        generate_thumbnail: bool = False,
        is_long: bool | None = None,
        upload: bool = True,
    ) -> bool:
        """Re-upload an already-rendered .mp4 by reusing the standard
        ``upload_video`` Selenium flow.

        Metadata source priority:

        1. ``<video>.meta.json`` sidecar â€” fastest, no LLM call.
        2. *subject* argument â€” generate title + description from the topic.
        3. Whisper transcript â€” recover from the audio when there is no
           sidecar and the user does not remember the topic.

        If ``generate_thumbnail`` is true, generate a custom thumbnail when
        one is not already restored from the sidecar.

        If ``upload`` is false, only recover/persist metadata and return True.
        Otherwise returns whatever ``upload_video`` returns.
        """
        if not os.path.isfile(video_path):
            error(f"Cannot re-upload: file not found at '{video_path}'.")
            return False

        self.video_path = video_path

        # 1) Sidecar
        sidecar = self.load_metadata_sidecar(video_path)
        sidecar_is_long = bool(sidecar.get("is_long")) if sidecar else False
        effective_is_long = sidecar_is_long if sidecar else bool(is_long)
        self._is_long_video = effective_is_long

        if sidecar and sidecar.get("title") and sidecar.get("description"):
            self.subject = sidecar.get("subject", "")
            self.metadata = {
                "title": sidecar["title"],
                "description": sidecar["description"],
            }
            saved_thumb = sidecar.get("thumbnail_path", "")
            if saved_thumb and os.path.isfile(saved_thumb):
                self.thumbnail_path = saved_thumb
                info(f" => Restored thumbnail from sidecar: {saved_thumb}")
            elif generate_thumbnail:
                try:
                    info(" => Generating thumbnail before upload...")
                    self.generate_thumbnail()
                except Exception as e:
                    warning(f"Thumbnail generation failed: {str(e)[:200]} (upload will continue without custom thumbnail)")
                    self.thumbnail_path = ""
            self._persist_metadata_sidecar(is_long=effective_is_long)
            info(" => Loaded saved metadata from sidecar.")
            success(f" => Title: {self.metadata['title']}")
            if not upload:
                return True
            return self.upload_video()

        # 2) Subject provided â†’ ask the LLM for title + description.
        if subject and subject.strip():
            self.subject = subject.strip()
            info(f" => Generating title + description for subject: {self.subject}")
            title_prompt = (
                f"Please generate a YouTube Video Title for the following subject: {self.subject}. "
                f"Optionally include 1-2 relevant hashtags at the end (but only if they fit naturally). "
                f"Only return the title, nothing else. Limit the title under 80 characters. Be concise. "
                f"YOU MUST WRITE THE TITLE IN {self._language}. Do NOT wrap the title in quotes."
            )
            desc_prompt = (
                f"Please generate a YouTube Video Description (2-4 sentences) for a video about: {self.subject}. "
                f"Only return the description, nothing else. Do NOT wrap it in quotes. "
                f"YOU MUST WRITE THE DESCRIPTION IN {self._language}."
            )
        else:
            # 3) Whisper fallback.
            transcript = self._transcribe_video_audio(video_path)
            if not transcript:
                error("Whisper produced an empty transcript â€” cannot generate metadata.")
                return False
            preview = transcript[:160] + ("..." if len(transcript) > 160 else "")
            info(f"  [Whisper] Transcript: {preview}")
            self.subject = transcript[:200]
            title_prompt = (
                f"Generate a YouTube Video Title that fits this video transcript:\n\n{transcript[:1500]}\n\n"
                f"Optionally include 1-2 relevant hashtags. Only return the title. "
                f"Limit under 80 characters. Be concise. "
                f"YOU MUST WRITE THE TITLE IN {self._language}. Do NOT wrap in quotes."
            )
            desc_prompt = (
                f"Generate a YouTube Video Description (2-4 sentences) that fits this transcript:\n\n{transcript[:2500]}\n\n"
                f"Only return the description, nothing else. Do NOT wrap in quotes. "
                f"YOU MUST WRITE THE DESCRIPTION IN {self._language}."
            )

        title = self.generate_response(title_prompt)
        title = re.sub(r'^[\"\'â€œâ€â€˜â€™]+|[\"\'â€œâ€â€˜â€™]+$', '', title.strip()).strip()
        if len(title) > 100:
            if "#" in title:
                title = title[:title.index("#")].strip()
            if len(title) > 100:
                title = title[:100]

        description = self.generate_response(desc_prompt)
        description = re.sub(r'^[\"\'â€œâ€â€˜â€™]+|[\"\'â€œâ€â€˜â€™]+$', '', description.strip()).strip()

        self.metadata = {"title": title, "description": description}
        success(f" => Title: {title}")
        info(f" => Description: {description[:120]}{'...' if len(description) > 120 else ''}")

        if generate_thumbnail:
            try:
                info(" => Generating thumbnail before upload...")
                self.generate_thumbnail()
            except Exception as e:
                warning(f"Thumbnail generation failed: {str(e)[:200]} (upload will continue without custom thumbnail)")
                self.thumbnail_path = ""

        # Persist a sidecar so a future retry skips the LLM/Whisper round.
        # Detect long-vs-short from existing sidecar if any; default short.
        self._persist_metadata_sidecar(is_long=effective_is_long)

        if not upload:
            return True
        return self.upload_video()

    def _persist_metadata_sidecar(self, is_long: bool) -> None:
        """Write a `<video_basename>.meta.json` next to the rendered .mp4 with
        subject + metadata + kind, so that a later upload-last invocation
        (which runs in a fresh subprocess and has no in-memory state) can
        recover what to upload. Without this sidecar the user gets
        'subject is empty' when clicking Subir from the dialog after generation.
        """
        try:
            video_path = getattr(self, "video_path", "")
            if not video_path:
                return
            sidecar = os.path.splitext(video_path)[0] + ".meta.json"
            payload = {
                "subject": getattr(self, "subject", "") or "",
                "metadata": getattr(self, "metadata", {}) or {},
                "is_long": bool(is_long),
                "thumbnail_path": getattr(self, "thumbnail_path", "") or "",
                # Stamp the owning channel so upload-last can never cross
                # channels even if the per-channel ref pointer is missing.
                "channel_id": getattr(self, "_account_uuid", "") or "",
                "retention_mode": getattr(self, "_retention_mode", "") or "",
                "retention_preflight": getattr(self, "retention_preflight", {}) or {},
                "retention_hook_lab": getattr(self, "retention_hook_lab", {}) or {},
                "visual_beat_map": getattr(self, "visual_beat_map", []) or [],
                "visual_beat_report": getattr(self, "visual_beat_report", {}) or {},
                "visual_preflight": getattr(self, "visual_preflight", {}) or {},
                "retention_plan": getattr(self, "retention_plan", {}) or {},
            }
            with open(sidecar, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            if get_verbose():
                info(f" => Wrote upload sidecar: {sidecar}")
        except Exception as e:
            if get_verbose():
                warning(f"Could not write upload sidecar: {e}")

    def _build_retention_plan(self, video_path: str = "") -> dict:
        if not is_max_retention(getattr(self, "_retention_mode", "")):
            self.retention_plan = {}
            return {}
        script = getattr(self, "script", "") or ""
        if not script.strip():
            self.retention_plan = {}
            return {}
        try:
            history_videos = self.get_videos()
        except Exception:
            history_videos = []
        try:
            plan = RetentionLab.build_retention_plan(
                script=script,
                topic=getattr(self, "subject", "") or "",
                niche=getattr(self, "niche", "") or "",
                language=getattr(self, "language", "") or "",
                retention_mode=getattr(self, "_retention_mode", "") or "",
                video_path=os.path.abspath(video_path or getattr(self, "video_path", "") or ""),
                retention_preflight=getattr(self, "retention_preflight", {}) or {},
                retention_hook_lab=getattr(self, "retention_hook_lab", {}) or {},
                visual_beat_map=getattr(self, "visual_beat_map", []) or [],
                visual_beat_report=getattr(self, "visual_beat_report", {}) or {},
                visual_preflight=getattr(self, "visual_preflight", {}) or {},
                history_videos=history_videos,
            )
            self.retention_plan = plan
            if get_verbose():
                info(
                    " => Retencion Pro: "
                    f"{plan.get('status', 'unknown')} "
                    f"score={plan.get('overall_score', 0)}/10"
                )
            return plan
        except Exception as exc:
            self.retention_plan = {}
            if get_verbose():
                warning(f"Could not build Retencion Pro plan: {exc}")
            return {}

    def _persist_retention_plan(self) -> None:
        try:
            plan = getattr(self, "retention_plan", {}) or {}
            video_path = getattr(self, "video_path", "") or ""
            if plan and video_path:
                RetentionLab.persist_retention_plan(video_path, plan)
        except Exception as exc:
            if get_verbose():
                warning(f"Could not persist Retencion Pro plan: {exc}")

    # Default visual baseline applied when a channel has NO `image_style`
    # configured. Goal: keep all images uniform (same realism level) and let
    # the scene description itself carry the period-accurate clothing / setting
    # / objects. We deliberately avoid any "art style" cue (no "cinematic",
    # "painting", "cartoon", "illustration").
    #
    # PROMPTING NOTES:
    # - Lead with strong POSITIVE single-frame phrasing ("one full-bleed
    #   photograph filling the entire frame edge to edge"). Gemini / Nano
    #   Banana 2 respond much better to positive composition anchors than to
    #   "no panels / no collage" negatives, which can backfire via priming.
    # - Avoid identifiable faces by default. Hands, clothing, posture, props,
    #   silhouettes and environments carry the human emotion while preserving
    #   the documentary realism.
    DEFAULT_BASE_STYLE = (
        "one full-bleed cinematic photograph filling the entire frame edge to edge, "
        "one continuous uninterrupted scene captured in a single real exposure, "
        "ultra-photorealistic, true-to-life documentary realism, shot on full-frame "
        "digital cinema camera with a 50mm prime lens at f/2.0, shallow depth of field "
        "with natural creamy bokeh, motivated naturalistic lighting (soft key plus ambient fill), "
        "rich filmic color grading reminiscent of Kodak Vision3 500T, subtle volumetric haze, "
        "period-accurate clothing architecture weapons and everyday objects rendered as "
        "real physical materials (wool, linen, bronze, leather, dyed cloth, weathered stone, "
        "oiled wood), authentic textures with visible wear and micro-detail, "
        "human presence shown through realistic hands, clothing folds, posture, silhouettes, "
        "tools and environmental interaction, faces not visible or not identifiable, "
        "backs of heads, over-the-shoulder views, profile silhouettes, faces obscured by "
        "shadow, helmets, veils, hoods, smoke, documents or foreground objects, "
        "accurate hands with exactly five fingers, correct anatomy, "
        "fine 35mm film grain, no over-sharpening, neutral documentary tone, "
        "no front-facing faces, no portraits, no selfies, no beauty shots, no detailed eyes, "
        "no recognizable likeness, no cartoon, no illustration, no painting, no anime, no stylization, no cel-shading, "
        "no airbrushed look, no plastic skin, no waxy skin, no AI gloss"
    )

    FACE_SAFE_COMPOSITION = (
        "Face-safe composition: avoid identifiable faces. If humans appear, show hands, "
        "backs, silhouettes, over-the-shoulder angles, side profiles in shadow, or faces "
        "obscured by helmets, hoods, documents, smoke, tools or foreground objects. "
        "Use posture, gesture, clothing, props and environment to convey emotion."
    )

    # Words that frequently push Gemini / Nano Banana 2 toward producing a
    # multi-panel collage instead of a single image. Stripped from any LLM
    # prompt before it's sent to the image generator. Word-boundary regex.
    _COLLAGE_TRIGGERS = re.compile(
        r"\b("
        r"collage|montage|storyboard|comic[- ]?strip|panels?|grid|split[- ]?screen|"
        r"diptych|triptych|polyptych|side[- ]?by[- ]?side|before[- ]?and[- ]?after|"
        r"sequences?|series of|set of \d+|multiple (?:images|scenes|frames)|"
        r"frames?|stills?|tiled|stacked"
        r")\b",
        re.IGNORECASE,
    )

    _FACE_PROMPT_REWRITES: tuple[tuple[re.Pattern, str], ...] = (
        (re.compile(r"\btight close[- ]up of a single face\b", re.IGNORECASE),
         "tight close detail of hands, clothing and the story object, face outside the frame"),
        (re.compile(r"\b(?:extreme |tight )?close[- ]up of (?:a |the |his |her |their )?face\b", re.IGNORECASE),
         "close detail of hands, clothing and the story object, face outside the frame"),
        (re.compile(r"\bfront[- ]facing (?:face|portrait|person|subject)\b", re.IGNORECASE),
         "subject turned away from camera"),
        (re.compile(r"\bportrait(?:s)?\b", re.IGNORECASE),
         "environmental scene with face not visible"),
        (re.compile(r"\bfacial expression(?:s)?\b", re.IGNORECASE),
         "body language and hand gesture"),
        (re.compile(r"\bfaces? (?:showing|locked|frozen|filled with|show)\b", re.IGNORECASE),
         "postures showing"),
        (re.compile(r"\bintense expression on the subject\b", re.IGNORECASE),
         "tense body language from the subject, face turned away"),
        (re.compile(r"\bvisible emotion \(eyes, jaw, brow\)\b", re.IGNORECASE),
         "visible emotion through posture, shoulders and hands"),
        (re.compile(r"\beyes?, jaw, brow\b", re.IGNORECASE),
         "posture, shoulders and hands"),
        (re.compile(r"\bsharp detailed eyes?\b", re.IGNORECASE),
         "hands and material details"),
        (re.compile(r"\brecognizable likeness\b", re.IGNORECASE),
         "non-identifiable human presence"),
    )

    @classmethod
    def _sanitize_image_prompt(cls, text: str) -> str:
        """Remove multi-image trigger words from a prompt. Image generators
        (especially Gemini) interpret words like "panels", "sequence",
        "storyboard" as a request for a collage even when context says "one
        image" â€” so we strip them defensively before sending."""
        if not text:
            return text
        cleaned = cls._COLLAGE_TRIGGERS.sub("", text)
        for pattern, replacement in cls._FACE_PROMPT_REWRITES:
            cleaned = pattern.sub(replacement, cleaned)
        # Collapse double spaces and stray punctuation left after substitution.
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        cleaned = re.sub(r"\s+,", ",", cleaned)
        cleaned = re.sub(r",\s*,", ",", cleaned)
        return cleaned.strip(" ,")

    def _apply_channel_style(self, prompt: str) -> str:
        """
        Wrap an LLM-produced scene description with the channel's visual
        style + an era anchor so each image is on-topic AND consistent with
        the channel's aesthetic.

        Two modes:

        1) Channel has a custom `image_style` (e.g. cartoon, watercolor,
           anime). The style MUST dominate. We frame the prompt so Gemini
           reads it as: STYLE first, scene second, period items as content
           (NOT as realism cues), STYLE again at the end. The era block uses
           neutral wording ("use these era-appropriate items") instead of
           "period-accurate" / "photorealistic" cues that would fight the
           channel style.

        2) No `image_style` configured â†’ fall back to `DEFAULT_BASE_STYLE`
           (photoreal documentary look) and a stronger era anchor that
           explicitly forbids modern/industrial visuals.

        The split matters: with a cartoon channel we don't want phrases like
        "photorealistic" or "realistic skin" in the prompt because Gemini
        will average between the two and produce neither.
        """
        clean_prompt = self._sanitize_image_prompt(prompt).rstrip(', .')
        ctx = self._get_context_profile()
        custom_style = (self._image_style or "").strip()

        # Guard against placeholder / garbage image_style values like "1", "x",
        # "test", "default", or any string with fewer than 2 alphabetic words.
        # Without this, a config like image_style="1" makes us emit
        # "ART STYLE: 1" to the LLM, which then drifts into a generic cartoon
        # look instead of falling through to the photoreal default.
        if custom_style:
            alpha_words = [w for w in _unicode_words(custom_style) if len(w) >= 3]
            stripped_lower = custom_style.lower().strip()
            if (
                len(custom_style) < 8
                or len(alpha_words) < 2
                or stripped_lower in {"default", "test", "tbd", "todo", "n/a", "na", "none"}
            ):
                if get_verbose():
                    info(
                        f" => Ignoring placeholder image_style {custom_style!r}; "
                        f"falling back to photoreal default."
                    )
                custom_style = ""

        parts: list[str] = []

        if custom_style:
            # Style anchored at front for maximum weight, then scene, then a
            # neutral setting clause, then style repeated at the end as reminder.
            short_style = custom_style if len(custom_style) <= 200 else custom_style[:200].rsplit(",", 1)[0]
            parts.append(f"ART STYLE â€” render the entire image in this style: {custom_style}")
            parts.append(clean_prompt)
            if ctx and (ctx.get("setting") or ctx.get("visual_anchors")):
                setting_clause = (
                    f"ERA ACCURACY â€” this scene takes place in {ctx['setting']}. All clothing, architecture, objects and environment MUST be period-faithful to this era. " if ctx.get("setting") else ""
                )
                anchors_clause = (
                    f"Period-accurate elements to weave into the scene naturally (in the art style above): {ctx['visual_anchors']}. "
                    if ctx.get("visual_anchors") else ""
                )
                avoid_clause = (
                    f"FORBIDDEN â€” anachronistic or off-era elements: {ctx['must_avoid']}." if ctx.get("must_avoid") else ""
                )
                parts.append((setting_clause + anchors_clause + avoid_clause).strip())
            parts.append(
                f"FINAL REMINDER â€” keep the entire image in the art style described above ({short_style}). "
                f"Do NOT default to photorealism. Do NOT add realistic skin texture or photographic lighting. "
                f"The art style overrides any realism implied by the scene. {self.FACE_SAFE_COMPOSITION}"
            )
        else:
            parts.append(clean_prompt)
            if ctx and (ctx.get("setting") or ctx.get("visual_anchors")):
                setting_clause = (
                    f"ERA ACCURACY â€” this scene takes place in {ctx['setting']}. All clothing, architecture, objects and environment MUST be period-faithful to this era. " if ctx.get("setting") else ""
                )
                anchors_clause = (
                    f"Period-accurate elements to weave into the scene naturally: {ctx['visual_anchors']}. "
                    if ctx.get("visual_anchors") else ""
                )
                avoid_clause = (
                    f"FORBIDDEN â€” anachronistic or off-era elements: {ctx['must_avoid']}."
                    if ctx.get("must_avoid") else ""
                )
                parts.append((setting_clause + anchors_clause + avoid_clause).strip())
            parts.append(self.DEFAULT_BASE_STYLE)
            parts.append(self.FACE_SAFE_COMPOSITION)

        combined = ". ".join(p for p in parts if p)
        # Hard cap to ~1500 chars â€” Gemini accepts up to ~1900 in our payload
        # cap, so this leaves headroom while preventing prompt explosion.
        return combined[:1500]

    def _get_context_profile(self) -> dict:
        """
        Niche-agnostic context anchor for image-prompt generation.

        Uses the LLM to derive a per-video brief from the channel niche +
        topic + script, returning a dict shaped like:

            {
                "setting": "<short descriptor of where/when/in-what-world the
                            video takes place â€” e.g. 'Ancient Rome',
                            'Modern Wall Street trading floor',
                            'Pro NFL stadium', 'Tokyo high-end omakase
                            kitchen', 'Suburban American household 2020s'>",
                "visual_anchors": "<comma-separated concrete props, clothing,
                            architecture, objects and environmental cues that
                            should appear naturally in scenes for this video>",
                "must_avoid": "<comma-separated visual elements that would be
                            anachronistic or off-topic for this setting>"
            }

        Replaces the previous hardcoded CIVILIZATIONS keyword-matching system,
        which only covered ~17 historical eras and forced every channel into
        civilization-flavored visuals. The new approach works for any niche â€”
        history, science, finance, sports, food, tech, modern stories, etc.

        Cached per (subject, len(script)) tuple. Returns {} on parse failure
        or when the LLM declines (in which case no extra anchor is injected
        and the prompt falls back to scene-only content).
        """
        subject = (getattr(self, "subject", "") or "").strip()
        script = (getattr(self, "script", "") or "").strip()
        niche = (getattr(self, "niche", "") or "").strip()
        if not subject and not script:
            return {}

        cache_key = (subject, len(script))
        cached = getattr(self, "_ctx_profile_cached", None)
        if getattr(self, "_ctx_profile_key", None) == cache_key and cached is not None:
            return cached

        # Sample beginning + middle + end of the script (â‰ˆ3000 chars total) so
        # the visual anchors cover the WHOLE video, not just the intro. For a
        # 20-min documentary that visits multiple eras / places, sampling
        # only the first 1200 chars (the previous behaviour) made later
        # sections inherit visual anchors derived only from the cold open.
        SAMPLE = 1000
        if len(script) <= SAMPLE * 3:
            script_excerpt = script
        else:
            mid_start = (len(script) // 2) - (SAMPLE // 2)
            script_excerpt = (
                f"{script[:SAMPLE]}\n[... middle of script ...]\n"
                f"{script[mid_start:mid_start + SAMPLE]}\n[... end of script ...]\n"
                f"{script[-SAMPLE:]}"
            )
        prompt = f"""You are a visual research assistant. Read the channel niche, the video topic and the script excerpt, and produce a JSON brief that will anchor image generation for this single video.

CHANNEL NICHE: {niche or "(not specified)"}
VIDEO TOPIC: {subject or "(not specified)"}
SCRIPT EXCERPT (sampled across the full video â€” beginning, middle and end):
\"\"\"
{script_excerpt}
\"\"\"

Return ONLY a JSON object with EXACTLY these three string fields:
- "setting": a short descriptor of WHERE and WHEN the story happens â€” pick the most specific real-world setting that fits the topic and script (e.g. "Ancient Rome, late Republic", "Modern Wall Street trading floor", "Pro NFL stadium, game day", "Tokyo high-end omakase kitchen", "Silicon Valley startup office, 2020s", "Rural American farmhouse, present day", "Open ocean, modern container ship"). Do NOT default to "ancient civilization" unless the topic clearly requires it.
- "visual_anchors": a comma-separated list of CONCRETE props, clothing, architecture, vehicles, tools, environmental details that should appear naturally in scenes from this setting. 10 to 16 items. Be specific (materials, eras, styles). If the script visits multiple eras/places (e.g. ancient origin + modern legacy), include anchors from EACH so later sections of the video stay grounded.
- "must_avoid": a comma-separated list of visual elements that would be anachronistic, off-topic or break immersion for this setting. 4 to 8 items.

RULES:
- Match the SETTING to the actual subject. A topic about a modern athlete must NOT get a "Greek Olympics" setting just because the channel niche mentions sports history.
- If the script clearly visits multiple settings (origin + present-day, or different countries/eras), state the PRIMARY setting in "setting" but include anchors for ALL of them in "visual_anchors". Otherwise pick the one most viewers would picture.
- If the topic is abstract or the script is generic, pick the setting that most viewers would picture when reading the topic.
- Output ONLY the JSON object â€” no markdown, no preamble, no explanation. No code fences.
"""
        try:
            raw = str(self.generate_response(prompt) or "").strip()
        except Exception as e:
            if get_verbose():
                warning(f"Context profile LLM call failed: {e}")
            self._ctx_profile_key = cache_key
            self._ctx_profile_cached = {}
            return {}

        cleaned = raw.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        profile: dict = {}
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                profile = {
                    "setting": str(parsed.get("setting", "")).strip(),
                    "visual_anchors": str(parsed.get("visual_anchors", "")).strip(),
                    "must_avoid": str(parsed.get("must_avoid", "")).strip(),
                }
                # Drop the brief entirely if the LLM produced an empty / useless
                # blob â€” prevents injecting a placeholder anchor that would
                # confuse the image-prompt model.
                if not profile["setting"] and not profile["visual_anchors"]:
                    profile = {}
        except Exception as e:
            if get_verbose():
                warning(f"Context profile JSON parse failed: {e}")
            profile = {}

        if profile and get_verbose():
            info(f" => Context profile: setting='{profile.get('setting', '')[:80]}'")

        self._ctx_profile_key = cache_key
        self._ctx_profile_cached = profile
        return profile

    def _resolve_voice(self, voice: str) -> str:
        """Resolve a voice alias (e.g. 'Pablo') or raw Edge-TTS ID to its full voice ID."""
        from .Tts import EDGE_TTS_VOICES
        if not voice:
            return ""
        return EDGE_TTS_VOICES.get(voice, voice)

    def _topic_keywords(self) -> List[str]:
        """Key lowercase tokens from self.subject, used to anchor stock searches to the topic."""
        words = _unicode_words((self.subject or "").lower())
        return [w for w in words if len(w) > 2 and w not in _PHOTO_STOPWORDS]

    def _anchor_query(self, query: str) -> str:
        """Prepend up to 3 subject keywords not already in the query so stock results stay on-topic."""
        keywords = self._topic_keywords()
        if not keywords:
            return query
        q_lower = query.lower()
        anchor = " ".join(kw for kw in keywords[:3] if kw not in q_lower)
        return f"{anchor} {query}".strip() if anchor else query

    def _query_tokens(self, *texts: str) -> set:
        """Extract content-word tokens from the given strings for relevance checks."""
        combined = " ".join(t for t in texts if t).lower()
        tokens = _unicode_words(combined)
        return {t for t in tokens if len(t) > 2 and t not in _PHOTO_STOPWORDS}

    def _strict_anchor_tokens(self) -> set:
        """Distinctive tokens from the subject â€” generic words like 'roman' or
        'emperor' are dropped. These act as the must-match anchor when
        validating that a result is actually on-topic."""
        return set(self._topic_keywords()) - _GENERIC_TOPIC_TOKENS

    def _query_proper_nouns(self, query: str) -> set:
        """Capitalized words from the query â€” usually identify a specific
        person/place/event we want to actually appear in the result.
        Generic tokens (e.g. 'Roman') are stripped so they don't satisfy the
        anchor check on their own."""
        if not query:
            return set()
        nouns = _capitalized_unicode_tokens(query)
        out = set()
        for n in nouns:
            t = n.lower()
            if t in _PHOTO_STOPWORDS or t in _GENERIC_TOPIC_TOKENS:
                continue
            out.add(t)
        return out

    def _title_promises_list(self, title: str) -> bool:
        """True if the title promises a numbered list of items.
        Catches 'N <noun>' patterns ('5 curiosidades', '3 secretos', '7 razones')
        and 'Top N' constructions in Spanish/English. We trigger only on small
        single-digit lists (the typical clickbait range) â€” '1989' or 'mil aÃ±os'
        in a historical title shouldn't false-positive."""
        if not title:
            return False
        t = title.lower()
        # "N + noun" where N is 2-9 (single-digit clickbait counts).
        list_nouns = (
            r"curiosidad(?:es)?|secret[oa]s?|raz(?:Ã³n|on|ones)|cosas?|"
            r"dat[oa]s?|hech[oa]s?|reglas?|tips?|consejos?|trucos?|"
            r"misterios?|claves?|pasos?|errores?|verdades?|mitos?|"
            r"thing|things|reason|reasons|secret|secrets|fact|facts|"
            r"rule|rules|tip|tips|step|steps|truth|truths|myth|myths"
        )
        if re.search(rf"\b[2-9]\s+(?:{list_nouns})\b", t):
            return True
        # "Top N" in Spanish/English.
        if re.search(r"\btop\s+[2-9]\b", t):
            return True
        # "N <noun> que..." â€” catches "5 curiosidades que te sorprenderÃ¡n" even
        # when the noun isn't in the list above.
        if re.search(r"\b[2-9]\s+\w{4,}\s+que\b", t):
            return True
        return False

    def _title_uses_cliche(self, title: str) -> bool:
        """True if the title contains overused clickbait words we want to ban.

        These are basic/lazy hooks ('secreto', 'sabÃ­as que', 'increÃ­ble',
        'no vas a creer'â€¦) that the LLM keeps defaulting to. Detection is
        accent-insensitive and case-insensitive so 'sabias que' and 'SABÃAS
        QUE' both trigger.
        """
        if not title:
            return False
        # Strip accents for matching.
        import unicodedata
        norm = unicodedata.normalize("NFD", title.lower())
        norm = "".join(c for c in norm if unicodedata.category(c) != "Mn")
        cliche_phrases = (
            "secreto", "secretos", "misterio", "misterios",
            "sabias que", "no vas a creer", "te volara la cabeza",
            "increible", "impactante", "te sorprendera",
            "nadie sabe", "nadie te conto", "lo que no te dicen",
            "esto te dejara", "alucinante", "flipante",
            "shocking", "you won't believe", "you wont believe",
            "mind-blowing", "mind blowing", "secret", "mystery",
            "did you know",
        )
        for phrase in cliche_phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", norm):
                return True
        return False

    def _script_has_enumerated_items(self, script: str) -> bool:
        """Crude check: does the script actually list at least 3 enumerated items?
        Looks for explicit ordinal/list markers ('primero', 'segundo', 'tercero',
        'first', 'second', 'third', 'nÃºmero uno', 'one:', '1.', '2.', etc.).
        If it doesn't find them, we conclude the script tells one story and a
        list-form title is dishonest."""
        if not script:
            return False
        s = script.lower()
        markers = 0
        # Spanish ordinals as words
        for w in ("primero", "primera", "segundo", "segunda", "tercero", "tercera",
                  "cuarto", "cuarta", "quinto", "quinta", "sexto", "sexta",
                  "sÃ©ptimo", "sÃ©ptima", "octavo", "octava", "noveno", "novena"):
            if re.search(rf"\b{w}\b", s):
                markers += 1
        # English ordinals
        for w in ("first", "second", "third", "fourth", "fifth", "sixth",
                  "seventh", "eighth", "ninth"):
            if re.search(rf"\b{w}\b", s):
                markers += 1
        # Numbered list markers ("1.", "1)", "1 -")
        markers += len(re.findall(r"(?:^|\s)[1-9][\.\)\-:]\s", s))
        # "nÃºmero uno/dos/tres" / "number one/two/three"
        for w in ("uno", "dos", "tres", "cuatro", "cinco",
                  "one", "two", "three", "four", "five"):
            if re.search(rf"\bn[uÃº]mero\s+{w}\b|\bnumber\s+{w}\b", s):
                markers += 1
        return markers >= 3

    def _is_relevant(self, query: str, *result_texts: str) -> bool:
        """Strict relevance check used by every photo provider.

        A result counts as on-topic if it contains AT LEAST ONE distinctive
        anchor token â€” either from the subject itself or from the query's
        proper nouns. Generic words ('roman', 'emperor', 'history') are NOT
        sufficient on their own. If we can't derive any anchor (rare â€” e.g.
        the subject is a generic phrase), we fall back to the previous
        any-token overlap so the pipeline doesn't deadlock.
        """
        result_tokens = self._query_tokens(*result_texts)
        if not result_tokens:
            return False
        anchors = self._strict_anchor_tokens() | self._query_proper_nouns(query)
        if anchors:
            return bool(anchors & result_tokens)
        # No anchors at all â†’ fall back to the loose any-token check so we
        # still trim obvious off-topic results.
        loose = self._query_tokens(query, self.subject)
        return bool(loose & result_tokens) if loose else True

    def _extract_search_query(self, prompt: str) -> str:
        """Extract clean search keywords from an AI image prompt for stock photo search."""
        import re
        # Remove common AI style/photography keywords
        style_words = r'\b(cinematic|dramatic|lighting|8K|4K|ultra|HD|macro|bokeh|aerial|drone|cyberpunk|hyper-realistic|vibrant|saturated|documentary|photography|shot|wide|close-up|extreme|detailed|textures?|colors?|film grain|neon|volumetric|fog|aesthetic|digital painting|golden hour|breathtaking|raw|authentic|feel|shallow depth|field|sweeping|portrait|selfie|headshot|face|faces|facial|eyes?|style|composition|render|realistic|illustration|art|scene|view|high quality|resolution|background|foreground|angle|perspective|moody|atmosphere|accent|dark|light)\b'
        cleaned = re.sub(style_words, '', prompt, flags=re.IGNORECASE)
        cleaned = re.sub(r'[,\-:;"\'\(\)]', ' ', cleaned)
        cleaned = ' '.join(cleaned.split())
        # Take meaningful words (3-6) for search
        words = [w for w in cleaned.split() if len(w) > 2][:6]
        query = ' '.join(words) if words else self.subject
        return query

    def _try_pexels(self, prompt: str) -> bytes:
        """Try Pexels stock photos API (free, reliable, HD). Requires free API key."""
        from config import get_pexels_api_key
        api_key = get_pexels_api_key()
        if not api_key:
            raise RuntimeError("Pexels API key not configured")

        import urllib.parse
        import random

        # In photos mode the LLM already generated a clean query â€” don't strip it further.
        if getattr(self, "_image_mode", "ai") == "photos":
            query = prompt.strip()
        else:
            query = self._extract_search_query(prompt)
        query = self._anchor_query(query)

        print(colored(f"    [Pexels] Searching: {query[:60]}...", "cyan"), flush=True)
        headers = {"Authorization": api_key}
        # Fetch more results and pick a random page for more variety
        page = random.randint(1, 3)
        resp = requests.get(
            f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page=15&page={page}",
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            raise RuntimeError("Pexels: no photos found")

        # Relevance filter: alt text must contain a distinctive anchor token
        # from the subject or one of the query's proper nouns. Generic words
        # ('roman', 'emperor', etc.) alone are NOT enough â€” see _is_relevant.
        relevant = [p for p in photos if self._is_relevant(query, p.get("alt") or "")]
        if not relevant:
            raise RuntimeError("Pexels: no relevant photos (all off-topic)")
        photos = relevant

        # Filter out already-used images
        available = [p for p in photos if p["src"]["large2x"] not in self._used_stock_urls]
        if not available:
            available = photos  # all used, allow repeats as last resort

        photo = random.choice(available)
        img_url = photo["src"]["large2x"]  # high-res version
        self._used_stock_urls.add(img_url)
        img_resp = requests.get(img_url, timeout=60)
        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
            print(colored("OK", "green"))
            return img_resp.content
        raise RuntimeError("Pexels: failed to download image")

    def _try_pixabay(self, prompt: str) -> bytes:
        """Try Pixabay stock photos API (free, reliable, HD). Requires free API key."""
        from config import get_pixabay_api_key
        api_key = get_pixabay_api_key()
        if not api_key:
            raise RuntimeError("Pixabay API key not configured")

        import urllib.parse
        import random

        if getattr(self, "_image_mode", "ai") == "photos":
            query = prompt.strip()
        else:
            query = self._extract_search_query(prompt)
        query = self._anchor_query(query)

        print(colored(f"    [Pixabay] Searching: {query[:60]}...", "cyan"), flush=True)
        page = random.randint(1, 3)
        resp = requests.get(
            f"https://pixabay.com/api/?key={api_key}&q={urllib.parse.quote(query)}&image_type=photo&per_page=15&page={page}&min_width=1080",
            timeout=30,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            raise RuntimeError("Pixabay: no photos found")

        # Relevance filter: Pixabay `tags` is a comma-separated list â€” require
        # a distinctive anchor token (proper noun) overlap, not just any word.
        relevant = [h for h in hits if self._is_relevant(query, h.get("tags") or "")]
        if not relevant:
            raise RuntimeError("Pixabay: no relevant photos (all off-topic)")
        hits = relevant

        # Filter out already-used images
        available = [h for h in hits if h.get("largeImageURL", "") not in self._used_stock_urls]
        if not available:
            available = hits

        hit = random.choice(available)
        img_url = hit.get("largeImageURL", hit.get("webformatURL", ""))
        if not img_url:
            raise RuntimeError("Pixabay: no image URL in result")
        self._used_stock_urls.add(img_url)
        img_resp = requests.get(img_url, timeout=60)
        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
            print(colored("OK", "green"))
            return img_resp.content
        raise RuntimeError("Pixabay: failed to download image")

    def _try_wikipedia_article(self, prompt: str) -> bytes:
        """
        Find the Wikipedia article whose title best matches the query and return
        the article's MAIN image (the one in the infobox).

        Why this works better than Commons file-search for historical/educational topics:
          * Wikipedia's article search is fuzzy + redirects-aware (`Hiparco` â†’ `Hipparchus`).
          * The infobox image is curated to represent the topic.
          * Tries the channel's language wiki first, then English as fallback.
        """
        import urllib.parse
        import random

        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        # Channel-language wiki code (e.g. "es", "en") + English as fallback.
        lang_map = {"spanish": "es", "english": "en", "portuguese": "pt", "french": "fr",
                    "german": "de", "italian": "it"}
        ch_lang = lang_map.get((self._language or "").lower(), "en")
        wikis = [ch_lang, "en"] if ch_lang != "en" else ["en"]

        headers = {"User-Agent": "MoneyPrinterLargo/1.0 (research use)"}

        for wiki in wikis:
            print(colored(f"    [Wikipedia/{wiki}] Searching: {query[:60]}...", "cyan"), flush=True)
            try:
                # Step 1: search articles by query.
                search_url = (
                    f"https://{wiki}.wikipedia.org/w/api.php"
                    f"?action=query&format=json&list=search"
                    f"&srsearch={urllib.parse.quote(query)}"
                    f"&srlimit=10&srprop=size"
                )
                resp = requests.get(search_url, headers=headers, timeout=20)
                resp.raise_for_status()
                hits = resp.json().get("query", {}).get("search") or []
                if not hits:
                    continue

                # Try the top results until we find one with a usable infobox image.
                for hit in hits[:5]:
                    title = hit.get("title") or ""
                    if not title:
                        continue
                    # Step 2: fetch the article's main image at full resolution.
                    img_url = self._wikipedia_main_image(wiki, title, headers)
                    if not img_url or img_url in self._used_stock_urls:
                        continue
                    # Strict relevance check: the article title must contain
                    # at least one distinctive anchor token from the subject
                    # or query's proper nouns.
                    if not self._is_relevant(query, title):
                        continue
                    try:
                        img_resp = requests.get(img_url, headers=headers, timeout=60)
                        if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                            self._used_stock_urls.add(img_url)
                            print(colored(f"OK ({title[:50]})", "green"))
                            return img_resp.content
                    except Exception:
                        continue
            except Exception:
                continue

        raise RuntimeError("Wikipedia article: no suitable image found")

    def _wikipedia_main_image(self, wiki: str, title: str, headers: dict) -> str:
        """Get the original-resolution main image URL for a Wikipedia article."""
        import urllib.parse
        try:
            url = (
                f"https://{wiki}.wikipedia.org/w/api.php"
                f"?action=query&format=json&prop=pageimages"
                f"&piprop=original&titles={urllib.parse.quote(title)}"
            )
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {}) or {}
            for page in pages.values():
                src = (page.get("original") or {}).get("source") or ""
                if src:
                    return src
        except Exception:
            pass
        return ""

    def _try_wikimedia(self, prompt: str) -> bytes:
        """
        Search Wikimedia Commons file descriptions for matching images.
        Tries multiple query variants so we don't fail just because the LLM's
        query wording doesn't exactly match Commons file descriptions.
        """
        import urllib.parse
        import random

        # In photos mode the prompt is already a clean search query.
        # If it looks like an AI-style prompt (long / has style words), clean it.
        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        # Build a shortlist of query variants â€” try the original, then progressively
        # shorter / proper-noun-only versions so we recover from over-specific queries.
        words = query.split()
        STOP = {"the", "a", "an", "of", "in", "on", "at", "to", "and", "or",
                "el", "la", "los", "las", "un", "una", "y", "o", "de", "del"}
        proper_nouns = [w for w in words if w[:1].isupper() and w.lower() not in STOP]
        variants = []
        seen = set()
        for v in (query, " ".join(proper_nouns), " ".join(words[:3]), " ".join(proper_nouns[:2])):
            v = v.strip()
            if v and v.lower() not in seen:
                variants.append(v)
                seen.add(v.lower())

        headers = {"User-Agent": "MoneyPrinterLargo/1.0 (https://github.com/; research use)"}

        for variant in variants:
            print(colored(f"    [Wikimedia] Searching: {variant[:60]}...", "cyan"), flush=True)
            try:
                api_url = (
                    "https://commons.wikimedia.org/w/api.php"
                    "?action=query&format=json&generator=search&gsrnamespace=6"
                    f"&gsrsearch={urllib.parse.quote(variant)}&gsrlimit=20"
                    "&prop=imageinfo&iiprop=url|size|mime"
                )
                resp = requests.get(api_url, headers=headers, timeout=30)
                resp.raise_for_status()
                pages = resp.json().get("query", {}).get("pages", {})
                if not pages:
                    continue

                candidates = []
                for page in pages.values():
                    info_list = page.get("imageinfo", [])
                    if not info_list:
                        continue
                    info = info_list[0]
                    url = info.get("url", "")
                    mime = info.get("mime", "")
                    w, h = info.get("width", 0), info.get("height", 0)
                    title = page.get("title") or ""
                    if not url or url in self._used_stock_urls:
                        continue
                    if mime not in ("image/jpeg", "image/png", "image/webp"):
                        continue
                    if min(w, h) < 600:
                        continue
                    # Strict relevance check: file title (e.g. "File:Hipparchus.jpg")
                    # must contain a distinctive anchor token from the subject
                    # or query's proper nouns. Generic adjectives don't count.
                    if not self._is_relevant(variant, title):
                        continue
                    candidates.append(url)

                if not candidates:
                    continue
                random.shuffle(candidates)
                for img_url in candidates[:5]:
                    try:
                        img_resp = requests.get(img_url, headers=headers, timeout=60)
                        if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                            self._used_stock_urls.add(img_url)
                            print(colored("OK", "green"))
                            return img_resp.content
                    except Exception:
                        continue
            except Exception:
                continue

        raise RuntimeError("Wikimedia: no suitable images across all query variants")

    def _try_met_museum(self, prompt: str) -> bytes:
        """
        Met Museum Open Access (paintings, sculptures, artifacts, prints).
        No API key required. Best for art, statues, classical artifacts.
        Docs: https://metmuseum.github.io/
        """
        import urllib.parse
        import random

        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        print(colored(f"    [Met Museum] Searching: {query[:60]}...", "cyan"), flush=True)
        headers = {"User-Agent": "MoneyPrinterLargo/1.0 (research use)"}

        search_url = (
            "https://collectionapi.metmuseum.org/public/collection/v1/search"
            f"?q={urllib.parse.quote(query)}&hasImages=true"
        )
        resp = requests.get(search_url, headers=headers, timeout=30)
        resp.raise_for_status()
        obj_ids = (resp.json().get("objectIDs") or [])[:30]
        if not obj_ids:
            raise RuntimeError("Met Museum: no results")

        random.shuffle(obj_ids)

        for obj_id in obj_ids[:8]:
            try:
                obj_resp = requests.get(
                    f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{obj_id}",
                    headers=headers, timeout=20,
                )
                obj_resp.raise_for_status()
                obj = obj_resp.json()
                img_url = obj.get("primaryImage") or ""
                if not img_url or img_url in self._used_stock_urls:
                    continue
                # Strict relevance check against the object's metadata â€”
                # generic culture/period words ("Roman", "Imperial") on their
                # own do not satisfy _is_relevant.
                metadata_blob = " ".join(
                    str(obj.get(k, "")) for k in
                    ("title", "culture", "period", "objectName", "department",
                     "classification", "artistDisplayName", "country", "region")
                )
                if not self._is_relevant(query, metadata_blob):
                    continue
                img_resp = requests.get(img_url, headers=headers, timeout=60)
                if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                    self._used_stock_urls.add(img_url)
                    print(colored("OK", "green"))
                    return img_resp.content
            except Exception:
                continue
        raise RuntimeError("Met Museum: no usable image found")

    def _try_loc(self, prompt: str) -> bytes:
        """
        Library of Congress photo collection (historical photos, prints, maps,
        manuscripts, posters). No API key required.
        Docs: https://www.loc.gov/apis/json-and-yaml/
        """
        import urllib.parse
        import random

        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        print(colored(f"    [LoC] Searching: {query[:60]}...", "cyan"), flush=True)
        headers = {"User-Agent": "MoneyPrinterLargo/1.0 (research use)"}
        search_url = (
            f"https://www.loc.gov/photos/?q={urllib.parse.quote(query)}&fo=json&c=25"
        )
        resp = requests.get(search_url, headers=headers, timeout=30)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            raise RuntimeError("LoC: no results")

        candidates = []
        for r in results:
            urls = r.get("image_url") or []
            if not urls:
                continue
            # Largest version is typically the last entry.
            img_url = urls[-1]
            if not img_url or img_url in self._used_stock_urls:
                continue
            title = r.get("title") or ""
            descr = r.get("description") or ""
            if isinstance(descr, list):
                descr = " ".join(str(d) for d in descr)
            subj = r.get("subject") or []
            subj_text = " ".join(subj) if isinstance(subj, list) else str(subj)
            # Strict relevance: at least one distinctive anchor token must
            # appear in title/description/subject metadata.
            if not self._is_relevant(query, title, str(descr), subj_text):
                continue
            candidates.append(img_url)

        if not candidates:
            raise RuntimeError("LoC: no relevant images")

        random.shuffle(candidates)
        for img_url in candidates[:5]:
            try:
                img_resp = requests.get(img_url, headers=headers, timeout=60)
                if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                    self._used_stock_urls.add(img_url)
                    print(colored("OK", "green"))
                    return img_resp.content
            except Exception:
                continue
        raise RuntimeError("LoC: failed to download any candidate")

    def _try_wikidata(self, prompt: str) -> bytes:
        """
        Wikidata-driven image lookup. The flow is:
          1. Search Wikidata entities for the query in the channel language
             (es/en) â€” returns a Q-id whose label most closely matches.
          2. Fetch that entity's claims:
             * P18 (image) â†’ curated lead image used by every Wikipedia entry.
             * P373 (Commons category) â†’ curated category of related images
               about that exact entity (statues, coins, frescoes, etc.).
          3. Verify the entity's labels actually contain a distinctive anchor
             token from the subject â€” protects against Q-id collisions
             (e.g. "Nero" â†’ musician vs. emperor).

        Why this works better than fuzzy article search: Wikidata returns a
        deterministic entity ID, not a free-text article match. The image we
        get back is the canonical one Wikipedia uses everywhere â€” so for
        "Nero", we get the bust from the Capitoline Museums, not a generic
        Roman ruin.
        """
        import urllib.parse
        import random

        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        lang_map = {"spanish": "es", "english": "en", "portuguese": "pt", "french": "fr",
                    "german": "de", "italian": "it"}
        ch_lang = lang_map.get((self._language or "").lower(), "en")
        languages = [ch_lang, "en"] if ch_lang != "en" else ["en"]

        headers = {"User-Agent": "MoneyPrinterLargo/1.0 (research use)"}

        for lang in languages:
            print(colored(f"    [Wikidata/{lang}] Searching: {query[:60]}...", "cyan"), flush=True)
            try:
                search_url = (
                    "https://www.wikidata.org/w/api.php"
                    "?action=wbsearchentities&format=json&type=item"
                    f"&language={lang}&uselang={lang}"
                    f"&search={urllib.parse.quote(query)}&limit=8"
                )
                resp = requests.get(search_url, headers=headers, timeout=20)
                resp.raise_for_status()
                entities = resp.json().get("search") or []
                if not entities:
                    continue

                for ent in entities[:5]:
                    qid = ent.get("id") or ""
                    label = ent.get("label") or ""
                    desc = ent.get("description") or ""
                    if not qid:
                        continue

                    # Anchor check: the entity label/description must contain a
                    # distinctive token from the subject or the query's proper
                    # nouns. Filters out unrelated Q-ids that happen to share
                    # a generic word.
                    if not self._is_relevant(query, label, desc):
                        continue

                    # Fetch the entity's claims.
                    ent_url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
                    try:
                        ent_resp = requests.get(ent_url, headers=headers, timeout=20)
                        ent_resp.raise_for_status()
                        claims = (
                            ent_resp.json()
                            .get("entities", {})
                            .get(qid, {})
                            .get("claims", {})
                        )
                    except Exception:
                        continue

                    # Collect candidate Commons filenames.
                    candidates: List[str] = []

                    # P18 = primary image. Curated, single best image.
                    p18 = claims.get("P18") or []
                    for c in p18:
                        try:
                            fname = c["mainsnak"]["datavalue"]["value"]
                            if fname:
                                candidates.append(fname)
                        except Exception:
                            continue

                    # P373 = Commons category. Pull a sample of files from it
                    # so we get variety (busts, coins, paintings, etc.).
                    p373 = claims.get("P373") or []
                    for c in p373[:1]:
                        try:
                            cat_name = c["mainsnak"]["datavalue"]["value"]
                        except Exception:
                            continue
                        if not cat_name:
                            continue
                        try:
                            cat_url = (
                                "https://commons.wikimedia.org/w/api.php"
                                "?action=query&format=json&list=categorymembers"
                                f"&cmtitle=Category:{urllib.parse.quote(cat_name)}"
                                "&cmtype=file&cmlimit=20"
                            )
                            cat_resp = requests.get(cat_url, headers=headers, timeout=20)
                            cat_resp.raise_for_status()
                            members = (
                                cat_resp.json()
                                .get("query", {})
                                .get("categorymembers", [])
                            )
                            for m in members:
                                title = m.get("title") or ""
                                if title.startswith("File:"):
                                    fname = title[5:]
                                    # Skip non-image / generic logos.
                                    if any(fname.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
                                        candidates.append(fname)
                        except Exception:
                            continue

                    if not candidates:
                        continue

                    # Resolve filenames to full-resolution URLs via Special:FilePath.
                    random.shuffle(candidates)
                    for fname in candidates[:8]:
                        img_url = (
                            "https://commons.wikimedia.org/wiki/Special:FilePath/"
                            + urllib.parse.quote(fname.replace(" ", "_"))
                        )
                        if img_url in self._used_stock_urls:
                            continue
                        try:
                            img_resp = requests.get(img_url, headers=headers, timeout=60, allow_redirects=True)
                            if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                                self._used_stock_urls.add(img_url)
                                print(colored(f"OK ({label[:40]} / {qid})", "green"))
                                return img_resp.content
                        except Exception:
                            continue
            except Exception:
                continue

        raise RuntimeError("Wikidata: no suitable entity image found")

    def _try_europeana(self, prompt: str) -> bytes:
        """
        Europeana â€” aggregator of European cultural-heritage institutions
        (museums, libraries, archives). Free API key required.
        Coverage is similar in quality to Wikipedia for historical/art topics
        and often surfaces material that isn't on Commons (museum scans,
        digitized prints, period engravings).

        Docs: https://pro.europeana.eu/page/intro
        """
        from config import get_europeana_api_key
        api_key = get_europeana_api_key()
        if not api_key:
            raise RuntimeError("Europeana API key not configured")

        import urllib.parse
        import random

        query = prompt.strip()
        if len(query) > 60 or any(w in query.lower() for w in ("cinematic", "8k", "lighting", "photorealistic")):
            query = self._extract_search_query(prompt)

        print(colored(f"    [Europeana] Searching: {query[:60]}...", "cyan"), flush=True)
        headers = {"User-Agent": "MoneyPrinterLargo/1.0 (research use)"}

        # `media=true` â†’ only items with a real media URL we can download.
        # `type=IMAGE` â†’ drops audio/video/text. `reusability=open` would be
        # safer for licensing but excludes too much; we keep results broad
        # since the videos are not commercial in nature.
        search_url = (
            "https://api.europeana.eu/record/v2/search.json"
            f"?wskey={urllib.parse.quote(api_key)}"
            f"&query={urllib.parse.quote(query)}"
            "&type=IMAGE&media=true&thumbnail=true&rows=20&profile=rich"
        )
        resp = requests.get(search_url, headers=headers, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("items") or []
        if not items:
            raise RuntimeError("Europeana: no results")

        candidates = []
        for it in items:
            # Strict relevance: title + dcSubject + dcDescription must contain
            # a distinctive anchor token. Each field can be a list of strings
            # (Europeana returns localised variants), so flatten to a blob.
            def _flat(field) -> str:
                v = it.get(field)
                if not v:
                    return ""
                if isinstance(v, list):
                    return " ".join(str(x) for x in v)
                return str(v)

            blob = " ".join(_flat(f) for f in (
                "title", "dcTitle", "dcSubject", "dcDescription",
                "dcCreator", "edmConceptPrefLabel", "dataProvider",
            ))
            if not self._is_relevant(query, blob):
                continue

            # Prefer the full-resolution media; fall back to the preview.
            img_url = ""
            for k in ("edmIsShownBy", "edmIsShownAt", "edmPreview"):
                v = it.get(k)
                if isinstance(v, list) and v:
                    img_url = str(v[0])
                    break
                if isinstance(v, str) and v:
                    img_url = v
                    break
            if not img_url or img_url in self._used_stock_urls:
                continue
            candidates.append(img_url)

        if not candidates:
            raise RuntimeError("Europeana: no relevant images")

        random.shuffle(candidates)
        for img_url in candidates[:6]:
            try:
                img_resp = requests.get(img_url, headers=headers, timeout=60, allow_redirects=True)
                # Europeana sometimes proxies through HTML pages; require a
                # real image content-type AND a reasonable size.
                ctype = img_resp.headers.get("Content-Type", "").lower()
                if (
                    img_resp.status_code == 200
                    and len(img_resp.content) > 10000
                    and ("image/" in ctype or img_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
                ):
                    self._used_stock_urls.add(img_url)
                    print(colored("OK", "green"))
                    return img_resp.content
            except Exception:
                continue
        raise RuntimeError("Europeana: failed to download any candidate")

    def _try_picsum_stock(self, prompt: str) -> bytes:
        """Fallback: HD stock photo from Picsum (fast, always works)."""
        print(colored(f"    [Picsum HD] Getting image...", "yellow"), flush=True)
        seed = abs(hash(prompt)) % 1000
        url = f"https://picsum.photos/seed/{seed}/1080/1920"
        resp = requests.get(url, timeout=60, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(colored("OK", "green"))
            return resp.content
        raise RuntimeError(f"Picsum returned status {resp.status_code}")

    def _generate_fallback_image(self, prompt: str) -> str:
        """
        Generates a stylish fallback image using Pillow when all API providers fail.
        """
        from PIL import Image, ImageDraw, ImageFont
        import random as rand_mod

        if get_verbose():
            warning("All providers failed. Creating styled fallback image...")

        # Create gradient background
        color_schemes = [
            ((15, 15, 80), (80, 20, 120)),
            ((10, 50, 80), (20, 100, 100)),
            ((60, 10, 60), (120, 30, 80)),
            ((10, 40, 20), (30, 100, 60)),
        ]
        c1, c2 = rand_mod.choice(color_schemes)
        img = Image.new("RGB", (1080, 1920))
        draw = ImageDraw.Draw(img)

        for y in range(1920):
            r = int(c1[0] + (c2[0] - c1[0]) * y / 1920)
            g = int(c1[1] + (c2[1] - c1[1]) * y / 1920)
            b = int(c1[2] + (c2[2] - c1[2]) * y / 1920)
            draw.line([(0, y), (1080, y)], fill=(r, g, b))

        # Add text
        try:
            font_path = os.path.join(get_fonts_dir(), get_font())
            font = ImageFont.truetype(font_path, 52)
        except Exception:
            font = ImageFont.load_default()

        words = prompt.split()
        lines, current_line = [], ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if len(test) > 25:
                lines.append(current_line)
                current_line = word
            else:
                current_line = test
        if current_line:
            lines.append(current_line)

        y_pos = 1920 // 2 - (len(lines) * 70) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            # Shadow
            draw.text(((1080 - w) // 2 + 3, y_pos + 3), line, fill=(0, 0, 0), font=font)
            # Text
            draw.text(((1080 - w) // 2, y_pos), line, fill="white", font=font)
            y_pos += 70

        image_path = os.path.join(get_temp_cache_path(), str(uuid4()) + ".png")
        img.save(image_path)
        self.images.append(image_path)

        if get_verbose():
            info(f' => Wrote fallback image to "{image_path}"')

        return image_path

    def generate_images_batch(self, prompts: List[str], image_mode: str = "ai") -> None:
        """
        Generate ALL images using multiple providers in cascade.

        Args:
            prompts: List of image prompts / search queries.
            image_mode: "ai" â†’ AI generators first, stock photos as fallback (default).
                        "photos" â†’ Wikimedia / stock photos first, AI as last-resort fallback.
        """
        self._image_mode = image_mode
        selected_ai_providers = self._ai_image_providers(1080, 1920)

        if image_mode == "photos":
            print(colored(f"\n  [Images] Fetching {len(prompts)} real photos...", "blue"))
            providers = [
                # Tier 1: deterministic entity-based lookup. Wikidata maps the
                # query to a concrete entity (Q-id) and returns the curated
                # lead image (P18) plus a sample of files from its Commons
                # category (P373). Far more precise than fuzzy article search,
                # so it goes first.
                ("Wikidata", self._try_wikidata, "stock"),
                # Tier 2: fuzzy Wikipedia article search (handles redirects,
                # spelling variants) â†’ curated infobox image.
                ("Wikipedia article", self._try_wikipedia_article, "stock"),
                # Tier 3: free-text search across other curated heritage
                # archives. Europeana aggregates European museums/libraries,
                # Wikimedia Commons covers everything else, Met Museum and
                # Library of Congress cover art and historical photos.
                ("Europeana", self._try_europeana, "stock"),
                ("Wikimedia Commons", self._try_wikimedia, "stock"),
                ("Met Museum", self._try_met_museum, "stock"),
                ("Library of Congress", self._try_loc, "stock"),
                # Tier 4: modern stock (filtered by relevance) â€” useful for
                # non-historical topics where heritage archives are sparse.
                ("Pexels", self._try_pexels, "stock"),
                ("Pixabay", self._try_pixabay, "stock"),
                # Tier 5: AI fallback when no real photo matches the topic.
            ] + selected_ai_providers
        else:
            provider_label = self._ai_image_provider_choice()
            label_suffix = "" if provider_label == "auto" else f" via {provider_label}"
            print(colored(f"\n  [Images] Generating {len(prompts)} images{label_suffix}...", "blue"))
            providers = selected_ai_providers
            if provider_label == "auto":
                providers += [
                    # Stock photos remain as a reliability fallback in auto mode.
                    ("Pexels", self._try_pexels, "stock"),
                    ("Pixabay", self._try_pixabay, "stock"),
                ]

        for i, prompt in enumerate(prompts):
            print(colored(f"\n  Image {i+1}/{len(prompts)}", "blue"))
            saved = False
            for name, fn, kind in providers:
                try:
                    # In photos mode the LLM produces short search queries â€” AI providers need cinematic context to render well.
                    effective_prompt = prompt
                    if image_mode == "photos" and kind == "ai":
                        effective_prompt = self._augment_for_ai_fallback(prompt)
                    elif kind == "ai":
                        # AI mode: append per-channel image style suffix (if any).
                        effective_prompt = self._apply_channel_style(prompt)
                    img_bytes = fn(effective_prompt)
                    if img_bytes and len(img_bytes) > 1000:
                        self._persist_image(img_bytes, name)
                        saved = True
                        break
                except Exception as e:
                    if get_verbose():
                        warning(f"    {name} failed: {str(e)[:100]}")
                    time.sleep(1)
            if not saved:
                self._generate_fallback_image(prompt)

        success(f"All {len(prompts)} images ready!")

    def generate_image(self, prompt: str) -> str:
        """
        Generates an AI Image trying multiple FREE providers in cascade:
        1. HuggingFace (new router URL, needs free token)
        2. Picsum (HD stock photos, fast)
        3. Pillow gradient fallback

        Args:
            prompt (str): Reference for image generation

        Returns:
            path (str): The path to the generated image.
        """
        providers = [
            (name, fn)
            for name, fn, _kind in self._ai_image_providers(1080, 1920)
        ]

        print(colored(f"  [Image] {prompt[:80]}...", "blue"))

        for name, provider_fn in providers:
            try:
                img_bytes = provider_fn(prompt)
                if img_bytes and len(img_bytes) > 1000:
                    success(f"Image generated via {name}!")
                    return self._persist_image(img_bytes, name)
            except Exception as e:
                if get_verbose():
                    warning(f"{name} failed: {str(e)[:100]}")
                time.sleep(1)

        # All providers failed - use Pillow fallback
        return self._generate_fallback_image(prompt)

    def generate_script_to_speech(self, tts_instance: TTS) -> str:
        """
        Converts the generated script into Speech and returns the path to the wav file.
        Also captures word-level timestamps for karaoke subtitles when available.

        Args:
            tts_instance (tts): Instance of TTS Class.

        Returns:
            path_to_wav (str): Path to generated audio (WAV Format).
        """
        path = os.path.join(get_temp_cache_path(), str(uuid4()) + ".wav")

        # Sanitize while keeping punctuation (commas, colons, em-dashes, Â¿Â¡)
        # so Edge-TTS pauses naturally. The script we display keeps Roman
        # numerals intact ("Cosimo I"); only the text fed to TTS expands them
        # ("Cosimo primero") so pronunciation is correct.
        # Strip leaked stage directions ("(imagen de ...)") before any other
        # cleaning so TTS never reads them out loud.
        self.script = strip_stage_directions(self.script)
        self.script = strip_narration_structure_labels(self.script)
        self.script = clean_script_for_tts(self.script)
        tts_text, regnal_subs = expand_regnal_numerals_tracked(self.script)
        # Expand digit numbers to Spanish words. Applied to tts_text only so
        # the original self.script (used for subtitle alignment) keeps its
        # short tokens, while what the TTS reads has natural Spanish numbers.
        tts_text = expand_spanish_numbers(tts_text)

        # Per-channel short voice override (falls back to TTS instance default if empty).
        short_vid = self._resolve_voice(self._short_voice)
        # Optional dramatic modulation for narrator-style channels. MAXIMA
        # RETENCION keeps the voice moving faster and lowers the pitch only
        # slightly when drama is enabled.
        if is_max_retention(getattr(self, "_retention_mode", "")):
            rate = MaxRetentionEngine.VOICE_RATE
            pitch = MaxRetentionEngine.VOICE_DRAMA_PITCH if self._voice_drama else ""
        else:
            rate = "-5%" if self._voice_drama else ""
            pitch = "-8Hz" if self._voice_drama else ""
        path, word_timestamps = tts_instance.synthesize_with_timestamps(
            tts_text, path, voice_id=short_vid or None, rate=rate, pitch=pitch,
        )

        # Put the Roman numerals back in the word-level timestamps so the
        # karaoke subtitles read "I" / "XIV" while the audio says "primero" /
        # "catorce".
        if word_timestamps:
            word_timestamps = restore_regnal_numerals_in_timestamps(
                word_timestamps, regnal_subs
            )
        self.word_timestamps = word_timestamps

        self.tts_path = path

        if get_verbose():
            ts_info = f" ({len(word_timestamps)} words timed)" if word_timestamps else ""
            info(f' => Wrote TTS to "{path}"{ts_info}')

        return path

    def add_video(self, video: dict) -> None:
        """
        Adds a video to the cache.

        Args:
            video (dict): The video to add

        Returns:
            None
        """
        videos = self.get_videos()
        videos.append(video)

        cache = get_youtube_cache_path()

        with json_write_lock(cache):
            with open(cache, "r", encoding="utf-8") as file:
                previous_json = json.loads(file.read())
            for account in previous_json["accounts"]:
                if account["id"] == self._account_uuid:
                    account["videos"].append(video)
            with open(cache, "w", encoding="utf-8") as f:
                f.write(json.dumps(previous_json))

    def generate_subtitles(self, audio_path: str) -> str:
        """
        Generates subtitles from the known script text.
        Uses script-based generation by default (instant, no STT needed since we
        already have the exact text). Falls back to STT only if explicitly configured.

        Args:
            audio_path (str): The path to the audio file.

        Returns:
            path (str): The path to the generated SRT File.
        """
        provider = str(get_stt_provider() or "script").lower()

        # Default: use the script we already have (instant, no extra dependencies)
        if provider not in ("local_whisper", "third_party_assemblyai"):
            return self.generate_subtitles_from_script(audio_path)

        try:
            if provider == "local_whisper":
                return self.generate_subtitles_local_whisper(audio_path)

            if provider == "third_party_assemblyai":
                return self.generate_subtitles_assemblyai(audio_path)
        except Exception as e:
            warning(f"STT subtitles failed ({e}), using script-based subtitles instead.")

        return self.generate_subtitles_from_script(audio_path)

    def generate_subtitles_from_script(self, audio_path: str) -> str:
        """
        Generates subtitles by splitting the script text into sentences
        and distributing them evenly across the audio duration.
        No STT engine required.

        Args:
            audio_path (str): Audio file path (used to get duration)

        Returns:
            path (str): Path to SRT file
        """
        from moviepy.editor import AudioFileClip as _AFC

        duration = _AFC(audio_path).duration
        sentences = re.split(r'(?<=[.!?])\s+', self.script.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            sentences = [self.script.strip()]

        seg_dur = duration / len(sentences)
        lines = []

        for idx, sentence in enumerate(sentences):
            start = self._format_srt_timestamp(idx * seg_dur)
            end = self._format_srt_timestamp(min((idx + 1) * seg_dur, duration))
            lines.append(str(idx + 1))
            lines.append(f"{start} --> {end}")
            lines.append(sentence)
            lines.append("")

        srt_path = os.path.join(get_temp_cache_path(), str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))

        if get_verbose():
            info(f" => Generated script-based subtitles ({len(sentences)} segments)")

        return srt_path

    def generate_subtitles_assemblyai(self, audio_path: str) -> str:
        """
        Generates subtitles using AssemblyAI.

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        aai.settings.api_key = get_assemblyai_api_key()
        config = aai.TranscriptionConfig()
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_path)
        subtitles = transcript.export_subtitles_srt()

        srt_path = os.path.join(get_temp_cache_path(), str(uuid4()) + ".srt")

        with open(srt_path, "w", encoding="utf-8") as file:
            file.write(subtitles)

        return srt_path

    def _format_srt_timestamp(self, seconds: float) -> str:
        """
        Formats a timestamp in seconds to SRT format.

        Args:
            seconds (float): Seconds

        Returns:
            ts (str): HH:MM:SS,mmm
        """
        total_millis = max(0, int(round(seconds * 1000)))
        hours = total_millis // 3600000
        minutes = (total_millis % 3600000) // 60000
        secs = (total_millis % 60000) // 1000
        millis = total_millis % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def generate_subtitles_local_whisper(self, audio_path: str) -> str:
        """
        Generates subtitles using local Whisper (faster-whisper).

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            error(
                "Local STT selected but 'faster-whisper' is not installed. "
                "Install it or switch stt_provider to third_party_assemblyai."
            )
            raise

        whisper_model_name = get_whisper_model()
        print(colored(f"  [Whisper] Loading model '{whisper_model_name}'...", "cyan"), flush=True)
        model = WhisperModel(
            whisper_model_name,
            device=get_whisper_device(),
            compute_type=get_whisper_compute_type(),
        )
        print(colored(f"  [Whisper] Transcribing audio...", "cyan"), flush=True)
        segments, _ = model.transcribe(audio_path, vad_filter=True)

        lines = []
        for idx, segment in enumerate(segments, start=1):
            start = self._format_srt_timestamp(segment.start)
            end = self._format_srt_timestamp(segment.end)
            text = str(segment.text).strip()

            if not text:
                continue

            lines.append(str(idx))
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        subtitles = "\n".join(lines)
        srt_path = os.path.join(get_temp_cache_path(), str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write(subtitles)

        return srt_path

    def _build_karaoke_subtitles(self, audio_duration: float, fps: int = 30):
        """
        Build word-by-word karaoke subtitle clip from word_timestamps.
        Shows groups of up to 5 words with multi-line wrapping; the active
        word is highlighted in yellow â€” modern YouTube Shorts style.
        """
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        words = self.word_timestamps
        if not words:
            return None

        max_mode = is_max_retention(getattr(self, "_retention_mode", ""))
        caption_cfg = MaxRetentionEngine.caption_config() if max_mode else None
        font_path = os.path.join(get_fonts_dir(), "Poppins-Black.ttf").replace("\\", "/")
        font_size = caption_cfg.font_size if caption_cfg else 80
        font = ImageFont.truetype(font_path, font_size)
        canvas_w = 1080
        max_line_width = 920
        word_spacing = 28
        line_spacing = 0  # ascent+descent already provides natural spacing
        max_words_per_group = caption_cfg.max_words_per_group if caption_cfg else 5
        max_lines = 2 if max_mode else 3
        hot_word_set = set()
        if max_mode:
            try:
                hot_word_set = set(RetentionLab.hot_words(getattr(self, "script", "") or "", getattr(self, "subject", "") or ""))
            except Exception:
                hot_word_set = set()

        def _caption_key(text: str) -> str:
            return RetentionLab.normalize(text)

        # Measure height of a single line using full font metrics (ascent + descent)
        # plus stroke so descenders (g, y, p) and strokes never get clipped
        ascent, descent = font.getmetrics()
        line_h = ascent + descent

        # --- Helper: wrap a list of texts into lines that fit max_line_width ---
        def _wrap_group(texts):
            """Returns list of lines, each line is a list of (text, width) tuples."""
            lines = []
            current_line = []
            current_w = 0
            for t in texts:
                bb = font.getbbox(t)
                tw = bb[2] - bb[0]
                test_w = current_w + tw + (word_spacing if current_line else 0)
                if current_line and test_w > max_line_width:
                    lines.append(current_line)
                    current_line = [(t, tw)]
                    current_w = tw
                else:
                    current_line.append((t, tw))
                    current_w = test_w
            if current_line:
                lines.append(current_line)
            return lines

        # --- Group words (up to 5, but never exceeding max_lines when wrapped) ---
        groups = []
        current_group = []

        for w in words:
            candidate = current_group + [w]
            candidate_texts = [gw["word"].upper() for gw in candidate]
            lines_needed = len(_wrap_group(candidate_texts))
            if len(candidate) > max_words_per_group or lines_needed > max_lines:
                if current_group:
                    groups.append(current_group)
                current_group = [w]
            else:
                current_group = candidate
        if current_group:
            groups.append(current_group)

        # --- Build index: global word index â†’ (group_idx, local_idx) ---
        word_to_group = {}
        gi = 0
        for g_idx, group in enumerate(groups):
            for l_idx in range(len(group)):
                word_to_group[gi] = (g_idx, l_idx)
                gi += 1

        # --- Pre-render one frame per word (group with that word highlighted) ---
        # First pass: determine max canvas height across all groups
        max_num_lines = 1
        for group in groups:
            texts = [gw["word"].upper() for gw in group]
            lines = _wrap_group(texts)
            max_num_lines = max(max_num_lines, len(lines))

        stroke_pad = 6 * 2  # stroke_width extends outward on all sides
        canvas_h = max_num_lines * line_h + (max_num_lines - 1) * line_spacing + stroke_pad + 20

        rendered = {}  # global_word_idx â†’ (rgb np.array, alpha np.array)

        for word_idx, (g_idx, l_idx) in word_to_group.items():
            group = groups[g_idx]
            texts = [gw["word"].upper() for gw in group]
            lines = _wrap_group(texts)

            img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Track which global-in-group index we're drawing
            word_counter = 0
            y = 20
            for line in lines:
                line_total_w = sum(tw for _, tw in line) + word_spacing * (len(line) - 1)
                x = (canvas_w - line_total_w) // 2
                for t, tw in line:
                    if word_counter == l_idx:
                        draw.text((x, y), t, fill=(255, 215, 0), font=font,
                                  stroke_width=6, stroke_fill="black")
                    else:
                        fill = (255, 95, 70) if _caption_key(t) in hot_word_set else "white"
                        draw.text((x, y), t, fill=fill, font=font,
                                  stroke_width=6, stroke_fill="black")
                    x += tw + word_spacing
                    word_counter += 1
                y += line_h + line_spacing

            arr = np.array(img)
            rendered[word_idx] = (arr[:, :, :3], arr[:, :, 3].astype(np.float64) / 255.0)

        # Blank frame for silence gaps
        blank_rgb = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
        blank_alpha = np.zeros((canvas_h, canvas_w), dtype=np.float64)

        # --- Lookup: find active word at time t ---
        def find_active(t):
            for i, w in enumerate(words):
                if w["start"] <= t <= w["end"]:
                    return i
            # Between words: keep showing the last spoken word
            for i in range(len(words) - 1):
                if words[i]["end"] < t < words[i + 1]["start"]:
                    return i
            if words and t >= words[-1]["start"]:
                return len(words) - 1
            return -1

        def make_rgb(t):
            idx = find_active(t)
            if idx < 0 or idx not in rendered:
                return blank_rgb
            return rendered[idx][0]

        def make_mask(t):
            idx = find_active(t)
            if idx < 0 or idx not in rendered:
                return blank_alpha
            return rendered[idx][1]

        clip = VideoClip(make_rgb, duration=audio_duration).set_fps(fps)
        mask = VideoClip(make_mask, duration=audio_duration, ismask=True).set_fps(fps)
        clip = clip.set_mask(mask)
        clip = clip.set_position(("center", caption_cfg.position_y if caption_cfg else 1300))
        return clip

    def _build_karaoke_subtitles_landscape(self, audio_duration: float, fps: int = 24):
        """
        Build karaoke subtitles for 16:9 long videos.

        Unlike the Shorts subtitle builder, this renders words lazily with a
        small cache. A long narration can have thousands of words, so pre-
        rendering every possible highlighted word would use too much memory.
        """
        from bisect import bisect_right
        from functools import lru_cache
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        words = self.word_timestamps
        if not words:
            return None

        font_path = os.path.join(get_fonts_dir(), "Poppins-Black.ttf").replace("\\", "/")
        font_size = 58
        font = ImageFont.truetype(font_path, font_size)
        canvas_w = 1920
        max_line_width = 1500
        word_spacing = 24
        max_words_per_group = 7
        max_lines = 2
        stroke_width = 5

        ascent, descent = font.getmetrics()
        line_h = ascent + descent
        canvas_h = max_lines * line_h + (stroke_width * 2) + 28

        def _word_text(item):
            return str(item.get("word", "")).strip().upper()

        def _measure(text: str) -> int:
            bb = font.getbbox(text)
            return bb[2] - bb[0]

        def _wrap_texts(texts):
            lines = []
            current = []
            current_w = 0
            for text in texts:
                width = _measure(text)
                test_w = current_w + width + (word_spacing if current else 0)
                if current and test_w > max_line_width:
                    lines.append(current)
                    current = [(text, width)]
                    current_w = width
                else:
                    current.append((text, width))
                    current_w = test_w
            if current:
                lines.append(current)
            return lines

        groups = []
        current_group = []
        for word in words:
            candidate = current_group + [word]
            candidate_texts = [_word_text(w) for w in candidate]
            if len(candidate) > max_words_per_group or len(_wrap_texts(candidate_texts)) > max_lines:
                if current_group:
                    groups.append(current_group)
                current_group = [word]
            else:
                current_group = candidate
        if current_group:
            groups.append(current_group)

        word_to_group = {}
        global_idx = 0
        for group_idx, group in enumerate(groups):
            for local_idx in range(len(group)):
                word_to_group[global_idx] = (group_idx, local_idx)
                global_idx += 1

        starts = [float(w.get("start", 0.0)) for w in words]
        ends = [float(w.get("end", 0.0)) for w in words]
        blank_rgb = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
        blank_alpha = np.zeros((canvas_h, canvas_w), dtype=np.float64)

        @lru_cache(maxsize=96)
        def _render(word_idx: int):
            if word_idx not in word_to_group:
                return blank_rgb, blank_alpha
            group_idx, local_idx = word_to_group[word_idx]
            group = groups[group_idx]
            texts = [_word_text(w) for w in group]
            lines = _wrap_texts(texts)

            img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            counter = 0
            y = 14
            for line in lines[:max_lines]:
                line_total_w = sum(width for _, width in line) + word_spacing * (len(line) - 1)
                x = (canvas_w - line_total_w) // 2
                for text, width in line:
                    fill = (255, 215, 0) if counter == local_idx else "white"
                    draw.text(
                        (x, y),
                        text,
                        fill=fill,
                        font=font,
                        stroke_width=stroke_width,
                        stroke_fill="black",
                    )
                    x += width + word_spacing
                    counter += 1
                y += line_h

            arr = np.array(img)
            return arr[:, :, :3], arr[:, :, 3].astype(np.float64) / 255.0

        def _active_word_index(t: float) -> int:
            idx = bisect_right(starts, t) - 1
            if idx < 0:
                return -1
            if idx >= len(words):
                idx = len(words) - 1
            # Keep the previous word visible in tiny timing gaps, but hide it
            # during the music-only tail after the last narrated word.
            if idx == len(words) - 1 and t > ends[idx] + 0.8:
                return -1
            return idx

        def make_rgb(t):
            idx = _active_word_index(t)
            return blank_rgb if idx < 0 else _render(idx)[0]

        def make_mask(t):
            idx = _active_word_index(t)
            return blank_alpha if idx < 0 else _render(idx)[1]

        clip = VideoClip(make_rgb, duration=audio_duration).set_fps(fps)
        mask = VideoClip(make_mask, duration=audio_duration, ismask=True).set_fps(fps)
        clip = clip.set_mask(mask)
        clip = clip.set_position(("center", 820))
        return clip

    def _estimate_word_timestamps(self, audio_duration: float):
        """Estimate word timestamps from script when TTS didn't provide them."""
        words = self.script.split()
        if not words:
            return []
        dur_per_word = audio_duration / len(words)
        return [
            {"start": i * dur_per_word, "end": (i + 1) * dur_per_word, "word": w}
            for i, w in enumerate(words)
        ]

    def _append_music_attribution(self, line: str) -> None:
        """
        Append a music attribution line to the video description, idempotent.
        Called from combine()/combine_long() when a track requiring credit is
        picked. Safe to call multiple times â€” duplicates are skipped.
        """
        meta = getattr(self, "metadata", None)
        if not isinstance(meta, dict):
            return
        desc = meta.get("description", "") or ""
        if line in desc:
            return
        meta["description"] = (desc.rstrip() + "\n\n" + line).lstrip()

    @staticmethod
    def _short_clip_durations(num_clips: int, max_duration: float, crossfade: float) -> list[float]:
        total_overlap = crossfade * max(0, num_clips - 1)
        target_total = max_duration + total_overlap
        req_dur = target_total / num_clips
        durations = []
        elapsed = 0.0

        for idx in range(num_clips):
            this_dur = target_total - elapsed if idx == num_clips - 1 else req_dur
            if this_dur <= 0:
                break
            durations.append(this_dur)
            elapsed += this_dur

        return durations

    @staticmethod
    def _long_clip_durations(
        num_clips: int,
        max_duration: float,
        crossfade: float,
        extra_tail: float,
    ) -> list[float]:
        total_overlap = crossfade * max(0, num_clips - 1)
        target_total = max_duration + total_overlap + extra_tail
        req_dur = target_total / num_clips
        durations = []
        elapsed = 0.0

        for idx in range(num_clips):
            this_dur = target_total - elapsed if idx == num_clips - 1 else req_dur
            if this_dur <= 0:
                break
            durations.append(this_dur)
            elapsed += this_dur

        return durations

    @staticmethod
    def _ass_timestamp(seconds: float) -> str:
        centiseconds = max(0, int(round(float(seconds) * 100)))
        hours, rem = divmod(centiseconds, 360000)
        minutes, rem = divmod(rem, 6000)
        secs, cs = divmod(rem, 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"

    @staticmethod
    def _escape_ass_text(text: str) -> str:
        return (
            str(text or "")
            .replace("\\", "\\\\")
            .replace("{", r"\{")
            .replace("}", r"\}")
            .replace("\n", " ")
            .strip()
        )

    @staticmethod
    def _ffmpeg_filter_escape_path(path: str) -> str:
        normalized = os.path.abspath(path).replace("\\", "/")
        return normalized.replace(":", r"\:").replace("'", r"\'")

    def _write_karaoke_ass_subtitles(self, output_path: str, audio_duration: float) -> bool:
        from PIL import ImageFont

        words = self.word_timestamps or []
        if not words:
            return False

        max_mode = is_max_retention(getattr(self, "_retention_mode", ""))
        caption_cfg = MaxRetentionEngine.caption_config() if max_mode else None
        font_path = os.path.join(get_fonts_dir(), "Poppins-Black.ttf").replace("\\", "/")
        font_size = caption_cfg.font_size if caption_cfg else 80
        font = ImageFont.truetype(font_path, font_size)
        max_line_width = 920
        word_spacing = 28
        max_words_per_group = caption_cfg.max_words_per_group if caption_cfg else 5
        max_lines = 2 if max_mode else 3
        position_y = caption_cfg.position_y if caption_cfg else 1300

        hot_word_set = set()
        if max_mode:
            try:
                hot_word_set = set(
                    RetentionLab.hot_words(
                        getattr(self, "script", "") or "",
                        getattr(self, "subject", "") or "",
                    )
                )
            except Exception:
                hot_word_set = set()

        def _caption_key(text: str) -> str:
            return RetentionLab.normalize(text)

        def _measure(text: str) -> int:
            bb = font.getbbox(text)
            return bb[2] - bb[0]

        def _word_text(item: dict) -> str:
            return str(item.get("word", "")).strip().upper()

        def _wrap_texts(texts: list[str]) -> list[list[str]]:
            lines = []
            current = []
            current_w = 0
            for text in texts:
                width = _measure(text)
                test_w = current_w + width + (word_spacing if current else 0)
                if current and test_w > max_line_width:
                    lines.append(current)
                    current = [text]
                    current_w = width
                else:
                    current.append(text)
                    current_w = test_w
            if current:
                lines.append(current)
            return lines

        groups = []
        current_group = []
        for word in words:
            candidate = current_group + [word]
            candidate_texts = [_word_text(w) for w in candidate]
            if len(candidate) > max_words_per_group or len(_wrap_texts(candidate_texts)) > max_lines:
                if current_group:
                    groups.append(current_group)
                current_group = [word]
            else:
                current_group = candidate
        if current_group:
            groups.append(current_group)

        word_to_group = {}
        global_idx = 0
        for group_idx, group in enumerate(groups):
            for local_idx in range(len(group)):
                word_to_group[global_idx] = (group_idx, local_idx)
                global_idx += 1

        white = "&H00FFFFFF&"
        yellow = "&H0000D7FF&"
        hot_red = "&H00465FFF&"
        outline = "&H00000000&"

        def _colored_word(text: str, color: str) -> str:
            return f"{{\\c{color}}}{self._escape_ass_text(text)}"

        lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Karaoke,Poppins Black,{font_size},{white},{white},{outline},"
            f"&H00000000&,-1,0,0,0,100,100,0,0,1,6,0,8,0,0,0,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        for word_idx, word in enumerate(words):
            if word_idx not in word_to_group:
                continue
            start = max(0.0, float(word.get("start", 0.0)))
            if start >= audio_duration:
                continue
            if word_idx < len(words) - 1:
                end = float(words[word_idx + 1].get("start", start))
            else:
                end = audio_duration
            end = min(audio_duration, max(end, float(word.get("end", start + 0.05)), start + 0.05))

            group_idx, local_idx = word_to_group[word_idx]
            group = groups[group_idx]
            texts = [_word_text(w) for w in group]
            wrapped = _wrap_texts(texts)
            local_counter = 0
            rendered_lines = []
            for wrapped_line in wrapped:
                rendered_words = []
                for text in wrapped_line:
                    if local_counter == local_idx:
                        color = yellow
                    elif _caption_key(text) in hot_word_set:
                        color = hot_red
                    else:
                        color = white
                    rendered_words.append(_colored_word(text, color))
                    local_counter += 1
                rendered_lines.append(" ".join(rendered_words))

            ass_text = r"\N".join(rendered_lines)
            prefix = f"{{\\an8\\pos(540,{position_y})}}"
            lines.append(
                "Dialogue: 0,"
                f"{self._ass_timestamp(start)},{self._ass_timestamp(end)},"
                f"Karaoke,,0,0,0,,{prefix}{ass_text}"
            )

        with open(output_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
        return True

    def _write_karaoke_ass_subtitles_landscape(self, output_path: str, audio_duration: float) -> bool:
        from PIL import ImageFont

        words = self.word_timestamps or []
        if not words:
            return False

        font_path = os.path.join(get_fonts_dir(), "Poppins-Black.ttf").replace("\\", "/")
        font_size = 58
        font = ImageFont.truetype(font_path, font_size)
        max_line_width = 1500
        word_spacing = 24
        max_words_per_group = 7
        max_lines = 2

        def _measure(text: str) -> int:
            bb = font.getbbox(text)
            return bb[2] - bb[0]

        def _word_text(item: dict) -> str:
            return str(item.get("word", "")).strip().upper()

        def _wrap_texts(texts: list[str]) -> list[list[str]]:
            lines = []
            current = []
            current_w = 0
            for text in texts:
                width = _measure(text)
                test_w = current_w + width + (word_spacing if current else 0)
                if current and test_w > max_line_width:
                    lines.append(current)
                    current = [text]
                    current_w = width
                else:
                    current.append(text)
                    current_w = test_w
            if current:
                lines.append(current)
            return lines

        groups = []
        current_group = []
        for word in words:
            candidate = current_group + [word]
            candidate_texts = [_word_text(w) for w in candidate]
            if len(candidate) > max_words_per_group or len(_wrap_texts(candidate_texts)) > max_lines:
                if current_group:
                    groups.append(current_group)
                current_group = [word]
            else:
                current_group = candidate
        if current_group:
            groups.append(current_group)

        word_to_group = {}
        global_idx = 0
        for group_idx, group in enumerate(groups):
            for local_idx in range(len(group)):
                word_to_group[global_idx] = (group_idx, local_idx)
                global_idx += 1

        white = "&H00FFFFFF&"
        yellow = "&H0000D7FF&"
        outline = "&H00000000&"

        def _colored_word(text: str, color: str) -> str:
            return f"{{\\c{color}}}{self._escape_ass_text(text)}"

        lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Karaoke,Poppins Black,{font_size},{white},{white},{outline},"
            f"&H00000000&,-1,0,0,0,100,100,0,0,1,5,0,8,0,0,0,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        for word_idx, word in enumerate(words):
            if word_idx not in word_to_group:
                continue
            start = max(0.0, float(word.get("start", 0.0)))
            if start >= audio_duration:
                continue
            if word_idx < len(words) - 1:
                end = float(words[word_idx + 1].get("start", start))
            else:
                end = float(word.get("end", start + 0.05)) + 0.8
            end = min(
                audio_duration,
                max(end, float(word.get("end", start + 0.05)), start + 0.05),
            )

            group_idx, local_idx = word_to_group[word_idx]
            group = groups[group_idx]
            texts = [_word_text(w) for w in group]
            wrapped = _wrap_texts(texts)
            local_counter = 0
            rendered_lines = []
            for wrapped_line in wrapped:
                rendered_words = []
                for text in wrapped_line:
                    color = yellow if local_counter == local_idx else white
                    rendered_words.append(_colored_word(text, color))
                    local_counter += 1
                rendered_lines.append(" ".join(rendered_words))

            ass_text = r"\N".join(rendered_lines)
            prefix = r"{\an8\pos(960,820)}"
            lines.append(
                "Dialogue: 0,"
                f"{self._ass_timestamp(start)},{self._ass_timestamp(end)},"
                f"Karaoke,,0,0,0,,{prefix}{ass_text}"
            )

        with open(output_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
        return True

    @staticmethod
    def _available_ffmpeg_encoders() -> set[str]:
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except Exception:
            return set()
        output = f"{result.stdout}\n{result.stderr}"
        return {
            codec
            for codec in ("h264_nvenc", "h264_qsv", "h264_amf", "libx264")
            if codec in output
        }

    def _render_codec_candidates(self) -> list[str]:
        configured = get_render_codec().strip()
        if configured.lower() != "auto":
            return [configured or "libx264"]

        available = self._available_ffmpeg_encoders()
        candidates = [
            codec
            for codec in ("h264_nvenc", "h264_qsv", "h264_amf")
            if codec in available
        ]
        candidates.append("libx264")
        return candidates

    @staticmethod
    def _mp4_compat_ffmpeg_params() -> list[str]:
        """Keep rendered MP4s playable in Windows Media Player and browser previews."""
        return [
            "-pix_fmt", "yuv420p",
            "-color_range", "tv",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-movflags", "+faststart",
        ]

    @staticmethod
    def _ffmpeg_failure_tail(result: subprocess.CompletedProcess, max_lines: int = 16) -> str:
        """Return the useful tail of an FFmpeg failure without flooding the UI."""
        output = "\n".join(part for part in (result.stderr, result.stdout) if part)
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            return "no FFmpeg output"
        return "\n".join(lines[-max_lines:])

    def _write_videofile_with_fallback(self, clip, output_path: str, *, threads: int, fps: int) -> None:
        candidates = self._render_codec_candidates()
        configured_preset = get_render_preset()
        bitrate = get_render_bitrate()
        last_error = None

        for idx, codec in enumerate(candidates):
            preset = configured_preset
            if not preset and codec == "libx264":
                preset = "ultrafast"

            kwargs = {
                "threads": threads,
                "fps": fps,
                "codec": codec,
                "audio_codec": "aac",
                "audio": True,
                "logger": "bar",
                "ffmpeg_params": self._mp4_compat_ffmpeg_params(),
            }
            if preset:
                kwargs["preset"] = preset
            if bitrate:
                kwargs["bitrate"] = bitrate

            if get_verbose():
                info(
                    " => Render settings: "
                    f"fps={fps}, codec={codec}, preset={preset or '(default)'}, "
                    f"threads={threads}"
                )

            try:
                clip.write_videofile(output_path, **kwargs)
                return
            except Exception as exc:
                last_error = exc
                if idx >= len(candidates) - 1:
                    break
                warning(
                    f"Render failed with codec {codec}; "
                    f"trying {candidates[idx + 1]} instead."
                )

        raise last_error

    def _short_ffmpeg_filter_complex(
        self,
        *,
        image_count: int,
        durations: list[float],
        fps: int,
        crossfade: float,
        ken_burns_enabled: bool,
        karaoke_ass_path: str,
        music_volume: float,
        audio_duration: float,
    ) -> str:
        filters = []
        pan_scale_w = 1124
        pan_scale_h = 1998
        horizontal_pan = 180
        vertical_pan = 120
        for idx, this_dur in enumerate(durations):
            frames = max(1, int(round(this_dur * fps)))
            frame_denom = max(1, frames - 1)
            repeated = (
                f"loop=loop={max(0, frames - 1)}:size=1:start=0,"
                f"setpts=N/({fps}*TB),"
            )
            base = (
                f"[{idx}:v]"
                "scale=1080:1920:force_original_aspect_ratio=increase:"
                "flags=lanczos+accurate_rnd,"
                "crop=1080:1920,setsar=1,format=rgb24,"
            )
            if ken_burns_enabled:
                pan_base = (
                    f"[{idx}:v]"
                    f"scale={pan_scale_w}:{pan_scale_h}:"
                    "force_original_aspect_ratio=increase:"
                    "flags=lanczos+accurate_rnd,"
                    "setsar=1,format=rgb24,"
                )
                progress = f"n/{frame_denom}"
                if idx % 4 == 0:
                    x_expr = (
                        f"((iw-ow)/2)-(min(iw-ow\\,{horizontal_pan})/2)+"
                        f"min(iw-ow\\,{horizontal_pan})*({progress})"
                    )
                    y_expr = "(ih-oh)/2"
                elif idx % 4 == 1:
                    x_expr = (
                        f"((iw-ow)/2)+(min(iw-ow\\,{horizontal_pan})/2)-"
                        f"min(iw-ow\\,{horizontal_pan})*({progress})"
                    )
                    y_expr = "(ih-oh)/2"
                elif idx % 4 == 2:
                    x_expr = "(iw-ow)/2"
                    y_expr = (
                        f"((ih-oh)/2)-(min(ih-oh\\,{vertical_pan})/2)+"
                        f"min(ih-oh\\,{vertical_pan})*({progress})"
                    )
                else:
                    x_expr = "(iw-ow)/2"
                    y_expr = (
                        f"((ih-oh)/2)+(min(ih-oh\\,{vertical_pan})/2)-"
                        f"min(ih-oh\\,{vertical_pan})*({progress})"
                    )
                filters.append(
                    f"{pan_base}"
                    f"{repeated}"
                    f"crop=1080:1920:x='{x_expr}':y='{y_expr}',"
                    f"trim=duration={this_dur:.6f},"
                    "setpts=PTS-STARTPTS,format=yuv420p"
                    f"[v{idx}]"
                )
            else:
                filters.append(
                    f"{base},"
                    f"{repeated}"
                    f"trim=duration={this_dur:.6f},"
                    "format=yuv420p"
                    f"[v{idx}]"
                )

        effective_crossfade = crossfade
        if image_count <= 1:
            video_label = "[v0]"
        elif effective_crossfade > 0 and all(d > effective_crossfade for d in durations):
            video_label = "[v0]"
            running_duration = durations[0]
            for idx in range(1, image_count):
                out_label = f"[vx{idx}]"
                offset = max(0.0, running_duration - effective_crossfade)
                filters.append(
                    f"{video_label}[v{idx}]"
                    f"xfade=transition=fade:duration={effective_crossfade:.6f}:"
                    f"offset={offset:.6f},format=yuv420p"
                    f"{out_label}"
                )
                video_label = out_label
                running_duration += durations[idx] - effective_crossfade
        else:
            concat_inputs = "".join(f"[v{idx}]" for idx in range(image_count))
            filters.append(f"{concat_inputs}concat=n={image_count}:v=1:a=0,format=yuv420p[vbase]")
            video_label = "[vbase]"

        if karaoke_ass_path:
            ass_path = self._ffmpeg_filter_escape_path(karaoke_ass_path)
            fonts_dir = self._ffmpeg_filter_escape_path(get_fonts_dir())
            filters.append(
                f"{video_label}"
                f"ass=filename='{ass_path}':fontsdir='{fonts_dir}',"
                "scale=1080:1920:flags=lanczos+accurate_rnd:out_range=tv,"
                "format=yuv420p,"
                "setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709"
                "[vout]"
            )
        else:
            filters.append(
                f"{video_label}"
                "scale=1080:1920:flags=lanczos+accurate_rnd:out_range=tv,"
                "format=yuv420p,"
                "setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709"
                "[vout]"
            )

        voice_idx = image_count
        music_idx = image_count + 1
        filters.extend([
            f"[{voice_idx}:a]aresample=44100,atrim=0:{audio_duration:.6f},"
            "asetpts=PTS-STARTPTS[voice]",
            f"[{music_idx}:a]aresample=44100,atrim=0:{audio_duration:.6f},"
            f"asetpts=PTS-STARTPTS,volume={music_volume:.4f}[music]",
            "[voice][music]amix=inputs=2:duration=first:dropout_transition=0,"
            f"atrim=0:{audio_duration:.6f},asetpts=PTS-STARTPTS[aout]",
        ])
        return ";".join(filters)

    def _write_quality_short_with_ffmpeg(
        self,
        *,
        output_path: str,
        image_paths: list[str],
        durations: list[float],
        random_song: str,
        fps: int,
        crossfade: float,
        ken_burns_enabled: bool,
        karaoke_enabled: bool,
        music_volume: float,
        audio_duration: float,
        threads: int,
    ) -> None:
        karaoke_ass_path = ""
        if karaoke_enabled:
            karaoke_ass_path = os.path.join(get_temp_cache_path(), f"{uuid4()}.ass")
            if not self._write_karaoke_ass_subtitles(karaoke_ass_path, audio_duration):
                karaoke_ass_path = ""

        filter_complex = self._short_ffmpeg_filter_complex(
            image_count=len(image_paths),
            durations=durations,
            fps=fps,
            crossfade=crossfade,
            ken_burns_enabled=ken_burns_enabled,
            karaoke_ass_path=karaoke_ass_path,
            music_volume=music_volume,
            audio_duration=audio_duration,
        )

        configured_preset = get_render_preset()
        bitrate = get_render_bitrate()
        candidates = self._render_codec_candidates()
        last_error = None

        for idx, codec in enumerate(candidates):
            preset = configured_preset
            if not preset and codec == "libx264":
                preset = "ultrafast"
            elif not preset and codec == "h264_nvenc":
                preset = "p1"

            cmd = ["ffmpeg", "-y", "-hide_banner", "-nostdin"]
            for image_path in image_paths:
                cmd.extend(["-i", image_path])
            cmd.extend(["-i", self.tts_path])
            cmd.extend(["-stream_loop", "-1", "-i", random_song])
            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-map", "[aout]",
                "-t", f"{audio_duration:.6f}",
                "-r", str(fps),
                "-threads", str(threads),
                "-c:v", codec,
            ])
            if preset:
                cmd.extend(["-preset", preset])
            if bitrate:
                cmd.extend(["-b:v", bitrate])
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                *self._mp4_compat_ffmpeg_params(),
                "-shortest",
                output_path,
            ])

            if get_verbose():
                info(
                    " => FFmpeg quality render: "
                    f"fps={fps}, codec={codec}, preset={preset or '(default)'}, "
                    f"threads={threads}, karaoke={bool(karaoke_ass_path)}"
                )

            result = subprocess.run(cmd, check=False)
            if result.returncode == 0:
                return

            last_error = RuntimeError(f"ffmpeg exited with code {result.returncode}")
            if idx < len(candidates) - 1:
                warning(
                    f"FFmpeg render failed with codec {codec}; "
                    f"trying {candidates[idx + 1]} instead."
                )

        raise last_error or RuntimeError("ffmpeg render failed")

    def _long_ffmpeg_filter_complex(
        self,
        *,
        image_count: int,
        durations: list[float],
        fps: int,
        crossfade: float,
        karaoke_ass_path: str,
        music_volume: float,
        audio_duration: float,
        total_duration: float,
        extra_tail: float,
    ) -> str:
        filters = []
        pan_scale_w = 1998
        pan_scale_h = 1124
        horizontal_pan = 220
        vertical_pan = 120

        for idx, this_dur in enumerate(durations):
            frames = max(1, int(round(this_dur * fps)))
            frame_denom = max(1, frames - 1)
            repeated = (
                f"loop=loop={max(0, frames - 1)}:size=1:start=0,"
                f"setpts=N/({fps}*TB),"
            )
            pan_base = (
                f"[{idx}:v]"
                f"scale={pan_scale_w}:{pan_scale_h}:"
                "force_original_aspect_ratio=increase:"
                "flags=lanczos+accurate_rnd,"
                "setsar=1,format=rgb24,"
            )
            progress = f"n/{frame_denom}"
            if idx % 4 == 0:
                x_expr = (
                    f"((iw-ow)/2)-(min(iw-ow\\,{horizontal_pan})/2)+"
                    f"min(iw-ow\\,{horizontal_pan})*({progress})"
                )
                y_expr = "(ih-oh)/2"
            elif idx % 4 == 1:
                x_expr = (
                    f"((iw-ow)/2)+(min(iw-ow\\,{horizontal_pan})/2)-"
                    f"min(iw-ow\\,{horizontal_pan})*({progress})"
                )
                y_expr = "(ih-oh)/2"
            elif idx % 4 == 2:
                x_expr = "(iw-ow)/2"
                y_expr = (
                    f"((ih-oh)/2)-(min(ih-oh\\,{vertical_pan})/2)+"
                    f"min(ih-oh\\,{vertical_pan})*({progress})"
                )
            else:
                x_expr = "(iw-ow)/2"
                y_expr = (
                    f"((ih-oh)/2)+(min(ih-oh\\,{vertical_pan})/2)-"
                    f"min(ih-oh\\,{vertical_pan})*({progress})"
                )

            filters.append(
                f"{pan_base}"
                f"{repeated}"
                f"crop=1920:1080:x='{x_expr}':y='{y_expr}',"
                f"trim=duration={this_dur:.6f},"
                "setpts=PTS-STARTPTS,format=yuv420p"
                f"[v{idx}]"
            )

        effective_crossfade = crossfade
        if image_count <= 1:
            video_label = "[v0]"
        elif effective_crossfade > 0 and all(d > effective_crossfade for d in durations):
            video_label = "[v0]"
            running_duration = durations[0]
            for idx in range(1, image_count):
                out_label = f"[lvx{idx}]"
                offset = max(0.0, running_duration - effective_crossfade)
                filters.append(
                    f"{video_label}[v{idx}]"
                    f"xfade=transition=fade:duration={effective_crossfade:.6f}:"
                    f"offset={offset:.6f},format=yuv420p"
                    f"{out_label}"
                )
                video_label = out_label
                running_duration += durations[idx] - effective_crossfade
        else:
            concat_inputs = "".join(f"[v{idx}]" for idx in range(image_count))
            filters.append(f"{concat_inputs}concat=n={image_count}:v=1:a=0,format=yuv420p[lvbase]")
            video_label = "[lvbase]"

        if extra_tail > 0:
            filters.append(
                f"{video_label}"
                f"fade=t=out:st={audio_duration:.6f}:d={extra_tail:.6f},"
                "format=yuv420p[lvfade]"
            )
            video_label = "[lvfade]"

        if karaoke_ass_path:
            ass_path = self._ffmpeg_filter_escape_path(karaoke_ass_path)
            fonts_dir = self._ffmpeg_filter_escape_path(get_fonts_dir())
            filters.append(
                f"{video_label}"
                f"ass=filename='{ass_path}':fontsdir='{fonts_dir}',"
                "scale=1920:1080:flags=lanczos+accurate_rnd:out_range=tv,"
                "format=yuv420p,"
                "setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709"
                "[vout]"
            )
        else:
            filters.append(
                f"{video_label}"
                "scale=1920:1080:flags=lanczos+accurate_rnd:out_range=tv,"
                "format=yuv420p,"
                "setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709"
                "[vout]"
            )

        voice_idx = image_count
        music_idx = image_count + 1
        music_fadein = min(3.0, total_duration)
        music_fadeout = min(extra_tail + 1.0, total_duration)
        music_fadeout_start = max(0.0, total_duration - music_fadeout)
        filters.extend([
            f"[{voice_idx}:a]aresample=44100,apad,atrim=0:{total_duration:.6f},"
            "asetpts=PTS-STARTPTS[voice]",
            f"[{music_idx}:a]aresample=44100,atrim=0:{total_duration:.6f},"
            f"asetpts=PTS-STARTPTS,volume={music_volume:.4f},"
            f"afade=t=in:st=0:d={music_fadein:.6f},"
            f"afade=t=out:st={music_fadeout_start:.6f}:d={music_fadeout:.6f}"
            "[music]",
            "[voice][music]amix=inputs=2:duration=first:dropout_transition=0,"
            f"atrim=0:{total_duration:.6f},asetpts=PTS-STARTPTS[aout]",
        ])
        return ";".join(filters)

    def _write_long_with_ffmpeg(
        self,
        *,
        output_path: str,
        image_paths: list[str],
        durations: list[float],
        random_song: str,
        fps: int,
        crossfade: float,
        karaoke_enabled: bool,
        music_volume: float,
        audio_duration: float,
        total_duration: float,
        extra_tail: float,
        threads: int,
    ) -> None:
        karaoke_ass_path = ""
        if karaoke_enabled:
            karaoke_ass_path = os.path.join(get_temp_cache_path(), f"{uuid4()}.ass")
            if not self._write_karaoke_ass_subtitles_landscape(karaoke_ass_path, total_duration):
                karaoke_ass_path = ""

        filter_complex = self._long_ffmpeg_filter_complex(
            image_count=len(image_paths),
            durations=durations,
            fps=fps,
            crossfade=crossfade,
            karaoke_ass_path=karaoke_ass_path,
            music_volume=music_volume,
            audio_duration=audio_duration,
            total_duration=total_duration,
            extra_tail=extra_tail,
        )

        configured_preset = get_render_preset()
        bitrate = get_render_bitrate()
        candidates = self._render_codec_candidates()
        last_error = None

        for idx, codec in enumerate(candidates):
            preset = configured_preset
            if not preset and codec == "libx264":
                preset = "ultrafast"
            elif not preset and codec == "h264_nvenc":
                preset = "p1"

            cmd = ["ffmpeg", "-y", "-hide_banner", "-nostdin"]
            for image_path in image_paths:
                cmd.extend(["-i", image_path])
            cmd.extend(["-i", self.tts_path])
            cmd.extend(["-stream_loop", "-1", "-i", random_song])
            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-map", "[aout]",
                "-t", f"{total_duration:.6f}",
                "-r", str(fps),
                "-threads", str(threads),
                "-c:v", codec,
            ])
            if preset:
                cmd.extend(["-preset", preset])
            if bitrate:
                cmd.extend(["-b:v", bitrate])
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                *self._mp4_compat_ffmpeg_params(),
                "-shortest",
                output_path,
            ])

            if get_verbose():
                info(
                    " => FFmpeg long render: "
                    f"fps={fps}, codec={codec}, preset={preset or '(default)'}, "
                    f"threads={threads}, karaoke={bool(karaoke_ass_path)}"
                )

            result = subprocess.run(cmd, check=False)
            if result.returncode == 0:
                return

            last_error = RuntimeError(f"ffmpeg exited with code {result.returncode}")
            if idx < len(candidates) - 1:
                warning(
                    f"FFmpeg long render failed with codec {codec}; "
                    f"trying {candidates[idx + 1]} instead."
                )

        raise last_error or RuntimeError("ffmpeg long render failed")

    def combine(self) -> str:
        """
        Combines everything into the final video.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        combined_image_path = os.path.join(get_video_cache_path(), str(uuid4()) + ".mp4")
        threads = get_threads()
        render_profile = get_short_render_profile()
        render_fps = get_short_render_fps()
        ken_burns_enabled = get_short_ken_burns_enabled()
        karaoke_enabled = get_short_karaoke_subtitles_enabled()
        crossfade = get_short_crossfade_seconds()
        tts_clip = AudioFileClip(self.tts_path)
        max_duration = tts_clip.duration

        print(colored("[+] Combining images...", "blue"))
        if get_verbose():
            info(
                " => Short render profile: "
                f"{render_profile} | fps={render_fps} | "
                f"ken_burns={ken_burns_enabled} | "
                f"karaoke={karaoke_enabled} | crossfade={crossfade:.2f}s"
            )

        # Verify all images exist BEFORE computing duration distribution â€”
        # stale paths would inflate n_imgs and shrink req_dur, leaving a
        # black tail where clips run out before the TTS does.
        valid_images = [p for p in self.images if os.path.exists(p)]
        if not valid_images:
            raise FileNotFoundError("No valid images found for video combination")
        if len(valid_images) != len(self.images):
            missing = [p for p in self.images if not os.path.exists(p)]
            if get_verbose():
                warning(f"Missing {len(missing)} images, using {len(valid_images)} valid ones")
            self.images = valid_images

        random_song = choose_random_song(getattr(self, "subject", ""))
        if is_soundimage_track(random_song):
            self._append_music_attribution(MATYAS_ATTRIBUTION)

        music_volume = (
            MaxRetentionEngine.MUSIC_VOLUME
            if is_max_retention(getattr(self, "_retention_mode", ""))
            else 0.15
        )

        if karaoke_enabled and not self.word_timestamps:
            self.word_timestamps = self._estimate_word_timestamps(max_duration)

        # Crossfade overlap between clips â€” compensate so the composed total == max_duration
        n_imgs = len(self.images)
        durations = self._short_clip_durations(n_imgs, max_duration, crossfade)

        if render_profile == "quality":
            try:
                print(colored("[+] Rendering quality Short with ffmpeg...", "blue"), flush=True)
                self._write_quality_short_with_ffmpeg(
                    output_path=combined_image_path,
                    image_paths=self.images,
                    durations=durations,
                    random_song=random_song,
                    fps=render_fps,
                    crossfade=crossfade,
                    ken_burns_enabled=ken_burns_enabled,
                    karaoke_enabled=karaoke_enabled,
                    music_volume=music_volume,
                    audio_duration=max_duration,
                    threads=threads,
                )
                success(f'Wrote Video to "{combined_image_path}"')
                return combined_image_path
            except Exception as e:
                warning(f"FFmpeg quality render failed, falling back to MoviePy: {e}")

        clips = []
        # Add each image once, distributing duration evenly across the full TTS length
        for idx, (image_path, this_dur) in enumerate(zip(self.images, durations)):
            if this_dur <= 0:
                break
            clip = ImageClip(image_path).set_duration(this_dur).set_fps(render_fps)

            # Not all images are same size,
            # so we need to resize them
            if round((clip.w / clip.h), 4) < 0.5625:
                if get_verbose():
                    info(f" => Resizing Image: {image_path} to 1080x1920")
                clip = crop(
                    clip,
                    width=clip.w,
                    height=round(clip.w / 0.5625),
                    x_center=clip.w / 2,
                    y_center=clip.h / 2,
                )
            else:
                if get_verbose():
                    info(f" => Resizing Image: {image_path} to 1920x1080")
                clip = crop(
                    clip,
                    width=round(0.5625 * clip.h),
                    height=clip.h,
                    x_center=clip.w / 2,
                    y_center=clip.h / 2,
                )
            clip = clip.resize((1080, 1920))

            if ken_burns_enabled:
                # Ken Burns: subtle zoom (alternating in/out per image for variety).
                # Pre-scale to 1.06x so zoom never reveals empty edges, then animate scale
                # between 1.00 (fit) and ~1.06 (fill+zoom). We wrap in a fixed-size
                # CompositeVideoClip so the output stays a deterministic 1080x1920.
                base = clip.resize(1.06).set_position("center")
                if idx % 2 == 0:
                    kb = base.resize(lambda t, d=this_dur: (1 / 1.06) + (1 - 1 / 1.06) * (t / d))
                else:
                    kb = base.resize(lambda t, d=this_dur: 1 - (1 - 1 / 1.06) * (t / d))
                kb = kb.set_position("center")

                clip = CompositeVideoClip([kb], size=(1080, 1920)).set_duration(this_dur)

            # Subtle crossfade in (except first clip) for smooth transitions
            if crossfade > 0 and idx > 0 and this_dur > crossfade:
                clip = clip.crossfadein(crossfade)

            # Re-assert duration just in case
            clip = clip.set_duration(this_dur)

            clips.append(clip)

        # Negative padding overlaps clips by `crossfade` seconds for smooth blending.
        # Duration was pre-compensated so composed total == max_duration (no black tail).
        padding = -crossfade if len(clips) > 1 else 0
        concat_method = "compose" if padding else "chain"
        final_clip = concatenate_videoclips(clips, padding=padding, method=concat_method)
        final_clip = final_clip.set_fps(render_fps)
        # Trim any float drift so video matches TTS exactly
        if final_clip.duration > max_duration:
            final_clip = final_clip.subclip(0, max_duration)

        subtitles = None
        if karaoke_enabled:
            try:
                print(colored("[+] Building karaoke subtitles...", "blue"), flush=True)

                subtitles = self._build_karaoke_subtitles(max_duration, fps=render_fps)

                if subtitles is not None:
                    print(colored("[+] Karaoke subtitles ready.", "green"), flush=True)
            except Exception as e:
                warning(f"Failed to generate subtitles, continuing without subtitles: {e}")
        elif get_verbose():
            info(" => Skipping burned-in karaoke subtitles for faster rendering.")

        print(colored("[+] Mixing audio...", "blue"), flush=True)
        random_song_clip = AudioFileClip(random_song).set_fps(44100)

        # Loop background music if shorter than TTS, then trim to match
        if random_song_clip.duration < tts_clip.duration:
            loops_needed = int(tts_clip.duration // random_song_clip.duration) + 1
            random_song_clip = concatenate_audioclips([random_song_clip] * loops_needed)
        random_song_clip = random_song_clip.subclip(0, tts_clip.duration)

        # Keep background music present but under the voice. MAXIMA RETENCION
        # lowers it further so the faster narration remains crisp.
        random_song_clip = random_song_clip.fx(afx.volumex, music_volume)
        comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), random_song_clip])

        final_clip = final_clip.set_audio(comp_audio)
        # Force exact duration match so no black frames can appear at the tail
        final_clip = final_clip.set_duration(max_duration)

        if subtitles is not None:
            # Clamp subtitles to video duration so they can't extend the composite
            # past the last image (which would produce a black tail with subs visible).
            subtitles = subtitles.set_duration(max_duration)
            final_clip = CompositeVideoClip(
                [final_clip, subtitles], size=(1080, 1920)
            ).set_duration(max_duration)

        print(colored("[+] Rendering final video (this may take a minute)...", "blue"), flush=True)
        self._write_videofile_with_fallback(
            final_clip,
            combined_image_path,
            threads=threads,
            fps=render_fps,
        )

        success(f'Wrote Video to "{combined_image_path}"')

        return combined_image_path

    def generate_video(self, tts_instance: TTS, custom_topic: str = "", image_mode: str = "ai",
                       preset_script: str = "") -> str:
        """
        Public entry point for the Shorts pipeline. Pins the LLM to the same
        cloud thinking model used by long videos (DeepSeek V4 Pro on Ollama
        Cloud by default, `think=high`), then delegates to the inner pipeline.

        When the user picked a specific provider+model from the UI
        (`is_user_override()`), the hardcoded force_provider call is skipped
        so the user's choice is respected end-to-end.

        `preset_script` skips the LLM script step â€” used by the "Vista previa"
        flow so the user-approved (and possibly edited) script is rendered
        as-is.
        """
        from llm_provider import force_provider, warmup_ollama_model, is_user_override, get_active_provider, get_active_model
        if is_user_override():
            active = get_active_provider()
            active_model = get_active_model() or "(default)"
            info(f"\n  Short LLM: {active}/{active_model} (user override - no think pin)")
            if active == "ollama" and active_model and active_model != "(default)":
                warmup_ollama_model(active_model)
            return self._generate_video_inner(tts_instance, custom_topic, image_mode, preset_script)

        long_models = get_long_video_llm_models()
        primary = long_models[0] if long_models else get_long_video_llm_model()
        info(f"\n  Short LLM: ollama/{primary}"
             + (f"  (fallbacks: {', '.join(long_models[1:])})" if len(long_models) > 1 else ""))
        if primary:
            warmup_ollama_model(primary)
        with force_provider("ollama", long_models or primary):
            return self._generate_video_inner(tts_instance, custom_topic, image_mode, preset_script)

    def _generate_video_inner(self, tts_instance: TTS, custom_topic: str = "", image_mode: str = "ai",
                              preset_script: str = "") -> str:
        """
        Generates a YouTube Short based on the provided niche and language.

        Args:
            tts_instance (TTS): Instance of TTS Class.
            custom_topic (str): Optional user-provided topic. If given, skips auto topic generation.
            image_mode (str): "ai" (default) uses AI image generators first.
                              "photos" uses real photos (Wikimedia / Pexels / Pixabay) first.
            preset_script (str): Optional pre-approved script body. When non-empty,
                                 the LLM script-generation step is skipped â€” used by
                                 the "Vista previa" flow so the user can review (and
                                 even edit) the script before render starts.

        Returns:
            path (str): The path to the generated MP4 File, or empty string if cancelled.
        """
        # Reset per-video state. Without this, a 2nd run in the same session
        # inherits stale paths from the 1st (whose PNGs were wiped by
        # rem_temp_files()), inflating n_imgs in combine() and leaving half
        # the short as a black tail.
        self.images = []
        self.image_prompts = []
        self.word_timestamps = None
        self.tts_path = None
        self.subtitles_path = None
        self._used_stock_urls = set()
        self.retention_preflight = {}
        self.retention_hook_lab = {}
        self.visual_beat_map = []
        self.visual_beat_report = {}
        self.visual_preflight = {}
        self.retention_plan = {}
        # Shorts upload fast â€” no need for the long-video patient wait.
        self._is_long_video = False

        # Generate the Topic (or use the user-provided one)
        if custom_topic and custom_topic.strip():
            self.subject = custom_topic.strip()
            if get_verbose():
                info(f" => Using custom topic: {self.subject}")
        else:
            self.generate_topic()

        # Duplicate guard: generate_topic returns "" when it cannot produce a
        # topic that has not already been used on this channel. We refuse to
        # publish a repeat, so bail out cleanly.
        if not self.subject or not self.subject.strip():
            error(
                "Aborting Short: no unique topic available. "
                "No video will be generated or uploaded."
            )
            self.video_path = ""
            return ""

        # Generate the Script (unless the caller pre-approved one)
        if preset_script and preset_script.strip():
            self.script = preset_script.strip()
            self._run_max_retention_preflight(
                self.script,
                sentence_length=self._sentence_length_override or get_script_sentence_length(),
                allow_rewrite=False,
            )
            if get_verbose():
                info(f" => Using pre-approved script ({len(self.script)} chars)")
        else:
            self.generate_script()

        # Generate the Metadata
        self.generate_metadata()

        # Generate the Image Prompts (AI-style or search-query-style)
        self.generate_prompts(image_mode=image_mode)

        # Generate the Images (parallel batch for speed)
        self.generate_images_batch(self.image_prompts, image_mode=image_mode)

        # Generate the TTS
        self.generate_script_to_speech(tts_instance)

        # Combine everything
        path = self.combine()

        if get_verbose():
            info(f" => Generated Video: {path}")

        self.video_path = os.path.abspath(path)
        self._build_retention_plan(self.video_path)
        self._persist_metadata_sidecar(is_long=False)

        try:
            from upload_tracker import record_generation
            record_generation(
                self.video_path,
                list(self.images),
                [getattr(self, "tts_path", None), getattr(self, "subtitles_path", None)],
                subject=getattr(self, "subject", "") or "",
            )
        except Exception as _e:
            warning(f"Could not record upload manifest: {_e}")
        self._persist_retention_plan()

        return path

    # ============================================================
    #  LONG VIDEO PIPELINE (15-16 minutes max, 16:9 landscape)
    # ============================================================

    def generate_long_script(self) -> str:
        """
        Generates a structured long-form script for a 15-16 minute video
        (~2000-2200 words at slow Spanish documentary narration speed).

        Two strategies, picked by active LLM provider:
          - Gemini Flash 2.5/3 â†’ SINGLE call (large output window handles 3000+ words).
            Falls back to per-section if the single call returns too short.
          - Ollama / others â†’ ONE LLM CALL PER SECTION (12 calls)
            because free / small models cap output around 400-700 words per call.

        Both paths share the same narrative structure (cold-open hook from
        HOOK_PROFILES, sections shaped by LONG_VIDEO_SECTION_THEMES) so the
        video opening hooks the viewer regardless of provider.
        """
        import random

        lang = self.language

        # Pick ONE hook style per video so the cold open isn't generic. The
        # picked (style, example) is forwarded into both single-call and
        # sectional paths â€” keeps the opening varied across runs.
        is_cosmic_video = CosmicRetentionEngine.is_cosmic_context(self.subject, self.niche)
        profile_name = (self._hook_profile or "").strip().lower() or (
            "storytelling" if is_cosmic_video else "educational"
        )
        hook_styles = HOOK_PROFILES.get(profile_name) or HOOK_PROFILES["educational"]
        if profile_name not in HOOK_PROFILES and self._hook_profile:
            warning(f"Unknown hook_profile '{self._hook_profile}', falling back to 'educational'.")
            profile_name = "educational"
        hook_style, hook_example = random.choice(hook_styles)
        if get_verbose():
            info(f" => Long-video hook profile: {profile_name} | style: {hook_style}")

        # ---- FAST PATH: Gemini can produce the whole script in a single call ----
        try:
            from llm_provider import get_active_provider
            active_provider = get_active_provider()
        except Exception:
            active_provider = ""

        if active_provider == "gemini":
            SINGLE_CALL_ATTEMPTS = 3
            info(f" [Script] Gemini detected â€” trying single-call fast path (up to {SINGLE_CALL_ATTEMPTS} attempts)...")
            best_short = ""  # remember the longest under-2000-word draft in case all attempts come up short
            for attempt in range(1, SINGLE_CALL_ATTEMPTS + 1):
                try:
                    full = self._generate_long_script_single_call(lang, hook_style, hook_example)
                    word_count = len(full.split())
                    if word_count >= 2000:
                        full = self._postprocess_long_script(full)
                        self.script = full
                        self._persist_long_script(full)
                        info(f" => Generated long script: {len(full.split())} words (~{len(full.split()) // LONG_VIDEO_ESTIMATED_WPM} min) (single-call attempt {attempt})")
                        return full
                    warning(f"   Single-call attempt {attempt}/{SINGLE_CALL_ATTEMPTS} returned only {word_count} words.")
                    if word_count > len(best_short.split()):
                        best_short = full
                except Exception as e:
                    warning(f"   Single-call attempt {attempt}/{SINGLE_CALL_ATTEMPTS} failed: {str(e)[:200]}")
            warning("   All single-call attempts came up short or failed; falling back to per-section.")

        # ---- DEFAULT PATH: per-section for capped providers ----
        full = self._generate_long_script_sectional(lang, hook_style, hook_example)
        full = self._postprocess_long_script(full)
        self.script = full
        self._persist_long_script(full)
        return full

    def _postprocess_long_script(self, script: str) -> str:
        """
        Final sanity pass on a long script:
        - Strip any LLM preamble that survived per-call cleaning ("Por supuesto", "Claro,", etc).
        - Cap total length to ~2200 words (about 15-16 min) to prevent runaways.
        - Warn (not fail) if the first 200 words don't mention any topic keyword,
          which is a strong hint the LLM went off-topic.
        """
        text = script.strip()

        # Strip leading conversational preamble paragraphs the per-call cleaner can miss.
        preamble_starters = (
            r"^\s*(Â¡?(por supuesto|claro|desde luego|con gusto|aquÃ­ (te|te lo|tienes|estÃ¡|va)|"
            r"a continuaciÃ³n|sure|of course|certainly|absolutely|here(?:'s| is)|i'?ll|let me))[^\n]*\n+"
        )
        for _ in range(3):  # peel up to 3 preamble lines if stacked
            new = re.sub(preamble_starters, "", text, count=1, flags=re.IGNORECASE)
            if new == text:
                break
            text = new

        # Hard cap so we stay around 15-16 min of narration. Cut on a sentence boundary near the cap.
        WORD_CAP = LONG_VIDEO_TARGET_MAX_WORDS
        words = text.split()
        if len(words) > WORD_CAP:
            warning(f"   Script {len(words)} words â†’ capping to ~{WORD_CAP} words.")
            cut_text = " ".join(words[:WORD_CAP])
            # Try to end on a sentence boundary so the cap doesn't sound abrupt.
            last_period = max(cut_text.rfind("."), cut_text.rfind("!"), cut_text.rfind("?"))
            if last_period > len(cut_text) * 0.7:
                cut_text = cut_text[: last_period + 1]
            text = cut_text

        # Topic relevance â€” be strict. The script MUST mention significant tokens
        # from self.subject. If not, abort: a wrong-topic script is worse than no video.
        def _norm(s: str) -> str:
            import unicodedata
            s = unicodedata.normalize("NFKD", s.lower())
            return "".join(c for c in s if not unicodedata.combining(c))

        subj_tokens = {
            _norm(t) for t in _unicode_words(self.subject or "")
            if len(t) > 4
        }
        if subj_tokens:
            full_norm = _norm(text)
            mentions = sum(1 for tok in subj_tokens if tok in full_norm)
            head_norm = _norm(" ".join(text.split()[:300]))
            head_mentions = sum(1 for tok in subj_tokens if tok in head_norm)

            # If the topic appears NOWHERE in the entire script â†’ off-topic, abort.
            if mentions == 0:
                raise RuntimeError(
                    f"Aborting: generated script never mentions any keyword from the topic "
                    f"({', '.join(list(subj_tokens)[:5])}). The LLM drifted entirely. "
                    f"Re-run the generation."
                )
            # If the topic appears in <30% of expected places, warn loudly.
            if mentions < max(1, len(subj_tokens) // 3):
                warning(
                    f"   Topic only mentioned {mentions} of {len(subj_tokens)} keywords â€” "
                    f"script may be partially off-topic. Inspect before publishing."
                )
            # If the intro never mentions the topic, warn (intro should hook the topic).
            if head_mentions == 0:
                warning(
                    f"   Script intro doesn't mention the topic. Inspect the first paragraph."
                )

        return text.strip()

    def _persist_long_script(self, script: str) -> None:
        """Save the final long script to scratch space for inspection / debugging."""
        try:
            path = os.path.join(get_temp_cache_path(), f"script_{uuid4()}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Topic: {self.subject}\n")
                f.write(f"# Words: {len(script.split())}\n")
                f.write(f"# Estimated duration: ~{len(script.split()) // LONG_VIDEO_ESTIMATED_WPM} min\n")
                f.write("# " + ("=" * 60) + "\n\n")
                f.write(script)
            info(f"   [Script] Saved to: {path}")
        except Exception as e:
            warning(f"   Could not persist script: {e}")

    def _generate_long_script_single_call(self, lang: str, hook_style: str, hook_example: str) -> str:
        """
        Ask the LLM for the entire 15-16 min script in one call.
        Designed for high-output-window providers (Gemini Flash 2.5/3).
        """
        # Series-aware: when the active series defines a brief / themes, build
        # the structure description from those themes so the single-call prompt
        # gets the same immersive guidance as the sectional path.
        series = getattr(self, "active_series", None) or {}
        script_brief = (series.get("script_brief") or "").strip()
        series_themes = series.get("section_themes") or []

        if script_brief:
            info(f" => Using series narrative brief: {series.get('id', '')}")

        if isinstance(series_themes, list) and len(series_themes) == 10:
            themes = list(series_themes)
        else:
            themes = CosmicRetentionEngine.long_section_themes(
                LONG_VIDEO_SECTION_THEMES,
                self.subject,
                self.niche,
            )
        sections_block = "\n\n".join(
            f"[SECTION {i+1}: <tÃ­tulo corto descriptivo>]\n{theme}\n(8-10 oraciones, 160-190 palabras.)"
            for i, theme in enumerate(themes)
        )

        brief_block = (
            f"\nDIRECTIVA NARRATIVA DE LA SERIE â€” OBLIGATORIA EN CADA PALABRA DE TU RESPUESTA:\n{script_brief}\n"
            if script_brief else ""
        )
        retention_block = CosmicRetentionEngine.long_generation_directive(
            self.subject,
            self.niche,
            lang,
        )
        voice_block = NarrationVoice.long_generation_directive(lang)

        prompt = f"""Eres un narrador experto de documentales y guionista profesional especializado en RETENCIÃ“N: tu trabajo es que el espectador NO se vaya en los primeros 5 minutos y aguante hasta el final.
Escribe un GUION COMPLETO de narraciÃ³n cautivador de 15 a 16 minutos como mÃ¡ximo sobre el siguiente tema.

Tema: {self.subject}
{brief_block}
{retention_block}
{voice_block}
ARQUITECTURA DE RETENCIÃ“N â€” LEE ESTO ANTES DE EMPEZAR:
- Los primeros 5 minutos (INTRO + SECTION 1 + SECTION 2) son un MOTOR DE GANCHO: cold open cinematogrÃ¡fico â†’ viÃ±eta inmersiva â†’ siembra del MISTERIO PRINCIPAL del video.
- ESTÃ PROHIBIDO mencionar "me gusta" o "like" en el INTRO, en la SECTION 1 o en la SECTION 2. La invitaciÃ³n al like aparece SOLO al INICIO de la SECTION 3, cuando el espectador ya estÃ¡ enganchado.
- El loop principal sembrado en la SECTION 2 NO se responde hasta la SECTION 9 (clÃ­max). Las secciones intermedias pueden abrir y cerrar loops secundarios mÃ¡s pequeÃ±os, pero el principal queda intacto.
- Cada secciÃ³n debe ENGANCHAR a la siguiente: termina con una imagen, pregunta o tensiÃ³n que obligue a seguir.

ESTRUCTURA OBLIGATORIA (usa estos marcadores EXACTOS):
[INTRO]
Cold open de impacto (5-6 oraciones, 100-130 palabras). NO incluyas invitaciÃ³n al like aquÃ­. Estructura interna:
1. PRIMERA ORACIÃ“N â€” gancho cinematogrÃ¡fico siguiendo EXACTAMENTE este estilo: {hook_style}.
   Ejemplo del estilo (adapta a {lang} y al tema, no copies literal): {hook_example}
   No defaultees a "SabÃ­as que..." ni a "Imagina que...". El estilo de arriba es obligatorio.
2. ORACIONES 2-3 â€” promesa del video: quÃ© descubrirÃ¡ el espectador, expresada como apuesta narrativa, NO como Ã­ndice de contenidos.
3. ORACIONES 4-6 â€” siembra 2-3 LOOPS ABIERTOS: preguntas, anomalÃ­as o contradicciones especÃ­ficas que NO respondes aquÃ­. Promete que las respuestas llegan mÃ¡s adelante. Ejemplos del tipo de frase a usar: "Pero hay un detalle que no encajaâ€¦", "Y aquÃ­ es donde la historia se vuelve imposibleâ€¦", "Lo que vinieron a descubrir nadie estaba preparado para contarlo."
4. ÃšLTIMA ORACIÃ“N â€” corta y poderosa, que invite a quedarse. NO menciones suscripciÃ³n, NO menciones like.

{sections_block}

[CLOSING]
ConclusiÃ³n memorable (4-5 oraciones, 80-110 palabras). Termina con una reflexiÃ³n que perdure.

[OUTRO]
Despedida cÃ¡lida y llamado a la acciÃ³n para los Ãºltimos segundos del video, cuando aparecen las pantallas finales de YouTube (suscribirse, video recomendado). Dura 3-4 oraciones (40-60 palabras).
DEBE incluir, redactado de forma natural y orgÃ¡nica:
1. Agradecer al espectador por haber visto el video.
2. Pedir que dÃ© "me gusta" si le gustÃ³.
3. Pedir que se SUSCRIBA al canal y active la CAMPANITA para no perderse contenido similar.
4. Una despedida cÃ¡lida ("Hasta la prÃ³xima", "Hasta pronto", "Nos vemos en el siguiente video", o equivalente).
NO uses bullets, NO suene robÃ³tico â€” escrÃ­belo como si lo dijeras hablando, con calidez.

REGLAS DE ESTILO:
- Escribe como un narrador apasionado, NO como un libro de texto. Lenguaje vÃ­vido y sensorial.
- Cada oraciÃ³n fluye naturalmente hacia la siguiente.
- Usa preguntas retÃ³ricas, comparaciones sorprendentes y ganchos emocionales.
- Oraciones CORTAS (mÃ¡ximo 20 palabras cada una).
- TOTAL OBLIGATORIO: entre {LONG_VIDEO_TARGET_MIN_WORDS} y {LONG_VIDEO_TARGET_MAX_WORDS} palabras. Nunca pases de {LONG_VIDEO_TARGET_MAX_WORDS} palabras.
- Cada secciÃ³n debe aportar material NUEVO, no repetir.
- ESCRIBE TODO EN {lang}. NO uses inglÃ©s.
- NO markdown, NO viÃ±etas, NO listas numeradas.
- NO URLs, enlaces, citas ni referencias.
- NO digas etiquetas de estructura en la narraciÃ³n: nunca escribas "primera revelaciÃ³n", "segunda revelaciÃ³n", "hook", "contexto", "desarrollo", "conclusiÃ³n", "parte uno" ni "secciÃ³n dos". Esos nombres son instrucciones privadas, no texto hablado.
- ESTRICTAMENTE PROHIBIDO escribir acotaciones de cualquier tipo. Solo texto que un narrador dirÃ­a EN VOZ ALTA. NUNCA escribas:
    * "(imagen de ...)", "(imÃ¡genes de ...)", "[plano cerrado de ...]", "(escena ...)", "(secuencia ...)"
    * "(B-roll: ...)", "(B/O ...)", "(voz en off)", "(narrador:)"
    * "(mÃºsica suave)", "(sonido de ...)", "(efectos)", "(silencio)"
    * "(emoji ...)", "(emoticono ...)", "(sÃ­mbolo ...)"
    * "(transiciÃ³n)", "(fundido)", "(zoom)", "(corte)", "(cierre)"
  Si crees que necesitas describir una imagen o un sonido, NO LO HAGAS â€” el video ya tiene imÃ¡genes y mÃºsica. Solo narra.
- NÃšMEROS: escribe TODOS los nÃºmeros con palabras, no con dÃ­gitos. Ejemplos:
    * "hace cuatro mil quinientos aÃ±os" (no "hace 4.500 aÃ±os")
    * "el aÃ±o mil cuatrocientos cincuenta y tres" (no "1453")
    * "el siglo diecisÃ©is" (no "el siglo XVI" ni "el siglo 16")
    * "tres coma uno cuatro" (no "3,14")
- AÃ‘O vs DURACIÃ“N â€” distÃ­nguelos siempre. Un AÃ‘O es una FECHA del calendario; una DURACIÃ“N es el tiempo transcurrido. Son cosas distintas. Para citar un aÃ±o, di "el aÃ±o <aÃ±o>". La fÃ³rmula "hace <N> aÃ±os" expresa SOLO duraciÃ³n: <N> es la diferencia entre el aÃ±o actual y el aÃ±o del evento, NO es el aÃ±o mismo. Ante la duda, nombra el aÃ±o ("el aÃ±o X") y NO uses la fÃ³rmula "hace X aÃ±os".
- SOLO devuelve el guion completo con los 12 marcadores arriba listados. Sin preÃ¡mbulo.
"""
        completion = self._clean_llm_script(self.generate_response(prompt))
        return completion

    def _generate_long_script_sectional(self, lang: str, hook_style: str, hook_example: str) -> str:
        """Per-section generation (12 calls) for providers with low output caps."""

        # Series-aware: when a series brief / themes are configured, use them so
        # the script follows the series voice (e.g. immersive 2nd-person POV for
        # "Un dÃ­a en la historia") instead of the generic documentary structure.
        series = getattr(self, "active_series", None) or {}
        script_brief = (series.get("script_brief") or "").strip()
        series_themes = series.get("section_themes") or []
        if script_brief:
            info(f" => Using series narrative brief: {series.get('id', '')}")

        # Per-section thematic guidance â€” what role each section plays in the narrative arc.
        # Series-defined themes win when present and are exactly 10 entries.
        if isinstance(series_themes, list) and len(series_themes) == 10:
            section_themes = list(series_themes)
        else:
            section_themes = CosmicRetentionEngine.long_section_themes(
                LONG_VIDEO_SECTION_THEMES,
                self.subject,
                self.niche,
            )

        # Block of narrative directives prepended to every per-call prompt when
        # a series brief is active. Empty string in non-series mode (no-op).
        brief_block = (
            f"\n\nDIRECTIVA NARRATIVA DE LA SERIE â€” OBLIGATORIA EN CADA PALABRA DE TU RESPUESTA:\n{script_brief}\n\n"
            if script_brief else ""
        )
        retention_block = CosmicRetentionEngine.long_generation_directive(
            self.subject,
            self.niche,
            lang,
        )
        voice_block = NarrationVoice.long_generation_directive(lang)

        def _ask_section(prompt: str, min_words: int) -> str:
            """Call the LLM with retries until we hit min_words AND the content is clean."""
            best = ""
            for attempt in range(4):
                completion = self._clean_llm_script(self.generate_response(prompt))
                # Reject the response entirely if it looks like garbage / metadata.
                if self._looks_like_garbage(completion):
                    warning(f"   chunk looked like garbage / metadata, retry {attempt + 2}/4")
                    continue
                if len(completion.split()) > len(best.split()):
                    best = completion
                if len(best.split()) >= min_words:
                    break
                if attempt < 3:
                    warning(f"   chunk short ({len(best.split())} words), retry {attempt + 2}/4")
            return best

        def _ensure_marker(text: str, marker: str) -> str:
            """Prepend the section marker if the LLM forgot it (or used a wrong one)."""
            text = text.strip()
            if not re.match(r"^\s*\[(INTRO|SECTION|CLOSING|OUTRO)", text, re.IGNORECASE):
                text = f"{marker}\n{text}"
            return text

        parts: List[str] = []
        info(f" [Script] Building 15-16 min script section by section...")

        # ---- INTRO â€” cold open + open loops (NO like-ask here) ----
        intro_prompt = f"""Eres un narrador experto de documentales especializado en RETENCIÃ“N. Escribe SOLO la INTRODUCCIÃ“N de un guion documental sobre: {self.subject}
{brief_block}{retention_block}{voice_block}
OBJETIVO DE LA INTRO: enganchar al espectador en los primeros 30 segundos para que se quede hasta el final. NO menciones "me gusta" ni "like" â€” esa invitaciÃ³n va en otra secciÃ³n posterior, NUNCA aquÃ­.

ESTRUCTURA OBLIGATORIA (5-6 oraciones, 100-130 palabras):
1. PRIMERA ORACIÃ“N â€” gancho cinematogrÃ¡fico que siga EXACTAMENTE este estilo: {hook_style}.
   Ejemplo del estilo (adapta al tema y a {lang}, NO copies literal): {hook_example}
   No defaultees a "SabÃ­as que..." ni a "Imagina que...". El estilo descrito es OBLIGATORIO.
2. ORACIONES 2-3 â€” promesa del video: quÃ© descubrirÃ¡ el espectador. NO como Ã­ndice de contenidos, sino como apuesta narrativa con tono de "no te vas a creer lo que viene".
3. ORACIONES 4-6 â€” SIEMBRA 2-3 LOOPS ABIERTOS: preguntas, anomalÃ­as o contradicciones especÃ­ficas que NO respondes aquÃ­. Que el espectador NO PUEDA irse sin saber la respuesta. Frases tipo: "Pero hay un detalle que no encajaâ€¦", "Y aquÃ­ es donde la historia se vuelve imposibleâ€¦", "Lo que descubrieron nadie esperaba contarlo." Promete que las respuestas llegan mÃ¡s adelante.
4. ÃšLTIMA ORACIÃ“N â€” corta, poderosa, que invite a quedarse. NO menciones suscripciÃ³n, NO menciones like, NO digas "vamos a empezar".

REGLAS DE ESTILO:
- Lenguaje vÃ­vido y sensorial. Oraciones CORTAS (mÃ¡ximo 20 palabras).
- ESCRIBE TODO EN {lang}. NO uses inglÃ©s.
- NO uses markdown, viÃ±etas, listas, URLs, ni meta-texto.
- NO digas etiquetas de estructura en voz alta: nada de "primera revelaciÃ³n", "segunda revelaciÃ³n", "hook", "contexto", "desarrollo", "conclusiÃ³n", "parte uno" o "secciÃ³n dos".
- ESTRICTAMENTE PROHIBIDO escribir acotaciones: nada de "(imagen ...)", "[plano ...]", "(B-roll ...)", "(mÃºsica ...)", "(emoji ...)", "(transiciÃ³n)" etc. Solo texto hablado.
- NÃšMEROS: escribe los nÃºmeros con palabras, no con dÃ­gitos ("mil cuatrocientos cincuenta y tres", no "1453"; "cuatro mil quinientos", no "4.500").
- AÃ‘O vs DURACIÃ“N â€” distÃ­nguelos siempre. Un AÃ‘O es una FECHA del calendario; una DURACIÃ“N es el tiempo transcurrido. Para citar un aÃ±o, di "el aÃ±o <aÃ±o>". "Hace <N> aÃ±os" expresa SOLO duraciÃ³n. Ante la duda, nombra el aÃ±o.
- Devuelve SOLO el texto, precedido EXACTAMENTE por la lÃ­nea: [INTRO]
"""
        intro = _ensure_marker(_ask_section(intro_prompt, min_words=80), "[INTRO]")
        parts.append(intro)
        info(f"   [Script] INTRO: {len(intro.split())} words")

        # ---- SECTIONS 1-10 ----
        # `opening_context` snapshots the INTRO + S1 + S2 (the "first 5 min hook engine")
        # so that sections 3-9 can see which loops were planted and respect them
        # (the main mystery stays open until S9; the like-ask happens only at the
        # opening of S3). Captured once S1 and S2 have been written.
        opening_context = ""
        for i, theme in enumerate(section_themes, start=1):
            prior = "\n\n".join(parts)
            tail = " ".join(prior.split()[-250:]) if prior else ""

            # Snapshot the hook engine after S2 is in `parts` (i.e. when we're
            # about to write S3 and onward). `parts` currently holds
            # [INTRO, S1, ..., S(i-1)] â€” for i=3 that is exactly INTRO+S1+S2.
            if i == 3:
                opening_context = "\n\n".join(parts)

            # Build the "open loops" reminder block prepended to S3+ prompts.
            # - S1/S2: empty (these sections ARE the loop engine).
            # - S3-S8: "main loop stays open, you may close small loops".
            # - S9: "this is the climax â€” you MUST close the main loop now".
            # - S10: post-climax, focus on legacy, do NOT reopen the loop.
            if i >= 3 and opening_context:
                if i == 9:
                    loops_block = (
                        "\n\nPRIMEROS 5 MINUTOS DEL VIDEO (los loops que sembraste â€” ahora hay que cerrar el principal):\n"
                        f'"""\n{opening_context}\n"""\n'
                        "ESTA SECCIÃ“N ES EL CLÃMAX. Debes responder de forma satisfactoria al MISTERIO PRINCIPAL sembrado en la secciÃ³n 2. NO dejes esa pregunta abierta.\n"
                    )
                elif i == 10:
                    loops_block = (
                        "\n\nNOTA NARRATIVA: el MISTERIO PRINCIPAL ya fue revelado en la secciÃ³n anterior (clÃ­max). Esta secciÃ³n es el cierre: no abras loops nuevos, asienta lo aprendido y prepara emocionalmente al espectador para la despedida.\n"
                    )
                else:
                    loops_block = (
                        "\n\nPRIMEROS 5 MINUTOS DEL VIDEO (referencia â€” respeta los loops abiertos aquÃ­):\n"
                        f'"""\n{opening_context}\n"""\n'
                        "REGLA DE LOOPS: el MISTERIO PRINCIPAL sembrado en la secciÃ³n 2 NO se responde todavÃ­a â€” se reserva para la secciÃ³n 9 (clÃ­max). Puedes cerrar loops secundarios pequeÃ±os y abrir nuevos segÃºn el rol de esta secciÃ³n.\n"
                    )
            else:
                loops_block = ""

            section_prompt = f"""Eres un narrador experto de documentales especializado en retenciÃ³n. EstÃ¡s escribiendo la SECCIÃ“N {i} de 10 de un guion sobre: {self.subject}
{brief_block}{retention_block}{voice_block}{loops_block}
Esto es lo Ãºltimo que ya se narrÃ³ (NO lo repitas, continÃºa el flujo natural):
\"\"\"
{tail}
\"\"\"

Escribe SOLO la SECCIÃ“N {i}:
- ROL NARRATIVO de esta secciÃ³n: {theme}
- 8-10 oraciones (160-190 palabras).
- Lenguaje vÃ­vido y sensorial. Oraciones CORTAS (mÃ¡ximo 20 palabras).
- Aporta material NUEVO, no repitas ideas ya dichas.
- ESCRIBE TODO EN {lang}. NO uses inglÃ©s.
- NO uses markdown, viÃ±etas, listas, URLs, ni meta-texto.
- NO digas etiquetas de estructura en voz alta: nada de "primera revelaciÃ³n", "segunda revelaciÃ³n", "hook", "contexto", "desarrollo", "conclusiÃ³n", "parte uno" o "secciÃ³n dos".
- ESTRICTAMENTE PROHIBIDO escribir acotaciones: nada de "(imagen ...)", "[plano ...]", "(B-roll ...)", "(mÃºsica ...)", "(emoji ...)", "(transiciÃ³n)" etc. Solo texto hablado.
- NÃšMEROS: escribe los nÃºmeros con palabras, no con dÃ­gitos ("mil cuatrocientos cincuenta y tres", no "1453"; "cuatro mil quinientos", no "4.500").
- AÃ‘O vs DURACIÃ“N â€” distÃ­nguelos siempre. Un AÃ‘O es una FECHA del calendario; una DURACIÃ“N es el tiempo transcurrido. Son cosas distintas. Para citar un aÃ±o, di "el aÃ±o <aÃ±o>". La fÃ³rmula "hace <N> aÃ±os" expresa SOLO duraciÃ³n: <N> es la diferencia entre el aÃ±o actual y el aÃ±o del evento, NO es el aÃ±o mismo. Ante la duda, nombra el aÃ±o ("el aÃ±o X") y NO uses la fÃ³rmula "hace X aÃ±os".
- Devuelve SOLO el texto de la secciÃ³n, precedido EXACTAMENTE por una lÃ­nea con: [SECTION {i}: <tÃ­tulo breve descriptivo>]
"""
            section = _ensure_marker(_ask_section(section_prompt, min_words=160), f"[SECTION {i}: parte {i}]")
            parts.append(section)
            info(f"   [Script] SECTION {i}: {len(section.split())} words")

        # ---- CLOSING ----
        prior = "\n\n".join(parts)
        tail = " ".join(prior.split()[-300:])
        closing_prompt = f"""Eres un narrador experto de documentales. EstÃ¡s escribiendo el CIERRE de un guion sobre: {self.subject}
{brief_block}{retention_block}{voice_block}
Esto es lo Ãºltimo que se narrÃ³:
\"\"\"
{tail}
\"\"\"

Escribe SOLO el CIERRE:
- 4-5 oraciones (80-110 palabras).
- ConclusiÃ³n memorable. Termina con una reflexiÃ³n que se quede con el espectador.
- Lenguaje vÃ­vido. Oraciones CORTAS (mÃ¡ximo 20 palabras).
- ESCRIBE TODO EN {lang}. NO uses inglÃ©s.
- NO uses markdown, viÃ±etas, listas, URLs, ni meta-texto.
- NO digas etiquetas de estructura en voz alta: nada de "primera revelaciÃ³n", "segunda revelaciÃ³n", "hook", "contexto", "desarrollo", "conclusiÃ³n", "parte uno" o "secciÃ³n dos".
- ESTRICTAMENTE PROHIBIDO escribir acotaciones: nada de "(imagen ...)", "[plano ...]", "(B-roll ...)", "(mÃºsica ...)", "(emoji ...)", "(transiciÃ³n)" etc. Solo texto hablado.
- NÃšMEROS: escribe los nÃºmeros con palabras, no con dÃ­gitos ("mil cuatrocientos cincuenta y tres", no "1453").
- AÃ‘O vs DURACIÃ“N â€” distÃ­nguelos siempre. Un AÃ‘O es una FECHA del calendario; una DURACIÃ“N es el tiempo transcurrido. Son cosas distintas. Para citar un aÃ±o, di "el aÃ±o <aÃ±o>". La fÃ³rmula "hace <N> aÃ±os" expresa SOLO duraciÃ³n: <N> es la diferencia entre el aÃ±o actual y el aÃ±o del evento, NO es el aÃ±o mismo. Ante la duda, nombra el aÃ±o ("el aÃ±o X") y NO uses la fÃ³rmula "hace X aÃ±os".
- Devuelve SOLO el texto, precedido EXACTAMENTE por la lÃ­nea: [CLOSING]
"""
        closing = _ensure_marker(_ask_section(closing_prompt, min_words=80), "[CLOSING]")
        parts.append(closing)
        info(f"   [Script] CLOSING: {len(closing.split())} words")

        # ---- OUTRO (CTA + farewell â€” coincides with YouTube's end screen overlay) ----
        prior = "\n\n".join(parts)
        tail = " ".join(prior.split()[-200:])
        outro_prompt = f"""Eres un narrador experto de documentales. EstÃ¡s escribiendo la DESPEDIDA FINAL de un guion sobre: {self.subject}

Esto es lo Ãºltimo que se narrÃ³:
\"\"\"
{tail}
\"\"\"

Escribe SOLO la DESPEDIDA, pensada para los Ãºltimos segundos del video cuando aparecen las pantallas finales de YouTube (suscribirse, video recomendado).

ESTRUCTURA OBLIGATORIA (3-4 oraciones, 40-60 palabras), redactada de forma natural y orgÃ¡nica como si la dijeras hablando con calidez (NO bullets, NO suene robÃ³tico):
1. Agradece al espectador por haber visto el video.
2. PÃ­dele que dÃ© "me gusta" si le gustÃ³.
3. PÃ­dele que se SUSCRIBA al canal y active la CAMPANITA para no perderse contenido similar.
4. DespÃ­dete cÃ¡lidamente ("Hasta la prÃ³xima", "Hasta pronto", "Nos vemos en el siguiente video", o equivalente).

REGLAS:
- ESCRIBE TODO EN {lang}. NO uses inglÃ©s.
- Tono cÃ¡lido, cercano, humano â€” como un amigo, no como una mÃ¡quina.
- Oraciones CORTAS (mÃ¡ximo 20 palabras).
- NO uses markdown, viÃ±etas, listas, URLs, hashtags ni meta-texto.
- NO digas etiquetas de estructura en voz alta: nada de "primera revelaciÃ³n", "segunda revelaciÃ³n", "hook", "contexto", "desarrollo", "conclusiÃ³n", "parte uno" o "secciÃ³n dos".
- ESTRICTAMENTE PROHIBIDO escribir acotaciones: nada de "(imagen ...)", "[plano ...]", "(B-roll ...)", "(mÃºsica ...)", "(emoji ...)", "(transiciÃ³n)" etc. Solo texto hablado.
- Devuelve SOLO el texto, precedido EXACTAMENTE por la lÃ­nea: [OUTRO]
"""
        outro = _ensure_marker(_ask_section(outro_prompt, min_words=40), "[OUTRO]")
        parts.append(outro)
        info(f"   [Script] OUTRO: {len(outro.split())} words")

        full = "\n\n".join(parts).strip()
        word_count = len(full.split())

        if not full or word_count < 600:
            raise RuntimeError(f"Failed to generate long script (only {word_count} words)")

        info(f" => Sectional script built: {word_count} words (~{word_count // LONG_VIDEO_ESTIMATED_WPM} min)")
        return full

    def generate_long_metadata(self) -> dict:
        """
        Generates metadata optimized for long-form YouTube videos.
        """
        series = getattr(self, "active_series", None)
        title_template = (series or {}).get("title_template", "").strip()

        if title_template:
            # Series mode: ask the LLM only for the placeholder values, then format
            # the template ourselves. This guarantees every video in the series
            # ends up with the same title shape.
            placeholders = re.findall(r"\{(\w+)\}", title_template)
            if placeholders:
                fields_desc = ", ".join(f'"{p}"' for p in placeholders)
                raw = self.generate_response(
                    f"Vas a producir los datos para el tÃ­tulo de un video de la serie "
                    f"\"{series.get('id', '')}\".\n"
                    f"TEMA DEL VIDEO: {self.subject}\n\n"
                    f"Devuelve SOLO un objeto JSON con estos campos exactos: {fields_desc}.\n"
                    f"Cada valor debe ir en {self.language}, en MAYÃšSCULAS, sin comillas, "
                    f"sin tildes invertidas, conciso (1-4 palabras por campo), y derivado "
                    f"directamente del tema. Ejemplo de formato: {{\"rol\": \"SAMURÃI\", "
                    f"\"lugar\": \"EL JAPÃ“N FEUDAL\"}}.\n"
                    f"NO devuelvas markdown, NO devuelvas explicaciÃ³n, SOLO el JSON."
                )
                raw = str(raw).replace("```json", "").replace("```", "").strip()
                values = {}
                try:
                    values = json.loads(raw)
                except Exception:
                    m = re.search(r"\{.*\}", raw, re.DOTALL)
                    if m:
                        try:
                            values = json.loads(m.group())
                        except Exception:
                            values = {}
                # Default each missing placeholder to the subject in upper-case so
                # we never crash on a malformed LLM response.
                fallback = re.sub(r"\s+", " ", self.subject).strip().upper()
                filled = {p: str(values.get(p, fallback)).strip().upper() or fallback
                          for p in placeholders}
                title = title_template.format(**filled)
            else:
                # Template has no placeholders â†’ use it verbatim.
                title = title_template
        else:
            title = self.generate_response(
                f"Genera un tÃ­tulo para un video largo de YouTube sobre: {self.subject}.\n"
                f"REQUISITOS DEL TÃTULO:\n"
                f"- MÃ¡ximo 70 caracteres.\n"
                f"- Puede incluir opcionalmente 1 palabra en MAYÃšSCULAS para Ã©nfasis, elegida segÃºn lo que "
                f"mejor encaje con el tema especÃ­fico del video. Ejemplos de palabras vÃ¡lidas segÃºn contexto: "
                f"NUNCA, JAMÃS, NADIE, VERDAD, REAL, IMPOSIBLE, PROHIBIDO, INCREÃBLE, OLVIDADO, PERDIDO, "
                f"OCULTO, BRUTAL, EXTREMO, DEFINITIVO, ÃšNICO, ABSOLUTO, Ã‰PICO. "
                f"PROHIBIDO usar SECRETO o SECRETOS â€” estÃ¡n sobreutilizados. Elige la palabra que mejor describa "
                f"el tono real del video, no la primera que se te ocurra.\n"
                f"- Despierta curiosidad o promete una revelaciÃ³n basada en el tema real.\n"
                f"- SIN signos de exclamaciÃ³n ni de interrogaciÃ³n.\n"
                f"- SIN emojis, SIN comillas, SIN hashtags.\n"
                f"- ESCRIBE EN {self.language}.\n"
                f"Devuelve SOLO el tÃ­tulo, sin explicaciÃ³n."
            )

        # Strip any quotes the LLM might add (regular, curly, single)
        title = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', title.strip()).strip()

        # Always strip hashtags from long-video titles \u2014 the LLM ignores the rule sometimes.
        title = re.sub(r"#\w+", "", title)
        title = re.sub(r"\s{2,}", " ", title).strip(" -\u2013\u2014:|")

        if len(title) > 100:
            title = title[:100]

        description = self.generate_response(
            f"""Genera una descripciÃ³n de YouTube para un video largo con este guion:

{self.script[:2000]}

Incluye:
- Un resumen breve de 2 oraciones del video
- 5-8 hashtags relevantes
- Un llamado a la acciÃ³n (suscribirse, dar like, comentar)

NO pongas comillas alrededor de la descripciÃ³n.
ESCRIBE TODO EN {self.language}. Solo devuelve la descripciÃ³n."""
        )

        # Strip any quotes the LLM might add (regular, curly, single)
        description = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', description.strip()).strip()

        self.metadata = {"title": title, "description": description}
        return self.metadata

    def generate_thumbnail(self) -> str:
        """
        Build a clickbait 1280x720 thumbnail for the long video:
          1. LLM produces a dramatic visual prompt + 2-4 punchy overlay words.
          2. Leonardo AI renders the background.
          3. Pillow upscales to 1280x720, darkens the bottom for legibility,
             and stamps the overlay text in Impact-style with thick black stroke.
        Sets self.thumbnail_path and returns it. Returns "" if generation fails.
        """
        from PIL import Image, ImageDraw, ImageFont
        import io

        info("Generating thumbnail...")
        self.thumbnail_path = ""

        video_title = (self.metadata or {}).get("title", "") if hasattr(self, "metadata") else ""

        # Series mode: overlay text is pinned, so we skip the entire LLM-overlay
        # path and only ask the LLM for a visual prompt for the background image.
        series = getattr(self, "active_series", None)
        series_overlay = (series or {}).get("thumbnail_overlay", "").strip()

        # Build the set of allowed tokens (lowercased, accent-stripped) from title + topic.
        # Any LLM-generated overlay word must derive from this vocabulary or it gets rejected
        # (this is what catches hallucinations like "TÃQUILAS SE HOJAN").
        def _norm(s: str) -> str:
            import unicodedata
            s = unicodedata.normalize("NFKD", s.lower())
            return "".join(c for c in s if not unicodedata.combining(c))

        title_topic_text = f"{video_title} {self.subject}".lower()
        allowed_tokens = {
            _norm(t) for t in _unicode_words(title_topic_text) if len(t) > 2
        }

        visual_prompt = ""
        overlay_words = ""

        if series_overlay:
            overlay_words = series_overlay.upper()
            # Ask the LLM for a visual prompt only (no overlay words) â€” keeps the
            # series identity stable while letting the background still match the topic.
            visual_prompt = str(self.generate_response(
                f"Write a SINGLE English image-generation prompt for a YouTube thumbnail "
                f"about: {self.subject}.\n"
                f"REQUIREMENTS:\n"
                f"- 40-70 words.\n"
                f"- Describe a SPECIFIC dramatic scene tied to the topic. Name actual people, "
                f"places, objects, era, clothing, architecture or symbols. Use proper nouns "
                f"when relevant.\n"
                f"- ONE single dramatic scene, not a list of unrelated elements.\n"
                f"- Composition cues only â€” describe framing, lighting direction, depth, focus, "
                f"mood. Examples: 'dramatic side lighting', 'high contrast', 'shallow depth of "
                f"field', 'low angle', 'tense body language with the face turned away'. Style-agnostic.\n"
                f"- FACE-SAFE: avoid clear front-facing faces, portraits, selfies, beauty shots, detailed eyes, "
                f"or recognizable likenesses. If people appear, use backs, silhouettes, over-the-shoulder angles, "
                f"hands, props, helmets, hoods, smoke, shadow or foreground occlusion.\n"
                f"- DO NOT mention rendering style, medium, or technique. NEVER write "
                f"'photorealistic', 'cinematic film look', 'cartoon', 'anime', '3D render', "
                f"'watercolor', '8K', 'photograph', 'illustration', or any similar word that "
                f"locks in a visual style â€” the channel's art style is added separately.\n"
                f"- End with: no text, no letters, no logos, no watermark.\n"
                f"- Return ONLY the prompt itself. No quotes, no preamble, no explanation."
            )).strip().strip('"\'`')
            info(f"Thumbnail: using series overlay '{overlay_words}'")

        # Step 1: ask LLM for the visual concept + overlay words.
        # Skipped entirely in series mode â€” overlay is pinned and visual was
        # built above without the JSON ceremony.
        if not series_overlay:
            llm_raw = str(self.generate_response(
                f"""Design a YouTube thumbnail for this video.

VIDEO TITLE: {video_title or "(see topic)"}
TOPIC: {self.subject}

Return ONLY a JSON object with two fields:

- "visual": ENGLISH prompt (40-70 words) for an AI image generator. CRITICAL RULES:
  * The image MUST be visually unmistakable as the topic â€” name the actual SPECIFIC people, places, objects, clothing, architecture, era, or symbols from the topic. Use proper nouns when relevant.
  * Build ONE single dramatic scene, not a list of unrelated elements.
  * Composition cues only â€” describe framing, lighting direction, depth, focus, mood. Examples: "dramatic side lighting", "high contrast", "shallow depth of field", "low angle", "tense body language with the face turned away". Style-agnostic.
  * FACE-SAFE: avoid clear front-facing faces, portraits, selfies, beauty shots, detailed eyes, or recognizable likenesses. If people appear, use backs, silhouettes, over-the-shoulder angles, hands, props, helmets, hoods, smoke, shadow or foreground occlusion.
  * DO NOT mention rendering style, medium, or technique. NEVER write "photorealistic", "cinematic film look", "cartoon", "anime", "3D render", "watercolor", "8K", "photograph", "illustration", or any similar word that locks in a visual style â€” the channel's art style is added separately downstream.
  * End the prompt with: "no text, no letters, no logos, no watermark".
  * FORBIDDEN: generic phrases like "person looking", "mysterious figure", "abstract concept" â€” be SPECIFIC.

- "words": a CLICKBAIT TEASER PHRASE in {self.language}, ALL UPPERCASE, for the thumbnail overlay. ABSOLUTELY CRITICAL RULES:
  * Length: 3 to 6 words forming a COMPLETE PUNCHY PHRASE. NEVER return a single word.
  * It must SOUND like a YouTube clickbait teaser â€” provoke curiosity, hint at a revelation, or pose a question fragment. It is NOT a label.
  * It must be CLEARLY tied to the video's title or topic â€” pick the most charged, SPECIFIC words: proper names, places, dates, concrete actions, key objects.
  * EVERY WORD must already appear (literally or as a clear root form) in the VIDEO TITLE or TOPIC above. DO NOT INVENT WORDS. Each word must be a correctly-spelled real word in {self.language}.
  * VARY THE ANGLE between videos â€” pick the most specific hook from THIS topic. Available patterns (use whichever fits the topic best):
      - Proper-noun reveal: "ANUBIS Y EL JUICIO FINAL", "EL DIARIO DE TUTANKAMÃ“N".
      - Date/place anchor: "1959, EL PASO DYATLOV", "LA NOCHE DEL MARY CELESTE".
      - Question fragment: "POR QUÃ‰ DESAPARECIERON TODOS", "QUIÃ‰N ENCONTRÃ“ EL CUERPO".
      - Concrete action: "PLANTÃ“ UN BOSQUE POR ELLA", "CRUZARON LOS ANDES A PIE".
      - Revelation hook: "LO QUE ENCONTRARON ALLÃ", "NADIE VOLVIÃ“ A VERLOS".
      - Contrast/twist: "ERA UN ANCIANO CIEGO", "EL ÃšLTIMO MENSAJE DE OLOF".
  * ABSOLUTELY FORBIDDEN openings â€” never start the overlay with any of these, regardless of what the title says: "EL SECRETO", "SECRETO DE", "SECRETO QUE", "EL MISTERIO", "MISTERIO DE", "MISTERIO QUE". Even if the title contains those words, the thumbnail overlay MUST pick a different angle (a name, a place, a date, an action, a question fragment) from the patterns above. The title and the thumbnail overlay should NOT say the same thing â€” the overlay highlights a different specific hook.
  * BAD examples: "SECRETO" (single word, no teaser), "NADIE LO SABE" (clichÃ©), "INCREÃBLE" (generic), "EL SECRETO DE X" / "EL MISTERIO DE X" (forbidden openings â€” too generic).
  * AVOID these overused clichÃ©s entirely: "NADIE LO SABE", "NUNCA LO SABE", "TE VA A IMPACTAR", "INCREÃBLE", "JAMÃS LO CREERÃS".

Return ONLY the JSON. No markdown, no explanation."""
            )).replace("```json", "").replace("```", "").strip()

            try:
                data = json.loads(llm_raw)
                visual_prompt = str(data.get("visual", "")).strip()
                overlay_words = str(data.get("words", "")).strip().upper()
            except Exception:
                match = re.search(r"\{.*\}", llm_raw, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group())
                        visual_prompt = str(data.get("visual", "")).strip()
                        overlay_words = str(data.get("words", "")).strip().upper()
                    except Exception:
                        pass

            BANNED_OVERLAYS = {
                "NADIE LO SABE", "NUNCA LO SABE", "TE VA A IMPACTAR",
                "INCREÃBLE", "INCREIBLE", "JAMÃS LO CREERÃS", "JAMAS LO CREERAS",
            }

            # The LLM keeps defaulting to "EL SECRETO DE ..." / "EL MISTERIO DE ..."
            # for almost every video. Reject those openings unconditionally â€”
            # the overlay must pick a more specific angle even when the title
            # itself uses those words.
            FORBIDDEN_OVERLAY_PREFIXES = (
                "el secreto", "secreto de", "secreto que",
                "el misterio", "misterio de", "misterio que",
            )

            def _validate_overlay(candidate: str) -> bool:
                """Reject if too short, banned, lazy-default, or hallucinated."""
                if not candidate:
                    return False
                if candidate in BANNED_OVERLAYS:
                    return False
                norm_cand = _norm(candidate)
                if any(norm_cand.startswith(p) for p in FORBIDDEN_OVERLAY_PREFIXES):
                    return False
                STOP = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "o",
                        "que", "por", "para", "con", "en", "a", "su", "sus", "lo"}
                words = [_norm(w) for w in _unicode_words(candidate)]
                # Reject one-word overlays â€” clickbait needs a phrase.
                if len(words) < 3:
                    return False
                content_words = [w for w in words if w not in STOP]
                if not content_words:
                    return False
                for w in content_words:
                    if not any(w == a or w in a or a in w for a in allowed_tokens):
                        return False
                return True

            if overlay_words and not _validate_overlay(overlay_words):
                warning(f"Thumbnail: LLM overlay '{overlay_words}' rejected (hallucinated, banned, or lazy default).")
                overlay_words = ""

        if not visual_prompt:
            # Style-neutral fallback â€” composition cues only. The channel's art
            # style is appended downstream by `_apply_channel_style`, so this
            # prompt MUST NOT lock in a rendering medium ("cinematic",
            # "photorealistic", etc.) that would fight cartoon/anime channels.
            visual_prompt = (
                f"Dramatic face-safe scene related to {self.subject}, "
                f"hands, symbolic objects, or a subject turned away from camera, dramatic side lighting, "
                f"dark moody background, high contrast, no text"
            )

        # Deterministic fallback path (always coherent with title â€” never hallucinates).
        # Helper used by every fallback path below â€” strips accents and matches
        # SECRETO/SECRETOS/MISTERIO/MISTERIOS so we can drop those words wherever
        # they appear, regardless of source.
        def _is_secreto_misterio(word: str) -> bool:
            """True for SECRETO/SECRETOS/MISTERIO/MISTERIOS (any case, with or without accents)."""
            w = re.sub(r"[ÃÃ‰ÃÃ“ÃšÃœÃ¡Ã©Ã­Ã³ÃºÃ¼]", lambda m: {
                "Ã": "A", "Ã‰": "E", "Ã": "I", "Ã“": "O", "Ãš": "U", "Ãœ": "U",
                "Ã¡": "a", "Ã©": "e", "Ã­": "i", "Ã³": "o", "Ãº": "u", "Ã¼": "u",
            }[m.group()], word).upper()
            return w in {"SECRETO", "MISTERIO", "SECRETOS", "MISTERIOS"}

        if not overlay_words and video_title:
            clean_title = re.sub(r"[Â¿?Â¡!,.:;\"'â€œâ€â€˜â€™]", "", video_title).strip()
            tw = clean_title.split()
            STOP = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "o",
                    "que", "por", "quÃ©", "para", "con", "en", "a", "su", "sus", "lo"}

            # 1. Find UPPERCASE keyword (the title generator always puts 1-2 in caps) and
            #    grab a wider window around it for a proper teaser phrase (3-5 words).
            #    Skip SECRETO / MISTERIO so the overlay doesn't keep defaulting
            #    to "EL SECRETO DE X" â€” pick the next caps word if there is one.
            CAPS_SKIP = {"SECRETO", "MISTERIO", "SECRETOS", "MISTERIOS"}

            def _is_caps_keyword(word: str) -> bool:
                parts = _unicode_words(word)
                if len(parts) != 1:
                    return False
                token = parts[0]
                return (
                    len(token) >= 4
                    and token.upper() == token
                    and _norm(token).upper() not in CAPS_SKIP
                )

            caps_idx = next(
                (i for i, w in enumerate(tw) if _is_caps_keyword(w)),
                None,
            )

            if caps_idx is not None:
                start = max(0, caps_idx - 2)
                end = min(len(tw), caps_idx + 4)
                chunk = tw[start:end]
                # Drop SECRETO/MISTERIO from the chunk â€” we never want them on a thumbnail.
                chunk = [w for w in chunk if not _is_secreto_misterio(w)]
                while chunk and chunk[0].lower() in STOP:
                    chunk = chunk[1:]
                while chunk and chunk[-1].lower() in STOP:
                    chunk = chunk[:-1]
                # Cap at 5 words to keep it readable on a thumbnail.
                if len(chunk) > 5:
                    chunk = chunk[:5]
                # Need at least 3 words for a real teaser phrase.
                if len(chunk) >= 3:
                    overlay_words = " ".join(chunk).upper()

            # 2. No usable caps window â†’ take the first 4-5 meaningful words from the title.
            if not overlay_words:
                meaningful = [
                    w for w in tw
                    if w.lower() not in STOP and len(w) > 2
                    and not _is_secreto_misterio(w)
                ]
                if len(meaningful) >= 3:
                    overlay_words = " ".join(meaningful[:5]).upper()

            if overlay_words:
                warning(f"Thumbnail: derived overlay from title: {overlay_words}")

        # Absolute fallback so the thumbnail is never wordless.
        if not overlay_words:
            STOP = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "o",
                    "que", "por", "quÃ©", "para", "con", "en", "a"}
            topic_words = [
                w for w in _unicode_words(self.subject or "")
                if w.lower() not in STOP and len(w) > 3
                and not _is_secreto_misterio(w)
            ][:5]
            overlay_words = " ".join(topic_words).upper() if topic_words else "DESCUBRE LA VERDAD"
            warning(f"Thumbnail: using topic-derived overlay text: {overlay_words}")

        # Step 2: render the background image.
        # Append the channel's image_style suffix so the thumbnail matches the video's look.
        styled_visual_prompt = self._apply_channel_style(visual_prompt)
        if get_verbose() and styled_visual_prompt != visual_prompt:
            info(" => Thumbnail: applied channel art style")

        bg_bytes = None
        thumb_providers = [
            (name, fn)
            for name, fn, _kind in self._ai_image_providers(1280, 720)
        ]
        for name, fn in thumb_providers:
            try:
                bg_bytes = fn(styled_visual_prompt)
                if bg_bytes and len(bg_bytes) > 5000:
                    break
                bg_bytes = None
            except Exception as e:
                if get_verbose():
                    warning(f"Thumbnail bg via {name} failed: {str(e)[:120]}")
                bg_bytes = None

        THUMB_W, THUMB_H = 1280, 720

        if bg_bytes:
            bg = Image.open(io.BytesIO(bg_bytes)).convert("RGB").resize(
                (THUMB_W, THUMB_H), Image.LANCZOS
            )
        else:
            warning("Thumbnail providers all failed; using gradient background.")
            bg = Image.new("RGB", (THUMB_W, THUMB_H))
            d = ImageDraw.Draw(bg)
            for y in range(THUMB_H):
                t = y / THUMB_H
                d.line(
                    [(0, y), (THUMB_W, y)],
                    fill=(int(20 + 80 * t), int(10 + 30 * t), int(60 + 90 * t)),
                )

        # Step 3: darken the bottom-LEFT corner so the overlay reads well there.
        # Combine a vertical "bottom darker" gradient with a horizontal "left darker" one,
        # giving a corner-vignette feel that protects the right-side image content.
        import numpy as np
        veil_start_y = int(THUMB_H * 0.45)
        veil_end_x = int(THUMB_W * 0.70)
        ys = np.arange(THUMB_H).reshape(-1, 1).astype(np.float32)
        xs = np.arange(THUMB_W).reshape(1, -1).astype(np.float32)
        v_factor = np.clip((ys - veil_start_y) / max(1, THUMB_H - veil_start_y), 0.0, 1.0)
        h_factor = np.clip(1.0 - (xs / max(1, veil_end_x)), 0.0, 1.0)
        alpha_field = (210.0 * v_factor * h_factor).astype(np.uint8)
        veil_arr = np.zeros((THUMB_H, THUMB_W, 4), dtype=np.uint8)
        veil_arr[..., 3] = alpha_field
        veil = Image.fromarray(veil_arr, "RGBA")
        bg = Image.alpha_composite(bg.convert("RGBA"), veil).convert("RGB")

        # Step 4: stamp overlay text in the BOTTOM-LEFT, left-aligned (Impact font for clickbait look).
        if overlay_words:
            font_path = None
            series_font = (series or {}).get("thumbnail_font", "").strip()
            font_candidates = []
            if series_font:
                # Series-specific font wins. Accept either an absolute path, a
                # bare filename in C:\Windows\Fonts, or a name in fonts/.
                if os.path.isabs(series_font):
                    font_candidates.append(series_font)
                else:
                    font_candidates.append(os.path.join(r"C:\Windows\Fonts", series_font))
                    font_candidates.append(os.path.join(get_fonts_dir(), series_font))
            font_candidates.extend([
                r"C:\Windows\Fonts\impact.ttf",
                r"C:\Windows\Fonts\arialbd.ttf",
                os.path.join(get_fonts_dir(), get_font()),
            ])
            for cand in font_candidates:
                if cand and os.path.isfile(cand):
                    font_path = cand
                    break

            # Wrap the overlay so each line fits within ~55% of the width (left half + a bit).
            margin_left = 60
            margin_right = THUMB_W - int(THUMB_W * 0.42)  # right edge of text area
            max_w = margin_right - margin_left

            def _wrap(text: str, fnt) -> list:
                """Greedy word-wrap so no line exceeds max_w pixels."""
                wrapped, current = [], []
                tmp_draw = ImageDraw.Draw(bg)
                for w in text.split():
                    trial = " ".join(current + [w])
                    if tmp_draw.textbbox((0, 0), trial, font=fnt)[2] <= max_w:
                        current.append(w)
                    else:
                        if current:
                            wrapped.append(" ".join(current))
                        current = [w]
                if current:
                    wrapped.append(" ".join(current))
                return wrapped

            # Pick the largest font size where the wrapped text fits in â‰¤3 lines.
            font_size = 130
            font = None
            lines = [overlay_words]
            while font_size >= 50:
                try:
                    font = (
                        ImageFont.truetype(font_path, font_size)
                        if font_path else ImageFont.load_default()
                    )
                except Exception:
                    font = ImageFont.load_default()
                lines = _wrap(overlay_words, font)
                if len(lines) <= 3:
                    break
                font_size -= 8

            draw = ImageDraw.Draw(bg)
            line_h = int(font_size * 1.05)
            total_h = line_h * len(lines)
            margin_bottom = 50
            y = THUMB_H - total_h - margin_bottom
            for line in lines:
                draw.text(
                    (margin_left, y), line, font=font,
                    fill=(255, 255, 255),
                    stroke_width=10, stroke_fill=(0, 0, 0),
                )
                y += line_h

        # Save to a persistent directory OUTSIDE .mp/ so rem_temp_files() doesn't wipe it.
        # This way, even if the auto-upload to YT fails, the file is still on disk for
        # manual recovery via YouTube Studio.
        thumbs_dir = os.path.join(ROOT_DIR, "thumbnails")
        os.makedirs(thumbs_dir, exist_ok=True)
        out_path = os.path.join(thumbs_dir, f"thumb_{uuid4()}.png")
        bg.save(out_path, "PNG")
        self.thumbnail_path = out_path
        success(f" Thumbnail: {out_path}")
        return out_path

    # Per-prompt diversity controls for `generate_long_prompts`. Indexed
    # modulo the array length and offset so that consecutive prompts never
    # share shot type AND lighting at the same time â€” image generators
    # otherwise default to "wide dramatic vista in golden hour" for every
    # frame, which is what made long videos look generic.
    _LONG_SHOT_TYPES: list[str] = [
        "tight detail of hands, clothing and the key object â€” face outside the frame, shallow background",
        "medium shot of subject mid-action â€” hands and gesture clearly visible, environment partly framed",
        "wide establishing shot â€” subject placed within the full setting, scale of the world visible",
        "low-angle hero shot â€” subject filling the frame from below, sky or ceiling behind",
        "over-the-shoulder POV â€” viewer sees what the subject is looking at, back of subject's head/shoulder in foreground",
        "profile silhouette â€” subject lit from behind against a bright background, edge light defining the body",
        "two-shot â€” two characters interacting through a shared object, both faces hidden or turned away",
        "overhead / top-down â€” subject(s) seen from directly above, environment as a flat backdrop",
    ]
    _LONG_LIGHTING: list[str] = [
        "golden hour â€” warm orange light, long shadows raking across the scene",
        "stormy overcast â€” cold gray diffuse light, rain or fog visible, drained colors",
        "candlelight or firelight â€” small warm pool of light, deep shadows, flicker",
        "harsh midday sun â€” sharp high-contrast shadows, bleached highlights",
        "single interior lamp or lantern â€” warm pool of light, surrounding darkness",
        "dawn fog â€” cold blue-gray atmosphere, low visibility, silhouettes",
        "twilight blue hour â€” deep blue sky, subjects lit by a secondary warm source",
        "flat soft overcast â€” even illumination, no shadows, muted palette",
    ]

    @staticmethod
    def _narrative_beat_for(index: int, total: int) -> tuple[str, str]:
        """
        Map a 0-indexed prompt position to a narrative beat + mood hint.
        Drives emotional variation across the video: cold-open energy at the
        front, climax peak ~85% in, contemplative legacy at the end.
        """
        pos = index / max(1, total)
        if pos < 0.10:
            return ("cold-open hook", "cinematic awe, dramatic lighting, EPIC scale, faces hidden by silhouette or framing, the moment that opens the video")
        if pos < 0.20:
            return ("immersive vignette", "sensorial â€” viewer is INSIDE the scene, vivid textures, dust/breath/sweat visible, intimate framing")
        if pos < 0.30:
            return ("mystery pivot", "ominous â€” something is off, doubt shown through posture and hesitation, off-kilter framing, cold or dim light")
        if pos < 0.42:
            return ("first revelation + backstory", "discovery energy, hands uncovering or inspecting, warm light revealing a detail, faces outside the frame")
        if pos < 0.55:
            return ("escalation", "rising tension, motion blur, conflict, sweat / breath / urgency, strain shown through shoulders and hands")
        if pos < 0.68:
            return ("reversal", "shock or realization shown through posture and frozen gestures, hard contrast, the moment the truth lands")
        if pos < 0.78:
            return ("human element", "intimate emotion â€” grief, joy, fear, awe â€” tight on hands, clothing, personal objects, vulnerable framing with face hidden")
        if pos < 0.90:
            return ("climax â€” peak intensity", "MOST DRAMATIC of the video, peak intensity, the revelation moment, bodies frozen in awe or horror, strongest composition, faces obscured")
        return ("legacy / contemplation", "contemplative, quiet, soft warm lighting, a single subject, reflective stillness")

    def generate_long_prompts(self) -> List[str]:
        """
        Generates 30 image prompts for a long video, anchored to the script:
        the script is split into N chunks and each prompt MUST illustrate its
        chunk literally, naming the people / places / objects from the topic.

        Anti-generic mechanisms (in order of impact):
          1. Anchor noun rule â€” every prompt must contain â‰¥1 proper noun
             from the chunk or the topic title.
          2. Forbidden generic phrases â€” explicit blacklist of clichÃ©s
             ("a figure", "ancient ruins", "dramatic landscape" â€¦).
          3. Per-prompt shot type + lighting hints (rotated so consecutive
             frames never share both axes).
          4. Per-prompt narrative beat hint (cold-open / mystery / climax / â€¦)
             so emotional energy tracks the script position.
          5. 800-char chunk window (was 400) so the LLM has enough source
             material to lift specific details instead of inventing them.
        """
        n_prompts = 30

        # Extract proper-noun anchors from the topic title â€” these are the
        # fallback names when a script chunk has no named entity of its own.
        # Lowercased connectors filtered so we keep only meaningful tokens.
        _topic_anchors = [
            tok for tok in _unicode_tokens(self.subject or "")
            if len(tok) > 2 and tok.lower() not in _PHOTO_STOPWORDS
        ]
        topic_anchor_str = ", ".join(_topic_anchors[:6]) or (self.subject or "the topic")

        # Split the script into N chunks. 800-char window (up from 400) gives
        # the LLM enough material to extract specific details, not just gist.
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', self.script) if s.strip()]
        sections = []
        if sentences:
            per_section = max(1, len(sentences) // n_prompts)
            for i in range(n_prompts):
                start = i * per_section
                end = start + per_section if i < n_prompts - 1 else len(sentences)
                section_text = ' '.join(sentences[start:end])[:800]
                if section_text:
                    sections.append(section_text)
        while len(sections) < n_prompts:
            sections.append(self.subject)

        # Per-prompt diversity assignments. Shot rotates 1-step, lighting
        # rotates 3-step â†’ never sync, never repeat consecutively.
        shot_idx = lambda i: i % len(self._LONG_SHOT_TYPES)
        light_idx = lambda i: (i * 3) % len(self._LONG_LIGHTING)

        sections_text = ""
        for i, sec in enumerate(sections):
            beat_name, beat_mood = self._narrative_beat_for(i, n_prompts)
            sections_text += (
                f'\nSECTION {i+1}\n'
                f'  Narrative beat: {beat_name}\n'
                f'  Mood/emotion to convey: {beat_mood}\n'
                f'  Shot type for this image: {self._LONG_SHOT_TYPES[shot_idx(i)]}\n'
                f'  Lighting for this image: {self._LONG_LIGHTING[light_idx(i)]}\n'
                f'  Script chunk to illustrate: "{sec}"\n'
            )

        # Setting anchor â€” names the world/era of THIS video inside the prompt
        # so the LLM doesn't drift into off-setting visuals on abstract script
        # lines. Niche-agnostic: works for history, modern, sports, food, tech,
        # etc. (see `_get_context_profile`).
        ctx = self._get_context_profile()
        era_clause = ""
        if ctx and (ctx.get("setting") or ctx.get("visual_anchors")):
            setting_line = ctx.get("setting") or "(see niche)"
            anchors_line = ctx.get("visual_anchors") or "(infer from topic)"
            avoid_line = ctx.get("must_avoid") or "anything that breaks the setting's immersion"
            era_clause = (
                f"\n\n=== SETTING â€” NON-NEGOTIABLE ===\n"
                f"This documentary is set in: **{setting_line}**.\n"
                f"Visual anchors that should appear naturally when relevant: {anchors_line}.\n"
                f"FORBIDDEN visual elements (anachronistic / off-setting): {avoid_line}.\n"
                f"REQUIRED in every prompt with a person: clothing, props and architecture that belong to the setting above; faces must be hidden, turned away, cropped out, shadowed, veiled or otherwise non-identifiable.\n"
                f"=========================================="
            )

        period_inline = (
            f"Setting is **{ctx['setting']}**. Every prompt with a person MUST name at least 2 specific clothing/prop items that belong to this setting, and AVOID: {ctx.get('must_avoid', '')}. "
            if (ctx and ctx.get("setting")) else ""
        )

        visual_retention = CosmicRetentionEngine.visual_retention_directive(
            self.subject,
            self.niche,
        )

        prompt = f"""Task: write {n_prompts} image prompts for a long-form video about "{self.subject}".{era_clause}
{visual_retention}

You receive {n_prompts} script chunks below, each tagged with a narrative beat, shot type and lighting. Each prompt MUST illustrate the LITERAL content of its chunk â€” the people, the action, the place, the moment that chunk describes. The shot type and lighting tags are NON-OPTIONAL: bake them into the prompt so the {n_prompts} images don't look identical.

ABSOLUTE RULES (every prompt):
1. ENGLISH ONLY â€” NON-NEGOTIABLE. Write every prompt entirely in English, even if the script is in Spanish. Image generators are trained on English data and produce wrong subjects when given Spanish prompts. Translate proper nouns naturally. NO Spanish words anywhere in the output.

2. ANCHOR NOUN â€” STRICT. Every prompt MUST contain at least ONE specific proper noun: a real person's name, a specific place name, a specific object/artifact, a specific event, or a specific date drawn from the chunk text. If the chunk has none, lift one from the topic title: **{topic_anchor_str}**. NEVER write a prompt with only generic subjects.

3. NO GENERIC SUBJECTS. The following phrasings are FORBIDDEN and will cause the prompt to be discarded:
   - "a person", "a figure", "someone", "a man", "a woman", "an individual" â€” alone, with no name AND no 3+ physical traits
   - "a warrior", "a scientist", "a soldier", "a king", "a priest" â€” alone, without name AND specific period clothing
   - "a person standing", "a figure looking", "a figure in the distance", "a silhouette"
   - "ancient temple", "ancient ruins", "ancient city", "ancient civilization" â€” without naming WHICH
   - "dramatic landscape", "epic scene", "mysterious place", "ancient times", "a historical moment"
   - "a moment in history", "a turning point", "a key event", "a fateful day"
   - "symbolic", "metaphorical", "conceptual" visuals â€” only describe LITERAL scenes.

4. SCENE FIDELITY. Open with a concrete action (subject + verb) drawn from the chunk text. If the chunk says "Galileo demonstrates his telescope to the cardinals at night", the image is exactly that â€” not "an astronomer in a robe".

5. FACE-SAFE PEOPLE. Avoid people entirely when a landscape, artifact, spacecraft, building, document, tool, map or environment can carry the idea. When people are necessary, keep them non-identifiable: back view, over-the-shoulder, profile silhouette, face turned away, cropped outside the frame, hidden by shadow, helmet, veil, hood, smoke, documents, hands, tools or foreground objects. NEVER request a clear front-facing face, portrait, selfie, beauty shot, detailed eyes, or recognizable likeness.

6. NAMED CHARACTER IDENTITY WITHOUT LIKENESS. When the script names a real person, do NOT ask for their face or likeness. Anchor them through clothing, era, location, action, posture and objects instead (for example, "Galileo's hands adjusting a brass telescope beside candlelit papers, his face hidden in shadow"). The name can appear in the prompt for story anchoring, but the visual must not show an identifiable face.

7. SETTING ACCURACY â€” STRICT. {period_inline}If a person appears, describe their clothing exactly as it would look in the setting (fabric, cut, color, footwear, headwear). Same for architecture, tools, vehicles and 2-3 supporting objects.

8. SHOT + LIGHTING â€” USE THE TAGS. Each chunk below has a "Shot type" and "Lighting" tag. The prompt must clearly reflect that shot type and that lighting. If one chunk uses a tight detail under candlelight, the next must vary framing and light.

9. NARRATIVE BEAT â€” USE THE MOOD TAG. Each chunk has a "Mood/emotion to convey" tag tied to its position in the video. A prompt for the "cold-open hook" beat must read cinematic and high-impact; a prompt for the "human element" beat must read intimate and emotional through hands, posture, personal objects or distance between bodies; a prompt for the "climax" beat must be the MOST DRAMATIC of all.

10. CONSISTENT REALISM. All {n_prompts} prompts describe the SAME world â€” same realism level, same physical universe. No image should feel like it comes from a different show. Vary action, time of day, framing â€” but never the level of realism.

11. NO ART STYLE WORDS. Describe SCENES ONLY. Never write "painting", "illustration", "cartoon", "anime", "drawing", "vector", "3D render", "ukiyo-e", "fresco", "engraving", "comic", "pixel art" or any other medium/aesthetic label. The visual look is decided by a suffix appended later â€” your job is content only.

12. LENGTH. 55-90 English words per prompt. No camera or lens jargon ("close-up" as written text is fine; "85mm f/1.4" is not).

Examples of GOOD scene-only prompts (the PATTERN matters â€” names and props will differ for your topic):
- (Historical setting, no visible face) "Caesar in a red cloak crosses the shallow Rubicon at dusk on a black warhorse, seen from behind with his hooded head turned away, his legion wading behind him in lorica segmentata armor with rectangular shields and silver eagle standards, low hills on the horizon, tense posture, low-angle hero composition, golden hour."
- (Modern setting) "A young trader leans over three glowing monitors on the floor of the New York Stock Exchange, mouth open mid-shout, paper tickets crumpled on his keyboard, the index ticker spiking red overhead, colleagues running behind him, tight medium shot, harsh fluorescent overhead light."
- (Sports setting) "A quarterback in a navy and red jersey throws a tight spiral over the defensive line under stadium floodlights, mud streaking his white pants, breath visible in cold air, tens of thousands of blurred fans behind the end zone, low-angle hero shot, sodium floodlight."
- (Science / probe) "The Voyager 1 probe, gold-foiled and antenna-extended, drifts past the dark crescent of Saturn's rings, faint sunlight glancing off its main dish, the rings casting a black band across the planet, profile silhouette composition, harsh sunlight from the right."

Examples of BAD prompts (DO NOT WRITE THESE â€” they will be rejected):
- "An ancient scene at sunset." (vague, no name, no action)
- "A historical illustration of [subject]." (forbidden art-style word, generic)
- "Symbolic image of [subject]'s power." (no concrete moment)
- "A warrior standing in ancient ruins." (forbidden generics: 'a warrior' + 'ancient ruins')
- "A figure looking at the horizon at golden hour." (forbidden generic 'a figure')

{sections_text}
Forbidden art-style words: cinematic, photograph, camera, shot, lens, close-up jargon, 4K, 8K, HD, render, abstract, concept, metaphor, symbolic, visualization, painting, illustration, cartoon, drawing, anime, fresco, engraving, comic, vector, sketch.
Forbidden multi-image triggers: series, sequence, scenes (plural), panels, panel, storyboard, comic strip, montage, collage, grid, split screen, frames, multiple, diptych, triptych, before-and-after, side by side.
Also forbidden unless the topic itself demands it: medieval/ancient-civilization imagery, fantasy creatures, magic/sorcery effects, cartoon stylization.

Return ONLY a JSON array of {n_prompts} strings (one prompt per section, in order). Example format:
["scene 1 description...", "scene 2 description...", ...]
No markdown. No explanation. Just the JSON array."""

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        def _extract_prompts_long(parsed_value):
            out = []
            if isinstance(parsed_value, list):
                for item in parsed_value:
                    if isinstance(item, str):
                        out.append(item)
                    elif isinstance(item, dict):
                        p = item.get("prompt") or item.get("image_prompt") or ""
                        moment = item.get("moment") or item.get("key_visual_moment") or ""
                        if p:
                            out.append(str(p))
                        elif moment:
                            out.append(str(moment))
            return out

        image_prompts = []
        try:
            parsed = json.loads(completion)
            image_prompts = _extract_prompts_long(parsed)
        except Exception:
            match = re.search(r'\[.*\]', completion, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    image_prompts = _extract_prompts_long(parsed)
                except Exception:
                    pass

        # Fallback: build a specific, anchored prompt per chunk so images stay
        # both on-topic AND varied even when the LLM fails to return JSON.
        # Uses the same shot/lighting/beat rotation as the LLM path so the
        # video still feels visually intentional, not random.
        if not image_prompts or len(image_prompts) < 4:
            if get_verbose():
                warning("Failed to parse long video prompts, using anchored fallback")
            setting_str = (ctx or {}).get("setting", "") or self.subject
            avoid_str = (ctx or {}).get("must_avoid", "")
            image_prompts = []
            for i in range(n_prompts):
                chunk = sections[i] if i < len(sections) else self.subject
                # Pick a named entity from the chunk if any, else fall back to topic anchors
                chunk_nouns = [
                    tok for tok in _capitalized_unicode_tokens(chunk)
                    if tok.lower() not in _PHOTO_STOPWORDS
                ]
                anchor = chunk_nouns[0] if chunk_nouns else (_topic_anchors[0] if _topic_anchors else self.subject)
                beat_name, beat_mood = self._narrative_beat_for(i, n_prompts)
                shot = self._LONG_SHOT_TYPES[shot_idx(i)]
                light = self._LONG_LIGHTING[light_idx(i)]
                image_prompts.append(
                    f"{anchor} in a concrete scene from {setting_str}: {chunk[:220]}. "
                    f"Shot: {shot}. Lighting: {light}. Mood: {beat_mood}. "
                    f"Period-accurate clothing, props and architecture. "
                    f"Avoid: {avoid_str or 'generic landscape, symbolic imagery, cartoon stylization'}. "
                    f"16:9 landscape."
                )

        image_prompts = image_prompts[:n_prompts]
        self.image_prompts = image_prompts

        if get_verbose():
            info(f" => Generated {len(image_prompts)} long video image prompts")

        return image_prompts

    def _try_leonardo_landscape(self, prompt: str) -> bytes:
        """Try Leonardo AI API in 16:9 landscape format for long videos."""
        from config import get_leonardo_api_key
        api_key = get_leonardo_api_key()
        if not api_key:
            raise RuntimeError("Leonardo AI API key not configured")

        print(colored(f"    [Leonardo AI 16:9] Generating...", "cyan"), flush=True)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt[:1500],
            "modelId": "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3",  # Leonardo Phoenix 1.0
            "width": 1024,
            "height": 576,
            "num_images": 1,
            "contrast": 3.5,
            "alchemy": True,
        }
        style_text = (self._image_style or "").lower()
        if any(k in style_text for k in ("cartoon", "anime", "illustration", "animated", "cel shading", "hand-drawn")):
            payload["presetStyle"] = "ILLUSTRATION"
        elif any(k in style_text for k in ("cinematic", "film", "movie")):
            payload["presetStyle"] = "CINEMATIC"
        elif self._image_style:
            payload["presetStyle"] = "DYNAMIC"
        resp = requests.post(
            "https://cloud.leonardo.ai/api/rest/v1/generations",
            headers=headers, json=payload, timeout=30,
        )
        resp.raise_for_status()
        gen_id = resp.json().get("sdGenerationJob", {}).get("generationId", "")
        if not gen_id:
            raise RuntimeError("Leonardo: no generation ID returned")

        for _ in range(30):
            time.sleep(5)
            status_resp = requests.get(
                f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}",
                headers=headers, timeout=15,
            )
            status_resp.raise_for_status()
            gen = status_resp.json().get("generations_by_pk", {})
            status = gen.get("status", "")
            if status == "COMPLETE":
                images = gen.get("generated_images", [])
                if images:
                    img_url = images[0].get("url", "")
                    img_resp = requests.get(img_url, timeout=60)
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        print(colored("OK", "green"))
                        return img_resp.content
                raise RuntimeError("Leonardo: no image in result")
            elif status == "FAILED":
                raise RuntimeError("Leonardo: generation failed")
        raise RuntimeError("Leonardo: timeout waiting for generation")

    def generate_long_images(self, prompts: List[str]) -> None:
        """
        Generate images for long video in 16:9 landscape format (1920x1080).
        Cascade: Leonardo AI â†’ HuggingFace â†’ Pillow fallback.
        """
        print(colored(f"\n  [Long Video] Generating {len(prompts)} images (1920x1080)...", "blue"))

        for i, prompt in enumerate(prompts):
            print(colored(f"\n  Image {i+1}/{len(prompts)}", "blue"))
            saved = False

            # Apply per-channel style suffix to AI prompts.
            styled_prompt = self._apply_channel_style(prompt)

            providers = [
                (name, fn)
                for name, fn, _kind in self._ai_image_providers(1920, 1080)
            ]
            for name, fn in providers:
                try:
                    img_bytes = fn(styled_prompt)
                    if img_bytes and len(img_bytes) > 1000:
                        self._persist_image(img_bytes, name)
                        saved = True
                        break
                except Exception as e:
                    if get_verbose():
                        warning(f"    {name} failed: {str(e)[:100]}")
                    time.sleep(1)

            if not saved:
                self._generate_fallback_image_landscape(prompt)

        success(f"All {len(self.images)} long video images ready!")

    def _generate_fallback_image_landscape(self, prompt: str) -> str:
        """Fallback landscape image (1920x1080) when all providers fail."""
        from PIL import Image, ImageDraw, ImageFont
        import random as rand_mod

        if get_verbose():
            warning("All providers failed. Creating styled fallback image (landscape)...")

        color_schemes = [
            ((15, 15, 80), (80, 20, 120)),
            ((10, 50, 80), (20, 100, 100)),
            ((60, 10, 60), (120, 30, 80)),
            ((10, 40, 20), (30, 100, 60)),
        ]
        c1, c2 = rand_mod.choice(color_schemes)
        img = Image.new("RGB", (1920, 1080))
        draw = ImageDraw.Draw(img)

        for y in range(1080):
            r = int(c1[0] + (c2[0] - c1[0]) * y / 1080)
            g = int(c1[1] + (c2[1] - c1[1]) * y / 1080)
            b = int(c1[2] + (c2[2] - c1[2]) * y / 1080)
            draw.line([(0, y), (1920, y)], fill=(r, g, b))

        try:
            font_path = os.path.join(get_fonts_dir(), get_font())
            font = ImageFont.truetype(font_path, 48)
        except Exception:
            font = ImageFont.load_default()

        words = prompt.split()
        text_lines, current_line = [], ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if len(test) > 45:
                text_lines.append(current_line)
                current_line = word
            else:
                current_line = test
        if current_line:
            text_lines.append(current_line)

        y_pos = 1080 // 2 - (len(text_lines) * 60) // 2
        for line in text_lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            draw.text(((1920 - w) // 2 + 3, y_pos + 3), line, fill=(0, 0, 0), font=font)
            draw.text(((1920 - w) // 2, y_pos), line, fill="white", font=font)
            y_pos += 60

        image_path = os.path.join(get_temp_cache_path(), str(uuid4()) + ".png")
        img.save(image_path)
        self.images.append(image_path)
        return image_path

    # Patterns that mean "this line is metadata / API junk / not narration".
    # If a line matches ANY of these, it gets dropped before TTS.
    _GARBAGE_LINE_PATTERNS = [
        re.compile(r"https?://", re.IGNORECASE),
        re.compile(r"\bwww\.[a-z]", re.IGNORECASE),
        re.compile(r"\b[\w.-]+\.(?:com|org|net|io|ai|gov|edu|co|es)\b", re.IGNORECASE),
        re.compile(r"^\s*[\{\}\[\]<>]+\s*$"),
        re.compile(r"^\s*[#/!*=\-]{3,}\s*$"),
        re.compile(r"^\s*```"),
        re.compile(r"^\s*<[/!?]?[a-z][^>]*>\s*$", re.IGNORECASE),
        re.compile(r"\b(?:guion[\s-]?bajo|barra[\s-]?baja|underscore|forward[\s-]?slash|backslash|asterisk|asterisco)\b", re.IGNORECASE),
        re.compile(r"\b(?:generating|generando|loading|cargando)\s+(?:script|content|response|el\s+\w+)\b", re.IGNORECASE),
        re.compile(r"\b(?:please\s+(?:try\s+again|retry|wait)|por\s+favor\s+(?:intenta|reintente|espere))\b", re.IGNORECASE),
        re.compile(r"\b(?:api[\s_-]?(?:key|token|endpoint|response|error|call))\b", re.IGNORECASE),
        re.compile(r"\b(?:status[\s_-]?code|error[\s_-]?code|http\s*\d{3})\b", re.IGNORECASE),
        re.compile(r"\b(?:404|429|500|502|503)\b\s+(?:not\s+found|error|too\s+many|internal|bad\s+gateway|unavailable)", re.IGNORECASE),
        re.compile(r"\b(?:role|content|model|message|completion|payload|tokens?|prompt)\s*[:=]\s*[\"']?[A-Za-z]"),
        re.compile(r"\{\s*[\"']\w+[\"']\s*:"),
        re.compile(r"^\s*\w+_\w+(?:_\w+)*\s*$"),
        re.compile(r"^\s*[A-Z_]{4,}(?:\s+[A-Z_]{4,}){0,2}\s*$"),
        re.compile(r"\bI\s+(?:am|will|cannot|can'?t)\s+(?:generate|provide|continue|create|write)\b", re.IGNORECASE),
        re.compile(r"\b(?:no\s+puedo|lo\s+siento,)\s+(?:generar|continuar|crear|proveer)\b", re.IGNORECASE),
    ]

    @classmethod
    def _filter_garbage_lines(cls, text: str) -> tuple:
        """Drop lines that look like metadata / URLs / system messages. Returns (clean_text, dropped_count)."""
        kept, dropped = [], 0
        for line in text.split("\n"):
            if line.strip() and any(p.search(line) for p in cls._GARBAGE_LINE_PATTERNS):
                dropped += 1
                continue
            kept.append(line)
        return "\n".join(kept), dropped

    @classmethod
    def _looks_like_garbage(cls, text: str) -> bool:
        """Heuristic: is the LLM response dominated by metadata / non-narration?"""
        if not text or len(text.split()) < 30:
            return True
        # If >25% of non-empty lines are garbage, the output is unusable.
        lines = [ln for ln in text.split("\n") if ln.strip()]
        if not lines:
            return True
        bad = sum(1 for ln in lines if any(p.search(ln) for p in cls._GARBAGE_LINE_PATTERNS))
        return bad / len(lines) > 0.25

    @classmethod
    def _clean_llm_script(cls, text: str) -> str:
        """Clean raw LLM response: strip JSON wrappers, markdown, preambles, garbage lines."""
        if not text:
            return ""
        # Strip JSON wrapper: {"role":"assistant","content":"..."}
        text = re.sub(
            r'^\s*\{?\s*"?role"?\s*:\s*"?\w+"?\s*,?\s*"?content"?\s*:\s*"?',
            '', text
        )
        text = re.sub(r'"\s*\}?\s*$', '', text)
        # Strip code blocks (and their content) and inline backticks.
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`+', '', text)
        # Strip markdown emphasis/headings.
        text = re.sub(r"\*+", "", text)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # Strip LLM preamble lines.
        text = re.sub(
            r'^\s*(Here\'s|Here is|Sure[!,.]?\s*here|Of course|AquÃ­ (estÃ¡|tienes|te presento)|'
            r'Â¡?(Por supuesto|Claro|Desde luego|Con gusto)|A continuaciÃ³n)[^\n]*\n',
            '', text, flags=re.IGNORECASE
        )
        # Strip trailing notes.
        text = re.sub(
            r'\n\s*(Note:|Nota:|---|\*\*\*|This script|Este guion|Espero que|I hope this)[^\n]*$',
            '', text, flags=re.IGNORECASE
        )
        # Final pass: drop any line that looks like metadata / URL / API junk.
        text, dropped = cls._filter_garbage_lines(text)
        if dropped > 0:
            warning(f"   [Clean] dropped {dropped} garbage line(s) from LLM output.")
        text = strip_narration_structure_labels(text)
        return text.strip()

    @classmethod
    def _clean_script_for_tts(cls, script: str) -> str:
        """Last-line-of-defense cleaner: only spoken narration survives."""
        text = script

        # Strip stage-direction artifacts the LLM leaks ("(imagen de ...)",
        # "[B-roll: ...]", "MÃºsica: ...") BEFORE the section-marker pass so
        # nothing falls through.
        text = strip_stage_directions(text)

        # Strip section markers in any language / case.
        text = re.sub(r'\[(INTRO|INTRODUCCIÃ“N|INTRODUCCION|CLOSING|CIERRE|OUTRO|DESPEDIDA)\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[(SECTION|SECCIÃ“N|SECCION)\s*\d+\s*:?[^\]]*\]', '', text, flags=re.IGNORECASE)
        text = strip_narration_structure_labels(text)

        # Some LLMs write the markers WITHOUT brackets â€” strip those too.
        text = re.sub(r'^\s*(INTRO|INTRODUCCIÃ“N|INTRODUCCION|CLOSING|CIERRE|OUTRO|DESPEDIDA)\s*:?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        text = re.sub(r'^\s*(SECTION|SECCIÃ“N|SECCION)\s*\d+\s*:[^\n]*$', '', text, flags=re.IGNORECASE | re.MULTILINE)

        # Strip JSON / code artifacts.
        text = re.sub(r'"role"\s*:\s*"[^"]*"', '', text)
        text = re.sub(r'"content"\s*:\s*"', '', text)
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`+', '', text)

        # Strip URLs / bare domains so the TTS never reads one out loud.
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'\bwww\.\S+', '', text)
        text = re.sub(r'\b[\w.-]+\.(?:com|org|net|io|ai|gov|edu|co|es|app|dev|tv)(?:/\S*)?', '', text, flags=re.IGNORECASE)

        # Strip markdown artifacts.
        text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*+', '', text)

        # Strip stray JSON braces and quotes at start/end.
        text = re.sub(r'^\s*[\{\}]\s*', '', text)
        text = re.sub(r'\s*[\{\}]\s*$', '', text)

        # Drop garbage lines (URLs, identifiers, "guion bajo ...", error messages).
        text, _ = cls._filter_garbage_lines(text)

        # Drop snake_case / kebab identifiers that survived (`user_role`, `api-key`).
        text = re.sub(r'\b\w+(?:[_-]\w+){1,}\b', '', text)

        # Collapse whitespace.
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        return text.strip()

    def combine_long(self) -> str:
        """
        Combines images and audio into a long-form 16:9 landscape video.
        Cinematic Ken Burns effect, smooth transitions, and optional karaoke subtitles.
        """
        combined_path = os.path.join(get_video_cache_path(), str(uuid4()) + ".mp4")
        threads = get_threads()
        tts_clip = AudioFileClip(self.tts_path)
        max_duration = tts_clip.duration

        t_total = time.time()
        print(colored(f"[+] Combining {len(self.images)} images into long video ({max_duration:.0f}s)...", "blue"), flush=True)

        valid_images = [p for p in self.images if os.path.exists(p)]
        if not valid_images:
            raise FileNotFoundError("No valid images found")
        self.images = valid_images

        n_total = len(self.images)

        # Compensate req_dur for the crossfade overlap so the VISIBLE duration matches
        # the audio exactly. Each of the (n-1) crossfades eats CROSSFADE_DUR seconds, so
        # we extend each clip a bit. Without this, the last ~23s of audio play over a
        # black screen because the visible video ends early.
        # Also reserve EXTRA_TAIL extra seconds on the last clip so it can fade out gracefully.
        CROSSFADE_DUR = 0.8
        EXTRA_TAIL = 1.5  # the last clip lingers 1.5s for the fade-out
        durations = self._long_clip_durations(n_total, max_duration, CROSSFADE_DUR, EXTRA_TAIL)
        target_visual_duration = max_duration + EXTRA_TAIL
        total_dur = target_visual_duration

        random_song = choose_random_song(getattr(self, "subject", ""))
        if is_soundimage_track(random_song):
            self._append_music_attribution(MATYAS_ATTRIBUTION)

        try:
            print(colored("[+] Rendering long video with ffmpeg...", "blue"), flush=True)
            t_phase = time.time()
            self._write_long_with_ffmpeg(
                output_path=combined_path,
                image_paths=self.images,
                durations=durations,
                random_song=random_song,
                fps=24,
                crossfade=CROSSFADE_DUR,
                karaoke_enabled=bool(getattr(self, "word_timestamps", None)),
                music_volume=0.10,
                audio_duration=max_duration,
                total_duration=total_dur,
                extra_tail=EXTRA_TAIL,
                threads=threads,
            )
            print(colored(f"    [Render] done in {time.time() - t_phase:.1f}s", "green"), flush=True)
            print(colored(f"[+] Total combine_long: {time.time() - t_total:.1f}s", "blue"), flush=True)
            tts_clip.close()
            success(f'Wrote long video to "{combined_path}"')
            return combined_path
        except Exception as e:
            warning(f"FFmpeg long render failed, falling back to MoviePy: {e}")

        t_phase = time.time()
        clips = []
        for clip_idx, (image_path, clip_dur) in enumerate(zip(self.images, durations), start=1):
            if clip_dur < 0.5:
                break

            try:
                print(colored(f"    [Build] Clip {clip_idx}/{n_total} ({clip_dur:.1f}s)...", "cyan"), flush=True)
                img_clip = ImageClip(image_path).set_duration(clip_dur)

                # Resize to 1920x1080
                w, h = img_clip.size
                aspect = w / h
                target_aspect = 1920 / 1080

                if aspect > target_aspect:
                    img_clip = img_clip.resize(height=1080)
                    img_clip = crop(img_clip, x_center=img_clip.w / 2, y_center=540, width=1920, height=1080)
                else:
                    img_clip = img_clip.resize(width=1920)
                    img_clip = crop(img_clip, x_center=960, y_center=img_clip.h / 2, width=1920, height=1080)

                # Ken Burns: gentle slow zoom (1.0x â†’ 1.08x over clip duration)
                # Use default arg to capture clip_dur in the closure
                img_clip = img_clip.resize(lambda t, d=clip_dur: 1 + 0.08 * (t / d))

                # Crossfade between images
                if clip_dur > 2.0:
                    img_clip = img_clip.crossfadein(0.8)

                img_clip = img_clip.set_fps(24)
                clips.append(img_clip)

            except Exception as e:
                if get_verbose():
                    warning(f"Skipping image {image_path}: {e}")
                continue
        print(colored(f"    [Build] {len(clips)} clips ready in {time.time() - t_phase:.1f}s", "green"), flush=True)

        if not clips:
            raise RuntimeError("No clips could be created from images")

        # Concatenate with crossfade overlap between clips
        print(colored("[+] Applying transitions...", "blue"), flush=True)
        t_phase = time.time()
        padding = -CROSSFADE_DUR if len(clips) > 1 else 0
        final_clip = concatenate_videoclips(clips, padding=padding, method="compose")
        final_clip = final_clip.set_fps(24)

        # The video should now last about (audio + EXTRA_TAIL); cap to (audio + EXTRA_TAIL)
        # so we have a small visual tail beyond the last narration word that fades out.
        target_visual_duration = max_duration + EXTRA_TAIL
        if final_clip.duration > target_visual_duration:
            final_clip = final_clip.subclip(0, target_visual_duration)

        # Smooth fade-to-black at the very end so the closing doesn't cut abruptly.
        final_clip = final_clip.fadeout(EXTRA_TAIL)

        subtitles = None
        if getattr(self, "word_timestamps", None):
            try:
                print(colored("[+] Building long-video karaoke subtitles...", "blue"), flush=True)
                subtitles = self._build_karaoke_subtitles_landscape(target_visual_duration, fps=24)
                if subtitles is not None:
                    subtitles = subtitles.set_duration(target_visual_duration)
                    final_clip = CompositeVideoClip(
                        [final_clip, subtitles], size=(1920, 1080)
                    ).set_duration(target_visual_duration)
                    print(colored("[+] Long karaoke subtitles ready.", "green"), flush=True)
            except Exception as e:
                warning(f"Failed to generate long karaoke subtitles, continuing without subtitles: {e}")

        print(colored(f"    [Transitions] done in {time.time() - t_phase:.1f}s", "green"), flush=True)

        # Audio: TTS + background music
        print(colored("[+] Mixing audio...", "blue"), flush=True)
        t_phase = time.time()
        music_clip = AudioFileClip(random_song).set_fps(44100)

        # Loop music if shorter than the full timeline (narration + fade tail)
        if music_clip.duration < total_dur:
            loops_needed = int(total_dur // music_clip.duration) + 1
            music_clip = concatenate_audioclips([music_clip] * loops_needed)
        music_clip = music_clip.subclip(0, total_dur)

        # Background music at 10% volume for long videos (subtle ambient)
        music_clip = music_clip.fx(afx.volumex, 0.10)

        # Music fades in over 3s at start; fades out across the EXTRA_TAIL closing window
        # in sync with the visual fade-to-black.
        music_clip = music_clip.audio_fadein(3.0).audio_fadeout(EXTRA_TAIL + 1.0)

        comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), music_clip])

        # Set audio THEN duration â€” order matters for MoviePy
        final_clip = final_clip.set_duration(total_dur)
        final_clip = final_clip.set_audio(comp_audio)
        print(colored(f"    [Audio] mixed in {time.time() - t_phase:.1f}s", "green"), flush=True)

        print(colored("[+] Rendering long video (ffmpeg)...", "blue"), flush=True)
        t_phase = time.time()
        self._write_videofile_with_fallback(
            final_clip,
            combined_path,
            threads=threads,
            fps=24,
        )
        print(colored(f"    [Render] done in {time.time() - t_phase:.1f}s", "green"), flush=True)
        print(colored(f"[+] Total combine_long: {time.time() - t_total:.1f}s", "blue"), flush=True)

        success(f'Wrote long video to "{combined_path}"')
        return combined_path

    def generate_long_video(self, tts_instance: TTS, custom_topic: str = "") -> str:
        """
        Public entry point for the long-video pipeline. Pins the LLM to the
        configured long-video model chain unless the user picked a provider
        and model explicitly from the UI.
        """
        from llm_provider import force_provider, warmup_ollama_model, is_user_override, get_active_provider, get_active_model
        if is_user_override():
            active = get_active_provider()
            active_model = get_active_model() or "(default)"
            info(f"\n  Long-video LLM: {active}/{active_model} (user override - no think pin)")
            if active == "ollama" and active_model and active_model != "(default)":
                warmup_ollama_model(active_model)
            return self._generate_long_video_inner(tts_instance, custom_topic)

        long_models = get_long_video_llm_models()
        primary = long_models[0] if long_models else get_long_video_llm_model()
        info(f"\n  Long-video LLM: ollama/{primary}"
             + (f"  (fallbacks: {', '.join(long_models[1:])})" if len(long_models) > 1 else ""))
        if primary:
            warmup_ollama_model(primary)
        with force_provider("ollama", long_models or primary):
            return self._generate_long_video_inner(tts_instance, custom_topic)

    def _generate_long_video_inner(self, tts_instance: TTS, custom_topic: str = "") -> str:
        """
        Full pipeline for generating a long-form YouTube video (15-16 minutes max).
        16:9 landscape, documentary style, no subtitles.

        Args:
            tts_instance (TTS): Instance of TTS Class.
            custom_topic (str): Optional user-provided topic. If given, skips auto topic generation.

        Returns:
            path (str): Path to the generated MP4 file.
        """
        info("=" * 50)
        info("  LONG VIDEO GENERATION PIPELINE")
        info("=" * 50)

        # Mark this as a long video so upload_video knows to wait longer for the upload to finish.
        self._is_long_video = True
        self.retention_plan = {}
        self.retention_preflight = {}
        self.retention_hook_lab = {}
        self.visual_beat_map = []
        self.visual_beat_report = {}
        self.visual_preflight = {}

        # Step 1: Generate Topic (or use the user-provided one)
        info("\n[1/7] Generating topic...")
        if custom_topic and custom_topic.strip():
            self.subject = custom_topic.strip()
            info(f" => Using custom topic: {self.subject}")
        else:
            self.generate_topic()
        if not self.subject or not self.subject.strip():
            error(
                "Aborting long video: no unique topic available. "
                "No video will be generated or uploaded."
            )
            self.video_path = ""
            return ""

        # Series detection: if subject starts with "[series_id] ...", strip the
        # prefix and remember which series this video belongs to. generate_long_metadata
        # and generate_thumbnail use the series template/overlay instead of asking
        # the LLM to invent a title or overlay text.
        self.active_series, self.subject = resolve_series(self.subject)
        if self.active_series:
            info(f" => Series: {self.active_series.get('id', '')}")

        success(f" Topic: {self.subject}")

        # Step 2: Generate long script with chapters
        info("\n[2/7] Generating long-form script...")
        self.generate_long_script()

        # Step 3: Generate metadata
        info("\n[3/7] Generating title & description...")
        self.generate_long_metadata()
        success(f" Title: {self.metadata['title']}")

        # Step 4: Generate clickbait thumbnail (1280x720)
        info("\n[4/7] Generating thumbnail...")
        try:
            self.generate_thumbnail()
        except Exception as e:
            warning(f"Thumbnail generation failed: {str(e)[:200]} (will upload without custom thumbnail)")
            self.thumbnail_path = ""

        # Step 5: Generate image prompts
        info("\n[5/7] Generating image prompts...")
        self.images = []  # Reset images
        self.generate_long_prompts()

        # Step 6: Generate images (landscape 1920x1080)
        info("\n[6/7] Generating images...")
        self.generate_long_images(self.image_prompts)

        # Step 7: Generate TTS with natural voice
        info("\n[7/7] Generating narration audio...")
        path = os.path.join(get_temp_cache_path(), str(uuid4()) + ".wav")

        # Clean script for TTS: remove ALL non-narration content
        tts_script = self._clean_script_for_tts(self.script)

        # Fallback: if cleaning wiped everything, use the raw script
        if not tts_script or len(tts_script.split()) < 50:
            warning("TTS cleaning removed too much content, using raw script")
            tts_script = re.sub(r'\[.*?\]', '', self.script).strip()

        # Expand spoken symbols ("90%" -> "90 por ciento") so TTS verbalizes them.
        tts_script = expand_spoken_symbols(tts_script)

        # Expand regnal numerals ("Luis XIV" -> "Luis catorce") for correct TTS pronunciation
        tts_script = expand_regnal_numerals(tts_script)

        # Expand digit numbers to Spanish words ("4.500" -> "cuatro mil quinientos",
        # "1453" -> "mil cuatrocientos cincuenta y tres") so the TTS doesn't read
        # them digit-by-digit ("4 punto 5 0 0").
        tts_script = expand_spanish_numbers(tts_script)

        if get_verbose():
            info(f" => TTS script preview (first 200 chars): {tts_script[:200]}")

        # Per-channel long-video voice (or fall back to the default deep narrator).
        from .Tts import LONG_VIDEO_NARRATOR
        long_vid = self._resolve_voice(self._long_voice) or LONG_VIDEO_NARRATOR
        # Locale guard: Edge-TTS returns NoAudioReceived if you ship Spanish
        # text to an English voice (e.g. "Bruno" -> en-US-DavisNeural). When
        # the channel language is Spanish, force a Spanish narrator.
        lang = (self._language or "").strip().lower()
        is_spanish = lang.startswith("esp") or lang in {"es", "spanish"}
        if is_spanish and not long_vid.lower().startswith("es-"):
            warning(f"Voice '{long_vid}' is not Spanish but channel language is '{self._language}'. Falling back to {LONG_VIDEO_NARRATOR}.")
            long_vid = LONG_VIDEO_NARRATOR
        info(f" => Using long-video voice: {long_vid}")
        tts_instance.synthesize_long(tts_script, path, voice_id=long_vid)
        self.tts_path = path

        if os.path.exists(path) and os.path.getsize(path) > 1000:
            audio_dur = AudioFileClip(path).duration
            info(f" => Audio duration: {audio_dur:.0f} seconds ({audio_dur/60:.1f} min)")
        else:
            raise RuntimeError(f"TTS failed to generate audio file at {path}")

        # Step 7: Combine everything
        info("\n[+] Assembling final video...")
        video_path = self.combine_long()

        self.video_path = os.path.abspath(video_path)
        self._persist_metadata_sidecar(is_long=True)

        try:
            from upload_tracker import record_generation
            record_generation(
                self.video_path,
                list(self.images),
                [getattr(self, "tts_path", None), getattr(self, "subtitles_path", None)],
                subject=getattr(self, "subject", "") or "",
            )
        except Exception as _e:
            warning(f"Could not record upload manifest: {_e}")

        success(f"\n=> Long video generated: {video_path}")

        return video_path

    def _verify_thumbnail_uploaded(self, driver) -> bool:
        """
        After send_keys(thumbnail.png), confirm YouTube actually accepted it.
        Multiple signals because YT Studio's DOM varies by locale and rollout.
        Returns True if any custom-thumbnail signal is detected.
        """
        try:
            # Primary signal: scoped <img> elements inside the thumbnail editor whose
            # src is NOT an i.ytimg.com auto-generated URL.
            imgs = driver.find_elements(
                By.CSS_SELECTOR,
                "ytcp-thumbnails-compact-editor img, "
                "ytcp-thumbnail-uploader img, "
                "ytcp-thumbnails-compact-editor-uploader img, "
                "ytcp-uploads-still img, "
                "ytcp-thumbnail-card img, "
                "ytcp-thumbnail img"
            )
            for img in imgs:
                try:
                    src = (img.get_attribute("src") or "").lower()
                except Exception:
                    continue
                if not src:
                    continue
                # Auto-generated thumbnails from YT come from i.ytimg.com / i9.ytimg.com.
                # Anything else inside the editor area (blob:, data:, googleusercontent,
                # lh3.google, or a YT-internal upload URL) means a custom upload rendered.
                if "ytimg.com" in src:
                    continue
                if (src.startswith("blob:")
                        or src.startswith("data:image")
                        or "googleusercontent.com" in src
                        or "lh3.google" in src
                        or "yt3.ggpht.com" in src):
                    return True
            # Alternative signal: any control that only renders once a custom
            # thumbnail is in place (Replace / Edit / Options menu).
            for selector in (
                "[aria-label*='Cambiar miniatura' i]",
                "[aria-label*='Reemplazar miniatura' i]",
                "[aria-label*='Editar miniatura' i]",
                "[aria-label*='Opciones de miniatura' i]",
                "[aria-label*='Replace thumbnail' i]",
                "[aria-label*='Edit thumbnail' i]",
                "[aria-label*='Thumbnail options' i]",
                "ytcp-thumbnail-card-options",
                "ytcp-thumbnails-compact-editor ytcp-thumbnail-card[selected]",
            ):
                try:
                    if driver.find_elements(By.CSS_SELECTOR, selector):
                        return True
                except Exception:
                    continue
            # Last resort: the uploader's "Upload thumbnail" CTA disappears once a
            # custom thumbnail is present. If we previously saw it and now it's gone,
            # treat that as a positive signal.
            try:
                upload_ctas = driver.find_elements(
                    By.CSS_SELECTOR,
                    "[aria-label*='Subir miniatura' i], "
                    "[aria-label*='Upload thumbnail' i]"
                )
                visible_cta = any(
                    el.is_displayed() for el in upload_ctas if el is not None
                )
                if upload_ctas and not visible_cta:
                    return True
            except Exception:
                pass
        except Exception:
            pass
        return False

    def _find_thumbnail_input(self, driver, wait):
        """
        Locate YouTube Studio's thumbnail file input across UI variants.

        Strategy (most reliable first):
          1. Find every `input[type=file]` and pick the one whose `accept` attribute
             names an image type â€” that filters out the video upload input itself.
          2. Fall back to known CSS selectors for older YT Studio versions.
        Returns the WebElement or None.
        """
        # Give YT Studio a moment to finish rendering the Details panel.
        time.sleep(2)

        try:
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        except Exception:
            file_inputs = []

        for inp in file_inputs:
            try:
                accept = (inp.get_attribute("accept") or "").lower()
            except Exception:
                accept = ""
            if "image" in accept and "video" not in accept:
                return inp

        # Legacy / variant-specific selectors as fallback.
        for sel in (
            "ytcp-thumbnails-compact-editor input[type='file']",
            "ytcp-thumbnails-compact-editor-uploader input[type='file']",
            "ytcp-thumbnail-uploader input[type='file']",
            "input#file-loader[accept*='image']",
        ):
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el is not None:
                    return el
            except Exception:
                continue
        return None

    def _ensure_browser(self) -> None:
        """
        Ensures the Firefox browser is running and connected.
        Launches (or re-launches) the browser if it is None or the session has died.
        Called lazily just before upload so a browser crash during video generation
        does not discard the finished video.
        """
        session_alive = False
        if self.browser is not None:
            try:
                # A simple property access will raise if the session is dead
                _ = self.browser.current_url
                session_alive = True
            except Exception:
                session_alive = False
                try:
                    self.browser.quit()
                except Exception:
                    pass
                self.browser = None

        if not session_alive:
            info(" => Conectando con Firefox...")
            self._free_firefox_profile()
            service = Service(GeckoDriverManager().install())
            self.browser = webdriver.Firefox(service=service, options=self.options)
            success(" => Firefox conectado.")

    def _free_firefox_profile(self) -> None:
        """
        Selenium can't open Firefox if the configured profile is already in use
        (the user has Firefox open, or a previous run left lock files behind).
        Kill any running firefox.exe / geckodriver.exe and remove stale profile
        locks so the upcoming `webdriver.Firefox(...)` call gets a clean slate.
        Best-effort: never raise â€” if killing fails, Selenium will surface the
        usual "Process unexpectedly closed with status 0".
        """
        import os
        import sys
        import time
        import subprocess

        # 1) Kill any running Firefox / geckodriver. Without this, Selenium's
        # spawned firefox.exe just hands the URL to the existing window and
        # exits, leaving the driver with no session.
        targets = ["firefox.exe", "geckodriver.exe"] if sys.platform == "win32" else ["firefox", "geckodriver"]
        killed_any = False
        for proc_name in targets:
            try:
                if sys.platform == "win32":
                    result = subprocess.run(
                        ["taskkill", "/F", "/IM", proc_name, "/T"],
                        capture_output=True, text=True, timeout=10,
                    )
                    # taskkill returns 128 if no such process â€” treat as success.
                    if result.returncode == 0:
                        killed_any = True
                else:
                    subprocess.run(["pkill", "-f", proc_name], capture_output=True, timeout=10)
            except Exception:
                pass
        if killed_any:
            info(" => CerrÃ© Firefox abierto para liberar el perfil.")
            time.sleep(1.5)  # let Windows release file handles

        # 2) Remove stale lock files in the configured profile directory.
        try:
            from config import get_firefox_profile_path
            profile_dir = get_firefox_profile_path()
        except Exception:
            profile_dir = None
        if profile_dir and os.path.isdir(profile_dir):
            for lock_name in ("parent.lock", ".parentlock", "lock"):
                lock_path = os.path.join(profile_dir, lock_name)
                try:
                    if os.path.exists(lock_path):
                        os.remove(lock_path)
                except Exception:
                    pass

    def _extract_channel_id_from_url(self, url: str) -> str:
        match = re.search(r"/channel/([^/?#]+)", url or "")
        if match:
            return match.group(1)
        return ""

    def get_channel_id(self) -> str:
        """
        Gets the Channel ID of the YouTube Account.

        Returns:
            channel_id (str): The Channel ID.
        """
        driver = self.browser
        existing_channel_id = getattr(self, "channel_id", "") or ""
        try:
            driver.set_page_load_timeout(75)
        except Exception:
            pass
        try:
            driver.get("https://studio.youtube.com")
        except Exception as e:
            warning(f"Could not fully load YouTube Studio while resolving channel ID: {e}")
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
        finally:
            try:
                driver.set_page_load_timeout(300)
            except Exception:
                pass
        time.sleep(2)
        channel_id = self._extract_channel_id_from_url(getattr(driver, "current_url", "") or "")
        if channel_id:
            self.channel_id = channel_id
            return channel_id
        if existing_channel_id:
            return existing_channel_id
        warning("Could not resolve YouTube channel ID from Studio URL; upload will continue.")

        return ""

    def _get_channel_id_safe(self) -> str:
        """
        Resolve the channel ID WITHOUT navigating the current tab.

        Critical for long-video uploads: once the user has clicked "Done"
        on the upload dialog, navigating the upload tab to studio.youtube.com
        cancels the in-flight HTTP file transfer. This helper opens a
        SEPARATE tab, reads the URL, then closes that tab and returns to
        the original handle.

        Falls back to the existing self.channel_id if the side tab cannot
        be opened. Returns "" if everything fails.
        """
        driver = self.browser
        if driver is None:
            return getattr(self, "channel_id", "") or ""

        original_handle = driver.current_window_handle
        status_handle = None
        try:
            existing = set(driver.window_handles)
            driver.execute_script("window.open('about:blank', '_blank');")
            time.sleep(1)
            new_handles = [h for h in driver.window_handles if h not in existing]
            if not new_handles:
                return getattr(self, "channel_id", "") or ""
            status_handle = new_handles[0]
            driver.switch_to.window(status_handle)
            try:
                driver.set_page_load_timeout(75)
            except Exception:
                pass
            try:
                driver.get("https://studio.youtube.com")
            except Exception as e:
                warning(f"Safe channel_id Studio load timed out: {e}")
                try:
                    driver.execute_script("window.stop();")
                except Exception:
                    pass
            time.sleep(3)
            channel_id = self._extract_channel_id_from_url(getattr(driver, "current_url", "") or "")
            if channel_id:
                self.channel_id = channel_id
                return channel_id
            return getattr(self, "channel_id", "") or ""
        except Exception as e:
            warning(f"Safe channel_id resolve failed: {e}")
            return getattr(self, "channel_id", "") or ""
        finally:
            try:
                driver.set_page_load_timeout(300)
            except Exception:
                pass
            try:
                if status_handle and status_handle in driver.window_handles:
                    driver.switch_to.window(status_handle)
                    driver.close()
            except Exception:
                pass
            try:
                if original_handle in driver.window_handles:
                    driver.switch_to.window(original_handle)
            except Exception:
                pass

    def _wait_for_listing_settled(
        self,
        driver,
        listing_tab: str,
        kind_label: str,
        max_wait_s: int,
        poll_interval_s: int = 8,
        refresh_interval_s: int = 60,
    ) -> bool:
        """
        Wait for an upload (Short or long video) to finish transferring + processing,
        WITHOUT touching the original tab where the upload runs in the background.

        IMPORTANT: navigating or refreshing the upload tab while the HTTP file
        transfer is in flight CANCELS the upload (YouTube shows
        "Upload interrupted" / "Subida interrumpida"). We therefore open a SECOND
        tab, do all polling there, close it, and return to the original tab
        untouched.

        Strategy:
          1. Open a new browser tab via JS.
          2. Switch to it and navigate to /videos/<listing_tab>.
          3. Poll the row matching our title until ALL in-progress markers
             disappear (Subiendo / Uploading / Pendiente / Pending / Procesando /
             Processing / Verificando / Checking / Cancelar carga).
          4. If we see an explicit "Subida interrumpida / Upload interrupted"
             marker, abort early and tell the user.
          5. ALWAYS close the new tab and switch back to the original tab.

        Args:
            listing_tab: "short" for Shorts, "upload" for long videos.
            kind_label: human-readable label used only in log lines.
            max_wait_s: hard total cap.
            poll_interval_s: time between row reads.
            refresh_interval_s: time between status-tab refreshes.

        Returns:
            True when the row settles cleanly, False on timeout or detected
            interruption.
        """
        info(f"\t=> Waiting up to {max_wait_s // 60} min for {kind_label} upload + processing...")
        info("\t   (polling in a SEPARATE tab so the upload tab is never disturbed)")

        deadline = time.time() + max_wait_s
        if not getattr(self, "channel_id", None):
            warning("\t=> Cannot poll YouTube Studio listing because channel ID was not resolved.")
            return False
        if listing_tab == "short":
            listing_url = f"https://studio.youtube.com/channel/{self.channel_id}/videos/short"
        else:
            listing_url = (
                f"https://studio.youtube.com/channel/{self.channel_id}/videos"
                f'?filter=%5B%5D&sort=%7B%22columnType%22%3A%22date%22%2C%22sortOrder%22%3A%22DESCENDING%22%7D'
            )
        target_title = (self.metadata.get("title") or "").strip()
        target_match = target_title[:50] if target_title else ""

        in_progress_markers = (
            "subiendo", "uploading",
            "procesando", "processing",
            "pendiente", "pending",
            "verificando", "verificaciones en curso",
            "checking", "checks in progress",
            "cancelar carga", "cancel upload",
        )
        # Hard-fail markers: YouTube has explicitly interrupted the transfer.
        error_markers = (
            "subida interrumpida",
            "carga interrumpida",
            "upload interrupted",
        )
        # YT Studio "Oops, something went wrong" / "Algo saliÃ³ mal" page.
        # When this shows up, the listing tab is broken â€” refresh() alone
        # often can't recover, so we re-navigate to the URL.
        studio_error_markers = (
            "oops, something went wrong",
            "something went wrong",
            "algo saliÃ³ mal",
            "algo salio mal",
            "ha ocurrido un error",
            "se produjo un error",
            "intenta volver a cargar",
            "try reloading",
            "try again later",
            "vuelve a intentarlo",
        )
        max_studio_error_retries = 5

        original_handle = driver.current_window_handle
        status_handle = None
        try:
            # Retry opening the status tab a few times â€” window.open() can
            # transiently fail while YouTube is busy parsing the just-uploaded
            # file. We do NOT switch away from the upload tab during retries.
            new_handles: List[str] = []
            for open_attempt in range(1, 6):
                existing = set(driver.window_handles)
                try:
                    driver.execute_script("window.open('about:blank', '_blank');")
                except Exception as e:
                    warning(f"\t=> window.open attempt {open_attempt}/5 failed: {e}")
                time.sleep(2)
                new_handles = [h for h in driver.window_handles if h not in existing]
                if new_handles:
                    break
                warning(f"\t=> Status-tab open attempt {open_attempt}/5 produced no new handle; retrying...")

            if not new_handles:
                # We genuinely couldn't open a side tab. DO NOT touch the
                # upload tab â€” just sleep in place and return False so the
                # caller knows the upload was not verified. Returning True
                # here would make the caller try to resolve the URL on the
                # upload tab, cancelling the upload mid-transfer.
                warning(
                    "\t=> Could not open status-check tab after 5 attempts. "
                    "Will stay idle (upload tab untouched) and let the user "
                    "verify manually in YouTube Studio."
                )
                # Long videos: wait the full requested window (capped to a
                # generous 60 min so we don't sleep forever) so the upload
                # has time to actually finish in the background.
                idle_wait = min(max_wait_s, 3600)
                info(f"\t=> Idle-waiting {idle_wait // 60} min in place â€” DO NOT navigate or close the upload tab.")
                time.sleep(idle_wait)
                return False
            status_handle = new_handles[0]
            driver.switch_to.window(status_handle)

            try:
                driver.get(listing_url)
                time.sleep(12)
            except Exception as e:
                warning(f"\t=> Could not navigate status tab to listing: {e}")
                return False

            last_status = ""
            last_announce = 0.0
            last_refresh = time.time()
            stable_done_count = 0  # require 2 consecutive "no markers" reads to call it done
            studio_error_retries = 0
            consecutive_empty_polls = 0

            while time.time() < deadline:
                row_text = ""
                rows_found = 0
                try:
                    rows = driver.find_elements(By.TAG_NAME, "ytcp-video-row")
                    rows_found = len(rows)
                    chosen_row = None
                    if target_match:
                        for r in rows[:15]:
                            try:
                                t = r.text.strip()
                            except Exception:
                                t = ""
                            if target_match in t:
                                chosen_row = r
                                break
                    if chosen_row is None and rows:
                        chosen_row = rows[0]
                    if chosen_row is not None:
                        row_text = chosen_row.text.lower()
                except Exception:
                    row_text = ""

                # Detect YT Studio's generic error page (no rows + "oops" text in body).
                # When it shows up, plain refresh() often can't rescue it â€” re-navigate.
                if rows_found == 0:
                    page_text = ""
                    try:
                        page_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
                    except Exception:
                        page_text = ""
                    if any(m in page_text for m in studio_error_markers):
                        studio_error_retries += 1
                        if studio_error_retries > max_studio_error_retries:
                            warning(
                                f"\t=> YT Studio listing keeps showing an error page after "
                                f"{max_studio_error_retries} retries. Giving up on the polling "
                                "tab â€” the upload tab itself is untouched and likely fine. "
                                "Verify manually in Studio."
                            )
                            return False
                        warning(
                            f"\t=> YT Studio listing showed an error page "
                            f"(retry {studio_error_retries}/{max_studio_error_retries}). "
                            "Re-navigating the polling tab..."
                        )
                        try:
                            driver.get(listing_url)
                            time.sleep(8)
                            last_refresh = time.time()
                        except Exception as e:
                            warning(f"\t=> Re-navigation failed: {e}")
                        consecutive_empty_polls = 0
                        time.sleep(poll_interval_s)
                        continue

                if row_text:
                    studio_error_retries = 0
                    consecutive_empty_polls = 0

                    if any(m in row_text for m in error_markers):
                        error(
                            f"\t=> {kind_label} upload was INTERRUPTED by YouTube. "
                            "Open the original tab and click 'Reanudar carga / Resume upload' manually."
                        )
                        return False

                    present = [m for m in in_progress_markers if m in row_text]
                    if not present:
                        stable_done_count += 1
                        if stable_done_count >= 2:
                            info(f"\t=> {kind_label} upload + processing finished.")
                            return True
                        info(f"\t=> {kind_label} looks done; confirming with one more poll...")
                    else:
                        stable_done_count = 0
                        if "subiendo" in present or "uploading" in present:
                            current_status = "uploading"
                        elif "procesando" in present or "processing" in present:
                            current_status = "processing"
                        elif ("verificando" in present or "checking" in present
                              or "verificaciones en curso" in present
                              or "checks in progress" in present):
                            current_status = "running checks"
                        else:
                            current_status = "pending"
                        now = time.time()
                        if current_status != last_status or (now - last_announce) > 60:
                            info(f"\t=> {kind_label} status: {current_status} â€” still waiting (upload tab untouched)...")
                            last_status = current_status
                            last_announce = now
                else:
                    stable_done_count = 0
                    consecutive_empty_polls += 1
                    now = time.time()
                    if (now - last_announce) > 60:
                        info(f"\t=> Waiting for {kind_label} to appear in listing...")
                        last_announce = now
                    # If many polls in a row return zero rows (no error text either â€”
                    # could be a slow render, ghost spinner, or a blank Studio page),
                    # force a hard re-navigation rather than waiting for the next refresh.
                    if consecutive_empty_polls >= 12:
                        studio_error_retries += 1
                        if studio_error_retries > max_studio_error_retries:
                            warning(
                                "\t=> Polling tab never showed any rows after multiple "
                                "re-navigations. Giving up â€” verify manually in Studio."
                            )
                            return False
                        warning(
                            f"\t=> Polling tab is empty after {consecutive_empty_polls} polls "
                            f"(retry {studio_error_retries}/{max_studio_error_retries}). Re-navigating..."
                        )
                        try:
                            driver.get(listing_url)
                            time.sleep(15)
                            last_refresh = time.time()
                        except Exception as e:
                            warning(f"\t=> Re-navigation failed: {e}")
                        consecutive_empty_polls = 0
                        time.sleep(poll_interval_s)
                        continue

                now = time.time()
                if now - last_refresh > refresh_interval_s:
                    try:
                        driver.refresh()
                        time.sleep(5)
                        last_refresh = time.time()
                    except Exception:
                        pass

                time.sleep(poll_interval_s)

            warning(
                f"\t=> Hit total wait cap of {max_wait_s // 60} min for {kind_label}. "
                "Firefox will stay open so YT can keep processing â€” close it manually when done."
            )
            return False
        finally:
            # ALWAYS clean up: close the status tab and return to the upload tab.
            # If we don't, subsequent driver.get() calls will run on the wrong tab.
            try:
                if status_handle and status_handle in driver.window_handles:
                    driver.switch_to.window(status_handle)
                    driver.close()
            except Exception:
                pass
            try:
                if original_handle in driver.window_handles:
                    driver.switch_to.window(original_handle)
            except Exception:
                pass

    def _resolve_video_url_safe(self, driver, listing_tab: str) -> str:
        """
        Resolve the public URL of the just-uploaded video using a SEPARATE tab,
        so the original upload tab is never navigated. Same status-tab pattern
        as `_wait_for_listing_settled`. Returns "" if it can't find a match.
        """
        if not getattr(self, "channel_id", None):
            return ""
        if listing_tab == "short":
            listing_url = f"https://studio.youtube.com/channel/{self.channel_id}/videos/short"
        else:
            listing_url = (
                f"https://studio.youtube.com/channel/{self.channel_id}/videos"
                f'?filter=%5B%5D&sort=%7B%22columnType%22%3A%22date%22%2C%22sortOrder%22%3A%22DESCENDING%22%7D'
            )
        target_title = (self.metadata.get("title") or "").strip()
        target_match = target_title[:50] if target_title else ""

        studio_error_markers = (
            "oops, something went wrong",
            "something went wrong",
            "algo saliÃ³ mal",
            "algo salio mal",
            "ha ocurrido un error",
            "se produjo un error",
            "intenta volver a cargar",
            "try reloading",
            "try again later",
            "vuelve a intentarlo",
        )

        original_handle = driver.current_window_handle
        status_handle = None
        try:
            existing = set(driver.window_handles)
            driver.execute_script("window.open('about:blank', '_blank');")
            time.sleep(3)
            new_handles = [h for h in driver.window_handles if h not in existing]
            if not new_handles:
                return ""
            status_handle = new_handles[0]
            driver.switch_to.window(status_handle)

            # Retry the navigation if YT Studio greets us with the "Oops"
            # error page or with an empty listing. Up to 5 attempts, each
            # gives the page a few seconds to render.
            videos = []
            for attempt in range(1, 6):
                try:
                    driver.get(listing_url)
                except Exception as e:
                    warning(f"URL-resolve navigation failed (attempt {attempt}): {e}")
                    time.sleep(3)
                    continue
                time.sleep(12 if attempt == 1 else 15)

                try:
                    videos = driver.find_elements(By.TAG_NAME, "ytcp-video-row")
                except Exception:
                    videos = []

                if videos:
                    break

                page_text = ""
                try:
                    page_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
                except Exception:
                    page_text = ""
                if any(m in page_text for m in studio_error_markers):
                    warning(
                        f"URL-resolve listing showed an error page (attempt {attempt}/5). Retrying..."
                    )
                    time.sleep(8)
                    continue
                # No rows, no error â€” listing might just be slow. Retry anyway.
                time.sleep(5)

            chosen_href = None
            for row in videos[:15]:
                try:
                    row_text = row.text.strip()
                except Exception:
                    row_text = ""
                if target_match and target_match in row_text:
                    try:
                        chosen_href = row.find_element(By.TAG_NAME, "a").get_attribute("href")
                        break
                    except Exception:
                        continue
            if not chosen_href and videos:
                try:
                    chosen_href = videos[0].find_element(By.TAG_NAME, "a").get_attribute("href")
                except Exception:
                    chosen_href = None

            if chosen_href:
                video_id = chosen_href.split("/")[-2]
                return build_url(video_id)
            return ""
        except Exception as e:
            warning(f"Could not resolve URL via status tab: {e}")
            return ""
        finally:
            try:
                if status_handle and status_handle in driver.window_handles:
                    driver.switch_to.window(status_handle)
                    driver.close()
            except Exception:
                pass
            try:
                if original_handle in driver.window_handles:
                    driver.switch_to.window(original_handle)
            except Exception:
                pass

    def _robust_click(self, driver, element, label: str = "") -> bool:
        """
        Click an element in YouTube Studio in a way that survives the two
        failure modes we keep seeing:

          (a) ElementClickInterceptedException â€” another node (hashtag tooltip,
              tutorial overlay, sticky header) sits on top of the target. The
              standard `.click()` aims at the visual coordinates and hits the
              overlay instead.
          (b) ElementNotInteractableException â€” the element is in the DOM but
              hasn't been scrolled into view yet (long Details panel, the
              visibility radios live way below the fold).

        Strategy: scroll the element to the center of the viewport, try a
        normal click, and if that fails for any reason fall back to a JS click
        which dispatches the event directly on the node and ignores overlays.
        Returns True on success, False if both attempts blow up.
        """
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                element,
            )
            time.sleep(0.4)
        except Exception:
            pass
        try:
            element.click()
            return True
        except Exception as e:
            if get_verbose() and label:
                warning(
                    f"\t=> {label}: standard click intercepted ({type(e).__name__}); "
                    "falling back to JS click."
                )
            try:
                driver.execute_script("arguments[0].click();", element)
                return True
            except Exception as e2:
                if label:
                    warning(f"\t=> {label}: JS click also failed: {str(e2)[:160]}")
                return False

    def _dismiss_still_checking_dialog(self, driver, timeout_s: float = 6.0) -> bool:
        """
        Handle the "We're still checking your content" confirmation dialog that
        YouTube Studio shows after clicking Done when its background checks have
        not finished yet. The default highlighted button is "Go back", so we
        explicitly click "Publish anyway" / "Publicar de todos modos".

        Returns True if a dialog was found and dismissed, False otherwise.
        """
        verbose = get_verbose()
        publish_anyway_labels = (
            "Publish anyway",
            "Publicar de todos modos",
            "Publicar igualmente",
            "Publicar de todas formas",
        )
        text_predicates = " or ".join(
            f"normalize-space(.)='{label}'" for label in publish_anyway_labels
        )
        xpath = (
            "//tp-yt-paper-dialog//*[self::ytcp-button or self::button or self::a]"
            f"[{text_predicates}]"
        )

        deadline = time.time() + timeout_s
        last_err = None
        while time.time() < deadline:
            try:
                candidates = driver.find_elements(By.XPATH, xpath)
                for el in candidates:
                    try:
                        if not el.is_displayed():
                            continue
                    except Exception:
                        continue
                    if verbose:
                        info(
                            "\t=> 'Still checking content' dialog detected; "
                            "clicking 'Publish anyway'..."
                        )
                    if self._robust_click(driver, el, "Publish anyway button"):
                        time.sleep(1.5)
                        return True
            except Exception as e:
                last_err = e
            time.sleep(0.5)

        if verbose and last_err is not None:
            warning(f"\t=> No 'still checking' dialog handled: {str(last_err)[:160]}")
        return False

    def upload_video(self) -> bool:
        """
        Uploads the video to YouTube via Selenium.
        Uses explicit waits and robust element selection for YouTube Studio 2025+.

        Returns:
            success (bool): Whether the upload was successful or not.
        """
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys

        # Guard: refuse to upload if the generation pipeline aborted (e.g.
        # duplicate-topic guard fired).
        if not getattr(self, "video_path", None) or not str(self.video_path).strip():
            error("Cannot upload: no video was generated (video_path is empty).")
            return False
        if not os.path.isfile(self.video_path):
            error(f"Cannot upload: video file not found at '{self.video_path}'.")
            return False
        if not getattr(self, "subject", None) or not str(self.subject).strip():
            error("Cannot upload: subject is empty (pipeline aborted earlier).")
            return False

        self._ensure_browser()
        driver = self.browser
        verbose = get_verbose()
        wait = WebDriverWait(driver, 30)

        try:
            # Step 1: Get channel ID
            if verbose:
                info("\t=> Getting channel ID...")
            self.get_channel_id()
            if verbose:
                info(f"\t=> Channel ID: {self.channel_id}")

            # Step 2: Navigate to upload page
            if verbose:
                info("\t=> Navigating to upload page...")
            driver.get("https://www.youtube.com/upload")
            time.sleep(3)
            if not getattr(self, "channel_id", None):
                channel_id = self._extract_channel_id_from_url(getattr(driver, "current_url", "") or "")
                if channel_id:
                    self.channel_id = channel_id

            # Step 3: Upload the video file
            if verbose:
                info(f"\t=> Uploading file: {self.video_path}")

            # Find the file input (hidden input inside the upload picker)
            file_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )
            file_input.send_keys(self.video_path)

            if verbose:
                info("\t=> File selected, waiting for upload dialog...")

            # Wait for the upload dialog to appear (title textbox)
            time.sleep(8)

            # Step 4: Set title
            if verbose:
                info("\t=> Setting title...")

            # YouTube Studio uses contenteditable divs with id="textbox"
            textboxes = wait.until(
                EC.presence_of_all_elements_located((By.ID, YOUTUBE_TEXTBOX_ID))
            )

            if len(textboxes) < 2:
                warning(f"Expected 2+ textboxes, found {len(textboxes)}")

            title_el = textboxes[0]
            # Use JavaScript click to bypass overlay dialogs (dialog-scrim, social-suggestions)
            # that YouTube Studio renders on top of the title field.
            driver.execute_script("arguments[0].scrollIntoView(true);", title_el)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", title_el)
            time.sleep(0.5)

            # YouTube auto-fills the title with the file's UUID basename when
            # the .mp4 is selected. Without clearing first, our title gets
            # APPENDED to that UUID and the resulting title is "<uuid> <real
            # title>" â€” uglier and over the 100-char limit. Select-all + Delete
            # wipes the prefilled value before typing.
            title_el.send_keys(Keys.CONTROL, "a")
            time.sleep(0.2)
            title_el.send_keys(Keys.DELETE)
            time.sleep(0.3)

            # Type the new title character by character to avoid issues
            clean_title = self.metadata["title"].replace("\n", " ")[:100]
            title_el.send_keys(clean_title)
            time.sleep(1)

            if verbose:
                info(f"\t=> Title set: {clean_title}")

            # Step 5: Set description
            if verbose:
                info("\t=> Setting description...")

            description_el = textboxes[-1]
            # Use JavaScript click to bypass the "Suggested hashtags" panel
            # that YouTube Studio renders between title and description fields.
            # A normal .click() fails with ElementClickInterceptedException.
            driver.execute_script("arguments[0].scrollIntoView(true);", description_el)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", description_el)
            time.sleep(0.5)

            # Clear any pre-filled content (channel default description, etc.)
            # before writing ours. Same Ctrl+A / Delete trick as the title.
            description_el.send_keys(Keys.CONTROL, "a")
            time.sleep(0.2)
            description_el.send_keys(Keys.DELETE)
            time.sleep(0.3)

            clean_desc = self.metadata["description"].replace("\n", " ")[:5000]
            description_el.send_keys(clean_desc)
            time.sleep(1)

            if verbose:
                info("\t=> Description set")

            # Step 6: Set "Not made for kids"
            if verbose:
                info("\t=> Setting 'not made for kids'...")

            try:
                if not get_is_for_kids():
                    not_for_kids = wait.until(
                        EC.presence_of_element_located((By.NAME, YOUTUBE_NOT_MADE_FOR_KIDS_NAME))
                    )
                    self._robust_click(driver, not_for_kids, "kids radio (not for kids)")
                else:
                    for_kids = wait.until(
                        EC.presence_of_element_located((By.NAME, YOUTUBE_MADE_FOR_KIDS_NAME))
                    )
                    self._robust_click(driver, for_kids, "kids radio (made for kids)")
                time.sleep(1)
            except Exception as e:
                warning(f"Could not set kids option: {e}")

            # Step 6.5: Upload custom thumbnail (long videos only â€” set by generate_thumbnail()).
            # Strategy: send_keys() returning without exception is NOT proof that YouTube
            # accepted the file. Empirically, the file can fail to register (busy uploader
            # widget, oversized file, channel not verified, stale input element) while
            # send_keys silently succeeds, and clicking Next then publishes with the
            # auto-generated thumbnail. So: visual verification is REQUIRED before we
            # leave the Details panel; if we can't verify, we retry the whole upload.
            thumb_path = getattr(self, "thumbnail_path", "")
            self._thumbnail_uploaded = False
            if thumb_path and os.path.isfile(thumb_path):
                abs_thumb = os.path.abspath(thumb_path)

                # Pre-flight: YouTube silently rejects thumbnails over 2 MB. If we're
                # over the limit, re-encode as JPEG (quality 90) into a sibling path
                # so the original PNG is preserved for manual recovery.
                YT_THUMB_MAX_BYTES = 2 * 1024 * 1024
                try:
                    fsize = os.path.getsize(abs_thumb)
                except Exception:
                    fsize = 0
                if fsize > YT_THUMB_MAX_BYTES:
                    warning(
                        f"\t=> Thumbnail is {fsize/1024/1024:.2f} MB (>2 MB cap); "
                        "re-encoding as JPEG to fit YouTube's limit."
                    )
                    try:
                        from PIL import Image as _PilImage
                        jpg_path = os.path.splitext(abs_thumb)[0] + "_yt.jpg"
                        with _PilImage.open(abs_thumb) as im:
                            im.convert("RGB").save(jpg_path, "JPEG", quality=90, optimize=True)
                        if os.path.getsize(jpg_path) <= YT_THUMB_MAX_BYTES:
                            abs_thumb = jpg_path
                            info(f"\t=> Re-encoded thumbnail: {abs_thumb} ({os.path.getsize(jpg_path)/1024/1024:.2f} MB)")
                        else:
                            warning(f"\t=> Re-encoded JPEG still over 2 MB; YouTube will likely reject it.")
                    except Exception as e:
                        warning(f"\t=> JPEG re-encode failed: {str(e)[:150]}")

                info(f"\t=> Uploading thumbnail: {abs_thumb}")

                # Scroll the thumbnail editor into view (it's below title/description).
                try:
                    editor = driver.find_element(
                        By.CSS_SELECTOR,
                        "ytcp-thumbnails-compact-editor, ytcp-thumbnail-uploader, ytcp-thumbnails-compact-editor-uploader",
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", editor)
                    time.sleep(1)
                except Exception:
                    pass

                VERIFY_TIMEOUT_S = 180         # YT can take a while to render the preview
                VERIFY_POLL_S = 2
                RETRY_BACKOFF_S = 30
                MAX_ATTEMPTS = 3
                accepted = False
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    info(f"\t=> Thumbnail upload attempt {attempt}/{MAX_ATTEMPTS}...")
                    try:
                        thumb_input = self._find_thumbnail_input(driver, wait)
                        if thumb_input is None:
                            raise RuntimeError("no thumbnail file input found on Details page")
                        # Force the (usually hidden) input to be interactable.
                        driver.execute_script(
                            "arguments[0].style.display='block';"
                            "arguments[0].style.visibility='visible';"
                            "arguments[0].style.opacity='1';"
                            "arguments[0].removeAttribute('hidden');",
                            thumb_input,
                        )
                        thumb_input.send_keys(abs_thumb)
                        info(f"\t=> send_keys dispatched; polling up to {VERIFY_TIMEOUT_S}s for preview...")
                    except Exception as e:
                        warning(f"\t=> send_keys failed on attempt {attempt}: {str(e)[:200]}")
                        if attempt < MAX_ATTEMPTS:
                            time.sleep(RETRY_BACKOFF_S)
                        continue

                    deadline = time.time() + VERIFY_TIMEOUT_S
                    while time.time() < deadline:
                        if self._verify_thumbnail_uploaded(driver):
                            accepted = True
                            break
                        time.sleep(VERIFY_POLL_S)

                    if accepted:
                        success(f"\t=> Thumbnail visually confirmed (attempt {attempt}).")
                        # Give YouTube Studio a few seconds to commit the upload to its
                        # internal video draft state. Empirically, navigating away too
                        # fast can cause the thumbnail to revert to the auto-generated one.
                        time.sleep(5)
                        self._thumbnail_uploaded = True
                        break
                    else:
                        warning(
                            f"\t=> Thumbnail preview NOT detected after {VERIFY_TIMEOUT_S}s on attempt {attempt}."
                        )
                        if attempt < MAX_ATTEMPTS:
                            info(f"\t=> Waiting {RETRY_BACKOFF_S}s before re-trying full upload...")
                            time.sleep(RETRY_BACKOFF_S)

                if not accepted:
                    error(
                        f"Thumbnail upload failed: visual verification never succeeded after {MAX_ATTEMPTS} attempts. "
                        f"The thumbnail file is preserved at:\n    {abs_thumb}\n"
                        "Common causes: channel not verified for custom thumbnails, file > 2 MB, "
                        "or YT Studio DOM changed. Open YouTube Studio â†’ your video â†’ Edit â†’ upload it manually."
                    )
                    try:
                        debug_path = os.path.join(
                            ROOT_DIR, "thumbnails",
                            f"upload_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                        )
                        driver.save_screenshot(debug_path)
                        info(f"\t=> Saved upload-page screenshot for debugging: {debug_path}")
                    except Exception:
                        pass
            elif thumb_path:
                warning(f"\t=> Thumbnail file not found on disk: {thumb_path} (skipping)")

            # Step 7: Click Next 3 times (Details â†’ Video elements â†’ Checks â†’ Visibility)
            for step_num in range(3):
                if verbose:
                    info(f"\t=> Clicking Next (step {step_num + 1}/3)...")
                try:
                    next_btn = wait.until(
                        EC.presence_of_element_located((By.ID, YOUTUBE_NEXT_BUTTON_ID))
                    )
                    if not self._robust_click(driver, next_btn, f"Next step {step_num + 1}/3"):
                        warning(f"Next button step {step_num + 1} could not be clicked.")
                    time.sleep(2)
                except Exception as e:
                    warning(f"Next button step {step_num + 1} failed: {e}")

            # Step 8: Set visibility to Unlisted (radio button index 2)
            if verbose:
                info("\t=> Setting visibility to Unlisted...")

            time.sleep(2)
            try:
                radio_buttons = driver.find_elements(By.XPATH, YOUTUBE_RADIO_BUTTON_XPATH)
                if len(radio_buttons) >= 3:
                    self._robust_click(driver, radio_buttons[2], "visibility radio")  # 0=Private, 1=Unlisted, 2=Public
                elif len(radio_buttons) >= 2:
                    self._robust_click(driver, radio_buttons[1], "visibility radio (fallback idx 1)")
                time.sleep(1)
            except Exception as e:
                warning(f"Could not set visibility: {e}")

            # Step 9: Click Done
            if verbose:
                info("\t=> Clicking Done button...")

            try:
                done_btn = wait.until(
                    EC.presence_of_element_located((By.ID, YOUTUBE_DONE_BUTTON_ID))
                )
                if not self._robust_click(driver, done_btn, "Done button"):
                    warning("Done button could not be clicked.")
            except Exception as e:
                warning(f"Done button failed: {e}")

            # YT Studio sometimes interrupts the publish flow with a
            # "We're still checking your content" confirmation when its
            # background scans have not finished. The default action is
            # "Go back", so force-click "Publish anyway" if present.
            try:
                self._dismiss_still_checking_dialog(driver)
            except Exception as e:
                warning(f"'Still checking content' dialog handler failed: {e}")

            is_long_video = bool(getattr(self, "_is_long_video", False))

            # Lock in the upload-tab handle the moment Done is clicked.
            # From this point on, NOTHING is allowed to navigate, refresh,
            # or close this tab until the upload + processing is verified
            # done â€” doing so cancels the in-flight HTTP transfer.
            try:
                self._upload_tab_handle = driver.current_window_handle
            except Exception:
                self._upload_tab_handle = None

            # CRITICAL: persist the cache entry RIGHT NOW with a placeholder URL.
            # Even if Firefox crashes / network drops mid-upload, the title, description,
            # subject and date are saved so nothing is lost.
            cache_entry = {
                "title": self.metadata["title"],
                "description": self.metadata["description"],
                "subject": self.subject,
                "url": "uploading...",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "thumbnail_path": getattr(self, "thumbnail_path", "") or "",
                "is_short": not is_long_video,
                "retention_mode": getattr(self, "_retention_mode", "") or "",
                "retention_score": (
                    (getattr(self, "retention_preflight", {}) or {}).get("final_score")
                    or (getattr(self, "retention_preflight", {}) or {}).get("score")
                ),
                "hook_score": (getattr(self, "retention_hook_lab", {}) or {}).get("best_score"),
                "first_image_score": (
                    ((getattr(self, "visual_preflight", {}) or {}).get("first_image") or {}).get("score")
                ),
                "platform_uploads": {
                    "youtube": {
                        "status": "pending",
                        "url": None,
                        "updated_at": None,
                        "error": "",
                    }
                },
            }
            try:
                self.add_video(cache_entry)
                if verbose:
                    info("\t=> Cache entry saved (with placeholder URL)")
            except Exception as e:
                warning(f"Could not pre-save cache entry: {e}")

            # Step 9.5: Wait for the file transfer to actually finish.
            # Both long videos and Shorts now use the SAME strategy: poll the
            # channel listing in a SEPARATE tab so the upload tab is never
            # navigated/refreshed (which would cancel the upload). The only
            # differences are the listing URL and the timeouts.
            if not getattr(self, "channel_id", None):
                try:
                    # NEVER navigate the upload tab during an in-flight upload.
                    # Resolve channel_id on a side tab instead.
                    self._get_channel_id_safe()
                except Exception as e:
                    warning(f"Could not resolve channel_id before upload wait: {e}")

            if is_long_video:
                if verbose:
                    info("\t=> Long video â€” polling listing page in a separate tab...")
                upload_finished = self._wait_for_listing_settled(
                    driver,
                    listing_tab="long",
                    kind_label="long video",
                    max_wait_s=10800,        # 3h total cap (HD 30+ min videos can take a while to encode)
                    poll_interval_s=15,
                    refresh_interval_s=120,  # refresh status tab every 2 min
                )
            else:
                if verbose:
                    info("\t=> Short video â€” polling listing page in a separate tab...")
                upload_finished = self._wait_for_listing_settled(
                    driver,
                    listing_tab="short",
                    kind_label="Short",
                    max_wait_s=1800,         # 30 min total cap
                    poll_interval_s=8,
                    refresh_interval_s=60,
                )

            # Step 10: Get the video URL.
            # For long videos we ALWAYS resolve via a separate tab â€” even when
            # the wait succeeded, navigating the original tab is risky if any
            # background processing is still in flight, and the user has asked
            # that the upload tab never be touched programmatically.
            if verbose:
                info("\t=> Getting video URL...")

            listing_tab = "long" if is_long_video else "short"
            url = None

            if is_long_video:
                # Only attempt URL resolution if the upload genuinely finished.
                # If wait_for_listing_settled timed out or fell back, the upload
                # may still be in flight â€” opening another tab is safe but
                # adds noise. Skip silently and let the user verify manually.
                if upload_finished:
                    url = self._resolve_video_url_safe(driver, listing_tab) or None
                else:
                    warning(
                        "\t=> Upload not confirmed within wait window. "
                        "Skipping URL resolution; the upload tab is left untouched "
                        "so any in-flight transfer can complete."
                    )
            else:
                # Shorts: original behavior (navigate the same tab â€” Firefox is
                # about to be closed anyway when the short upload is confirmed).
                if not getattr(self, "channel_id", None):
                    warning("Could not get video URL: channel ID was not resolved.")
                else:
                    try:
                        driver.get(
                            f"https://studio.youtube.com/channel/{self.channel_id}/videos/{listing_tab}"
                        )
                        time.sleep(3)

                        target_title = (self.metadata.get("title") or "").strip()
                        videos = driver.find_elements(By.TAG_NAME, "ytcp-video-row")

                        chosen_href = None
                        for row in videos[:15]:
                            try:
                                row_text = row.text.strip()
                            except Exception:
                                row_text = ""
                            if target_title and target_title[:50] in row_text:
                                try:
                                    chosen_href = row.find_element(By.TAG_NAME, "a").get_attribute("href")
                                    break
                                except Exception:
                                    continue

                        if not chosen_href and videos:
                            try:
                                chosen_href = videos[0].find_element(By.TAG_NAME, "a").get_attribute("href")
                            except Exception:
                                chosen_href = None

                        if chosen_href:
                            if verbose:
                                info(f"\t=> Found URL: {chosen_href}")
                            video_id = chosen_href.split("/")[-2]
                            url = build_url(video_id)
                    except Exception as e:
                        warning(f"Could not get video URL: {e}")

            if url:
                self.uploaded_video_url = url
                success(f" => Uploaded Video: {url}")
                # Update the placeholder cache entry with the real URL.
                try:
                    self._update_last_video_url(cache_entry["date"], url)
                except Exception as e:
                    warning(f"Could not update cache URL: {e}")
            else:
                self.uploaded_video_url = "https://studio.youtube.com"
                warning(" => Could not retrieve video URL â€” check YouTube Studio manually. "
                        "Cache entry has placeholder URL.")

            # CRITICAL: never auto-close Firefox for long videos. The user has explicitly
            # asked that the browser stay open through upload + processing + verification
            # so they can manually confirm everything before closing it.
            #
            # For shorts: only close Firefox if we BOTH (a) saw the wait-for-upload
            # finish cleanly AND (b) successfully retrieved the public URL. Otherwise
            # leave it open so the user can confirm manually â€” same philosophy as long
            # videos, just less verbose.
            if is_long_video:
                info("=" * 60)
                if upload_finished:
                    info(" Long video upload finished. Firefox is staying OPEN.")
                else:
                    warning(" Long video upload was NOT confirmed within the wait window.")
                    warning(" Firefox is staying OPEN so any in-flight upload can finish.")
                info(" â†’ DO NOT close Firefox or change the upload tab until")
                info("   YouTube Studio shows the video as Public/Unlisted")
                info("   (NOT 'Subiendo', 'Procesando' or 'Pendiente').")
                info(" â†’ Once verified, close Firefox manually.")
                info("=" * 60)
            else:
                short_confirmed = bool(upload_finished) and bool(url)
                if short_confirmed:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                else:
                    warning("=" * 60)
                    warning(" Short upload could NOT be fully confirmed. Firefox is staying OPEN.")
                    if not upload_finished:
                        warning(" â†’ Wait-for-upload did not complete cleanly within the timeout.")
                    if not url:
                        warning(" â†’ Could not retrieve the public video URL.")
                    warning(" â†’ Verify in YouTube Studio that the short shows as Public/Unlisted,")
                    warning("   then close Firefox manually.")
                    warning("=" * 60)

            if getattr(self, "_defer_upload_cleanup", False):
                info(" => Post-upload cleanup deferred until the remaining selected platforms finish.")
            else:
                try:
                    from upload_tracker import mark_uploaded, cleanup_uploaded
                    if mark_uploaded(self.video_path, getattr(self, "uploaded_video_url", None)):
                        removed = cleanup_uploaded()
                        if removed and get_verbose():
                            info(f" => Cleaned up {removed} uploaded asset(s) from .mp/")
                except Exception as _e:
                    warning(f"Post-upload cleanup skipped: {_e}")

            return True

        except Exception as e:
            import traceback
            error(f"Upload failed: {e}")
            traceback.print_exc()
            # DO NOT quit the driver on exception â€” the upload may still be in flight
            # in the background and closing Firefox would abort it. Keep the browser
            # open in BOTH long-video and short modes so the user can confirm what
            # actually made it to YouTube before closing manually.
            warning("Leaving Firefox open so the upload can finish in the background. "
                    "Close the browser manually after YouTube Studio shows the upload is done.")
            return False

    def _update_last_video_url(self, date_marker: str, new_url: str) -> None:
        """Update the URL field of the cache entry that matches `date_marker`."""
        cache = get_youtube_cache_path()
        with json_write_lock(cache):
            with open(cache, "r", encoding="utf-8") as f:
                data = json.load(f)
            for account in data.get("accounts", []):
                if account.get("id") != self._account_uuid:
                    continue
                for video in account.get("videos", []):
                    if video.get("date") == date_marker and video.get("url") in ("uploading...", "", None):
                        video["url"] = new_url
                        statuses = video.setdefault("platform_uploads", {})
                        statuses["youtube"] = {
                            "status": "uploaded",
                            "url": new_url,
                            "updated_at": datetime.utcnow().isoformat() + "Z",
                            "error": "",
                        }
                        break
            with open(cache, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

    def get_videos(self) -> List[dict]:
        """
        Gets the uploaded videos from the YouTube Channel.

        Returns:
            videos (List[dict]): The uploaded videos.
        """
        if not os.path.exists(get_youtube_cache_path()):
            # Create the cache file
            with open(get_youtube_cache_path(), "w", encoding="utf-8") as file:
                json.dump({"videos": []}, file, indent=4)
            return []

        videos = []
        # Read the cache file
        with open(get_youtube_cache_path(), "r", encoding="utf-8") as file:
            previous_json = json.loads(file.read())
            # Find our account
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    videos = account["videos"]

        return videos
