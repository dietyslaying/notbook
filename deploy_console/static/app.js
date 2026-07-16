/* Notbook Deploy Console — front-end */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = data.error || res.statusText || "request failed";
    throw new Error(err);
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
    const id = "tab-" + btn.dataset.tab;
    document.getElementById(id)?.classList.add("active");
  });
});

/* status */
async function refreshStatus() {
  const s = await api("/api/status");
  const bs = s.bot_secrets || (s.bot_live && s.bot_live.secrets) || null;
  const bl = s.bot_live || {};
  const botLine = bl.running
    ? `ONLINE  ·  ${bl.detail || "reachable"}`
    : `OFFLINE / UNREACHABLE  ·  ${bl.detail || bl.error || "not responding"}`;
  const lines = [
    `PROJECT   ${s.project_root}`,
    `PYTHON    ${s.python}  (${s.platform})`,
    ``,
    `TELEGRAM BOT  ${botLine}`,
    `  URL         ${bl.configured_url || "— (set BOT_BASE_URL)"}`,
    `  CHECK       ${bl.mode || "—"}`,
    `  LOCAL PID   ${s.local_bot_process ? "yes (" + s.bot_pid + ")" : "no (normal on cloud)"}`,
    ``,
    `CONSOLE READY  ${s.ready ? "YES — can upload books / use tools" : "NO — add keys on THIS console service"}`,
    ``,
    `NOTE  ${s.secrets_note || ""}`,
    ``,
    `SECRETS ON CONSOLE (this website's Environment)`,
    `  TELEGRAM   ${s.secrets.TELEGRAM_BOT_TOKEN ? "[OK]" : "[MISSING]"}`,
    `  GEMINI     ${s.secrets.GEMINI_API_KEY ? "[OK]" : "[MISSING]"}`,
    `  PINECONE   ${s.secrets.PINECONE_API_KEY ? "[OK]" : "[MISSING]"}`,
    `  ADMIN_IDS  ${s.secrets.ADMIN_USER_IDS ? "[OK]" : "[—]"}`,
    `  RENDER API ${s.secrets.RENDER_API_KEY ? "[OK]" : "[—]"}`,
    `  RENDER_SID ${s.render_service_id || "—"}`,
    `  LINK TOK   ${s.link && s.link.token_set ? "[OK]" : "[—]"}`,
    ``,
    `SECRETS ON BOT (live check)`,
    bs
      ? [
          `  TELEGRAM   ${bs.telegram ? "[OK]" : "[MISSING]"}`,
          `  GEMINI     ${bs.gemini ? "[OK]" : "[MISSING]"}`,
          `  PINECONE   ${bs.pinecone ? "[OK]" : "[MISSING]"}`,
          `  LINK TOK   ${bs.internal_token ? "[OK]" : "[MISSING]"}`,
        ].join("\n")
      : s.bot_pull_error
        ? `  health: ${bl.running ? "up" : "down"} · details: ${s.bot_pull_error}`
        : bl.running
          ? `  health: UP (set INTERNAL_SERVICE_TOKEN on both to see key checklist)`
          : `  (bot not reachable — free tier may be asleep; open bot URL once)`,
    ``,
    `STACK (config.yaml on console)`,
    `  LLM        ${s.llm_model || "—"}`,
    `  EMBED      ${(s.embed && s.embed.provider) || "—"} / ${(s.embed && s.embed.model) || "—"} d=${(s.embed && s.embed.dimension) || "—"}`,
    `  INDEX      ${s.index || "—"}`,
    `  RERANKER   ${s.reranker || "—"}`,
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

$("#btn-gen-artifacts")?.addEventListener("click", async () => {
  try {
    const r = await api("/api/artifacts/generate", { method: "POST", body: "{}" });
    setMsg("#status-pre", `GENERATED → ${r.dir}\n` + r.files.map((f) => "  · " + f).join("\n"));
    await listArtifacts();
  } catch (e) {
    setMsg("#status-pre", String(e), false);
  }
});

/* secrets */
async function loadSecrets(reveal = false) {
  const r = await api("/api/env?masked=" + (reveal ? "0" : "1"));
  const form = $("#form-secrets");
  for (const [k, v] of Object.entries(r.env || {})) {
    const input = form.elements.namedItem(k);
    if (input) input.value = v;
  }
}

$("#btn-save-secrets")?.addEventListener("click", async (ev) => {
  ev.preventDefault();
  const form = $("#form-secrets");
  const env = {};
  [...form.elements].forEach((el) => {
    if (el.name) env[el.name] = el.value;
  });
  try {
    const r = await api("/api/env", { method: "POST", body: JSON.stringify({ env }) });
    setMsg("#secrets-msg", r.message || "saved");
    await refreshStatus();
  } catch (e) {
    setMsg("#secrets-msg", String(e), false);
  }
});

$("#btn-reveal-secrets")?.addEventListener("click", async () => {
  try {
    await loadSecrets(true);
    setMsg("#secrets-msg", "loaded unmasked (session only)");
  } catch (e) {
    setMsg("#secrets-msg", String(e), false);
  }
});

/* config */
function getByPath(obj, path) {
  return path.split(".").reduce((a, k) => (a == null ? undefined : a[k]), obj);
}

async function loadConfig() {
  const r = await api("/api/config");
  const cfg = r.config || {};
  $$("#form-config [data-path]").forEach((el) => {
    const path = el.dataset.path;
    let val = getByPath(cfg, path);
    if (val === undefined || val === null) return;
    if (typeof val === "boolean") val = val ? "true" : "false";
    el.value = String(val);
  });
}

$("#btn-save-config")?.addEventListener("click", async (ev) => {
  ev.preventDefault();
  const fields = {};
  $$("#form-config [data-path]").forEach((el) => {
    fields[el.dataset.path] = el.value;
  });
  try {
    const r = await api("/api/config", {
      method: "POST",
      body: JSON.stringify({ fields }),
    });
    setMsg("#config-msg", r.message || "saved");
    await refreshStatus();
  } catch (e) {
    setMsg("#config-msg", String(e), false);
  }
});

$("#btn-reload-config")?.addEventListener("click", () => {
  loadConfig()
    .then(() => setMsg("#config-msg", "reloaded"))
    .catch((e) => setMsg("#config-msg", String(e), false));
});

/* library / pinecone upload + live progress */
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
    const cur = job.current != null ? job.current : "—";
    const tot = job.total != null ? job.total : "—";
    counts.textContent = `${cur} / ${tot} chunks`;
  }
  const jobEl = $("#lib-job");
  if (jobEl) jobEl.textContent = "job: " + (job.id || "—");
}

