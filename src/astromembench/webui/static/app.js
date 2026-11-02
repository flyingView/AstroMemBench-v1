/* Local workbench. Rendering, HTTP transport and experiment state stay separate. */
const $ = (query, root = document) => root.querySelector(query);
const $$ = (query, root = document) => [...root.querySelectorAll(query)];
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
let lang = "en";
try {
  lang =
    localStorage.getItem("astromembench.language") ||
    (navigator.language.startsWith("zh") ? "zh" : "en");
} catch {}
const t = (en, zh) => (lang === "zh" ? zh : en);
const numberFormats = new Map();
function fmt(value, digits = 1) {
  if (value === null || value === undefined) return "—";
  const key = `${lang}:${digits}`;
  if (!numberFormats.has(key))
    numberFormats.set(key, new Intl.NumberFormat(lang, { maximumFractionDigits: digits }));
  return numberFormats.get(key).format(value);
}
const seconds = (value) =>
  value == null
    ? "—"
    : value < 60
      ? `${fmt(value)} s`
      : `${fmt(value / 60)} min`;
const statusNames = {
  draft: ["Draft", "草稿"],
  starting: ["Starting", "启动中"],
  running: ["Running", "运行中"],
  pausing: ["Pausing", "暂停中"],
  paused: ["Paused", "已暂停"],
  stopping: ["Stopping", "停止中"],
  stopped: ["Stopped", "已停止"],
  completed: ["Completed", "已完成"],
  incomplete: ["Incomplete", "未完成"],
  failed: ["Failed", "失败"],
  pending: ["Pending", "待运行"],
  interrupted: ["Interrupted", "已中断"],
  unsupported: ["Unsupported", "不支持"],
  infrastructure_error: ["Infrastructure error", "运行环境错误"],
  agent_error: ["Agent error", "智能体错误"],
};
const statusText = (status) => t(...(statusNames[status] || [status, status]));
const statusHTML = (status) =>
  `<span class="status" data-status="${esc(status)}">${esc(statusText(status))}</span>`;
const activeStates = new Set(["starting", "running", "pausing", "stopping"]);
const modes = () => [
  ["same_session", t("Same session", "同一会话")],
  ["new_session", t("New session", "跨会话")],
];
const options = (items, selected, empty) =>
  (empty !== undefined ? `<option value="">${esc(empty)}</option>` : "") +
  items
    .map(
      ([value, label]) =>
        `<option value="${esc(value)}" ${String(value) === String(selected) ? "selected" : ""}>${esc(label)}</option>`,
    )
    .join("");
const button = (action, label, extra = "", kind = "") =>
  `<button type="button" data-action="${action}" ${extra} class="${kind}">${label}</button>`;
const query = (object) =>
  new URLSearchParams(
    Object.entries(object).filter(([, v]) => v !== "" && v != null),
  ).toString();
const ui = {
  boot: null,
  route: { page: "experiments", id: "new", view: "design" },
  drafts: new Map(),
  detail: null,
  state: null,
  sequence: 0,
  controller: null,
  historyOffset: 0,
  historySearch: "",
  historyKey: "",
  resultOffset: 0,
  caseOffset: 0,
  dialog: null,
  selectionTimers: new Map(),
  filterTimer: null,
  requests: new Map(),
  generations: {},
};
let pollTimer,
  noticeTimer,
  polling = false;
const report = (exc) => {
  if (exc.name !== "AbortError") error(exc.message);
};

function requestSlot(key) {
  ui.requests.get(key)?.abort();
  const controller = new AbortController();
  ui.requests.set(key, controller);
  const generation = (ui.generations[key] || 0) + 1;
  ui.generations[key] = generation;
  return {
    generation,
    signal: AbortSignal.any([
      controller.signal,
      ui.controller.signal,
      AbortSignal.timeout(20000),
    ]),
  };
}

async function api(path, { body, signal } = {}) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    cache: "no-store",
    credentials: "same-origin",
    headers:
      body === undefined
        ? {}
        : {
            "Content-Type": "application/json",
            "X-CSRF-Token": ui.boot?.csrf || "",
          },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: signal || AbortSignal.timeout(20000),
  });
  const value = await response.json();
  if (!response.ok) {
    if (response.status === 403 && body !== undefined) {
      try {
        ui.boot = await api("/api/bootstrap");
      } catch {}
    }
    throw new Error(value.error || `HTTP ${response.status}`);
  }
  return value;
}

function notify(message) {
  clearTimeout(noticeTimer);
  $("#notice").textContent = message;
  $("#notice").hidden = false;
  noticeTimer = setTimeout(() => {
    $("#notice").hidden = true;
  }, 4500);
}

function error(message, root = $("#main")) {
  let box = $(".error", root);
  if (!box) {
    box = document.createElement("div");
    box.className = "error";
    box.setAttribute("role", "alert");
    box.tabIndex = -1;
    root.prepend(box);
  }
  box.textContent = message;
  box.hidden = false;
  box.focus({ preventScroll: true });
}

function clearError(root = $("#main")) {
  $(".error", root)?.remove();
}
function draft() {
  return ui.drafts.get(ui.route.id);
}
function dirty() {
  const value = draft();
  if (value) value.dirty = true;
  const node = $("#unsaved");
  if (node) node.textContent = t("Unsaved changes", "有未保存的修改");
}
function groupDefault(index = 1) {
  return {
    name: t(`Group ${index}`, `分组 ${index}`),
    adapter_id: ui.boot.adapters[0]?.id || "",
    mode: "same_session",
    selection: { limit: 1 },
    repetitions: 1,
  };
}
function newDraft() {
  return {
    name: t("Untitled experiment", "未命名实验"),
    concurrency: 1,
    groups: [groupDefault()],
    expanded: 0,
    dirty: false,
  };
}
function experimentPath(id = ui.route.id) {
  return `/api/experiments/${encodeURIComponent(id)}`;
}
function navigation(page) {
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  $("#language").textContent = lang === "zh" ? "EN" : "中文";
  $("#navigation").innerHTML = [
    ["experiments", t("Experiments", "实验")],
    ["cases", t("Cases", "题库")],
    ["adapters", t("Adapters", "适配器")],
    ["guide", t("Guide", "接入指南")],
  ]
    .map(
      ([key, name]) =>
        `<a href="#${key}" ${page === key ? 'aria-current="page"' : ""}>${name}</a>`,
    )
    .join("");
  $(".skip-link").textContent = t("Skip to content", "跳转到内容");
}

async function history(force = false) {
  if (!$("#history-list")) return;
  const request = requestSlot("history");
  const values = await api(
    "/api/experiments?" +
      query({ offset: ui.historyOffset, limit: 15, search: ui.historySearch }),
    request,
  );
  if (request.generation !== ui.generations.history) return;
  const key = JSON.stringify([values, ui.route.id, lang]);
  if (key === ui.historyKey && !force) return;
  ui.historyKey = key;
  const list = $("#history-list");
  if (!list) return;
  list.innerHTML =
    values.items
      .map(
        (row) =>
          `<a class="history-item" href="#experiments/${row.id}/${row.status === "draft" ? "design" : "monitor"}" aria-current="${row.id === ui.route.id}"><strong>${esc(row.name)}</strong><span><span>${esc(statusText(row.status))}</span><span>${fmt(row.finished, 0)} / ${fmt(row.total, 0)}</span></span></a>`,
      )
      .join("") ||
    `<p class="info-line">${t("No experiments yet", "尚无实验")}</p>`;
  $("#history-pages").innerHTML =
    button(
      "history-prev",
      "←",
      `aria-label="${t("Previous experiments", "上一页实验")}" ${ui.historyOffset === 0 ? "disabled" : ""}`,
      "quiet",
    ) +
    `<span>${values.total ? ui.historyOffset + 1 : 0}–${Math.min(ui.historyOffset + 15, values.total)} / ${values.total}</span>` +
    button(
      "history-next",
      "→",
      `aria-label="${t("Next experiments", "下一页实验")}" ${ui.historyOffset + 15 >= values.total ? "disabled" : ""}`,
      "quiet",
    );
}

