# Skill Orchestration System

[English](README.md) | [中文](README_CN.md)

你的 agent skills 应该像一套顺手的工具箱，而不是越堆越乱的杂物抽屉。

Skill Orchestration System，简称 SOS，是一个面向 Codex 的本地 skill 整理工具。它把不断增长的 skill 库整理成更小、更清楚、可审查、可激活、可回退的技能包。它先写计划，再写文件；先 dry run，再真正 apply；先备份，再修改。

当前 SOS 以 Codex 为主。Claude Code 兼容性目前只保留结构入口，还没有接入专门的安装器、settings 写入器或完整集成测试。

## 为什么需要 SOS

Agent skill 好用，是因为很容易加进去。问题也出在这里。

时间一长，skills 目录很容易混进各种东西：旧实验、一次性工作流、插件缓存副本、个人 helper、生成出来的 pointer，还有少数真正常用的 skills 被埋在中间。一次暴露太多入口，agent 反而更难稳定使用。手动搬文件也不是不行，但只要漏掉配置、备份或回滚链路，后面就会变得难收拾。

SOS 做的事情很朴素：

- 扫描本地包含 `SKILL.md` 的技能目录；
- 按任务用途提出技能包建议；
- 在真正写入之前先生成可审查计划；
- 把选中的 skills 复制到受管理的 vault；
- 生成简短的 active pointer skills，例如 `sos-<pack>`；
- 记录 manifest、registry、fingerprint 和备份；
- 在需要时恢复或检查状态。

目标不是把 skills 变复杂，而是让它们重新变得好用。

## 一句话版本

SOS 有两层：

- `.agents/skills/sos/` 里的 **Codex skill wrapper**，负责引导 no-global-install 工作流；
- `src/sos/` 里的 **Python CLI backend**，负责确定性的扫描、规划、写入、同步、备份和恢复。

skill 负责告诉 agent 下一步该看什么、做什么；CLI 负责真正的文件操作。这个边界很重要：提示词可以引导，但写文件应该交给确定性的代码。

## 不做全局安装也能开始

推荐的第一步，是直接使用仓库自带的 `sos` skill。你可以 clone 这个仓库，在 Codex 里打开它，然后让 Codex 用 SOS skill 检查或整理你的本地 skills。

```bash
git clone https://github.com/Rainnystone/skill-orchestration-system.git
cd skill-orchestration-system
```

然后对 Codex 说：

```text
Use the sos skill to inspect my local skills and suggest a safe plan.
```

SOS skill 会先检查当前环境能不能直接运行 SOS。你也可以直接运行 doctor：

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

如果你想按普通 Python 项目的方式开发 SOS，需要 Python 3.11 或更新版本。

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

## 怎么使用 SOS

SOS 有两条主要使用路径。

### Codex skill 路径

这是推荐的第一次使用方式。把这个仓库放在 Codex 可以访问的 workspace 里，然后直接让 Codex 使用仓库自带的 `sos` skill。你不需要先记住整套 CLI 命令。

可以这样说：

```text
Use the sos skill to inspect my local Codex skills and explain what it finds.
Use the sos skill to propose skill packs, but do not write anything yet.
Use the sos skill to create a dry-run plan for organizing my skills.
Use the sos skill to apply the reviewed plan.
Use the sos skill to show what is inside my current packs.
Use the sos skill to check what changed after I installed new skills.
```

skill 被触发后，Codex 会读取 `.agents/skills/sos/SKILL.md`，运行或检查 `sos_doctor.py`，判断当前应该走 repo-local 模式还是 installed-CLI 模式；缺路径时会先问你，然后再调用默认 dry-run-first 的 SOS 命令。

### CLI 路径

CLI 是 skill 在需要确定性文件操作时调用的后端。如果你已经安装了 SOS，命令形式是：

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

也就是说，产品命令族仍然是 `sos ...`。`python -m sos ...` 只是 no-global-install 场景下，从仓库源码运行同一个后端的方式。

### 应用计划之后

当你确认并 apply 一个计划后，SOS 会把 active pointer skills 写入你选择的 skills root：

- `sos-haruhi`：负责 SOS 状态、备份、恢复和 pack 管理；
- `sos-<pack>`：指向某个生成出来的技能包，例如 pack id 是 `writing` 时会有 `sos-writing`。

之后你就像使用普通 Codex skills 一样使用它们：

```text
Use sos-haruhi to show my SOS status.
Use sos-writing for this documentation task.
```

pack pointer 会先运行 `sos pack activate PACK_ID --runtime-root RUNTIME_ROOT --sync=clean-auto`，再读取受管理 vault 中的 skill 副本。这样 SOS 可以让 active 层保持很轻，同时把完整 skill 内容保留在 vault 中。

### 查看一个 pack 里有什么

pack 写好之后，你不需要猜 agent 会看到什么。可以问 `sos` skill，也可以直接运行只读命令：

