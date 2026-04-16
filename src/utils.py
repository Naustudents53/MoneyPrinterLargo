import os
import re
import random
import zipfile
import requests
import platform

from status import *
from config import *

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


def clean_script_for_tts(text: str) -> str:
    """
    Sanitize script text for TTS and subtitles while PRESERVING punctuation
    that drives natural pacing: commas, colons, semicolons, em-dashes,
    ellipsis, parentheses, and Spanish opening marks (¿¡).
    Strips only markdown/control chars the LLM sometimes leaks.
    """
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

    for file in files:
        if not file.endswith(".json"):
            os.remove(os.path.join(mp_dir, file))

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


def choose_random_song() -> str:
    """
    Chooses a random song from the songs/ directory.

    Returns:
        str: The path to the chosen song.
    """
    try:
        songs_dir = os.path.join(ROOT_DIR, "Songs")
        songs = [
            name
            for name in os.listdir(songs_dir)
            if os.path.isfile(os.path.join(songs_dir, name))
            and name.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg"))
        ]
        if len(songs) == 0:
            raise RuntimeError("No audio files found in Songs directory")
        song = random.choice(songs)
        success(f" => Chose song: {song}")
        return os.path.join(ROOT_DIR, "Songs", song)
    except Exception as e:
        error(f"Error occurred while choosing random song: {str(e)}")
        raise
