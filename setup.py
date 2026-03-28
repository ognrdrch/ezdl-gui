#!/usr/bin/env python3
"""
setup.py — EZDL shortcut installer
====================================
Run this once after placing the EZDL folder wherever you want it to live.

  python setup.py          # install
  python setup.py remove   # uninstall

Linux  : creates ~/.local/share/applications/ezdl-downloader.desktop
         and (optionally) ~/Desktop/ezdl-downloader.desktop

Windows: creates a Start Menu shortcut and (optionally) a Desktop shortcut
         using only the standard library + built-in COM via ctypes — no
         extra packages required.

macOS  : creates an alias in ~/Applications pointing at the script.
         (basic support — no .app bundle generation)
"""

import os
import sys
import stat
import shutil
import argparse
import textwrap
from pathlib import Path

# ── Shared metadata ──────────────────────────────────────────────────────────

APP_NAME    = "EZDL"
APP_COMMENT = "YouTube / SoundCloud / Spotify audio & video downloader"
APP_VERSION = "2.0.0"
DESKTOP_ID  = "ezdl-downloader"          # used as filename base on Linux
WIN_LINK    = "EZDL Downloader.lnk"

# ── Helpers ───────────────────────────────────────────────────────────────────

def app_dir() -> Path:
    """Absolute directory that contains this setup script (= the EZDL folder)."""
    return Path(os.path.abspath(__file__)).parent


def find_icon() -> Path | None:
    """Return the first icon file found in the app directory, or None."""
    for name in ("icon512.png", "icon256.png", "icon128.png", "icon.png",
                 "icon512.ico", "icon256.ico", "icon.ico"):
        p = app_dir() / name
        if p.exists():
            return p
    return None


def find_python() -> str:
    """
    Return the absolute path to the Python interpreter that should be used to
    launch EZDL, resolved in this order:

    1. A venv detected next to setup.py  (bin/python on Linux/macOS,
       Scripts/python.exe on Windows) — works even if setup.py was
       accidentally invoked with the system Python.
    2. sys.executable, when it already points inside a venv (VIRTUAL_ENV is
       set or a pyvenv.cfg sits alongside it).
    3. sys.executable as a last resort, with a printed warning.
    """
    base = app_dir()

    # 1. Venv co-located with the app (the recommended Arch Linux setup).
    #    bin/python is often a symlink — use os.path.exists (follows symlinks)
    #    and also glob for versioned names like python3.14 in case only that exists.
    bin_dir     = base / "bin"
    scripts_dir = base / "Scripts"  # Windows

    # Fixed names first
    candidates = [
        bin_dir     / "python",
        bin_dir     / "python3",
        scripts_dir / "python.exe",
    ]
    # Also match versioned names: python3.x, python3.xx
    if bin_dir.is_dir():
        candidates += sorted(bin_dir.glob("python3.*"))

    for c in candidates:
        # os.path.exists follows symlinks; also accept symlinks that resolve fine.
        # Return the venv path itself (NOT resolved) — resolving a venv symlink
        # gives back the system interpreter, which defeats the whole point.
        if os.path.exists(c) and os.path.isfile(c):
            return str(c.absolute())

    # 2. sys.executable is already a venv interpreter
    exe = Path(sys.executable).absolute()
    if (
        os.environ.get("VIRTUAL_ENV")
        or (exe.parent / "pyvenv.cfg").exists()
        or (exe.parent.parent / "pyvenv.cfg").exists()
    ):
        return str(exe)

    # 3. Fallback — warn loudly
    warn(
        "Could not find a venv inside the app directory.\n"
        "         The desktop entry will use the system Python:\n"
        f"           {exe}\n"
        "         On Arch Linux it is recommended to first create a venv:\n"
        f"           python -m venv {base}\n"
        f"           {base / 'bin' / 'pip'} install -r {base / 'requirements.txt'}\n"
        "         Then re-run:  python setup.py"
    )
    return str(exe)


def find_main() -> Path:
    return app_dir() / "main.py"


