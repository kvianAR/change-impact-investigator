"use strict";

const $ = (id) => document.getElementById(id);
const sessionToken = document.querySelector('meta[name="panel-token"]').content;
const marks = { openrouter: "OR", openai: "AI", ollama: "OL", custom: "API" };
let state = null;
let selectedFilter = "all";
let catalogRequest = null;
let catalogModels = [];
let nameWasEdited = false;
let toastTimer = null;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "X-Impact-Token": sessionToken, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || "The request could not be completed.");
    error.status = response.status;
    throw error;
  }
  return result;
}

function toast(message, error = false) {
  const target = $("toast");
  clearTimeout(toastTimer);
  target.textContent = message;
  target.classList.toggle("error", error);
  target.hidden = false;
  toastTimer = setTimeout(() => { target.hidden = true; }, error ? 9000 : 4500);
}

function provider(id) {
  return state.providers.find((item) => item.id === id);
}

function ready(profile) {
  const connection = provider(profile.provider);
  return !connection.requires_key || connection.key_available;
}

function connectionStatus(connection) {
  if (connection.id === "ollama") return "Local · no API key needed";
  if (connection.key_error) return "Unlock your keychain";
  if (connection.key_source === "environment") return "Key from environment";
  if (connection.key_available) return "Key saved in keychain";
  return connection.requires_key ? "API key required" : "Optional API key";
}

function button(label, className, handler) {
  const node = element("button", className, label);
  node.type = "button";
  node.addEventListener("click", handler);
  return node;
}

function setState(next) {
  state = next;
  render();
}

async function refresh() {
  setState(await api("/api/state"));
}

function render() {
  $("storage-notice").hidden = state.secure_storage_available;
  $("model-count").textContent = state.models.length;
  const active = state.models.find((item) => item.id === state.active_model_id);
  $("active-name").textContent = active ? active.name : "Choose your first model";
  $("active-description").textContent = active ? active.model : "Your active model becomes the default for CLI and MCP summaries.";
  $("active-provider").textContent = active ? provider(active.provider).name : "Cloud or local. Your choice.";
  $("active-badge").textContent = active ? (ready(active) ? "Active" : "Key required") : "Not set";
  $("test-active").disabled = !active || !ready(active);
  $("test-active").onclick = () => active && testModel(active, $("test-active"));
  renderFilters();
  renderModels();
  renderConnections();
}

function renderFilters() {
  const container = $("provider-filters");
  container.replaceChildren();
  const choices = [{ id: "all", name: "All providers" }, ...state.providers];
  for (const choice of choices) {
    const filter = button(choice.name, "filter", () => {
      selectedFilter = choice.id;
      renderFilters();
      renderModels();
    });
    filter.setAttribute("aria-pressed", String(selectedFilter === choice.id));
    container.append(filter);
  }
}

function renderModels() {
  const container = $("models-list");
  const search = $("model-search").value.trim().toLowerCase();
  const models = state.models.filter((item) => (selectedFilter === "all" || item.provider === selectedFilter) && `${item.name} ${item.model} ${provider(item.provider).name}`.toLowerCase().includes(search));
  models.sort((a, b) => Number(b.id === state.active_model_id) - Number(a.id === state.active_model_id) || a.name.localeCompare(b.name));
  container.replaceChildren();
  if (models.length === 0) {
    const empty = element("div", "empty-state");
    const icon = element("div", "empty-symbol", "+");
    icon.setAttribute("aria-hidden", "true");
    empty.append(icon, element("h3", "", state.models.length ? "No matching models" : "Your model collection starts here"), element("p", "", state.models.length ? "Try another name or provider filter." : "Add a model, save its provider key, and choose which one is active."));
    empty.append(button(state.models.length ? "Clear filters" : "Add your first model", "button secondary", () => {
      if (!state.models.length) return showModel();
      selectedFilter = "all";
      $("model-search").value = "";
      renderFilters();
      renderModels();
    }));
    container.append(empty);
    return;
  }
  for (const profile of models) {
    const active = profile.id === state.active_model_id;
    const row = element("article", `model-row${active ? " is-active" : ""}`);
    const mark = element("div", "provider-mark", marks[profile.provider]);
    mark.setAttribute("aria-hidden", "true");
    const info = element("div", "model-info");
    const title = element("div", "model-title");
    title.append(element("span", "", profile.name));
    if (active) title.append(element("span", "pill success", "Active"));
    if (!ready(profile)) title.append(element("span", "pill warning", "Key required"));
    info.append(title, element("div", "model-code", profile.model), element("div", "model-provider", provider(profile.provider).name));
    const actions = element("div", "model-actions");
    const test = button("Test", "row-button", () => testModel(profile, test));
    test.disabled = !ready(profile);
    test.setAttribute("aria-label", `Test ${profile.name}`);
    const edit = button("Edit", "row-button", () => showModel(profile));
    edit.setAttribute("aria-label", `Edit ${profile.name}`);
    const activate = button(active ? "Active" : "Make active", "row-button activate", () => activateModel(profile, activate));
    activate.disabled = active || !ready(profile);
    activate.setAttribute("aria-label", active ? `${profile.name} is active` : `Make ${profile.name} active`);
    const remove = button("Remove", "row-button danger", () => removeModel(profile));
    remove.setAttribute("aria-label", `Remove ${profile.name}`);
    actions.append(test, edit, activate, remove);
    row.append(mark, info, actions);
    container.append(row);
  }
}

