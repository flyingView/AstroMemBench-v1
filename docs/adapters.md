# Adapter guide / 适配器指南

[English](#english) · [简体中文](#简体中文)

## English

[Home](../README.md) · [Quick start](quickstart.md) · [Evaluation](evaluation.md)

An adapter connects AstroMemBench to your agent, model, or memory system. It can be written in any language that can read UTF-8 JSON lines from standard input and write UTF-8 JSON lines to standard output. It translates the benchmark lifecycle into your system's own operations.

The runner controls the task environment, selects public inputs, executes submitted actions, and calculates scores. The adapter controls model calls, prompt construction, memory storage and retrieval, and conversation management.

### Start from the example

Two files show the complete integration:

- [`examples/random_adapter.py`](../examples/random_adapter.py): a JSONL process that handles all six operations and selects random allowed actions.
- [`examples/random-adapter.json`](../examples/random-adapter.json): its launch configuration.

Run it with the [one-case quick start](quickstart.md). It uses no model or memory service; the example is for checking the protocol.

### Adapter configuration

Supply a JSON file with `--adapter`. A typical custom configuration is:

```json
{
  "name": "my-system",
  "argv": ["${PYTHON}", "my_adapter.py"],
  "config": {},
  "pass_env": ["MY_MODEL_API_KEY"],
  "timeout_s": 600
}
```

| Field | Meaning |
| --- | --- |
| `argv` | Required command and argument array; launched directly, without a shell |
| `name` | Optional display name for the subject |
| `config` | Optional JSON object containing your adapter settings |
| `pass_env` | Optional names of host environment variables to pass to the adapter |
| `credential_env` | Optional host variable whose value is also exposed as `ASTROMEMBENCH_API_KEY` |
| `timeout_s` | Optional wall-clock timeout for a single protocol request; default 7,200 seconds |

`${PYTHON}` expands to the Python executable running the benchmark. Relative file arguments are resolved against the configuration file's directory. Keep your adapter script beside its JSON configuration, or use an absolute path. The adapter's working directory is a per-attempt workspace, so do not depend on the benchmark repository being its current directory.

The runner provides `ASTROMEMBENCH_WORKSPACE`, `ASTROMEMBENCH_CONFIG`, and `ASTROMEMBENCH_OPERATION_TIMEOUT_S`; `ASTROMEMBENCH_CONFIG` is a JSON string containing `config`. Read credentials from the environment and include their variable names in `pass_env`. Alternatively, use `credential_env` when your adapter expects the conventional `ASTROMEMBENCH_API_KEY` name. Install any client libraries required by your system in the environment used by `argv`.

### Transport and envelopes

Each request and reply occupies exactly one line. Flush standard output after every reply. Write diagnostic messages to standard error, which the runner captures in `adapter.log`. Long-lived or detached child services must not inherit the protocol's standard input or output; the adapter is responsible for shutting them down.

Request:

```json
{"protocol":"astromembench/2","id":1,"operation":"reset","payload":{}}
```

Reply:

```json
{"id":1,"result":{"cleared":true}}
```

The reply's integer `id` must match the request. A successful reply contains a JSON object in `result`. An unsuccessful reply contains an `error` object instead; never include both. The protocol identifier describes the wire format and is independent of the software release version. Requests may also carry an `observation` object with evaluator timing metadata outside `payload`; keep this metadata out of the subject's inputs.

Requests are sequential. Finish the requested work before replying; an acknowledgment should mean that the corresponding state change or history processing has completed. Do not write progress bars, logging, or model output directly to standard output.

### Lifecycle

One case follows this sequence:

```text
reset
new_session
history × 30
[new_session, only for mode=new_session]
observe → submit action → environment transition
          repeat until the task ends
feedback
end
```

The evaluator subsequently closes the adapter process. `close` is a host-side cleanup operation, not a seventh JSONL request.

#### `reset`

Clear state from previous cases, including subject-owned persistent memory that could carry answers between cases. Return only after the clear is complete.

Payload: `{}`.

```json
{"id":1,"result":{"cleared":true}}
```

Use a dedicated memory namespace or collection for the evaluation so this operation can clear case state without deleting unrelated user data. Returning `cleared: true` must describe an actual reset.

#### `new_session`

Open a fresh conversation with the instructions supplied in `payload.instructions`. Return a nonempty conversation identifier.

Example reply:

```json
{"id":2,"result":{"conversation_id":"conversation-1"}}
```

The first call follows `reset`. In `new_session` mode, the runner calls this operation again after history delivery and requires a different identifier. At that boundary, clear the active conversation transcript while preserving the persistent memory your system built from history. Let the system's own memory mechanism retrieve what it needs.

`new_session` is distinct from `reset`: it changes the conversation, not the entire subject state. If your system cannot implement this boundary, return an `unsupported` error. A new identifier alone does not create a new conversation.

#### `history`

Read one round of past records. A public history packet includes reception and occurrence times, the channel, and `data.records`. Each record contains text and may contain image attachments.

These are facts about events that have already happened. Your system may write, retrieve, consolidate, or otherwise maintain memory during this operation, but it must not execute historical actions in the current environment.

Example reply:

```json
{"id":3,"result":{"processed":true,"assistant_text":"收到","action_attempted":false}}
```

`processed: true` is required. `assistant_text` and `action_attempted` can describe what happened; the evaluator does not require that every system use the exact acknowledgment text shown above. Wait for any required memory work to finish before acknowledging the packet.

The runner sends all 30 rounds in order. It does not choose memories or build a retrieval index for your system.

#### `observe`

Process the current task observation and submit one action. The observation includes the current action choices and, where needed, an `action_parameters` description for additional fields.

Example reply for a selection action:

```json
{"id":33,"result":{"action_submitted":true,"action":{"action":"select","option":"A"}}}
```

This is a structural example; use an option actually offered in the current observation. Copy the selected entry's `arguments` as the base action object. Add a field only when the current `action_parameters` explicitly declares it, following its type, requiredness, and format. Do not submit descriptions, explanations, or undeclared evidence fields inside the action.

The `action` object is the submitted action itself, with no extra `arguments` or `parameters` wrapper. A prose answer or JSON inside `assistant_text` is not an action submission. Set `action_submitted: true` only when the subject has produced an operational action.

For an agent that uses tool calls, expose a `robot_action` tool to the agent and translate its actual tool call into the reply above. Other systems can implement their native decision interface and return the resulting action object. Keep this translation consistent across cases.

The runner checks and executes the action. Submitting an action does not guarantee that it is valid or successful. Later observations report the evolving public environment state.

#### `feedback`

Process the final environment feedback. The payload includes `stage`, `terminal`, and `observation`. This is a chance for your system to finish processing the outcome; it must not submit a new action.

```json
{"id":34,"result":{"processed":true}}
```

The scored terminal state is determined by the environment. Feedback handling does not turn an unsuccessful task into a successful one.

#### `end`

Finish pending work for the case, flush resources, and prepare for process shutdown. Payload: `{}`.

```json
{"id":35,"result":{"processed":true}}
```

### Images

Image attachments arrive in `images` arrays within public inputs. Each attachment has this shape:

```json
{"id":"I01","mime_type":"image/jpeg","data_base64":"<base64 image bytes>"}
```

The `data_base64` string contains the original image bytes. Pass them through your system's native image interface. IDs are neutral attachment labels; source paths, evaluator annotations, and scoring information are not provided as model inputs.

Do not replace the images with guessed descriptions. If your system cannot handle a required input modality, return `unsupported` and report the resulting coverage with your scores.

### Errors

An error response uses the same request ID:

```json
{"id":33,"error":{"kind":"unsupported","message":"This adapter does not support image input."}}
```

| `kind` | When to use it |
| --- | --- |
| `unsupported` | A required lifecycle operation or input modality is unavailable |
| `agent` | The subject processed the input but failed to produce an operational answer |
| `infrastructure` | A service, transport, or execution failure prevented evaluation |

During `observe`, an `agent` error without a submitted action consumes an action attempt. If memory maintenance itself fails, set `error.failure_phase` to `memory_capture`, `memory_recall`, or `memory_finish_history`. This terminates the case at its current score. An `agent` error during history also terminates the case with a score of zero.

Use accurate failure attribution. A timeout, invalid JSON reply, disconnected process, or mismatched reply ID is a transport failure, not a valid answer. The runner records these separately from scored task outcomes; see [evaluation](evaluation.md#scores-and-coverage).

### Parallel isolation and optional usage

The workbench can run isolated groups concurrently. Set `parallel_safe` only when each adapter process owns a distinct external memory namespace and native sessions. Derive a namespace from the unique `ASTROMEMBENCH_WORKSPACE` or create a fresh identifier. `reset` must clear that case's state only, and `end` must clean up resources owned by that process. Provider routing, credentials, rate limits, model selection, retrieval policies and remote deployment remain your adapter's responsibility. See [workbench contracts](workbench.md).

A successful reply may include an optional `usage` object inside `result`:

```json
{"id":3,"result":{"processed":true,"usage":{"input_tokens":1200,"output_tokens":12,"cached_input_tokens":1000,"model_calls":1}}}
```

Report **deltas for this operation**, including its model or memory-service calls, rather than cumulative conversation counters. The supported fields are `input_tokens`, `output_tokens`, `cached_input_tokens` and `model_calls`, each a nonnegative integer. Omit unknown fields; omit `usage` entirely when unavailable. Cached input is a subset of input tokens, not an additional token total. Invalid usage metadata is ignored with a warning and cannot change a task score. Saved results expose sums of reported deltas and reporting coverage; they do not infer missing tokens or costs.

### Integration checks

Before a full run, verify these behaviors with one case:

1. `reset` isolates cases, including external memory stores.
2. `new_session` creates a real conversation boundary and preserves only the system's intended persistent memory.
3. Every history acknowledgment follows completed processing, and no history record triggers a current action.
4. `observe` submits an action that follows the current action contract.
5. Standard output contains only matching JSONL replies, and standard error contains diagnostics.
6. The subject receives only the public protocol inputs. It does not read task files, scoring rules, private environment state, or evaluator traces.

The adapter process runs locally; the public-message boundary is not an operating-system sandbox. Maintain that boundary in your integration and record your system's prompt, model, memory policy, and relevant generation settings when reporting results.

---

## 简体中文

[首页](../README.md#简体中文) · [快速开始](quickstart.md#简体中文) · [评测](evaluation.md#简体中文)

适配器将 AstroMemBench 接入你自己的智能体、模型或记忆系统。只要能从标准输入读取 UTF-8 JSON 行、向标准输出写入 UTF-8 JSON 行，就可以使用该语言编写适配器。它负责将基准的生命周期操作转换为被测系统自身的操作。

运行器负责任务环境、公开输入的选择、动作执行和评分。适配器负责模型调用、提示词构造、记忆存储与检索，以及会话管理。

### 从示例开始

两个文件展示了完整的接入方式：

- [`examples/random_adapter.py`](../examples/random_adapter.py)：处理全部六个操作的 JSONL 进程，从允许的动作中随机选择。
- [`examples/random-adapter.json`](../examples/random-adapter.json)：示例的启动配置。

按[单题快速开始](quickstart.md#简体中文)运行。示例不使用模型或记忆服务，用于检查协议是否接通。

### 适配器配置

通过 `--adapter` 传入 JSON 文件。自定义配置示例：

```json
{
  "name": "my-system",
  "argv": ["${PYTHON}", "my_adapter.py"],
  "config": {},
  "pass_env": ["MY_MODEL_API_KEY"],
  "timeout_s": 600
}
```

| 字段 | 含义 |
| --- | --- |
| `argv` | 必填，命令及参数数组；直接启动，不经过 shell |
| `name` | 可选，被测系统的显示名称 |
| `config` | 可选，存放适配器设置的 JSON 对象 |
| `pass_env` | 可选，需要传给适配器的宿主环境变量名称 |
| `credential_env` | 可选，指定一个宿主环境变量，其值还会以 `ASTROMEMBENCH_API_KEY` 提供给适配器 |
| `timeout_s` | 可选，单次协议请求的实际时间上限；默认 7,200 秒 |

`${PYTHON}` 会展开为运行基准的 Python 解释器路径。相对文件参数以配置文件所在目录为基准解析。请将适配器脚本与 JSON 配置放在同一目录，或使用绝对路径。适配器的工作目录是每次尝试独立的工作区，不要假定其当前目录是基准仓库。

运行器提供 `ASTROMEMBENCH_WORKSPACE`、`ASTROMEMBENCH_CONFIG` 和 `ASTROMEMBENCH_OPERATION_TIMEOUT_S`。其中，`ASTROMEMBENCH_CONFIG` 是包含 `config` 内容的 JSON 字符串。通过环境变量读取凭证，并将变量名加入 `pass_env`；如果适配器使用约定名称 `ASTROMEMBENCH_API_KEY`，也可以使用 `credential_env`。被测系统需要的客户端依赖应安装在 `argv` 使用的环境中。

### 传输与消息格式

每个请求和回复各占一行。每次回复后刷新标准输出。诊断信息写入标准错误，运行器会将其保存在 `adapter.log` 中。长期运行或脱离父进程运行的子服务不得继承协议的标准输入、标准输出；适配器负责关闭这些服务。

请求：

```json
{"protocol":"astromembench/2","id":1,"operation":"reset","payload":{}}
```

回复：

```json
{"id":1,"result":{"cleared":true}}
```

回复中的整数 `id` 必须与请求一致。成功回复在 `result` 中提供 JSON 对象，失败回复提供 `error` 对象，两者不能同时出现。协议标识描述消息格式，与软件发布版本独立。请求还可能在 `payload` 之外携带 `observation` 对象，用于记录评测器的计时元数据；不要将这些元数据传给被测系统。

请求按顺序发送。完成相应工作后再回复；确认回复应表示对应的状态变更或历史处理已经完成。不要将进度条、日志或模型输出直接写入标准输出。

### 生命周期

一道题按以下顺序运行：

```text
reset
new_session
history × 30
[new_session, only for mode=new_session]
observe → submit action → environment transition
          repeat until the task ends
feedback
end
```

之后，评测器关闭适配器进程。`close` 是宿主侧的清理操作，不是第七个 JSONL 请求。

#### `reset`：重置

清空上一道题留下的状态，包括可能在题目之间传递答案的被测系统持久记忆。清空完成后再回复。

请求体为 `{}`。

```json
{"id":1,"result":{"cleared":true}}
```

建议为评测使用独立的记忆命名空间或集合，使重置可以清理题目状态而不影响其他用户数据。返回 `cleared: true` 必须意味着实际完成了重置。

#### `new_session`：新建会话

使用 `payload.instructions` 提供的指令创建新会话，返回非空的会话标识。

回复示例：

```json
{"id":2,"result":{"conversation_id":"conversation-1"}}
```

第一次调用发生在 `reset` 之后。在 `new_session` 模式中，运行器会在历史发送完成后再次调用此操作，并要求返回不同的标识。此时应清空当前会话记录，同时保留系统从历史中建立的持久记忆，再由系统自身的记忆机制检索所需信息。

`new_session` 改变的是会话，`reset` 清空的是被测系统的整体状态。如果系统无法实现这一会话边界，应返回 `unsupported` 错误。只更换标识并不等于实际创建了新会话。

#### `history`：处理历史

读取一轮过去的记录。公开历史包包含接收时间、发生时间、通道和 `data.records`。每条记录含文本，也可能包含图片附件。

这些内容描述已经发生的事件。系统可以在此阶段写入、检索、整理或维护记忆，但不得在当前环境中执行历史动作。

回复示例：

```json
{"id":3,"result":{"processed":true,"assistant_text":"收到","action_attempted":false}}
```

`processed: true` 是必填项。`assistant_text` 和 `action_attempted` 可以描述处理情况；评测器不要求所有系统都使用示例中的确认文本。需要完成的记忆操作结束后，再确认这条历史输入。

运行器会按顺序发送全部 30 轮历史，不会替被测系统选择记忆或构建检索索引。

#### `observe`：观测与动作

处理当前任务观测，并提交一个动作。观测包含当前可选动作；需要额外字段时，还会提供 `action_parameters` 说明。

选择动作的回复示例：

```json
{"id":33,"result":{"action_submitted":true,"action":{"action":"select","option":"A"}}}
```

这里只演示结构；实际使用当前观测中提供的选项。将选中项的 `arguments` 复制为基础动作对象。只有当前 `action_parameters` 明确声明的字段才能额外填写，并遵守其类型、必填要求和格式。不要在动作中加入说明文本、解释或未声明的证据字段。

`action` 对象就是提交的动作本身，不再套一层 `arguments` 或 `parameters`。普通文字答案，或放在 `assistant_text` 中的 JSON，都不算动作提交。只有被测系统实际给出了操作动作时，才设置 `action_submitted: true`。

如果智能体使用工具调用，应向它提供 `robot_action` 工具，并将真实工具调用转换为上述回复。其他系统可以通过自身的原生决策接口产生动作，再返回对应的动作对象。所有题目应使用一致的转换方式。

运行器会检查并执行动作。提交动作不代表动作一定有效或成功，后续观测会反映公开环境状态的变化。

#### `feedback`：处理反馈

处理环境的最终反馈。请求体包含 `stage`、`terminal` 和 `observation`。系统可以借此完成结果处理，但不得提交新动作。

```json
{"id":34,"result":{"processed":true}}
```

计分终局由环境决定，处理反馈不会把失败任务变成成功任务。

#### `end`：结束题目

完成当前题目尚未结束的工作，刷新资源，并准备退出进程。请求体为 `{}`。

```json
{"id":35,"result":{"processed":true}}
```

### 图片

图片附件通过公开输入中的 `images` 数组提供，每个附件的结构如下：

```json
{"id":"I01","mime_type":"image/jpeg","data_base64":"<base64 image bytes>"}
```

`data_base64` 包含原始图片字节，应通过被测系统的原生图片接口传入。ID 是中性的附件标签；来源路径、评测器标注和评分信息不会作为模型输入提供。

不要用猜测的描述替代图片。如果系统无法处理必需的输入模态，应返回 `unsupported`，并在报告分数时说明实际覆盖范围。

### 错误

错误回复使用与请求相同的 ID：

```json
{"id":33,"error":{"kind":"unsupported","message":"This adapter does not support image input."}}
```

| `kind` | 使用场景 |
| --- | --- |
| `unsupported` | 无法提供所需的生命周期操作或输入模态 |
| `agent` | 被测系统处理了输入，但没有产生操作答案 |
| `infrastructure` | 服务、传输或执行故障导致无法评测 |

在 `observe` 阶段，未提交动作的普通 `agent` 错误会消耗一次动作机会。如果失败发生在记忆维护本身，请将 `error.failure_phase` 设为 `memory_capture`、`memory_recall` 或 `memory_finish_history`，评测器会结束该题并保留当时的分数。在历史阶段返回 `agent` 错误会以零分结束该题。

请准确区分失败原因。超时、无效 JSON 回复、进程断连或回复 ID 不匹配均属于传输故障，不能作为有效答案。运行器会将它们与已计分的任务结果分开记录，详见[评测说明](evaluation.md#分数与覆盖率)。

### 并行隔离与可选用量

工作台可并行运行已隔离的分组。只有每个适配器进程都拥有独立的外部记忆命名空间和原生会话时，才能声明 `parallel_safe`。可从唯一的 `ASTROMEMBENCH_WORKSPACE` 派生命名空间，也可创建新标识。`reset` 只能清理该用例状态，`end` 只能清理本进程拥有的资源。服务路由、凭据、限流、模型选择、检索策略和远程部署由适配器负责，详见[工作台接口](workbench.md#简体中文)。

成功响应可在 `result` 中附带 `usage`：

```json
{"id":3,"result":{"processed":true,"usage":{"input_tokens":1200,"output_tokens":12,"cached_input_tokens":1000,"model_calls":1}}}
```

报告**本次操作的增量**，包含其模型或记忆服务调用，不得传入会话累计计数。支持 `input_tokens`、`output_tokens`、`cached_input_tokens`、`model_calls`，均为非负整数。不知道的字段应省略，完全不可用时省略 `usage`。缓存输入属于输入 token 的子集，不额外计入总 token。无效用量会被忽略并记录警告，不改变题目得分。结果只汇总已报告增量并显示报告覆盖情况，不推算缺失 token 或费用。

### 接入检查

完整运行前，先用一道题确认：

1. `reset` 能隔离题目，包括外部记忆存储。
2. `new_session` 建立真实的会话边界，只保留系统预期的持久记忆。
3. 每次历史确认都发生在处理完成之后，历史记录不会触发当前动作。
4. `observe` 提交的动作遵守当前动作约定。
5. 标准输出只有与请求匹配的 JSONL 回复，诊断信息写入标准错误。
6. 被测系统只接收公开协议输入，不读取题目文件、评分规则、环境内部状态或评测器轨迹。

适配器在本机运行；公开消息边界不等于操作系统沙箱。接入时应维护这一边界，报告结果时记录提示词、模型、记忆策略和相关生成设置。
