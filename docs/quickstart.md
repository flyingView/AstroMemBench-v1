# Quick start / 快速开始

[English](#english) · [简体中文](#简体中文)

## English

[Home](../README.md) · [Installation](installation.md) · [Adapters](adapters.md)

This walkthrough uses the included random-action adapter. It checks the complete path from history delivery to result files without calling a model service.

### 1. Check the data

Install the [complete release package](installation.md), then run:

```bash
astromembench validate --data data/benchmark
astromembench list --data data/benchmark --limit 5
```

The release contains 2,240 cases. IDs identify a template and a three-digit instance number; for example, `FM-C1-P1-001` belongs to template `FM-C1-P1`.

### 2. Run one case

```bash
astromembench run --data data/benchmark --adapter examples/random-adapter.json --output runs/quickstart --case FM-C1-P1-001 --mode same_session
```

The runner starts [the example adapter](../examples/random_adapter.py), resets its state, opens a conversation, delivers all 30 history rounds, and requests actions until the task ends. This example stays in the same conversation after reading the history.

The adapter samples the action entries offered in each observation. Its choices can succeed or fail; the score is not an installation check. Confirm that the run finishes and writes a result, then inspect the summary:

```bash
astromembench summarize runs/quickstart
```

Use a new output directory for each distinct configuration. See [evaluation outputs](evaluation.md#outputs) for the files and status fields.

### 3. Try the session boundary

```bash
astromembench run --data data/benchmark --adapter examples/random-adapter.json --output runs/quickstart-new-session --case FM-C1-P1-001 --mode new_session
```

`new_session` opens a second conversation after the history. An adapter should keep the system's persistent memory while clearing its conversation transcript. This tests the integration boundary; the random-action example does not implement a memory system.

### 4. Select cases and inspect tasks

List a specific template:

```bash
astromembench list --data data/benchmark --template FM-C1-P1 --limit 16
```

Pass `--case` more than once to run a selected set:

```bash
astromembench run --data data/benchmark --adapter examples/random-adapter.json --output runs/two-cases --case FM-C1-P1-001 --case FM-C1-P1-002 --mode same_session
```

Launch the local interface and open it in your browser:

```bash
python scripts/start_webui.py
```

The launcher chooses an available local port and opens the browser. On Windows, double-clicking **Start AstroMemBench.cmd** opens the same interface. Import the example JSON in **Adapters**, create an experiment, choose one case and a session mode, then run it. The workbench saves results under `runs/workbench` by default. Ctrl+C stops the HTTP server; background experiments continue. Use Pause or Stop to control the experiment itself, and reopen the same workspace to reconnect. See [workbench controls and interfaces](workbench.md).

### 5. Connect your system

Start with [the example adapter configuration](../examples/random-adapter.json) and the [protocol guide](adapters.md). Your adapter translates public requests into your system's native operations; the runner maintains task state and scores the outcome.

After a successful one-case integration check, remove `--case` to run the full benchmark. Report `same_session` and `new_session` as separate conditions. Every run uses the complete released history, including background material.

---

## 简体中文

[首页](../README.md#简体中文) · [安装](installation.md#简体中文) · [适配器](adapters.md#简体中文)

本指南使用随项目提供的随机动作适配器，不调用模型服务，检查从历史输入到结果文件的完整运行流程。

### 1. 检查数据

安装[完整发布包](installation.md#简体中文)，然后运行：

```bash
astromembench validate --data data/benchmark
astromembench list --data data/benchmark --limit 5
```

发布版包含 2,240 道题。题号由模板编号和三位实例编号组成，例如 `FM-C1-P1-001` 属于模板 `FM-C1-P1`。

### 2. 运行一道题

```bash
astromembench run --data data/benchmark --adapter examples/random-adapter.json --output runs/quickstart --case FM-C1-P1-001 --mode same_session
```

运行器会启动[示例适配器](../examples/random_adapter.py)，重置其状态，创建会话，发送全部 30 轮历史，再请求动作直到任务结束。本例在读取历史后继续使用同一个会话。

适配器从每次观测提供的动作项中随机选择。随机选择可能成功，也可能失败；不能用分数判断安装是否正常。先确认任务完成并写出结果，再查看汇总：

```bash
astromembench summarize runs/quickstart
```

不同配置使用不同的输出目录。结果文件和状态字段见[评测输出](evaluation.md#输出文件)。

### 3. 检查会话切换

```bash
astromembench run --data data/benchmark --adapter examples/random-adapter.json --output runs/quickstart-new-session --case FM-C1-P1-001 --mode new_session
```

`new_session` 会在历史结束后创建第二个会话。适配器应清空会话记录，同时保留被测系统的持久记忆。这一步用于检查接入时的会话边界；随机动作示例本身不实现记忆系统。

### 4. 选择题目与查看任务

列出一个模板的题目：

```bash
astromembench list --data data/benchmark --template FM-C1-P1 --limit 16
```

重复传入 `--case` 可以选择多道题：

```bash
astromembench run --data data/benchmark --adapter examples/random-adapter.json --output runs/two-cases --case FM-C1-P1-001 --case FM-C1-P1-002 --mode same_session
```

启动本地浏览器界面：

```bash
python scripts/start_webui.py
```

启动器会选择空闲的本地端口并打开浏览器。Windows 用户也可以双击 **Start AstroMemBench.cmd**。在「适配器」中导入示例 JSON，新建实验，选择一道题和会话模式后运行。结果默认保存于 `runs/workbench`。Ctrl+C 只停止 HTTP 服务，后台实验继续运行；暂停或停止实验应使用对应控件，重开相同工作目录即可重新连接。详见[工作台控制与接口](workbench.md#简体中文)。

### 5. 接入自己的系统

参照[示例适配器配置](../examples/random-adapter.json)和[协议指南](adapters.md#简体中文)。适配器将公开请求转换为被测系统的原生操作；运行器负责维护任务状态并评分。

完成单题接入检查后，移除 `--case` 即可运行完整题库。`same_session` 和 `new_session` 应作为两种条件分别报告。每次运行都使用发布版的完整历史，包括背景材料。
