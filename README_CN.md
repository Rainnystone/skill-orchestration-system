# Skill Orchestration System

[English](README.md) | [中文](README_CN.md)

Skill Orchestration System，简称 SOS，是一个本地命令行工具，用来把大量 agent
skill 整理成可审查、可激活、可回滚的技能包。

它适合这种场景：你有很多技能文件夹，但日常只希望暴露少量按任务组织的入口。SOS
会扫描包含 `SKILL.md` 的技能目录，提出语义化分组，写出可审查的计划文件，把选中的
技能复制到受管理的 vault，生成指针技能，在 Codex 配置里禁用原始活动技能，并在真正
写入之前创建备份。

## 这个项目解决什么问题

- 扫描本地包含 `SKILL.md` 的技能目录。
- 自动提出 Apify、Obsidian、浏览器游戏工作流等内置技能包。
- 在修改文件前生成可审查的计划文件。
- 只有显式传入 `--apply` 时才真正写入。
- 默认保留原始技能目录。
- 生成 `sos-apify`、`sos-obsidian` 等活动指针技能。
- 记录技能包 manifest、运行时 registry、备份、恢复目标和同步指纹。
- 支持 dry-run 状态检查、备份清理、恢复和技能包同步流程。

## 安全模型

SOS 默认非常保守：

- `scan`、`propose`、`plan` 不会修改活动技能目录。
- 不带 `--apply` 的 `apply` 只是 dry run。
- `apply --apply` 会先创建备份，再写入文件。
- 默认不会删除源技能目录。源目录删除必须同时提供
  `--delete-source`、`--apply` 和 `--confirm-delete-source <pack-id>`。
- 插件缓存路径会被保护，不允许作为源目录删除目标。
- 恢复和备份清理命令默认也是 dry run，只有传入 `--apply` 才会写入。

运行任何会写入文件的命令前，都应该先检查生成的计划文件。

## 安装

SOS 需要 Python 3.11 或更新版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m sos --version
```

上面的安装命令会同时安装 SOS 和它的运行依赖，包括 `tomli-w`。只要按这种方式安装，就
不需要再手动单独安装 `tomli-w`。

安装后也可以直接使用命令：

```bash
sos --version
```

## 快速开始

下面使用的是占位路径。请替换成你自己的技能目录、SOS 运行时目录和 Codex 配置路径。

```bash
export SKILLS_ROOT="$HOME/.codex/skills"
export RUNTIME_ROOT="$HOME/.sos"
export CODEX_CONFIG="$HOME/.codex/config.toml"
```

扫描活动技能：

```bash
sos scan --root "$SKILLS_ROOT" --codex-config "$CODEX_CONFIG"
```

预览内置技能包建议：

```bash
sos propose --root "$SKILLS_ROOT"
```

创建可审查的计划：

```bash
sos plan \
  --root "$SKILLS_ROOT" \
  --runtime-root "$RUNTIME_ROOT" \
  --codex-config "$CODEX_CONFIG" \
  --out "$RUNTIME_ROOT/plan.toml"
```

先 dry-run 检查计划：

```bash
sos apply --plan "$RUNTIME_ROOT/plan.toml"
```

确认无误后再真正执行：

```bash
sos apply --plan "$RUNTIME_ROOT/plan.toml" --apply
```

查看运行时状态：

```bash
sos status --runtime-root "$RUNTIME_ROOT"
```

## 命令参考

| 命令 | 作用 | 默认是否写入 |
| --- | --- | --- |
| `sos scan --root <path> [--codex-config <path>]` | 列出目录下启用的技能。 | 否 |
| `sos propose --root <path>` | 根据扫描结果提出内置技能包。 | 否 |
| `sos plan --root <path> --runtime-root <path> --codex-config <path> --out <path>` | 写出可审查的计划文件。 | 只写计划文件 |
| `sos apply --plan <path>` | 汇总计划内容。 | 否 |
| `sos apply --plan <path> --apply` | 复制技能、写 manifest 和指针、禁用原始技能并创建备份。 | 是 |
| `sos pack activate <pack> --runtime-root <path>` | 激活技能包，并在状态干净时执行同步。 | 可能 |
| `sos pack sync <pack> --runtime-root <path>` | 展示技能包同步计划。 | 否 |
| `sos pack sync <pack> --runtime-root <path> --apply` | 执行有效的技能包同步计划。 | 是 |
| `sos status --runtime-root <path>` | 查看 registry 和备份状态。 | 否 |
| `sos backup list --runtime-root <path>` | 列出备份。 | 否 |
| `sos backup clean --runtime-root <path> --keep <count>` | 预览备份清理。 | 否 |
| `sos backup clean --runtime-root <path> --keep <count> --apply` | 清理旧备份。 | 是 |
| `sos restore <backup-id> --runtime-root <path>` | 预览恢复目标。 | 否 |
| `sos restore <backup-id> --runtime-root <path> --apply` | 恢复记录中的配置和 vault 目标。 | 是 |

## 运行时目录结构

SOS 的运行时目录是它管理技能包状态的地方。典型结构如下：

```text
<runtime-root>/
  backups/
  packs/
  state/
  vault/
```

- `vault/` 保存复制后的技能包内容。
- `packs/` 保存 TOML 格式的技能包 manifest。
- `state/` 保存 registry 状态。
- `backups/` 保存写入前创建的配置和 vault 快照。

## 内置技能包建议

SOS 当前识别这些内置家族：

- `apify`：名称以 `apify-` 开头的技能。
- `obsidian`：名称以 `obsidian-` 开头的技能，以及 `json-canvas`。
- `game-design`：Game Studio 和浏览器游戏相关工作流技能。

当某个家族过大时，SOS 会把它拆成稳定的语义子包。

## 源目录删除

正常激活不会删除源技能目录。如果你明确希望在技能复制到 SOS vault 后删除源目录，可以使用：

```bash
sos apply \
  --plan "$RUNTIME_ROOT/plan.toml" \
  --apply \
  --delete-source \
  --confirm-delete-source <pack-id>
```

这个命令只适合在你已经检查计划文件，并确认备份存在之后使用。

## 开发

安装开发依赖：

```bash
python -m pip install -e ".[dev]"
```

运行测试：

```bash
python -m pytest
```

运行 CLI 冒烟检查：

```bash
python -m sos --version
```

## 项目状态

SOS 目前是早期本地 CLI。已实现行为有测试覆盖，但公共接口和内置技能包建议规则在稳定
版本前仍可能调整。

## 参与贡献

欢迎提交 issue 和 pull request。建议保持改动小而清晰，补充测试，并遵循“先 dry run，
再显式写入”的安全模型。

## 安全与隐私

不要提交真实本地配置、私人技能库、备份或运行时 vault 内容。分享问题时，请把本地路径、
用户名、访问令牌和私人工作区名称替换成占位符。

## 许可证

MIT License。见 [LICENSE](LICENSE)。
