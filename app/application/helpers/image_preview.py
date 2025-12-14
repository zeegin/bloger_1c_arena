from __future__ import annotations

import random
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image

from ...domain import Channel
from .image_provider import ImageProvider


class CombinedImageService:
    def __init__(
        self,
        *,
        image_provider: ImageProvider,
        vs_images_dir: Path | None = None,
        cache_ttl: int = 60 * 60,
        height: int = 512,
    ):
        self.height = height
        self.cache_ttl = cache_ttl
        self.cache: dict[str, tuple[float, BytesIO]] = {}
        self.vs_images = list(vs_images_dir.glob("*.png")) if vs_images_dir else []
        self._image_provider = image_provider

    async def build_preview(self, a: Channel, b: Channel) -> BytesIO:
        cache_key = f"{a.id}-{b.id}"
        now = time.time()
        cached = self.cache.get(cache_key)
        if cached and now - cached[0] < self.cache_ttl:
            return BytesIO(cached[1].getvalue())

        photo = await self._compose_image(a, b)
        self.cache[cache_key] = (now, BytesIO(photo.getvalue()))
        return photo

    async def _compose_image(self, a: Channel, b: Channel) -> BytesIO:
        img_a = await self._load_channel_image((a.image_url or "").strip())
        img_b = await self._load_channel_image((b.image_url or "").strip())

        if not img_a:
            img_a = self._placeholder_image()
        if not img_b:
            img_b = self._placeholder_image()

        img_a = self._resize_to_height(img_a)
        img_b = self._resize_to_height(img_b)
        vs_image = self._pick_vs_image()
        gap = 12
        vs_width = vs_image.width + gap if vs_image else 0
        total_width = img_a.width + img_b.width + gap + vs_width
        combined = Image.new("RGB", (total_width, self.height), color=(20, 20, 20))
        combined.paste(img_a, (0, 0))
        offset = img_a.width + gap
        if vs_image:
            combined.paste(vs_image, (offset, 0), vs_image)
            offset += vs_image.width + gap
        combined.paste(img_b, (offset, 0))

        buffer = BytesIO()
        combined.save(buffer, format="JPEG", quality=85)
        buffer.seek(0)
        return buffer

    async def close(self) -> None:
        await self._image_provider.close()

    async def _load_channel_image(self, url: str) -> Optional[Image.Image]:
        if not url:
            return None
        data = await self._image_provider.fetch(url)
        if not data:
            return None
        try:
            img = Image.open(BytesIO(data))
            return img.convert("RGB")
        except Exception:
            return None

    def _placeholder_image(self) -> Image.Image:
        return Image.new("RGB", (self.height, self.height), color=(240, 240, 240))

    def _resize_to_height(self, img: Image.Image) -> Image.Image:
        width, current_height = img.size
        if current_height == self.height:
            return img
        ratio = self.height / float(current_height)
        new_width = max(1, int(width * ratio))
        return img.resize((new_width, self.height), Image.LANCZOS)

    def _pick_vs_image(self) -> Image.Image | None:
        if not self.vs_images:
            return None
        vs_path = random.choice(self.vs_images)
        try:
            vs_image = Image.open(vs_path).convert("RGBA")
            return self._resize_to_height(vs_image)
        except Exception:
            return None
