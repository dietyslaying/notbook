/* Notbook Console — status, library, bot deploy, logs */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || res.statusText || "request failed");
  }
  return data;
}

function setMsg(el, text, ok = true) {
  const node = typeof el === "string" ? $(el) : el;
  if (!node) return;
  node.textContent = text || "";
  node.style.color = ok ? "var(--dim)" : "#000";
  node.style.fontWeight = ok ? "400" : "600";
}

function tickClock() {
  const d = new Date();
  const s = d.toISOString().replace("T", " ").slice(0, 19) + "Z";
  const el = $("#clock");
  if (el) el.textContent = s;
}

/* tabs */
$$("#tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$("#tabs button").forEach((b) => b.classList.remove("active"));
    $$(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab)?.classList.add("active");
  });
});

/* ---------- STATUS ---------- */
async function refreshStatus() {
  const s = await api("/api/status");
  const bs = s.bot_secrets || (s.bot_live && s.bot_live.secrets) || null;
  const bl = s.bot_live || {};
  const botLine = bl.running
    ? `ONLINE  ·  ${bl.detail || "reachable"}`
    : `OFFLINE / UNREACHABLE  ·  ${bl.detail || bl.error || "not responding"}`;
  const howBits = [];
  if (bl.local_ok) howBits.push("local process");
  if (bl.remote_ok) howBits.push("remote /health");
  const howLine = howBits.length
    ? howBits.join(" + ")
    : bl.mode === "none"
      ? "no check configured"
      : "no live signal yet";

  const lines = [
    `PROJECT   ${s.project_root}`,
    `PYTHON    ${s.python}  (${s.platform})`,
    ``,
    `TELEGRAM BOT  ${botLine}`,
    `  URL         ${bl.configured_url || "— (set BOT_BASE_URL on console Environment)"}`,
    `  CHECK       ${bl.mode || "—"}  (${howLine})`,
    ``,
    `CONSOLE READY  ${s.ready ? "YES — can upload books" : "NO — add Gemini + Pinecone (+ Telegram) on THIS console Environment"}`,
    ``,
    `NOTE  ${s.secrets_note || ""}`,
    ``,
    `SECRETS ON CONSOLE (Render Environment for this website)`,
    `  TELEGRAM   ${s.secrets.TELEGRAM_BOT_TOKEN ? "[OK]" : "[MISSING]"}`,
    `  GEMINI     ${s.secrets.GEMINI_API_KEY ? "[OK]" : "[MISSING]"}`,
    `  PINECONE   ${s.secrets.PINECONE_API_KEY ? "[OK]" : "[MISSING]"}`,
    `  RENDER API ${s.secrets.RENDER_API_KEY ? "[OK]" : "[—] needed for DEPLOY BOT / LOGS"}`,
    `  BOT SVC ID ${s.render_service_id || "—"}`,
    ``,
    `SECRETS ON BOT (live check)`,
    bs
      ? [
          `  TELEGRAM   ${bs.telegram ? "[OK]" : "[MISSING]"}`,
          `  GEMINI     ${bs.gemini ? "[OK]" : "[MISSING]"}`,
          `  PINECONE   ${bs.pinecone ? "[OK]" : "[MISSING]"}`,
        ].join("\n")
      : bl.running
        ? `  health: UP`
        : `  (bot not reachable)`,
    ``,
    `STACK`,
    `  LLM     ${s.llm_model || "—"}`,
    `  EMBED   ${(s.embed && s.embed.provider) || "—"} / ${(s.embed && s.embed.model) || "—"}`,
    `  INDEX   ${s.index || "—"}`,
  ];
  $("#status-pre").textContent = lines.join("\n");
  const parts = [];
  parts.push(bl.running ? "BOT ONLINE" : "BOT OFFLINE");
  parts.push(s.ready ? "CONSOLE READY" : "CONSOLE NEEDS SECRETS");
  $("#meta-line").textContent = parts.join(" · ");
  return s;
}

$("#btn-refresh-status")?.addEventListener("click", () => {
  refreshStatus().catch((e) => setMsg("#status-pre", String(e), false));
});

