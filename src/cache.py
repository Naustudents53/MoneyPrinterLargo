import os
import json
import time
import contextlib

from typing import List
import config


@contextlib.contextmanager
def json_write_lock(json_path: str, timeout: float = 15.0):
    """Process-safe exclusive lock for a JSON cache file.

    Uses a `.lock` sentinel file — O_CREAT|O_EXCL is atomic on NTFS and
    ext4, so it works correctly across multiple subprocesses without any
    shared memory. Stale locks (left by a crashed process) are removed
    automatically after `timeout` seconds."""
    lock_path = json_path + ".lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                age = time.monotonic() - os.path.getmtime(lock_path)
                if age > timeout:
                    os.remove(lock_path)
                    continue
            except OSError:
                pass
            if time.monotonic() > deadline:
                try:
                    os.remove(lock_path)
                except Exception:
                    pass
                continue
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(lock_path)
        except Exception:
            pass

def atomic_write_json(path: str, data, indent: int = 4) -> None:
    """Write JSON via tmp + os.replace so a crash mid-write can never leave a
    truncated/corrupt file behind. Callers that need cross-process exclusion
    must hold `json_write_lock(path)` around read-modify-write themselves."""
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=indent, ensure_ascii=False)
    os.replace(tmp_path, path)


def get_cache_path(root_dir: str | None = None) -> str:
    """
    Gets the path to the cache file.

    Returns:
        path (str): The path to the cache folder
    """
    path = os.path.join(root_dir or config.ROOT_DIR, '.mp')
    os.makedirs(path, exist_ok=True)
    return path

def _get_cache_subdir(name: str, root_dir: str | None = None) -> str:
    path = os.path.join(get_cache_path(root_dir), name)
    os.makedirs(path, exist_ok=True)
    return path

def get_temp_cache_path(root_dir: str | None = None) -> str:
    """Scratch space for generated images, audio, subtitles, and previews."""
    return _get_cache_subdir('tmp', root_dir)

def get_video_cache_path(root_dir: str | None = None) -> str:
    """Persistent rendered videos and their per-video sidecars."""
    return _get_cache_subdir('videos', root_dir)

def get_photo_uploads_path(root_dir: str | None = None) -> str:
    """Temporary web uploads before they are normalized for MoviePy."""
    return _get_cache_subdir('photo_uploads', root_dir)

def get_job_logs_path(root_dir: str | None = None) -> str:
    """Detailed per-job logs used by the Operations page."""
    return _get_cache_subdir('job_logs', root_dir)

def iter_video_cache_paths(root_dir: str | None = None) -> List[str]:
    """Return current and legacy video folders, without duplicates."""
    paths = [get_video_cache_path(root_dir), get_cache_path(root_dir)]
    seen = set()
    out = []
    for path in paths:
        norm = os.path.abspath(path)
        if norm in seen:
            continue
        seen.add(norm)
        out.append(path)
    return out

def get_afm_cache_path() -> str:
    """
    Gets the path to the Affiliate Marketing cache file.

    Returns:
        path (str): The path to the AFM cache folder
    """
    return os.path.join(get_cache_path(), 'afm.json')

def get_twitter_cache_path() -> str:
    """
    Gets the path to the Twitter cache file.

    Returns:
        path (str): The path to the Twitter cache folder
    """
    return os.path.join(get_cache_path(), 'twitter.json')

def get_youtube_cache_path() -> str:
    """
    Gets the path to the YouTube cache file.

    Returns:
        path (str): The path to the YouTube cache folder
    """
    return os.path.join(get_cache_path(), 'youtube.json')

def get_provider_cache_path(provider: str) -> str:
    """
    Gets the cache path for a supported account provider.

    Args:
        provider (str): The provider name ("twitter" or "youtube")

    Returns:
        path (str): The provider-specific cache path

    Raises:
        ValueError: If the provider is unsupported
    """
    if provider == "twitter":
        return get_twitter_cache_path()
    if provider == "youtube":
        return get_youtube_cache_path()

    raise ValueError(f"Unsupported provider '{provider}'. Expected 'twitter' or 'youtube'.")