function sidebar() {
  $("#sidebar").hidden = ui.route.page !== "experiments";
  if (ui.route.page !== "experiments") return;
  $("#sidebar").innerHTML =
    `<details ${matchMedia("(min-width:781px)").matches ? "open" : ""}><summary>${t("Experiments", "实验记录")}</summary><input class="search" id="history-search" type="search" aria-label="${t("Search experiments", "搜索实验")}" placeholder="${t("Search experiments…", "搜索实验…")}" value="${esc(ui.historySearch)}">${button("new", t("+ New experiment", "＋ 新建实验"), "", "new")}<div id="history-list" class="history-list"></div><div class="pagination" id="history-pages"></div></details>`;
  $('[data-action="new"]', $("#sidebar")).insertAdjacentHTML(
    "afterend",
    button(
      "import-run",
      t("Open CLI results", "打开 CLI 结果"),
      "",
      "quiet small",
    ),
  );
}

async function navigate() {
  const seq = ++ui.sequence;
  for (const [key, value] of ui.drafts) if (!value.dirty) ui.drafts.delete(key);
  ui.controller?.abort();
  ui.controller = new AbortController();
  const parts = location.hash.slice(1).split("/");
  const page = ["experiments", "cases", "adapters", "guide"].includes(parts[0])
    ? parts[0]
    : "experiments";
  const id = /^[a-f0-9]{32}$/.test(parts[1] || "") ? parts[1] : "new";
  const view = ["design", "monitor", "results", "compare"].includes(parts[2])
    ? parts[2]
    : "design";
  ui.route = { page, id, view };
  ui.detail = null;
  ui.state = null;
  ui.resultOffset = 0;
  navigation(page);
  sidebar();
  $("#main").innerHTML =
    `<div class="empty" role="status">${t("Loading…", "加载中…")}</div>`;
  try {
    if (page === "experiments") {
      if (id !== "new") {
        const detail = await api(experimentPath(id), {
          signal: ui.controller.signal,
        });
        if (seq !== ui.sequence) return;
        ui.detail = detail;
        if (!ui.drafts.has(id))
          ui.drafts.set(id, {
            ...structuredClone(detail.definition),
            expanded: 0,
            dirty: false,
          });
      } else if (!ui.drafts.has("new")) ui.drafts.set("new", newDraft());
      renderExperiment();
      await history(true);
      if (id !== "new") {
        const state = await api(experimentPath(id) + "/state", {
          signal: ui.controller.signal,
        });
        if (seq !== ui.sequence) return;
        ui.state = state;
        renderLive();
      }
      if (view === "results" && id !== "new") await loadResults();
      if (view === "compare" && id !== "new") await loadComparison();
    } else if (page === "cases") {
      renderCases();
      await loadCases();
    } else if (page === "adapters") {
      await refreshAdapters();
      renderAdapters();
    } else renderGuide();
  } catch (exc) {
    if (exc.name !== "AbortError" && seq === ui.sequence) error(exc.message);
  }
}

function controls() {
  const state = ui.state?.status || ui.detail?.status || "draft";
  const disabled = !ui.boot.bank || !ui.boot.adapters.length;
  if (ui.detail?.definition.read_only)
    return button("copy-experiment", t("Copy", "复制"));
  if (ui.route.id === "new" || state === "draft")
    return (
      button("save", t("Save", "保存"), "", "") +
      button(
        "start",
        t("Run experiment", "运行实验"),
        disabled ? "disabled" : "",
        "primary",
      )
    );
  if (activeStates.has(state))
    return (
      button(
        "pause",
        t("Pause", "暂停"),
        state === "pausing" || state === "stopping" ? "disabled" : "",
      ) +
      button(
        "stop",
        t("Stop", "停止"),
        state === "stopping" ? "disabled" : "",
        "danger",
      )
    );
  return (
    button("copy-experiment", t("Copy", "复制")) +
    (state !== "completed"
      ? button("start", t("Resume", "继续运行"), "", "primary")
      : "")
  );
}

function renderExperiment() {
  const value = draft();
  const state = ui.state?.status || ui.detail?.status || "draft";
  const saved = ui.route.id !== "new";
  $("#main").innerHTML =
    `<div class="page-heading"><div class="heading-copy"><h1>${esc(value.name)}</h1><div id="experiment-status">${statusHTML(state)}</div></div><div id="experiment-controls" class="actions">${controls()}</div></div>
    <nav class="tabs" aria-label="${t("Experiment views", "实验视图")}">${[
      ["design", t("Design", "设计")],
      ["monitor", t("Run", "运行")],
      ["results", t("Results", "结果")],
      ["compare", t("Compare", "比较")],
    ]
      .filter(([key]) => saved || key === "design")
      .map(
        ([key, label]) =>
          `<a href="#experiments/${ui.route.id}/${key}" ${ui.route.view === key ? 'aria-current="page"' : ""}>${label}</a>`,
      )
      .join("")}</nav><div id="experiment-content"></div>`;
  if (ui.route.view === "design" || !saved) renderDesign();
  else if (ui.route.view === "monitor") renderMonitor();
  else if (ui.route.view === "results") renderResults();
  else renderCompare();
}

function groupHTML(group, index, locked) {
  const value = draft(),
    open = value.expanded === index;
  const count = group.case_ids?.length ?? group.selection?.limit;
  return `<section class="group" data-group="${index}"><div class="group-heading"><button class="group-toggle" type="button" data-action="toggle-group" data-index="${index}" aria-expanded="${open}" aria-controls="group-body-${index}"><span class="group-number">${String(index + 1).padStart(2, "0")}</span><span class="group-title">${esc(group.name)}</span><span class="group-count" id="group-count-${index}">${count ? t(`${fmt(count, 0)} cases`, `${fmt(count, 0)} 题`) : t("All cases", "全部题目")}</span></button>${!locked ? `<div class="tools">${button("copy-group", t("Copy", "复制"), `data-index="${index}"`, "quiet")}${button("up-group", "↑", `data-index="${index}" aria-label="${t("Move group up", "上移分组")}" ${index === 0 ? "disabled" : ""}`, "quiet")}${button("down-group", "↓", `data-index="${index}" aria-label="${t("Move group down", "下移分组")}" ${index === value.groups.length - 1 ? "disabled" : ""}`, "quiet")}${button("remove-group", "×", `data-index="${index}" aria-label="${t("Remove group", "移除分组")}" ${value.groups.length === 1 ? "disabled" : ""}`, "quiet danger")}</div>` : ""}</div>
    <div class="group-body" id="group-body-${index}" ${open ? "" : "hidden"}>${open ? groupEditor(group, index, locked) : ""}</div></section>`;
}

function groupEditor(group, index, locked) {
  const selection = group.selection || {},
    off = locked ? "disabled" : "";
  return `<fieldset ${off}><div class="form-grid"><label>${t("Group name", "分组名称")}<input data-field="name" value="${esc(group.name)}" maxlength="160" required></label><label>${t("Adapter", "适配器")}<select data-field="adapter_id">${options(
    ui.boot.adapters.map((a) => [a.id, a.name]),
    group.adapter_id,
    t("Choose an adapter", "选择适配器"),
  )}</select></label><label>${t("Session", "会话模式")}<select data-field="mode">${options(modes(), group.mode)}</select></label><label>${t("Templates", "模板")}${button("templates", selection.templates?.length ? t(`${selection.templates.length} selected`, `已选 ${selection.templates.length} 个`) : t("All templates", "全部模板"), `data-index="${index}"`, "template-button")}</label><fieldset><legend>${t("Difficulty", "难度")}</legend><div class="checks">${[
    ["easy", t("Easy", "简单")],
    ["medium", t("Medium", "中等")],
    ["hard", t("Hard", "困难")],
  ]
    .map(
      ([key, label]) =>
        `<label><input type="checkbox" data-difficulty="${key}" ${!selection.difficulties?.length || selection.difficulties.includes(key) ? "checked" : ""}>${label}</label>`,
    )
    .join(
      "",
    )}</div></fieldset><div class="form-grid"><label>${t("Case limit", "题数上限")}<input data-field="limit" type="number" min="1" max="2240" placeholder="${t("All", "全部")}" value="${esc(selection.limit || "")}"></label><label>${t("Repetitions", "重复次数")}<input data-field="repetitions" type="number" min="1" max="100" value="${group.repetitions || 1}"></label></div></div><div class="selection-footer"><details ${selection.case_ids?.length ? "open" : ""}><summary>${t("Explicit case IDs", "指定题目 ID")}</summary><label class="sr-label"><textarea data-field="case_ids" aria-label="${t("Explicit case IDs, one per line", "指定题目 ID，每行一个")}" spellcheck="false">${esc((selection.case_ids || []).join("\n"))}</textarea></label></details></div></fieldset>${locked ? `<p class="info-line">${esc(group.adapter_name || "")}</p>` : ""}`;
}