function appendLibLogs(newLines) {
  if (!newLines || !newLines.length) return;
  _libLogLines = _libLogLines.concat(newLines);
  // keep last 400 lines in UI
  if (_libLogLines.length > 400) {
    _libLogLines = _libLogLines.slice(-400);
  }
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
    `/api/library/upload/${encodeURIComponent(jobId)}?since=${_libLogOffset}`
  );
  const data = await r.json();
  if (!r.ok || data.ok === false) {
    throw new Error(data.error || r.statusText);
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
  if (!(r.books || []).length) {
    lines.push("(empty — upload a PDF above)");
  }
  $("#lib-books").textContent = lines.join("\n");
}

$("#btn-lib-refresh")?.addEventListener("click", () => {
  refreshBooks()
    .then(() => setMsg("#lib-msg", "books refreshed"))
    .catch((e) => setMsg("#lib-msg", String(e), false));
});

$("#btn-lib-upload")?.addEventListener("click", async (ev) => {
  ev.preventDefault();
  const fileInput = $("#lib-file");
  const nameInput = $("#lib-name");
  const file = fileInput?.files?.[0];
  const displayName = (nameInput?.value || "").trim();
  if (!file) {
    setMsg("#lib-msg", "choose a PDF", false);
    return;
  }
  if (!displayName) {
    setMsg("#lib-msg", "enter display name (shown in Telegram Books)", false);
    return;
  }
  if (_libPollTimer) {
    setMsg("#lib-msg", "upload already running", false);
    return;
  }

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
    _libPollTimer = setInterval(async () => {
      try {
        const job = await pollLibJob(jobId);
        if ((job.log_total || 0) > lastLogTotal) {
          lastLogTotal = job.log_total || 0;
          stallTicks = 0;
        } else if (job.status === "running" || job.status === "queued") {
          stallTicks += 1;
          // ~45s with no new logs
          if (stallTicks === 75) {
            appendLibLogs([
              "[ui] Still running — large PDFs / first Gemini import can take several minutes…",
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
              `index=${r.index}`,
              `pages=${r.pages} chunks=${r.chunks}`,
              `Telegram: Menu → Books → select “${r.book || displayName}”`,
            ].join("\n")
          );
          await refreshBooks();
        } else if (job.status === "error") {
          stopLibPoll();
          if (btn) btn.disabled = false;
          setMsg("#lib-msg", "FAILED: " + (job.error || job.message), false);
        }
      } catch (e) {
        stopLibPoll();
        if (btn) btn.disabled = false;
        setMsg("#lib-msg", String(e), false);
      }
    }, 600);
  } catch (e) {
    stopLibPoll();
    if (btn) btn.disabled = false;
    setMsg("#lib-msg", String(e), false);
  }
});