```bash
sos pack list --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT
sos pack show PACK_ID --runtime-root RUNTIME_ROOT --skill SKILL_NAME
```

`pack list` 回答“我现在有哪些 packs”；`pack show` 回答“这个 pack 里有哪些 skills”。如果你指定了 skill name，SOS 会按 manifest 里的 `skills.name` 精确过滤，这样 agent 可以直接看一个明确的 vault skill，而不是先浏览整个 pack。

### 安装或编辑新 skills 之后

当你的本地 skill 库发生变化时，先用 `changes` 看状态，再决定要不要重建计划：

```bash
sos changes --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG
```

这也是只读命令。它会报告新增的 unmanaged skills、缺失或变更的 managed sources、vault drift、缺失或过期的 generated pointers，以及意外重新启用的 managed source skills。它不会自动修复，只会告诉你哪些地方值得重新 scan、propose 或生成新的可审查计划。

### Workspace recommendation 路径

除了整理整套 skill 库，SOS 还支持“这个 workspace 现在应该启用什么”的本地推荐流程，而且不会把这次选择变成全局 skill 改动。

- `sos-nagato` 负责 workspace 级推荐。它查看当前 workspace，在已有 learned reference 时一并读取，再建议适合的 managed packs。
- `sos-asahina` 不负责自动推荐。它只在你明确要整理和沉淀已批准的推荐结果时使用。

这个流程完全本地、可审查：

1. 先看当前 workspace，不写任何文件：

   ```bash
   sos recommend context --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT
   ```

2. 把你认可的 packs 写成可审查的 workspace activation plan：

   ```bash
   sos recommend activation-plan --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --packs docs,browser --out WORKSPACE_PLAN
   ```

3. 先 dry run 预览：

   ```bash
   sos recommend activate --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT
   ```

4. 确认后再真正应用：

   ```bash
   sos recommend activate --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --apply
   ```

应用后，SOS 会把 workspace 专用 skills 写到 `WORKSPACE_ROOT/.agents/skills/`：

- `sos-nagato/SKILL.md`
- `sos-asahina/SKILL.md`
- 每个所选 pack 对应一个 `sos-<pack>/SKILL.md`

推荐过程的状态保存在 `RUNTIME_ROOT/state/recommendations/`：

- `selection-events.jsonl`：记录被接受的 selection records；
- `asahina-reference.md`：保存供 `sos-nagato` 读取的 learned reference。

这个流程不会写入全局 skills，不会使用 hooks，也不会保存 raw prompt、file contents、model messages、account identifiers 或过于宽泛的私人绝对路径。workspace 只会以哈希后的标识写入记录，因此日志既可审查，也不会直接暴露原始路径。

## 一个安全的起步流程

下面的命令使用大写占位符，请替换成你自己的真实路径：

- `SKILLS_ROOT`：当前 active Codex skills 目录；
- `RUNTIME_ROOT`：你希望 SOS 使用的 runtime 目录；
- `CODEX_CONFIG`：你的 Codex config 路径；
- `PLAN_PATH`：你希望 SOS 写出的计划文件路径。

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

## 安全模型

SOS 默认很保守。

- `scan` 和 `propose` 不写入；
- `plan` 只写指定的计划文件；
- 不带 `--apply` 的 `apply` 只是 dry run；
- `apply --apply` 会先创建备份，再执行受管理写入；
- 源 skill 删除默认关闭，必须同时提供 `--delete-source`、`--apply` 和 `--confirm-delete-source <pack-id>`；
- restore 和 backup cleanup 默认也是 dry run，只有加上 `--apply` 才会真的写入。

运行任何会写文件的命令前，都应该先看计划。如果不确定，就再跑一次 dry run。

## SOS 会生成什么

当你确认并 apply 一个计划后，SOS 会把生成出来的 active skills 写进你选择的 skill root。生成入口会保持很短：

- `sos-haruhi`：用于 pack 管理、状态查看、备份和恢复的 companion skill；
- `sos-<pack>`：每个技能包对应一个 pointer skill。

pointer skill 不会塞入原始 `SKILL.md` 全文。它会指向 pack manifest 和受管理的 vault 副本。如果用户明确说了 packed skill name，pointer 会按 manifest `skills.name` 精确匹配；如果用户没有指定，就根据 manifest `skills.name` 和 `skills.description` 选择，歧义时先问用户。这样 active 层保持轻量，详细内容留在该留的地方。

## 它是怎么工作的