function renderDesign() {
  const value = draft(),
    state = ui.detail?.status || "draft";
  const locked = ui.route.id !== "new" && state !== "draft" && !value.appending;
  $("#experiment-content").innerHTML =
    `<div class="design-top"><label>${t("Experiment name", "实验名称")}<input id="experiment-name" value="${esc(value.name)}" maxlength="160" ${locked || value.appending ? "disabled" : ""}></label><label>${t("Parallel groups", "并行分组")}<input id="concurrency" type="number" min="1" max="8" value="${value.concurrency}" ${locked || value.appending ? "disabled" : ""}></label></div><div class="section-heading"><h2>${t("Groups", "实验分组")}</h2>${!locked ? button("add-group", t("+ Add group", "＋ 添加分组"), "", "quiet") : !activeStates.has(state) && !ui.detail?.definition.read_only ? button("append-groups", t("+ Append groups", "＋ 追加分组"), "", "quiet") : ""}</div><div id="groups">${value.groups.map((g, i) => groupHTML(g, i, locked || (value.appending && i < value.originalCount))).join("")}</div><div class="form-footer"><span id="unsaved" class="unsaved">${value.dirty ? t("Unsaved changes", "有未保存的修改") : ""}</span>${value.appending ? button("save-append", t("Save appended groups", "保存追加分组"), "", "primary") : ""}</div>
    ${!ui.boot.adapters.length ? `<p class="info-line"><a href="#adapters">${t("Add an adapter to run this experiment.", "添加适配器后即可运行实验。")}</a></p>` : ""}${settingsHTML()}`;
}

function settingsHTML() {
  return `<details class="settings" ${!ui.boot.bank ? "open" : ""}><summary>${t("Dataset & workspace", "数据集与工作目录")}</summary><form id="bank-form"><label>${t("Dataset directory", "数据集目录")}<input id="data-path" value="${esc(ui.boot.data)}" required spellcheck="false"></label><button type="submit">${t("Load", "加载")}</button></form>${ui.boot.bank_error ? `<p class="error">${esc(ui.boot.bank_error)}</p>` : ""}<p class="info-line">${t("Workspace", "工作目录")} · <span class="mono">${esc(ui.boot.workspace)}</span></p></details>`;
}

async function saveDraft(append = false) {
  clearError();
  const value = draft();
  if (!value.name.trim())
    throw new Error(t("Enter an experiment name", "请输入实验名称"));
  const body = {
    name: value.name,
    concurrency: value.concurrency,
    groups: value.groups.map(
      ({ id, name, adapter_id, mode, selection, repetitions }) => ({
        id,
        name,
        adapter_id,
        mode,
        selection,
        repetitions,
      }),
    ),
  };
  const saved = await api(
    ui.route.id === "new"
      ? "/api/experiments"
      : experimentPath() + (append ? "/append" : "/save"),
    { body },
  );
  ui.drafts.delete(ui.route.id);
  ui.drafts.set(saved.id, {
    ...structuredClone(saved.definition),
    expanded: 0,
    dirty: false,
  });
  ui.detail = saved;
  return saved.id;
}

function metricsHTML(summary) {
  return `<dl class="metrics"><div class="metric"><dt>${t("Scored", "已评分")}</dt><dd>${fmt(summary.scored, 0)} <small>/ ${fmt(summary.total, 0)}</small></dd></div><div class="metric"><dt>${t("Mean score", "平均分")}</dt><dd>${fmt(summary.mean_score)} <small>/ 100</small></dd></div><div class="metric"><dt>${t("Full credit", "满分")}</dt><dd>${fmt(summary.full_credit_count, 0)}</dd></div><div class="metric"><dt>${t("Failed / interrupted", "失败 / 中断")}</dt><dd>${fmt(summary.failed, 0)} <small>/ ${fmt(summary.interrupted, 0)}</small></dd></div></dl>`;
}

function renderMonitor() {
  $("#experiment-content").innerHTML =
    `<div id="run-metrics"></div><progress id="run-progress" class="run-progress" max="1" value="0" aria-label="${t("Experiment progress", "实验进度")}"></progress><div id="active-cases" class="live-list"></div><div class="section-heading"><h2>${t("Groups", "实验分组")}</h2></div><div id="group-progress"></div><p class="info-line mono">${esc(ui.detail?.directory)}</p>`;
}

function groupName(id) {
  return (
    (draft()?.groups || ui.detail?.definition.groups || []).find(
      (g) => g.id === id,
    )?.name || id
  );
}
function renderLive() {
  const state = ui.state;
  if (!state || ui.route.page !== "experiments") return;
  if (ui.detail) ui.detail.status = state.status;
  const status = $("#experiment-status");
  if (status && status.dataset.state !== state.status) {
    status.innerHTML = statusHTML(state.status);
    status.dataset.state = state.status;
    $("#experiment-controls").innerHTML = controls();
  }
  if (state.error) error(state.error);
  if ($("#run-metrics")) {
    const key = JSON.stringify(state.summary);
    if ($("#run-metrics").dataset.value !== key) {
      $("#run-metrics").innerHTML = metricsHTML(state.summary);
      $("#run-metrics").dataset.value = key;
    }
    $("#run-progress").max = state.summary.total || 1;
    $("#run-progress").value = state.summary.finished;
    $("#active-cases").innerHTML = state.active
      .map((row) => {
        const r = row.runtime || {};
        return `<article class="live-row"><header><strong>${esc(groupName(row.group_id))}</strong><span class="mono">${esc(row.case_id)} · ${row.repetition}</span></header><p>${esc(r.stage || t("Starting", "启动中"))} · ${r.history_processed ?? 0} / 30 ${t("history rounds", "轮历史")} · ${seconds(r.elapsed_s)} ${r.waiting ? `· ${t("Waiting for adapter", "等待适配器")}` : ""}</p></article>`;
      })
      .join("");
    $("#group-progress").innerHTML = state.groups
      .map(
        (group) =>
          `<div class="stat-row"><span class="label">${esc(groupName(group.label))}</span><meter min="0" max="${group.total || 1}" value="${group.finished}" aria-label="${esc(groupName(group.label))} ${t("progress", "进度")}"></meter><span class="number">${fmt(group.mean_score)}</span><span class="number muted">${group.finished} / ${group.total}</span></div>`,
      )
      .join("");
  }
}

function renderResults() {
  $("#experiment-content").innerHTML =
    `<div id="result-metrics"></div><div class="filter-row"><label>${t("Group", "分组")}<select id="result-group">${options(
      draft().groups.map((g) => [g.id, g.name]),
      "",
      t("All groups", "全部分组"),
    )}</select></label><label>${t("Status", "状态")}<select id="result-status">${options(
      Object.keys(statusNames)
        .filter(
          (k) =>
            ![
              "draft",
              "starting",
              "pausing",
              "paused",
              "stopping",
              "stopped",
              "incomplete",
              "failed",
            ].includes(k),
        )
        .map((k) => [k, statusText(k)]),
      "",
      t("All statuses", "全部状态"),
    )}</select></label><label class="wide">${t("Case ID", "题目 ID")}<input id="result-search" type="search" autocomplete="off"></label><div class="actions"><a class="download" href="${experimentPath()}/export?format=json" download>JSON ↓</a><a class="download" href="${experimentPath()}/export?format=csv" download>CSV ↓</a></div></div><div id="result-table"></div><div id="result-pages" class="pagination"></div><div class="breakdown-toolbar"><h2>${t("Breakdown", "分类统计")}</h2><label>${t("Group by", "分类维度")}<select id="breakdown-axis">${options(
      [
        ["group_id", t("Group", "分组")],
        ["challenge", t("Challenge", "挑战")],
        ["subchallenge", t("Subchallenge", "子挑战")],
        ["craft", t("Spacecraft", "航天器")],
        ["mission", t("Mission", "任务")],
        ["capability", t("Capability", "能力")],
        ["difficulty", t("Difficulty", "难度")],
        ["template", t("Template", "模板")],
      ],
      "group_id",
    )}</select></label></div><div id="breakdown"></div>`;
  $("#experiment-content").insertAdjacentHTML(
    "beforeend",
    `<details class="settings" data-measurements><summary>${t("Timing & reported usage", "耗时与已报告用量")}</summary><div id="measurements"></div></details>`,
  );
}

