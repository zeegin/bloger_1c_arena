import yaml
from pathlib import Path
from ..domain.rating.repositories import ChannelsRepository


def load_channels_from_yaml(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"channels file not found: {path}")

    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "channels" not in data:
        raise RuntimeError("Invalid channels.yaml format")

    channels = data["channels"]
    if not isinstance(channels, list):
        raise RuntimeError("channels must be a list")

    normalized = []
    for ch in channels:
        title = ch.get("title")
        url = ch.get("url")
        description = ch.get("description") or ""
        image = ch.get("image") or ""

        if not title or not url:
            raise RuntimeError(f"Invalid channel entry: {ch}")

        normalized.append({
            "title": title.strip(),
            "url": url.strip(),
            "description": description.strip(),
            "image": image.strip(),
        })

    return normalized

async def sync_channels(repo: ChannelsRepository, yaml_path: str, *, delete_missing: bool = True) -> None:
    channels = load_channels_from_yaml(yaml_path)
    synced_urls: set[str] = set()
    for ch in channels:
        synced_urls.add(ch["url"])
        await repo.add_or_update(
            tg_url=ch["url"],
            title=ch["title"],
            description=ch.get("description", ""),
            image_url=ch.get("image", ""),
        )
    if delete_missing:
        await repo.delete_not_in(synced_urls)
