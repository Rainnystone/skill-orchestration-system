from __future__ import annotations

from pathlib import Path

SUPPORTED_HOSTS = ("codex", "claude")


def validate_host(host: str) -> str:
    if host not in SUPPORTED_HOSTS:
        raise ValueError(f"unsupported host: {host}")
    return host


def workspace_skill_parent_for_host(workspace_root: str | Path, host: str) -> Path:
    safe_host = validate_host(host)
    root = Path(workspace_root)
    if safe_host == "codex":
        return root / ".agents"
    return root / ".claude"


def workspace_skill_root_for_host(workspace_root: str | Path, host: str) -> Path:
    return workspace_skill_parent_for_host(workspace_root, host) / "skills"