function pagination(value, prefix) {
  return `<span>${value.total ? value.offset + 1 : 0}–${Math.min(value.offset + value.limit, value.total)} / ${fmt(value.total, 0)}</span>${button(prefix + "-prev", "←", `aria-label="${t("Previous page", "上一页")}" ${value.offset === 0 ? "disabled" : ""}`, "quiet")}${button(prefix + "-next", "→", `aria-label="${t("Next page", "下一页")}" ${value.offset + value.limit >= value.total ? "disabled" : ""}`, "quiet")}`;
}

async function loadResults() {
  if (!$("#result-table")) return;
  const seq = ui.sequence,
    id = ui.route.id;
  const request = requestSlot("results");
  const filters = {
    group_id: $("#result-group").value,
    status: $("#result-status").value,
    search: $("#result-search").value,
  };
  const [values, stats] = await Promise.all([
    api(
      experimentPath(id) +
        "/results?" +
        query({ ...filters, offset: ui.resultOffset, limit: 40 }),
      request,
    ),
    api(
      experimentPath(id) +
        "/statistics?" +
        query({ ...filters, axis: $("#breakdown-axis").value }),
      request,
    ),
  ]);
  if (
    seq !== ui.sequence ||
    request.generation !== ui.generations.results ||
    !$("#result-table")
  )
    return;
  $("#result-table").innerHTML = values.items.length
    ? `<div class="table-wrap"><table><thead><tr><th>${t("Case", "题目")}</th><th>${t("Group", "分组")}</th><th>${t("Repeat", "重复")}</th><th>${t("Status", "状态")}</th><th class="number">${t("Score", "得分")}</th><th class="number">${t("Elapsed", "耗时")}</th><th>${t("Attempt", "尝试")}</th></tr></thead><tbody>${values.items.map((row) => `<tr><td>${button("result-detail", esc(row.case_id), `data-group-id="${row.group_id}" data-case="${esc(row.case_id)}" data-repetition="${row.repetition}"`, "link mono")}</td><td class="wrap">${esc(groupName(row.group_id))}</td><td>${row.repetition}</td><td>${statusHTML(row.status)}</td><td class="number">${fmt(row.score)}</td><td class="number">${seconds(row.elapsed_s)}</td><td>${row.attempt ?? "—"}</td></tr>`).join("")}</tbody></table></div>`
    : `<div class="empty">${t("No matching results", "没有符合条件的结果")}</div>`;
  $("#result-pages").innerHTML = pagination(values, "results");
  $("#result-metrics").innerHTML = metricsHTML(stats.overall);
  $("#breakdown").innerHTML =
    stats.items
      .map(
        (row) =>
          `<div class="stat-row"><span class="label">${esc(stats.axis === "group_id" ? groupName(row.label) : row.label)}</span><meter min="0" max="100" value="${row.mean_score ?? 0}" aria-label="${esc(row.label)} ${t("mean score", "平均分")}"></meter><span class="number">${fmt(row.mean_score)}</span><span class="number muted">${row.scored} / ${row.total}</span></div>`,
      )
      .join("") +
    (stats.axis === "capability"
      ? `<p class="chart-note">${t("A case can belong to more than one capability.", "同一道题可能涉及多项能力。")}</p>`
      : "");
  if ($("[data-measurements]")?.open) await measurements();
}

async function measurements() {
  const request = requestSlot("measurements");
  const values = await api(
    experimentPath() +
      "/measurements?" +
      query({
        group_id: $("#result-group")?.value,
        status: $("#result-status")?.value,
        search: $("#result-search")?.value,
      }),
    request,
  );
  if (!$("#measurements") || request.generation !== ui.generations.measurements)
    return;
  $("#measurements").innerHTML =
    `<div class="table-wrap"><table><thead><tr><th>${t("Stage", "阶段")}</th><th>${t("Mean time", "平均耗时")}</th><th>${t("Measured cases", "已测量题目")}</th></tr></thead><tbody>${values.stages.map((row) => `<tr><td>${esc(row.stage)}</td><td>${seconds(row.mean_s)}</td><td>${row.measured} / ${values.total}</td></tr>`).join("")}</tbody></table></div>` +
    (values.usage.length
      ? `<div class="table-wrap"><table><thead><tr><th>${t("Reported usage", "已报告用量")}</th><th>${t("Total", "合计")}</th><th>${t("Reporting cases", "有报告的题目")}</th></tr></thead><tbody>${values.usage.map((row) => `<tr><td>${esc(row.metric)}</td><td>${fmt(row.reported_total, 0)}</td><td>${row.reported_cases} / ${values.total}</td></tr>`).join("")}</tbody></table></div>`
      : `<p class="info-line">${t("The adapter did not report usage.", "适配器未报告用量。")}</p>`);
}

function renderCompare() {
  const groups = draft().groups.map((g) => [g.id, g.name]);
  $("#experiment-content").innerHTML =
    `<div class="two-columns"><label>${t("Reference group", "基准分组")}<select id="compare-left">${options(groups, groups[0]?.[0])}</select></label><label>${t("Comparison group", "比较分组")}<select id="compare-right">${options(groups, groups[1]?.[0] || groups[0]?.[0])}</select></label></div><div id="comparison"></div>`;
}

async function loadComparison() {
  if (!$("#compare-left")) return;
  const seq = ui.sequence;
  const request = requestSlot("comparison");
  const left = $("#compare-left").value,
    right = $("#compare-right").value;
  if (left === right) {
    $("#comparison").innerHTML =
      `<div class="empty">${t("Choose two different groups.", "请选择两个不同分组。")}</div>`;
    return;
  }
  const result = await api(
    "/api/compare?" +
      query({
        left_experiment: ui.route.id,
        left_group: left,
        right_experiment: ui.route.id,
        right_group: right,
      }),
    request,
  );
  if (
    seq !== ui.sequence ||
    request.generation !== ui.generations.comparison ||
    !$("#comparison")
  )
    return;
  if (!result.comparable) {
    $("#comparison").innerHTML =
      `<p class="info-line">${t("Select the same dataset, cases and repetition count. Verified v1 releases can be compared across versions.", "请选择相同的数据集、题目和重复次数。已核验的 v1 正式版本支持跨版本比较。")}</p>`;
    return;
  }
  $("#comparison").innerHTML =
    `<dl class="metrics"><div class="metric"><dt>${t("Paired cases", "已配对评分")}</dt><dd>${result.paired} <small>/ ${result.total}</small></dd></div><div class="metric"><dt>${t("Mean difference · comparison − reference", "平均差 · 比较组 − 基准组")}</dt><dd>${result.mean_difference > 0 ? "+" : ""}${fmt(result.mean_difference)}</dd></div><div class="metric"><dt>${t("Comparison wins", "比较组更高")}</dt><dd>${result.right_wins ?? 0}</dd></div><div class="metric"><dt>${t("Reference wins / ties", "基准组更高 / 持平")}</dt><dd>${result.left_wins ?? 0} <small>/ ${result.ties ?? 0}</small></dd></div></dl><div class="table-wrap"><table><thead><tr><th>${t("Group", "分组")}</th><th>${t("Scored", "已评分")}</th><th>${t("Mean", "均分")}</th><th>${t("Failed", "失败")}</th><th>${t("Unsupported", "不支持")}</th></tr></thead><tbody>${[
      [left, result.left],
      [right, result.right],
    ]
      .map(
        ([id, row]) =>
          `<tr><td class="wrap">${esc(groupName(id))}</td><td>${row.scored} / ${row.total}</td><td>${fmt(row.mean_score)}</td><td>${row.failed}</td><td>${row.unsupported}</td></tr>`,
      )
      .join(
        "",
      )}</tbody></table></div><p class="info-line">${t("Differences use only cases scored in both groups. Failures and missing results are not zero scores.", "差值仅使用两组都已评分的配对题目，失败和缺失结果不计为零分。")}</p>`;
}

function renderCases() {
  $("#main").innerHTML =
    `<div class="page-heading"><h1>${t("Case catalog", "题库")}</h1><span class="muted">${ui.boot.bank?.task_count || 0} ${t("cases", "题")} · 30 ${t("history rounds", "轮历史")}</span></div><div class="filter-row"><label class="wide">${t("Search", "搜索")}<input id="case-search" type="search" placeholder="${t("Case ID or template name", "题目 ID 或模板名称")}"></label><label>${t("Template", "模板")}<select id="case-template">${options(
      (ui.boot.bank?.templates || []).map((row) => [
        row.id,
        `${row.id} · ${lang === "zh" ? row.name : row.english}`,
      ]),
      "",
      t("All templates", "全部模板"),
    )}</select></label><label>${t("Difficulty", "难度")}<select id="case-difficulty">${options(
      [
        ["easy", t("Easy", "简单")],
        ["medium", t("Medium", "中等")],
        ["hard", t("Hard", "困难")],
      ],
      "",
      t("All difficulties", "全部难度"),
    )}</select></label></div><div id="case-table"></div><div id="case-pages" class="pagination"></div>${settingsHTML()}`;
}

