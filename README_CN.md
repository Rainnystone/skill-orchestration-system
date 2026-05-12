# 让 Vibe Coding 变得更热闹的 SOS

[English](README.md) | [中文](README_CN.md)

你的 agent skills 应该像一间能派上用场的活动室，而不是一个越塞越满、最后谁也不敢打开的杂物柜。

Skill Orchestration System，简称 SOS，是给 Codex 和 Claude Code 用户整理本地 Agent Skills 的工具。它会扫描本地 skills，按任务提出 pack 建议，在真正写文件之前先生成可审查的计划，并且把备份、回滚和状态记录放在手边。听起来很朴素，但既然我们已经被拉进了这个奇怪的 SOS 团式工作流，至少得让它不要把房间弄得更乱。

SOS 同时支持 Codex 和 Claude Code 两种宿主。通过每条写入命令的 `--host {codex,claude}` 参数选择宿主。

## 为什么你需要 SOS

Agent skill 好用，是因为它很容易加进去。问题也正是它太容易加进去了。

几个星期之后，你的 skills 目录里可能同时住着旧实验、一次性工作流、插件缓存副本、个人 helper，以及少数真正每天会用的技能。全部保持 active，agent 会看见太多入口；手动搬文件，又很容易漏掉配置、备份或回滚路径。所谓 vibe coding，如果最后变成在文件夹里翻箱倒柜，那气氛未免太现实了一点。

SOS 做的是把这堆东西整理成更小、更可审查的形状：

- 扫描本地 `SKILL.md` 目录；
- 按任务提出 docs、browser、data、deploy 或工具家族类 pack；
- 在受管理写入前先生成 dry-run 计划；
- 把选中的 skills 复制进受管理的 vault；
- 生成短小的 active skills，比如 `sos-haruhi` 和 `sos-<pack>`；
- 记录 manifests、registry、fingerprints、backups 和 restore 路径；
- 在某个 workspace 需要临时技能组合时，通过 `sos-nagato` 推荐 workspace 级 packs。

目标不是把技能系统变得神秘。目标是让神秘感留给你真正要做的东西，而不是留给“到底哪个文件夹里才是正确的 SKILL.md”。

## 怎么使用 SOS

实际使用有三条路：让 Codex 调用仓库自带的 `sos` skill，直接用 CLI，或者在某个 workspace 里使用推荐流程。

### 使用仓库自带的 Codex skill

这是推荐的第一次使用方式。把这个仓库放在 Codex 可以访问的 workspace 里，然后让 Codex 使用仓库自带的 `sos` skill。

可以这样说：

```text
Use the sos skill to inspect my local Codex skills and explain what it finds.
Use the sos skill to propose skill packs, but do not write anything yet.
Use the sos skill to create a dry-run plan for organizing my skills.
Use the sos skill to apply the reviewed plan.
Use the sos skill to show what is inside my current packs.
Use the sos skill to check what changed after I installed new skills.
```

这个 skill 会先判断 SOS 能不能从当前源码 checkout 运行，或者是否有已安装的 CLI；缺路径时会先问你；然后才调用默认 dry-run-first 的 SOS 命令。skill 负责引导对话，真正写文件的动作交给确定性的 Python 代码。

### 直接使用 CLI

CLI 是 skill 背后的确定性后端。如果已经安装 SOS，命令大致是这样：

```bash
sos scan --root SKILLS_ROOT --codex-config CODEX_CONFIG
sos propose --root SKILLS_ROOT
sos plan --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG --out PLAN_PATH
sos apply --plan PLAN_PATH
sos apply --plan PLAN_PATH --apply
```

安全节奏永远一样：

1. `scan` 和 `propose` 只检查。
2. `plan` 只写计划文件。
3. 不带 `--apply` 的 `apply` 只预览。
4. 你审查计划后，再运行 `apply --apply` 做受管理写入。

### 使用生成出来的 pack skills

计划 apply 之后，SOS 会把短小的 active skills 写入你选择的 skills root：

- `sos-haruhi`：查看 SOS 状态、管理 packs、备份、恢复和检查变化；
- `sos-<pack>`：每个生成 pack 一个入口，比如 `sos-docs` 或 `sos-browser`。

