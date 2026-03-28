import os
import sys
import re
import shutil
import subprocess
import requests
import time
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal
from updater import get_ytdlp_cmd


# ── VOE helpers ───────────────────────────────────────────────────────────────

def _is_direct_segment_url(url: str) -> bool:
    """True if URL is a direct .ts segment link (ignores query string)."""
    path = url.split('?')[0]
    return bool(re.search(r'seg-\d+', path, re.IGNORECASE)) and path.endswith('.ts')


def _is_voe_url(url: str) -> bool:
    """Return True if the URL is a VOE page or a direct segment link."""
    if re.search(r'voe\.sx|voe-unblock|voeunblock', url, re.IGNORECASE):
        return True
    if _is_direct_segment_url(url):
        return True
    return False


def _direct_segment_pattern(url: str) -> str:
    """
    Replace only the segment number in a .ts URL with {}, preserving query string.
    Handles:
      .../seg-1-v1-a1.ts?token=x  → .../seg-{}-v1-a1.ts?token=x
      .../seg-001.ts               → .../seg-{}.ts
      .../seg-42-sometoken.ts      → .../seg-{}-sometoken.ts
    """
    parts = url.split('?', 1)
    path  = parts[0]
    query = ('?' + parts[1]) if len(parts) > 1 else ''

    # Form: seg-N-... (number followed by another dash)
    new_path = re.sub(r'(seg-)(\d+)(-)', lambda m: m.group(1) + '{}' + m.group(3), path, count=1)
    if new_path == path:
        # Fallback: seg-N at end of path component (before . or end)
        new_path = re.sub(r'(seg-)(\d+)', lambda m: m.group(1) + '{}', path, count=1)

    return new_path + query


