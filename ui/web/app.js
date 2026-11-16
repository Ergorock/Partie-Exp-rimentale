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
  lastScores: null,
  lastEvaluation: null,
  filter: "review",
  cursor: -1, // index du paragraphe à vérifier sélectionné (navigation J / K)
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

// Aperçu de la mise en forme produite dans Word : label seul en gras,
// δ et J en italique (selon les paramètres), m/z en italique. Affichage seulement.
function renderNmr(text) {
  let html = escapeHtml(text);
  if (state.settings?.bold_label !== false) {
    html = html.replace(
      /([⁰¹²³⁴-⁹]+[A-Za-z]+(?:\{[^}]*\})?\s*(?:NMR|RMN))(?=\s*\()/g,
      "<b>$1</b>"
    );
    html = html.replace(/\bHRMS(?=(?: \([^)]*\))? m\/z)/g, "<b>HRMS</b>");
    html = html.replace(/\bRf(?= = )/g, "<b>R<sub>f</sub></b>");
  }
  if (state.settings?.italic_delta !== false) {
    html = html.replace(/δ/g, "<i>δ</i>");
  }
  html = html.replace(/\bm\/z(?=:)/g, "<i>m/z</i>");
  // Aperçu seulement : le d des solvants deutérés (DMSO-d₆, TFA-d) en italique.
  html = html.replace(/(-)d(?=[₀-₉]*, )/g, "$1<i>d</i>");
  if (state.settings?.italic_j !== false) {
    html = html.replace(/(?<![A-Za-z])J(?=\s*=)/g, "<i>J</i>");
  }
  return html;
}

// --- Surlignage dans le texte ---------------------------------------------------
// Les empans (début, fin, cas) sont calculés en Python (core/highlights.py) sur
// le texte final ; ici on se contente de les poser sur le texte déjà mis en
// forme (gras / italique), en découpant les noeuds texte pour que les balises
// existantes restent correctement imbriquées.
const HL_TITLES = {
  corrected: "Corrigé automatiquement",
  flagged: "À vérifier",
  placeholder: "Marqueur inséré (donnée manquante)",
};
// Mise en forme RÉELLE du document (gras, italique, exposant, indice) : les
// runs Word sont lus en Python (docx_io.paragraph_formats) ; ici, affichage seul.
const FORMAT_TAGS = { b: "b", i: "i", sup: "sup", sub: "sub" };
function renderFormatted(text, formats) {
  if (!formats) return renderNmr(text);
  const cuts = new Set([0, text.length]);
  for (const [a, b] of formats) {
    cuts.add(a);
    cuts.add(b);
  }
  const points = [...cuts].filter((c) => c >= 0 && c <= text.length).sort((x, y) => x - y);
  let html = "";
  for (let k = 0; k < points.length - 1; k++) {
    const [a, b] = [points[k], points[k + 1]];
    const tags = formats.filter(([s, e]) => s <= a && e >= b).map(([, , kind]) => FORMAT_TAGS[kind]).filter(Boolean);
    html += tags.map((t) => `<${t}>`).join("") + escapeHtml(text.slice(a, b)) + tags.reverse().map((t) => `</${t}>`).join("");
  }
  return html;
}
function highlightHtml(text, spans, formats) {
  const box = document.createElement("div");
  box.innerHTML = renderFormatted(text, formats);
  if (!spans || spans.length === 0) return box.innerHTML;
  const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let offset = 0;
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    nodes.push({ node: n, start: offset });
    offset += n.nodeValue.length;
  }
  for (const { node, start } of nodes) {
    const value = node.nodeValue;
    const end = start + value.length;
    const hits = spans.filter((s) => s.start < end && s.end > start);
    if (hits.length === 0) continue;
    const fragment = document.createDocumentFragment();
    let pos = 0;
    for (const s of hits) {
      const a = Math.max(s.start, start) - start;
      const b = Math.min(s.end, end) - start;
      if (a > pos) fragment.append(value.slice(pos, a));
      const mark = document.createElement("mark");
      mark.className = `hl hl-${s.kind}`;
      mark.title = HL_TITLES[s.kind] || "";
      mark.textContent = value.slice(a, b);
      fragment.append(mark);
      pos = b;
    }
    if (pos < value.length) fragment.append(value.slice(pos));
    node.replaceWith(fragment);
  }
  return box.innerHTML;
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
  // Les résultats affichés concernaient le document précédent.
  state.lastReport = null;
  state.lastEvaluation = null;
  showView(null);
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
  updateRulesCount();
}

