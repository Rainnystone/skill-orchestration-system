from __future__ import annotations

import hashlib
from pathlib import Path


def fingerprint_dir(path: str | Path) -> str:
    root = Path(path)
    digest = hashlib.sha256()

    for file_path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative_path = file_path.relative_to(root).as_posix()
        encoded_path = relative_path.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(file_path.stat().st_size.to_bytes(8, "big"))
        with file_path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)

    return f"sha256:{digest.hexdigest()}"