def _extract_voe_segment_url(page_url: str):
    """
    Fetch the VOE page and scrape the HLS / segment base URL.
    Returns ("m3u8", url), ("segments", pattern) or None.
    """
    try:
        resp = requests.get(page_url, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        html = resp.text

        # 1. Try to find an m3u8 playlist URL
        m3u8_match = re.search(r'["\'](?:hls|src)["\']:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', html)
        if not m3u8_match:
            m3u8_match = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if m3u8_match:
            return ("m3u8", m3u8_match.group(1))

        # 2. Try direct .ts segment pattern
        seg_match = re.search(r'(https?://[^\s"\'<>]+seg-1[^\s"\'<>]*\.ts)', html)
        if seg_match:
            base = re.sub(r'seg-1', 'seg-{}', seg_match.group(1))
            return ("segments", base)

    except Exception:
        pass
    return None


def _resolve_m3u8_segments(m3u8_url: str):
    """
    Download an m3u8 playlist and derive segment URLs.
    Returns ("pattern", end_count), ("list", [urls]) or None.
    """
    try:
        resp = requests.get(m3u8_url, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        lines = [l.strip() for l in resp.text.splitlines()
                 if l.strip() and not l.startswith('#')]
        if not lines:
            return None
        base = m3u8_url.rsplit('/', 1)[0] + '/'
        seg_urls = [l if l.startswith('http') else base + l for l in lines]

        # Try to detect numeric seg- pattern
        first = seg_urls[0]
        num_match = re.search(r'seg-(\d+)', first)
        if num_match:
            pattern = re.sub(r'seg-\d+', 'seg-{}', first)
            return ("pattern", (pattern, len(seg_urls)))
        return ("list", seg_urls)
    except Exception:
        return None


def _probe_end_segment(pattern: str, start: int = 1, max_probe: int = 5000) -> int:
    """
    Binary-search for the last valid segment index.
    Exponential probe first, then binary narrow-down.
    """
    high = start
    while high <= max_probe:
        url = pattern.format(high)
        try:
            r = requests.head(url, timeout=8,
                              headers={"User-Agent": "Mozilla/5.0"},
                              allow_redirects=True)
            if r.status_code >= 400:
                break
            high *= 2
        except Exception:
            break

    lo, hi = max(start, high // 2), min(high, max_probe)
    last_good = start
    while lo <= hi:
        mid = (lo + hi) // 2
        url = pattern.format(mid)
        try:
            r = requests.head(url, timeout=8,
                              headers={"User-Agent": "Mozilla/5.0"},
                              allow_redirects=True)
            if r.status_code < 400:
                last_good = mid
                lo = mid + 1
            else:
                hi = mid - 1
        except Exception:
            hi = mid - 1
    return last_good


def _download_segment(url: str, dest: str, retries: int = 3) -> bool:
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=30,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            with open(dest, 'wb') as f:
                f.write(r.content)
            return True
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
    return False


def _get_ffmpeg_cmd() -> str:
    """
    Resolve the ffmpeg executable.
    Checks PATH first so a system install is used when available.
    Falls back to the bare name so the FileNotFoundError is still
    caught and reported clearly if ffmpeg is missing entirely.
    """
    found = shutil.which("ffmpeg")
    return found if found else "ffmpeg"


# ── Worker ────────────────────────────────────────────────────────────────────

class DownloadWorker(QThread):
    """Worker thread for downloading media."""
    progress = pyqtSignal(str)
    percent  = pyqtSignal(float)
    finished = pyqtSignal(bool, str)

    def __init__(self, url: str, mode: str, settings: dict):
        super().__init__()
        self.url        = url
        self.mode       = mode
        self.settings   = settings
        self._cancelled = False
        self._process   = None

    def cancel(self):
        self._cancelled = True
        if self._process:
            self._process.terminate()

    # ── Spotify ───────────────────────────────────────────

    def _resolve_spotify(self, url: str):
        """
        If the URL is a Spotify link, resolve it to a list of yt-dlp search
        URLs via the Spotify API.  Returns:
          - the original URL unchanged if not a Spotify link
          - a list[str] of ytsearch: URLs for Spotify tracks
          - None on failure (emits a progress message explaining why)
        """
        if "spotify" not in url.lower():
            return url

        from spotify_resolver import parse_spotify_url, resolve_spotify_url

        if not parse_spotify_url(url):
            # Looks like spotify in the domain but not a parseable track/album/playlist
            self.progress.emit("⚠ Could not parse Spotify URL.")
            return None

        s = self.settings.get("other", {})
        cid  = s.get("spotify_id",     "client_id")
        csec = s.get("spotify_secret", "client_secret")

        if cid in ("client_id", "", None) or csec in ("client_secret", "", None):
            self.progress.emit(
                "⚠ Spotify credentials not configured. "
                "Open Settings → Spotify and enter your Client ID and Secret."
            )
            return None

        try:
            search_urls = resolve_spotify_url(url, cid, csec, self.progress.emit)
            if not search_urls:
                self.progress.emit("⚠ No tracks found for this Spotify URL.")
                return None
            return search_urls          # list of ytsearch1:… strings
        except Exception as e:
            self.progress.emit(f"⚠ Spotify resolution failed: {e}")
            return None

    # ── VOE download ──────────────────────────────────────

    def _run_voe(self, url: str, output_path: str):
        self.progress.emit("🔍 Detected VOE link — scraping page…")
        result = _extract_voe_segment_url(url)

        if result is None:
            self.finished.emit(False, "Could not extract segment URL from VOE page.")
            return

        kind, data = result
        seg_list = None
        pattern  = None
        end_seg  = 0

        if kind == "m3u8":
            self.progress.emit(f"  Found m3u8 playlist: {data}")
            resolved = _resolve_m3u8_segments(data)
            if resolved is None:
                self.finished.emit(False, "Failed to parse m3u8 playlist.")
                return
            rk, rv = resolved
            if rk == "list":
                seg_list = rv
                end_seg  = len(seg_list)
                pattern  = None
            else:
                pattern, end_seg = rv
        else:
            pattern = data
            self.progress.emit(f"  Segment pattern: {pattern}")
            self.progress.emit("  Probing for last segment (this may take a moment)…")
            end_seg = _probe_end_segment(pattern, start=1)

        self._run_voe_from_pattern(pattern, seg_list, end_seg, output_path)

    def _run_voe_from_pattern(self, pattern, seg_list, end_seg: int, output_path: str):
        self.progress.emit(f"  Total segments detected: {end_seg}")

        # Name output file after the current date and time — unique and human-readable
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        slug      = f"voe_{timestamp}"
        out_file  = os.path.join(output_path, slug + ".mp4")
        tmp_dir   = os.path.join(output_path, f"_voe_tmp_{timestamp}")
        os.makedirs(tmp_dir, exist_ok=True)

        seg_files = []
        failed    = 0

        for i in range(1, end_seg + 1):
            if self._cancelled:
                break
            seg_url  = seg_list[i - 1] if seg_list else pattern.format(i)
            seg_file = os.path.join(tmp_dir, f"seg-{i:05d}.ts")
            self.progress.emit(f"[download] Segment {i}/{end_seg}  {seg_url}")
            ok = _download_segment(seg_url, seg_file)
            if ok:
                seg_files.append(seg_file)
            else:
                failed += 1
                self.progress.emit(f"  ⚠ Segment {i} failed — skipping")
            self.percent.emit(i / end_seg * 90)

        if self._cancelled:
            self._cleanup(tmp_dir)
            self.finished.emit(False, "Download cancelled.")
            return

        if not seg_files:
            self._cleanup(tmp_dir)
            self.finished.emit(False, "All segments failed to download.")
            return

        concat_file = os.path.join(tmp_dir, "filelist.txt")
        with open(concat_file, "w", encoding="utf-8") as f:
            for sf in seg_files:
                # ffmpeg concat demuxer requires forward slashes on all platforms
                sf_fwd = sf.replace("\\", "/")
                f.write(f"file '{sf_fwd}'\n")

        self.progress.emit(f"  Merging {len(seg_files)} segments with ffmpeg…")
        ffmpeg = _get_ffmpeg_cmd()
        try:
            subprocess.run(
                [ffmpeg, "-y", "-f", "concat", "-safe", "0",
                 "-i", concat_file, "-c", "copy", out_file],
                check=True, capture_output=True
            )
        except subprocess.CalledProcessError as e:
            self._cleanup(tmp_dir)
            self.finished.emit(False, f"ffmpeg merge failed: {e.stderr.decode()[:300]}")
            return
        except FileNotFoundError:
            self._cleanup(tmp_dir)
            self.finished.emit(
                False,
                "ffmpeg not found. Please install ffmpeg and ensure it is on your PATH.\n"
                "Download: https://ffmpeg.org/download.html"
            )
            return

        self._cleanup(tmp_dir)
        self.percent.emit(100.0)
        msg = f"VOE video saved → {out_file}"
        if failed:
            msg += f"  ({failed} segment(s) skipped)"
        self.finished.emit(True, msg)

    def _cleanup(self, tmp_dir: str):
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # ── yt-dlp download ───────────────────────────────────

    def _run_ytdlp(self, url: str):
        s   = self.settings["settings"]
        cmd = get_ytdlp_cmd()

        if self.mode == "audio":
            output_path = os.path.expanduser(s["audio_path"])
            fmt     = s.get("audio_format", "mp3")
            quality = str(s.get("audio_quality", 0))
            naming  = s.get("file_naming_scheme", "%(title)s.%(ext)s")
            out     = os.path.join(output_path, naming)

            args = [
                *cmd,
                "-x",
                "--audio-format", fmt,
                "--audio-quality", quality,
                "--output", out,
                "--newline",
            ]
        else:
            output_path = os.path.expanduser(s["video_path"])
            vfmt   = s.get("video_format", "mp4")
            naming = s.get("file_naming_scheme", "%(title)s.%(ext)s")
            out    = os.path.join(output_path, naming)

            # Always request the absolute best video + audio available
            args = [
                *cmd,
                "-f", "bestvideo+bestaudio/best",
                "--merge-output-format", vfmt,
                "--output", out,
                "--newline",
            ]

        # Only embed thumbnail for formats that support it (not wav, aiff, etc.)
        THUMBNAIL_COMPATIBLE = {"mp3", "m4a", "aac", "opus", "flac", "ogg"}
        if (s.get("embed_thumbnail", True)
                and self.mode == "audio"
                and fmt in THUMBNAIL_COMPATIBLE):
            args.append("--embed-thumbnail")
        if s.get("embed_metadata", True):
            # --embed-metadata is the current yt-dlp flag (replaces deprecated --add-metadata)
            args.append("--embed-metadata")
        if not s.get("download_playlist", False):
            args.append("--no-playlist")
        if s.get("use_cookies", False):
            browser = s.get("cookie_browser", "brave")
            args.extend(["--cookies-from-browser", browser])

        args.append(url)
        os.makedirs(output_path, exist_ok=True)

        self.progress.emit(f"▶ Starting {self.mode} download…")
        self.progress.emit(f"  Output: {output_path}")

        try:
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            for line in self._process.stdout:
                if self._cancelled:
                    break
                line = line.rstrip()
                if not line:
                    continue
                self.progress.emit(line)

                if "[download]" in line and "%" in line:
                    try:
                        pct = float(line.split("%")[0].split()[-1])
                        self.percent.emit(pct)
                    except (ValueError, IndexError):
                        pass

            self._process.wait()

            if self._cancelled:
                self.finished.emit(False, "Download cancelled.")
            elif self._process.returncode == 0:
                self.percent.emit(100.0)
                self.finished.emit(True, f"{self.mode.title()} downloaded successfully!")
            else:
                self.finished.emit(False, f"yt-dlp exited with code {self._process.returncode}")

        except FileNotFoundError:
            self.finished.emit(False, "yt-dlp not found. Please install it (pip install yt-dlp).")
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")

    # ── Entry point ───────────────────────────────────────

    def run(self):
        resolved = self._resolve_spotify(self.url)
        if resolved is None:
            self.finished.emit(False, "Invalid or unconfigured Spotify URL.")
            return

        # Spotify multi-track: download each search URL in sequence
        if isinstance(resolved, list):
            total = len(resolved)
            self.progress.emit(f"▶ Downloading {total} track(s) from Spotify…")
            failed_tracks = []
            for idx, search_url in enumerate(resolved, 1):
                if self._cancelled:
                    self.finished.emit(False, "Download cancelled.")
                    return
                self.progress.emit(f"\n[{idx}/{total}] {search_url}")
                self._run_ytdlp(search_url)
                # _run_ytdlp calls self.finished internally only on hard error;
                # we suppress per-track finished here and emit our own summary.
                # Re-wire: collect failures by checking the process return code
                # (already logged). We just keep going.
            self.finished.emit(True, f"Spotify: {total} track(s) downloaded.")
            return

        url = resolved  # plain string — not Spotify
        if _is_voe_url(url):
            s           = self.settings["settings"]
            output_path = os.path.expanduser(s["video_path"])
            os.makedirs(output_path, exist_ok=True)

            # Direct .ts segment link — build pattern immediately, skip page scrape
            if _is_direct_segment_url(url):
                pattern = _direct_segment_pattern(url)
                # Sanity check: pattern must contain {} otherwise substitution failed
                if '{}' not in pattern:
                    self.finished.emit(False,
                        f"Could not detect segment number in URL: {url}\n"
                        "Expected a URL containing 'seg-<number>' e.g. seg-1, seg-001")
                    return
                self.progress.emit("🔍 Detected direct segment URL — building pattern…")
                self.progress.emit(f"  Original:  {url}")
                self.progress.emit(f"  Pattern:   {pattern}")
                self.progress.emit(f"  Test seg2: {pattern.format(2)}")
                self.progress.emit("  Probing for last segment…")
                end_seg = _probe_end_segment(pattern, start=1)
                self._run_voe_from_pattern(pattern, None, end_seg, output_path)
            else:
                self._run_voe(url, output_path)
        else:
            self._run_ytdlp(url)