```text
.
|-- .agents/skills/sos/     # 面向 Codex 的 SOS skill wrapper
|-- references/             # 公开行为和安全参考
|-- src/sos/                # CLI 和库实现
|   |-- cli.py              # 命令行入口
|   |-- scanner.py          # SKILL.md 发现
|   |-- propose.py          # 技能包建议规则
|   |-- pack_inspect.py     # 只读 pack list/show helpers
|   |-- changes.py          # 只读 runtime 和 skill drift 报告
|   |-- planner.py          # 可审查写入计划
|   |-- apply.py            # 计划执行和可回滚写入
|   |-- sync.py             # 技能包激活和 clean sync
|   |-- backups.py          # 备份、恢复和保留策略
|   `-- templates/          # 打包进 Python 包的 pointer skill 模板
|-- templates/              # 生成 skill 模板的源码副本
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
- `packs/` 保存 TOML pack manifests，其中包含每个 managed skill 的 `name`、`description`、source path、vault path 和 sync fingerprints；
- `state/` 保存 registry state；
- `backups/` 保存写入前创建的 config 和 vault 快照。

pack proposal 是确定性的。SOS 会优先看 Agent Skill 的 head metadata，尤其是 `name` 和 `description`；先识别清楚的 source 或 tool family，例如 Apify 或 Obsidian，再识别 Docs、Browser、Deploy、Data 这类功能组。歧义 skills 会留给人工 review，而不是交给隐藏分类器直接打包。

## CLI 参考

| 命令 | 用途 | 默认是否写入 |
| --- | --- | --- |
| `sos scan --root <path> [--codex-config <path>]` | 列出某个目录下已启用的 skills。 | 否 |
| `sos propose --root <path>` | 根据扫描结果提出技能包候选。 | 否 |
| `sos plan --root <path> --runtime-root <path> --codex-config <path> --out <path>` | 写出可审查的计划文件。 | 只写计划文件 |
| `sos apply --plan <path>` | 汇总计划内容，做 dry run。 | 否 |
| `sos apply --plan <path> --apply` | 复制 skills、写 manifest 和 pointer、禁用原入口并创建备份。 | 是 |
| `sos pack activate <pack> --runtime-root <path>` | 激活技能包，并在符合条件时执行 clean sync。 | 可能 |
| `sos pack list --runtime-root <path>` | 列出已写入的 runtime packs。 | 否 |
| `sos pack show <pack> --runtime-root <path>` | 显示一个 pack 的 manifest 和其管理的 skills。 | 否 |
| `sos pack sync <pack> --runtime-root <path>` | 展示技能包同步计划。 | 否 |
| `sos pack sync <pack> --runtime-root <path> --apply` | 执行有效的技能包同步计划。 | 是 |
| `sos changes --root <path> --runtime-root <path> --codex-config <path>` | 报告新增、缺失、变更、过期或意外启用的 skills 和 pointers。 | 否 |
| `sos recommend context --workspace-root <path> --runtime-root <path>` | 查看当前 workspace 的推荐上下文。 | 否 |
| `sos recommend activation-plan --workspace-root <path> --runtime-root <path> --packs <ids> --out <path>` | 写出 workspace 级激活计划。 | 只写计划文件 |
| `sos recommend activate --plan <path> --workspace-root <path> --runtime-root <path>` | 预览 workspace 激活计划。 | 否 |
| `sos recommend activate --plan <path> --workspace-root <path> --runtime-root <path> --apply` | 写入 workspace 专用 skills 和 learned reference stub。 | 是 |
| `sos recommend record-selection --runtime-root <path> --workspace-root <path> ...` | 记录一次被接受的 workspace 推荐选择。 | 是 |
| `sos recommend learn --runtime-root <path>` | 预览 learned reference。 | 否 |
| `sos recommend learn --runtime-root <path> --apply` | 写入 learned reference。 | 是 |
| `sos status --runtime-root <path>` | 查看 runtime registry 和备份状态。 | 否 |
| `sos backup list --runtime-root <path>` | 列出备份。 | 否 |
| `sos backup clean --runtime-root <path> --keep <count>` | 预览备份清理。 | 否 |
| `sos backup clean --runtime-root <path> --keep <count> --apply` | 清理旧备份。 | 是 |
| `sos restore <backup-id> --runtime-root <path>` | 预览恢复目标。 | 否 |
| `sos restore <backup-id> --runtime-root <path> --apply` | 恢复备份记录中的 config 和 vault 目标。 | 是 |

## 兼容性

SOS 当前以 Codex 为主。经过测试的写入路径可以在创建备份后更新 Codex skill 配置，而且只有显式传入 `--apply` 时才会真的写入。

Claude Code 兼容性目前只在结构层面存在：生成的 skills 是普通 `SKILL.md` 文件夹，pack 元数据是标准 TOML manifest。SOS 还没有 Claude Code 专用安装器、settings 写入器或完整集成测试。

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

SOS 仍然是早期软件。已实现的行为有测试覆盖，但公开 API 和技能包建议模型在稳定版本前仍可能调整。

## 安全与隐私

不要提交真实本地配置、私人 skill 库、备份、runtime vault 内容、账户数据或 token。分享问题时，请把本地路径、用户名和私人 workspace 名称替换成占位符。

## 许可证

MIT License. See [LICENSE](LICENSE).