function renderConnections() {
  const container = $("provider-cards");
  container.replaceChildren();
  for (const connection of state.providers) {
    const card = element("article", "provider-card");
    const heading = element("div", "provider-card-heading");
    const mark = element("span", "provider-mark", marks[connection.id]);
    mark.setAttribute("aria-hidden", "true");
    heading.append(mark, element("span", "", connection.name));
    const status = element("p", `connection-status${connection.key_available || connection.id === "ollama" ? " ready" : ""}`, connectionStatus(connection));
    const manage = button("Manage connection", "manage-button", () => showConnection(connection.id));
    manage.setAttribute("aria-label", `Manage ${connection.name} connection`);
    card.append(heading, status, manage);
    container.append(card);
  }
}

function fillProviders(select) {
  select.replaceChildren();
  for (const connection of state.providers) {
    const option = element("option", "", connection.name);
    option.value = connection.id;
    select.append(option);
  }
}

function resetSecret(id) {
  $(id).value = "";
  $(id).type = "password";
  const toggle = document.querySelector(`[data-input="${id}"]`);
  toggle.textContent = "Show";
  toggle.setAttribute("aria-pressed", "false");
}

function updateProviderFields(prefix) {
  const connection = provider($(`${prefix}-provider`).value);
  resetSecret(`${prefix}-key`);
  const editable = ["custom", "ollama"].includes(connection.id);
  $(`${prefix}-endpoint-field`).hidden = !editable;
  $(`${prefix}-endpoint`).value = connection.base_url;
  $(`${prefix}-endpoint`).required = connection.id === "custom";
  $(`${prefix}-key-field`).hidden = connection.id === "ollama";
  const status = $(`${prefix}-key-status`);
  status.textContent = connectionStatus(connection);
  status.classList.toggle("saved", connection.key_available);
  $(`${prefix}-key`).placeholder = connection.key_available ? "Enter a new key to replace the saved key" : "Paste your API key";
  if (prefix === "model") {
    clearCatalog();
    $("model-id").placeholder = connection.id === "ollama" ? "qwen3.5:2b-q4_K_M" : connection.id === "openrouter" ? "vendor/model-name" : "Enter the exact model ID";
  } else {
    $("local-connection-note").hidden = connection.id !== "ollama";
    $("remove-key").disabled = !connection.saved_key;
    $("connection-key").required = connection.requires_key && !connection.key_available;
  }
  updateSaveLabel();
}

function updateSaveLabel() {
  $("save-model").textContent = $("make-active").checked ? "Save & activate" : "Save model";
  if (!state) return;
  const connection = provider($("model-provider").value);
  if (connection) $("model-key").required = $("make-active").checked && connection.requires_key && !connection.key_available;
}

