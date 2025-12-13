import tempfile
import unittest
from pathlib import Path

from app.infrastructure.channels_loader import load_channels_from_yaml, sync_channels


def _write_yaml(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


class LoadChannelsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_missing_file_raises(self):
        missing = self.base / "missing.yaml"
        with self.assertRaisesRegex(RuntimeError, "channels file not found"):
            load_channels_from_yaml(str(missing))

    def test_invalid_structure_raises(self):
        path = self.base / "bad.yaml"
        _write_yaml(path, "[]")
        with self.assertRaisesRegex(RuntimeError, "Invalid channels.yaml format"):
            load_channels_from_yaml(str(path))

    def test_invalid_entry_missing_required_fields(self):
        path = self.base / "invalid.yaml"
        _write_yaml(
            path,
            """
channels:
  - title: ""
    url: https://t.me/foo
""",
        )
        with self.assertRaisesRegex(RuntimeError, "Invalid channel entry"):
            load_channels_from_yaml(str(path))

    def test_loads_and_normalizes_channels(self):
        path = self.base / "channels.yaml"
        _write_yaml(
            path,
            """
channels:
  - title: "  Alpha  "
    url: " https://t.me/alpha "
    description: "  desc  "
    image: "  img.png  "
""",
        )

        result = load_channels_from_yaml(str(path))

        self.assertEqual(
            result,
            [
                {
                    "title": "Alpha",
                    "url": "https://t.me/alpha",
                    "description": "desc",
                    "image": "img.png",
                }
            ],
        )


class FakeChannelsRepo:
    def __init__(self):
        self.calls: list[dict] = []
        self.deleted_with: set[str] | None = None

    async def add_or_update(self, *, tg_url: str, title: str, description: str, image_url: str):
        self.calls.append(
            {
                "tg_url": tg_url,
                "title": title,
                "description": description,
                "image_url": image_url,
            }
        )

    async def delete_not_in(self, allowed_urls: set[str]):
        self.deleted_with = set(allowed_urls)
        return 0


class SyncChannelsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    async def test_sync_invokes_repository_for_each_channel(self):
        path = self.base / "channels.yaml"
        _write_yaml(
            path,
            """
channels:
  - title: Alpha
    url: https://t.me/alpha
  - title: Beta
    url: https://t.me/beta
    description: beta desc
    image: beta.png
""",
        )
        repo = FakeChannelsRepo()

        await sync_channels(repo, str(path))

        self.assertEqual(
            repo.calls,
            [
                {
                    "tg_url": "https://t.me/alpha",
                    "title": "Alpha",
                    "description": "",
                    "image_url": "",
                },
                {
                    "tg_url": "https://t.me/beta",
                    "title": "Beta",
                    "description": "beta desc",
                    "image_url": "beta.png",
                },
            ],
        )
        self.assertEqual(
            repo.deleted_with,
            {"https://t.me/alpha", "https://t.me/beta"},
        )

    async def test_sync_skips_delete_when_flag_disabled(self):
        path = self.base / "channels.yaml"
        _write_yaml(
            path,
            """
channels:
  - title: Alpha
    url: https://t.me/alpha
""",
        )
        repo = FakeChannelsRepo()

        await sync_channels(repo, str(path), delete_missing=False)

        self.assertIsNone(repo.deleted_with)