async function loadCases() {
  if (!$("#case-table") || !ui.boot.bank) return;
  const seq = ui.sequence;
  const request = requestSlot("cases");
  const result = await api(
    "/api/catalog?" +
      query({
        search: $("#case-search").value,
        template: $("#case-template").value,
        difficulty: $("#case-difficulty").value,
        offset: ui.caseOffset,
        limit: 40,
      }),
    request,
  );
  if (
    seq !== ui.sequence ||
    request.generation !== ui.generations.cases ||
    !$("#case-table")
  )
    return;
  const names = new Map(
    ui.boot.bank.templates.map((row) => [
      row.id,
      lang === "zh" ? row.name : row.english,
    ]),
  );
  $("#case-table").innerHTML = result.items.length
    ? `<div class="table-wrap"><table><thead><tr><th>${t("Case", "题目")}</th><th>${t("Template", "模板")}</th><th>${t("Difficulty", "难度")}</th></tr></thead><tbody>${result.items.map((row) => `<tr><td>${button("preview", esc(row.case_id), `data-case="${esc(row.case_id)}"`, "link mono")}</td><td class="wrap">${esc(names.get(row.template))}</td><td>${esc(row.difficulty)}</td></tr>`).join("")}</tbody></table></div>`
    : `<div class="empty">${t("No matching cases", "没有符合条件的题目")}</div>`;
  $("#case-pages").innerHTML = pagination(result, "cases");
}

async function refreshAdapters() {
  ui.boot.adapters = (await api("/api/adapters")).items;
}
function renderAdapters() {
  $("#main").innerHTML =
    `<div class="page-heading"><h1>${t("Adapters", "适配器")}</h1><div class="actions">${button("import-adapter", t("Import JSON", "导入 JSON"))}${button("new-adapter", t("+ New adapter", "＋ 新建适配器"), "", "primary")}</div></div><div class="adapter-list">${ui.boot.adapters.map((row) => `<article class="adapter-row"><div><strong>${esc(row.name)}</strong>${row.parallel_safe ? `<p class="info-line">${t("Parallel execution enabled", "已启用并行执行")}</p>` : ""}</div><div class="actions">${button("check-adapter", t("Check", "检查"), `data-id="${row.id}"`)}${button("edit-adapter", t("Edit", "编辑"), `data-id="${row.id}"`, "quiet")}</div></article>`).join("") || `<div class="empty"><h2>${t("Connect your agent", "接入你的智能体")}</h2><p>${t("Import an adapter JSON or start with the offline example.", "导入适配器 JSON，或从离线示例开始。")}</p><a href="#guide">${t("View the adapter contract", "查看适配器契约")}</a></div>`}</div><p class="info-line">${t("Configuration checks do not send model requests. Use a one-case experiment to test the full protocol.", "配置检查不会发送模型请求。用单题实验验证完整协议。")}</p>`;
}

function openDialog(title, html, state) {
  ui.dialog = state;
  $("#dialog-title").textContent = title;
  $("#dialog-content").innerHTML = html;
  if (!$("#dialog").open) $("#dialog").showModal();
}

function templates(index) {
  const group = draft().groups[index];
  const selected = new Set(group.selection.templates || []);
  openDialog(
    t("Select templates", "选择模板"),
    `<input id="template-search" type="search" aria-label="${t("Search templates", "搜索模板")}" placeholder="${t("Search templates…", "搜索模板…")}"><div class="actions">${button("templates-all", t("All templates", "全部模板"), "", "quiet")}${button("templates-none", t("Clear selection", "清空选择"), "", "quiet")}</div><div id="template-list" class="template-list"></div><div id="template-pages" class="pagination"></div><div class="dialog-actions"><span id="template-count" class="muted"></span>${button("templates-apply", t("Apply", "应用"), "", "primary")}</div>`,
    { kind: "templates", index, selected, all: !selected.size, offset: 0 },
  );
  renderTemplates();
}

function renderTemplates() {
  const dialog = ui.dialog;
  const search = ($("#template-search")?.value || "").toLocaleLowerCase();
  const rows = (ui.boot.bank?.templates || []).filter((row) =>
    `${row.id} ${row.name} ${row.english}`.toLocaleLowerCase().includes(search),
  );
  $("#template-list").innerHTML = rows
    .slice(dialog.offset, dialog.offset + 40)
    .map(
      (row) =>
        `<label class="template-choice"><input type="checkbox" data-template="${row.id}" ${dialog.all || dialog.selected.has(row.id) ? "checked" : ""}><span><code>${row.id}</code>${esc(lang === "zh" ? row.name : row.english)}</span></label>`,
    )
    .join("");
  $("#template-pages").innerHTML = pagination(
    { offset: dialog.offset, limit: 40, total: rows.length },
    "templates",
  );
  $("#template-count").textContent = t(
    `${dialog.all ? 140 : dialog.selected.size} selected`,
    `已选 ${dialog.all ? 140 : dialog.selected.size} 个`,
  );
}

function publicPayload(value) {
  const images = [];
  function clean(item) {
    if (Array.isArray(item)) return item.map(clean);
    if (item && typeof item === "object")
      return Object.fromEntries(
        Object.entries(item)
          .filter(([key, val]) => {
            if (key === "images" && Array.isArray(val)) {
              images.push(...val);
              return false;
            }
            return true;
          })
          .map(([key, val]) => [key, clean(val)]),
      );
    return item;
  }
  const copy = clean(value);
  return `<pre>${esc(JSON.stringify(copy, null, 2))}</pre>${images.length ? `<details data-images="${esc(JSON.stringify(images))}"><summary>${t(`Show ${images.length} image attachments`, `显示 ${images.length} 张图片附件`)}</summary><div class="preview-images"></div></details>` : ""}`;
}

async function preview(caseId) {
  openDialog(
    caseId,
    `<label>${t("Input", "输入")}<select id="preview-round">${options([["", t("Current task", "当前任务")], ...Array.from({ length: 30 }, (_, i) => [String(i + 1), t(`History round ${i + 1}`, `历史第 ${i + 1} 轮`)])], "")}</select></label><div id="preview-body"></div>`,
    { kind: "preview", caseId, generation: 0 },
  );
  await loadPreview();
}

async function loadPreview() {
  const dialog = ui.dialog,
    generation = ++dialog.generation;
  const result = await api(
    "/api/task?" +
      query({ case_id: dialog.caseId, round: $("#preview-round").value }),
  );
  if (ui.dialog !== dialog || dialog.generation !== generation) return;
  $("#preview-body").innerHTML = publicPayload(result.input || result.public);
}

async function resultDetail(groupId, caseId, repetition, attempt) {
  const experimentId = ui.route.id;
  const params = { group_id: groupId, case_id: caseId, repetition, attempt };
  const result = await api(
    experimentPath(experimentId) + "/result?" + query(params),
  );
  const r = result.result;
  openDialog(
    caseId,
    `<div class="detail-meta">${statusHTML(r?.status || result.row.status)}<span>${t("Score", "得分")} ${fmt(r?.outcome?.score)}</span><span>${seconds(r?.elapsed_s)}</span><label>${t("Attempt", "尝试")}<select id="result-attempt">${options(
      result.attempts.map((n) => [n, String(n)]),
      result.attempt,
    )}</select></label></div>${r?.error ? `<p class="error">${esc(r.error)}</p>` : ""}${r?.usage ? `<details><summary>${t("Reported usage", "已报告用量")}</summary><pre>${esc(JSON.stringify(r.usage, null, 2))}</pre></details>` : ""}${r?.timing ? `<details><summary>${t("Stage timing", "阶段耗时")}</summary><pre>${esc(JSON.stringify(r.timing.stages, null, 2))}</pre></details>` : ""}<div class="section-heading"><h3>${t("Interactions", "交互记录")}</h3></div><div id="events"></div>${button("events-more", t("Load interactions", "加载交互记录"), "", "quiet")}`,
    {
      kind: "result",
      experimentId,
      params: { ...params, attempt: result.attempt },
      cursor: 0,
    },
  );
}