function enabledRules() {
  return [...document.querySelectorAll("[data-rule]")].filter((c) => c.checked).map((c) => c.dataset.rule);
}

// Résumé affiché dans l'en-tête repliable : « 6 sur 6 actives ».
function updateRulesCount() {
  const total = document.querySelectorAll("[data-rule]").length;
  $("rules-count").textContent = total ? `${enabledRules().length} sur ${total} actives` : "";
}

function updateRunButton() {
  updateRulesCount();
  $("run").disabled = !state.input || !state.output || enabledRules().length === 0;
  $("evaluate").disabled = !state.input || enabledRules().length === 0;
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
    state.lastScores = result.scores;
    state.filter = result.report.counts.flagged + result.report.counts.placeholder > 0 ? "review" : "all";
    renderReport();
  } finally {
    button.textContent = "Standardiser";
    updateRunButton();
  }
}

// Vue affichée dans la zone de résultats : "report", "evaluation" ou null
// (état vide). La bascule n'apparaît que si les deux résultats existent.
function showView(view) {
  $("empty").hidden = view !== null;
  $("report").hidden = view !== "report";
  $("evaluation").hidden = view !== "evaluation";
  $("views").hidden = !(state.lastReport && state.lastEvaluation);
  for (const b of document.querySelectorAll("[data-view]")) {
    b.setAttribute("aria-pressed", String(b.dataset.view === view));
  }
}

// Score de conformité avant / après standardisation (mêmes règles).
function renderShift() {
  const { before, after } = state.lastScores || {};
  const known = before?.score != null && after?.score != null;
  $("shift").hidden = !known;
  if (!known) return;
  $("shift-before").textContent = percent(before.score);
  $("shift-after").textContent = percent(after.score);
  $("shift-grade").textContent = after.grade;
  $("shift-grade").dataset.tone = gradeTone(after.grade);
}

function renderReport() {
  const report = state.lastReport;
  const { corrected, placeholder } = report.counts;
  const toReview = report.paragraphs.filter((p) => p.needs_review).length;

  showView("report");
  renderShift();

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
  }
  for (const p of shown) list.appendChild(renderEntry(p));
  state.cursor = -1;
  updateStep();
}

// --- Navigation entre paragraphes à vérifier (boutons, touches J / K) ----------

function reviewEntries() {
  return [...$("entries").querySelectorAll(".entry[data-review]")];
}

function updateStep() {
  const total = reviewEntries().length;
  $("step").hidden = total === 0;
  $("step-pos").textContent = state.cursor < 0 ? "" : `${state.cursor + 1} sur ${total}`;
  $("prev-review").disabled = state.cursor <= 0;
  $("next-review").disabled = state.cursor >= total - 1;
}

function goToReview(delta) {
  const list = reviewEntries();
  if (list.length === 0) return;
  const next = state.cursor < 0 ? (delta > 0 ? 0 : list.length - 1) : state.cursor + delta;
  state.cursor = Math.max(0, Math.min(list.length - 1, next));
  list.forEach((el, i) => el.classList.toggle("is-current", i === state.cursor));
  const target = list[state.cursor];
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  target.scrollIntoView({ block: "start", behavior: smooth ? "smooth" : "auto" });
  target.focus({ preventScroll: true });
  updateStep();
}

function onKey(event) {
  if (event.ctrlKey || event.metaKey || event.altKey || $("report").hidden) return;
  if ($("settings").open || event.target.closest("input, select, textarea")) return;
  const key = event.key.toLowerCase();
  if (key === "j") goToReview(1);
  else if (key === "k") goToReview(-1);
  else return;
  event.preventDefault();
}

