// Standardisation RMN : logique de l'interface.
// Toute la logique métier est en Python (window.pywebview.api) ; ce fichier ne
// fait qu'afficher et transmettre. Aucune dépendance, aucune étape de build.
"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  input: "",
  output: "",
  settings: null,
  defaults: null,
  lastReport: null,
  lastOutput: "",
  filter: "review",
};

const SUPERSCRIPT = { 0: "⁰", 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹" };

function api() {
  return window.pywebview.api;
}

function escapeHtml(text) {
  return text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

// '1H NMR' -> '¹H NMR' pour l'affichage du nom de règle.
function prettyRuleName(name) {
  return name.replace(/^(\d+)/, (d) => [...d].map((c) => SUPERSCRIPT[c]).join(""));
}

// Aperçu de la mise en forme produite dans Word : label + parenthèse en gras,
// δ en italique (selon les paramètres). Affichage seulement.
function renderNmr(text) {
  let html = escapeHtml(text);
  if (state.settings?.bold_label !== false) {
    html = html.replace(
      /([⁰¹²³⁴-⁹]+[A-Za-z]+(?:\{[^}]*\})?\s*(?:NMR|RMN)\s*\([^)]*\))/g,
      "<b>$1</b>"
    );
  }
  if (state.settings?.italic_delta !== false) {
    html = html.replace(/δ/g, "<i>δ</i>");
  }
  return html;
}

function splitPath(path) {
  const i = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  return i < 0 ? ["", path] : [path.slice(0, i), path.slice(i + 1)];
}

function plural(n, one, many) {
  return `${n} ${n > 1 ? many : one}`;
}

// --- Fichiers ------------------------------------------------------------------

function applyInput(result) {
  if (!result) return;
  state.input = result.input;
  state.output = result.output;
  const [dir, name] = splitPath(state.input);
  $("input-name").textContent = name;
  $("input-dir").textContent = dir;
  $("dropzone").dataset.state = "filled";
  $("output-path").textContent = state.output;
  $("choose-output").disabled = false;
  showError("");
  updateRunButton();
}

async function chooseInput() {
  applyInput(await api().choose_input(state.input, state.output));
}

// Appelé par Python quand un fichier est déposé sur la fenêtre (chemin complet
// fourni par pywebview, inaccessible au JavaScript seul).
window.onDroppedPath = async (path) => {
  $("dropzone").classList.remove("hover");
  const result = await api().set_input(path, state.input, state.output);
  if (result) applyInput(result);
  else showError("Seuls les documents Word (.docx) peuvent être standardisés.");
};

async function chooseOutput() {
  const path = await api().choose_output(state.output);
  if (path) {
    state.output = path;
    $("output-path").textContent = path;
  }
}

// --- Règles ----------------------------------------------------------------------

function renderRules(rules) {
  const box = $("rules");
  box.innerHTML = "";
  for (const rule of rules) {
    const label = document.createElement("label");
    label.className = "check";
    label.innerHTML = `<input type="checkbox" checked data-rule="${escapeHtml(rule.name)}">
      <span><span class="rule-name">${escapeHtml(prettyRuleName(rule.name))}</span></span>`;
    label.querySelector("input").addEventListener("change", updateRunButton);
    box.appendChild(label);
  }
}

function enabledRules() {
  return [...document.querySelectorAll("[data-rule]")].filter((c) => c.checked).map((c) => c.dataset.rule);
}

function updateRunButton() {
  $("run").disabled = !state.input || !state.output || enabledRules().length === 0;
}

// --- Standardisation --------------------------------------------------------------

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

async function run() {
  const button = $("run");
  button.disabled = true;
  button.textContent = "Standardisation…";
  try {
    const result = await api().run(state.input, state.output, enabledRules(), $("annotate").checked);
    if (!result.success) {
      showError(result.message);
      return;
    }
    showError("");
    state.lastReport = result.report;
    state.lastOutput = result.output_path;
    state.filter = result.report.counts.flagged + result.report.counts.placeholder > 0 ? "review" : "all";
    renderReport();
  } finally {
    button.textContent = "Standardiser";
    updateRunButton();
  }
}

function renderReport() {
  const report = state.lastReport;
  const { corrected, placeholder } = report.counts;
  const toReview = report.paragraphs.filter((p) => p.needs_review).length;

  $("empty").hidden = true;
  $("report").hidden = false;

  if (report.paragraphs.length === 0) {
    $("headline").textContent = "Aucune ligne RMN trouvée dans ce document.";
  } else if (toReview === 0) {
    $("headline").textContent = `Tout est conforme : ${plural(corrected, "paragraphe corrigé", "paragraphes corrigés")}.`;
  } else {
    $("headline").textContent = `${plural(toReview, "paragraphe à vérifier", "paragraphes à vérifier")}, ${plural(corrected, "corrigé", "corrigés")}.`;
  }

  const details = [];
  if (placeholder) details.push(`${plural(placeholder, "marqueur inséré", "marqueurs insérés")} pour une donnée manquante`);
  if (report.comments) details.push(`${plural(report.comments, "commentaire ajouté", "commentaires ajoutés")} dans le document`);
  details.push(`enregistré sous ${splitPath(state.lastOutput)[1]}`);
  $("subline").textContent = details.join(", ") + ".";

  $("filter-review").textContent = `À vérifier (${toReview})`;
  $("filter-all").textContent = `Tous (${report.paragraphs.length})`;
  for (const b of document.querySelectorAll("[data-filter]")) {
    b.setAttribute("aria-pressed", String(b.dataset.filter === state.filter));
  }
  renderEntries();
}