/* ---------- LIBRARY ---------- */
let _libPollTimer = null;
let _libLogOffset = 0;
let _libLogLines = [];

function setLibProgress(job) {
  const pct = Math.max(0, Math.min(100, Number(job.pct) || 0));
  const fill = $("#lib-prog-fill");
  if (fill) fill.style.width = pct + "%";
  const phase = $("#lib-phase");
  if (phase) phase.textContent = (job.phase || job.status || "idle").toUpperCase();
  const pctLabel = $("#lib-pct-label");
  if (pctLabel) pctLabel.textContent = pct.toFixed(1) + "%";
  const counts = $("#lib-counts");
  if (counts) {
    counts.textContent = `${job.current != null ? job.current : "—"} / ${
      job.total != null ? job.total : "—"
    } chunks`;
  }
  const jobEl = $("#lib-job");
  if (jobEl) jobEl.textContent = "job: " + (job.id || "—");
}

function appendLibLogs(newLines) {
  if (!newLines || !newLines.length) return;
  _libLogLines = _libLogLines.concat(newLines);
  if (_libLogLines.length > 400) _libLogLines = _libLogLines.slice(-400);
  const el = $("#lib-live-log");
  if (el) {
    el.textContent = _libLogLines.join("\n");
    el.scrollTop = el.scrollHeight;
  }
}

function resetLibProgress() {
  _libLogOffset = 0;
  _libLogLines = [];
  setLibProgress({ pct: 0, phase: "idle", current: 0, total: 0, id: "—" });
  const el = $("#lib-live-log");
  if (el) el.textContent = "// waiting…";
}

async function pollLibJob(jobId) {
  const r = await fetch(
    `/api/library/upload/${encodeURIComponent(jobId)}?since=${_libLogOffset}`,
    { cache: "no-store", headers: { Accept: "application/json" } }
  );
  const raw = await r.text();
  let data = null;
  if (raw && raw.trim()) {
    try {
      data = JSON.parse(raw);
    } catch (_) {
      const err = new Error(`poll non-JSON (${r.status})`);
      err.transient = true;
      throw err;
    }
  } else {
    const err = new Error(`poll empty body (${r.status})`);
    err.transient = true;
    throw err;
  }
  if (!r.ok || data.ok === false) {
    const err = new Error(data.error || r.statusText || "poll failed");
    err.transient = r.status >= 500 || r.status === 0 || r.status === 429;
    throw err;
  }
  setLibProgress(data);
  if (data.logs && data.logs.length) {
    appendLibLogs(data.logs);
    _libLogOffset = data.log_total || _libLogOffset + data.logs.length;
  }
  return data;
}

function stopLibPoll() {
  if (_libPollTimer) {
    clearInterval(_libPollTimer);
    _libPollTimer = null;
  }
}

async function refreshBooks() {
  const r = await api("/api/library/books");
  if (!r.ok) throw new Error(r.error || "list failed");
  const lines = [
    `COUNT  ${r.count}`,
    ``,
    ...(r.books || []).map(
      (b) =>
        `• ${b.display_name}\n  ns=${b.namespace}\n  vectors=${b.vectors ?? "?"}  token=${b.token}`
    ),
  ];
  if (!(r.books || []).length) lines.push("(empty — upload a PDF above)");
  $("#lib-books").textContent = lines.join("\n");
}

$("#btn-lib-refresh")?.addEventListener("click", () => {
  refreshBooks()
    .then(() => setMsg("#lib-msg", "books refreshed"))
    .catch((e) => setMsg("#lib-msg", String(e), false));
});

