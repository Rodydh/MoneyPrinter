"""Download allowed Wikimedia Commons media and convert photos to short video clips."""
from pathlib import Path
import subprocess
from urllib.parse import urlparse
from uuid import uuid4

import requests

from logstream import log
from search import HEADERS
from utils import TEMP_DIR

MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024


def download_media(media: dict, directory: Path = TEMP_DIR) -> str:
    """Return a playable video file, optionally animating an image to MP4.

    Video URL must be from Wikimedia's file CDN. Download size is bounded.
    """
    source_url = media["url"]
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname != "upload.wikimedia.org":
        raise ValueError("Only Wikimedia Commons file uploads are accepted.")

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    kind = media.get("type")
    if kind not in ("video", "photo"):
        raise ValueError(f"Unsupported media type: {kind}")

    suffix = Path(parsed.path).suffix.lower()
    if suffix not in (".webm", ".ogv", ".ogg", ".mp4", ".jpg", ".jpeg", ".png", ".webp"):
        raise ValueError("Unsupported file format.")
    src = directory / (str(uuid4()) + suffix)
    try:
        total = 0
        with requests.get(source_url, headers=HEADERS, timeout=(15, 90), stream=True) as response:
            response.raise_for_status()
            if response.url and urlparse(response.url).hostname != "upload.wikimedia.org":
                raise ValueError("Unexpected media redirect.")
            with src.open("wb") as out:
                for chunk in response.iter_content(chunk_size=1024 * 512):
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise ValueError("Wikimedia media file exceeds size limit.")
                    out.write(chunk)
        if total < 1024:
            raise ValueError("Media file empty or too small.")

        if kind == "video":
            return str(src)

        mp4 = directory / (str(uuid4()) + ".mp4")
        # Commons images are made into short portrait clips for the existing compositor.
        subprocess.run([
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-loop", "1",
            "-framerate", "30", "-i", str(src),
            "-t", "6",
            "-vf", "scale=720:1280:force_original_aspect_ratio=increase,"
                   "crop=720:1280,setsar=1,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
            "-pix_fmt", "yuv420p", str(mp4),
        ], check=True, capture_output=True, text=True, timeout=120)
        if not mp4.exists() or mp4.stat().st_size < 1024:
            raise RuntimeError("Photo conversion did not produce a playable clip.")
        return str(mp4)
    except Exception:
        src.unlink(missing_ok=True)
        raise


def write_credits(media_files: list[dict], destination: Path) -> None:
    """Preserve source URLs and creator/license details for use in video descriptions."""
    lines = [
        "# Media credits – Wikimedia Commons",
        "",
        "These files were used as footage or adapted into portrait video clips.",
        "Review each linked license for attribution and share-alike requirements.",
        "",
    ]
    for item in media_files:
        lines.extend([
            f"- **{item['title']}**",
            f"  - Creator: {item['artist']}",
            f"  - License: {item['license']}",
            f"  - License details: {item['license_url']}",
            f"  - File page: {item['page_url']}",
            f"  - Changes: cropped, resized, and/or shortened to fit a portrait-format video",
            "",
        ])
    Path(destination).write_text("\n".join(lines), encoding="utf-8")
