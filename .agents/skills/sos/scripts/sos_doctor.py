from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Callable


PROJECT_NAME = "skill-orchestration-system"
VersionRunner = Callable[[list[str], dict[str, str]], tuple[bool, str]]


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


def _run_version_command(command: list[str], env_updates: dict[str, str]) -> tuple[bool, str]:
    env = os.environ.copy()
    env.update(env_updates)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)

    output = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part.strip()
    )
    if completed.returncode != 0:
        return False, output
    if not completed.stdout.strip().startswith("sos "):
        return False, output or "Version command did not identify SOS."
    return True, completed.stdout.strip()


def _probe_claude_skill_root(cwd: Path) -> str | None:
    candidates = []
    home_env = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if home_env:
        candidates.append(Path(home_env) / ".claude" / "skills")
    candidates.append(cwd / ".claude" / "skills")
    for candidate in candidates:
        if candidate.is_dir():
            return str(candidate.resolve())
    return None


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
    version_runner: VersionRunner = _run_version_command,
    *,
    claude_lookup: bool = True,
) -> dict[str, object]:
    resolved_cwd = Path(cwd if cwd is not None else os.getcwd()).resolve()
    repo_root = find_repo_root(resolved_cwd)
    installed_cli = cli_finder("sos")
    claude_root = _probe_claude_skill_root(resolved_cwd) if claude_lookup else None
    base: dict[str, object] = {
        "cwd": str(resolved_cwd),
        "repo_root": str(repo_root) if repo_root is not None else None,
        "installed_cli": installed_cli,
        "python": sys.executable,
        "platform": platform.platform(),
        "claude_skill_root": claude_root,
    }

    if repo_root is not None:
        repo_command = [sys.executable, "-m", "sos", "--version"]
        repo_env_updates = {"PYTHONPATH": _build_pythonpath_update(repo_root)}
        repo_ok, repo_diagnostic = version_runner(repo_command, repo_env_updates)
        if repo_ok:
            return {
                **base,
                "mode": "repo-local",
                "message": "SOS source checkout detected; use repo-local Python invocation.",
                "command": repo_command,
                "env_updates": repo_env_updates,
            }
    else:
        repo_diagnostic = ""

    if installed_cli is not None:
        installed_ok, installed_diagnostic = version_runner(
            [installed_cli, "--version"],
            {},
        )
        if not installed_ok:
            message = "An executable named sos was found on PATH, but it is not a verified SOS executable."
            if repo_root is not None:
                message = (
                    "SOS source checkout detected, but repo-local invocation failed; "
                    "the PATH sos executable is also not a verified SOS executable."
                )
            return {
                **base,
                "mode": "advisory",
                "message": message,
                "command": [],
                "env_updates": {},
                "diagnostic": installed_diagnostic or repo_diagnostic,
            }
        return {
            **base,
            "mode": "installed-cli",
            "message": "Verified SOS executable found on PATH.",
            "command": ["sos", "--version"],
            "env_updates": {},
        }

    if repo_root is not None:
        return {
            **base,
            "mode": "advisory",
            "message": (
                "SOS source checkout detected, but repo-local invocation failed. "
                "Install project dependencies or use a Python environment where SOS dependencies are available."
            ),
            "command": [],
            "env_updates": {},
            "diagnostic": repo_diagnostic,
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
    parser.add_argument("--no-claude-lookup", action="store_true")
    args = parser.parse_args(argv)
    cli_finder = (lambda _: None) if args.no_path_lookup else shutil.which
    print(json.dumps(
        detect(
            cwd=args.cwd,
            cli_finder=cli_finder,
            claude_lookup=not args.no_claude_lookup,
        ),
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
