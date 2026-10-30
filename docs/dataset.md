# Dataset / 题库

[English](#english) · [简体中文](#简体中文)

## English

[Home](../README.md) · [Installation](installation.md) · [Evaluation](evaluation.md)

### Release contents

The v1.0.0 benchmark contains **2,240 fixed cases from 140 templates**. Each template has 16 cases: 6 easy, 6 medium, and 4 hard. Each case supplies exactly 30 rounds of historical input followed by a current task.

The complete [v1.0.0 release package](https://github.com/flyingView/AstroMemBench-v1/releases/tag/v1.0.0), `astromembench-1.0.0.zip`, includes the dataset under `astromembench-1.0.0/data/benchmark/`. Git users can download the data-only `astromembench-benchmark-v1.0.0.zip` and extract it at the repository root to create `data/benchmark/`.

| File or directory | Purpose |
| --- | --- |
| `tasks.jsonl` | All 2,240 fixed task records with complete prescribed histories |
| `manifest.json` | Release identity and integrity information |
| `index.json` | Case metadata for locating and listing tasks |
| `assets/` | Image files required by the tasks, with provenance information |

These are ready-to-use task definitions. No data generation or tokenizer download is required. `tasks.jsonl` occupies 788,488,913 bytes, approximately 752 MiB, before compression. The archive also contains 22 task images.

### Coverage

The catalog combines mission scenarios with memory-related subchallenges and capability tags.

| Challenge family | Examples of what the agent must retain or revise |
| --- | --- |
| Communication delays | Earlier requirements, out-of-order revisions, delivery confirmations |
| Time-critical operations | Validity periods and future obligations |
| Environmental uncertainty | Prior experience, changed conditions, environmental landmarks |
| Complex physical interactions | Connections, operation state, and accumulated effects |
| Power and computational resource constraints | Energy experience, future reservations, reusable computations |
| Safety and reliability | Safety prerequisites, changed capabilities, recovery progress |

The nine mission scenarios are regional surveying, site-specific sampling, cargo transport, target inspection, equipment maintenance, on-orbit resupply, cruise support, scientific observation, and data downlink. They span planetary surface, on-orbit servicing, and deep-space spacecraft settings.

Ten capability tags describe perceptual interpretation, spatial navigation, observation acquisition, mechanical manipulation, operational regulation, equipment configuration, data processing, communication and transmission, task planning, and resource allocation. Tags describe coverage; they do not imply that every case exercises every tagged capability equally.

Task content is primarily Chinese. Images are part of the input for some cases and must be passed to a capable subject when evaluating those cases.

### History

Each case includes the complete prescribed history: 30 rounds with task-relevant records and background material. The subject must process them in sequence and retain the information it needs for the current task. The evaluator's background/evidence classification is not included in messages sent to the subject.

### Task records and visibility

Each nonempty line of a task JSONL file is one JSON object.

| Field | Role |
| --- | --- |
| `case_id` | Stable case identifier, for example `FM-C1-P1-001` |
| `template` | Template identifier, for example `FM-C1-P1` |
| `difficulty` | `easy`, `medium`, or `hard` |
| `history` | Thirty ordered historical events |
| `public` | Information used to construct current task observations |
| `initial` | Initial environment state |
| `world` | Environment facts and transition data |
| `rubric` | Scoring rules |
| `design` | Evaluator-side construction and classification metadata |
| `schema_version` | Identifier of the task serialization format |

The task file is an evaluator input. It contains private state and scoring information, so it should not be given directly to a model or memory system. The runner constructs public history and observations, removes evaluator-only fields, and supplies image bytes through the adapter protocol. Integrate against those protocol messages rather than loading task records inside your adapter.

A history message contains reception and occurrence times, a channel, and public records. Reception order is preserved even when the events described in the records occurred in a different order. Historical actions describe the past and must not be executed again.

### Integrity and versions

```bash
astromembench validate --data data/benchmark
```

Keep the released task files unchanged. Use the manifest and validation output to identify the dataset associated with a result. A software release version identifies the distribution; serialization identifiers identify file formats and are separate from the software version.

When sharing scores, state the release, selected case IDs or full-set size, session mode, and subject configuration. An evaluation on a subset should identify that subset explicitly.

### Licenses and image attribution

The [MIT License](../LICENSE) covers the source code, original task definitions, and synthetic histories. It does not relicense third-party images.

The benchmark archive records image sources and credits in `data/benchmark/assets/sources.json`. Retain these attributions when redistributing the images and follow the terms stated by their original sources.

---

## 简体中文

[首页](../README.md#简体中文) · [安装](installation.md#简体中文) · [评测](evaluation.md#简体中文)

### 发布内容

v1.0.0 题库包含 **140 个模板，共 2,240 道固定测试题**。每个模板有 16 道题，其中简单 6 道、中等 6 道、困难 4 道。每题先提供恰好 30 轮历史输入，再给出当前任务。

[完整发布包](https://github.com/flyingView/AstroMemBench-v1/releases/tag/v1.0.0) `astromembench-1.0.0.zip` 已将题库存放在 `astromembench-1.0.0/data/benchmark/` 中。通过 Git 获取代码的用户可以下载题库包 `astromembench-benchmark-v1.0.0.zip`，在仓库根目录解压，得到 `data/benchmark/`。

| 文件或目录 | 用途 |
| --- | --- |
| `tasks.jsonl` | 全部 2,240 道固定题目及其完整规定历史 |
| `manifest.json` | 发布标识与完整性信息 |
| `index.json` | 用于定位和列出题目的元数据 |
| `assets/` | 题目所需的图片及来源信息 |

这些题目定义可以直接使用，无需生成数据或下载分词器。`tasks.jsonl` 未压缩时为 788,488,913 字节，约 752 MiB。压缩包还包含 22 张题目图片。

### 覆盖范围

题库将场景任务、记忆子挑战和技能标签关联起来。

| 挑战类别 | 需要保留或修订的信息示例 |
| --- | --- |
| 通信时延 | 已有要求、乱序修订、交付确认 |
| 时间关键操作 | 有效期、未来义务 |
| 环境不确定性 | 既有经验、环境变化、环境地标 |
| 复杂物理交互 | 连接关系、操作状态、累积效应 |
| 功率与计算资源约束 | 能耗经验、后续资源预留、计算结果复用 |
| 安全与可靠性 | 安全前提、能力变化、恢复进度 |

九项场景任务分别是区域勘察、定点采样、物资转运、目标巡检、设备维修、在轨补给、巡航保障、科学观测和数据回传，覆盖星表作业、在轨服务与深空探索三类航天器场景。

十项技能标签分别描述感知判读、空间导航、观测采集、机械操作、运行调控、设备配置、数据处理、通信传输、任务规划和资源分配。标签用于描述覆盖范围，不表示每道题都会同等程度地涉及所有关联技能。

题目以中文为主。部分题目的输入包含图片，评测这些题目时，需要将图片传给支持该模态的被测系统。

### 历史输入

每题包含完整的规定历史：30 轮输入，混合任务相关记录与背景材料。被测系统需要按顺序处理，并保留当前任务所需的信息。评测器使用的背景与证据分类不会出现在发送给被测系统的消息中。

### 题目记录与可见范围

JSONL 文件中的每个非空行都是一个 JSON 对象。

| 字段 | 用途 |
| --- | --- |
| `case_id` | 稳定的题号，例如 `FM-C1-P1-001` |
| `template` | 模板编号，例如 `FM-C1-P1` |
| `difficulty` | `easy`、`medium` 或 `hard` |
| `history` | 三十轮有序历史事件 |
| `public` | 用于构造当前任务观测的信息 |
| `initial` | 环境初始状态 |
| `world` | 环境事实与状态转移数据 |
| `rubric` | 评分规则 |
| `design` | 评测器使用的题目构造与分类元数据 |
| `schema_version` | 题目序列化格式标识 |

题目文件供评测器读取，其中含有环境内部状态和评分信息，不应直接交给模型或记忆系统。运行器会构造公开历史与观测，移除仅供评测器使用的字段，并通过适配器协议提供图片字节。接入时应使用这些协议消息，不要让适配器自行加载题目记录。

每条历史消息包含接收时间、发生时间、通道和公开记录。即使记录描述的事件发生顺序不同，接收顺序仍保持不变。历史中的动作描述过去已经发生的事情，不应再次执行。

### 完整性与版本

```bash
astromembench validate --data data/benchmark
```

保持发布题目文件不变，使用清单和校验输出标识结果对应的数据集。软件发布版本用于标识分发包；序列化标识用于标识文件格式，两者相互独立。

分享分数时，说明发布版本、所选题号或完整题目数量、会话模式和被测系统配置。如果只评测了子集，应明确列出该子集。

### 许可证与图片署名

[MIT 许可证](../LICENSE)覆盖源代码、自编题目内容和合成历史，不会改变第三方图片原有的许可。

题库包在 `data/benchmark/assets/sources.json` 中记录图片来源和署名。重新分发图片时，请保留这些署名，并遵守原始来源规定的条款。
