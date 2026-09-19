import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const EXTENSION_NAME = "fan.ai.visual.personal.assistant";
const ASSISTANT_NAME = "🚀 帆 AI 视觉个人助手";
const STORAGE_KEY = "fan-ai-assistant-running-starts-v1";

const state = {
  jobs: [],
  balances: [],
  warnings: [],
  root: null,
  refreshTimer: null,
  liveTimer: null,
  runningStarts: loadRunningStarts(),
};

function injectCss() {
  if (document.querySelector("#fan-ai-assistant-css")) return;
  const link = document.createElement("link");
  link.id = "fan-ai-assistant-css";
  link.rel = "stylesheet";
  link.href = new URL("./fan_ai_assistant.css", import.meta.url).href;
  document.head.appendChild(link);
}

function loadRunningStarts() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const value = raw ? JSON.parse(raw) : {};
    return value && typeof value === "object" ? value : {};
  } catch {
    return {};
  }
}

function saveRunningStarts() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.runningStarts));
}

function eventData(event) {
  return event?.detail ?? event ?? {};
}

async function fetchJson(path, options = {}) {
  const response = await api.fetchApi(path, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${body || response.statusText}`);
  }
  return response.json();
}

function toast(severity, summary, detail) {
  app.extensionManager.toast.add({ severity, summary, detail, life: 4000 });
}

function formatDate(timestamp) {
  if (!timestamp) return "未知时间";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(timestamp));
}

function durationMs(job) {
  const start = job.execution_start_time ?? state.runningStarts[job.id];
  if (!start) return null;
  const end = job.execution_end_time ?? (job.status === "in_progress" ? Date.now() : null);
  return end ? Math.max(0, end - start) : null;
}

function formatDuration(job) {
  const duration = durationMs(job);
  if (duration === null) return job.status === "pending" ? "等待执行" : "暂无耗时";
  if (duration < 1000) return `${Math.round(duration)} ms`;
  const seconds = duration / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${Math.floor(seconds % 60)} 秒`;
}

function statusLabel(status) {
  return ({
    pending: "排队中",
    in_progress: "运行中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
  })[status] ?? status ?? "未知";
}

function clone(value) {
  return typeof structuredClone === "function"
    ? structuredClone(value)
    : JSON.parse(JSON.stringify(value));
}

function randomSeed() {
  return Math.floor(Math.random() * 9_000_000_000_000_000);
}

function randomizeKnownSeeds(prompt) {
  const names = new Set(["seed", "noise_seed", "random_seed", "variation_seed"]);
  let changed = 0;
  for (const node of Object.values(prompt ?? {})) {
    if (!node?.inputs) continue;
    for (const [name, value] of Object.entries(node.inputs)) {
      if (names.has(name) && Number.isSafeInteger(value) && value >= 0) {
        node.inputs[name] = randomSeed();
        changed += 1;
      }
    }
  }
  return changed;
}

function previewUrl(preview) {
  if (!preview?.filename) return null;
  const params = new URLSearchParams({
    filename: preview.filename,
    subfolder: preview.subfolder ?? "",
    type: preview.type ?? "output",
  });
  return api.apiURL(`/view?${params.toString()}`);
}

async function refreshJobs() {
  const payload = await fetchJson("/api/jobs?limit=30&sort_by=created_at&sort_order=desc");
  state.jobs = Array.isArray(payload) ? payload : payload.jobs ?? payload.items ?? [];

  for (const job of state.jobs) {
    if (job.execution_start_time && !state.runningStarts[job.id]) {
      state.runningStarts[job.id] = job.execution_start_time;
    }
    if (["completed", "failed", "cancelled"].includes(job.status)) {
      delete state.runningStarts[job.id];
    }
  }
  saveRunningStarts();
}

async function refreshBalances() {
  const payload = await fetchJson("/fan-ai-assistant/api/balances");
  state.balances = payload.balances ?? [];
  state.warnings = payload.warnings ?? [];
}

async function getJobDetail(jobId) {
  return fetchJson(`/api/jobs/${encodeURIComponent(jobId)}`);
}

async function queueWorkflow(prompt, extraData = {}, workflowId = null) {
  const body = { prompt, extra_data: extraData };
  if (workflowId) body.workflow_id = workflowId;
  return fetchJson("/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function rerunJob(jobId, randomize = false) {
  const detail = await getJobDetail(jobId);
  if (!detail.workflow?.prompt) throw new Error("该任务没有可重新执行的 API 工作流数据");

  const prompt = clone(detail.workflow.prompt);
  const extraData = clone(detail.workflow.extra_data ?? {});
  delete extraData.client_id;

  if (randomize && randomizeKnownSeeds(prompt) === 0) {
    toast("warn", ASSISTANT_NAME, "没有识别到 Seed，已按原参数重新执行。");
  }

  const result = await queueWorkflow(prompt, extraData, detail.workflow_id ?? null);
  toast("success", randomize ? "已提交再出生成" : "已提交原样重跑", `任务 ID：${result.prompt_id}`);
  await refreshAndRender();
}

async function loadJobWorkflow(jobId) {
  const detail = await getJobDetail(jobId);
  const uiWorkflow =
    detail.workflow?.extra_data?.extra_pnginfo?.workflow ??
    detail.workflow?.extra_data?.workflow ??
    null;
  if (!uiWorkflow) {
    throw new Error("该任务没有保存前端画布工作流，可能来自外部 API。 ");
  }
  await app.loadGraphData(uiWorkflow);
  toast("success", ASSISTANT_NAME, "工作流已载入画布");
}

async function cancelJob(jobId) {
  const payload = await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
  toast(payload.cancelled ? "success" : "info", ASSISTANT_NAME, payload.cancelled ? "任务已取消" : "任务已结束或无需取消");
  await refreshAndRender();
}

function el(tag, className = "", text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(label, handler, variant = "") {
  const node = el("button", `fan-ai-button ${variant}`.trim(), label);
  node.type = "button";
  node.addEventListener("click", async () => {
    node.disabled = true;
    try {
      await handler();
    } catch (error) {
      console.error(`[${ASSISTANT_NAME}]`, error);
      toast("error", ASSISTANT_NAME, error?.message ?? String(error));
    } finally {
      node.disabled = false;
    }
  });
  return node;
}

function renderBalance(item) {
  const card = el("article", "fan-ai-balance-card");
  const head = el("div", "fan-ai-card-head");
  head.append(
    el("strong", "", item.label ?? item.provider ?? "API"),
    el("span", "fan-ai-badge", item.balance_type ?? "unknown"),
  );
  card.append(head);
  const remaining = item.remaining == null ? "未提供" : `${Number(item.remaining).toFixed(4)} ${item.currency ?? ""}`;
  card.append(el("div", "fan-ai-balance-main", `剩余：${remaining}`));
  if (item.used != null) card.append(el("div", "fan-ai-muted", `已用：${Number(item.used).toFixed(4)} ${item.currency ?? ""}`));
  if (item.budget != null) card.append(el("div", "fan-ai-muted", `预算：${Number(item.budget).toFixed(4)} ${item.currency ?? ""}`));
  return card;
}

function renderJob(job, index) {
  const card = el("article", "fan-ai-job-card");
  const head = el("div", "fan-ai-card-head");
  head.append(
    el("strong", "", index === 0 ? "最近一次任务" : `任务 ${index + 1}`),
    el("span", `fan-ai-status fan-ai-status-${job.status}`, statusLabel(job.status)),
  );
  card.append(head);
  card.append(
    el("div", "fan-ai-job-id", job.workflow_id ? `工作流：${job.workflow_id}` : `任务：${job.id}`),
    el("div", "fan-ai-muted", `创建：${formatDate(job.create_time)}`),
    el("div", "fan-ai-duration", `耗时：${formatDuration(job)}`),
  );

  const url = previewUrl(job.preview_output);
  if (url) {
    const link = el("a", "fan-ai-preview-link");
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    const image = document.createElement("img");
    image.className = "fan-ai-preview";
    image.src = url;
    image.alt = "任务输出预览";
    image.loading = "lazy";
    link.append(image);
    card.append(link);
  }

  const actions = el("div", "fan-ai-actions");
  if (url) actions.append(button("查看输出", async () => window.open(url, "_blank", "noopener,noreferrer")));
  if (["completed", "failed", "cancelled"].includes(job.status)) {
    actions.append(
      button("原样重跑", () => rerunJob(job.id, false)),
      button("再出生成", () => rerunJob(job.id, true), "primary"),
      button("载入画布", () => loadJobWorkflow(job.id)),
    );
  }
  if (["pending", "in_progress"].includes(job.status)) {
    actions.append(button("取消任务", () => cancelJob(job.id), "danger"));
  }
  card.append(actions);
  return card;
}

function render() {
  if (!state.root) return;
  const root = state.root;
  root.replaceChildren();

  const hero = el("header", "fan-ai-hero");
  hero.append(
    el("h2", "", ASSISTANT_NAME),
    el("p", "", "任务耗时、API 预算、最近工作流与一键再生成"),
  );
  root.append(hero);

  const toolbar = el("div", "fan-ai-toolbar");
  toolbar.append(button("刷新", refreshAndRender, "primary"));
  root.append(toolbar);

  const balanceSection = el("section", "fan-ai-section");
  balanceSection.append(el("h3", "", "API 资产"));
  if (!state.balances.length) {
    balanceSection.append(el("div", "fan-ai-empty", "尚未配置余额来源。请设置环境变量后重启 ComfyUI。"));
  } else {
    state.balances.forEach((item) => balanceSection.append(renderBalance(item)));
  }
  state.warnings.forEach((warning) => balanceSection.append(el("div", "fan-ai-warning", warning)));
  root.append(balanceSection);

  const jobsSection = el("section", "fan-ai-section");
  jobsSection.append(el("h3", "", "最近任务"));
  if (!state.jobs.length) {
    jobsSection.append(el("div", "fan-ai-empty", "还没有任务。先运行一个工作流，系统才有东西可记录。"));
  } else {
    state.jobs.forEach((job, index) => jobsSection.append(renderJob(job, index)));
  }
  root.append(jobsSection);
}

async function refreshAndRender() {
  const results = await Promise.allSettled([refreshJobs(), refreshBalances()]);
  results.forEach((result) => {
    if (result.status === "rejected") console.error(`[${ASSISTANT_NAME}] 刷新失败`, result.reason);
  });
  render();
}

function registerExecutionEvents() {
  api.addEventListener("execution_start", (event) => {
    const data = eventData(event);
    if (!data.prompt_id) return;
    state.runningStarts[data.prompt_id] = data.timestamp ?? Date.now();
    saveRunningStarts();
    refreshAndRender().catch(console.error);
  });

  const terminal = (event) => {
    const data = eventData(event);
    if (data.prompt_id) {
      delete state.runningStarts[data.prompt_id];
      saveRunningStarts();
    }
    refreshAndRender().catch(console.error);
  };
  api.addEventListener("execution_success", terminal);
  api.addEventListener("execution_error", terminal);
  api.addEventListener("execution_interrupted", terminal);
}

app.registerExtension({
  name: EXTENSION_NAME,
  async setup() {
    injectCss();
    registerExecutionEvents();
    app.extensionManager.registerSidebarTab({
      id: "fan-ai-visual-assistant",
      icon: "pi pi-rocket",
      title: "帆 AI 助手",
      tooltip: ASSISTANT_NAME,
      type: "custom",
      render: (container) => {
        if (state.refreshTimer) window.clearInterval(state.refreshTimer);
        if (state.liveTimer) window.clearInterval(state.liveTimer);
        const root = el("div", "fan-ai-assistant-root");
        container.replaceChildren(root);
        state.root = root;
        refreshAndRender().catch(console.error);
        state.refreshTimer = window.setInterval(() => refreshAndRender().catch(console.error), 10_000);
        state.liveTimer = window.setInterval(() => {
          if (state.jobs.some((job) => job.status === "in_progress")) render();
        }, 1_000);
      },
    });
  },
});
