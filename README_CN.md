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
- 根据扫描结果提出功能性技能包候选。
- 在修改文件前生成可审查的计划文件。
- 只有显式传入 `--apply` 时才真正写入。
- 默认保留原始技能目录。
- 生成 `sos-<pack>` 形式的活动指针技能。
- 记录技能包 manifest、运行时 registry、备份、恢复目标和同步指纹。
- 支持 dry-run 状态检查、备份清理、恢复和技能包同步流程。

## 仓库目录结构

```text
.
|-- .github/workflows/     # CI 工作流
|-- references/            # 公开行为与安全参考文档
|-- src/sos/               # CLI 和库实现
|   |-- cli.py             # 命令行入口
|   |-- planner.py         # 可审查写入计划生成
|   |-- apply.py           # 计划执行和可回滚写入
|   |-- sync.py            # 技能包激活与干净同步
|   |-- backups.py         # 备份、恢复和保留策略
|   `-- templates/         # 打包进 Python 包的指针技能模板
|-- templates/             # 生成技能模板的源码副本
|-- tests/                 # 单元测试和 CLI 冒烟测试
|-- README.md              # 英文文档
|-- README_CN.md           # 中文文档
|-- pyproject.toml         # Python 包元数据
`-- LICENSE
```

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

预览技能包候选：

```bash
sos propose --root "$SKILLS_ROOT"
```

候选只是起点，不是最终决定。真正写入之前，应先检查生成的计划，并确认技能包边界符合
你的实际工作方式。

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

成功执行 apply 后，SOS 会把生成的活动技能写入你选择的技能根目录。生成入口见下一节。

查看运行时状态：

```bash
sos status --runtime-root "$RUNTIME_ROOT"
```

## 命令参考

| 命令 | 作用 | 默认是否写入 |
| --- | --- | --- |
| `sos scan --root <path> [--codex-config <path>]` | 列出目录下启用的技能。 | 否 |
| `sos propose --root <path>` | 根据扫描结果提出技能包候选。 | 否 |
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

## 生成的技能入口

SOS 不会把生成后的活动技能文件夹提交到这个仓库。只有当你对计划执行 `--apply` 时，
它们才会被写入你选择的活动技能根目录。

生成内容包括：

- `sos-haruhi`：用于技能包管理、状态查看、备份和恢复的 companion 入口。
- `sos-<pack>`：每个已启用技能包对应一个 pointer skill，由对应的 pack manifest
  生成。

生成的 pointer skill 会保持很短，只指向 pack manifest 和 vault 副本，不会把原始
`SKILL.md` 全文塞进活动入口。

## 技能包建议模型

SOS 把技能包建议当作可审查候选，而不是最终决定。一个技能包应该对应真实工作流边界；
任何写入命令执行前，都应先检查计划文件。

当前建议引擎保持保守。后续版本可以继续加入更多建议规则、自定义 manifest 或交互式
选择流程。

## 兼容性

SOS 当前是 Codex-first。已测试的写入路径可以在创建备份后更新 Codex skill 配置，并且
只有显式使用 `--apply` 时才会写入。

Claude Code 兼容性目前是结构层面的：生成技能是普通 `SKILL.md` 文件夹，技能包元数据
是普通 TOML manifest。SOS 还没有提供 Claude Code 专用安装器、settings 写入器或集成
测试。看起来属于 Claude 的路径会受到保护，避免被宽泛的源目录删除误伤。

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
