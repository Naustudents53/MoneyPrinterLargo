"""
One-command launcher for MoneyPrinter Pro (FastAPI + Vite) — runs both
processes in the SAME terminal with prefixed, color-coded output, and
shuts everything down cleanly on Ctrl-C.

Usage (from project root):
    python run_webapp.py

Optional flags:
    --api-port 8000     FastAPI port (default 8000)
    --web-port 5173     Vite port (default 5173)
    --no-reload         Disable uvicorn auto-reload
    --no-web            Run only the API
    --no-api            Run only the web frontend
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "webapp" / "web"
IS_WIN = os.name == "nt"

# ANSI colors — Windows 10+ terminals support these.
COLORS = {
    "api": "\033[36m",   # cyan
    "web": "\033[35m",   # magenta
    "sys": "\033[33m",   # yellow
    "err": "\033[31m",   # red
    "reset": "\033[0m",
}


def color(tag: str, text: str) -> str:
    return f"{COLORS.get(tag, '')}{text}{COLORS['reset']}"


def python_exe() -> str:
    """Prefer the project venv if present."""
    if IS_WIN:
        venv = ROOT / "venv" / "Scripts" / "python.exe"
    else:
        venv = ROOT / "venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def npm_cmd() -> str:
    """Resolve npm: must use npm.cmd on Windows when not going through a shell."""
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def stream(proc: subprocess.Popen, tag: str, stop: threading.Event) -> None:
    """Pipe a subprocess's stdout to our terminal with a colored prefix."""
    prefix = color(tag, f"[{tag}] ")
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            if stop.is_set():
                break
            sys.stdout.write(prefix + line.rstrip("\n") + "\n")
            sys.stdout.flush()
    except Exception as e:
        sys.stdout.write(color("err", f"[{tag}] stream error: {e}\n"))


def spawn(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.Popen:
    """Spawn a child process with merged stdout/stderr ready for line streaming."""
    creationflags = 0
    preexec_fn = None
    if IS_WIN:
        # CREATE_NEW_PROCESS_GROUP so we can send Ctrl+Break to the group.
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        preexec_fn = os.setsid  # new session — kill the whole tree later

    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, **(env or {})},
        creationflags=creationflags,
        preexec_fn=preexec_fn,
    )


def terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if IS_WIN:
            # Send Ctrl+Break to the group, then fall back to TerminateProcess.
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        pass
    try:
        proc.wait(timeout=3)
    except Exception:
        pass
    # On Windows the uvicorn reloader sometimes ignores Ctrl+Break and leaves
    # the child server bound to the port — kill the whole tree to be safe.
    if proc.poll() is None:
        if IS_WIN:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        try:
            proc.wait(timeout=3)
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-port", type=int, default=8000)
    ap.add_argument("--web-port", type=int, default=5173)
    ap.add_argument("--no-reload", action="store_true")
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--no-api", action="store_true")
    args = ap.parse_args()

    if args.no_api and args.no_web:
        print("Nothing to run.")
        return 1

    # Sanity checks
    if not args.no_web and not WEB_DIR.is_dir():
        print(color("err", f"[sys] webapp/web not found at {WEB_DIR}"))
        return 2
    if not args.no_web and not (WEB_DIR / "node_modules").is_dir():
        print(color("sys", "[sys] node_modules missing — run `npm install` inside webapp/web first."))

    print(color("sys", "═══ MoneyPrinter Pro launcher ═══"))
    print(color("sys", f"[sys] Python: {python_exe()}"))
    print(color("sys", f"[sys] Root:   {ROOT}"))

    procs: list[tuple[str, subprocess.Popen]] = []
    stop = threading.Event()

    if not args.no_api:
        api_cmd = [
            python_exe(), "-m", "uvicorn", "webapp.api.main:app",
            "--host", "127.0.0.1", "--port", str(args.api_port),
        ]
        if not args.no_reload:
            # Scope the watcher to ONLY the API + the project src/ that the API
            # imports. Watching the project root saturates WatchFiles on
            # Windows (node_modules, venv, .mp/, thumbnails/) and hangs the
            # event loop so requests never return.
            api_cmd += [
                "--reload",
                "--reload-dir", str(ROOT / "webapp" / "api"),
                "--reload-dir", str(ROOT / "src"),
            ]
        print(color("sys", f"[sys] API → http://127.0.0.1:{args.api_port}"))
        api_proc = spawn(api_cmd, cwd=ROOT, env={"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
        procs.append(("api", api_proc))
        threading.Thread(target=stream, args=(api_proc, "api", stop), daemon=True).start()

    if not args.no_web:
        # Brief stagger so the API banner prints first.
        if not args.no_api:
            time.sleep(1.0)
        web_cmd = [npm_cmd(), "run", "dev", "--", "--port", str(args.web_port)]
        print(color("sys", f"[sys] Web → http://127.0.0.1:{args.web_port}"))
        web_proc = spawn(web_cmd, cwd=WEB_DIR)
        procs.append(("web", web_proc))
        threading.Thread(target=stream, args=(web_proc, "web", stop), daemon=True).start()

    print(color("sys", "[sys] Ctrl+C para detener todo.\n"))

    exit_code = 0
    try:
        while True:
            time.sleep(0.5)
            for tag, p in procs:
                rc = p.poll()
                if rc is not None:
                    print(color("err", f"[{tag}] exited rc={rc} — shutting down the rest."))
                    exit_code = rc or 1
                    raise KeyboardInterrupt
    except KeyboardInterrupt:
        print(color("sys", "\n[sys] stopping…"))
    finally:
        stop.set()
        for _tag, p in procs:
            terminate(p)
        print(color("sys", "[sys] bye."))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