之后像普通 Codex skills 一样使用它们：

```text
Use sos-haruhi to show my SOS status.
Use sos-docs for this documentation task.
Use sos-browser to inspect this local web flow.
```

pack pointer 不会把原始 skill 全文塞进 active 层。它会把 agent 指向 pack manifest 和受管理 vault 副本。如果你明确说出某个 packed skill，SOS 会按 manifest `skills.name` 精确匹配；如果没说清楚，它会根据 manifest 元数据选择，并在歧义时先问你。
在读取 vault 副本前，pack pointer 会使用 `pack activate PACK_ID --runtime-root RUNTIME_ROOT --sync=clean-auto`，这样受管理副本可以保持同步。

### 查看现有 packs

想先确认活动室里到底有什么，再让人开始发号施令，可以用：

```bash
sos pack list --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT --skill SKILL_NAME
```

这些命令只读。它们会告诉你有哪些 packs、pack 里有哪些 skills、受管理的 vault 副本在哪里。

### 安装或编辑 skills 之后检查漂移

本地 skill 库变化后，先运行：

```bash
sos changes --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG
```

它会报告新增的 unmanaged skills、缺失或变化的 managed sources、vault drift、过期 pointer，以及意外重新启用的 managed source skills。它不会自己修复，只会指出问题在哪。说实话，这种克制在 SOS 团式工作里还挺稀有。

### 使用 workspace 推荐

有些 workspace 需要自己的 active skills，但你并不想改全局技能设置。这就是凉宫彩蛋组登场的地方。

- `sos-nagato` 负责 workspace 级推荐。它查看轻量 workspace 信号，读取本地 learned reference，然后建议适合当前任务的 managed packs。
- `sos-asahina` 是显式触发的整理工具。只有当你想把已批准的本地推荐历史整理成 learned reference 时才使用它。它不是 hook，也不会在后台自动运行。

典型流程：

```bash
sos recommend context --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT
sos recommend activation-plan --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --packs docs,browser --out WORKSPACE_PLAN
sos recommend activate --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT
sos recommend activate --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --apply
```

workspace activation 成功后，SOS 会把 workspace 专用 skills 写到：

```text
WORKSPACE_ROOT/.agents/skills/
```

包括：

- `sos-nagato/SKILL.md`
- `sos-asahina/SKILL.md`
- 每个所选 pack 对应一个 `sos-<pack>/SKILL.md`

如果用户接受了推荐，可以记录这个本地事实：

```bash
sos recommend record-selection --runtime-root RUNTIME_ROOT --workspace-root WORKSPACE_ROOT --scenario-label docs --scenario-tags docs --packs docs --skills documents --manifest-fingerprint sha256:example
```

当你明确想刷新 learned reference 时：

```bash
sos recommend learn --runtime-root RUNTIME_ROOT
sos recommend learn --runtime-root RUNTIME_ROOT --apply
```

`learn` 会先用当前 runtime manifests 校验历史记录。对不上真实 pack 或 skill 的旧记录、手写 JSONL 或过期数据会被跳过，不会变成新的推荐依据。

## 怎么安装 SOS

### 不做全局安装也能试用

克隆仓库：

```bash
git clone https://github.com/Rainnystone/skill-orchestration-system.git
cd skill-orchestration-system
```

然后让 Codex 使用它：

```text
Use the sos skill to inspect my local skills and suggest a safe plan.
```

也可以直接运行 doctor：

```bash
python .agents/skills/sos/scripts/sos_doctor.py --no-path-lookup
```

源码 checkout 下的 CLI smoke check：

**macOS / Linux**

```bash
PYTHONPATH=src python -m sos --version
```

**Windows PowerShell**

```powershell
$env:PYTHONPATH = "src"
python -m sos --version
```

预期输出：

```text
sos 0.1.0
```

### 开发安装

