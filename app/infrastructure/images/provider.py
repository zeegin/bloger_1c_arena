from __future__ import annotations

import hashlib
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from ...application.helpers.image_provider import ImageProvider


class ImageDownloader:
    def __init__(
        self,
        *,
        allowed_hosts: set[str] | None = None,
        max_download_bytes: int = 2_000_000,
        request_timeout: int = 10,
        session_timeout: int = 15,
    ):
        self.allowed_hosts = {host.lower() for host in allowed_hosts} if allowed_hosts else None
        self.max_download_bytes = max_download_bytes
        self._request_timeout = request_timeout
        self._session_timeout = session_timeout
        self._session: aiohttp.ClientSession | None = None

    async def fetch(self, url: str) -> bytes | None:
        if not self._is_allowed_url(url):
            return None
        session = self._get_session()
        try:
            async with session.get(url, timeout=self._request_timeout) as resp:
                if resp.status != 200:
                    return None
                buffer = bytearray()
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    buffer.extend(chunk)
                    if len(buffer) > self.max_download_bytes:
                        return None
            return bytes(buffer)
        except Exception:
            return None

    def _is_allowed_url(self, url: str) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        if self.allowed_hosts and host not in self.allowed_hosts:
            return False
        return True

    def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._session_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None


class CachedImageProvider(ImageProvider):
    def __init__(
        self,
        *,
        downloader: ImageDownloader,
        cache_dir: Path | None = None,
        ttl_seconds: int = 7 * 24 * 60 * 60,
    ):
        self._downloader = downloader
        base_dir = cache_dir or Path(tempfile.gettempdir()) / "arena_image_cache"
        self._cache_dir = base_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_seconds

    async def fetch(self, url: str) -> bytes | None:
        if not url:
            return None
        path = self._cache_path(url)
        if path.exists():
            if self._is_fresh(path):
                try:
                    return path.read_bytes()
                except OSError:
                    pass
            else:
                try:
                    path.unlink()
                except OSError:
                    pass

        data = await self._downloader.fetch(url)
        if data:
            tmp_path = path.with_suffix(".tmp")
            try:
                tmp_path.write_bytes(data)
                tmp_path.replace(path)
            except OSError:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        return data

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.img"

    def _is_fresh(self, path: Path) -> bool:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return False
        return (time.time() - mtime) < self._ttl

    async def close(self) -> None:
        await self._downloader.close()