/* Bot ↔ Console link */
async function loadLinkForm() {
  try {
    const env = await api("/api/env?masked=0");
    const e = env.env || {};
    if ($("#link-bot-url") && e.BOT_BASE_URL) $("#link-bot-url").value = e.BOT_BASE_URL;
    if ($("#link-console-url") && e.CONSOLE_BASE_URL)
      $("#link-console-url").value = e.CONSOLE_BASE_URL;
    if ($("#link-token") && e.INTERNAL_SERVICE_TOKEN)
      $("#link-token").value = e.INTERNAL_SERVICE_TOKEN;
  } catch (_) {
    /* ignore */
  }
  try {
    const st = await api("/api/link/status");
    if ($("#link-console-url") && !($("#link-console-url").value || "").trim() && st.console_base_url) {
      $("#link-console-url").value = st.console_base_url;
    }
    renderLinkEvents(st.recent_bot_events || []);
  } catch (_) {}
}

function renderLinkEvents(events) {
  const el = $("#link-events");
  if (!el) return;
  if (!events.length) {
    el.textContent = "(no events yet)";
    return;
  }
  el.textContent = events
    .map((ev) => {
      const t = ev.ts ? new Date(ev.ts * 1000).toISOString() : "";
      return `[${t}] ${ev.event}  ${JSON.stringify(ev.payload || {})}`;
    })
    .join("\n");
}

function showLinkOut(obj) {
  const el = $("#link-out");
  if (!el) return;
  el.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
}

$("#btn-link-save")?.addEventListener("click", async () => {
  try {
    const body = {
      BOT_BASE_URL: ($("#link-bot-url")?.value || "").trim(),
      CONSOLE_BASE_URL: ($("#link-console-url")?.value || "").trim(),
      INTERNAL_SERVICE_TOKEN: ($("#link-token")?.value || "").trim(),
    };
    const r = await api("/api/link/save", { method: "POST", body: JSON.stringify(body) });
    setMsg("#link-msg", r.message || "saved");
    // also mirror into main secrets form if present
    await refreshStatus();
  } catch (e) {
    setMsg("#link-msg", String(e), false);
  }
});

$("#btn-link-status")?.addEventListener("click", async () => {
  try {
    const st = await api("/api/link/status");
    showLinkOut(st);
    renderLinkEvents(st.recent_bot_events || []);
    setMsg(
      "#link-msg",
      st.configured ? "link configured" : "not configured — set URL + token"
    );
  } catch (e) {
    setMsg("#link-msg", String(e), false);
  }
});

async function linkPull(what) {
  setMsg("#link-msg", `pull ${what}…`);
  try {
    const r = await api("/api/link/pull/bot", {
      method: "POST",
      body: JSON.stringify({ what }),
    });
    showLinkOut(r.data || r);
    setMsg("#link-msg", `pulled ${what}`);
  } catch (e) {
    setMsg("#link-msg", String(e), false);
  }
}
$("#btn-link-ping")?.addEventListener("click", () => linkPull("ping"));
$("#btn-link-pull-status")?.addEventListener("click", () => linkPull("status"));
$("#btn-link-pull-books")?.addEventListener("click", () => linkPull("books"));
$("#btn-link-pull-config")?.addEventListener("click", () => linkPull("config"));