$("#btn-lib-upload")?.addEventListener("click", async (ev) => {
  ev.preventDefault();
  const file = $("#lib-file")?.files?.[0];
  const displayName = ($("#lib-name")?.value || "").trim();
  if (!file) return setMsg("#lib-msg", "choose a PDF", false);
  if (!displayName) return setMsg("#lib-msg", "enter display name", false);
  if (_libPollTimer) return setMsg("#lib-msg", "upload already running", false);

  resetLibProgress();
  setMsg("#lib-msg", "starting background upload…");
  const btn = $("#btn-lib-upload");
  if (btn) btn.disabled = true;

  const fd = new FormData();
  fd.append("file", file);
  fd.append("display_name", displayName);

  try {
    const res = await fetch("/api/library/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || res.statusText);
    const jobId = data.job_id;
    setMsg("#lib-msg", `job ${jobId} running — live progress below`);
    setLibProgress({ id: jobId, pct: 0, phase: "queued", current: 0, total: 0 });

    let stallTicks = 0;
    let lastLogTotal = 0;
    let pollFails = 0;
    let pollBusy = false;
    _libPollTimer = setInterval(async () => {
      if (pollBusy) return;
      pollBusy = true;
      try {
        const job = await pollLibJob(jobId);
        pollFails = 0;
        if ((job.log_total || 0) > lastLogTotal) {
          lastLogTotal = job.log_total || 0;
          stallTicks = 0;
        } else if (job.status === "running" || job.status === "queued") {
          stallTicks += 1;
          if (stallTicks === 30) {
            appendLibLogs([
              "[ui] Still running — large PDFs + free Gemini can take a long time.",
            ]);
          }
        }
        if (job.status === "done") {
          stopLibPoll();
          if (btn) btn.disabled = false;
          const r = job.result || {};
          setMsg(
            "#lib-msg",
            [
              "UPLOAD COMPLETE",
              `book=${r.book}`,
              `namespace=${r.namespace}`,
              `chunks=${r.chunks}`,
              `Telegram: Menu → Books → “${r.book || displayName}”`,
            ].join("\n")
          );
          await refreshBooks();
        } else if (job.status === "error") {
          stopLibPoll();
          if (btn) btn.disabled = false;
          setMsg("#lib-msg", "FAILED: " + (job.error || job.message), false);
        } else {
          setMsg(
            "#lib-msg",
            `job ${jobId} ${job.status || "running"} — ${Number(job.pct || 0).toFixed(1)}%`
          );
        }
      } catch (e) {
        pollFails += 1;
        appendLibLogs([`[ui] poll hiccup #${pollFails}: ${e}`]);
        if (!e.transient && pollFails >= 3) {
          stopLibPoll();
          if (btn) btn.disabled = false;
          setMsg("#lib-msg", String(e), false);
        } else if (pollFails >= 40) {
          stopLibPoll();
          if (btn) btn.disabled = false;
          setMsg(
            "#lib-msg",
            "Lost progress contact. Job may still run on server — check logs, don’t re-upload yet.",
            false
          );
        }
      } finally {
        pollBusy = false;
      }
    }, 2000);
  } catch (e) {
    stopLibPoll();
    if (btn) btn.disabled = false;
    setMsg("#lib-msg", String(e), false);
  }
});

/* ---------- DEPLOY BOT ---------- */
function selectedBotServiceId() {
  return ($("#bot-service-select")?.value || "").trim();
}

async function loadBotServices() {
  const r = await api("/api/render/services");
  const sel = $("#bot-service-select");
  if (!sel) return;
  const preferred = r.preferred || "";
  sel.innerHTML = "";
  const opt0 = document.createElement("option");
  opt0.value = "";
  opt0.textContent = "— pick bot service —";
  sel.appendChild(opt0);
  for (const s of r.services || []) {
    const opt = document.createElement("option");
    opt.value = s.id;
    const label = `${s.name || s.id}  (${s.type || "?"})`;
    opt.textContent = label;
    if (s.id === preferred) opt.selected = true;
    // prefer names that look like the bot
    const n = (s.name || "").toLowerCase();
    if (!preferred && (n.includes("bot") || n.includes("notbook")) && !n.includes("console")) {
      opt.selected = true;
    }
    sel.appendChild(opt);
  }
  setMsg("#deploy-msg", `loaded ${r.count} service(s)`);
  if (selectedBotServiceId()) await refreshDeployDetail();
}

async function refreshDeployDetail() {
  const sid = selectedBotServiceId();
  if (!sid) {
    $("#deploy-detail").textContent = "// select a service";
    $("#deploy-deploys").textContent = "// —";
    return;
  }
  const r = await api("/api/render/service/" + encodeURIComponent(sid));
  const s = r.service || {};
  $("#deploy-detail").textContent = [
    `ID      ${s.id}`,
    `NAME    ${s.name}`,
    `TYPE    ${s.type}`,
    `URL     ${s.url || "—"}`,
    `BRANCH  ${s.branch || "—"}`,
    `REGION  ${s.region || "—"}`,
    `SUSP    ${s.suspended || "—"}`,
  ].join("\n");
  const deps = r.deploys || [];
  if (!deps.length) {
    $("#deploy-deploys").textContent = "(no recent deploys)";
  } else {
    $("#deploy-deploys").textContent = deps
      .map(
        (d) =>
          `${d.createdAt || d.finishedAt || "?"}  ${d.status || "?"}  ${d.id || ""}`
      )
      .join("\n");
  }
}

async function deployBot(clearCache) {
  const sid = selectedBotServiceId();
  if (!sid) return setMsg("#deploy-msg", "select the bot service first", false);
  setMsg("#deploy-msg", clearCache ? "clear cache + deploy…" : "deploying…");
  try {
    const path = clearCache ? "/api/render/deploy/clear" : "/api/render/deploy";
    const r = await api(path, {
      method: "POST",
      body: JSON.stringify({ service_id: sid }),
    });
    setMsg(
      "#deploy-msg",
      clearCache
        ? `CLEAR CACHE + DEPLOY started: ${JSON.stringify(r.deploy || r)}`
        : `DEPLOY started: ${JSON.stringify(r.deploy || r)}`
    );
    await refreshDeployDetail();
  } catch (e) {
    setMsg("#deploy-msg", String(e), false);
  }
}

$("#btn-bot-list")?.addEventListener("click", () => {
  loadBotServices().catch((e) => setMsg("#deploy-msg", String(e), false));
});
$("#btn-bot-refresh")?.addEventListener("click", () => {
  refreshDeployDetail()
    .then(() => setMsg("#deploy-msg", "detail refreshed"))
    .catch((e) => setMsg("#deploy-msg", String(e), false));
});
$("#bot-service-select")?.addEventListener("change", () => {
  refreshDeployDetail().catch((e) => setMsg("#deploy-msg", String(e), false));
});
$("#btn-bot-deploy")?.addEventListener("click", () => deployBot(false));
$("#btn-bot-deploy-clear")?.addEventListener("click", () => {
  if (!selectedBotServiceId()) return setMsg("#deploy-msg", "select service first", false);
  if (!confirm("Clear build cache and deploy latest bot code?")) return;
  deployBot(true);
});

/* ---------- LOGS ---------- */
let _logsTimer = null;

async function fetchBotLogs(type) {
  const sid = selectedBotServiceId();
  if (!sid) {
    $("#logs-out").textContent = "// select bot service on DEPLOY BOT tab first";
    setMsg("#logs-msg", "no service selected", false);
    return;
  }
  const q = type ? `?type=${encodeURIComponent(type)}` : "";
  const r = await api("/api/render/logs/" + encodeURIComponent(sid) + q);
  $("#logs-out").textContent = r.text || "(empty)";
  setMsg("#logs-msg", `logs: ${r.count} lines` + (type ? ` (${type})` : ""));
}

$("#btn-logs-app")?.addEventListener("click", () => {
  fetchBotLogs("app").catch((e) => setMsg("#logs-msg", String(e), false));
});
$("#btn-logs-build")?.addEventListener("click", () => {
  fetchBotLogs("build").catch((e) => setMsg("#logs-msg", String(e), false));
});
$("#btn-logs-auto")?.addEventListener("click", () => {
  if (_logsTimer) {
    clearInterval(_logsTimer);
    _logsTimer = null;
    setMsg("#logs-msg", "auto-refresh OFF");
    return;
  }
  setMsg("#logs-msg", "auto-refresh ON (15s)");
  fetchBotLogs("app").catch(() => {});
  _logsTimer = setInterval(() => {
    fetchBotLogs("app").catch(() => {});
  }, 15000);
});

/* boot */
setInterval(tickClock, 1000);
tickClock();
refreshStatus().catch(() => {});
refreshBooks().catch(() => {});