需要 Python 3.11 或更新版本。

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m sos --version
```

**Windows PowerShell**

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

### Claude Code 宿主

Claude Code 使用同一套 scan、plan、dry-run、apply 节奏。毕竟一个奇怪社团有两个入口也不算太离谱。使用 `--host claude`；skill root 通常是 `~/.claude/skills`，项目级工作区里也可以是 `.claude/skills`。

```bash
sos scan --root ~/.claude/skills
sos propose --root ~/.claude/skills
sos plan --host claude --root ~/.claude/skills --runtime-root ~/.sos --out plan.toml
sos apply --plan plan.toml
sos apply --plan plan.toml --host claude --apply
```

对 `sos plan` 和 `sos changes` 来说，`--host codex` 需要 `--codex-config`，`--host claude` 会拒绝 `--codex-config`。`sos apply` 会从 plan TOML 里读取 host，所以 apply 命令本身不直接接收 `--codex-config`。Apply 后，被禁用的 Claude source skills 会移动到 `~/.claude/skills/.sos-archive/<pack-id>/<name>/`；restore 会把它们移回去。

## 技术参考

### 安全模型

SOS 默认保守。

- `scan`、`propose`、`pack list`、`pack show`、`changes`、`status` 和大多数预览命令不写文件。
- `plan` 只写显式指定的计划文件。
- 不带 `--apply` 的 `apply` 只是 dry run。
- `apply --apply` 会先创建备份，再执行受管理写入。
- 源 skill 删除默认关闭，必须同时提供 `--delete-source`、`--apply` 和 `--confirm-delete-source <pack-id>`。
- restore 和 backup cleanup 默认也是 dry run，只有加 `--apply` 才写入。
- workspace recommendation activation 必须提供外部 `--workspace-root` 锚点，篡改过的 plan 不能悄悄把 workspace skills 写到别处。

### SOS 会生成什么

全局整理计划会把生成的 active skills 写到你选择的 skill root。workspace 推荐计划只会写到当前 workspace 的 `.agents/skills/` 目录。

生成入口刻意保持很短：

- `sos-haruhi`：SOS 管理 companion skill；
- `sos-nagato`：workspace 推荐；
- `sos-asahina`：显式 learned-reference 整理；
- `sos-<pack>`：每个所选 pack 一个 pointer skill。

pointer skills 不嵌入完整 source skill 正文。它们把 agent 路由到 manifests 和 vault 副本，让 active skill surface 保持轻量。

### Runtime 布局

```text
<runtime-root>/
  backups/
  packs/
  state/
  vault/
```

- `vault/` 保存受管理的 skill 副本。
- `packs/` 保存 TOML pack manifests。
- `state/` 保存 registry 和 recommendation state。
- `backups/` 保存写入前创建的 config 和 vault 快照。

workspace recommendation state 位于：

```text
<runtime-root>/state/recommendations/
  selection-events.jsonl
  asahina-reference.md