async function loadEvents() {
  const dialog = ui.dialog;
  dialog.cursors ||= [0];
  dialog.page ??= 0;
  const result = await api(
    experimentPath(dialog.experimentId) +
      "/events?" +
      query({
        ...dialog.params,
        cursor: dialog.cursors[dialog.page],
        limit: 10,
      }),
  );
  if (ui.dialog !== dialog) return;
  const list = $("#events");
  dialog.events = result.items;
  list.innerHTML = result.items
    .map(
      (row, i) =>
        `<details class="event" data-event-index="${i}"><summary>${esc(row.operation || row.event)} · ${esc(row.event)} ${row.history_round ? `· ${row.history_round}/30` : ""}</summary></details>`,
    )
    .join("");
  dialog.cursors[dialog.page + 1] = result.next_cursor;
  if (!$('[data-action="events-prev"]'))
    list.insertAdjacentHTML(
      "afterend",
      button(
        "events-prev",
        t("Previous interactions", "上一页交互"),
        "",
        "quiet",
      ),
    );
  $('[data-action="events-prev"]').disabled = dialog.page === 0;
  const control = $('[data-action="events-more"]');
  dialog.waiting = result.waiting_for_complete_record;
  control.textContent = dialog.waiting
    ? t("Refresh interactions", "刷新交互记录")
    : t("Next interactions", "下一页交互");
  control.hidden = !result.has_more && !dialog.waiting;
  if (!result.items.length && !list.children.length)
    list.innerHTML = `<p class="info-line">${t("No interactions recorded yet.", "暂无交互记录。")}</p>`;
}

async function adapterDialog(id, importing = false) {
  const value = id ? await api("/api/adapters/" + id) : null;
  const definition = value?.definition || {
    name: "My adapter",
    argv: ["${PYTHON}", "adapter.py"],
    config: {},
    pass_env: [],
    timeout_s: 7200,
  };
  openDialog(
    importing
      ? t("Import adapter", "导入适配器")
      : t("Adapter configuration", "适配器配置"),
    `<form id="adapter-form" class="form-stack">${importing ? `<label>${t("Adapter JSON path", "适配器 JSON 路径")}<input id="adapter-path" required spellcheck="false" placeholder="examples/random-adapter.json"></label>` : `<label>${t("Resolve relative files from", "相对文件路径基准目录")}<input id="adapter-directory" spellcheck="false" placeholder="${t("Current server directory", "服务启动目录")}"></label><label>JSON<textarea id="adapter-json" class="adapter-code" spellcheck="false" required>${esc(JSON.stringify(definition, null, 2))}</textarea></label>`}<div class="checks"><label><input id="parallel-safe" type="checkbox" ${value?.parallel_safe ? "checked" : ""}>${t("Each process isolates its external session and memory", "每个进程都隔离外部会话和记忆")}</label></div><div class="dialog-actions"><a href="#guide" data-action="close-dialog">${t("Adapter contract", "适配器契约")}</a><button type="submit" class="primary">${t("Save adapter", "保存适配器")}</button></div></form>`,
    { kind: "adapter", id, importing },
  );
}

function renderGuide() {
  $("#main").innerHTML =
    `<div class="page-heading"><h1>${t("Integration guide", "接入指南")}</h1><span class="mono">astromembench/2</span></div><article class="guide"><section><h2>${t("Run your first experiment", "运行第一个实验")}</h2><ol><li>${t("Import <code>examples/random-adapter.json</code> under Adapters. It runs offline and demonstrates the protocol.", "在「适配器」中导入 <code>examples/random-adapter.json</code>。此示例离线运行，用于演示协议。")}</li><li>${t("Create an experiment, select the adapter and one case, then run it.", "新建实验，选择适配器和一道题，然后运行。")}</li><li>${t("Open Results to inspect the score, attempts and full interaction trace.", "在「结果」中查看评分、各次尝试和完整交互记录。")}</li></ol></section><section><h2>${t("Your adapter owns the agent", "适配器负责你的智能体")}</h2><p>${t("Implement model calls, memory, retrieval, native session creation, credentials and service deployment in your adapter. The evaluator supplies public inputs, applies actions and scores the outcome.", "模型调用、记忆、检索、原生会话创建、凭据及服务部署由适配器实现。评测器负责提供公开输入、执行动作并评分。")}</p><p>${t("The adapter is a trusted local command. Keep API keys in environment variables, and declare only their names in <code>pass_env</code> or <code>credential_env</code>.", "适配器是你信任的本机命令。API 密钥放在环境变量中，仅在 <code>pass_env</code> 或 <code>credential_env</code> 中声明变量名称。")}</p></section><section><h2>${t("Six operations", "六个操作")}</h2><div class="table-wrap"><table><thead><tr><th>${t("Operation", "操作")}</th><th>${t("Required behavior", "必须遵守的行为")}</th></tr></thead><tbody>${[
      [
        "reset",
        t(
          "Clear all case-owned memory and sessions; reply cleared: true.",
          "清空当前用例的记忆和会话，返回 cleared: true。",
        ),
      ],
      [
        "new_session",
        t(
          "Create a native session and return a new conversation_id. Preserve memory across the within-case boundary.",
          "创建原生会话并返回新的 conversation_id；用例内跨会话时保留记忆。",
        ),
      ],
      [
        "history",
        t(
          "Process the supplied history completely before acknowledging processed: true. Do not execute actions.",
          "完成该轮历史处理后才返回 processed: true，禁止执行动作。",
        ),
      ],
      [
        "observe",
        t(
          "Use only the public observation and return action_submitted: true with an action.",
          "仅使用公开观测，返回 action_submitted: true 和 action。",
        ),
      ],
      [
        "feedback",
        t(
          "Process the action result; acknowledge processed: true.",
          "处理动作反馈，返回 processed: true。",
        ),
      ],
      [
        "end",
        t(
          "Finish the case and clean up owned resources; acknowledge processed: true.",
          "完成用例并清理其资源，返回 processed: true。",
        ),
      ],
    ]
      .map(
        ([op, description]) =>
          `<tr><td><code>${op}</code></td><td class="wrap">${description}</td></tr>`,
      )
      .join(
        "",
      )}</tbody></table></div></section><section><h2>JSONL</h2><p>${t("One request and response per line. Echo the request id exactly. stdout contains JSONL only; diagnostics go to stderr. Never read benchmark answers or evaluator files.", "每行一个请求或响应，原样回传请求 id。stdout 仅输出 JSONL，诊断写入 stderr。禁止读取题目答案或评测器内部文件。")}</p><pre>{"protocol":"astromembench/2","id":1,"operation":"reset","payload":{}}
{"id":1,"result":{"cleared":true}}</pre><p>${t("Return structured errors with kind <code>agent</code>, <code>unsupported</code> or <code>infrastructure</code>. Infrastructure failures are unscored. A subject failure can end a case with zero or partial credit. Resume skips all scored cases.", "错误使用结构化 kind：<code>agent</code>、<code>unsupported</code> 或 <code>infrastructure</code>。基础设施故障不计分。智能体失败时可产生零分或保留已取得的部分分数。恢复时跳过所有已计分题目。")}</p></section><section><h2>${t("Sessions and concurrency", "会话与并发")}</h2><p>${t("Same session: all 30 history rounds and the current task share a conversation. New session: start another native conversation after history while retaining case memory. Each case starts with reset.", "同一会话：30 轮历史与当前任务共用一个会话。跨会话：历史结束后新建原生会话，保留当前用例的记忆。每道题都从 reset 开始。")}</p><p>${t("Parallel groups require isolated remote memory and session namespaces for each process. If a backend shares mutable state, keep concurrency at 1. Pause drains active cases; Stop interrupts current adapter calls. Workers continue when the UI closes.", "并行分组要求每个进程使用独立的远程记忆和会话命名空间。如果后端共享可变状态，请将并发保持为 1。暂停会等待当前用例结束；停止会中断当前适配器调用。关闭 UI 不会终止后台实验。")}</p></section><section><h2>${t("Timing and optional usage", "耗时与可选用量")}</h2><p>${t("Timing is measured by the evaluator. A reply may include usage with nonnegative per-operation deltas: input_tokens, output_tokens, cached_input_tokens, model_calls. Do not send cumulative session counters. Missing usage remains unknown; costs are not inferred.", "耗时由评测器测量。响应可选附带 usage，提供本次操作的非负增量：input_tokens、output_tokens、cached_input_tokens、model_calls。不得传入会话累计计数。未报告用量保持未知，不推算费用。")}</p></section><section><h2>${t("Files and interfaces", "文件与接口")}</h2><p>${t("The workspace holds experiment definitions, result indexes and original attempts. Use the same --workspace when reopening the server or controlling workers from the CLI.", "工作目录保存实验定义、结果索引和原始尝试。重开服务或通过 CLI 控制进程时，使用相同的 --workspace。")}</p><pre>astromembench webui --data data/benchmark --workspace runs/workbench
astromembench experiment --workspace runs/workbench list
astromembench experiment --workspace runs/workbench pause EXPERIMENT_ID</pre><p>${t("See <code>docs/adapters.md</code> for the full protocol and <code>docs/workbench.md</code> for experiment schemas, HTTP endpoints and CLI examples.", "完整协议见 <code>docs/adapters.md</code>；实验结构、HTTP 接口与 CLI 示例见 <code>docs/workbench.md</code>。")}</p></section></article>`;
}

