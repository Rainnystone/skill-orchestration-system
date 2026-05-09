from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Callable


PROJECT_NAME = "skill-orchestration-system"


def _read_project_name(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError:
        return None
    except tomllib.TOMLDecodeError:
        return None

    project = data.get("project")
    if not isinstance(project, dict):
        return None

    name = project.get("name")
    return name if isinstance(name, str) else None


def _looks_like_sos_pyproject(path: Path) -> bool:
    return _read_project_name(path) == PROJECT_NAME


def _build_pythonpath_update(repo_root: Path) -> str:
    repo_src = str((repo_root / "src").resolve())
    existing_pythonpath = os.environ.get("PYTHONPATH")
    if existing_pythonpath:
        return f"{repo_src}{os.pathsep}{existing_pythonpath}"
    return repo_src


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
            "env_updates": {"PYTHONPATH": _build_pythonpath_update(repo_root)},
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
    parser.add_argument("--no-path-lookup", action="store_true")
    args = parser.parse_args(argv)
    cli_finder = (lambda _: None) if args.no_path_lookup else shutil.which
    print(json.dumps(detect(cwd=args.cwd, cli_finder=cli_finder), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
