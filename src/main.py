import schedule
import subprocess
from datetime import datetime

# Fix Pillow 10+ compatibility with MoviePy (ANTIALIAS removed, now LANCZOS)
from PIL import Image as _PILImage
if not hasattr(_PILImage, "ANTIALIAS"):
    _PILImage.ANTIALIAS = _PILImage.LANCZOS

# Ensure ffmpeg is discoverable system-wide
def _setup_ffmpeg_path():
    import os, shutil
    if shutil.which("ffmpeg"):
        return
    # Check common winget installation paths
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

_setup_ffmpeg_path()

from art import *
from cache import *
from utils import *
from config import *
from status import *
from uuid import uuid4
from constants import *
from classes.Tts import TTS
from termcolor import colored
from classes.Twitter import Twitter
from classes.YouTube import YouTube
from classes.MovieSummary import MovieSummary
from classes.MovieCatalog import MovieCatalog, PAGE_SIZE
from prettytable import PrettyTable
from classes.Outreach import Outreach
from classes.AFM import AffiliateMarketing
from llm_provider import list_models, select_model, get_active_model, set_llm_provider


def _trunc(s, n: int) -> str:
    """Truncate string to at most n chars, adding an ellipsis if cut. Plain text only — apply BEFORE coloring."""
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: max(1, n - 1)] + "…"


def _browse_movie_catalog(catalog: MovieCatalog, account_id: str, ms, tts) -> None:
    """
    Paginated picker over the archive.org catalog. Shows 10 entries per page,
    marks already-summarized ones with ✓ and pending ones with ·. Commands:
      n / p          → next / previous page
      s <query>      → filter by title substring (empty s clears the filter)
      a              → toggle "show all" vs "show only pending" (default: pending)
      <1-10>         → pick that entry, run the summary pipeline, then return here
      q              → exit the browser
    """
    from cache import get_accounts as _get_accounts

    page = 1
    query = ""
    show_all = False  # default: hide already summarized

    while True:
        # Re-load account each iteration so we pick up newly summarized entries
        accounts = _get_accounts("movies")
        account = next((a for a in accounts if a.get("id") == account_id), None)
        if account is None:
            error("Account vanished from cache.")
            return

        all_items = catalog.search(query) if show_all else catalog.pending(account, query)
        total = len(all_items)
        total_pages = catalog.total_pages(all_items, PAGE_SIZE)
        page = max(1, min(page, total_pages))
        page_items = catalog.paginate(all_items, page, PAGE_SIZE)
        done_set = catalog.summarized_identifiers(account)

        view_label = "all" if show_all else "pending only"
        filter_label = f' filter:"{query}"' if query else ""
        info(
            f"\n[Catalog] page {page}/{total_pages} — {total} items ({view_label}){filter_label}",
            False,
        )
        if total == 0:
            warning(" No movies match those filters.")
        else:
            for i, e in enumerate(page_items, 1):
                mark = colored("✓", "green") if e["identifier"] in done_set else colored("·", "yellow")
                year = f" ({e['year']})" if e.get("year") else ""
                runtime = f" [{e['runtime']}]" if e.get("runtime") else ""
                downloads = f" {e.get('downloads', 0):,} dl"
                title = _trunc(e["title"], 60)
                rating = e.get("imdb_rating")
                if rating:
                    votes = e.get("imdb_votes", 0)
                    rating_str = colored(f" ⭐ {rating:.1f} ({votes:,})", "yellow")
                else:
                    rating_str = colored("  —     ", "white")
                print(f"  {mark} {i:>2}. {rating_str}  {colored(title, 'cyan')}{year}{runtime}{downloads}")

        info(
            "\n[n]ext / [p]rev / [s] <query> / [a] toggle all/pending / [1-10] pick / [q]uit",
            False,
        )
        raw = question("> ").strip()
        if not raw:
            continue
        cmd = raw.lower()

        if cmd == "q":
            return
        if cmd == "n":
            if page < total_pages:
                page += 1
            continue
        if cmd == "p":
            if page > 1:
                page -= 1
            continue
        if cmd == "a":
            show_all = not show_all
            page = 1
            continue
        if cmd.startswith("s "):
            query = raw[2:].strip()
            page = 1
            continue
        if cmd == "s":
            query = ""
            page = 1
            continue

        # Numeric selection
        try:
            idx = int(raw) - 1
        except ValueError:
            warning("Unrecognized command.")
            continue
        if not (0 <= idx < len(page_items)):
            warning("Out of range.")
            continue

        selected = page_items[idx]
        if selected["identifier"] in done_set:
            if not confirm(f"'{selected['title']}' already summarized. Run again?", default=False):
                continue

        info(f"\n=> Generating summary for: {selected['title']}")
        try:
            video_path = ms.generate_movie_summary(
                tts, selected["title"], archive_identifier=selected["identifier"]
            )
        except Exception as gen_err:
            error(f"Movie summary failed: {type(gen_err).__name__}: {gen_err}")
            continue
        if not video_path:
            warning("Movie summary aborted — nothing to upload.")
            continue
        if confirm("Upload this video to YouTube?", default=True):
            try:
                ms.upload_video()
            except KeyboardInterrupt:
                warning(f"\nUpload cancelled. Video saved at: {video_path}")
            except Exception as up_err:
                error(f"Upload failed: {type(up_err).__name__}: {up_err}")
                warning(f"Video preserved on disk: {video_path}")


