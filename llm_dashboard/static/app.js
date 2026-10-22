"use strict";

// All dynamic content is inserted with textContent / text nodes, never innerHTML:
// summaries and plugin metadata can contain attacker-controlled text.

const $ = (selector) => document.querySelector(selector);

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

function describeError(data, status) {
  const detail = data && data.detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return detail || (data && data.error) || `Request failed (${status})`;
}

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(describeError(data, res.status));
  return data;
}

function setStatus(node, message, isError = false) {
  node.textContent = message;
  node.classList.toggle("error", isError);
}

// Runs `task` while the form's button is disabled, reporting the outcome in `status`.
async function withBusy(form, status, task) {
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  setStatus(status, "Working…");
  try {
    await task();
  } catch (err) {
    setStatus(status, err.message, true);
  } finally {
    button.disabled = false;
  }
}

// --- tabs --------------------------------------------------------------------

const loaders = {};

function showTab(name) {
  document.querySelectorAll("section").forEach((s) => (s.hidden = s.id !== `tab-${name}`));
  document.querySelectorAll("nav button").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name));
  loaders[name]?.().catch((err) => console.error(err));
}

document.querySelectorAll("nav button").forEach((b) =>
  b.addEventListener("click", () => showTab(b.dataset.tab)));

// --- plugins -----------------------------------------------------------------

loaders.plugins = async () => {
  const { plugins } = await api("/api/plugins");
  const rows = plugins.length
    ? plugins.map((p) => el("tr", {}, el("td", { textContent: p.name }),
        el("td", { textContent: p.version }), el("td", { textContent: p.summary })))
    : [el("tr", {}, el("td", { colSpan: 3, textContent: "No plugins installed." }))];
  $("#plugin-rows").replaceChildren(...rows);
};

$("#plugin-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  const body = { name: form.name.value.trim(), version: form.version.value.trim() || null };
  withBusy(form, $("#plugin-status"), async () => {
    const plugin = await api("/api/plugins", { method: "POST", body });
    setStatus($("#plugin-status"), `Installed ${plugin.name} ${plugin.version}`);
    form.reset();
    await loaders.plugins();
  });
});

// --- models ------------------------------------------------------------------

loaders.models = async () => {
  const { models } = await api("/api/models");
  const items = models.length
    ? models.map((m) => el("li", { textContent: m.name }))
    : [el("li", { textContent: "No models pulled yet." })];
  $("#model-list").replaceChildren(...items);
};

$("#model-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  withBusy(form, $("#model-status"), async () => {
    const result = await api("/api/models/pull", {
      method: "POST", body: { name: form.name.value.trim() },
    });
    setStatus($("#model-status"), `${result.name}: ${result.status}`);
    form.reset();
    await loaders.models();
  });
});

// --- agent -------------------------------------------------------------------

loaders.agent = async () => {
  const { files } = await api("/api/agent/workspace");
  const chips = files.map((f) => el("li", {}, el("button", {
    type: "button",
    textContent: f,
    onclick: () => { $("#agent-form").target.value = f; },
  })));
  $("#workspace-files").replaceChildren(...chips);
};

$("#agent-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  $("#agent-summary").hidden = true;
  $("#agent-steps").replaceChildren();
  withBusy(form, $("#agent-status"), async () => {
    const run = await api("/api/agent/summarize", {
      method: "POST", body: { target: form.target.value.trim() },
    });
    setStatus($("#agent-status"), "Done");
    $("#agent-summary").textContent = run.summary;
    $("#agent-summary").hidden = false;
    $("#agent-steps").replaceChildren(...run.steps.map((s) => el("li", {},
      el("code", { textContent: `${s.tool}(${JSON.stringify(s.arguments)})` }),
      ` → ${s.output.slice(0, 120)}`)));
  });
});

// --- settings ----------------------------------------------------------------

loaders.settings = async () => {
  const s = await api("/api/settings");
  const form = $("#settings-form");
  form.provider.value = s.provider;
  form.model.value = s.model;
  form.base_url.value = s.base_url;
  form.update_channel.value = s.update_channel;
  form.api_key.value = "";
  form.clear_api_key.checked = false;
  form.api_key.placeholder = s.api_key_set ? "(stored — leave blank to keep)" : "not set";
};

$("#settings-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  const body = {
    provider: form.provider.value,
    model: form.model.value.trim(),
    base_url: form.base_url.value.trim(),
    update_channel: form.update_channel.value,
  };
  if (form.clear_api_key.checked) body.api_key = null;
  else if (form.api_key.value) body.api_key = form.api_key.value;
  withBusy(form, $("#settings-status"), async () => {
    await api("/api/settings", { method: "PUT", body });
    await loaders.settings();
    setStatus($("#settings-status"), "Saved");
  });
});

// --- self-update -------------------------------------------------------------

$("#update-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  const output = $("#update-output");
  output.hidden = true;
  withBusy(form, $("#update-status"), async () => {
    const result = await api("/api/update", {
      method: "POST", body: { target: form.target.value.trim() },
    });
    output.textContent = [result.stdout, result.stderr].filter(Boolean).join("\n");
    output.hidden = !output.textContent;
    if (result.success) setStatus($("#update-status"), `Updated to ${result.target}`);
    else setStatus($("#update-status"), `Update to ${result.target} failed`, true);
  });
});

// --- boot --------------------------------------------------------------------

api("/api/health")
  .then((h) => { $("#mock-badge").hidden = !h.mock_mode; })
  .catch(() => {});
showTab("plugins");
