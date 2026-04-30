# RUN THIS N AMOUNT OF TIMES
import sys

from status import *
from cache import get_accounts
from config import get_verbose
from classes.Tts import TTS
from classes.Twitter import Twitter
from classes.YouTube import YouTube
from classes.MovieSummary import MovieSummary
from cache import add_account, remove_account
from config import get_llm_provider, get_pollinations_text_model
from llm_provider import select_model, set_llm_provider

def main():
    """Main function to post content to Twitter or upload videos to YouTube.

    This function determines its operation based on command-line arguments:
    - If the purpose is "twitter", it initializes a Twitter account and posts a message.
    - If the purpose is "youtube", it initializes a YouTube account, generates a video with TTS, and uploads it.

    Command-line arguments:
        sys.argv[1]: A string indicating the purpose, either "twitter" or "youtube".
        sys.argv[2]: A string representing the account UUID.

    The function also handles verbose output based on user settings and reports success or errors as appropriate.

    Args:
        None. The function uses command-line arguments accessed via sys.argv.

    Returns:
        None. The function performs operations based on the purpose and account UUID and does not return any value."""
    purpose = str(sys.argv[1])
    account_id = str(sys.argv[2])
    model = str(sys.argv[3]) if len(sys.argv) > 3 else None

    llm_provider = get_llm_provider()
    set_llm_provider(llm_provider)

    if model:
        select_model(model)
    elif llm_provider == "pollinations":
        select_model(get_pollinations_text_model() or "openai")
    else:
        error("No Ollama model specified. Pass model name as third argument.")
        sys.exit(1)

    verbose = get_verbose()

    if purpose == "twitter":
        accounts = get_accounts("twitter")

        if not account_id:
            error("Account UUID cannot be empty.")

        for acc in accounts:
            if acc["id"] == account_id:
                if verbose:
                    info("Initializing Twitter...")
                twitter = Twitter(
                    acc["id"],
                    acc["nickname"],
                    acc["firefox_profile"],
                    acc["topic"]
                )
                twitter.post()
                if verbose:
                    success("Done posting.")
                break
    elif purpose == "youtube":
        tts = TTS()

        accounts = get_accounts("youtube")

        if not account_id:
            error("Account UUID cannot be empty.")

        for acc in accounts:
            if acc["id"] == account_id:
                if verbose:
                    info("Initializing YouTube...")
                youtube = YouTube(
                    acc["id"],
                    acc["nickname"],
                    acc["firefox_profile"],
                    acc["niche"],
                    acc["language"],
                    image_style=acc.get("image_style", ""),
                    short_voice=acc.get("short_voice", ""),
                    long_voice=acc.get("long_voice", ""),
                    hook_profile=acc.get("hook_profile", ""),
                    voice_drama=acc.get("voice_drama", False),
                )
                video_path = youtube.generate_video(tts)
                if not video_path:
                    # Pipeline aborted (e.g. duplicate-topic guard): skip upload.
                    error("Skipping upload: video generation aborted.")
                    sys.exit(1)
                youtube.upload_video()
                if verbose:
                    success("Uploaded Short.")
                break
    elif purpose == "movies":
        tts = TTS()

        accounts = get_accounts("movies")

        if not account_id:
            error("Account UUID cannot be empty.")

        for acc in accounts:
            if acc["id"] == account_id:
                if verbose:
                    info("Initializing Movie Summary...")
                ms = MovieSummary(
                    acc["id"],
                    acc["nickname"],
                    acc["firefox_profile"],
                    acc["niche"],
                    acc["language"],
                    image_style=acc.get("image_style", ""),
                    short_voice=acc.get("short_voice", ""),
                    long_voice=acc.get("long_voice", ""),
                    hook_profile=acc.get("hook_profile", ""),
                    voice_drama=acc.get("voice_drama", False),
                )
                pending = list(acc.get("pending_titles") or [])
                if not pending:
                    error("No pending movie titles in account; nothing to do.")
                    sys.exit(1)
                next_title = pending.pop(0)
                video_path = ms.generate_movie_summary(tts, next_title)
                if not video_path:
                    error("Skipping upload: movie summary aborted.")
                    sys.exit(1)
                ms.upload_video()
                # Persist the consumed-from-queue state by rewriting the account
                acc["pending_titles"] = pending
                remove_account("movies", acc["id"])
                add_account("movies", acc)
                if verbose:
                    success(f"Uploaded movie summary: {next_title}")
                break
    else:
        error("Invalid Purpose, exiting...")
        sys.exit(1)

if __name__ == "__main__":
    main()
