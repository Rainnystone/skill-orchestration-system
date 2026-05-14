from __future__ import annotations

import pytest

from sos.host_paths import (
    validate_host,
    workspace_skill_parent_for_host,
    workspace_skill_root_for_host,
)


class TestValidateHost:
    def test_accepts_codex(self) -> None:
        assert validate_host("codex") == "codex"

    def test_accepts_claude(self) -> None:
        assert validate_host("claude") == "claude"

    def test_rejects_unknown_host(self) -> None:
        with pytest.raises(ValueError, match="unsupported host"):
            validate_host("unknown")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="unsupported host"):
            validate_host("")


class TestWorkspaceSkillParentForHost:
    def test_returns_agents_for_codex(self, tmp_path: object) -> None:
        from pathlib import Path

        root = Path(str(tmp_path))
        result = workspace_skill_parent_for_host(root, "codex")
        assert result == root / ".agents"

    def test_returns_claude_for_claude(self, tmp_path: object) -> None:
        from pathlib import Path

        root = Path(str(tmp_path))
        result = workspace_skill_parent_for_host(root, "claude")
        assert result == root / ".claude"


class TestWorkspaceSkillRootForHost:
    def test_returns_agents_skills_for_codex(self, tmp_path: object) -> None:
        from pathlib import Path

        root = Path(str(tmp_path))
        result = workspace_skill_root_for_host(root, "codex")
        assert result == root / ".agents" / "skills"

    def test_returns_claude_skills_for_claude(self, tmp_path: object) -> None:
        from pathlib import Path

        root = Path(str(tmp_path))
        result = workspace_skill_root_for_host(root, "claude")
        assert result == root / ".claude" / "skills"
