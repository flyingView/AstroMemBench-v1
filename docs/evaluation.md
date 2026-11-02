# Evaluation / 评测

[English](#english) · [简体中文](#简体中文)

## English

[Home](../README.md) · [Adapters](adapters.md) · [Dataset](dataset.md)

### Select a condition

All runs use the complete released history. Choose how the conversation continues after the 30 history rounds.

| Setting | Meaning |
| --- | --- |
| `--mode same_session` | The history and current task share a conversation |
| `--mode new_session` | A fresh conversation starts after the history, retaining the subject's persistent memory |

Every case starts with a subject reset and receives 30 history rounds. The task environment then requests actions until it reaches a terminal state. Score the conditions separately and use the same case set for comparisons.

### Run a case or the full benchmark

Start with a single case:

```bash
astromembench run --data data/benchmark --adapter my-adapter.json --output runs/my-system-check --case FM-C1-P1-001 --mode same_session
```

After checking the protocol trace and result, run all cases:

```bash
astromembench run --data data/benchmark --adapter my-adapter.json --output runs/my-system-new-session --mode new_session
```

Omitting `--case` selects all 2,240 cases. Repeat `--case` to select an explicit subset. Use a separate output directory for each adapter configuration and session mode.

```bash
astromembench summarize runs/my-system-new-session
```

### Scores and coverage

The environment scores the actual action trajectory and terminal state using the task's rubric. Scores lie between 0 and 100, with higher scores indicating better task performance. `full_credit` is true for a score of 100. Task-specific validity, progress, safety, and resource constraints determine the outcome; the evaluator does not use an external language-model judge.

The summary distinguishes scored outcomes from failures that prevent evaluation:

| Summary field | Meaning |
| --- | --- |
| `total` | Number of selected cases |
| `finished` | Cases with a score or an unsupported result |
| `scored` | Cases with a numeric outcome score, including zero scores |
| `unsupported` | Cases the subject cannot support |
| `failed` | Cases with unscored failures |
| `interrupted` | Cases interrupted before a scored outcome |
| `pending` | Cases awaiting execution |
| `mean_score` | Arithmetic mean over the `scored` cases only |
| `full_credit_count` | Number of scored cases receiving full credit |
| `status` | Overall run state |
| `cases` | Case-level summary records |

Report `scored / total` alongside `mean_score`, plus unsupported and failed counts. Unsupported cases, infrastructure failures, and interruptions are excluded from the mean. A mean over a subset is therefore not directly comparable to a mean over all 2,240 cases.

An overall `completed` status means every selected case has a score or an unsupported result. Check `scored` and `unsupported` to determine coverage.

A subject's incorrect or invalid action can lead to a scored failure under the environment's rules. A missing service or broken transport is an execution problem and is recorded separately. If a terminal score has already been determined, a later feedback or cleanup warning does not erase that score.

A subject failure that ends a case has status `agent_error` in v1.0.1. All v1 releases score incomplete history at zero and retain any task progress earned before a terminal memory failure. These scores count toward the mean and coverage and are skipped on resume. A missing or malformed action during action selection uses the task's action budget. v1.0.0 stored scored subject failures as `completed` with `outcome.termination=agent_failure`.

### Outputs

The `--output` directory contains the run definition, progress, summary, and per-case attempts. Each attempt keeps its own records so that an explicit retry does not overwrite the previous attempt's trace.

The main files to inspect are:

| File | Use |
| --- | --- |
| `run.json` | Run definition, adapter configuration, selected cases, and data/code identity |
| `summary.json` | Current aggregate and case-level status records |
| `cases/<case-id>/result.json` | The case's saved outcome and status |
| `cases/<case-id>/attempts/0001/result.json` | Outcome, errors, and completion metadata for one attempt |
| `cases/<case-id>/attempts/0001/events.jsonl` | The sequence of public requests and adapter replies |
| `cases/<case-id>/attempts/0001/workspace/adapter.log` | Standard-error diagnostics from the adapter process |

Use `astromembench summarize <output-directory>` to read the current aggregate. The local web interface can also launch runs, display progress, cancel a run, and inspect results:

```bash
python scripts/start_webui.py
```

The launcher opens the local interface in your browser. On Windows, double-click **Start AstroMemBench.cmd** as an alternative. The [workbench](workbench.md) saves named groups and independent background experiments in `runs/workbench` by default; use `--workspace` to choose another directory. It uses the same evaluator as the CLI and can open inactive CLI result directories for read-only inspection.

Run outputs are local artifacts from your own evaluation. They may contain the text and images delivered to your system and its responses. Review them before sharing.

### Resume a run

The runner does not automatically rerun a case to improve its score. To continue an interrupted run or retry an unscored execution failure, repeat the same command with `--resume`:

```bash
astromembench run --data data/benchmark --adapter my-adapter.json --output runs/my-system-new-session --mode new_session --resume
```

Resuming skips cases that already have a score and cases already marked unsupported. Unfinished or infrastructure-failed cases receive a new attempt directory; earlier records remain available. Keep the original condition and adapter configuration unchanged. For a changed system or a deliberate repeated measurement, create a new run directory.

### Reporting results

Include enough information for another user to reproduce the condition:

- Code release and benchmark data identity.
- Full case set or explicit subset, including scored coverage.
- Session mode.
- Model or agent version, memory implementation, and adapter version.
- Prompt and generation settings that affect behavior.
- Mean score, full-credit count, unsupported cases, and execution failures.
- Any resume attempts used to recover unscored execution failures.

Keep the released task files and scoring rules unchanged when reporting results for this benchmark version.

---

## 简体中文

[首页](../README.md#简体中文) · [适配器](adapters.md#简体中文) · [题库](dataset.md#简体中文)

### 选择会话条件

所有运行都使用发布版的完整历史。下面的设置决定 30 轮历史结束后如何继续会话。

| 设置 | 含义 |
| --- | --- |
| `--mode same_session` | 历史输入与当前任务使用同一个会话 |
| `--mode new_session` | 历史结束后创建新会话，保留被测系统的持久记忆 |

每道题都会先重置被测系统，再发送 30 轮历史。之后，任务环境持续请求动作，直到进入终局。两种条件应分别统计分数，比较时使用相同的题目集合。

### 运行单题或完整题库

先运行一道题：

```bash
astromembench run --data data/benchmark --adapter my-adapter.json --output runs/my-system-check --case FM-C1-P1-001 --mode same_session
```

检查协议轨迹和结果后，再运行全部题目：

```bash
astromembench run --data data/benchmark --adapter my-adapter.json --output runs/my-system-new-session --mode new_session
```

不传入 `--case` 就会选择全部 2,240 道题。重复传入 `--case` 可以明确选择一个子集。不同的适配器配置和会话模式应使用不同的输出目录。

```bash
astromembench summarize runs/my-system-new-session
```

### 分数与覆盖率

环境根据题目评分规则，对实际动作轨迹和终局状态评分。分数范围是 0 到 100，越高表示任务完成得越好；得分为 100 时，`full_credit` 为 true。具体题目的有效性、进度、安全和资源约束共同决定结果，评测器不使用外部语言模型裁判。

汇总会区分已计分结果与导致无法评测的失败：

| 汇总字段 | 含义 |
| --- | --- |
| `total` | 所选题目总数 |
| `finished` | 已产生分数或标记为不支持的题目数 |
| `scored` | 有数值得分的题目数，包括零分 |
| `unsupported` | 被测系统不支持的题目数 |
| `failed` | 发生失败且尚未计分的题目数 |
| `interrupted` | 产生分数前被中断的题目数 |
| `pending` | 等待执行的题目数 |
| `mean_score` | 仅对 `scored` 题目计算的算术平均分 |
| `full_credit_count` | 已计分题目中获得满分的数量 |
| `status` | 整体运行状态 |
| `cases` | 每道题的汇总记录 |

报告 `mean_score` 时，同时提供 `scored / total`、不支持数量和失败数量。不支持、基础设施故障和中断均不计入平均分，因此，子集均分不能直接与完整 2,240 道题的均分比较。

整体状态为 `completed`，表示每道所选题目都已经产生分数或不支持结果。请结合 `scored` 和 `unsupported` 判断实际覆盖范围。

被测系统提交错误或无效动作后，环境可以按规则给出已计分的失败结果。服务不可用或传输故障属于执行问题，会另外记录。如果已经确定终局分数，后续反馈处理或清理警告不会抹去该分数。

v1.0.1 将导致题目终止的智能体错误标为 `agent_error`。所有 v1 版本对未完成的历史处理记零分，对执行中途的记忆维护失败保留当时已取得的任务分数。这些分数计入均分和覆盖率，恢复时跳过。选择动作时，缺失或格式错误的动作会消耗该题的动作次数。v1.0.0 将这类已计分失败保存为 `completed`，其 `outcome.termination` 为 `agent_failure`。

### 输出文件

`--output` 目录保存运行定义、进度、汇总和每道题的各次尝试。每次尝试单独保存，显式重试不会覆盖此前的交互记录。

主要文件如下：

| 文件 | 用途 |
| --- | --- |
| `run.json` | 运行定义、适配器配置、所选题目及数据与代码标识 |
| `summary.json` | 当前汇总与各题状态记录 |
| `cases/<case-id>/result.json` | 该题保存的结果与状态 |
| `cases/<case-id>/attempts/0001/result.json` | 一次尝试的结果、错误和完成元数据 |
| `cases/<case-id>/attempts/0001/events.jsonl` | 公开请求与适配器回复序列 |
| `cases/<case-id>/attempts/0001/workspace/adapter.log` | 适配器进程的标准错误诊断信息 |

使用 `astromembench summarize <output-directory>` 读取当前汇总。本地浏览器界面也可以启动运行、查看进度、取消运行和检查结果：

```bash
python scripts/start_webui.py
```

启动器会在浏览器中打开本地界面。Windows 用户也可以双击 **Start AstroMemBench.cmd**。[工作台](workbench.md#简体中文)支持命名分组与独立后台实验，默认保存于 `runs/workbench`，可通过 `--workspace` 更改。浏览器与 CLI 使用相同评测器，也可只读打开未运行中的 CLI 结果目录。

运行输出是用户自己评测时产生的本地文件，可能包含交给系统的文本、图片及其回复。分享前请检查内容。

### 恢复运行

运行器不会为了提高分数自动重跑题目。如果需要继续被中断的运行，或重试尚未计分的执行失败，使用原命令并加上 `--resume`：

```bash
astromembench run --data data/benchmark --adapter my-adapter.json --output runs/my-system-new-session --mode new_session --resume
```

恢复时会跳过已产生分数和已标记为不支持的题目。未完成或发生基础设施故障的题目会使用新的尝试目录，之前的记录仍然保留。请保持原来的会话条件和适配器配置。如果更换了系统，或需要有意重复测量，应创建新的运行目录。

### 报告结果

请提供足够的信息，方便其他用户复现评测条件：

- 代码发布版本和题库数据标识。
- 完整题目集合或明确的子集，包括实际计分覆盖率。
- 会话模式。
- 模型或智能体版本、记忆实现和适配器版本。
- 会影响行为的提示词与生成设置。
- 平均分、满分题数、不支持题数和执行失败数量。
- 用于恢复未计分执行失败的续跑尝试。

报告本版本基准的结果时，请保持发布题目和评分规则不变。