// Classe de surlignage d'une entrée : la plus grave prime (à vérifier, marqueur, corrigé).
function entryTone(actions, changed) {
  if (actions.some((a) => a.kind === "flagged")) return "is-flagged";
  if (actions.some((a) => a.kind === "placeholder")) return "is-placeholder";
  return changed || actions.some((a) => a.kind === "corrected") ? "is-fixed" : "is-ok";
}
function renderEntry(p) {
  const li = document.createElement("li");
  li.className = `entry ${entryTone(p.actions, p.changed)}`;
  li.tabIndex = -1;
  if (p.needs_review) li.dataset.review = "";
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
  const beforeHtml = p.changed ? `<p class="before">${renderFormatted(p.before, p.before_formats)}</p>` : "";

  li.innerHTML = `
    <p class="entry-where">${escapeHtml(p.label)}</p>
    <div>
      <p class="entry-text">${highlightHtml(p.after, p.spans, p.after_formats)}</p>
      ${fixes.length || p.changed ? `<details><summary>Voir l'original et les corrections</summary>${beforeHtml}${fixesHtml}</details>` : ""}
    </div>
    <div class="notes">${noteHtml}</div>`;
  return li;
}

// --- Évaluation (le calcul est en Python ; ici, affichage seulement) -------------

const THRESHOLD_KEYS = ["parfait", "tres_bon", "bon", "correct"];
const STATUS_ORDER = { "à vérifier": 0, "corrigé": 1, "conforme": 2 };
const ISSUE_LABELS = { flagged: "À vérifier", placeholder: "Marqueur", corrected: "Corrigeable" };

// Tonalité de la note : verte (Parfait, Très bon), ambre (Bon, Correct), rouge.
function gradeTone(grade) {
  if (grade === "Parfait" || grade === "Très bon") return "good";
  if (grade === "Bon" || grade === "Correct") return "fair";
  if (grade === "Mauvais") return "bad";
  return "none";
}

function percent(value) {
  return `${Math.round(value)} %`;
}

async function evaluate() {
  const button = $("evaluate");
  button.disabled = true;
  button.textContent = "Évaluation…";
  try {
    const result = await api().evaluate(state.input, enabledRules());
    if (!result.success) {
      showError(result.message);
      return;
    }
    showError("");
    state.lastEvaluation = result.evaluation;
    renderEvaluation(result.evaluation);
  } finally {
    button.textContent = "Évaluer sans modifier";
    updateRunButton();
  }
}

function renderEvaluation(ev) {
  showView("evaluation");

  const tone = gradeTone(ev.grade);
  $("eval-score").textContent = ev.score === null ? "—" : percent(ev.score);
  $("eval-grade").textContent = ev.grade;
  $("eval-grade").dataset.tone = tone;
  $("eval-fill").dataset.tone = tone;
  $("eval-fill").style.width = `${ev.score ?? 0}%`;

  // Repères des seuils sur la jauge.
  const gauge = $("eval-gauge");
  gauge.querySelectorAll(".tick").forEach((t) => t.remove());
  for (const key of THRESHOLD_KEYS) {
    const value = ev.thresholds[key];
    if (value <= 0 || value >= 100) continue;
    const tick = document.createElement("span");
    tick.className = "tick";
    tick.style.left = `${value}%`;
    gauge.appendChild(tick);
  }

  const name = splitPath(state.input)[1];
  if (ev.total === 0) {
    $("eval-subline").textContent = `Aucune section reconnue par les règles dans ${name}.`;
  } else {
    const c = ev.counts;
    $("eval-subline").textContent =
      `${ev.ok} sur ${plural(ev.total, "section", "sections")} conforme${ev.ok > 1 ? "s" : ""}` +
      ` · ${c["corrigé"]} corrigeable${c["corrigé"] > 1 ? "s" : ""} automatiquement` +
      ` · ${c["à vérifier"]} à vérifier · ${name}`;
  }

  $("eval-rules-block").hidden = ev.by_rule.length === 0;
  $("eval-rules").innerHTML = ev.by_rule
    .map(
      (r) => `<tr>
        <th scope="row"><span class="rule-name">${escapeHtml(prettyRuleName(r.rule))}</span></th>
        <td class="bar"><span class="track"><span class="fill" style="width:${r.score}%"></span></span></td>
        <td class="num">${percent(r.score)}</td>
        <td class="num muted">${r.ok}/${r.total}</td>
      </tr>`
    )
    .join("");

  $("eval-issues-block").hidden = ev.issues.length === 0;
  $("eval-issues").innerHTML = ev.issues
    .map(
      (i) => `<li class="issue ${i.kind}">
        <span class="issue-kind">${ISSUE_LABELS[i.kind] || i.kind}</span>
        <span class="issue-text"><span class="rule-tag">${escapeHtml(prettyRuleName(i.rule))}</span> ${escapeHtml(i.description)}</span>
        <span class="num">${plural(i.count, "section", "sections")}</span>
      </li>`
    )
    .join("");

  const bad = ev.items
    .filter((i) => i.status !== "conforme")
    .sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status]);
  $("eval-items-block").hidden = bad.length === 0;
  $("eval-items").innerHTML = "";
  for (const item of bad) $("eval-items").appendChild(renderEvalItem(item));
}

function renderEvalItem(item) {
  const li = document.createElement("li");
  li.className = `entry ${entryTone(item.actions, item.status === "corrigé")}`;
  const notes = item.actions.filter((a) => a.kind !== "corrected");
  const fixes = item.actions.filter((a) => a.kind === "corrected");
  const notesHtml = notes
    .map((a) => `<div class="note ${a.kind}"><strong>${escapeHtml(a.label)}</strong>${escapeHtml(a.message)}</div>`)
    .join("");
  const fixesHtml = fixes.length
    ? `<ul class="fixes">${fixes.map((a) => `<li>${escapeHtml(a.message)}</li>`).join("")}</ul>`
    : "";
  li.innerHTML = `
    <p class="entry-where">${escapeHtml(item.label)} · ${escapeHtml(prettyRuleName(item.rule))} · ${escapeHtml(item.status)}</p>
    <div>
      <p class="entry-text">${highlightHtml(item.text, item.spans, [])}</p>
      ${fixesHtml ? `<details open><summary>Corrections que la standardisation appliquerait</summary>${fixesHtml}</details>` : ""}
    </div>
    <div class="notes">${notesHtml || '<p class="note-ok">Corrigeable automatiquement</p>'}</div>`;
  return li;
}

// --- Paramètres --------------------------------------------------------------------

function addMultRow(written = "", becomes = "", bodyId = "mult-rows") {
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input type="text" aria-label="Écrit dans le document" spellcheck="false" value="${escapeHtml(written)}"></td>
    <td><input type="text" aria-label="Devient" spellcheck="false" value="${escapeHtml(becomes)}"></td>
    <td><button type="button" class="link" aria-label="Retirer ${escapeHtml(written)}">Retirer</button></td>`;
  tr.querySelector("button").addEventListener("click", () => tr.remove());
  $(bodyId).appendChild(tr);
  return tr;
}