```

记录保留在本地。SOS 只保存紧凑的 scenario tags、selected pack ids、selected skill names、manifest fingerprint 和哈希后的 workspace id。它不保存 raw prompts、file contents、model messages、account identifiers 或宽泛的私人绝对路径。

### 项目结构

```text
.
|-- .agents/skills/sos/     # 面向 Codex 的 SOS skill wrapper
|-- references/             # 公开行为和安全参考
|-- src/sos/                # CLI 和库实现
|   |-- cli.py              # 命令行入口
|   |-- scanner.py          # SKILL.md 发现
|   |-- propose.py          # pack 建议规则
|   |-- pack_inspect.py     # 只读 pack list/show helpers
|   |-- changes.py          # 只读 runtime 和 skill drift 报告
|   |-- planner.py          # 可审查写入计划
|   |-- apply.py            # 计划执行和可回滚写入
|   |-- workspace_activation.py
|   |-- recommendation_engine.py
|   |-- recommendation_store.py
|   `-- templates/          # 打包进 Python 包的 generated-skill templates
|-- templates/              # generated-skill templates 的源码副本
|-- tests/                  # 单元测试和 CLI smoke tests
|-- README.md
|-- README_CN.md
|-- pyproject.toml
`-- LICENSE
```

### CLI 参考

| 命令 | 用途 | 默认是否写入 |
| --- | --- | --- |
| `sos scan --root <path> [--codex-config <path>]` | 列出某个目录下已启用的 skills。 | 否 |
| `sos propose --root <path>` | 根据扫描结果提出 pack 候选。 | 否 |
| `sos plan --host <host> --root <path> --runtime-root <path> --codex-config <path> --out <path>` | 写出可审查的计划文件。 | 只写计划文件 |
| `sos apply --plan <path> [--host <host>]` | 汇总计划内容，做 dry run；未传 `--host` 时从计划文件中推断。 | 否 |
| `sos apply --plan <path> [--host <host>] --apply` | 复制 skills、写 manifest 和 pointer、禁用原入口（Codex：写配置；Claude：移入 `.sos-archive`）并创建备份。 | 是 |
| `sos pack activate <pack> --runtime-root <path>` | 激活 pack，并在符合条件时执行 clean sync。 | 可能 |
| `sos pack list --runtime-root <path>` | 列出 runtime packs。 | 否 |
| `sos pack show <pack> --runtime-root <path>` | 显示一个 pack manifest 和受管理 skills。 | 否 |
| `sos pack sync <pack> --runtime-root <path>` | 展示 pack sync 计划。 | 否 |
| `sos pack sync <pack> --runtime-root <path> --apply` | 执行有效的 pack sync 计划。 | 是 |
| `sos changes --root <path> --runtime-root <path> --codex-config <path>` | 报告新增、缺失、变化、过期或意外启用的 skills 和 pointers。 | 否 |
| `sos recommend context --workspace-root <path> --runtime-root <path>` | 查看 workspace 推荐上下文。 | 否 |
| `sos recommend activation-plan --workspace-root <path> --runtime-root <path> --packs <ids> --out <path>` | 写出 workspace activation plan。 | 只写计划文件 |
| `sos recommend activate --plan <path> --workspace-root <path> --runtime-root <path>` | 预览 workspace activation。 | 否 |
| `sos recommend activate --plan <path> --workspace-root <path> --runtime-root <path> --apply` | 写入 workspace skills 和 learned-reference stub。 | 是 |
| `sos recommend record-selection --runtime-root <path> --workspace-root <path> ...` | 记录一次被接受的 workspace 推荐选择。 | 是 |
| `sos recommend learn --runtime-root <path>` | 预览 learned reference。 | 否 |
| `sos recommend learn --runtime-root <path> --apply` | 写入 learned reference。 | 是 |
| `sos status --runtime-root <path>` | 查看 runtime registry 和 backup 状态。 | 否 |
| `sos backup list --runtime-root <path>` | 列出备份。 | 否 |
| `sos backup clean --runtime-root <path> --keep <count>` | 预览备份清理。 | 否 |
| `sos backup clean --runtime-root <path> --keep <count> --apply` | 清理旧备份。 | 是 |
| `sos restore <backup-id> --runtime-root <path>` | 预览 restore 目标。 | 否 |
| `sos restore <backup-id> --runtime-root <path> --apply` | 恢复备份记录中的 config 和 vault 目标。 | 是 |

### 兼容性

SOS 支持两种宿主：

- **Codex**：写入路径在创建备份后更新 Codex skill 配置，且只有传入 `--apply` 时才会写入。
- **Claude Code**：写入路径将被禁用的源目录移入 `<skill-root>/.sos-archive/<pack-id>/<name>/`，使 Claude 不再发现它们；同样在创建 vault 备份后执行，且只有传入 `--apply` 时才会写入。

生成的 skills 是普通 `SKILL.md` 文件夹，pack 元数据存储为普通 TOML manifest。通过每条写入命令的 `--host {codex,claude}` 参数选择宿主。

### 开发

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

### 项目状态

SOS 仍然是早期软件。已实现的行为有测试覆盖，但公开 API 和 pack proposal 模型在稳定版本前仍可能调整。

### 安全与隐私

不要提交真实本地配置、私人 skill 库、备份、runtime vault 内容、账户数据或 token。分享问题时，请把本地路径、用户名和私人 workspace 名称替换成占位符。

## 许可证

MIT License. See [LICENSE](LICENSE).
