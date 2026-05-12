# Skill Orchestration System

[English](README.md) | [中文](README_CN.md)

你的 agent skills 应该像一套顺手的工具箱，而不是第二个杂物抽屉。

Skill Orchestration System，简称 SOS，是一个面向 Codex 用户的本地 skill
整理系统。它把越来越多的本地 agent skills 整理成更小、更清楚、可审查、可激活、可回滚的技能包。它会先写计划，再写文件；先做 dry run，再真正 apply；先备份，再修改。

SOS 同时支持 Codex 和 Claude Code 两种宿主。通过每条写入命令的 `--host {codex,claude}` 参数选择宿主。

## 为什么需要 SOS

Agent skills 好用，是因为它们很容易添加。问题也在这里。

过一段时间后，你的 skills 目录可能会长成一堆混合物：旧实验、一次性工作流、插件缓存副本、个人 helper、生成出来的 pointer，还有几个真正重要的 skills 混在中间。一次暴露太多入口，agent 反而更难稳定使用。手动搬文件也不是不行，直到你漏掉了配置、备份或回滚路径。

SOS 做的事情很朴素：

- 扫描本地包含 `SKILL.md` 的技能目录；
- 提出按任务组织的技能包候选；
- 在真正写入前生成可审查的计划；
- 把选中的 skills 复制到受管理的 vault；
- 生成短入口，比如 `sos-<pack>`；
- 记录 manifest、registry、fingerprint 和备份；
- 在需要时恢复或检查状态。

目标不是让 skills 变得更花哨，而是让它们重新变得好用。

## 一句话版本

SOS 有两层：

- `.agents/skills/sos/` 里的 **Codex skill wrapper**，负责引导 agent 进行 no-global-install 的工作流；
- `src/sos/` 里的 **Python CLI backend**，负责确定性的扫描、规划、写入、同步、备份和恢复。

skill 负责告诉 agent 下一步该看什么、做什么。CLI 负责真正的文件操作。这个边界很重要：prompt 可以引导，但写文件这件事应该交给确定性代码。

## 不全局安装也能开始

推荐第一步是直接使用仓库自带的 `sos` skill。你可以 clone 这个仓库，在 Codex 中打开它，然后让 Codex 使用 SOS skill 来检查或整理你的本地 skills。

```bash
git clone https://github.com/Rainnystone/skill-orchestration-system.git
cd skill-orchestration-system
```

然后可以对 Codex 说：

```text
Use the sos skill to inspect my local skills and suggest a safe plan.
```

SOS skill 会先检查当前环境能不能运行 SOS。你也可以直接运行 doctor：

```bash
python .agents/skills/sos/scripts/sos_doctor.py --no-path-lookup
```

如果当前目录就是 SOS 源码 checkout，SOS 可以用 repo-local 模式运行，不需要先安装一个全局 `sos` 命令。

**macOS / Linux：**

```bash
PYTHONPATH=src python -m sos --version
```

**Windows PowerShell：**

```powershell
$env:PYTHONPATH = "src"
python -m sos --version
```

预期输出：

```text
sos 0.1.0
```

## 开发安装

如果你想以普通 Python 项目的方式开发 SOS，需要 Python 3.11 或更新版本。

**macOS / Linux：**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m sos --version
```

**Windows PowerShell：**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m sos --version
```

安装后也可以直接使用：

```bash
sos --version
```

## 实际怎么用 SOS

SOS 有两种用法。

### Codex skill 路线

这是推荐的第一次使用方式。把这个仓库放在 Codex 能看到的 workspace 里，然后直接让 Codex 使用仓库自带的 `sos` skill。你不需要先记住一整串 CLI 命令。

可以这样说：

```text
Use the sos skill to inspect my local Codex skills and explain what it finds.
Use the sos skill to propose skill packs, but do not write anything yet.
Use the sos skill to create a dry-run plan for organizing my skills.
Use the sos skill to apply the reviewed plan.
Use the sos skill to show what is inside my current packs.
Use the sos skill to check what changed after I installed new skills.
```

skill 被触发后，Codex 会读取 `.agents/skills/sos/SKILL.md`，运行或检查 `sos_doctor.py`，判断当前应该用 repo-local 模式还是 installed-CLI 模式；缺路径时会先问你，然后再调用默认 dry-run-first 的 SOS 命令。

### CLI 路线

CLI 是 skill 在需要确定性文件操作时调用的后端。如果你已经安装了 SOS，命令形状是：

```bash
sos scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
```

如果你不想全局安装，就从源码 checkout 里用同一套后端：

**macOS / Linux：**

```bash
PYTHONPATH=src python -m sos scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
```

**Windows PowerShell：**

```powershell
$env:PYTHONPATH = "src"
python -m sos scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
```

所以，原来的 `sos ...` 这条线还在。`python -m sos ...` 只是 no-global-install 场景下从仓库源码运行同一个后端的方式。

### Apply 计划之后

当你确认并 apply 一个计划后，SOS 会把 active pointer skills 写入你选择的 skills root：

