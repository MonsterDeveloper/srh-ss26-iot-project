from __future__ import annotations

import subprocess
from pathlib import Path


class DerivativeError(RuntimeError):
    pass


def _run(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DerivativeError("Video playback derivative could not be generated") from exc


def _valid_mp4(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 16:
        return False
    try:
        subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
            check=True, capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def create_mp4(source: Path, target: Path) -> str:
    """Create a browser-ready MP4, preferring a lossless remux."""
    try:
        _run(["ffmpeg", "-y", "-fflags", "+genpts", "-r", "30", "-i", str(source), "-c:v", "copy", "-movflags", "+faststart", str(target)])
        if _valid_mp4(target):
            return "remux"
    except DerivativeError:
        pass
    target.unlink(missing_ok=True)
    _run(["ffmpeg", "-y", "-fflags", "+genpts", "-r", "30", "-i", str(source), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)])
    if not _valid_mp4(target):
        raise DerivativeError("Video playback derivative could not be validated")
    return "transcode"