def main():
    """Main entry point for the application, providing a menu-driven interface
    to manage YouTube, Twitter bots, Affiliate Marketing, and Outreach tasks.

    This function allows users to:
    1. Start the YouTube Shorts Automater to manage YouTube accounts, 
       generate and upload videos, and set up CRON jobs.
    2. Start a Twitter Bot to manage Twitter accounts, post tweets, and 
       schedule posts using CRON jobs.
    3. Manage Affiliate Marketing by creating pitches and sharing them via 
       Twitter accounts.
    4. Initiate an Outreach process for engagement and promotion tasks.
    5. Exit the application.

    The function continuously prompts users for input, validates it, and 
    executes the selected option until the user chooses to quit.

    Args:
        None

    Returns:
        None"""

    def _prompt_youtube_account_fields(defaults: dict | None = None) -> dict:
        """
        Ask the user for the fields that define a YouTube account.
        If `defaults` is given, each prompt shows the current value and pressing Enter keeps it.
        Returns a dict with: nickname, firefox_profile, niche, language, image_style, short_voice, long_voice.
        """
        from classes.Tts import EDGE_TTS_VOICES
        defaults = defaults or {}

        def _ask(label: str, key: str) -> str:
            cur = defaults.get(key, "")
            hint = f" [{cur}]" if cur else ""
            val = question(f" => {label}{hint}: ").strip()
            return val or cur

        nickname = _ask("Nickname for this account", "nickname")
        fp_profile = _ask("Path to the Firefox profile", "firefox_profile")
        niche = _ask("Account niche", "niche")
        language = _ask("Account language", "language")

        # Per-channel image style (free text appended to AI image prompts).
        info("\n   Image style: free-text suffix that gets appended to every AI image prompt.")
        info("   Examples:")
        info("     - cinematic photorealistic, dramatic lighting, classical aesthetic")
        info("     - vibrant macro photography, vivid colors, lab aesthetic")
        info("     - chiaroscuro lighting, contemplative, classical sculpture aesthetic")
        info("     - dark atmospheric, low-key lighting, foggy, eerie tones")
        info("   Leave empty for no per-channel style.")
        image_style = _ask("Image style (optional)", "image_style")

        # Voice selection — show the catalog so the user can pick by alias.
        info("\n   Available voices (alias → Edge-TTS ID):")
        for alias, vid in EDGE_TTS_VOICES.items():
            print(colored(f"     {alias:<8} → {vid}", "cyan"))
        info("   You can type either an alias (e.g. Pablo) OR a full Edge-TTS ID (e.g. es-ES-ElviraNeural).")
        info("   Leave empty to use the global default from config.json.")
        short_voice = _ask("Short-video voice", "short_voice")
        long_voice = _ask("Long-video voice (default: es-ES-AlvaroNeural)", "long_voice")

        return {
            "nickname": nickname,
            "firefox_profile": fp_profile,
            "niche": niche,
            "language": language,
            "image_style": image_style,
            "short_voice": short_voice,
            "long_voice": long_voice,
        }

    # Get user input
    # user_input = int(question("Select an option: "))
    valid_input = False
    while not valid_input:
        try:
    # Show user options
            info("\n============ OPTIONS ============", False)

            for idx, option in enumerate(OPTIONS):
                print(colored(f" {idx + 1}. {option}", "cyan"))

            info("=================================\n", False)
            user_input = input("Select an option: ").strip()
            if user_input == '':
                print("\n" * 100)
                raise ValueError("Empty input is not allowed.")
            user_input = int(user_input)
            valid_input = True
        except ValueError as e:
            print("\n" * 100)
            print(f"Invalid input: {e}")


    # Start the selected option
    if user_input == 1:
        info("Starting YT Shorts Automater...")

        cached_accounts = get_accounts("youtube")

        if len(cached_accounts) == 0:
            warning("No accounts found in cache. Create one now?")
            if confirm("Create one now?", default=True):
                generated_uuid = str(uuid4())
                success(f" => Generated ID: {generated_uuid}")
                fields = _prompt_youtube_account_fields()
                account_data = {"id": generated_uuid, **fields, "videos": []}
                add_account("youtube", account_data)
                success("Account configured successfully!")
        else:
            table = PrettyTable()
            table.field_names = ["#", "Nickname", "Niche", "Image style", "Short voice", "Long voice"]
            # Left-align text columns so truncation reads cleanly.
            for col in ("Nickname", "Niche", "Image style", "Short voice", "Long voice"):
                table.align[col] = "l"

            # Per-column character caps. Tuned so the whole table fits in ~120 cols
            # (VS Code's default integrated terminal). Truncate with ellipsis BEFORE
            # coloring — termcolor wraps strings in ANSI escapes which break len().
            CAPS = {"nickname": 18, "niche": 26, "image_style": 18, "voice": 20}

            for idx, account in enumerate(cached_accounts):
                nickname = _trunc(account.get("nickname", ""), CAPS["nickname"])
                niche = _trunc(account.get("niche", ""), CAPS["niche"])
                image_style = _trunc(account.get("image_style") or "<default>", CAPS["image_style"])
                short_v = _trunc(account.get("short_voice") or "<default>", CAPS["voice"])
                long_v = _trunc(account.get("long_voice") or "<default>", CAPS["voice"])
                table.add_row([
                    idx + 1,
                    colored(nickname, "blue"),
                    colored(niche, "green"),
                    colored(image_style, "yellow"),
                    colored(short_v, "magenta"),
                    colored(long_v, "magenta"),
                ])

            print(table)
            info("Type 'd' to delete, 'n' to add new, 'e' to edit an account.", False)

            user_input = question("Select an account to start (or 'd'/'n'/'e'): ").strip()

            if user_input.lower() == "n":
                generated_uuid = str(uuid4())
                success(f" => Generated ID: {generated_uuid}")
                fields = _prompt_youtube_account_fields()
                account_data = {"id": generated_uuid, **fields, "videos": []}
                add_account("youtube", account_data)
                success("Account configured successfully!")
                return

            if user_input.lower() == "d":
                delete_input = question("Enter account number to delete: ").strip()
                account_to_delete = None
                for idx, account in enumerate(cached_accounts):
                    if str(idx + 1) == delete_input:
                        account_to_delete = account
                        break

                if account_to_delete is None:
                    error("Invalid account selected. Please try again.", "red")
                else:
                    if confirm(f"Are you sure you want to delete '{account_to_delete['nickname']}'?", default=False):
                        remove_account("youtube", account_to_delete["id"])
                        success("Account removed successfully!")
                    else:
                        warning("Account deletion canceled.", False)
                return

            if user_input.lower() == "e":
                edit_input = question("Enter account number to edit: ").strip()
                account_to_edit = None
                for idx, account in enumerate(cached_accounts):
                    if str(idx + 1) == edit_input:
                        account_to_edit = account
                        break

                if account_to_edit is None:
                    error("Invalid account selected. Please try again.", "red")
                else:
                    info(f"Editing '{account_to_edit['nickname']}' — press Enter to keep current value.")
                    new_fields = _prompt_youtube_account_fields(defaults=account_to_edit)
                    # Merge: keep id + videos, replace the rest.
                    merged = {**account_to_edit, **new_fields}
                    # Persist by removing old + re-adding.
                    remove_account("youtube", account_to_edit["id"])
                    add_account("youtube", merged)
                    success(f"Account '{merged['nickname']}' updated.")
                return

            selected_account = None

            for idx, account in enumerate(cached_accounts):
                if str(idx + 1) == user_input:
                    selected_account = account
                    break

            if selected_account is None:
                error("Invalid account selected. Please try again.", "red")
                main()
            else:
                youtube = YouTube(
                    selected_account["id"],
                    selected_account["nickname"],
                    selected_account["firefox_profile"],
                    selected_account["niche"],
                    selected_account["language"],
                    image_style=selected_account.get("image_style", ""),
                    short_voice=selected_account.get("short_voice", ""),
                    long_voice=selected_account.get("long_voice", ""),
                    hook_profile=selected_account.get("hook_profile", ""),
                    voice_drama=selected_account.get("voice_drama", False),
                )

                while True:
                    rem_temp_files()
                    info("\n============ OPTIONS ============", False)

                    for idx, youtube_option in enumerate(YOUTUBE_OPTIONS):
                        print(colored(f" {idx + 1}. {youtube_option}", "cyan"))

                    info("=================================\n", False)

                    # Get user input
                    user_input = int(question("Select an option: "))
                    tts = TTS()

                    if user_input == 1:
                        # Upload Short
                        custom_topic = question(
                            "Enter a custom topic (or leave empty to auto-generate): "
                        ).strip()
                        image_choice = question(
                            "Image source - [1] AI (default), [2] Real photos: "
                        ).strip()
                        image_mode = "photos" if image_choice == "2" else "ai"
                        video_path = youtube.generate_video(
                            tts,
                            custom_topic=custom_topic,
                            image_mode=image_mode,
                        )
                        if not video_path:
                            warning("Video generation aborted — nothing to upload.")
                        elif confirm("Do you want to upload this video to YouTube?", default=True):
                            try:
                                youtube.upload_video()
                            except KeyboardInterrupt:
                                warning(f"\nUpload cancelled by user. Video saved at: {video_path}")
                            except Exception as _upload_err:
                                error(f"Upload failed: {type(_upload_err).__name__}: {_upload_err}")
                                warning(f"Video preserved on disk: {video_path}")
                                warning("You can retry uploading by running the app again.")
                    elif user_input == 2:
                        # Upload Long Video
                        custom_topic = question(
                            "Enter a custom topic (or leave empty to auto-generate): "
                        ).strip()

                        # Series picker — only shown if (a) at least one series is
                        # configured and (b) the user typed a topic that doesn't
                        # already carry a [series_id] prefix. The prefix style still
                        # works for power users who don't want the menu.
                        series_list = get_series()
                        if (
                            series_list
                            and custom_topic
                            and not custom_topic.lstrip().startswith("[")
                        ):
                            print(colored("\nApply to a series? (Enter for none)", "cyan"))
                            print(colored("  0. (None)", "cyan"))
                            for i, s in enumerate(series_list, 1):
                                label = s.get("name") or s.get("id", "")
                                print(colored(f"  {i}. {label}", "cyan"))
                            sel = question("Series: ").strip()
                            if sel.isdigit():
                                idx = int(sel) - 1
                                if 0 <= idx < len(series_list):
                                    chosen = series_list[idx]
                                    custom_topic = f"[{chosen['id']}] {custom_topic}"
                                    info(f" => Using series: {chosen.get('name') or chosen['id']}")

                        info("Starting Long Video Generation (15-20 min)...")
                        long_path = youtube.generate_long_video(tts, custom_topic=custom_topic)
                        if not long_path:
                            warning("Long video generation aborted — nothing to upload.")
                        elif confirm("Do you want to upload this video to YouTube?", default=True):
                            try:
                                youtube.upload_video()
                            except KeyboardInterrupt:
                                warning(f"\nUpload cancelled by user. Video saved at: {long_path}")
                            except Exception as _upload_err:
                                error(f"Upload failed: {type(_upload_err).__name__}: {_upload_err}")
                                warning(f"Video preserved on disk: {long_path}")
                                warning("You can retry uploading by running the app again.")
                    elif user_input == 3:
                        # Show all Videos
                        videos = youtube.get_videos()

                        if len(videos) > 0:
                            videos_table = PrettyTable()
                            videos_table.field_names = ["ID", "Date", "Title"]

                            for video in videos:
                                videos_table.add_row([
                                    videos.index(video) + 1,
                                    colored(video["date"], "blue"),
                                    colored(video["title"][:60] + "...", "green")
                                ])

                            print(videos_table)
                        else:
                            warning(" No videos found.")
                    elif user_input == 4:
                        # Clean up saved videos (.mp4 files in .mp/)
                        mp_dir = os.path.join(ROOT_DIR, ".mp")
                        mp4s = [
                            os.path.join(mp_dir, f)
                            for f in os.listdir(mp_dir)
                            if f.lower().endswith(".mp4")
                        ]
                        if not mp4s:
                            info(" => No saved videos to clean.")
                        else:
                            total_bytes = sum(os.path.getsize(p) for p in mp4s)
                            total_mb = total_bytes / (1024 * 1024)
                            info(f" => Found {len(mp4s)} saved video(s) using {total_mb:.1f} MB:")
                            for p in sorted(mp4s, key=os.path.getmtime, reverse=True):
                                size_mb = os.path.getsize(p) / (1024 * 1024)
                                mtime = datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
                                print(colored(f"   - {os.path.basename(p)}  ({size_mb:.1f} MB, {mtime})", "cyan"))
                            if confirm(f"Delete all {len(mp4s)} saved video(s)?", default=False):
                                deleted = 0
                                for p in mp4s:
                                    try:
                                        os.remove(p)
                                        deleted += 1
                                    except Exception as e:
                                        warning(f"   Could not delete {os.path.basename(p)}: {e}")
                                success(f" => Deleted {deleted}/{len(mp4s)} video(s), freed {total_mb:.1f} MB.")
                            else:
                                info(" => Cancelled.")
                    elif user_input == 5:
                        # Re-upload existing video
                        mp_dir = os.path.join(ROOT_DIR, ".mp")
                        try:
                            mp4s = sorted(
                                [
                                    os.path.join(mp_dir, f)
                                    for f in os.listdir(mp_dir)
                                    if f.lower().endswith(".mp4")
                                ],
                                key=os.path.getmtime,
                                reverse=True,
                            )
                        except FileNotFoundError:
                            mp4s = []

                        if not mp4s:
                            warning(" => No saved videos found in .mp/ to re-upload.")
                        else:
                            info(f"\n => Found {len(mp4s)} saved video(s):")
                            for i, p in enumerate(mp4s, 1):
                                size_mb = os.path.getsize(p) / (1024 * 1024)
                                mtime = datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
                                meta = YouTube.load_metadata_sidecar(p)
                                if meta and meta.get("title"):
                                    tag = colored(f"  [meta: {meta['title'][:50]}]", "green")
                                else:
                                    tag = colored("  [no metadata]", "yellow")
                                print(colored(f"   {i}. {os.path.basename(p)}  ({size_mb:.1f} MB, {mtime})", "cyan") + tag)

                            sel = question("\nSelect a video to re-upload (number, or empty to cancel): ").strip()
                            if not sel:
                                info(" => Cancelled.")
                            else:
                                try:
                                    idx = int(sel) - 1
                                    if not (0 <= idx < len(mp4s)):
                                        raise ValueError()
                                except ValueError:
                                    warning(" => Invalid selection.")
                                else:
                                    chosen_path = mp4s[idx]
                                    saved_meta = YouTube.load_metadata_sidecar(chosen_path)

                                    subj_to_pass = None
                                    proceed = True

                                    if saved_meta and saved_meta.get("title") and saved_meta.get("description"):
                                        info(f" => Found saved metadata: {saved_meta['title']}")
                                        if not confirm("Use saved metadata?", default=True):
                                            saved_meta = None  # fall through to recovery menu

                                    if not saved_meta:
                                        info("\n => No saved metadata. Recovery options:")
                                        print(colored("   1. Auto-transcribe with Whisper (recovers original content)", "cyan"))
                                        print(colored("   2. Type a topic manually (LLM generates title + description)", "cyan"))
                                        print(colored("   3. Cancel", "cyan"))
                                        choice = question("Select [1/2/3]: ").strip()
                                        if choice == "1":
                                            subj_to_pass = None  # triggers Whisper path in reupload_video
                                        elif choice == "2":
                                            subj_to_pass = question("Enter the topic: ").strip()
                                            if not subj_to_pass:
                                                warning(" => Empty topic — cancelled.")
                                                proceed = False
                                        else:
                                            info(" => Cancelled.")
                                            proceed = False

                                    if proceed:
                                        try:
                                            youtube.reupload_video(chosen_path, subj_to_pass)
                                        except KeyboardInterrupt:
                                            warning(f"\nUpload cancelled by user. Video preserved at: {chosen_path}")
                                        except Exception as _re_err:
                                            error(f"Re-upload failed: {type(_re_err).__name__}: {_re_err}")
                                            warning(f"Video preserved at: {chosen_path}")
                    elif user_input == 6:
                        # Setup CRON Job
                        info("How often do you want to upload?")

                        info("\n============ OPTIONS ============", False)
                        for idx, cron_option in enumerate(YOUTUBE_CRON_OPTIONS):
                            print(colored(f" {idx + 1}. {cron_option}", "cyan"))

                        info("=================================\n", False)

                        user_input = int(question("Select an Option: "))

                        cron_script_path = os.path.join(ROOT_DIR, "src", "cron.py")
                        command = ["python", cron_script_path, "youtube", selected_account['id'], get_active_model()]

                        def job():
                            subprocess.run(command)

                        if user_input == 1:
                            # Upload Once
                            schedule.every(1).day.do(job)
                            success("Set up CRON Job.")
                        elif user_input == 2:
                            # Upload Twice a day
                            schedule.every().day.at("10:00").do(job)
                            schedule.every().day.at("16:00").do(job)
                            success("Set up CRON Job.")
                        else:
                            break
                    elif user_input == 7:
                        if get_verbose():
                            info(" => Climbing Options Ladder...", False)
                        break
    elif user_input == 2:
        info("Starting Twitter Bot...")

        cached_accounts = get_accounts("twitter")

        if len(cached_accounts) == 0:
            warning("No accounts found in cache. Create one now?")
            user_input = question("Yes/No: ")

            if user_input.lower() == "yes":
                generated_uuid = str(uuid4())

                success(f" => Generated ID: {generated_uuid}")
                nickname = question(" => Enter a nickname for this account: ")
                fp_profile = question(" => Enter the path to the Firefox profile: ")
                topic = question(" => Enter the account topic: ")

                add_account("twitter", {
                    "id": generated_uuid,
                    "nickname": nickname,
                    "firefox_profile": fp_profile,
                    "topic": topic,
                    "posts": []
                })
        else:
            table = PrettyTable()
            table.field_names = ["ID", "UUID", "Nickname", "Account Topic"]

            for idx, account in enumerate(cached_accounts):
                table.add_row([idx + 1, colored(account["id"], "cyan"), colored(account["nickname"], "blue"), colored(account["topic"], "green")])

            print(table)
            info("Type 'd' to delete an account.", False)

            user_input = question("Select an account to start (or 'd' to delete): ").strip()

            if user_input.lower() == "d":
                delete_input = question("Enter account number to delete: ").strip()
                account_to_delete = None

                for idx, account in enumerate(cached_accounts):
                    if str(idx + 1) == delete_input:
                        account_to_delete = account
                        break

                if account_to_delete is None:
                    error("Invalid account selected. Please try again.", "red")
                else:
                    if confirm(f"Are you sure you want to delete '{account_to_delete['nickname']}'?", default=False):
                        remove_account("twitter", account_to_delete["id"])
                        success("Account removed successfully!")
                    else:
                        warning("Account deletion canceled.", False)

                return

            selected_account = None

            for idx, account in enumerate(cached_accounts):
                if str(idx + 1) == user_input:
                    selected_account = account
                    break

            if selected_account is None:
                error("Invalid account selected. Please try again.", "red")
                main()
            else:
                twitter = Twitter(selected_account["id"], selected_account["nickname"], selected_account["firefox_profile"], selected_account["topic"])

                while True:
                    
                    info("\n============ OPTIONS ============", False)

                    for idx, twitter_option in enumerate(TWITTER_OPTIONS):
                        print(colored(f" {idx + 1}. {twitter_option}", "cyan"))

                    info("=================================\n", False)

                    # Get user input
                    user_input = int(question("Select an option: "))

                    if user_input == 1:
                        twitter.post()
                    elif user_input == 2:
                        posts = twitter.get_posts()

                        posts_table = PrettyTable()

                        posts_table.field_names = ["ID", "Date", "Content"]

                        for post in posts:
                            posts_table.add_row([
                                posts.index(post) + 1,
                                colored(post["date"], "blue"),
                                colored(post["content"][:60] + "...", "green")
                            ])

                        print(posts_table)
                    elif user_input == 3:
                        info("How often do you want to post?")

                        info("\n============ OPTIONS ============", False)
                        for idx, cron_option in enumerate(TWITTER_CRON_OPTIONS):
                            print(colored(f" {idx + 1}. {cron_option}", "cyan"))

                        info("=================================\n", False)

                        user_input = int(question("Select an Option: "))

                        cron_script_path = os.path.join(ROOT_DIR, "src", "cron.py")
                        command = ["python", cron_script_path, "twitter", selected_account['id'], get_active_model()]

                        def job():
                            subprocess.run(command)

                        if user_input == 1:
                            # Post Once a day
                            schedule.every(1).day.do(job)
                            success("Set up CRON Job.")
                        elif user_input == 2:
                            # Post twice a day
                            schedule.every().day.at("10:00").do(job)
                            schedule.every().day.at("16:00").do(job)
                            success("Set up CRON Job.")
                        elif user_input == 3:
                            # Post thrice a day
                            schedule.every().day.at("08:00").do(job)
                            schedule.every().day.at("12:00").do(job)
                            schedule.every().day.at("18:00").do(job)
                            success("Set up CRON Job.")
                        else:
                            break
                    elif user_input == 4:
                        if get_verbose():
                            info(" => Climbing Options Ladder...", False)
                        break
    elif user_input == 3:
        info("Starting Affiliate Marketing...")

        cached_products = get_products()

        if len(cached_products) == 0:
            warning("No products found in cache. Create one now?")
            user_input = question("Yes/No: ")

            if user_input.lower() == "yes":
                affiliate_link = question(" => Enter the affiliate link: ")
                twitter_uuid = question(" => Enter the Twitter Account UUID: ")

                # Find the account
                account = None
                for acc in get_accounts("twitter"):
                    if acc["id"] == twitter_uuid:
                        account = acc

                add_product({
                    "id": str(uuid4()),
                    "affiliate_link": affiliate_link,
                    "twitter_uuid": twitter_uuid
                })

                afm = AffiliateMarketing(affiliate_link, account["firefox_profile"], account["id"], account["nickname"], account["topic"])

                afm.generate_pitch()
                afm.share_pitch("twitter")
        else:
            table = PrettyTable()
            table.field_names = ["ID", "Affiliate Link", "Twitter Account UUID"]

            for idx, product in enumerate(cached_products):
                table.add_row([idx + 1, colored(product["affiliate_link"], "cyan"), colored(product["twitter_uuid"], "blue")])

            print(table)

            user_input = question("Select a product to start: ")

            selected_product = None

            for idx, product in enumerate(cached_products):
                if str(idx + 1) == user_input:
                    selected_product = product
                    break

            if selected_product is None:
                error("Invalid product selected. Please try again.", "red")
                main()
            else:
                # Find the account
                account = None
                for acc in get_accounts("twitter"):
                    if acc["id"] == selected_product["twitter_uuid"]:
                        account = acc

                afm = AffiliateMarketing(selected_product["affiliate_link"], account["firefox_profile"], account["id"], account["nickname"], account["topic"])

                afm.generate_pitch()
                afm.share_pitch("twitter")

    elif user_input == 4:
        info("Starting Outreach...")

        outreach = Outreach()

        outreach.start()
    elif user_input == 5:
        info("Starting Movie Summary...")

        cached_accounts = get_accounts("movies")

        if len(cached_accounts) == 0:
            warning("No accounts found in cache.")
            if confirm("Create one now?", default=True):
                generated_uuid = str(uuid4())
                success(f" => Generated ID: {generated_uuid}")
                fields = _prompt_youtube_account_fields()
                account_data = {"id": generated_uuid, **fields, "videos": [], "pending_titles": []}
                add_account("movies", account_data)
                success("Account configured successfully!")
        else:
            table = PrettyTable()
            table.field_names = ["#", "Nickname", "Niche", "Long voice"]
            for col in ("Nickname", "Niche", "Long voice"):
                table.align[col] = "l"
            for idx, account in enumerate(cached_accounts):
                table.add_row([
                    idx + 1,
                    colored(_trunc(account.get("nickname", ""), 18), "blue"),
                    colored(_trunc(account.get("niche", ""), 26), "green"),
                    colored(_trunc(account.get("long_voice") or "<default>", 24), "magenta"),
                ])
            print(table)
            info("Type 'd' to delete, 'n' to add new, 'e' to edit an account.", False)

            user_input = question("Select an account to start (or 'd'/'n'/'e'): ").strip()

            if user_input.lower() == "n":
                generated_uuid = str(uuid4())
                success(f" => Generated ID: {generated_uuid}")
                fields = _prompt_youtube_account_fields()
                add_account("movies", {"id": generated_uuid, **fields, "videos": [], "pending_titles": []})
                success("Account configured successfully!")
                return

            if user_input.lower() == "d":
                delete_input = question("Enter account number to delete: ").strip()
                target = next((a for i, a in enumerate(cached_accounts) if str(i + 1) == delete_input), None)
                if target is None:
                    error("Invalid account selected. Please try again.", "red")
                elif confirm(f"Are you sure you want to delete '{target['nickname']}'?", default=False):
                    remove_account("movies", target["id"])
                    success("Account removed successfully!")
                else:
                    warning("Account deletion canceled.", False)
                return

            if user_input.lower() == "e":
                edit_input = question("Enter account number to edit: ").strip()
                target = next((a for i, a in enumerate(cached_accounts) if str(i + 1) == edit_input), None)
                if target is None:
                    error("Invalid account selected. Please try again.", "red")
                else:
                    info(f"Editing '{target['nickname']}' — press Enter to keep current value.")
                    new_fields = _prompt_youtube_account_fields(defaults=target)
                    merged = {**target, **new_fields}
                    remove_account("movies", target["id"])
                    add_account("movies", merged)
                    success(f"Account '{merged['nickname']}' updated.")
                return

            selected_account = next(
                (a for i, a in enumerate(cached_accounts) if str(i + 1) == user_input),
                None,
            )

            if selected_account is None:
                error("Invalid account selected. Please try again.", "red")
                main()
            else:
                ms = MovieSummary(
                    selected_account["id"],
                    selected_account["nickname"],
                    selected_account["firefox_profile"],
                    selected_account["niche"],
                    selected_account["language"],
                    image_style=selected_account.get("image_style", ""),
                    short_voice=selected_account.get("short_voice", ""),
                    long_voice=selected_account.get("long_voice", ""),
                    hook_profile=selected_account.get("hook_profile", ""),
                    voice_drama=selected_account.get("voice_drama", False),
                )

                while True:
                    rem_temp_files()
                    info("\n============ OPTIONS ============", False)
                    for idx, opt in enumerate(MOVIE_OPTIONS):
                        print(colored(f" {idx + 1}. {opt}", "cyan"))
                    info("=================================\n", False)

                    movie_choice = int(question("Select an option: "))
                    tts = TTS()

                    if movie_choice == 1:
                        # Browse archive.org catalog (paginated)
                        catalog = MovieCatalog()
                        if not catalog.is_fresh():
                            warning(
                                " Catalog is empty or older than 7 days. "
                                "Run 'Refresh catalog' first or wait for auto-refresh."
                            )
                            if confirm("Refresh catalog now?", default=True):
                                info(" => Refreshing catalog from archive.org "
                                     "(may take 1-3 min)...")
                                total = catalog.refresh(
                                    progress_cb=lambda c, n, tot: info(
                                        f"   - {c}: {n}/{tot or '?'}", False
                                    )
                                )
                                success(f" Catalog refreshed: {total} movies.")
                            else:
                                continue
                        _browse_movie_catalog(catalog, selected_account["id"], ms, tts)
                    elif movie_choice == 2:
                        # Refresh catalog
                        catalog = MovieCatalog()
                        info(" => Refreshing catalog from archive.org "
                             "(may take 1-3 min)...")
                        try:
                            total = catalog.refresh(
                                progress_cb=lambda c, n, tot: info(
                                    f"   - {c}: {n}/{tot or '?'}", False
                                )
                            )
                            success(f" Catalog refreshed: {total} movies.")
                        except Exception as cat_err:
                            error(f"Catalog refresh failed: {type(cat_err).__name__}: {cat_err}")
                    elif movie_choice == 3:
                        # Generate from custom title (YouTube fallback search)
                        movie_title = question("Enter the movie title (in any language): ").strip()
                        if not movie_title:
                            warning("Empty title — cancelled.")
                            continue
                        try:
                            video_path = ms.generate_movie_summary(tts, movie_title)
                        except Exception as gen_err:
                            error(f"Movie summary generation failed: {type(gen_err).__name__}: {gen_err}")
                            continue
                        if not video_path:
                            warning("Movie summary aborted — nothing to upload.")
                        elif confirm("Do you want to upload this video to YouTube?", default=True):
                            try:
                                ms.upload_video()
                            except KeyboardInterrupt:
                                warning(f"\nUpload cancelled by user. Video saved at: {video_path}")
                            except Exception as up_err:
                                error(f"Upload failed: {type(up_err).__name__}: {up_err}")
                                warning(f"Video preserved on disk: {video_path}")
                    elif movie_choice == 4:
                        # Show all summaries (across both archive.org picks and custom titles)
                        accounts_now = get_accounts("movies")
                        acc_now = next(
                            (a for a in accounts_now if a.get("id") == selected_account["id"]),
                            selected_account,
                        )
                        summarized = acc_now.get("summarized_movies", []) or []
                        videos = acc_now.get("videos", []) or []
                        if not summarized and not videos:
                            warning(" No summaries found.")
                        else:
                            t = PrettyTable()
                            t.field_names = ["#", "Date", "Source", "Title"]
                            t.align["Title"] = "l"
                            row = 0
                            for s in summarized:
                                row += 1
                                t.add_row([
                                    row,
                                    colored(s.get("date", ""), "blue"),
                                    colored("archive.org", "magenta"),
                                    colored(_trunc(s.get("title", ""), 60), "green"),
                                ])
                            for v in videos:
                                row += 1
                                t.add_row([
                                    row,
                                    colored(v.get("date", ""), "blue"),
                                    colored("youtube", "magenta"),
                                    colored(_trunc(v.get("title", ""), 60), "green"),
                                ])
                            print(t)
                    elif movie_choice == 5:
                        # Re-upload existing summary (reuses inherited reupload_video)
                        mp_dir = os.path.join(ROOT_DIR, ".mp")
                        try:
                            mp4s = sorted(
                                [os.path.join(mp_dir, f) for f in os.listdir(mp_dir) if f.lower().endswith(".mp4")],
                                key=os.path.getmtime,
                                reverse=True,
                            )
                        except FileNotFoundError:
                            mp4s = []
                        if not mp4s:
                            warning(" => No saved videos in .mp/.")
                        else:
                            for i, p in enumerate(mp4s, 1):
                                size_mb = os.path.getsize(p) / (1024 * 1024)
                                mtime = datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
                                print(colored(f"   {i}. {os.path.basename(p)}  ({size_mb:.1f} MB, {mtime})", "cyan"))
                            sel = question("\nSelect a video to re-upload (number, empty to cancel): ").strip()
                            if sel:
                                try:
                                    idx = int(sel) - 1
                                    if 0 <= idx < len(mp4s):
                                        ms.reupload_video(mp4s[idx], None)
                                except (ValueError, Exception) as re_err:
                                    error(f"Re-upload failed: {type(re_err).__name__}: {re_err}")
                    elif movie_choice == 6:
                        info("How often do you want to upload?")
                        info("\n============ OPTIONS ============", False)
                        for idx, cron_opt in enumerate(MOVIE_CRON_OPTIONS):
                            print(colored(f" {idx + 1}. {cron_opt}", "cyan"))
                        info("=================================\n", False)
                        cron_choice = int(question("Select an Option: "))
                        cron_script_path = os.path.join(ROOT_DIR, "src", "cron.py")
                        command = ["python", cron_script_path, "movies", selected_account["id"], get_active_model()]

                        def movie_job():
                            subprocess.run(command)

                        if cron_choice == 1:
                            schedule.every(1).day.do(movie_job)
                            success("Set up CRON Job.")
                        elif cron_choice == 2:
                            schedule.every().day.at("10:00").do(movie_job)
                            schedule.every().day.at("16:00").do(movie_job)
                            success("Set up CRON Job.")
                        else:
                            break
                    elif movie_choice == 7:
                        if get_verbose():
                            info(" => Climbing Options Ladder...", False)
                        break
    elif user_input == 6:
        if get_verbose():
            print(colored(" => Quitting...", "blue"))
        sys.exit(0)
    else:
        error("Invalid option selected. Please try again.", "red")
        main()
    

