import requests

from anna_integration import download_book, get_download_urls, search_books


class FakeResponse:
    def __init__(self, text="", json_data=None, status_code=200, headers=None, chunks=None):
        self.text = text
        self._json_data = json_data if json_data is not None else {}
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks or []

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data

    def iter_content(self, chunk_size=8192):
        for chunk in self._chunks:
            yield chunk


def test_search_books_falls_back_to_next_known_good_base_url(monkeypatch):
    monkeypatch.setenv("ANNA_ARCHIVE_BASE_URLS", "https://mirror-a.example,https://mirror-b.example")
    calls = []

    md5 = "0123456789abcdef0123456789abcdef"
    html = f"""
    <html><body>
      <div>
        <a href="/md5/{md5}">Known Good Book</a>
        2020 .epub 1 MB English
      </div>
    </body></html>
    """

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        calls.append(url)
        if url.startswith("https://mirror-a.example"):
            raise requests.RequestException("mirror down")
        return FakeResponse(text=html)

    monkeypatch.setattr(requests, "get", fake_get)

    results = search_books("known-good-query", limit=5)

    assert calls[0] == "https://mirror-a.example/search"
    assert calls[1] == "https://mirror-b.example/search"
    assert len(results) == 1
    assert results[0]["id"] == md5
    assert results[0]["title"] == "Known Good Book"


def test_get_download_urls_collects_multiple_links(monkeypatch):
    monkeypatch.setenv("FAST_DOWNLOAD_KEY", "key")
    monkeypatch.setenv("ANNA_ARCHIVE_BASE_URLS", "https://mirror-a.example,https://mirror-b.example")

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        if url.startswith("https://mirror-a.example"):
            raise requests.RequestException("api unavailable")
        payload = {
            "download_url": "https://download-1.example/file.epub",
            "download_urls": [
                "https://download-2.example/file.epub",
                "https://download-1.example/file.epub",
            ],
            "links": [{"mirror": "https://download-3.example/file.epub"}],
            "status": "ok",
        }
        return FakeResponse(json_data=payload)

    monkeypatch.setattr(requests, "get", fake_get)

    links = get_download_urls("0123456789abcdef0123456789abcdef")

    assert links == [
        "https://download-1.example/file.epub",
        "https://download-2.example/file.epub",
        "https://download-3.example/file.epub",
    ]


def test_download_book_tries_next_link_after_failure(monkeypatch, tmp_path):
    md5 = "0123456789abcdef0123456789abcdef"
    links = ["https://bad-link.example/file.epub", "https://good-link.example/file.epub"]

    monkeypatch.setattr("anna_integration.get_download_urls", lambda _: links)
    call_urls = []

    def fake_get(url, headers=None, stream=None, timeout=None, **kwargs):
        call_urls.append(url)
        if "bad-link" in url:
            return FakeResponse(status_code=503)
        return FakeResponse(
            status_code=200,
            headers={
                "Content-Disposition": 'attachment; filename="good.epub"',
                "Content-Type": "application/epub+zip",
            },
            chunks=[b"hello", b"world"],
        )

    monkeypatch.setattr(requests, "get", fake_get)

    downloaded_path = download_book(md5, tmp_path, title="Ignored")

    assert call_urls == links
    assert downloaded_path is not None
    assert downloaded_path.name == "good.epub"
    assert downloaded_path.read_bytes() == b"helloworld"