function showModel(profile = null) {
  $("model-form").reset();
  fillProviders($("model-provider"));
  $("model-provider").value = profile ? profile.provider : selectedFilter === "all" ? "openrouter" : selectedFilter;
  $("profile-id").value = profile ? profile.id : "";
  $("model-dialog-title").textContent = profile ? "Edit model" : "Add a model";
  $("model-error").hidden = true;
  nameWasEdited = !!profile;
  updateProviderFields("model");
  $("model-id").value = profile ? profile.model : "";
  $("model-name").value = profile ? profile.name : "";
  $("model-tokens").value = profile ? profile.max_output_tokens : 800;
  $("make-active").checked = profile ? state.active_model_id === profile.id : !state.active_model_id;
  updateSaveLabel();
  $("model-dialog").showModal();
}

function showConnection(id = "openrouter") {
  $("connection-form").reset();
  fillProviders($("connection-provider"));
  $("connection-provider").value = id;
  $("connection-error").hidden = true;
  updateProviderFields("connection");
  $("connection-dialog").showModal();
}

function clearCatalog() {
  if (catalogRequest) catalogRequest.abort();
  catalogRequest = null;
  catalogModels = [];
  $("model-catalog").replaceChildren();
  $("catalog-note").textContent = "Enter a model ID, or load suggestions from your provider.";
  $("load-catalog").disabled = false;
  $("load-catalog").textContent = "Browse models";
}

function connectionData(prefix) {
  const selected = $(`${prefix}-provider`).value;
  const data = { provider: selected };
  if (["custom", "ollama"].includes(selected)) data.base_url = $(`${prefix}-endpoint`).value.trim();
  const key = $(`${prefix}-key`).value.trim();
  if (key) data.api_key = key;
  return data;
}

async function withBusy(form, target, label, operation) {
  const controls = form ? [...form.querySelectorAll("input, select, button")] : [target];
  const disabled = controls.map((control) => control.disabled);
  const text = target.textContent;
  controls.forEach((control) => { control.disabled = true; });
  target.textContent = label;
  if (form) form.setAttribute("aria-busy", "true");
  try { return await operation(); }
  finally {
    controls.forEach((control, index) => { control.disabled = disabled[index]; });
    target.textContent = text;
    if (form) form.removeAttribute("aria-busy");
  }
}

async function formError(target, error) {
  target.textContent = error.message;
  target.hidden = false;
  if (error.status === 409) {
    try { await refresh(); } catch { /* Keep the original conflict visible. */ }
  }
}

async function loadCatalog() {
  clearCatalog();
  const controller = new AbortController();
  catalogRequest = controller;
  const chosen = $("model-provider").value;
  $("load-catalog").disabled = true;
  $("load-catalog").textContent = "Loading…";
  $("catalog-note").textContent = "Fetching the provider catalog…";
  try {
    const response = await fetch("/api/catalog", { method: "POST", headers: { "X-Impact-Token": sessionToken, "Content-Type": "application/json" }, body: JSON.stringify(connectionData("model")), signal: controller.signal, cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load the catalog.");
    if (catalogRequest !== controller || chosen !== $("model-provider").value) return;
    catalogModels = result.models;
    for (const model of catalogModels) {
      const option = document.createElement("option");
      option.value = model.id;
      option.label = model.name;
      $("model-catalog").append(option);
    }
    $("catalog-note").textContent = catalogModels.length ? `${catalogModels.length} models loaded. Type a name or ID to choose one.` : "This provider returned no models. You can enter a model ID manually.";
    $("model-id").focus();
  } catch (error) {
    if (error.name !== "AbortError" && catalogRequest === controller) $("catalog-note").textContent = `${error.message} You can still enter a model ID manually.`;
  } finally {
    if (catalogRequest === controller) {
      catalogRequest = null;
      $("load-catalog").disabled = false;
      $("load-catalog").textContent = "Browse models";
    }
  }
}

async function testModel(profile, target) {
  try {
    await withBusy(null, target, "Testing…", () => api(`/api/models/${profile.id}/test`, {}));
    toast(`${profile.name} responded successfully.`);
  } catch (error) { toast(error.message, true); }
}

async function activateModel(profile, target) {
  try {
    const next = await withBusy(null, target, "Activating…", () => api(`/api/models/${profile.id}/activate`, { revision: state.revision }));
    setState(next);
    toast(`${profile.name} is now active.`);
  } catch (error) {
    toast(error.message, true);
    if (error.status === 409) await refresh();
  }
}

function confirmRemoval(title, description) {
  $("confirm-title").textContent = title;
  $("confirm-description").textContent = description;
  const dialog = $("confirm-dialog");
  return new Promise((resolve) => {
    let answer = false;
    $("confirm-accept").onclick = () => { answer = true; dialog.close(); };
    $("confirm-cancel").onclick = () => dialog.close();
    dialog.addEventListener("close", () => resolve(answer), { once: true });
    dialog.showModal();
  });
}

async function removeModel(profile) {
  if (!await confirmRemoval("Remove model?", `Remove “${profile.name}”? Its provider key will stay saved.`)) return;
  try {
    setState(await api(`/api/models/${profile.id}/delete`, { revision: state.revision }));
    toast("Model removed.");
  } catch (error) { toast(error.message, true); }
}

$("model-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = { ...connectionData("model"), revision: state.revision, model: $("model-id").value.trim(), name: $("model-name").value.trim(), max_output_tokens: Number($("model-tokens").value), activate: $("make-active").checked };
  if ($("profile-id").value) data.id = $("profile-id").value;
  $("model-error").hidden = true;
  try {
    const next = await withBusy($("model-form"), $("save-model"), "Saving…", () => api("/api/models", data));
    setState(next);
    $("model-dialog").close();
    toast(data.activate ? "Model saved and activated." : "Model saved.");
  } catch (error) { await formError($("model-error"), error); }
});

$("connection-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = { ...connectionData("connection"), revision: state.revision };
  $("connection-error").hidden = true;
  try {
    const next = await withBusy($("connection-form"), $("save-connection"), "Saving…", () => api(`/api/providers/${data.provider}`, data));
    setState(next);
    $("connection-dialog").close();
    toast("Provider connection saved.");
  } catch (error) { await formError($("connection-error"), error); }
});