// Lit un tableau « Écrit / Devient » en dictionnaire (valeur vide : la clé).
function collectRows(bodyId) {
  const table = {};
  for (const tr of $(bodyId).querySelectorAll("tr")) {
    const [written, becomes] = [...tr.querySelectorAll("input")].map((i) => i.value.trim());
    if (written) table[written] = becomes || written;
  }
  return table;
}

function fillSettings(s) {
  $("mult-rows").innerHTML = "";
  for (const [written, becomes] of Object.entries(s.multiplicities)) addMultRow(written, becomes);
  $("solvent-rows").innerHTML = "";
  for (const [written, becomes] of Object.entries(s.solvents || {})) addMultRow(written, becomes, "solvent-rows");
  $("sort-order").value = s.sort_order;
  $("temperature-unit").value = s.temperature_unit;
  $("placeholder").value = s.temperature_placeholder;
  $("bold-label").checked = s.bold_label;
  $("italic-delta").checked = s.italic_delta;
  $("italic-j").checked = s.italic_j;
  $("check-temperature").checked = s.check_temperature !== false;
  $("convert-decimal-comma").checked = s.convert_decimal_comma !== false;
  $("hrms-ppm").value = s.hrms_ppm_tolerance;
  $("hrms-abs").value = s.hrms_abs_tolerance;
  for (const key of THRESHOLD_KEYS) $(`th-${key}`).value = s.evaluation_thresholds[key];
}

