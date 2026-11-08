"""Offline tests of Wikimedia Commons search, licensing, and the downloader."""
from pathlib import Path
import pytest
import requests
import search
from commons_download import download_media, write_credits


def fake_page(title, mime="image/jpeg", license="CC BY-SA 4.0", size=4000):
    return {"title": title, "index": 1, "imageinfo": [{
        "mime": mime,
        "size": size,
        "url": "https://upload.wikimedia.org/wikipedia/commons/0/0a/example.jpg",
        "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/example.jpg/1280px-example.jpg",
        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
        "extmetadata": {
            "LicenseShortName": {"value": license},
            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
            "Artist": {"value": "<b>Wikimedia creator</b>"},
        }
    }]}


def test_commons_image_metadata_and_credits(tmp_path):
    item = search._parse_page(fake_page("File:Example.jpg"))
    assert item["type"] == "photo"
    assert item["license"] == "CC BY-SA 4.0"
    assert item["artist"] == "Wikimedia creator"
    path = tmp_path / "ATTRIBUTION.md"
    write_credits([item], path)
    content = path.read_text()
    assert "Wikimedia creator" in content
    assert "creativecommons.org" in content
    assert "File:Example.jpg" in content


@pytest.mark.parametrize("license", ["CC BY-NC 4.0", "CC BY-ND 4.0", "", "All rights reserved"])
def test_restricted_licenses_skipped(license):
    assert search._parse_page(fake_page("File:Example.jpg", license=license)) is None


def test_oversize_video_is_rejected():
    video = fake_page("File:Movie.webm", mime="video/webm", size=search.MAX_VIDEO_BYTES + 5)
    video["imageinfo"][0]["url"] = "https://upload.wikimedia.org/wikipedia/commons/a/ab/movie.webm"
    assert search._parse_page(video) is None


def test_search_uses_api_and_prioritizes_videos(monkeypatch):
    video = fake_page("File:Test.webm", mime="video/webm")
    video["imageinfo"][0]["url"] = "https://upload.wikimedia.org/wikipedia/commons/a/ab/test.webm"
    def fake_get(_url, params, **_kwargs):
        class Resp:
            def raise_for_status(self):
                pass
            def json(self):
                return {"query": {"pages": [video]}}
        return Resp()
    monkeypatch.setattr(search.requests, "get", fake_get)
    found = search.search_for_stock_videos("mountains", it=5)
    assert found[0]["type"] == "video"
    assert len(found) == 1


def test_dangerous_download_url_rejected(tmp_path):
    with pytest.raises(ValueError):
        download_media({"url": "https://example.org/malicious.mp4", "type": "video"}, directory=tmp_path)


def test_video_download_no_api_key(monkeypatch, tmp_path):
    class Response:
        url = "https://upload.wikimedia.org/wiki/test.webm"
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def raise_for_status(self):
            pass
        def iter_content(self, chunk_size=4096):
            yield b"fake-video-content" * 100
    monkeypatch.setattr(requests, "get", lambda *_a, **_kw: Response())
    result = download_media({
        "url": "https://upload.wikimedia.org/wiki/test.webm",
        "type": "video",
    }, directory=tmp_path)
    assert Path(result).exists()
    assert Path(result).stat().st_size > 1000