$("remove-key").addEventListener("click", async () => {
  const chosen = $("connection-provider").value;
  if (!await confirmRemoval("Remove saved key?", `The saved ${provider(chosen).name} credential will be removed from this device.`)) return;
  try {
    setState(await api(`/api/providers/${chosen}`, { revision: state.revision, remove_key: true }));
    updateProviderFields("connection");
    toast("Saved provider key removed.");
  } catch (error) { await formError($("connection-error"), error); }
});

$("add-model").addEventListener("click", () => state && showModel());
$("connections-button").addEventListener("click", () => state && showConnection());
$("model-search").addEventListener("input", () => state && renderModels());
$("load-catalog").addEventListener("click", loadCatalog);
$("make-active").addEventListener("change", updateSaveLabel);
$("model-provider").addEventListener("change", () => { updateProviderFields("model"); $("model-id").value = ""; $("model-error").hidden = true; });
$("connection-provider").addEventListener("change", () => { updateProviderFields("connection"); $("connection-error").hidden = true; });
$("model-endpoint").addEventListener("input", clearCatalog);
$("model-name").addEventListener("input", () => { nameWasEdited = true; });
$("model-id").addEventListener("input", () => {
  if (!nameWasEdited) {
    const match = catalogModels.find((item) => item.id === $("model-id").value);
    $("model-name").value = (match ? match.name : $("model-id").value.split("/").pop()).slice(0, 100);
  }
});
document.querySelectorAll(".close-dialog").forEach((target) => target.addEventListener("click", () => target.closest("dialog").close()));
document.querySelectorAll(".reveal-key").forEach((target) => target.addEventListener("click", () => {
  const input = $(target.dataset.input);
  const reveal = input.type === "password";
  input.type = reveal ? "text" : "password";
  target.textContent = reveal ? "Hide" : "Show";
  target.setAttribute("aria-pressed", String(reveal));
}));
$("model-dialog").addEventListener("close", () => { resetSecret("model-key"); clearCatalog(); });
$("connection-dialog").addEventListener("close", () => resetSecret("connection-key"));
document.querySelectorAll(".settings-dialog").forEach((dialog) => dialog.addEventListener("cancel", (event) => { if (dialog.querySelector("form").getAttribute("aria-busy") === "true") event.preventDefault(); }));

refresh().catch((error) => {
  const container = $("models-list");
  container.replaceChildren(element("p", "form-error", error.message), button("Reload settings", "button secondary", () => window.location.reload()));
  toast(error.message, true);
});
