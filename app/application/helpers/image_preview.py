from __future__ import annotations

import random
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

from ...domain import Channel
from .image_provider import ImageProvider
from ...infrastructure.metrics import metrics


class CombinedImageService:
    def __init__(
        self,
        *,
        image_provider: ImageProvider,
        vs_images_dir: Path | None = None,
        height: int = 512,
    ):
        self.height = height
        self.vs_images = list(vs_images_dir.glob("*.png")) if vs_images_dir else []
        self._image_provider = image_provider

    async def build_preview(self, a: Channel, b: Channel) -> tuple[BytesIO, Optional[str]]:
        img_a, hit_a = await self._load_channel_image((a.image_url or "").strip())
        img_b, hit_b = await self._load_channel_image((b.image_url or "").strip())

        if not img_a:
            img_a = self._placeholder_image()
        if not img_b:
            img_b = self._placeholder_image()

        img_a = self._resize_to_height(img_a)
        img_b = self._resize_to_height(img_b)

        def compose():
            return self._compose_loaded(img_a, img_b)

        photo = await self._render_with_metrics("media:preview_compose", compose, is_async=False)
        if hit_a == "hit" and hit_b == "hit":
            overall_hit = "hit"
        elif hit_a == "hit" or hit_b == "hit":
            overall_hit = "halfhit"
        else:
            overall_hit = "miss"
        return photo, overall_hit

    def _compose_loaded(self, img_a: Image.Image, img_b: Image.Image) -> BytesIO:
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

    async def _load_channel_image(self, url: str) -> Tuple[Optional[Image.Image], Optional[str]]:
        if not url:
            return None, None
        data = await self._render_with_metrics(
            "media:channel_fetch",
            lambda: self._image_provider.fetch(url),
            is_async=True,
        )
        if not data:
            return None, None
        try:
            img = Image.open(BytesIO(data))
            return img.convert("RGB"), getattr(data, "cache_state", None)
        except Exception:
            return None, None

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

    async def _render_with_metrics(self, action: str, operation, *, is_async: bool = True):
        if is_async:
            async with metrics.span_async(action, source="media"):
                return await operation()
        else:
            with metrics.span(action, source="media"):
                return operation()
