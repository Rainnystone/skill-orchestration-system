# 让 Vibe Coding 变得更热闹的 SOS

[English](README.md) | [中文](README_CN.md)

> 唉，真是够了。说到底，你的 agent skills 目录本该像一间干净整洁、随时能派上用场的社团活动室，而不是一个堆满过期杂物的储藏室。
> 为什么大多数 AI Agent 框架都觉得解决复杂任务的终极方案就是往 Prompt 里塞进几十个不同的技能和工具？
> 每次开开心心地开始 vibe-coding，不出三天，你的 skills 文件夹就会变得像 SOS 团活动室一样——被某个精力旺盛的“团长”胡乱塞满各种奇奇怪怪、根本派不上用场的小玩意。
> 如果把它们全部保持 active，Agent 每次看到这些繁杂的提示词就会眼花缭乱；要是由着性子手动搬运，迟早会漏掉某个配置文件或备份路径。
> 既然我们已经被拉进了这个奇怪的社团工作流，不如用最理性、最不折腾的文书规矩，帮那个爱折腾的团长和她的工具箱做一次彻底的整理。

---

## 🔍 什么是 SOS？

**Skill Orchestration System (SOS)** 是一款专门针对 **Codex** 和 **Claude Code** 设计的本地 Agent Skill 管理与动态路由引擎。

通过 **Skill Pack (技能包) 机制**、**Workspace 级按需推荐** 与 **本地自适应学习**，SOS 能够帮助开发者自动分类并隔离本地庞大的 `SKILL.md` 库。它能在不改变原有 Agent 发现逻辑的前提下，将 active 层的技能数量降低 90% 以上，从根本上解决 Agent 的**提示词污染 (Prompt Pollution)**、**上下文稀释** 和 **函数调用幻觉 (Function Hallucination)**。

---

## ⚡ 为什么你需要 SOS (Core Pain Points)

在开发和使用 AI Agent 时，随着项目迭代，本地技能库会迅速退化：

- **Prompt 污染与上下文暴涨**：所有 `SKILL.md` 全部处于 Active 状态，Agent 加载了大量无关工具。
- **全局技能与局部工作区冲突**：不同项目需要的工具集不同，全局污染导致 Agent 在特定项目里误调用工具。
- **手动维护配置易错且无回滚**：手动搬运、重命名技能目录时，经常遗漏配置或误删文件。
- **推荐逻辑死板，不符合开发者习惯**：固定规则的推荐无法适应开发者在特定目录下的高频工具组合。

SOS 做的是把这堆东西整理成更小、更可审查的形状：
- 扫描本地 `SKILL.md` 目录；
- 按任务提出 docs、browser、data、deploy 或工具家族类 pack；
- 在受管理写入前先生成 dry-run 计划；
- 把选中的 skills 复制进受管理的 vault；
- 生成短小的 active skills，比如 `sos-haruhi` 和 `sos-<pack>`；
- 记录 manifests、registry、fingerprints、backups 和 restore 路径；
- 在某个 workspace 需要临时技能组合时，通过 `sos-nagato` 推荐 workspace 级 packs。

---

## 🌟 核心特色功能

### 1. Skill Pack 与 Vault 隔离
SOS 会扫描你指定的 skills 根目录，提取出零散 of `SKILL.md` 文件夹，并提议将它们打包成不同的 **Skill Packs**。
- **Vault 隔离**：被打包的原始技能会安全地存放在受管理的 `<runtime-root>/vault/` 中。
- **Pointer 代理**：在 Agent 可见的技能目录中，只生成对应的快捷代理入口（如 `sos-docs`、`sos-browser`），它们不含庞大的具体实现，仅包含精简的路由元数据。
- **按需热加载**：当 Agent 决定使用某个 Pack 时，Pointer 会在后台通过 `sos pack activate` 自动与 Vault 进行极速同步，实现“按需唤醒”。

### 2. 基于 Workspace 的按需推荐与注入 (`sos-nagato`)
> *长门有希总是能在最关键的时候，默默递给你最需要的资料。*

全局技能库再干净，遇到特定的工作区（项目文件夹）还是会面临“这个项目要用 deploy 工具，那个项目只需要 test 工具”的矛盾。
- 每次在新的 Workspace 中，Agent 可以调用 `sos-nagato`。
- `sos-nagato` 会扫描当前工作区的轻量特征，结合本地已学习的经验，推荐出最适配的 Skill Packs。
- 确认后，SOS 会在当前项目的本地隐藏目录（Codex 的 `.agents/skills/` 或 Claude Code 的 `.claude/skills/`）中动态生成对应的 Pointer 文件。

