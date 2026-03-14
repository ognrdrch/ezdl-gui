import re
import subprocess
import sys
from pathlib import Path
from PyQt5.QtCore import pyqtSignal, QThread

from config import get_app_dir


def _parse_requirements() -> list[str]:
    """
    Read requirements.txt next to the app and return a list of plain package
    names (stripping version specifiers and blank/comment lines).
    """
    req_file = get_app_dir() / "requirements.txt"
    if not req_file.exists():
        # Fallback hardcoded list matching requirements.txt
        return ["yt-dlp", "toml", "PyQt5", "requests", "mutagen"]
    packages = []
    for line in req_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip version specifiers: >=, ==, <=, ~=, !=, >  <
        name = re.split(r"[><=!~;\s]", line)[0].strip()
        if name:
            packages.append(name)
    return packages


class UpdateWorker(QThread):
    """Worker thread to update all packages listed in requirements.txt."""
    log      = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, update_type="all"):
        super().__init__()
        self.update_type = update_type  # kept for API compat, always updates all

    def run(self):
        packages = _parse_requirements()
        self.log.emit(f"Packages to update: {', '.join(packages)}")

        failed = []
        for pkg in packages:
            self.log.emit(f"  Updating {pkg}…")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", pkg],
                    capture_output=True, text=True, timeout=120
                )
                combined = result.stdout + result.stderr
                # Pull out the useful summary line from pip output
                summary = next(
                    (l for l in combined.splitlines()
                     if "Successfully installed" in l
                     or "already up-to-date" in l.lower()
                     or "already satisfied" in l.lower()),
                    ""
                )
                if result.returncode == 0:
                    self.log.emit(f"  ✓ {pkg}: {summary or 'updated OK'}")
                else:
                    err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
                    self.log.emit(f"  ✗ {pkg}: {err[:120]}")
                    failed.append(pkg)
            except Exception as e:
                self.log.emit(f"  ✗ {pkg}: {e}")
                failed.append(pkg)

        if failed:
            self.finished.emit(False, f"Done — failed: {', '.join(failed)}")
        else:
            self.finished.emit(True, f"All {len(packages)} packages up to date!")


def get_ytdlp_version() -> str:
    """Get the currently installed yt-dlp version."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "yt_dlp", "--version"],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip() if result.returncode == 0 else "not found"
        except Exception:
            return "not found"


def get_ytdlp_cmd() -> list:
    """Get the correct yt-dlp command for the current platform."""
    import shutil
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return [sys.executable, "-m", "yt_dlp"]
