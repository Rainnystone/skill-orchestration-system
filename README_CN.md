# Skill Orchestration System

[English](README.md) | [中文](README_CN.md)

你的 agent skills 应该像一套顺手的工具箱，而不是第二个杂物抽屉。

Skill Orchestration System，简称 SOS，是一个面向 Codex 用户的本地 skill
整理系统。它可以把越来越多的本地 agent skills 整理成更小、更清楚、可审查、可激活、可回滚的技能包。它会先写计划，再写文件；先做 dry run，再真正 apply；先备份，再修改。

当前 SOS 是 Codex-first。Claude Code 的兼容性只保留结构口子，还没有接入专用安装器、settings 写入器或集成测试。

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
- `src/sos/` 里的 **Python CLI backend**，负责确定性的扫描、计划、写入、同步、备份和恢复。

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

**macOS / Linux:**

```bash
PYTHONPATH=src python -m sos --version
```

**Windows PowerShell:**

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

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m sos --version
```

**Windows PowerShell:**

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

## 安全模型

SOS 默认很保守。

- `scan` 和 `propose` 不写入；
- `plan` 只写指定的计划文件；
- 不带 `--apply` 的 `apply` 只是 dry run；
- `apply --apply` 会先创建备份，再执行受管理的写入；
- 源 skill 删除默认关闭，需要同时提供 `--delete-source`、`--apply` 和
  `--confirm-delete-source <pack-id>`；
- restore 和 backup cleanup 默认也是 dry run，只有加上 `--apply` 才会写入。

运行任何会写文件的命令前，都应该先看计划。如果不确定，就再跑一次 dry run。

## SOS 会生成什么

当你确认并 apply 一个计划后，SOS 会把生成出来的 active skills 写入你选择的 skill root。生成入口会保持很短：

- `sos-haruhi`：用于 pack 管理、状态查看、备份和恢复的 companion skill；
- `sos-<pack>`：每个技能包对应一个 pointer skill。

pointer skill 不会塞入原始 `SKILL.md` 全文。它会指向 pack manifest 和受管理的 vault 副本。这样 active 层保持轻，详细内容留在该在的地方。

## 它是怎么工作的

```text
.
|-- .agents/skills/sos/     # 面向 Codex 的 SOS skill wrapper
|-- references/             # 公开行为和安全说明
|-- src/sos/                # CLI 和库实现
|   |-- cli.py              # 命令行入口
|   |-- scanner.py          # SKILL.md 发现
|   |-- propose.py          # 技能包建议规则
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
- `packs/` 保存 TOML pack manifests；
- `state/` 保存 registry 状态；
- `backups/` 保存写入前创建的 config 和 vault 快照。

## CLI 参考

| 命令 | 用途 | 默认是否写入 |
| --- | --- | --- |
| `sos scan --root <path> [--codex-config <path>]` | 列出某个目录下已启用的 skills。 | 否 |
| `sos propose --root <path>` | 根据扫描结果提出技能包候选。 | 否 |
| `sos plan --root <path> --runtime-root <path> --codex-config <path> --out <path>` | 写出可审查的计划文件。 | 只写计划文件 |
| `sos apply --plan <path>` | 汇总计划内容，做 dry run。 | 否 |
| `sos apply --plan <path> --apply` | 复制 skills、写 manifest 和 pointer、禁用原入口并创建备份。 | 是 |
| `sos pack activate <pack> --runtime-root <path>` | 激活技能包，并在符合条件时执行 clean sync。 | 可能 |
| `sos pack sync <pack> --runtime-root <path>` | 展示技能包同步计划。 | 否 |
| `sos pack sync <pack> --runtime-root <path> --apply` | 执行有效的技能包同步计划。 | 是 |
| `sos status --runtime-root <path>` | 查看 runtime registry 和备份状态。 | 否 |
| `sos backup list --runtime-root <path>` | 列出备份。 | 否 |
| `sos backup clean --runtime-root <path> --keep <count>` | 预览备份清理。 | 否 |
| `sos backup clean --runtime-root <path> --keep <count> --apply` | 清理旧备份。 | 是 |
| `sos restore <backup-id> --runtime-root <path>` | 预览恢复目标。 | 否 |
| `sos restore <backup-id> --runtime-root <path> --apply` | 恢复备份记录中的 config 和 vault 目标。 | 是 |

## 兼容性

SOS 当前是 Codex-first。经过测试的写入路径可以在创建备份后更新 Codex skill 配置，并且只有显式传入 `--apply` 时才会写入。

Claude Code 兼容性目前只是结构层面的：生成的 skills 是普通 `SKILL.md` 文件夹，pack 元数据是普通 TOML manifest。SOS 还没有 Claude Code 专用安装器、settings 写入器或集成测试。

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
