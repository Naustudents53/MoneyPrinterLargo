import sys
import os

if sys.platform == "win32":
    os.system("")  # enable ANSI escape codes on Windows
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8")

from termcolor import colored

def error(message: str, show_emoji: bool = True) -> None:
    """
    Prints an error message.

    Args:
        message (str): The error message
        show_emoji (bool): Whether to show the emoji

    Returns:
        None
    """
    emoji = "❌" if show_emoji else ""
    print(colored(f"{emoji} {message}", "red"))

def success(message: str, show_emoji: bool = True) -> None:
    """
    Prints a success message.

    Args:
        message (str): The success message
        show_emoji (bool): Whether to show the emoji

    Returns:
        None
    """
    emoji = "✅" if show_emoji else ""
    print(colored(f"{emoji} {message}", "green"))

def info(message: str, show_emoji: bool = True) -> None:
    """
    Prints an info message.

    Args:
        message (str): The info message
        show_emoji (bool): Whether to show the emoji

    Returns:
        None
    """
    emoji = "ℹ️" if show_emoji else ""
    print(colored(f"{emoji} {message}", "magenta"))

def warning(message: str, show_emoji: bool = True) -> None:
    """
    Prints a warning message.

    Args:
        message (str): The warning message
        show_emoji (bool): Whether to show the emoji

    Returns:
        None
    """
    emoji = "⚠️" if show_emoji else ""
    print(colored(f"{emoji} {message}", "yellow"))

def question(message: str, show_emoji: bool = True) -> str:
    """
    Prints a question message and returns the user's input.

    Args:
        message (str): The question message
        show_emoji (bool): Whether to show the emoji

    Returns:
        user_input (str): The user's input
    """
    emoji = "❓" if show_emoji else ""
    return input(colored(f"{emoji} {message}", "magenta"))


def _flush_stdin() -> None:
    """
    Discard any buffered stdin (e.g. stray Enter presses queued during a
    multi-hour render). Without this, the next input() returns immediately
    with garbage and skips the prompt entirely.
    """
    try:
        # Windows: msvcrt.kbhit/getwch drains the keyboard buffer.
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getwch()
    except Exception:
        # POSIX: termios/select-based drain.
        try:
            import sys, select, termios
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                while select.select([sys.stdin], [], [], 0)[0]:
                    sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass


def confirm(message: str, default: bool = False, show_emoji: bool = True) -> bool:
    """
    Yes/No confirmation prompt that:
      * Drains stdin first so buffered Enter presses don't auto-skip it.
      * Loops until the user types something the parser understands.
      * Accepts: yes / y / sí / si / s / true / 1   →  True
                 no  / n / false / 0                →  False
      * Empty input returns `default`.
    """
    _flush_stdin()
    yes_words = {"yes", "y", "si", "sí", "s", "true", "1"}
    no_words = {"no", "n", "false", "0"}
    suffix = " (Yes/No) " if default is False else " (YES/no) "
    while True:
        raw = question(message + suffix, show_emoji=show_emoji).strip().lower()
        if not raw:
            return default
        if raw in yes_words:
            return True
        if raw in no_words:
            return False
        print(colored("Please answer yes or no.", "yellow"))