async function estimate(index) {
  const group = draft()?.groups[index];
  if (!group) return;
  const id = ui.route.id,
    serialized = JSON.stringify(group.selection);
  try {
    const value = await api("/api/selection", {
      body: { selection: group.selection },
    });
    if (
      ui.route.id === id &&
      draft()?.groups[index] === group &&
      JSON.stringify(group.selection) === serialized
    ) {
      const node = $(`#group-count-${index}`);
      if (node)
        node.textContent = t(
          `${fmt(value.total, 0)} cases`,
          `${fmt(value.total, 0)} 题`,
        );
    }
  } catch (exc) {
    if (ui.route.id === id && $(`#group-count-${index}`))
      $(`#group-count-${index}`).textContent = t("Check selection", "检查选题");
  }
}

async function act(action, node) {
  const index = Number(node.dataset.index),
    value = draft();
  switch (action) {
    case "new":
      ui.drafts.set("new", newDraft());
      location.hash = "#experiments/new/design";
      if (ui.route.id === "new") await navigate();
      break;
    case "save": {
      const id = await saveDraft();
      location.hash = `#experiments/${id}/design`;
      if (ui.route.id === id) await navigate();
      notify(t("Experiment saved", "实验已保存"));
      break;
    }
    case "start": {
      const id =
        ui.route.id === "new" || ui.detail?.status === "draft"
          ? await saveDraft()
          : ui.route.id;
      await api(experimentPath(id) + "/start", { body: {} });
      location.hash = `#experiments/${id}/monitor`;
      if (ui.route.id === id && ui.route.view === "monitor") await navigate();
      break;
    }
    case "pause":
    case "stop":
      ui.state = await api(experimentPath() + "/" + action, { body: {} });
      renderLive();
      break;
    case "copy-experiment": {
      const copy = structuredClone(value);
      delete copy.appending;
      copy.groups.forEach((g) => {
        delete g.id;
        delete g.case_ids;
      });
      copy.name = t(`${copy.name} copy`, `${copy.name} 副本`);
      copy.dirty = true;
      ui.drafts.set("new", copy);
      location.hash = "#experiments/new/design";
      break;
    }
    case "toggle-group":
      value.expanded = value.expanded === index ? -1 : index;
      renderDesign();
      break;
    case "add-group":
      value.groups.push(groupDefault(value.groups.length + 1));
      value.expanded = value.groups.length - 1;
      dirty();
      renderDesign();
      break;
    case "copy-group": {
      const copy = structuredClone(value.groups[index]);
      delete copy.id;
      delete copy.case_ids;
      copy.name = t(`${copy.name} copy`, `${copy.name} 副本`);
      value.groups.splice(index + 1, 0, copy);
      value.expanded = index + 1;
      dirty();
      renderDesign();
      break;
    }
    case "up-group":
    case "down-group": {
      const next = index + (action === "up-group" ? -1 : 1);
      if (value.appending && next < value.originalCount) break;
      [value.groups[index], value.groups[next]] = [
        value.groups[next],
        value.groups[index],
      ];
      value.expanded = next;
      dirty();
      renderDesign();
      break;
    }
    case "remove-group":
      value.groups.splice(index, 1);
      value.expanded = Math.min(index, value.groups.length - 1);
      dirty();
      renderDesign();
      break;
    case "append-groups":
      value.appending = true;
      value.originalCount = value.groups.length;
      value.groups.push(groupDefault(value.groups.length + 1));
      value.expanded = value.groups.length - 1;
      dirty();
      renderDesign();
      break;
    case "save-append":
      await saveDraft(true);
      await navigate();
      notify(t("Groups appended", "分组已追加"));
      break;
    case "templates":
      templates(index);
      break;
    case "templates-all":
      ui.dialog.all = true;
      ui.dialog.selected.clear();
      renderTemplates();
      break;
    case "templates-none":
      ui.dialog.all = false;
      ui.dialog.selected.clear();
      renderTemplates();
      break;
    case "templates-apply": {
      if (!ui.dialog.all && !ui.dialog.selected.size)
        throw new Error(
          t("Select at least one template", "请至少选择一个模板"),
        );
      const i = ui.dialog.index;
      value.groups[i].selection.templates = ui.dialog.all
        ? []
        : [...ui.dialog.selected];
      delete value.groups[i].case_ids;
      dirty();
      $("#dialog").close();
      renderDesign();
      await estimate(i);
      break;
    }
    case "close-dialog":
      $("#dialog").close();
      break;
    case "history-prev":
    case "history-next":
      ui.historyOffset = Math.max(
        0,
        ui.historyOffset + (action.endsWith("next") ? 15 : -15),
      );
      await history();
      break;
    case "results-prev":
    case "results-next":
      ui.resultOffset = Math.max(
        0,
        ui.resultOffset + (action.endsWith("next") ? 40 : -40),
      );
      await loadResults();
      break;
    case "cases-prev":
    case "cases-next":
      ui.caseOffset = Math.max(
        0,
        ui.caseOffset + (action.endsWith("next") ? 40 : -40),
      );
      await loadCases();
      break;
    case "templates-prev":
    case "templates-next":
      ui.dialog.offset = Math.max(
        0,
        ui.dialog.offset + (action.endsWith("next") ? 40 : -40),
      );
      renderTemplates();
      break;
    case "preview":
      await preview(node.dataset.case);
      break;
    case "result-detail":
      await resultDetail(
        node.dataset.groupId,
        node.dataset.case,
        Number(node.dataset.repetition),
      );
      break;
    case "events-more":
      if (ui.dialog.events && !ui.dialog.waiting) ui.dialog.page++;
      await loadEvents();
      break;
    case "events-prev":
      ui.dialog.page = Math.max(0, ui.dialog.page - 1);
      await loadEvents();
      break;
    case "import-run":
      openDialog(
        t("Open saved CLI results", "打开已保存的 CLI 结果"),
        `<form id="import-run-form" class="form-stack"><label>${t("Run directory", "运行结果目录")}<input id="import-run-path" required spellcheck="false" placeholder="runs/quickstart"></label><button type="submit" class="primary">${t("Open", "打开")}</button></form>`,
        { kind: "import-run" },
      );
      break;
    case "import-adapter":
      await adapterDialog(null, true);
      break;
    case "new-adapter":
      await adapterDialog();
      break;
    case "edit-adapter":
      await adapterDialog(node.dataset.id);
      break;
    case "check-adapter": {
      const check = await api("/api/adapters/check", {
        body: { id: node.dataset.id },
      });
      if (!check.valid)
        throw new Error(
          t("Configuration incomplete: ", "配置不完整：") +
            (!check.executable_available
              ? t("executable unavailable", "找不到可执行文件")
              : "") +
            check.missing_environment.join(", "),
        );
      notify(
        t("Configuration valid · no model calls", "配置有效 · 未调用模型"),
      );
      break;
    }
  }
}

document.addEventListener("click", async (event) => {
  if (event.target.closest(".skip-link")) {
    event.preventDefault();
    $("#main").focus();
    return;
  }
  const node = event.target.closest("[data-action]");
  if (!node || node.disabled || node.dataset.pending) return;
  if (node.tagName === "BUTTON") event.preventDefault();
  node.dataset.pending = "true";
  node.setAttribute("aria-busy", "true");
  try {
    await act(node.dataset.action, node);
  } catch (exc) {
    if (exc.name !== "AbortError")
      error(exc.message, $("#dialog").open ? $("#dialog-content") : $("#main"));
  } finally {
    delete node.dataset.pending;
    node.removeAttribute("aria-busy");
  }
});