- `sos-haruhi`：管理 SOS 状态、备份、恢复和 pack 操作；
- `sos-<pack>`：指向某个生成出来的技能包，比如 pack id 是 `writing` 时会有 `sos-writing`。

之后你就像使用普通 Codex skills 一样使用它们：

```text
Use sos-haruhi to show my SOS status.
Use sos-writing for this documentation task.
```

pack pointer 会先运行 `sos pack activate PACK_ID --runtime-root RUNTIME_ROOT --sync=clean-auto`，再读取受管理 vault 里的 skill 副本。这就是 SOS 保持 active 层很轻，同时把完整 skill 内容留在 vault 里的方式。

### 看清一个 pack 里有什么

pack 存在以后，你不需要猜 agent 会看到什么。可以问 `sos` skill，也可以直接运行只读命令：

```bash
sos pack list --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT --skill SKILL_NAME
```

`pack list` 回答“我现在有哪些 packs？”`pack show` 回答“这个 pack 里有哪些 skills？”如果你指定了 skill name，SOS 会按 manifest 里的 `skills.name` 做精确过滤，这样 agent 可以读取一个明确的 vault skill，而不是一上来浏览整个 pack。

### 安装或编辑新 skills 之后

当你的本地 skill 库发生变化时，先用 `changes` 看状态，再决定要不要重新建计划：

```bash
sos changes --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG
```

这也是只读命令。它会报告新增的 unmanaged skills、缺失或变更的 managed sources、vault drift、缺失或过期的 generated pointers，以及意外重新启用的 managed source skills。它不会自动修复，只告诉你哪些地方值得重新 scan、propose 或生成可审查计划。

## 一个安全的起步流程

下面的命令使用大写占位符。请替换成你自己的真实路径：

- `SKILLS_ROOT`：当前 active Codex skills 目录；
- `RUNTIME_ROOT`：你希望 SOS 使用的 runtime 目录；
- `CODEX_CONFIG`：你的 Codex config 路径；
- `PLAN_PATH`：你希望 SOS 写入的计划文件路径。

先检查，不写入：

```bash
sos scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
sos propose --root SKILLS_ROOT
```

生成可审查计划：

```bash
sos plan --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG --out PLAN_PATH
```

先 dry run：

```bash
sos apply --plan PLAN_PATH
```

确认计划无误后再真正执行：

```bash
sos apply --plan PLAN_PATH --apply
```

### Claude Code 工作流

Claude Code 使用相同的流程，只需加上 `--host claude`。skill root 通常是 `~/.claude/skills`（项目级工作区中也可以是 `.claude/skills`）。先检查，不写入：

```bash
sos scan --root ~/.claude/skills
sos propose --root ~/.claude/skills
```

生成 Claude 计划（不传 `--codex-config`——Claude 没有中央 skill 注册表）：

```bash
sos plan --host claude --root ~/.claude/skills --runtime-root ~/.sos --out plan.toml
```

`--codex-config` 标志适用于 `sos plan` 和 `sos changes`：`--host codex` 时为必填项，`--host claude` 时会被拒绝。`sos apply` 命令从计划 TOML 中读取 host，因此 apply 命令不直接接受 `--codex-config`。

先 dry run，再 apply：

```bash
sos apply --plan plan.toml
sos apply --plan plan.toml --host claude --apply
```

Apply 后，原始 skill 目录会被移动到 `~/.claude/skills/.sos-archive/<pack-id>/<name>/`，Claude 将不再发现它们。`sos-<pack>` pointer skills 成为 active 层入口。

恢复时，归档目录会被移回原处：

```bash
sos restore <backup-id> --runtime-root ~/.sos --apply
```

## 安全模型

SOS 默认很保守。

- `scan` 和 `propose` 不写入。
- `plan` 只写指定的计划文件。
- 不带 `--apply` 的 `apply` 只是 dry run。
- `apply --apply` 会先创建备份，再执行受管理的写入。
- 源 skill 删除默认关闭，需要同时提供 `--delete-source`、`--apply` 和 `--confirm-delete-source <pack-id>`。
- restore 和 backup cleanup 默认也是 dry run，只有加上 `--apply` 才会写入。

运行任何会写文件的命令前，都应该先看计划。如果不确定，就再跑一次 dry run。

## SOS 会生成什么

当你确认并 apply 一个计划后，SOS 会把生成出来的 active skills 写入你选择的 skill root。生成入口会保持很短：

- `sos-haruhi`：用于 pack 管理、状态查看、备份和恢复的 companion skill；
- `sos-<pack>`：每个技能包对应一个 pointer skill。

pointer skill 不会塞入原始 `SKILL.md` 全文。它会指向 pack manifest 和受管理的 vault 副本。如果用户明确说了 packed skill name，pointer 会按 manifest `skills.name` 精确匹配；如果用户没有指定，就根据 manifest `skills.name` 和 `skills.description` 选择，歧义时先问用户。这样 active 层保持轻，详细内容留在该在的地方。

## 它是怎么工作的