### 3. 自适应事件记录与本地学习 (`sos-asahina`)
> *虽然朝比奈实玖瑠经常手忙脚乱，但只要认真把表格整理好，以后的推荐就会顺理成章。*

SOS 的推荐系统不是一成不变的，它拥有完全本地化的进化逻辑：
- **记录选择**：每当你在工作区接受并激活了某些 Packs，Agent 会调用 `sos recommend record-selection` 记录下这一事实。
- **指纹防过期**：每次记录均包含 Manifest 的哈希指纹。如果全局技能库发生了变更，过期的历史记录在学习时会被自动忽略，防止推荐模型学到过期知识。
- **本地编译学习**：通过运行 `sos recommend learn --apply`，SOS 会分析历史 selection 记录，编译生成一份精炼的本地人类可读 Markdown 参考：`asahina-reference.md`。之后 `sos-nagato` 就会基于这份参考，为同类 Workspace 自动推荐你最常用的工具。

---

## 🙋 常见问题解答 (FAQ)

### Q: SOS 是如何彻底防范 Agent 提示词/工具污染的？
**A**: 传统的 Agent 技能通常是将所有包含具体代码、使用说明的 `SKILL.md` 文件夹全部暴露在 Agent 的检索范围内，导致 Agent 在生成系统提示词时被塞入过多无用描述。
SOS 将技能全部归档到受管理的本地安全 Vault 中，仅在 Agent skills 目录中暴露少数 `sos-<pack>` 快捷指针。指针体积极小，只在 Agent 明确声明“我想使用 X 技能包”时，才会动态热激活 Vault 中的具体实现，从而让 active 层的提示词体积减少 90% 以上。

### Q: 为什么 SOS 支持 Codex 和 Claude Code 两种宿主？它们有什么区别？
**A**: SOS 设计了跨宿主的路径适配层。
- **Codex**：通过修改 Codex 专用的 skill 配置文件来启用/禁用技能。
- **Claude Code**：由于 Claude Code没有显式配置文件，它通过移动禁用技能文件夹到宿主目录下的 `.sos-archive/` 目录中，使 Claude 无法发现它们，从而达到禁用的效果。
在运行 CLI 时，可以通过 `--host {codex,claude}` 动态切换宿主逻辑。

### Q: 动态激活会影响 Agent 的响应速度吗？
**A**: 不会。SOS 的激活和同步（`sos pack activate`）基于高度优化的本地文件哈希指纹比对（Fingerprint）。如果 Vault 中的技能源文件没有发生实质性更改，同步过程仅需几毫秒，Agent 几乎毫无感知。

---

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
这也实现了安全激活路径：`pack activate` 命令被用来在 agent 决定读取或执行某技能时热加载。

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

有些 workspace 需要自己的 active skills，但你并不想改全局技能设置。这就是长门和朝比奈登场的地方。

- `sos-nagato` 负责 workspace 级推荐。它查看轻量 workspace 信号，读取本地 learned reference，然后建议适合当前任务的 managed packs。
- `sos-asahina` 是显式触发的整理工具。只有当你想把已批准的本地推荐历史整理成 learned reference 时才使用它。它不是 hook，也不会在后台自动运行。

Codex workspace activation 会写入 `.agents/skills`：

```bash
sos recommend activation-plan --host codex --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --packs docs,browser --out WORKSPACE_PLAN
sos recommend activate --host codex --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT
sos recommend activate --host codex --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --apply
```

Claude Code workspace activation 会写入 `.claude/skills`：

```bash
sos recommend activation-plan --host claude --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --packs docs,browser --out WORKSPACE_PLAN
sos recommend activate --host claude --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT
sos recommend activate --host claude --plan WORKSPACE_PLAN --workspace-root WORKSPACE_ROOT --runtime-root RUNTIME_ROOT --apply
```

包括：

- `sos-nagato/SKILL.md`
- `sos-asahina/SKILL.md`
- 每个所选 pack 对应一个 `sos-<pack>/SKILL.md`

如果用户接受了推荐，可以记录这个本地事实：

```bash
sos recommend record-selection --runtime-root RUNTIME_ROOT --workspace-root WORKSPACE_ROOT --scenario-label docs --scenario-tags docs --packs docs --skills documents --manifest-fingerprint MANIFEST_FINGERPRINT
```

