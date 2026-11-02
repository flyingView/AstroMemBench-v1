# Experiment workbench / 实验工作台

[English](#english) · [简体中文](#简体中文)

## English

[Home](../README.md) · [Adapters](adapters.md) · [Evaluation](evaluation.md)

The workbench designs experiments, runs them in independent local processes, and queries their saved results. The browser is a client of the experiment service. Closing a browser or stopping the HTTP server leaves running experiments active. Reopen the same workspace to control them.

### Start and save

```bash
astromembench webui --data data/benchmark --workspace runs/workbench --port 8765
```

In **Adapters**, import `examples/random-adapter.json` for an offline protocol check, or import your own configuration. **Check** validates the executable and declared environment variables without invoking the adapter. Run a one-case experiment to exercise the complete protocol.

Create an experiment and add named groups. Each group has a saved adapter, session mode, case selection and repetition count. Copy, reorder or remove groups while the experiment is a draft. Saving stores a snapshot of the resolved adapter configuration, so later adapter edits do not change a saved group. Environment variable *names* are saved; their values are read by the worker when it starts. Keep secrets out of `config` and command arguments.

Once started, groups are immutable. Copy the experiment to change its inputs. When a worker has stopped or paused, append new groups to the existing experiment while preserving all existing groups and results. An appended experiment retains its dataset, evaluator and concurrency. Starting it reuses terminal results and evaluates unfinished or newly added work.

### Selection and execution

| Setting | Contract |
| --- | --- |
| Templates and difficulties | Empty lists mean all; otherwise use the selected values |
| Explicit case IDs | Unique IDs from the fixed dataset; they must also satisfy any supplied filters |
| Case limit | Optional integer from 1 to 2,240; deterministically sample across templates in round-robin order |
| Execution order | Restore the published dataset order after selection |
| Repetitions | 1–100 independent repetitions per group, each starting with fresh case state |
| Groups | 1–64 uniquely named groups per experiment |
| Group concurrency | 1–8 evaluation lanes, default 1; each lane executes cases serially |
| Workspace capacity | At most 8 active lanes across all experiments |
| Experiment size | At most 100,000 case instances including repetitions |

Concurrency above one requires the saved adapter's explicit `parallel_safe` declaration. Every process must use its own remote memory namespace and sessions; a local working directory alone does not isolate a shared remote database. Concurrent experiments using the same adapter command also require that declaration. Configure provider rate limits and retries inside your adapter. The workbench does not route accounts or infer service quotas.

**Pause** finishes in-flight cases and stops scheduling subsequent cases. **Stop** cancels current adapter calls and preserves partial attempts. **Resume** reuses the first durable scored or unsupported result for each case; this includes a real score of zero. It retries unscored failures and interruptions in a new attempt directory. A worker crash is shown as interrupted once its process identity disappears; resume recovers any terminal result written before the crash.

The dataset and evaluator identities must match on resume. A software edit that changes the evaluator cannot silently continue an earlier run even if the release number remains 1.0.1. Copy that experiment for evaluation with the changed implementation. The original `astromembench run --resume` command remains available for CLI runs.

### Results and comparison

Results are paginated and can be filtered by group, case ID and status. Classification summaries use the fixed SCC catalog, including challenge, subchallenge, spacecraft, mission, capability, difficulty and template. Capability associations overlap: one case may contribute to several capability rows.

Mean score and full-credit count use scored cases only. Coverage reports scored cases divided by selected instances. Unsupported inputs, infrastructure errors, agent errors, interruptions and pending cases remain distinct. Open a case to inspect its attempts, stage timing, optional reported usage and paginated interaction trace. Large individual events stay in the original `events.jsonl` instead of expanding an unbounded browser payload.

Group comparisons require the same dataset, case IDs and repetition counts. The workbench can pair results from different official v1 releases using their verified evaluator fingerprints. Custom builds must share the same version and fingerprint. Old records whose fingerprint represents an empty source set can be inspected, but their evaluator cannot be verified for automatic pairing. Session mode and adapter may differ. The paired difference is **comparison minus reference**, computed only for case/repetition pairs scored in both groups. The interface shows paired coverage and each group's failures alongside the difference. It does not turn unscored results into zeros, or imply statistical significance.

JSON and CSV exports contain compact result projections from a single database snapshot. JSON metadata, result rows and statistics describe the same committed state even while an experiment is running. Exports omit adapter configurations, directory fields, raw error text and interaction traces; failure statuses remain available. User-supplied names and labels are retained, so exports do not automatically anonymize their contents. CSV neutralizes text that spreadsheet software could treat as formulas. Raw diagnostics and original attempts remain in the local workspace. **Open CLI results** registers an inactive `astromembench/run/1` directory for read-only inspection; it does not copy adapter workspaces or run the adapter. Keep that source directory available, and use the original CLI command to resume such a run.

### Workspace layout

```text
workbench/
  workbench.sqlite3                 experiment registry and compact result index
  cache/                           rebuildable task byte offsets
  experiments/<experiment-id>/
    experiment.json                saved input definition
    worker.log                     worker diagnostics
    .run.lock                      OS-managed worker ownership
    groups/<group-id>/<repetition>/
      run.json
      summary.json
      cases/<case-id>/attempts/0001/
        result.json
        events.jsonl
        timing-events.jsonl
        runtime.json
        workspace/                 adapter-owned files and logs
```

Attempt files are the scientific record. SQLite stores small query fields, not history prompts or image payloads. Back up the complete workspace after stopping its workers and HTTP server; do not copy only the SQLite main file while its WAL is active. Imported CLI run directories must be backed up separately. Each experiment references its extracted dataset directory, so keep that directory available for resume.

### CLI without the browser

```bash
astromembench adapters --workspace runs/workbench import examples/random-adapter.json --parallel-safe
astromembench adapters --workspace runs/workbench list
astromembench adapters --workspace runs/workbench check ADAPTER_ID
astromembench experiment --workspace runs/workbench create experiment.json --data data/benchmark
astromembench experiment --workspace runs/workbench list
astromembench experiment --workspace runs/workbench show EXPERIMENT_ID
astromembench experiment --workspace runs/workbench start EXPERIMENT_ID
astromembench experiment --workspace runs/workbench pause EXPERIMENT_ID
astromembench experiment --workspace runs/workbench stop EXPERIMENT_ID
astromembench experiment --workspace runs/workbench results EXPERIMENT_ID --offset 0 --limit 50
astromembench experiment --workspace runs/workbench export EXPERIMENT_ID --format csv --output results.csv
astromembench experiment --workspace runs/workbench import runs/quickstart --data data/benchmark
```

Use the returned adapter ID in `experiment.json`. Export refuses to overwrite an existing destination.

```json
{
  "name": "Session comparison",
  "concurrency": 1,
  "groups": [
    {
      "name": "Same session",
      "adapter_id": "ADAPTER_ID",
      "mode": "same_session",
      "selection": {"templates": ["FM-C1-P1"], "difficulties": ["easy"], "limit": 2},
      "repetitions": 1
    },
    {
      "name": "New session",
      "adapter_id": "ADAPTER_ID",
      "mode": "new_session",
      "selection": {"templates": ["FM-C1-P1"], "difficulties": ["easy"], "limit": 2},
      "repetitions": 1
    }
  ]
}
```

### HTTP contract for alternative frontends

The HTTP interface binds only to `127.0.0.1`. It is a local single-user interface, without remote authentication or CORS. A browser frontend must be served from the same origin. A local CLI client supplies the same `Origin` and CSRF header for mutations. Do not expose it through a public or LAN reverse proxy without implementing the deployment's authentication and authorization separately.

Start with `GET /api/bootstrap`. It returns `csrf`, a server `instance`, version, team, workspace, dataset metadata and saved adapter summaries. POST requests require `Content-Type: application/json`, `Origin: http://127.0.0.1:PORT` and `X-CSRF-Token: <csrf>`. JSON request bodies are limited to 2 MiB. Refresh bootstrap after a server restart; do not automatically replay a mutation whose outcome is unknown.

| Method and route | Inputs and response |
| --- | --- |
| `GET /api/catalog` | `search`, `template`, `difficulty`, `offset`, `limit`; paginated `items`, `total`, `offset`, `limit` |
| `GET /api/task` | `case_id`, optional `round` 1–30; public task or one history input, never world/rubric answers |
| `GET /api/asset` | `path` from a public image reference; only declared fixed-bank image paths are served |
| `POST /api/bank` | `{ "data": "path" }`; change the catalog for newly designed experiments |
| `POST /api/selection` | `{ "selection": {…} }`; resolved count and up to 20 preview IDs |
| `GET /api/adapters` | Saved adapter summaries; command/config details are omitted |
| `GET /api/adapters/ID` | Saved adapter definition for local editing |
| `POST /api/adapters/import` | `path`, optional `parallel_safe` and existing `id` |
| `POST /api/adapters/save` | `definition`, optional `directory`, `parallel_safe`, existing `id` |
| `POST /api/adapters/check` | `{ "id": "…" }`; configuration/environment presence checks, no model calls |
| `GET /api/experiments` | `search`, `offset`, `limit`; paginated experiment history |
| `POST /api/experiments` | Experiment definition shown above; creates a draft |
| `POST /api/experiments/import` | `{ "path": "saved-cli-run" }`; read-only result registration |
| `GET /api/experiments/ID` | Saved design, status and directory; adapter snapshots omitted |
| `POST /api/experiments/ID/save` | Full design replacement, allowed only for drafts |
| `POST /api/experiments/ID/append` | Full design retaining old group IDs and definitions, plus new groups |
| `POST /api/experiments/ID/start` | `{}`; start or resume an independent worker, returns HTTP 202 |
| `POST /api/experiments/ID/pause` | `{}`; drain in-flight work |
| `POST /api/experiments/ID/stop` | `{}`; cancel current work |
| `GET /api/experiments/ID/state` | Optional `since`; compact status, active cases and group totals |
| `GET /api/experiments/ID/results` | Pagination and filters; compact result rows |
| `GET /api/experiments/ID/statistics` | Optional `axis` and filters; overall and classified score/coverage statistics |
| `GET /api/experiments/ID/measurements` | Filters; stage timing and sums of explicitly reported usage |
| `GET /api/experiments/ID/result` | `group_id`, `repetition`, `case_id`, optional `attempt`; saved result and attempt list |
| `GET /api/experiments/ID/events` | Same identity, optional `cursor`, `limit`; bounded trace page and next cursor |
| `GET /api/experiments/ID/export` | `format=json` or `csv`; compact download |
| `GET /api/compare` | `left_experiment`, `left_group`, `right_experiment`, `right_group`; compatibility and paired statistics |

Result/statistic filters accept `group_id`, `status`, `search` (case ID), `template`, `difficulty`, `challenge`, `subchallenge`, `craft` and `mission`. Axes are `group_id`, `template`, `difficulty`, `challenge`, `subchallenge`, `craft`, `mission` and `capability`. Standard pages allow 1–100 rows; event pages allow 1–50 records and at most 512 KiB of ordinary event data. Treat event cursors as opaque byte offsets returned by the server.

State `revision` is opaque and includes the server instance. If unchanged, the response contains only `unchanged: true` and `revision`. The bundled UI checks active experiments every 500 ms after the previous request finishes, and slows down for idle or hidden tabs. `record_revision` changes with persisted experiment state; runtime-only updates change the opaque `revision`. Request result pages only when their filters or persisted revision change. Abort obsolete reads; fetch histories, images and traces on demand. Use text-safe rendering for adapter names, errors and traces. Never derive a score or selection rule independently in the frontend.

The Python entry point is `astromembench.experiments.ExperimentService`. It exposes the same use cases without an HTTP dependency. Workers call the original evaluator. Custom interfaces should use this service or HTTP contract instead of writing SQLite rows or manipulating worker processes directly.

## 简体中文

[首页](../README.zh-CN.md) · [适配器](adapters.md#简体中文) · [评测](evaluation.md#简体中文)

工作台负责实验设计、独立后台执行和已保存结果查询。浏览器是实验服务的客户端；关闭浏览器或 HTTP 服务不会终止后台实验，重新打开相同工作目录即可继续控制。

### 启动与设计

```bash
astromembench webui --data data/benchmark --workspace runs/workbench --port 8765
```

在「适配器」中导入 `examples/random-adapter.json`，可离线检查协议流程；也可导入自己的配置。「检查」只验证可执行文件和环境变量是否存在，不调用模型。使用单题实验检查完整协议。

每个分组分别设置名称、适配器、会话模式、选题与重复次数。草稿支持复制、排序和移除分组。保存时冻结已解析的适配器配置；此后修改适配器不会改变已保存的分组。环境变量只保存名称，值在工作进程启动时读取。不要把密钥放入 `config` 或命令参数。

启动后已有分组不可修改。需要改变输入时复制整个实验；需要增加实验条件时，暂停或停止后追加分组。追加操作保留原有分组、结果、数据集、评测器和并发设置，再次运行只处理未完成或新增工作。

### 选题与执行边界

- 模板、难度的空列表表示全部；指定题目 ID 时，ID 必须唯一，且同时满足已设置的模板和难度筛选。
- 题数上限为 1–2,240；先按模板轮询取样，再恢复固定题库顺序，保证结果可复现。
- 每组重复 1–100 次；每个实验 1–64 组，分组名称不得重复；包含重复次数后最多 100,000 个题目实例。
- 默认并发为 1，可设置 1–8 条执行通道，每条通道内串行执行；整个工作目录最多同时运行 8 条通道。
- 并发高于 1 时，适配器必须显式声明 `parallel_safe`，确保每个进程的远程会话与记忆命名空间独立。本地目录隔离不能代替远程数据库隔离。相同适配器命令跨实验同时运行也需要此声明。

模型服务限流、重试策略和部署由适配器负责，工作台不调度账号或推测服务配额。

「暂停」等待正在执行的题目完成后再停；「停止」中断当前适配器调用并保存未完成尝试。「继续运行」保留最早持久化的已评分或不支持结果，包括真实零分；只有未评分的失败和中断会建立新尝试。进程意外退出后会显示中断，恢复时先读取已经落盘的终局结果。

恢复要求数据集和评测器身份一致。即使版本号仍为 1.0.1，改变评测实现后也不能悄悄接着运行旧实验，应复制为新实验。原有 CLI 单次运行仍使用 `astromembench run --resume` 恢复。

### 结果与比较

结果按页查询，可按分组、题目 ID 和状态筛选；SCC 分类统计支持挑战、子挑战、航天器、任务、能力、难度和模板。一题可能涉及多项能力，因此能力统计并非互斥分桶。

均分和满分数只基于已评分题目，覆盖率是已评分数除以选定实例数。不支持、运行环境错误、智能体错误、中断与待运行分别保留。题目详情显示各次尝试、阶段耗时、可选用量及分页交互记录；超大的单条交互保留在原始 `events.jsonl` 中。

比较要求数据集、题目 ID 和重复次数一致，可使用不同适配器或会话模式。工作台通过已核验的评测器指纹配对不同 v1 正式版本的结果。自定义版本须同时匹配版本号和指纹。旧记录若保存了空源码集的指纹，仍可查看，但无法验证其评测器以自动配对。配对差值定义为「比较组减基准组」，仅计算两组均已评分的相同题目和重复序号，并同时显示配对覆盖率及失败数。未计分的结果不参与差值计算，差值不代表统计显著性。

JSON、CSV 从同一个数据库快照导出简洁结果。即使实验正在运行，JSON 中的实验信息、结果明细和统计也对应同一已提交状态。导出不包含适配器配置、目录字段、原始错误文本或交互记录，仍保留失败状态。用户填写的名称和标签会保留，导出不会自动将这些内容匿名化。CSV 对可能被表格软件执行为公式的文本进行转义。原始诊断信息和尝试保留在本地工作目录中。「打开 CLI 结果」只读登记未运行中的 `astromembench/run/1` 结果目录，不复制适配器工作目录，也不执行适配器。请保留源目录，需要继续评测时使用原 CLI 命令。

### 文件与命令

工作目录结构与上方英文示例相同：`workbench.sqlite3` 保存实验和查询索引，`cache/` 保存可重建的题库字节偏移；`experiments/实验ID/groups/分组ID/重复序号/` 下保留标准 `run.json`、`summary.json` 和各题的原始尝试。

备份前停止工作进程和 HTTP 服务，再备份完整工作目录。SQLite 的 WAL 活跃时不要只复制主数据库文件。只读导入的 CLI 源目录需要单独备份。恢复实验还需要保存定义中引用的数据集目录。

上方 [CLI 命令](#cli-without-the-browser)与 JSON 示例可直接用于中文界面：导入适配器后，将返回的 ID 填入 `adapter_id`；`create` 保存实验，`start` 启动或恢复，`pause` 暂停，`stop` 停止，`results` 分页查询，`export` 导出。导出命令不会覆盖已有文件。

### 自定义前端与服务

上方 [HTTP 接口表](#http-contract-for-alternative-frontends)是完整接口约定。服务仅监听 `127.0.0.1`，用于本机单用户操作，不提供远程认证或 CORS。浏览器前端必须同源；本机 CLI 的修改请求同样需要正确 `Origin` 和 CSRF 令牌。若自行部署公网或局域网服务，须另行实现认证与授权。

首先调用 `GET /api/bootstrap` 获取 `csrf` 和服务 `instance`。POST 使用 JSON 请求体、`Content-Type: application/json`、当前服务的 `Origin` 与 `X-CSRF-Token`，请求体最多 2 MiB。服务重启后重新获取 bootstrap；对于结果未知的修改请求，不应自动重放。

实验定义使用上方同一 JSON 结构。题库和选题都由后端解析；结果、分类统计和耗时支持 `group_id`、`status`、`search`、`template`、`difficulty`、`challenge`、`subchallenge`、`craft`、`mission` 筛选。普通分页 1–100 行；交互分页 1–50 条，普通交互数据每页最多 512 KiB，直接复用后端返回的游标。

`state.revision` 是包含服务实例身份的不透明值。未变化时只返回 `unchanged: true` 和 `revision`。内置 UI 在上次请求结束后间隔 500 ms 查询运行中状态，空闲或隐藏页面降低频率。`record_revision` 随已持久化状态变化，单纯运行时进度变化只影响不透明的 `revision`；筛选条件或持久化版本变化后才刷新当前结果页。取消过期读取请求，历史、图片和交互按需加载。名称、错误和交互文本必须安全渲染，前端不得独立推导评分或选题规则。

Python 调用入口是 `astromembench.experiments.ExperimentService`，不依赖 HTTP。工作进程调用原有评测核心。自定义前端应通过该服务或 HTTP 接口访问，不直接修改 SQLite，也不直接控制工作进程 PID。

---

Research Group on Intelligent Technologies for Spacecraft, Zhejiang University · you wu · 1.0.1
