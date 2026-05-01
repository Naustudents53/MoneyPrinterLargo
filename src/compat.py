"""
Compatibility patch module. Import this ONCE at the top of any entry-point
script (main.py, run_yt_short.py, test_generate.py, test_upload.py) and it
handles Pillow/MoviePy compat + ffmpeg discovery for the whole process.
"""
import os
import shutil

# Fix Pillow 10+ compatibility with MoviePy (ANTIALIAS removed, now LANCZOS)
from PIL import Image as _PILImage
if not hasattr(_PILImage, "ANTIALIAS"):
    _PILImage.ANTIALIAS = _PILImage.LANCZOS


def ensure_ffmpeg_on_path() -> None:
    """Make sure ffmpeg is discoverable on PATH, searching common install dirs."""
    if shutil.which("ffmpeg"):
        return
    search_dirs = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"),
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
    ]
    for base in search_dirs:
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            if "ffmpeg.exe" in files:
                os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                return
    # Fallback: use imageio_ffmpeg bundled binary
    try:
        import imageio_ffmpeg
        ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    except ImportError:
        pass


def find_ffmpeg() -> str | None:
    """Return the path to ffmpeg, or None. Checks PATH + winget dirs."""
    path = shutil.which("ffmpeg")
    if path:
        return path
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


ensure_ffmpeg_on_path()
