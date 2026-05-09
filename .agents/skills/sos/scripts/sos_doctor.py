from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Callable


PROJECT_NAME = "skill-orchestration-system"


def _looks_like_sos_pyproject(path: Path) -> bool:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    in_project_table = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project_table = stripped == "[project]"
            continue
        if not in_project_table or not stripped.startswith("name"):
            continue
        key, separator, value = stripped.partition("=")
        if separator and key.strip() == "name":
            return value.strip().strip('"').strip("'") == PROJECT_NAME
    return False


def find_repo_root(cwd: Path | str | None = None) -> Path | None:
    current = Path(cwd if cwd is not None else os.getcwd()).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        pyproject = candidate / "pyproject.toml"
        src_package = candidate / "src" / "sos"
        if (
            pyproject.is_file()
            and src_package.is_dir()
            and _looks_like_sos_pyproject(pyproject)
        ):
            return candidate
    return None


def detect(
    cwd: Path | str | None = None,
    cli_finder: Callable[[str], str | None] = shutil.which,
) -> dict[str, object]:
    resolved_cwd = Path(cwd if cwd is not None else os.getcwd()).resolve()
    repo_root = find_repo_root(resolved_cwd)
    installed_cli = cli_finder("sos")
    base: dict[str, object] = {
        "cwd": str(resolved_cwd),
        "repo_root": str(repo_root) if repo_root is not None else None,
        "installed_cli": installed_cli,
        "python": sys.executable,
        "platform": platform.platform(),
    }

    if repo_root is not None:
        return {
            **base,
            "mode": "repo-local",
            "message": "SOS source checkout detected; use repo-local Python invocation.",
            "command": [sys.executable, "-m", "sos", "--version"],
            "env_updates": {"PYTHONPATH": str(repo_root / "src")},
        }

    if installed_cli is not None:
        return {
            **base,
            "mode": "installed-cli",
            "message": "SOS executable found on PATH.",
            "command": ["sos", "--version"],
            "env_updates": {},
        }

    return {
        **base,
        "mode": "advisory",
        "message": "No SOS source checkout or installed CLI was detected.",
        "command": [],
        "env_updates": {},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    args = parser.parse_args(argv)
    print(json.dumps(detect(cwd=args.cwd), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
