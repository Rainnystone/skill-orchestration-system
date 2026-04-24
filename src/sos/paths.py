from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def expand_path(path: str | Path) -> Path:
    return Path(path).expanduser()


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    vault: Path
    packs: Path
    backups: Path
    state: Path

    @classmethod
    def default(cls) -> "RuntimePaths":
        return cls.from_root(Path.home() / ".sos")

    @classmethod
    def from_root(cls, root: str | Path) -> "RuntimePaths":
        expanded_root = expand_path(root)
        return cls(
            root=expanded_root,
            vault=expanded_root / "vault",
            packs=expanded_root / "packs",
            backups=expanded_root / "backups",
            state=expanded_root / "state",
        )