```text
.
|-- .agents/skills/sos/     # 面向 Codex 的 SOS skill wrapper
|-- references/             # 公开行为和安全说明
|-- src/sos/                # CLI 和库实现
|   |-- cli.py              # 命令行入口
|   |-- scanner.py          # SKILL.md 发现
|   |-- propose.py          # 技能包建议规则
|   |-- pack_inspect.py     # 只读 pack list/show helper
|   |-- changes.py          # 只读 runtime 和 skill drift 报告
|   |-- planner.py          # 可审查写入计划
|   |-- apply.py            # 计划执行和可回滚写入
|   |-- sync.py             # 技能包激活和 clean sync
|   |-- backups.py          # 备份、恢复和保留策略
|   `-- templates/          # 打包进 Python 包的 pointer skill 模板
|-- templates/              # 生成 skill 模板的源副本
|-- tests/                  # 单元测试和 CLI smoke tests
|-- README.md               # 英文 README
|-- README_CN.md            # 中文 README
|-- pyproject.toml          # Python 包元数据
`-- LICENSE
```

典型的 SOS runtime root 长这样：

```text
<runtime-root>/
  backups/
  packs/
  state/
  vault/
```

- `vault/` 保存受管理的 skill 副本；
- `packs/` 保存 TOML pack manifests，包括每个 managed skill 的 `name`、`description`、source path、vault path 和 sync fingerprints；
- `state/` 保存 registry 状态；
- `backups/` 保存写入前创建的 config 和 vault 快照。

pack proposal 是确定性的。SOS 会先看 Agent Skill head metadata，尤其是 `name` 和 `description`；先识别清楚的 source/tool family，比如 Apify 或 Obsidian，再识别 Docs、Browser、Deploy、Data 这类功能组。歧义 skills 会留给人工 review，而不是交给隐藏分类器直接打包。

## CLI 参考

| 命令 | 用途 | 默认是否写入 |
| --- | --- | --- |
| `sos scan --root <path> [--codex-config <path>]` | 列出某个目录下已启用的 skills。 | 否 |
| `sos propose --root <path>` | 根据扫描结果提出技能包候选。 | 否 |
| `sos plan --host <host> --root <path> --runtime-root <path> --codex-config <path> --out <path>` | 写出可审查的计划文件。 | 只写计划文件 |
| `sos apply --plan <path> [--host <host>]` | 汇总计划内容，做 dry run；未传 --host 时从计划文件中推断。 | 否 |
| `sos apply --plan <path> [--host <host>] --apply` | 复制 skills、写 manifest 和 pointer、禁用原入口（Codex：写配置；Claude：移入 `.sos-archive`）并创建备份。 | 是 |
| `sos pack activate <pack> --runtime-root <path>` | 激活技能包，并在符合条件时执行 clean sync。 | 可能 |
| `sos pack list --runtime-root <path>` | 列出已写入的 runtime packs。 | 否 |
| `sos pack show <pack> --runtime-root <path>` | 显示一个 pack 的 manifest 和其管理的 skills。 | 否 |
| `sos pack sync <pack> --runtime-root <path>` | 展示技能包同步计划。 | 否 |
| `sos pack sync <pack> --runtime-root <path> --apply` | 执行有效的技能包同步计划。 | 是 |
| `sos changes --root <path> --runtime-root <path> --codex-config <path>` | 报告新增、缺失、变更、过期或意外启用的 skills 和 pointers。 | 否 |
| `sos status --runtime-root <path>` | 查看 runtime registry 和备份状态。 | 否 |
| `sos backup list --runtime-root <path>` | 列出备份。 | 否 |
| `sos backup clean --runtime-root <path> --keep <count>` | 预览备份清理。 | 否 |
| `sos backup clean --runtime-root <path> --keep <count> --apply` | 清理旧备份。 | 是 |
| `sos restore <backup-id> --runtime-root <path>` | 预览恢复目标。 | 否 |
| `sos restore <backup-id> --runtime-root <path> --apply` | 恢复备份记录中的 config 和 vault 目标。 | 是 |

## 兼容性

SOS 支持两种宿主：

- **Codex**：写入路径在创建备份后更新 Codex skill 配置，且只有传入 `--apply` 时才会写入。
- **Claude Code**：写入路径将被禁用的源目录移入 `<skill-root>/.sos-archive/<pack-id>/<name>/`，使 Claude 不再发现它们；同样在创建 vault 备份后执行，且只有传入 `--apply` 时才会写入。

生成的 skills 是普通 `SKILL.md` 文件夹，pack 元数据存储为普通 TOML manifest。通过每条写入命令的 `--host {codex,claude}` 参数选择宿主。

## 开发

运行测试：

```bash
python -m pytest
```

源码树 CLI smoke check：

```bash
PYTHONPATH=src python -m sos --version
```

Windows PowerShell：

```powershell
$env:PYTHONPATH = "src"
python -m sos --version
```

## 项目状态

SOS 仍然是早期软件。已经实现的行为有测试覆盖，但公开 API 和技能包建议模型在稳定版本前仍可能调整。

## 安全和隐私

不要提交真实本地配置、私人 skill 库、备份、runtime vault 内容、账号数据或 token。分享问题时，请把本地路径、用户名和私人 workspace 名称替换成占位符。

## 许可证

MIT License. See [LICENSE](LICENSE).
