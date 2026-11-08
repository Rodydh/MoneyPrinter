"""Search Wikimedia Commons for freely reusable video clips and photos.

No API key needed. Creator/licence details are retained for mandatory attribution.
Commons sometimes has limited real video footage; photos are animated into clips.
"""
import html
import re

import requests

from logstream import log

API_URL = "https://commons.wikimedia.org/w/api.php"
HEADERS = {
    "User-Agent": "MoneyPrinterCommons/1.0 (https://github.com/Rodydh/MoneyPrinter; noncommercial project)",
}
ALLOWED_LICENSE_PREFIXES = ("CC BY", "CC0", "PUBLIC DOMAIN", "PD-", "PUBLIC-DOMAIN")
MAX_VIDEO_BYTES = 35 * 1024 * 1024


def _text(metadata: dict, key: str) -> str:
    raw = str((metadata.get(key) or {}).get("value") or "")
    return re.sub(r"<[^>]*>", "", html.unescape(raw)).strip()


def _allowed_license(name: str) -> bool:
    norm = " ".join(name.upper().replace("-", " ").split())
    if "NC" in norm.split() or "ND" in norm.split():
        return False
    return norm.startswith(("CC BY ", "CC0", "PUBLIC DOMAIN", "PD ", "PUBLIC-DOMAIN"))


def _parse_page(page: dict) -> dict | None:
    info = (page.get("imageinfo") or [{}])[0]
    mime = str(info.get("mime") or "").lower()
    kind = "video" if mime.startswith("video/") or mime == "application/ogg" else (
        "photo" if mime in ("image/jpeg", "image/png", "image/webp") else None
    )
    if not kind:
        return None

    meta = info.get("extmetadata") or {}
    license_name = _text(meta, "LicenseShortName")
    if not _allowed_license(license_name):
        return None

    if kind == "video" and int(info.get("size") or 0) > MAX_VIDEO_BYTES:
        return None

    url = (info.get("thumburl") if kind == "photo" else info.get("url")) or info.get("url")
    if not isinstance(url, str) or not url.startswith("https://upload.wikimedia.org/"):
        return None

    return {
        "title": page.get("title", "Wikimedia media"),
        "url": url,
        "page_url": info.get("descriptionurl") or "",
        "artist": _text(meta, "Artist") or _text(meta, "Credit") or "See source page",
        "license": license_name,
        "license_url": _text(meta, "LicenseUrl"),
        "type": kind,
    }


def _search_once(query: str, filetype: str, limit: int) -> list[dict]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{query} filetype:{filetype}",
        "gsrnamespace": 6,
        "gsrlimit": max(10, min(40, limit * 3)),
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "iiurlwidth": 1280,
        "format": "json",
        "formatversion": 2,
    }
    response = requests.get(API_URL, params=params, headers=HEADERS, timeout=25)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    pages = sorted(payload.get("query", {}).get("pages", []), key=lambda p: p.get("index", 999999))
    return [item for page in pages if (item := _parse_page(page))]


def search_for_stock_videos(query: str, it: int = 12, min_dur: int = 0) -> list[dict]:
    """Search for free videos, falling back to photos; no API key needed.

    min_dur is retained only for backwards-compatible callers; actual clips
    are shortened/looped to match narration by the video compositor.
    """
    if not query or not query.strip():
        return []
    limit = max(1, min(20, it))
    try:
        videos = [m for m in _search_once(query, "video", limit) if m["type"] == "video"]
        photos = []
        # Always include photos as backups in case a video cannot be downloaded.
        if len(videos) < 3:
            photos = [m for m in _search_once(query, "bitmap", limit) if m["type"] == "photo"]
        combined = (videos + photos)[:limit]
        log(f'[+] Wikimedia Commons: "{query}" found {len(combined)} reusable media files', "info")
        return combined
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        log(f"[-] Wikimedia Commons search error for {query}: {exc}", "warning")
        return []
