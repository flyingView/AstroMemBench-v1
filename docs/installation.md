# Installation / 安装

[English](#english) · [简体中文](#简体中文)

## English

[Home](../README.md) · [Next: quick start](quickstart.md)

### Set up Python

Use Python 3.11 or later and a separate virtual environment. The benchmark runner does not require a GPU or a hosted model account. Requirements for your own model, agent framework, or memory service belong to your adapter.

If your system provides `python3` instead of `python`, use `python3` for extraction and environment creation below. After activating the environment, `python` points to its interpreter.

Download **[astromembench-1.0.1.zip](https://github.com/flyingView/AstroMemBench-v1/releases/download/v1.0.1/astromembench-1.0.1.zip)** from [Release v1.0.1](https://github.com/flyingView/AstroMemBench-v1/releases/tag/v1.0.1). It includes the source code, guides, example adapter, and complete benchmark. Extract it and enter the resulting directory:

```bash
python -m zipfile -e astromembench-1.0.1.zip .
cd astromembench-1.0.1
python -m venv .venv
```

Activate the environment on Linux or macOS:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

If your shell does not allow activation scripts, use the virtual environment's Python executable directly, for example `.\.venv\Scripts\python.exe -m pip install -e .` on Windows.

Install the package from this directory:

```bash
python -m pip install -e .
astromembench --help
```

Commands in these guides assume that the package directory is the current directory and the virtual environment is active. You can also use `python -m astromembench` in place of `astromembench`. The complete package already contains `data/benchmark/tasks.jsonl`; continue to [verification](#verify-the-installation-and-data).

### Download the benchmark

This is the alternative for developers using Git. Skip it if you downloaded the complete package above.

```bash
git clone https://github.com/flyingView/AstroMemBench-v1.git
cd AstroMemBench-v1
python -m venv .venv
```

Activate the environment and install with `python -m pip install -e .`, as above. Then download **[astromembench-benchmark-v1.0.1.zip](https://github.com/flyingView/AstroMemBench-v1/releases/download/v1.0.1/astromembench-benchmark-v1.0.1.zip)** from the release, place it in the repository root, and extract it there:

```bash
python -m zipfile -e astromembench-benchmark-v1.0.1.zip .
```

This data-only archive includes its `data/benchmark/` directory. Do not extract it into another `data/benchmark/` directory, which would create a nested path. GitHub's automatically generated source ZIP and tarball contain code only; they are different from the complete package named `astromembench-1.0.1.zip`.

```text
AstroMemBench-v1/
├── pyproject.toml
├── src/
├── examples/
└── data/
    └── benchmark/
        ├── manifest.json
        ├── index.json
        ├── tasks.jsonl
        └── assets/
```

The task file is kept outside Git. It is 788,488,913 bytes, approximately 752 MiB, before compression. Keep the extracted data on a local disk with enough space for the archive, extracted files, and your own run outputs. The data is ready to use; no tokenizer download or task generation is required.

### Verify the installation and data

```bash
astromembench validate --data data/benchmark
astromembench list --data data/benchmark --limit 5
```

Validation checks the released data before you spend time running an adapter. Continue with the [one-case quick start](quickstart.md).

### Open the browser interface

From the repository root:

```bash
python scripts/start_webui.py
```

On Windows, you can instead double-click **Start AstroMemBench.cmd**. This launcher uses the repository's `.venv` created above and opens the interface in your default browser. Complete package installation and dataset extraction first.

The launcher selects an available local port. Keep its terminal open while using the interface. Ctrl+C stops the HTTP server; independent experiment workers continue until paused, stopped or finished. Reopen with the same `--workspace` to reconnect. See [the workbench guide](workbench.md). For an explicit host and port, use:

```bash
astromembench webui --data data/benchmark --host 127.0.0.1 --port 8765
```

If that port is occupied, use `--port 0` to let the operating system choose an available port. The browser opens the selected address automatically.

### Troubleshooting

| Symptom | Check |
| --- | --- |
| `astromembench` is not found | Activate the virtual environment, or use `python -m astromembench`. |
| A task file cannot be found | Confirm that `data/benchmark/tasks.jsonl` exists and that `--data` points to its containing directory. |
| The downloaded ZIP has no task files | Use the complete `astromembench-1.0.1.zip` package, or add the data-only asset to your source checkout. |
| An image cannot be loaded | Extract the complete benchmark asset, preserving its directory layout, then rerun validation. |
| Your adapter cannot import its dependencies | Install them in the Python environment used by its `argv` command. `${PYTHON}` selects the runner's Python executable. |
| Your adapter cannot find a credential | Add the environment variable name to `pass_env`; see [adapter configuration](adapters.md#adapter-configuration). |

For a reproducible evaluation, keep the release data intact and record the code version, data version, adapter configuration, and model or memory-system version with your results.

---

## 简体中文

[首页](../README.md#简体中文) · [下一步：快速开始](quickstart.md#简体中文)

### 设置 Python 环境

使用 Python 3.11 或更高版本，并创建独立的虚拟环境。基准运行器不需要 GPU 或托管模型账号；你自己的模型、智能体框架或记忆服务所需的依赖由适配器管理。

如果系统提供的是 `python3` 而不是 `python`，请在下面的解压和创建环境步骤中使用 `python3`。激活虚拟环境后，`python` 会指向该环境的解释器。

从 [v1.0.1 Release](https://github.com/flyingView/AstroMemBench-v1/releases/tag/v1.0.1) 下载 **[astromembench-1.0.1.zip](https://github.com/flyingView/AstroMemBench-v1/releases/download/v1.0.1/astromembench-1.0.1.zip)**。完整包包含源代码、指南、示例适配器和全部题库。解压后进入项目目录：

```bash
python -m zipfile -e astromembench-1.0.1.zip .
cd astromembench-1.0.1
python -m venv .venv
```

Linux 或 macOS 激活环境：

```bash
source .venv/bin/activate
```

Windows PowerShell 激活环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

如果终端不允许执行激活脚本，可以直接使用虚拟环境中的 Python。例如在 Windows 上运行 `.\.venv\Scripts\python.exe -m pip install -e .`。

在项目目录中安装：

```bash
python -m pip install -e .
astromembench --help
```

本指南中的命令都假定当前目录是项目目录，且虚拟环境已激活。也可以用 `python -m astromembench` 代替 `astromembench`。完整包已包含 `data/benchmark/tasks.jsonl`，可以直接进入[校验步骤](#校验安装与数据)。

### 下载题库

以下是通过 Git 获取代码时的替代安装方式。已经下载完整包的用户可以跳过。

```bash
git clone https://github.com/flyingView/AstroMemBench-v1.git
cd AstroMemBench-v1
python -m venv .venv
```

按上文激活环境，再运行 `python -m pip install -e .`。随后从 Release 下载 **[astromembench-benchmark-v1.0.1.zip](https://github.com/flyingView/AstroMemBench-v1/releases/download/v1.0.1/astromembench-benchmark-v1.0.1.zip)**，放在仓库根目录并在此处解压：

```bash
python -m zipfile -e astromembench-benchmark-v1.0.1.zip .
```

题库包内已经带有 `data/benchmark/` 目录。请直接解压到仓库根目录，避免在另一个 `data/benchmark/` 目录中解压而产生嵌套路径。GitHub 自动生成的源代码 ZIP 和 tarball 只提供代码，与名为 `astromembench-1.0.1.zip` 的完整包不同。

```text
AstroMemBench-v1/
├── pyproject.toml
├── src/
├── examples/
└── data/
    └── benchmark/
        ├── manifest.json
        ├── index.json
        ├── tasks.jsonl
        └── assets/
```

题目文件通过 Release 分发，不存入 Git。未压缩时为 788,488,913 字节，约 752 MiB。请将解压后的数据保存在本地磁盘，并为压缩包、解压文件和自己的评测输出预留空间。题库可以直接使用，无需下载分词器或生成题目。

### 校验安装与数据

```bash
astromembench validate --data data/benchmark
astromembench list --data data/benchmark --limit 5
```

校验会先检查发布数据，再开始耗时的适配器运行。通过后继续[单题快速开始](quickstart.md#简体中文)。

### 打开浏览器界面

在仓库根目录运行：

```bash
python scripts/start_webui.py
```

Windows 用户也可以双击 **Start AstroMemBench.cmd**。启动器使用前面在项目内创建的 `.venv`，并在默认浏览器中打开界面。请先完成安装和题库解压。

启动器会选择空闲的本地端口。使用界面时保持终端开启；Ctrl+C 只停止 HTTP 服务，独立实验进程会继续运行，直到暂停、停止或完成。重开时使用相同 `--workspace` 即可重新连接，详见[工作台指南](workbench.md#简体中文)。如果需要指定地址和端口，运行：

```bash
astromembench webui --data data/benchmark --host 127.0.0.1 --port 8765
```

如果端口已被占用，使用 `--port 0`，由操作系统分配空闲端口。浏览器会自动打开对应地址。

### 常见问题

| 问题 | 检查方法 |
| --- | --- |
| 找不到 `astromembench` 命令 | 激活虚拟环境，或使用 `python -m astromembench`。 |
| 找不到题目文件 | 确认 `data/benchmark/tasks.jsonl` 存在，且 `--data` 指向它所在的目录。 |
| 下载的 ZIP 没有题目文件 | 使用完整包 `astromembench-1.0.1.zip`，或在代码仓库中补充解压题库包。 |
| 图片无法加载 | 完整解压题库资源，保留目录结构，再次运行校验。 |
| 适配器无法导入依赖 | 在 `argv` 指定的 Python 环境中安装依赖。`${PYTHON}` 表示运行基准的 Python 解释器。 |
| 适配器找不到凭证 | 将环境变量名加入 `pass_env`，详见[适配器配置](adapters.md#适配器配置)。 |

为便于复现，请保持发布数据完整，并在结果中记录代码版本、数据版本、适配器配置，以及模型或记忆系统的版本。