def ok(msg: str):  print(f"  \033[92m✓\033[0m  {msg}")
def warn(msg: str): print(f"  \033[93m⚠\033[0m  {msg}")
def err(msg: str):  print(f"  \033[91m✗\033[0m  {msg}")
def info(msg: str): print(f"  →  {msg}")


# ── Linux ─────────────────────────────────────────────────────────────────────

DESKTOP_TEMPLATE = """\
[Desktop Entry]
Version=1.0
Type=Application
Name={app_name}
GenericName=Media Downloader
Comment={comment}
Exec={python} {main}
Icon={icon}
Terminal=false
Categories=AudioVideo;Network;
Keywords=youtube;download;audio;video;spotify;soundcloud;
StartupNotify=true
StartupWMClass=ezdl
"""


def _write_desktop_file(path: Path, python: str, main: Path, icon: str):
    content = DESKTOP_TEMPLATE.format(
        app_name = APP_NAME,
        comment  = APP_COMMENT,
        python   = python,
        main     = main,
        icon     = icon,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    # Must be executable for some DE launchers
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_linux():
    python = find_python()
    main   = find_main()
    icon   = find_icon()
    icon_str = str(icon) if icon else APP_NAME  # fallback to name for theme lookup

    if not main.exists():
        err(f"main.py not found at {main}"); sys.exit(1)

    # 1. Applications menu entry
    apps_dir  = Path.home() / ".local" / "share" / "applications"
    desk_file = apps_dir / f"{DESKTOP_ID}.desktop"
    _write_desktop_file(desk_file, python, main, icon_str)
    ok(f"Application menu entry  →  {desk_file}")

    # 2. Desktop shortcut (optional — skip silently if ~/Desktop doesn't exist)
    desktop_dir = Path.home() / "Desktop"
    if desktop_dir.is_dir():
        desk_shortcut = desktop_dir / f"{DESKTOP_ID}.desktop"
        _write_desktop_file(desk_shortcut, python, main, icon_str)
        ok(f"Desktop shortcut        →  {desk_shortcut}")
    else:
        info("~/Desktop not found — skipping desktop shortcut")

    # 3. Refresh desktop database so the entry appears immediately
    update_db = shutil.which("update-desktop-database")
    if update_db:
        os.system(f"{update_db} {apps_dir} 2>/dev/null")
        ok("Desktop database refreshed")
    else:
        warn("update-desktop-database not found — you may need to log out/in")

    print()
    ok(f"EZDL is now available in your application launcher.")


def remove_linux():
    removed = 0
    for path in [
        Path.home() / ".local" / "share" / "applications" / f"{DESKTOP_ID}.desktop",
        Path.home() / "Desktop" / f"{DESKTOP_ID}.desktop",
    ]:
        if path.exists():
            path.unlink()
            ok(f"Removed  {path}")
            removed += 1
    if removed == 0:
        info("No EZDL shortcuts found to remove.")


# ── Windows ───────────────────────────────────────────────────────────────────

def _create_win_shortcut(lnk_path: Path, target: str, args: str,
                          working_dir: str, icon_path: str, description: str):
    """
    Create a Windows .lnk shortcut via the WScript.Shell COM object.
    This is available on every Windows install without extra packages.
    """
    import ctypes, ctypes.wintypes

    # Use PowerShell as a fallback if COM is not available
    ps_script = textwrap.dedent(f"""
        $ws = New-Object -ComObject WScript.Shell
        $s  = $ws.CreateShortcut('{lnk_path}')
        $s.TargetPath       = '{target}'
        $s.Arguments        = '{args}'
        $s.WorkingDirectory = '{working_dir}'
        $s.IconLocation     = '{icon_path}'
        $s.Description      = '{description}'
        $s.Save()
    """).strip()

    try:
        # Preferred: pure Python COM via ctypes (no subprocess needed)
        import win32com.client  # type: ignore
        ws = win32com.client.Dispatch("WScript.Shell")
        s  = ws.CreateShortcut(str(lnk_path))
        s.TargetPath       = target
        s.Arguments        = args
        s.WorkingDirectory = working_dir
        s.IconLocation     = icon_path
        s.Description      = description
        s.Save()
    except ImportError:
        # Fallback: spawn PowerShell (available on Win 7+)
        import subprocess
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())