这里要使用 `sos recommend context` 输出的 `manifest_fingerprint`。如果 runtime manifests 已经变了，SOS 会拒绝旧 fingerprint，免得过期历史教 `sos-nagato` 学到奇怪东西。

当你明确想刷新 learned reference 时：

```bash
sos recommend learn --runtime-root RUNTIME_ROOT
sos recommend learn --runtime-root RUNTIME_ROOT --apply
```

`learn` 会先用当前 runtime manifests 和 fingerprint 校验历史记录。对不上真实 pack、skill 或 manifest 状态的旧记录、手写 JSONL 或过期数据会被跳过，不会变成新的推荐依据。

---

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

Claude Code 使用同一套 scan、plan、dry-run、apply 节奏。使用 `--host claude`；skill root 通常是 `~/.claude/skills`，项目级工作区里也可以是 `.claude/skills`。

```bash
sos scan --root ~/.claude/skills
sos propose --root ~/.claude/skills
sos plan --host claude --root ~/.claude/skills --runtime-root ~/.sos --out plan.toml
sos apply --plan plan.toml
sos apply --plan plan.toml --host claude --apply
```

对 `sos plan` 和 `sos changes` 来说，`--host codex` 需要 `--codex-config`，`--host claude` 会拒绝 `--codex-config`。`sos apply` 会从 plan TOML 里读取 host，所以 apply 命令本身不直接接收 `--codex-config`。Apply 后，被禁用的 Claude source skills 会移动到 `~/.claude/skills/.sos-archive/<pack-id>/<name>/`；restore 会把它们移回去。

---

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

全局整理计划会把生成的 active skills 写到你选择的 skill root。workspace 推荐计划会写入 workspace 的宿主专属目录：Codex 写入 `.agents/skills/`（通过 `--host codex`），Claude Code 写入 `.claude/skills/`（通过 `--host claude`）。

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
| `sos plan --host {codex,claude} --root <path> --runtime-root <path> [--codex-config <path>] --out <path>` | 写出可审查的计划文件。codex 必须传 `--codex-config`，claude 会拒绝它。 | 只写计划文件 |
| `sos apply --plan <path> [--host {codex,claude}]` | 汇总计划内容，做 dry run；未传 `--host` 时从计划文件中推断。 | 否 |
| `sos apply --plan <path> [--host {codex,claude}] --apply` | 复制 skills、写 manifest 和 pointer、禁用原入口（Codex：写配置；Claude：移入 `.sos-archive`）并创建备份。 | 是 |
| `sos pack activate <pack> --runtime-root <path>` | 激活 pack，并在符合条件时执行 clean sync。 | 可能 |
| `sos pack list --runtime-root <path>` | 列出 runtime packs。 | 否 |
| `sos pack show <pack> --runtime-root <path>` | 显示一个 pack manifest 和受管理 skills。 | 否 |
| `sos pack sync <pack> --runtime-root <path>` | 展示 pack sync 计划。 | 否 |
| `sos pack sync <pack> --runtime-root <path> --apply` | 执行有效的 pack sync 计划。 | 是 |
| `sos changes --root <path> --runtime-root <path> --codex-config <path>` | 报告新增、缺失、变化、过期或意外启用的 skills 和 pointers。 | 否 |
| `sos recommend context --workspace-root <path> --runtime-root <path>` | 查看 workspace 推荐上下文。 | 否 |
| `sos recommend activation-plan [--host {codex,claude}] --workspace-root <path> --runtime-root <path> --packs <ids> --out <path>` | 写出 workspace activation plan。 | 只写计划文件 |
| `sos recommend activate [--host {codex,claude}] --plan <path> --workspace-root <path> --runtime-root <path>` | 预览 workspace activation。 | 否 |
| `sos recommend activate [--host {codex,claude}] --plan <path> --workspace-root <path> --runtime-root <path> --apply` | 写入 workspace skills 和 learned-reference stub。 | 是 |
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

---

## 许可证

本项目采用 [MIT 许可证](LICENSE)。

---

> **友情提示**：
> “如果你不想在 debug 某个简单的脚本时，AI 突然自作聪明地用你半年前写废了的部署技能把服务器搞炸，我建议你现在就去跑一次 `sos propose`。
> 至于春日如果抱怨指针没有把她的全文展示出来……别理她，有长门和朝比奈在后台盯着，出不了乱子。”
