from pathlib import Path

import sos.pointer as pointer


def _frontmatter(path: Path) -> dict[str, str | bool]:
    frontmatter = path.read_text(encoding="utf-8").split("---", 2)[1]
    values: dict[str, str | bool] = {}
    for line in frontmatter.splitlines():
        if not line.strip():
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip()
        if value == "true":
            values[key] = True
        elif value == "false":
            values[key] = False
        elif value.startswith('"') and value.endswith('"'):
            values[key] = value[1:-1]
        else:
            values[key] = value
    return values


def test_render_nagato_skill_mentions_context_reference_and_hooks(tmp_path: Path):
    renderer = getattr(pointer, "render_nagato_skill", None)
    assert callable(renderer)

    target = tmp_path / "active"
    runtime_root = tmp_path / ".sos"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    learned_reference = runtime_root / "state" / "recommendations" / "asahina-reference.md"

    renderer(target, runtime_root=runtime_root, workspace_root=workspace_root)

    skill_path = target / "sos-nagato" / "SKILL.md"
    rendered = skill_path.read_text(encoding="utf-8")
    frontmatter = _frontmatter(skill_path)
    assert frontmatter["name"] == "sos-nagato"
    assert frontmatter["description"].startswith("Use ")
    assert "sos recommend context" in frontmatter["description"]
    assert "disable-model-invocation" not in frontmatter
    assert "sos recommend context" in rendered
    assert str(learned_reference) in rendered
    assert "Read the learned reference path" in rendered
    assert "workspace-only" in rendered
    assert "Keep context small" in rendered
    assert "Do not use hooks" in rendered
    assert len(rendered.splitlines()) < 90


def test_render_asahina_skill_mentions_learn_trigger_and_hook_boundary(tmp_path: Path):
    renderer = getattr(pointer, "render_asahina_skill", None)
    assert callable(renderer)

    target = tmp_path / "active" / "sos-asahina"
    runtime_root = tmp_path / ".sos"

    renderer(target, runtime_root=runtime_root)

    skill_path = target / "SKILL.md"
    rendered = skill_path.read_text(encoding="utf-8")
    frontmatter = _frontmatter(skill_path)
    assert frontmatter["name"] == "sos-asahina"
    assert frontmatter["description"].startswith("Use ")
    assert "sos recommend learn" in frontmatter["description"]
    assert frontmatter["disable-model-invocation"] is True
    assert "sos recommend learn" in rendered
    assert "explicitly" in rendered
    assert "Do not run from hooks" in rendered
    assert len(rendered.splitlines()) < 80