def _win_start_menu_dir() -> Path:
    """Return the per-user Start Menu Programs folder."""
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    # Fallback
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def _win_desktop_dir() -> Path:
    userprofile = os.environ.get("USERPROFILE", "")
    return Path(userprofile) / "Desktop" if userprofile else Path.home() / "Desktop"


def install_windows():
    python     = find_python()
    main       = find_main()
    icon       = find_icon()
    work_dir   = str(app_dir())

    if not main.exists():
        err(f"main.py not found at {main}"); sys.exit(1)

    # Prefer .ico for Windows; if only .png exists use that (Windows 10+ handles it)
    icon_str = str(icon) if icon else ""

    # ── Find / create a pythonw.exe launcher (no console window) ──────────────
    # pythonw.exe lives alongside python.exe in the same directory
    python_path = Path(python)
    pythonw = python_path.parent / "pythonw.exe"
    launcher = str(pythonw) if pythonw.exists() else python

    args = f'"{main}"'

    # 1. Start Menu shortcut
    start_menu = _win_start_menu_dir()
    start_menu.mkdir(parents=True, exist_ok=True)
    lnk_start = start_menu / WIN_LINK
    try:
        _create_win_shortcut(lnk_start, launcher, args, work_dir, icon_str, APP_COMMENT)
        ok(f"Start Menu shortcut  →  {lnk_start}")
    except Exception as e:
        err(f"Start Menu shortcut failed: {e}")

    # 2. Desktop shortcut
    desktop = _win_desktop_dir()
    lnk_desk = desktop / WIN_LINK
    try:
        _create_win_shortcut(lnk_desk, launcher, args, work_dir, icon_str, APP_COMMENT)
        ok(f"Desktop shortcut     →  {lnk_desk}")
    except Exception as e:
        err(f"Desktop shortcut failed: {e}")

    print()
    ok("EZDL shortcuts created. You can launch it from the Start Menu or Desktop.")


def remove_windows():
    removed = 0
    start_menu = _win_start_menu_dir()
    for path in [start_menu / WIN_LINK, _win_desktop_dir() / WIN_LINK]:
        if path.exists():
            path.unlink()
            ok(f"Removed  {path}")
            removed += 1
    if removed == 0:
        info("No EZDL shortcuts found to remove.")


# ── macOS ─────────────────────────────────────────────────────────────────────

def install_macos():
    python = find_python()
    main   = find_main()
    icon   = find_icon()

    if not main.exists():
        err(f"main.py not found at {main}"); sys.exit(1)

    # Write a tiny launcher shell script wrapped as a pseudo-app alias
    apps_dir = Path.home() / "Applications"
    apps_dir.mkdir(exist_ok=True)
    launcher = apps_dir / "EZDL.command"
    launcher.write_text(
        f'#!/bin/sh\nexec "{python}" "{main}"\n',
        encoding="utf-8"
    )
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    ok(f"Launcher script  →  {launcher}")
    info("Double-click it in Finder (or drag it to the Dock) to launch EZDL.")
    warn("For a proper .app bundle, use py2app or PyInstaller.")


def remove_macos():
    launcher = Path.home() / "Applications" / "EZDL.command"
    if launcher.exists():
        launcher.unlink()
        ok(f"Removed  {launcher}")
    else:
        info("No EZDL launcher found to remove.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Install or remove EZDL desktop shortcuts."
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="install",
        choices=["install", "remove"],
        help="install (default) or remove shortcuts",
    )
    args = parser.parse_args()

    print()
    print(f"  EZDL {APP_VERSION} — shortcut {'installer' if args.action == 'install' else 'remover'}")
    print(f"  App directory : {app_dir()}")
    print(f"  Python        : {find_python()}")
    print()

    platform = sys.platform
    action   = args.action

    if platform.startswith("linux"):
        install_linux()  if action == "install" else remove_linux()
    elif platform == "win32":
        install_windows() if action == "install" else remove_windows()
    elif platform == "darwin":
        install_macos()  if action == "install" else remove_macos()
    else:
        err(f"Unsupported platform: {platform}")
        sys.exit(1)


if __name__ == "__main__":
    main()