document.addEventListener("input", (event) => {
  const node = event.target;
  if (node.id === "experiment-name") {
    draft().name = node.value;
    dirty();
    return;
  }
  if (node.id === "concurrency") {
    draft().concurrency = Number(node.value);
    dirty();
    return;
  }
  const groupNode = node.closest("[data-group]");
  if (groupNode && (node.dataset.field || node.dataset.difficulty)) {
    const index = Number(groupNode.dataset.group),
      group = draft().groups[index],
      field = node.dataset.field;
    if (node.dataset.difficulty) {
      const chosen = $$("[data-difficulty]:checked", groupNode).map(
        (input) => input.dataset.difficulty,
      );
      group.selection.difficulties = chosen;
      if (!chosen.length) group.selection.difficulties = ["__none__"];
    } else if (field === "limit") {
      if (node.value) group.selection.limit = Number(node.value);
      else delete group.selection.limit;
    } else if (field === "case_ids")
      group.selection.case_ids = node.value.split(/[\s,;]+/).filter(Boolean);
    else
      group[field] = field === "repetitions" ? Number(node.value) : node.value;
    if (field === "name") $(".group-title", groupNode).textContent = node.value;
    delete group.case_ids;
    dirty();
    clearTimeout(ui.selectionTimers.get(index));
    ui.selectionTimers.set(
      index,
      setTimeout(() => estimate(index), 250),
    );
    return;
  }
  if (node.dataset.template) {
    const dialog = ui.dialog;
    if (dialog.all) {
      dialog.all = false;
      dialog.selected = new Set(ui.boot.bank.templates.map((row) => row.id));
    }
    if (node.checked) dialog.selected.add(node.dataset.template);
    else dialog.selected.delete(node.dataset.template);
    $("#template-count").textContent = t(
      `${dialog.selected.size} selected`,
      `已选 ${dialog.selected.size} 个`,
    );
    return;
  }
  if (node.id === "template-search") {
    ui.dialog.offset = 0;
    renderTemplates();
    return;
  }
  if (node.id === "history-search") {
    ui.historySearch = node.value;
    ui.historyOffset = 0;
    clearTimeout(ui.filterTimer);
    ui.filterTimer = setTimeout(() => history().catch(report), 250);
    return;
  }
  if (["case-search", "result-search"].includes(node.id)) {
    clearTimeout(ui.filterTimer);
    ui.filterTimer = setTimeout(() => {
      if (node.id === "case-search") {
        ui.caseOffset = 0;
        loadCases().catch(report);
      } else {
        ui.resultOffset = 0;
        loadResults().catch(report);
      }
    }, 220);
  }
});

document.addEventListener("change", async (event) => {
  const id = event.target.id;
  try {
    if (["case-template", "case-difficulty"].includes(id)) {
      ui.caseOffset = 0;
      await loadCases();
    }
    if (["result-group", "result-status", "breakdown-axis"].includes(id)) {
      ui.resultOffset = 0;
      await loadResults();
    }
    if (["compare-left", "compare-right"].includes(id)) await loadComparison();
    if (id === "preview-round") await loadPreview();
    if (id === "result-attempt") {
      const d = ui.dialog;
      await resultDetail(
        d.params.group_id,
        d.params.case_id,
        d.params.repetition,
        Number(event.target.value),
      );
    }
  } catch (exc) {
    if (exc.name !== "AbortError")
      error(exc.message, $("#dialog").open ? $("#dialog-content") : $("#main"));
  }
});

document.addEventListener("submit", async (event) => {
  if (
    !["adapter-form", "bank-form", "import-run-form"].includes(event.target.id)
  )
    return;
  event.preventDefault();
  const submit = $("[type=submit]", event.target);
  submit.disabled = true;
  try {
    if (event.target.id === "import-run-form") {
      const imported = await api("/api/experiments/import", {
        body: { path: $("#import-run-path").value },
      });
      $("#dialog").close();
      location.hash = `#experiments/${imported.id}/results`;
    } else if (event.target.id === "bank-form") {
      ui.boot.bank = await api("/api/bank", {
        body: { data: $("#data-path").value },
      });
      ui.boot.data = ui.boot.bank.data;
      ui.boot.bank_error = null;
      await navigate();
      notify(t("Dataset loaded", "数据集已加载"));
    } else {
      const d = ui.dialog,
        parallel_safe = $("#parallel-safe").checked;
      if (d.importing)
        await api("/api/adapters/import", {
          body: { path: $("#adapter-path").value, parallel_safe },
        });
      else
        await api("/api/adapters/save", {
          body: {
            id: d.id,
            directory: $("#adapter-directory").value,
            definition: JSON.parse($("#adapter-json").value),
            parallel_safe,
          },
        });
      $("#dialog").close();
      await refreshAdapters();
      renderAdapters();
      notify(t("Adapter saved", "适配器已保存"));
    }
  } catch (exc) {
    error(exc.message, $("#dialog").open ? $("#dialog-content") : $("#main"));
  } finally {
    if (submit.isConnected) submit.disabled = false;
  }
});

document.addEventListener(
  "toggle",
  (event) => {
    const details = event.target;
    if (details.open && details.hasAttribute("data-measurements"))
      measurements().catch(report);
    if (
      details.open &&
      details.dataset.eventIndex !== undefined &&
      !details.querySelector("pre")
    ) {
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(
        ui.dialog?.events?.[Number(details.dataset.eventIndex)],
        null,
        2,
      );
      details.append(pre);
    }
    if (
      details.open &&
      details.dataset.images &&
      !$(".preview-images", details).children.length
    ) {
      const images = JSON.parse(details.dataset.images);
      $(".preview-images", details).innerHTML = images
        .map((image, i) => {
          const path = typeof image === "string" ? image : image.path,
            id = typeof image === "string" ? `Image ${i + 1}` : image.id;
          return `<figure><img src="/api/asset?${query({ path })}" loading="lazy" decoding="async" width="640" height="480" alt="${esc(id)}"><figcaption>${esc(id)}</figcaption></figure>`;
        })
        .join("");
    }
  },
  true,
);

$("#dialog").addEventListener("close", () => {
  ui.dialog = null;
  $("#dialog-content").replaceChildren();
});
$("#language").addEventListener("click", () => {
  lang = lang === "zh" ? "en" : "zh";
  try {
    localStorage.setItem("astromembench.language", lang);
  } catch {}
  navigate();
});
window.addEventListener("hashchange", () => {
  if ($("#dialog").open) $("#dialog").close();
  navigate();
});
window.addEventListener("beforeunload", (event) => {
  if ([...ui.drafts.values()].some((d) => d.dirty)) {
    event.preventDefault();
    event.returnValue = "";
  }
});

async function poll() {
  if (polling) return;
  polling = true;
  clearTimeout(pollTimer);
  try {
    if (ui.boot && ui.route.page === "experiments") {
      const seq = ui.sequence,
        id = ui.route.id;
      if (id !== "new") {
        const state = await api(
          experimentPath(id) + "/state?" + query({ since: ui.state?.revision }),
        );
        if (seq === ui.sequence && !state.unchanged) {
          const prior = ui.state;
          ui.state = state;
          if (!state.revision.startsWith(ui.boot.instance + ":"))
            ui.boot = await api("/api/bootstrap");
          renderLive();
          if (
            ui.route.view === "results" &&
            prior?.record_revision !== state.record_revision
          )
            await loadResults();
          if (
            ui.route.view === "compare" &&
            prior?.record_revision !== state.record_revision
          )
            await loadComparison();
        }
      }
      await history();
    }
    $("#connection").hidden = true;
  } catch (exc) {
    if (exc.name !== "AbortError") {
      $("#connection").textContent = t(
        "Connection interrupted. Retrying… Background experiments continue.",
        "连接中断，正在重连… 后台实验继续运行。",
      );
      $("#connection").hidden = false;
    }
  }
  polling = false;
  pollTimer = setTimeout(
    poll,
    document.hidden ? 10000 : activeStates.has(ui.state?.status) ? 500 : 4000,
  );
}

async function boot() {
  try {
    ui.boot = await api("/api/bootstrap");
    await navigate();
    poll();
  } catch (exc) {
    error(exc.message);
    $("#connection").textContent = t("Connecting…", "正在连接…");
    $("#connection").hidden = false;
    setTimeout(boot, 3000);
  }
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(poll, 50);
  }
});
boot();
