import os
import re
import json
import random
import zipfile
import requests
import platform
import unicodedata

from status import error, info, success, warning
from config import ROOT_DIR, assert_folder_structure, get_first_time_running, get_nanobanana2_api_key, get_nanobanana2_aspect_ratio, get_threads, get_verbose, get_zip_url

DEFAULT_SONG_ARCHIVE_URLS = []


_ROMAN_ORDINALS_ES = {
    1: "primero", 2: "segundo", 3: "tercero", 4: "cuarto", 5: "quinto",
    6: "sexto", 7: "séptimo", 8: "octavo", 9: "noveno", 10: "décimo",
}
_ROMAN_CARDINALS_ES = {
    11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
    16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve",
    20: "veinte", 21: "veintiuno", 22: "veintidós", 23: "veintitrés",
    24: "veinticuatro", 25: "veinticinco", 26: "veintiséis",
    27: "veintisiete", 28: "veintiocho", 29: "veintinueve", 30: "treinta",
}


def _roman_to_int(roman: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total, prev = 0, 0
    for ch in reversed(roman.upper()):
        v = vals.get(ch, 0)
        if v == 0:
            return 0
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total


def _int_to_roman(n: int) -> str:
    if n <= 0:
        return ""
    pairs = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
             (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
             (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, s in pairs:
        while n >= v:
            out += s
            n -= v
    return out


_REGNAL_PATTERN = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ'’`´]+)\s+([IVXLCDM]+)\b(?![A-Za-záéíóúñ])"
)


def _regnal_replacement_word(roman: str) -> str:
    """Return the Spanish word for a canonical Roman numeral 1-30, or '' if rejected."""
    roman = roman.upper()
    n = _roman_to_int(roman)
    if n < 1 or n > 30:
        return ""
    if _int_to_roman(n) != roman:  # reject non-canonical like IIII, VX
        return ""
    return _ROMAN_ORDINALS_ES.get(n) or _ROMAN_CARDINALS_ES.get(n, "")


def expand_regnal_numerals(text: str) -> str:
    """
    Replace '<ProperNoun> <RomanNumeral>' with Spanish words so TTS pronounces
    regnal numerals correctly. Example: 'Cosimo I' -> 'Cosimo primero',
    'Luis XIV' -> 'Luis catorce', 'Benedicto XVI' -> 'Benedicto dieciséis'.

    Convention: 1-10 -> ordinal (primero, segundo...), 11-30 -> cardinal
    (once, doce...). Numerals outside 1-30 and non-canonical forms are left
    untouched. Only fires when preceded by a capitalized token (proper noun
    guard) to avoid mangling stray capital I/V/X tokens.
    """
    def repl(m: re.Match) -> str:
        name, roman = m.group(1), m.group(2).upper()
        word = _regnal_replacement_word(roman)
        return f"{name} {word}" if word else m.group(0)

    return _REGNAL_PATTERN.sub(repl, text)


def expand_regnal_numerals_tracked(text: str) -> tuple[str, list[tuple[str, str]]]:
    """
    Like expand_regnal_numerals, but also returns an ordered list of
    (spoken_word, original_roman) tuples for each substitution made.

    Use this when you want TTS to *pronounce* the expanded form but want
    subtitles/word-timestamps to display the original Roman numeral. After
    TTS runs, call `restore_regnal_numerals_in_timestamps` with this list.
    """
    replacements: list[tuple[str, str]] = []

    def repl(m: re.Match) -> str:
        name, roman = m.group(1), m.group(2).upper()
        word = _regnal_replacement_word(roman)
        if not word:
            return m.group(0)
        replacements.append((word, roman))
        return f"{name} {word}"

    expanded = _REGNAL_PATTERN.sub(repl, text)
    return expanded, replacements


def restore_regnal_numerals_in_timestamps(timestamps, replacements):
    """
    Walk word_timestamps in order; for each (spoken_word, original_roman) pair,
    find the first remaining entry whose word matches `spoken_word` and swap
    it back to `original_roman`. Timing is preserved.
    """
    if not timestamps or not replacements:
        return timestamps
    ri = 0
    for ts in timestamps:
        if ri >= len(replacements):
            break
        spoken, original = replacements[ri]
        if ts.get("word", "").strip().lower() == spoken.lower():
            ts["word"] = original
            ri += 1
    return timestamps


def expand_spoken_symbols(text: str) -> str:
    """
    Replace symbols the TTS can't pronounce (and that our whitelist strips)
    with their Spanish spoken form, so both narration and subtitles render
    naturally. Must run BEFORE clean_script_for_tts.

    Example: '90%' -> '90 por ciento'.
    """
    # "90%" / "90 %" / "90.5%" -> "90 por ciento"
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*%", r"\1 por ciento", text)
    # Bare "%" on its own (rare but possible) -> " por ciento"
    text = re.sub(r"%", " por ciento", text)
    return text


# Stage-direction keywords. If a parenthetical or bracket block STARTS with one
# of these, it's the LLM leaking video direction into the narration and gets
# stripped before TTS. Examples this catches:
#   "(imagen de un samurái)" → ""
#   "[B-roll: sol iluminando filo de espada]" → ""
#   "(plano cerrado del rostro)" → ""
#   "(música suave de fondo)" → ""
_STAGE_KEYWORDS = (
    r"im[aá]gen(?:es)?|"
    r"escena|escenario|plano|plano\s+(?:cerrado|abierto|general|medio)|"
    r"secuencia|toma|encuadre|corte|"
    r"transici[oó]n|fundido|disuelve|fade|cut|"
    r"zoom|paneo|paneando|paneo\s+lento|"
    r"emoji|emoticono|emoticonos|s[ií]mbolo\s+de|"
    r"b[\s./_-]?roll|b[\s./_-]?o\b|voz\s+en\s+off|narrador|locutor|"
    r"m[uú]sica|sonido|sonidos|efecto|efectos|sfx|fx|ruido|ambiente|"
    r"subt[ií]tulo|caption|insertar|insert|nota\s+del\s+editor|"
    r"intro\s*:|outro\s*:|cierre\s*:|"
    r"foto\s+de|fotograf[ií]a\s+de|video\s+de|clip\s+de"
)
_STAGE_PAREN_RE = re.compile(rf"\(\s*(?:{_STAGE_KEYWORDS})[^)]*\)", re.IGNORECASE)
_STAGE_BRACKET_RE = re.compile(rf"\[\s*(?:{_STAGE_KEYWORDS})[^\]]*\]", re.IGNORECASE)
_STAGE_LINE_RE = re.compile(
    rf"^\s*(?:{_STAGE_KEYWORDS})\s*[:\-—–][^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)


def strip_stage_directions(text: str) -> str:
    """
    Remove video-direction artifacts that the LLM sometimes leaks into the
    narration. Must run BEFORE the TTS reads the script aloud, otherwise the
    voice ends up saying things like "imagen de cara de emoticono sonriente"
    or "B O imagen de sol iluminando filo de espada".

    Strips:
      - "(imagen de ...)" / "(plano ...)" / "(música ...)" / "(emoji ...)"
      - "[B-roll: ...]" / "[plano cerrado ...]"
      - Whole lines that start with "Imagen:" / "Plano:" / "Música:" etc.

    Conservative: only fires when the parenthetical/bracket BEGINS with a
    known stage-direction keyword, so legitimate parentheticals
    ("(siglo XV)", "(Florencia, 1469)") survive.
    """
    if not text:
        return text
    text = _STAGE_PAREN_RE.sub("", text)
    text = _STAGE_BRACKET_RE.sub("", text)
    text = _STAGE_LINE_RE.sub("", text)
    # Collapse whitespace artifacts left by the strips.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +([.,;:!?])", r"\1", text)  # space-then-punct cleanup
    return text.strip()


def expand_spanish_numbers(text: str) -> str:
    """
    Convert digit strings to Spanish words so the TTS reads them as numbers
    instead of digit-by-digit. Must run BEFORE the TTS step, AFTER
    expand_regnal_numerals (so "Luis XIV" is already "Luis catorce" and we
    don't accidentally re-touch it).

    Handles:
      - Thousand separators (Spanish style):  "4.500" → "cuatro mil quinientos"
      - Decimals:                              "4,5"   → "cuatro coma cinco"
                                               "3.14"  → "tres punto uno cuatro"
      - Bare integers:                         "1453"  → "mil cuatrocientos cincuenta y tres"

    Distinguishing thousand-separator dots from decimal dots: a dot followed
    by exactly 3 digits is treated as a thousands separator (Spanish
    convention "1.000.000"). A dot followed by 1-2 digits is a decimal.
    """
    if not text:
        return text
    try:
        from num2words import num2words
    except Exception:
        # Library not available — leave the digits alone rather than crash.
        return text

    def _to_words(n: int) -> str:
        try:
            return num2words(n, lang="es")
        except Exception:
            return str(n)

    # 1. Thousand-separator integers: 1.000, 4.500, 1.234.567, 4,500
    #    Pattern: 1-3 digits, then one or more groups of (dot or comma)+(exactly 3 digits).
    def _thousand_repl(m: re.Match) -> str:
        digits = re.sub(r"[.,]", "", m.group(0))
        try:
            return _to_words(int(digits))
        except ValueError:
            return m.group(0)
    text = re.sub(r"\b\d{1,3}(?:[.,]\d{3})+\b", _thousand_repl, text)

    # 2. Decimals: 4,5 / 3.14 / 0,75
    def _decimal_repl(m: re.Match) -> str:
        whole, sep, frac = m.group(1), m.group(2), m.group(3)
        try:
            whole_w = _to_words(int(whole))
        except ValueError:
            return m.group(0)
        spoken_sep = "coma" if sep == "," else "punto"
        # Read each fractional digit one by one (standard Spanish convention
        # for decimals: "tres coma uno cuatro").
        digits_w = " ".join(_to_words(int(d)) for d in frac)
        return f"{whole_w} {spoken_sep} {digits_w}"
    text = re.sub(r"\b(\d+)([.,])(\d{1,2})\b", _decimal_repl, text)

    # 3. Plain integers (anything that survived steps 1-2).
    def _int_repl(m: re.Match) -> str:
        try:
            return _to_words(int(m.group(0)))
        except ValueError:
            return m.group(0)
    text = re.sub(r"\b\d+\b", _int_repl, text)

    return text


def clean_script_for_tts(text: str) -> str:
    """
    Sanitize script text for TTS and subtitles while PRESERVING punctuation
    that drives natural pacing: commas, colons, semicolons, em-dashes,
    ellipsis, parentheses, and Spanish opening marks (¿¡).
    Strips only markdown/control chars the LLM sometimes leaks.
    """
    # Expand spoken symbols (%, etc.) first so they aren't silently dropped
    # by the whitelist below.
    text = expand_spoken_symbols(text)
    # Remove markdown / stray formatting chars that confuse TTS
    text = re.sub(r"[*_`#\[\]{}|\\<>]", "", text)
    # Collapse multiple spaces
    text = re.sub(r"[ \t]+", " ", text)
    # Remove any remaining chars outside a safe whitelist
    text = re.sub(r"[^\w\s.,;:!?¿¡\-—–…()'\"’“”\n]", "", text)
    return text.strip()


def close_running_selenium_instances() -> None:
    """
    Closes any running Selenium instances.

    Returns:
        None
    """
    try:
        info(" => Closing running Selenium instances...")

        # Kill all running Firefox instances
        if platform.system() == "Windows":
            os.system("taskkill /f /im firefox.exe")
        else:
            os.system("pkill firefox")

        success(" => Closed running Selenium instances.")

    except Exception as e:
        error(f"Error occurred while closing running Selenium instances: {str(e)}")


def build_url(youtube_video_id: str) -> str:
    """
    Builds the URL to the YouTube video.

    Args:
        youtube_video_id (str): The YouTube video ID.

    Returns:
        url (str): The URL to the YouTube video.
    """
    return f"https://www.youtube.com/watch?v={youtube_video_id}"


def rem_temp_files() -> None:
    """
    Removes temporary files in the `.mp` directory and MoviePy temp files in project root.

    Returns:
        None
    """
    # Path to the `.mp` directory
    mp_dir = os.path.join(ROOT_DIR, ".mp")

    files = os.listdir(mp_dir)

    # Keep .json (cache state) AND .mp4 (rendered videos pending re-upload).
    # MP4s are preserved so the user can pick "Re-upload last generated video"
    # in the menu even after the menu loop has cycled.
    KEEP_EXT = (".json", ".mp4")
    for file in files:
        if file.lower().endswith(KEEP_EXT):
            continue
        try:
            os.remove(os.path.join(mp_dir, file))
        except Exception:
            pass

    # Clean MoviePy temp files from project root
    for file in os.listdir(ROOT_DIR):
        if "TEMP_MPY" in file:
            try:
                os.remove(os.path.join(ROOT_DIR, file))
            except Exception:
                pass


def fetch_songs() -> None:
    """
    Downloads songs into songs/ directory to use with geneated videos.

    Returns:
        None
    """
    try:
        info(f" => Fetching songs...")

        files_dir = os.path.join(ROOT_DIR, "Songs")
        if not os.path.exists(files_dir):
            os.mkdir(files_dir)
            if get_verbose():
                info(f" => Created directory: {files_dir}")
        else:
            existing_audio_files = [
                name
                for name in os.listdir(files_dir)
                if os.path.isfile(os.path.join(files_dir, name))
                and name.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg"))
            ]
            if len(existing_audio_files) > 0:
                return

        configured_url = get_zip_url().strip()
        download_urls = [configured_url] if configured_url else []
        download_urls.extend(DEFAULT_SONG_ARCHIVE_URLS)

        archive_path = os.path.join(files_dir, "songs.zip")
        downloaded = False

        for download_url in download_urls:
            try:
                response = requests.get(download_url, timeout=60)
                response.raise_for_status()

                with open(archive_path, "wb") as file:
                    file.write(response.content)

                SAFE_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
                with zipfile.ZipFile(archive_path, "r") as zf:
                    for member in zf.namelist():
                        basename = os.path.basename(member)
                        if not basename or not basename.lower().endswith(SAFE_EXTENSIONS):
                            warning(f"Skipping non-audio file in archive: {member}")
                            continue
                        if ".." in member or member.startswith("/"):
                            warning(f"Skipping suspicious path in archive: {member}")
                            continue
                        zf.extract(member, files_dir)

                downloaded = True
                break
            except Exception as err:
                warning(f"Failed to fetch songs from {download_url}: {err}")

        if not downloaded:
            raise RuntimeError(
                "Could not download a valid songs archive from any configured URL"
            )

        # Remove the zip file
        if os.path.exists(archive_path):
            os.remove(archive_path)

        success(" => Downloaded Songs to ../Songs.")

    except Exception as e:
        error(f"Error occurred while fetching songs: {str(e)}")


# Per-song theme tags for sci-fi / cosmos / futurism content. Each track is
# scored against the video subject by counting keyword hits. To add a new
# track: drop the file into Songs/ and add a key here with mood-specific
# keywords. Songs not listed still get picked when no track scores above 0.
SONG_KEYWORDS = {
    "infinity_cosmos.mp3": [
        # Vasto, contemplativo — escala del universo, cosmología
        "universo", "cosmos", "cosmico", "cósmico", "cosmica", "cósmica",
        "infinito", "infinita", "infinitud", "eterno", "eterna",
        "galaxia", "galaxias", "via lactea", "vía láctea",
        "big bang", "expansion", "expansión", "origen del universo",
        "cosmologia", "cosmología", "astronomia", "astronomía",
        "universe", "cosmic", "infinity", "galaxy", "cosmos",
    ],
    "vastness_space.mp3": [
        # Ambient profundo, escala/inmensidad — espacio profundo, filosofía cósmica
        "espacio profundo", "deep space", "vacio", "vacío",
        "inmensidad", "vastedad", "soledad cosmica", "soledad cósmica",
        "nebulosa", "nebulosas", "supernova", "supernovas",
        "agujero negro", "agujeros negros", "black hole",
        "horizonte de eventos", "singularidad",
        "vastness", "void", "deep space", "nebula",
    ],
    "light_years_space.mp3": [
        # Contemplativo, exploración — distancias, estrellas, exoplanetas
        "estrella", "estrellas", "star", "stars",
        "exoplaneta", "exoplanetas", "exoplanet",
        "anos luz", "años luz", "light year", "light years",
        "constelacion", "constelación", "constelaciones",
        "sistema solar", "kepler", "proxima centauri", "alpha centauri",
        "viaje interestelar", "interestelar", "interstellar",
        "exploracion espacial", "exploración espacial",
        "sol", "luna", "mercurio", "venus", "marte", "jupiter", "júpiter",
        "saturno", "urano", "neptuno", "pluton", "plutón",
    ],
    "red_lights_adhafera.mp3": [
        # Misterioso, alarmante — alienigenas, señales, fenomenos extraños
        "alienigena", "alienígena", "alienigenas", "alienígenas", "alien", "aliens",
        "extraterrestre", "extraterrestres", "ovni", "ovnis", "ufo",
        "señal", "señales", "signal", "fast radio burst", "frb",
        "wow signal", "seti", "contacto", "primer contacto",
        "fenómeno", "fenomeno", "anomalia", "anomalía", "anomalias", "anomalías",
        "misterio cosmico", "misterio cósmico", "misterio espacial",
        "encrucijada", "perdido en el espacio",
        "mystery", "anomaly", "alien", "extraterrestrial", "signal",
    ],
    "scifi_game.mp3": [
        # Energético, acción — combate, naves, accion sci-fi
        "nave", "naves", "spaceship", "starship",
        "combate", "batalla espacial", "guerra espacial",
        "imperio galactico", "imperio galáctico", "federacion", "federación",
        "rebelión", "rebelion", "rebellion",
        "laser", "láser", "blaster", "fotones",
        "piloto", "flota", "armada", "war", "battle", "fleet",
        "mission", "mision", "misión", "expedicion", "expedición",
    ],
    "transcending_science.mp3": [
        # Triunfal, esperanzador — tecnología, descubrimiento, breakthrough
        "tecnologia", "tecnología", "technology",
        "ciencia", "cientifico", "científico", "cientifica", "científica",
        "descubrimiento", "descubrimientos", "discovery",
        "innovacion", "innovación", "innovation",
        "futuro", "futurismo", "future", "futurism",
        "inteligencia artificial", "ia", "ai", "artificial intelligence",
        "robot", "robots", "robotica", "robótica", "androide",
        "biotecnologia", "biotecnología", "genetica", "genética",
        "computacion cuantica", "computación cuántica", "quantum",
        "nanotecnologia", "nanotecnología", "fusion", "fusión",
        "avance", "progreso", "breakthrough",
    ],
    "trouble_on_mercury.mp3": [
        # Tenso, aventura — colonias, problemas en misiones, planetas
        "marte", "mars", "mercurio", "mercury",
        "venus", "luna", "moon", "colonia", "colonias", "colony",
        "terraformacion", "terraformación", "terraforming",
        "rover", "perseverance", "curiosity",
        "astronauta", "astronautas", "astronaut", "cosmonauta",
        "estacion espacial", "estación espacial", "iss",
        "mision espacial", "misión espacial",
        "elon musk", "spacex", "nasa", "esa",
        "supervivencia", "perdido", "varado",
        "expedicion", "expedición",
    ],
    "feedback_dreams.mp3": [
        # Surreal, onírico — consciencia, dimensiones, paradojas, sueños
        "tiempo", "viaje en el tiempo", "time travel",
        "paradoja", "paradojas", "paradox",
        "dimension", "dimensión", "dimensiones", "multiverso", "multiverse",
        "realidad", "realidades", "simulacion", "simulación", "simulation",
        "consciencia", "conciencia", "consciousness",
        "sueño", "sueños", "dream", "dreams", "lucido", "lúcido",
        "mente", "cerebro", "mind",
        "dejavu", "déjà vu", "memoria",
        "filosofia", "filosofía", "metafisica", "metafísica",
        "cuantica", "cuántica", "quantum", "schrodinger", "schrödinger",
        "teoria de cuerdas", "teoría de cuerdas",
    ],
    "cold_moon.mp3": [
        # Sombrío, aislado — lunas, mundos congelados, soledad cósmica
        "luna", "lunas", "moon", "moons",
        "europa", "titán", "titan", "encelado", "enceladus", "io", "ganimedes",
        "frio", "frío", "congelado", "congelada", "hielo", "ice", "frozen",
        "desolado", "desolada", "abandonado", "abandonada",
        "soledad", "aislamiento", "isolation",
        "perdido en el espacio", "naufragio espacial",
        "criogenia", "criogenico", "criogénico", "hibernacion", "hibernación",
    ],
    "blazing_stars.mp3": [
        # Energético, brillante — fenómenos estelares intensos
        "supernova", "supernovas", "supernova explosion",
        "explosion estelar", "explosión estelar", "estrella moribunda",
        "nacimiento estelar", "formacion estelar", "formación estelar",
        "quasar", "quasares", "pulsar", "pulsares", "magnetar",
        "rayos gamma", "gamma ray burst",
        "energia oscura", "energía oscura", "dark energy",
        "fusion nuclear", "fusión nuclear", "nucleo solar", "núcleo solar",
        "tormenta solar", "llamarada solar",
    ],
    "the_darkness_below.mp3": [
        # Horror cósmico, pavor — abismo, lo desconocido, agujeros negros
        "agujero negro", "agujeros negros", "black hole", "black holes",
        "horizonte de eventos", "event horizon", "singularidad", "singularity",
        "materia oscura", "dark matter", "antimateria", "antimatter",
        "abismo", "abyss", "vacio cosmico", "vacío cósmico",
        "horror", "horror cosmico", "horror cósmico", "lovecraft", "lovecraftiano",
        "dread", "terror", "tenebroso", "siniestro",
        "lo desconocido", "the unknown", "fin del universo", "end of universe",
        "muerte termica", "muerte térmica", "heat death",
    ],
    "world_of_automatons.mp3": [
        # Mecánico, frío tech — IA, robots, automatización
        "robot", "robots", "androide", "androides", "android", "androids",
        "automatas", "autómatas", "automaton", "automatons",
        "inteligencia artificial", "artificial intelligence", "ai", "ia",
        "machine learning", "aprendizaje automatico", "aprendizaje automático",
        "consciencia artificial", "consciencia artificial",
        "uprising", "rebelion robot", "rebelión robot", "skynet",
        "singularidad tecnologica", "singularidad tecnológica",
        "cyborg", "cíborg", "transhumanismo", "posthumano", "poshumano",
        "automation", "automatizacion", "automatización",
    ],
    "dark_techno_city.mp3": [
        # Cyberpunk denso, urbano dark — ciudades distópicas, neon, hacking
        "cyberpunk", "ciberpunk", "dystopia", "distopia", "distopía", "distopico", "distópico",
        "neon", "neón", "neo tokyo", "neo-tokyo", "blade runner",
        "megaciudad", "megalopolis", "megalópolis", "megacity",
        "vigilancia", "surveillance", "panopticon", "panóptico",
        "corporacion", "corporación", "corporaciones", "corporate dystopia",
        "implante", "implantes", "implant", "augmentacion", "augmentación",
        "matrix", "ghost in the shell", "akira",
    ],
    "information_shutdown.mp3": [
        # Tenso, digital — hacking, ciberataques, datos
        "hacking", "hacker", "hackers", "ciberataque", "cyberattack",
        "ciberguerra", "cyber warfare",
        "datos", "data breach", "filtracion", "filtración",
        "internet", "red", "darknet", "dark web", "deep web",
        "malware", "virus informatico", "virus informático", "ransomware",
        "criptografia", "criptografía", "cryptography", "encriptacion", "encriptación",
        "blockchain", "criptomoneda", "criptomonedas", "bitcoin",
        "deep fake", "deepfake", "manipulacion", "manipulación",
    ],
    "theyre_here.mp3": [
        # Suspense alien, llegada — UFO, contacto, invasión
        "invasion", "invasión", "invasion alienigena", "invasión alienígena",
        "llegada", "arrival", "primer contacto", "first contact",
        "ovni avistamiento", "avistamiento", "abduccion", "abducción",
        "area 51", "área 51", "roswell",
        "cuerpo extraño", "circulos de cosechas", "círculos de cosechas", "crop circle",
        "men in black", "hombres de negro",
        "anunnaki", "antiguos astronautas", "ancient aliens",
        "they live", "predator", "alien", "depredador",
    ],
    "urban_jungle_2061.mp3": [
        # Futurismo urbano — ciudades del futuro, distopía suave
        "futuro", "future", "siglo xxii", "año 2050", "año 2100",
        "ciudad del futuro", "city of the future",
        "vehiculos voladores", "vehículos voladores", "coches voladores", "flying cars",
        "smart city", "ciudad inteligente",
        "rascacielos", "skyscraper", "vertical city",
        "transporte hyperloop", "hyperloop", "maglev",
        "realidad virtual", "vr", "virtual reality",
        "metaverso", "metaverse",
        "exoesqueleto", "exoskeleton",
    ],
    "creature_from_the_dark_lagoon.mp3": [
        # Horror biológico — criaturas alienígenas, vida extraña
        "criatura", "criaturas", "creature", "creatures", "monstruo", "monstruos",
        "vida extraterrestre", "alien life", "exobiologia", "exobiología",
        "astrobiologia", "astrobiología", "biosfera",
        "parasito", "parásito", "parasite", "xenomorfo",
        "mutacion", "mutación", "mutante",
        "extinción", "extincion", "extinction", "evolucion", "evolución",
        "dinosaurio", "dinosaurios", "dinosaur",
        "leviatan", "leviatán", "kraken",
        "jurassic", "jurásico", "alien creature",
    ],
    "factory_on_mercury.mp3": [
        # Industrial sci-fi — minería espacial, colonias industriales
        "mineria", "minería", "mining", "asteroide", "asteroides", "asterodide",
        "cinturon de asteroides", "cinturón de asteroides", "asteroid belt",
        "fabrica espacial", "fábrica espacial", "factory", "industrial",
        "recurso", "recursos", "helio 3", "helio-3", "tritio",
        "colonia industrial", "explotacion", "explotación",
        "robot industrial", "automatizacion industrial", "automatización industrial",
        "estacion minera", "estación minera",
        "proyecto manhattan", "ingenieria", "ingeniería", "megaestructura",
    ],
}

# Tracks attributable to Eric Matyas (soundimage.org). The license is "free
# for commercial use with credit" — every video using one of these MUST credit
# the artist in its YouTube description. Listed explicitly (not derived from
# SONG_KEYWORDS.keys()) so users can drop a non-Matyas track into Songs/ and
# add it to SONG_KEYWORDS without falsely attributing it.
SOUNDIMAGE_TRACKS = frozenset({
    "blazing_stars.mp3",
    "cold_moon.mp3",
    "creature_from_the_dark_lagoon.mp3",
    "dark_techno_city.mp3",
    "factory_on_mercury.mp3",
    "feedback_dreams.mp3",
    "infinity_cosmos.mp3",
    "information_shutdown.mp3",
    "light_years_space.mp3",
    "red_lights_adhafera.mp3",
    "scifi_game.mp3",
    "the_darkness_below.mp3",
    "theyre_here.mp3",
    "transcending_science.mp3",
    "trouble_on_mercury.mp3",
    "urban_jungle_2061.mp3",
    "vastness_space.mp3",
    "world_of_automatons.mp3",
})

MATYAS_ATTRIBUTION = "Music by Eric Matyas — www.soundimage.org"


def is_soundimage_track(path_or_name: str) -> bool:
    """True when `path_or_name` (full path or basename) belongs to Eric Matyas."""
    if not path_or_name:
        return False
    return os.path.basename(path_or_name) in SOUNDIMAGE_TRACKS


# How many of the most recently used songs to avoid when picking the next one.
RECENT_SONG_HISTORY_LEN = 2


def _normalize_text(text: str) -> str:
    """Lowercase + strip diacritics so 'filosofía' and 'filosofia' both match."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _song_history_path() -> str:
    return os.path.join(ROOT_DIR, ".mp", "song_history.json")


def _load_song_history() -> list:
    path = _song_history_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_song_history(history: list) -> None:
    cache_dir = os.path.join(ROOT_DIR, ".mp")
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(_song_history_path(), "w", encoding="utf-8") as f:
            json.dump(history[-RECENT_SONG_HISTORY_LEN:], f, ensure_ascii=False)
    except Exception:
        pass


def choose_random_song(subject: str = "") -> str:
    """
    Picks a background music track from Songs/, biased by the video's subject.

    Selection order:
      1. Filter out the last RECENT_SONG_HISTORY_LEN songs played (so the same
         track doesn't repeat back-to-back). If that empties the pool, fall back
         to all songs.
      2. Score remaining songs by counting SONG_KEYWORDS matches in the subject.
      3. If any song scores > 0, pick uniformly among the top-scoring ones.
         Otherwise pick uniformly at random.

    Args:
        subject: The video topic. Empty string = pure recency-aware random.

    Returns:
        Absolute path to the chosen audio file.
    """
    try:
        songs_dir = os.path.join(ROOT_DIR, "Songs")
        songs = [
            name
            for name in os.listdir(songs_dir)
            if os.path.isfile(os.path.join(songs_dir, name))
            and name.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg"))
        ]
        if not songs:
            raise RuntimeError("No audio files found in Songs directory")

        history = _load_song_history()
        eligible = [s for s in songs if s not in history] or songs

        norm_subject = _normalize_text(subject)
        chosen = None
        if norm_subject:
            scored = []
            for song in eligible:
                kws = SONG_KEYWORDS.get(song, [])
                score = sum(1 for kw in kws if _normalize_text(kw) in norm_subject)
                scored.append((score, song))
            max_score = max(s for s, _ in scored)
            if max_score > 0:
                top = [song for score, song in scored if score == max_score]
                chosen = random.choice(top)
                success(f' => Chose song: {chosen} (matched {max_score} keyword(s) for subject)')
        if chosen is None:
            chosen = random.choice(eligible)
            success(f" => Chose song: {chosen}")

        _save_song_history(history + [chosen])
        return os.path.join(songs_dir, chosen)
    except Exception as e:
        error(f"Error occurred while choosing song: {str(e)}")
        raise
