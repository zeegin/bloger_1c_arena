import unittest
from io import BytesIO
from types import MethodType

from PIL import Image
from typing import Optional

from app.application.helpers.image_preview import CombinedImageService
from app.domain.shared.models import Channel


def make_channel(idx: int, title: str) -> Channel:
    return Channel(
        id=idx,
        title=title,
        tg_url=f"https://t.me/{title.lower()}",
        description="",
        image_url="",
        rating=1500.0,
        games=10,
        wins=5,
        losses=5,
    )


class DummyProvider:
    async def fetch(self, url: str) -> Optional[bytes]:  # pragma: no cover - trivial stub
        return None

    async def close(self) -> None:  # pragma: no cover - trivial stub
        return None


class CombinedImageServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.channel_a = make_channel(1, "Alpha")
        self.channel_b = make_channel(2, "Beta")
        self.provider = DummyProvider()

    async def test_build_preview_caches_rendered_bytes(self):
        service = CombinedImageService(cache_ttl=3600, image_provider=self.provider)
        self.addAsyncCleanup(service.close)
        compose_calls = 0

        async def fake_compose(self, a, b):
            nonlocal compose_calls
            compose_calls += 1
            return BytesIO(b"rendered-image")

        service._compose_image = MethodType(fake_compose, service)

        first = await service.build_preview(self.channel_a, self.channel_b)
        second = await service.build_preview(self.channel_a, self.channel_b)

        self.assertEqual(compose_calls, 1)
        self.assertIsNot(first, second)
        self.assertEqual(first.getvalue(), second.getvalue())

    async def test_compose_image_uses_placeholders_on_failed_downloads(self):
        service = CombinedImageService(height=100, image_provider=self.provider)
        self.addAsyncCleanup(service.close)

        async def always_none(self, url):
            return None

        service._load_channel_image = MethodType(always_none, service)
        service._pick_vs_image = lambda: None

        buffer = await service._compose_image(self.channel_a, self.channel_b)
        combined = Image.open(buffer)

        self.assertEqual(combined.size, (100 + 100 + 12, 100))
        left_px = combined.getpixel((0, 0))
        right_px = combined.getpixel((combined.width - 1, 0))
        for component in (*left_px, *right_px):
            self.assertGreaterEqual(component, 230)

    async def test_compose_image_merges_resized_images_and_vs_banner(self):
        service = CombinedImageService(height=100, image_provider=self.provider)
        self.addAsyncCleanup(service.close)

        red = Image.new("RGB", (50, 50), color=(255, 0, 0))
        blue = Image.new("RGB", (35, 200), color=(0, 0, 255))
        downloads = [red, blue]

        async def fake_load(self, url):
            return downloads.pop(0)

        service._load_channel_image = MethodType(fake_load, service)
        vs_banner = Image.new("RGBA", (30, 100), color=(0, 255, 0, 255))
        service._pick_vs_image = lambda: vs_banner

        resized_red_width = service._resize_to_height(red).width
        resized_blue_width = service._resize_to_height(blue).width

        buffer = await service._compose_image(self.channel_a, self.channel_b)
        combined = Image.open(buffer)

        expected_width = resized_red_width + resized_blue_width + 12 + (vs_banner.width + 12)
        self.assertEqual(combined.size, (expected_width, 100))

        mid_y = service.height // 2
        red_px = combined.getpixel((50, mid_y))
        self.assertGreater(red_px[0], 200)

        vs_start = 100 + 12
        vs_px = combined.getpixel((vs_start + vs_banner.width // 2, mid_y))
        self.assertGreater(vs_px[1], 200)

        blue_start = vs_start + vs_banner.width + 12
        blue_px = combined.getpixel((blue_start + 5, mid_y))
        self.assertGreater(blue_px[2], 200)