def get_accounts(provider: str) -> List[dict]:
    """
    Gets the accounts from the cache.

    Args:
        provider (str): The provider to get the accounts for

    Returns:
        account (List[dict]): The accounts
    """
    cache_path = get_provider_cache_path(provider)

    if not os.path.exists(cache_path):
        # Create the cache file
        with open(cache_path, 'w', encoding='utf-8') as file:
            json.dump({
                "accounts": []
            }, file, indent=4)

    with open(cache_path, 'r', encoding='utf-8') as file:
        parsed = json.load(file)

        if parsed is None:
            return []
        
        if 'accounts' not in parsed:
            return []

        # Get accounts dictionary
        return parsed['accounts']

def add_account(provider: str, account: dict) -> None:
    """
    Adds an account to the cache.

    Args:
        provider (str): The provider to add the account to ("twitter" or "youtube")
        account (dict): The account to add

    Returns:
        None
    """
    cache_path = get_provider_cache_path(provider)

    with json_write_lock(cache_path):
        accounts = get_accounts(provider)
        accounts.append(account)
        atomic_write_json(cache_path, {"accounts": accounts})

def remove_account(provider: str, account_id: str) -> None:
    """
    Removes an account from the cache.

    Args:
        provider (str): The provider to remove the account from ("twitter" or "youtube")
        account_id (str): The ID of the account to remove

    Returns:
        None
    """
    cache_path = get_provider_cache_path(provider)

    with json_write_lock(cache_path):
        accounts = get_accounts(provider)
        accounts = [a for a in accounts if a['id'] != account_id]
        atomic_write_json(cache_path, {"accounts": accounts})

def get_products() -> List[dict]:
    """
    Gets the products from the cache.

    Returns:
        products (List[dict]): The products
    """
    cache_path = get_afm_cache_path()
    if not os.path.exists(cache_path):
        atomic_write_json(cache_path, {"products": []})
        return []

    try:
        with open(cache_path, 'r', encoding='utf-8') as file:
            parsed = json.load(file)
    except (ValueError, OSError):
        return []
    if not isinstance(parsed, dict):
        return []
    products = parsed.get("products")
    return products if isinstance(products, list) else []

def add_product(product: dict) -> None:
    """
    Adds a product to the cache.

    Args:
        product (dict): The product to add

    Returns:
        None
    """
    cache_path = get_afm_cache_path()
    with json_write_lock(cache_path):
        products = get_products()
        products.append(product)
        atomic_write_json(cache_path, {"products": products})
    
def get_results_cache_path() -> str:
    """
    Gets the path to the results cache file.

    Returns:
        path (str): The path to the results cache folder
    """
    return os.path.join(get_cache_path(), 'scraper_results.csv')

def _sanitize_account_id(account_id: str) -> str:
    """Reduce an account id to a filesystem-safe slug for a memory file."""
    safe = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in str(account_id or ''))
    return safe or 'default'

def get_learning_cache_path(account_id: str) -> str:
    """Per-account LearningCoach memory file under .mp/learning/."""
    folder = _get_cache_subdir('learning')
    return os.path.join(folder, f"{_sanitize_account_id(account_id)}.json")

def get_learning(account_id: str) -> dict:
    """Read the LearningCoach memory for an account (empty dict if none).

    Reads under the same lock used by `save_learning` so a concurrent writer
    can never hand us a half-written file (which would read as {} and let the
    next reflection overwrite — and lose — every accumulated lesson).
    """
    path = get_learning_cache_path(account_id)
    if not os.path.exists(path):
        return {}
    try:
        with json_write_lock(path):
            with open(path, 'r', encoding='utf-8') as file:
                parsed = json.load(file)
    except (ValueError, OSError):
        return {}
    return parsed if isinstance(parsed, dict) else {}

def save_learning(account_id: str, data: dict) -> None:
    """Persist the LearningCoach memory for an account atomically."""
    path = get_learning_cache_path(account_id)
    tmp_path = path + '.tmp'
    with json_write_lock(path):
        with open(tmp_path, 'w', encoding='utf-8') as file:
            json.dump(data or {}, file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
