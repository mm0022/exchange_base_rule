import difflib
import json
from pathlib import Path


def load_snapshot(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_snapshot(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def unified_diff(old: str, new: str, label: str) -> str:
    if old == new:
        return ""
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"{label} (基线)",
        tofile=f"{label} (本次)",
        n=2,
    )
    return "".join(diff)