function renderEntries() {
  const list = $("entries");
  list.innerHTML = "";
  const shown = state.lastReport.paragraphs.filter((p) => state.filter === "all" || p.needs_review);
  if (shown.length === 0) {
    const li = document.createElement("li");
    li.className = "none-left";
    li.textContent = "Rien à vérifier : toutes les lignes ont été corrigées automatiquement.";
    list.appendChild(li);
    return;
  }
  for (const p of shown) list.appendChild(renderEntry(p));
}

function renderEntry(p) {
  const li = document.createElement("li");
  li.className = "entry";
  const notes = p.actions.filter((a) => a.kind === "flagged" || a.kind === "placeholder");
  const fixes = p.actions.filter((a) => a.kind === "corrected");

  const noteHtml = notes.length
    ? notes
        .map(
          (a) => `<div class="note ${a.kind}"><strong>${escapeHtml(a.label)}</strong>${escapeHtml(a.message)}</div>`
        )
        .join("")
    : `<p class="note-ok">${p.changed ? "Corrigé automatiquement" : "Déjà conforme"}</p>`;

  const fixesHtml = fixes.length
    ? `<ul class="fixes">${fixes.map((a) => `<li>${escapeHtml(a.message)}</li>`).join("")}</ul>`
    : "";
  const beforeHtml = p.changed ? `<p class="before">${escapeHtml(p.before)}</p>` : "";

  li.innerHTML = `
    <p class="entry-where">${escapeHtml(p.label)}</p>
    <div>
      <p class="entry-text">${renderNmr(p.after)}</p>
      ${fixes.length || p.changed ? `<details><summary>Voir l'original et les corrections</summary>${beforeHtml}${fixesHtml}</details>` : ""}
    </div>
    <div class="notes">${noteHtml}</div>`;
  return li;
}

// --- Paramètres --------------------------------------------------------------------

function addMultRow(written = "", becomes = "") {
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input type="text" aria-label="Écrit dans le document" spellcheck="false" value="${escapeHtml(written)}"></td>
    <td><input type="text" aria-label="Devient" spellcheck="false" value="${escapeHtml(becomes)}"></td>
    <td><button type="button" class="link" aria-label="Retirer ${escapeHtml(written)}">Retirer</button></td>`;
  tr.querySelector("button").addEventListener("click", () => tr.remove());
  $("mult-rows").appendChild(tr);
  return tr;
}

function fillSettings(s) {
  $("mult-rows").innerHTML = "";
  for (const [written, becomes] of Object.entries(s.multiplicities)) addMultRow(written, becomes);
  $("sort-order").value = s.sort_order;
  $("temperature-unit").value = s.temperature_unit;
  $("placeholder").value = s.temperature_placeholder;
  $("bold-label").checked = s.bold_label;
  $("italic-delta").checked = s.italic_delta;
}

function collectSettings() {
  const multiplicities = {};
  for (const tr of $("mult-rows").querySelectorAll("tr")) {
    const [written, becomes] = [...tr.querySelectorAll("input")].map((i) => i.value.trim());
    if (written) multiplicities[written] = becomes || written;
  }
  return {
    multiplicities,
    sort_order: $("sort-order").value,
    temperature_unit: $("temperature-unit").value,
    temperature_placeholder: $("placeholder").value,
    bold_label: $("bold-label").checked,
    italic_delta: $("italic-delta").checked,
  };
}

// Le marqueur suit l'unité tant qu'il a sa forme par défaut ('[??? K]').
function onUnitChange() {
  const unit = $("temperature-unit").value;
  const field = $("placeholder");
  if (/^\[\?\?\? (K|°C)\]$/.test(field.value)) field.value = `[??? ${unit}]`;
}

async function saveSettings() {
  state.settings = await api().save_settings(collectSettings());
  $("settings").close();
  if (state.lastReport) renderEntries();
}

// --- Démarrage -------------------------------------------------------------------

function wire() {
  $("choose-input").addEventListener("click", chooseInput);
  $("change-input").addEventListener("click", chooseInput);
  $("choose-output").addEventListener("click", chooseOutput);
  $("run").addEventListener("click", run);
  $("open-output").addEventListener("click", () => api().open_output(state.lastOutput));
  for (const b of document.querySelectorAll("[data-filter]")) {
    b.addEventListener("click", () => {
      state.filter = b.dataset.filter;
      renderReport();
    });
  }

  $("open-settings").addEventListener("click", () => {
    fillSettings(state.settings);
    $("settings").showModal();
  });
  $("add-mult").addEventListener("click", () => addMultRow().querySelector("input").focus());
  $("temperature-unit").addEventListener("change", onUnitChange);
  $("reset-settings").addEventListener("click", () => fillSettings(state.defaults));
  $("cancel-settings").addEventListener("click", () => $("settings").close());
  $("save-settings").addEventListener("click", saveSettings);

  // Survol pendant un glisser-déposer (le dépôt lui-même est traité en Python).
  const zone = document.body;
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    $("dropzone").classList.add("hover");
  });
  zone.addEventListener("dragleave", (e) => {
    if (e.relatedTarget === null) $("dropzone").classList.remove("hover");
  });
  zone.addEventListener("drop", (e) => e.preventDefault());
}

async function start() {
  const initial = await api().get_state();
  state.settings = initial.settings;
  state.defaults = initial.defaults;
  renderRules(initial.rules);
  wire();
}

window.addEventListener("pywebviewready", start);
