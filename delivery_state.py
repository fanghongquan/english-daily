"""Durable state for retry-safe Feishu delivery."""
import datetime
import json
import os
import tempfile
from pathlib import Path


def _path(state_dir: Path, date: str) -> Path:
    return Path(state_dir) / f"{date}.json"


def is_pushed(state_dir: Path, date: str) -> bool:
    try:
        data = json.loads(_path(state_dir, date).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return data.get("feishu_pushed") is True


def mark_pushed(state_dir: Path, date: str, article_date: str, url: str) -> Path:
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    target = _path(state_dir, date)
    payload = {
        "feishu_pushed": True,
        "article_date": article_date,
        "url": url,
        "pushed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    fd, temporary = tempfile.mkstemp(prefix=f".{date}.", suffix=".tmp", dir=state_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target
