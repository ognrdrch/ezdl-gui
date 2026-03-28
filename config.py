import os
import sys
import toml
from pathlib import Path

VERSION = "2.0.0"

def get_app_dir() -> Path:
    """Get the application directory (works frozen or not)."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent

def get_default_music_dir() -> str:
    if sys.platform == "win32":
        # Use Windows conventional Music folder under USERPROFILE
        return str(Path.home() / "Music")
    # Linux/macOS: respect XDG convention, fall back to ~/Music
    xdg = os.environ.get("XDG_MUSIC_DIR")
    if xdg:
        return xdg
    return str(Path.home() / "Music")

def get_default_video_dir() -> str:
    if sys.platform == "win32":
        # Use Windows conventional Videos folder under USERPROFILE
        return str(Path.home() / "Videos")
    # Linux/macOS: respect XDG convention, fall back to ~/Videos
    xdg = os.environ.get("XDG_VIDEOS_DIR")
    if xdg:
        return xdg
    return str(Path.home() / "Videos")

APP_DIR = get_app_dir()
SETTINGS_PATH = APP_DIR / "settings.toml"

DEFAULT_SETTINGS = {
    "settings": {
        "audio_path": get_default_music_dir(),
        "video_path": get_default_video_dir(),
        "file_naming_scheme": "%(title)s.%(ext)s",
        "audio_quality": 0,
        "audio_format": "flac",
        "video_format": "mp4",
        "download_playlist": False,
        "use_cookies": False,
        "cookie_browser": "brave",
        "embed_thumbnail": True,
        "embed_metadata": True,
    },
    "other": {
        "spotify_id": "client_id",
        "spotify_secret": "client_secret",
    }
}

def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = toml.load(f)
        # Merge with defaults to fill missing keys
        merged = _deep_merge(DEFAULT_SETTINGS, data)
        return merged
    except Exception as e:
        print(f"[settings] Error loading: {e}, using defaults")
        return DEFAULT_SETTINGS.copy()

def save_settings(settings: dict):
    # Backup before saving
    backup = SETTINGS_PATH.parent / "settings_backup.toml"
    if SETTINGS_PATH.exists():
        import shutil
        shutil.copy2(SETTINGS_PATH, backup)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        toml.dump(settings, f)

def _deep_merge(default: dict, current: dict) -> dict:
    result = default.copy()
    for key, val in current.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