if __name__ == "__main__":
    # Print ASCII Banner
    print_banner()

    first_time = get_first_time_running()

    if first_time:
        print(colored("Hey! It looks like you're running MoneyPrinter V2 for the first time. Let's get you setup first!", "yellow"))

    # Setup file tree
    assert_folder_structure()

    # Remove temporary files
    rem_temp_files()

    # Fetch MP3 Files
    fetch_songs()

    # Select LLM provider and model
    from config import get_llm_provider, get_pollinations_text_model

    llm_provider = get_llm_provider()
    set_llm_provider(llm_provider)

    if llm_provider == "gemini":
        from config import get_gemini_models
        models = get_gemini_models()
        success(f"Using Gemini LLM (cascade: {' → '.join(models)})")
    elif llm_provider == "pollinations":
        # Use Pollinations.ai (free, no local server needed)
        configured_model = get_pollinations_text_model()
        if configured_model:
            select_model(configured_model)
            success(f"Using Pollinations.ai with model: {configured_model}")
        else:
            try:
                models = list_models()
            except Exception as e:
                warning(f"Could not fetch Pollinations models: {e}")
                models = ["openai", "openai-large", "mistral", "llama", "deepseek"]

            info("\n======= POLLINATIONS MODELS =======", False)
            for idx, model_name in enumerate(models):
                print(colored(f" {idx + 1}. {model_name}", "cyan"))
            info("===================================\n", False)

            model_choice = None
            while model_choice is None:
                raw = input(colored("Select a model: ", "magenta")).strip()
                try:
                    choice_idx = int(raw) - 1
                    if 0 <= choice_idx < len(models):
                        model_choice = models[choice_idx]
                    else:
                        warning("Invalid selection. Try again.")
                except ValueError:
                    warning("Please enter a number.")

            select_model(model_choice)
            success(f"Using Pollinations.ai model: {model_choice}")
    else:
        # Use Ollama (local)
        configured_model = get_ollama_model()
        if configured_model:
            select_model(configured_model)
            success(f"Using Ollama model: {configured_model}")
        else:
            try:
                models = list_models()
            except Exception as e:
                error(f"Could not connect to Ollama: {e}")
                sys.exit(1)

            if not models:
                error("No models found on Ollama. Pull a model first (e.g. 'ollama pull llama3.2:3b').")
                sys.exit(1)

            info("\n========== OLLAMA MODELS =========", False)
            for idx, model_name in enumerate(models):
                print(colored(f" {idx + 1}. {model_name}", "cyan"))
            info("==================================\n", False)

            model_choice = None
            while model_choice is None:
                raw = input(colored("Select a model: ", "magenta")).strip()
                try:
                    choice_idx = int(raw) - 1
                    if 0 <= choice_idx < len(models):
                        model_choice = models[choice_idx]
                    else:
                        warning("Invalid selection. Try again.")
                except ValueError:
                    warning("Please enter a number.")

            select_model(model_choice)
            success(f"Using Ollama model: {model_choice}")

    while True:
        main()