function collectSettings() {
  return {
    multiplicities: collectRows("mult-rows"),
    solvents: collectRows("solvent-rows"),
    sort_order: $("sort-order").value,
    temperature_unit: $("temperature-unit").value,
    temperature_placeholder: $("placeholder").value,
    bold_label: $("bold-label").checked,
    italic_delta: $("italic-delta").checked,
    italic_j: $("italic-j").checked,
    check_temperature: $("check-temperature").checked,
    convert_decimal_comma: $("convert-decimal-comma").checked,
    hrms_ppm_tolerance: Number($("hrms-ppm").value),
    hrms_abs_tolerance: Number($("hrms-abs").value),
    hrms_abs_tolerance: Number($("hrms-abs").value),
    evaluation_thresholds: Object.fromEntries(THRESHOLD_KEYS.map((k) => [k, Number($(`th-${k}`).value)])),
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

// --- Exemple de l'état vide --------------------------------------------------------
// Sortie réelle du traitement pour cette ligne (texte, empans et messages copiés
// depuis core) : l'exemple utilise le même rendu qu'un vrai rapport.
const DEMO = {
  label: "Exemple",
  before: "1H NMR (400 MHz, CDCl3) δ 7.26 (d, J=8,1 Hz, 2H), 7.45 (ddq, J = 8.1 Hz, 2H), 2.31 (s, 3H)",
  after: "¹H NMR (400 MHz, CDCl₃, [??? K]) δ (ppm) = 7.26 (d, J=8,1 Hz, 2H), 7.45 (ddq, J = 8.1 Hz, 2H), 2.31 (s, 3H)",
  changed: true,
  needs_review: true,
  spans: [
    { start: 0, end: 2, kind: "corrected" },
    { start: 17, end: 24, kind: "corrected" },
    { start: 24, end: 31, kind: "placeholder" },
    { start: 34, end: 42, kind: "corrected" },
    { start: 67, end: 93, kind: "flagged" },
  ],
  actions: [
    { kind: "corrected", message: "Solvant en indices Unicode : 'CDCl3' -> 'CDCl₃'." },
    { kind: "placeholder", label: "Marqueur", message: "Température absente : marqueur '[??? K]' inséré." },
    {
      kind: "flagged",
      label: "À vérifier",
      message:
        "Un ou plusieurs signaux n'ont pas pu être analysés : liste des signaux laissée telle quelle, vérification manuelle.",
    },
  ],
};

function renderDemo() {
  const li = renderEntry(DEMO);
  li.querySelector("details").open = true;
  $("demo").replaceChildren(li);
}

// --- Démarrage -------------------------------------------------------------------

function wire() {
  $("choose-input").addEventListener("click", chooseInput);
  $("change-input").addEventListener("click", chooseInput);
  $("choose-output").addEventListener("click", chooseOutput);
  $("run").addEventListener("click", run);
  $("evaluate").addEventListener("click", evaluate);
  $("open-output").addEventListener("click", () => api().open_output(state.lastOutput));
  for (const b of document.querySelectorAll("[data-filter]")) {
    b.addEventListener("click", () => {
      state.filter = b.dataset.filter;
      renderReport();
    });
  }
  for (const b of document.querySelectorAll("[data-view]")) {
    b.addEventListener("click", () => {
      if (b.dataset.view === "report") renderReport();
      else renderEvaluation(state.lastEvaluation);
    });
  }
  $("prev-review").addEventListener("click", () => goToReview(-1));
  $("next-review").addEventListener("click", () => goToReview(1));
  document.addEventListener("keydown", onKey);

  $("open-settings").addEventListener("click", () => {
    fillSettings(state.settings);
    $("settings").showModal();
  });
  $("add-mult").addEventListener("click", () => addMultRow().querySelector("input").focus());
  $("add-solvent").addEventListener(
    "click", () => addMultRow("", "", "solvent-rows").querySelector("input").focus()
  );
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
  renderDemo();
  wire();
}

window.addEventListener("pywebviewready", start);
