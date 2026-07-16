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
  const lines = [
    `PROJECT   ${s.project_root}`,
    `PYTHON    ${s.python}  (${s.platform})`,
    `BOT       ${s.bot_running ? "RUNNING  pid=" + s.bot_pid : "STOPPED"}`,
    `READY     ${s.ready ? "YES" : "NO — fill secrets"}`,
    ``,
    `SECRETS`,
    `  TELEGRAM   ${s.secrets.TELEGRAM_BOT_TOKEN ? "[OK]" : "[MISSING]"}`,
    `  GEMINI     ${s.secrets.GEMINI_API_KEY ? "[OK]" : "[MISSING]"}`,
    `  PINECONE   ${s.secrets.PINECONE_API_KEY ? "[OK]" : "[MISSING]"}`,
    `  ADMIN_IDS  ${s.secrets.ADMIN_USER_IDS ? "[OK]" : "[—]"}`,
    ``,
    `STACK`,
    `  LLM        ${s.llm_model || "—"}`,
    `  EMBED      ${(s.embed && s.embed.provider) || "—"} / ${(s.embed && s.embed.model) || "—"} d=${(s.embed && s.embed.dimension) || "—"}`,
    `  INDEX      ${s.index || "—"}`,
    `  RERANKER   ${s.reranker || "—"}`,
  ];
  $("#status-pre").textContent = lines.join("\n");
  $("#meta-line").textContent = s.bot_running
    ? `BOT ONLINE · PID ${s.bot_pid}`
    : s.ready
      ? "READY · BOT OFFLINE"
      : "AWAITING SECRETS";
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

/* local */
$("#btn-start")?.addEventListener("click", async () => {
  try {
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