async function linkPush(action) {
  setMsg("#link-msg", `push ${action}…`);
  try {
    const r = await api("/api/link/push/bot", {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    showLinkOut(r.data || r);
    setMsg("#link-msg", `pushed ${action}`);
  } catch (e) {
    setMsg("#link-msg", String(e), false);
  }
}
$("#btn-link-cache")?.addEventListener("click", () => linkPush("cache_clear"));
$("#btn-link-refresh")?.addEventListener("click", () => linkPush("library_refresh"));

$("#btn-link-sync-render")?.addEventListener("click", async () => {
  // reuse render sync if service selected
  const sid = selectedRenderServiceId();
  if (!sid) {
    setMsg("#link-msg", "select a service on RENDER tab first (or set preferred)", false);
    return;
  }
  try {
    const r = await api("/api/render/env/sync", {
      method: "POST",
      body: JSON.stringify({
        service_id: sid,
        deploy: true,
        keys: [
          "TELEGRAM_BOT_TOKEN",
          "GEMINI_API_KEY",
          "GEMINI_API_KEYS",
          "PINECONE_API_KEY",
          "ADMIN_USER_IDS",
          "INTERNAL_SERVICE_TOKEN",
          "CONSOLE_BASE_URL",
          "BOT_BASE_URL",
        ],
      }),
    });
    showLinkOut(r);
    setMsg("#link-msg", "synced secrets (+ link vars) to Render + deploy");
  } catch (e) {
    setMsg("#link-msg", String(e), false);
  }
});

/* Render.com */
function selectedRenderServiceId() {
  return ($("#render-service-select")?.value || "").trim();
}

async function loadRenderServices() {
  const r = await api("/api/render/services");
  if (!r.ok) throw new Error(r.error || "list failed");
  const sel = $("#render-service-select");
  const prev = selectedRenderServiceId() || r.preferred_service_id || "";
  sel.innerHTML = "";
  const opt0 = document.createElement("option");
  opt0.value = "";
  opt0.textContent = r.count ? `— ${r.count} services —` : "— no services —";
  sel.appendChild(opt0);
  (r.services || []).forEach((s) => {
    const o = document.createElement("option");
    o.value = s.id;
    const sus = s.suspended === "suspended" ? " [SUSPENDED]" : "";
    o.textContent = `${s.name || s.id} (${s.type || "?"})${sus}`;
    sel.appendChild(o);
  });
  if (prev) sel.value = prev;
  setMsg("#render-msg", `loaded ${r.count} service(s)`);
  if (sel.value) await refreshRenderDetail();
  return r;
}

async function refreshRenderDetail() {
  const sid = selectedRenderServiceId();
  if (!sid) {
    $("#render-detail").textContent = "// select a service";
    $("#render-deploys").textContent = "// —";
    return;
  }
  const r = await api("/api/render/service/" + encodeURIComponent(sid));
  if (!r.ok) throw new Error(r.error || "detail failed");
  const s = r.service || {};
  $("#render-detail").textContent = [
    `ID        ${s.id || "—"}`,
    `NAME      ${s.name || "—"}`,
    `TYPE      ${s.type || "—"}`,
    `URL       ${s.url || "—"}`,
    `REGION    ${s.region || "—"}`,
    `BRANCH    ${s.branch || "—"}`,
    `SUSPEND   ${s.suspended || "—"}`,
    `AUTO_DEP  ${s.autoDeploy || "—"}`,
    `UPDATED   ${s.updatedAt || "—"}`,
    `DASHBOARD ${s.dashboard || "—"}`,
  ].join("\n");
  const deps = r.deploys || [];
  if (!deps.length) {
    $("#render-deploys").textContent = "(no recent deploys)";
  } else {
    $("#render-deploys").textContent = deps
      .map(
        (d, i) =>
          `${i + 1}. ${d.status || "?"}  ${d.createdAt || ""}\n` +
          `   id=${d.id || "—"}\n` +
          `   trigger=${d.trigger || "—"}  finished=${d.finishedAt || "—"}`
      )
      .join("\n\n");
  }
}

$("#btn-render-list")?.addEventListener("click", () => {
  loadRenderServices().catch((e) => setMsg("#render-msg", String(e), false));
});
$("#btn-render-refresh")?.addEventListener("click", () => {
  refreshRenderDetail()
    .then(() => setMsg("#render-msg", "detail refreshed"))
    .catch((e) => setMsg("#render-msg", String(e), false));
});
$("#render-service-select")?.addEventListener("change", () => {
  refreshRenderDetail().catch((e) => setMsg("#render-msg", String(e), false));
});

$("#btn-render-prefer")?.addEventListener("click", async () => {
  const sid = selectedRenderServiceId();
  if (!sid) return setMsg("#render-msg", "select a service first", false);
  try {
    await api("/api/render/prefer", {
      method: "POST",
      body: JSON.stringify({ service_id: sid }),
    });
    setMsg("#render-msg", `preferred service → ${sid}`);
    await refreshStatus();
  } catch (e) {
    setMsg("#render-msg", String(e), false);
  }
});

async function renderDeploy(clearCache) {
  const sid = selectedRenderServiceId();
  if (!sid) return setMsg("#render-msg", "select a service first", false);
  setMsg("#render-msg", clearCache ? "deploy + clear cache…" : "deploying…");
  try {
    const r = await api("/api/render/deploy", {
      method: "POST",
      body: JSON.stringify({ service_id: sid, clear_cache: !!clearCache }),
    });
    const d = r.deploy || {};
    setMsg(
      "#render-msg",
      `deploy triggered\nid=${d.id || "?"}\nstatus=${d.status || "?"}`
    );
    await refreshRenderDetail();
  } catch (e) {
    setMsg("#render-msg", String(e), false);
  }
}
$("#btn-render-deploy")?.addEventListener("click", () => renderDeploy(false));
$("#btn-render-deploy-clear")?.addEventListener("click", async () => {
  const sid = selectedRenderServiceId();
  if (!sid) return setMsg("#render-msg", "select a service first", false);
  if (
    !confirm(
      "Clear build cache and deploy the LATEST commit on the linked branch?\nThis rebuilds from scratch."
    )
  )
    return;
  setMsg("#render-msg", "CLEAR CACHE + DEPLOY LATEST…");
  try {
    const r = await api("/api/render/deploy/clear", {
      method: "POST",
      body: JSON.stringify({ service_id: sid }),
    });
    const d = r.deploy || {};
    setMsg(
      "#render-msg",
      `${r.message || "ok"}\nid=${d.id || "?"}\nstatus=${d.status || "?"}`
    );
    await refreshRenderDetail();
    await fetchRenderLogs(null);
  } catch (e) {
    setMsg("#render-msg", String(e), false);
  }
});

$("#btn-render-sync")?.addEventListener("click", async () => {
  const sid = selectedRenderServiceId();
  if (!sid) return setMsg("#render-msg", "select a service first", false);
  if (
    !confirm(
      "Push local .env secrets (Telegram/Gemini/Pinecone/Admin) to this Render service and deploy?"
    )
  )
    return;
  setMsg("#render-msg", "syncing secrets + deploy…");
  try {
    const r = await api("/api/render/env/sync", {
      method: "POST",
      body: JSON.stringify({ service_id: sid, deploy: true }),
    });
    setMsg(
      "#render-msg",
      `synced: ${(r.synced_keys || []).join(", ")}\ndeploy=${(r.deploy && r.deploy.id) || "ok"}`
    );
    await refreshRenderDetail();
  } catch (e) {
    setMsg("#render-msg", String(e), false);
  }
});

$("#btn-render-env")?.addEventListener("click", async () => {
  const sid = selectedRenderServiceId();
  if (!sid) return setMsg("#render-msg", "select a service first", false);
  try {
    const r = await api("/api/render/env/" + encodeURIComponent(sid) + "?masked=1");
    const lines = (r.env || []).map((e) => `${e.key}=${e.value}`);
    $("#render-detail").textContent =
      `ENV VARS MASKED (${lines.length})\n\n` + (lines.join("\n") || "(none)");
    setMsg("#render-msg", "env keys loaded (values masked)");
  } catch (e) {
    setMsg("#render-msg", String(e), false);
  }
});

$("#btn-render-env-full")?.addEventListener("click", async () => {
  const sid = selectedRenderServiceId();
  if (!sid) return setMsg("#render-msg", "select a service first", false);
  if (
    !confirm(
      "Pull FULL unmasked environment variables from Render?\nKeep this private — secrets will appear on screen."
    )
  )
    return;
  try {
    const r = await api(
      "/api/render/env/" + encodeURIComponent(sid) + "/full"
    );
    $("#render-detail").textContent =
      `ENV FULL (${r.count})\n\n` + (r.text || "(none)");
    setMsg("#render-msg", `pulled ${r.count} env vars (FULL — sensitive)`);
  } catch (e) {
    setMsg("#render-msg", String(e), false);
  }
});

/* logs */
let _renderLogsTimer = null;
async function fetchRenderLogs(type) {
  const sid = selectedRenderServiceId();
  if (!sid) {
    $("#render-logs").textContent = "// select a service first";
    return;
  }
  const q = type ? `?limit=100&type=${encodeURIComponent(type)}` : "?limit=100";
  const r = await api("/api/render/logs/" + encodeURIComponent(sid) + q);
  if (!r.ok) throw new Error(r.error || "logs failed");
  $("#render-logs").textContent = r.text || "(empty)";
  setMsg("#render-msg", `logs: ${r.count} lines` + (type ? ` type=${type}` : ""));
}
$("#btn-render-logs")?.addEventListener("click", () => {
  fetchRenderLogs("app").catch((e) => setMsg("#render-msg", String(e), false));
});
$("#btn-render-logs-build")?.addEventListener("click", () => {
  fetchRenderLogs("build").catch((e) => setMsg("#render-msg", String(e), false));
});
$("#btn-render-logs-req")?.addEventListener("click", () => {
  fetchRenderLogs("request").catch((e) => setMsg("#render-msg", String(e), false));
});
$("#btn-render-logs-auto")?.addEventListener("click", () => {
  if (_renderLogsTimer) {
    clearInterval(_renderLogsTimer);
    _renderLogsTimer = null;
    setMsg("#render-msg", "log auto-refresh OFF");
    return;
  }
  setMsg("#render-msg", "log auto-refresh ON (15s)");
  fetchRenderLogs("app").catch(() => {});
  _renderLogsTimer = setInterval(() => {
    fetchRenderLogs("app").catch(() => {});
  }, 15000);
});

/* SSH */
async function loadSshInfo() {
  const sid = selectedRenderServiceId();
  const q = sid ? "?service_id=" + encodeURIComponent(sid) : "";
  const r = await api("/api/render/ssh" + q);
  if (!r.ok) throw new Error(r.error || "ssh info failed");
  const lines = [
    "ADD THIS PUBLIC KEY ON RENDER:",
    "  " + (r.add_key_url || ""),
    "",
    "PUBLIC KEY:",
    r.public_key || "",
    "",
    "PRIVATE KEY PATH (local only):",
    "  " + (r.private_key_path || ""),
    "",
    "SSH COMMAND (after key is added; paid shell plans):",
    "  " + (r.ssh_command || "(select service for host)"),
    r.region ? "  region=" + r.region : "",
    "",
    "STEPS:",
    ...(r.instructions || []).map((s, i) => `  ${i + 1}. ${s}`),
    "",
    "NOTE: Deploy/env/logs use RENDER_API_KEY (already configured).",
    "      SSH is only for interactive shell into the instance.",
  ];
  $("#render-ssh").textContent = lines.filter(Boolean).join("\n");
  window._lastRenderPubKey = r.public_key || "";
  return r;
}
$("#btn-render-ssh")?.addEventListener("click", () => {
  loadSshInfo().catch((e) => {
    $("#render-ssh").textContent = String(e);
  });
});
$("#btn-copy-ssh")?.addEventListener("click", async () => {
  try {
    if (!window._lastRenderPubKey) await loadSshInfo();
    const key = window._lastRenderPubKey || "";
    if (!key) throw new Error("no key");
    await navigator.clipboard.writeText(key);
    setMsg("#render-msg", "public key copied to clipboard");
  } catch (e) {
    setMsg("#render-msg", "copy failed — select text manually", false);
  }
});

$("#btn-render-suspend")?.addEventListener("click", async () => {
  const sid = selectedRenderServiceId();
  if (!sid) return setMsg("#render-msg", "select a service first", false);
  if (!confirm("Suspend this Render service?")) return;
  try {
    await api("/api/render/suspend", {
      method: "POST",
      body: JSON.stringify({ service_id: sid }),
    });
    setMsg("#render-msg", "suspend requested");
    await refreshRenderDetail();
  } catch (e) {
    setMsg("#render-msg", String(e), false);
  }
});

$("#btn-render-resume")?.addEventListener("click", async () => {
  const sid = selectedRenderServiceId();
  if (!sid) return setMsg("#render-msg", "select a service first", false);
  try {
    await api("/api/render/resume", {
      method: "POST",
      body: JSON.stringify({ service_id: sid }),
    });
    setMsg("#render-msg", "resume requested");
    await refreshRenderDetail();
  } catch (e) {
    setMsg("#render-msg", String(e), false);
  }
});

/* local */
$("#btn-start")?.addEventListener("click", async () => {
  try {
    // On Render, local bot start is disabled noise — use the linked bot service
    const st = await api("/api/status");
    if (st.link && st.link.on_render) {
      setMsg(
        "#local-msg",
        "On Render: use the bot Web Service + LINK tab (not local start).",
        false
      );
      return;
    }
    const r = await api("/api/local/start", { method: "POST", body: "{}" });
    setMsg("#local-msg", `STARTED pid=${r.pid}\nlog=${r.log}`);
    await refreshStatus();
    await tailLog();
  } catch (e) {
    setMsg("#local-msg", String(e), false);
  }
});

$("#btn-stop")?.addEventListener("click", async () => {
  try {
    const r = await api("/api/local/stop", { method: "POST", body: "{}" });
    setMsg("#local-msg", r.message || "stopped");
    await refreshStatus();
  } catch (e) {
    setMsg("#local-msg", String(e), false);
  }
});

async function tailLog() {
  const r = await api("/api/local/log");
  $("#local-log").textContent = r.log || "(empty)";
}

$("#btn-log")?.addEventListener("click", () => {
  tailLog().catch((e) => {
    $("#local-log").textContent = String(e);
  });
});

/* deploy guides */
$$("#targets .target").forEach((btn) => {
  btn.addEventListener("click", async () => {
    $$("#targets .target").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    try {
      const r = await api("/api/deploy/guide/" + btn.dataset.target);
      const g = r.guide;
      const lines = [
        `TARGET    ${g.title}`,
        `SUITABLE  ${g.suitable ? "YES" : "NO"}`,
        g.note ? `NOTE      ${g.note}` : null,
        ``,
        `STEPS`,
        ...g.steps.map((s, i) => `  ${i + 1}. ${s}`),
      ].filter((x) => x !== null);
      $("#deploy-guide").textContent = lines.join("\n");
    } catch (e) {
      $("#deploy-guide").textContent = String(e);
    }
  });
});

/* artifacts */
async function listArtifacts() {
  const r = await api("/api/artifacts");
  const ul = $("#art-list");
  ul.innerHTML = "";
  (r.files || []).forEach((name) => {
    const li = document.createElement("li");
    li.textContent = name;
    li.addEventListener("click", async () => {
      $$("#art-list li").forEach((x) => x.classList.remove("active"));
      li.classList.add("active");
      const f = await api("/api/artifacts/" + encodeURIComponent(name));
      $("#art-view").textContent = f.content;
    });
    ul.appendChild(li);
  });
  if (!(r.files || []).length) {
    $("#art-view").textContent = "// no artifacts yet — click GENERATE ALL";
  }
}

$("#btn-gen")?.addEventListener("click", async () => {
  try {
    const r = await api("/api/artifacts/generate", { method: "POST", body: "{}" });
    setMsg("#art-view", `wrote ${r.files.length} files → ${r.dir}`);
    await listArtifacts();
  } catch (e) {
    $("#art-view").textContent = String(e);
  }
});

$("#btn-list-art")?.addEventListener("click", () => {
  listArtifacts().catch((e) => {
    $("#art-view").textContent = String(e);
  });
});

/* boot */
tickClock();
setInterval(tickClock, 1000);
refreshStatus().catch(() => {});
loadSecrets(false).catch(() => {});
loadConfig().catch(() => {});
listArtifacts().catch(() => {});
refreshBooks().catch(() => {});
loadRenderServices().catch(() => {});
loadLinkForm().catch(() => {});
