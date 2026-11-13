/* Iris Trips voter UI — a strict ranking of a handful of festivals.
   Tap "Rank it" to append, ▲▼ to reorder, ✕ to unrank, drag on desktop.
   Auto-saves every change; shade ∝ positional score, as in iris-ranking. */
"use strict";

let state = INITIAL_STATE;             // {groups: [[festivalId], ...], cant_go: [ids]}
const fests = {};
FESTIVALS.forEach(f => { fests[f.id] = f; });
const N_TOTAL = FESTIVALS.length;

const rankedEl = document.getElementById("ranked-list");
const poolEl = document.getElementById("pool");
const saveStatus = document.getElementById("save-status");
const SAVE_IDLE = saveStatus.textContent;
let saveTimer = null;
let dragFid = null;
let justPlaced = null;

function flatIds() { return state.groups.flat(); }

function scoreAt(i, n) { return 1 - (i + 0.5) / n; }   // i is 0-based

function colorFor(s) {
  // Same diverging scale as iris-ranking: neutral at 0.5, blue = upper
  // half of your list, red = lower half, deeper toward the ends.
  const pct = Math.round(Math.abs(s - 0.5) * 200);
  const [bgEnd, barEnd] = s >= 0.5 ? ["#94c1e1", "#2166ac"] : ["#ec9f88", "#b2182b"];
  return {
    bg: `color-mix(in oklab, ${bgEnd} ${pct}%, #f6f5f2)`,
    bar: `color-mix(in oklab, ${barEnd} ${pct}%, #d8d5cc)`,
  };
}

/* ---------- server ---------- */

function flashSaved() {
  saveStatus.textContent = "✓ saved";
  saveStatus.classList.add("saved");
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    saveStatus.textContent = SAVE_IDLE;
    saveStatus.classList.remove("saved");
  }, 1400);
}

async function post(url, body) {
  if (!VOTING_OPEN) { alert("Voting is closed."); return; }
  try {
    const resp = await fetch(url, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      alert(resp.status === 403 ? "Voting is closed." : "Could not save — please reload.");
      return;
    }
    state = await resp.json();
    flashSaved();
    render();
  } catch (e) {
    alert("Network error — your last change may not be saved. Please reload.");
  }
}

function rank(fid, position) {
  justPlaced = fid;
  return post("/api/rank", {festival_id: fid, position});
}
function unrank(fid) { return post("/api/unrank", {festival_id: fid}); }
function setCantGo(fid, on) { return post("/api/cant_go", {festival_id: fid, cant_go: on}); }

/* ---------- rendering ---------- */

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function festBody(f, compact) {
  // Key facts (name, dates, place, price) up front; the description and the
  // "hard to get in" caveat sit in a quieter line below (full cards only).
  const body = el("div", "fest-body");
  const head = el("div", "fest-head");
  let title;
  if (f.url) {
    title = el("a", "title fest-title-link", f.name);
    title.href = f.url;
    title.target = "_blank";
    title.rel = "noopener";
    title.title = "Open the festival website";
    title.draggable = false;
  } else {
    title = el("span", "title", f.name);
  }
  head.append(el("span", "fest-flag", f.flag), title);
  body.append(head);

  const facts = el("div", "fest-keyfacts");
  const cost = el("span", "kf kf-cost", `~${f.cost_chf} CHF`);
  cost.title = `Estimated total per person. Iris expects to cover ~${IRIS_CHF} CHF, ` +
               `so your share would be about ${Math.max(0, f.cost_chf - IRIS_CHF)} CHF ` +
               `(subject to change).`;
  const place = el("a", "kf kf-place", f.place);
  place.href = "https://www.google.com/maps/search/?api=1&query=" +
               encodeURIComponent(f.place);
  place.target = "_blank";
  place.rel = "noopener";
  place.title = "Show on Google Maps";
  place.draggable = false;
  facts.append(el("span", "kf kf-date", f.dates), place, cost);
  body.append(facts);
  if (compact) return body;

  const note = el("div", "fest-note");
  note.textContent = f.blurb;
  if (f.hard_to_get_in) {
    note.append(" ");
    note.append(el("span", "fest-hard", "· might be hard to get in"));
  }
  body.append(note);
  return body;
}

function iconBtn(label, title, onClick, disabled) {
  const b = el("button", "icon", label);
  b.type = "button";
  b.title = title;
  b.setAttribute("aria-label", title);
  b.disabled = !!disabled || !VOTING_OPEN;
  b.addEventListener("click", onClick);
  return b;
}

function render() {
  const ids = flatIds();
  const n = ids.length;
  rankedEl.innerHTML = "";
  ids.forEach((fid, i) => {
    const f = fests[fid];
    if (!f) return;
    const li = el("li", "ranked-item fest-item");
    li.dataset.fid = fid;
    const c = colorFor(n > 1 ? scoreAt(i, n) : 0.5);
    li.style.background = c.bg;
    li.style.borderLeftColor = c.bar;
    li.draggable = VOTING_OPEN;
    const pos = el("span", "pos", String(i + 1));
    const controls = el("div", "controls");
    controls.append(
      iconBtn("▲", `Move ${f.name} up`, () => rank(fid, i), i === 0),
      iconBtn("▼", `Move ${f.name} down`, () => rank(fid, i + 2), i === n - 1),
      iconBtn("✕", `Remove ${f.name} from your ranking`, () => unrank(fid)),
    );
    li.append(pos, festBody(f, true), controls);
    if (fid === justPlaced) li.classList.add("just-placed");
    rankedEl.append(li);
  });
  justPlaced = null;

  const cantSet = new Set(state.cant_go || []);
  const rankedSet = new Set(ids);
  const pool = FESTIVALS.filter(f => !rankedSet.has(f.id) && !cantSet.has(f.id));
  poolEl.innerHTML = "";
  pool.forEach(f => {
    const card = el("div", "pool-card fest-card");
    card.dataset.fid = f.id;
    card.draggable = VOTING_OPEN;
    const actions = el("div", "pool-actions");
    const btn = el("button", "primary", `Rank #${n + 1}`);
    btn.type = "button";
    btn.disabled = !VOTING_OPEN;
    btn.addEventListener("click", () => rank(f.id, n + 1));
    const no = el("button", "cantgo-btn", "🚫 Can't go");
    no.type = "button";
    no.disabled = !VOTING_OPEN;
    no.title = "I absolutely can't attend this one";
    no.addEventListener("click", () => setCantGo(f.id, true));
    actions.append(btn, no);
    card.append(festBody(f), actions);
    poolEl.append(card);
  });

  const cantEl = document.getElementById("cantgo");
  cantEl.innerHTML = "";
  FESTIVALS.filter(f => cantSet.has(f.id)).forEach(f => {
    const card = el("div", "pool-card fest-card");
    const actions = el("div", "pool-actions");
    const undo = el("button", "", "Undo");
    undo.type = "button";
    undo.disabled = !VOTING_OPEN;
    undo.addEventListener("click", () => setCantGo(f.id, false));
    actions.append(undo);
    card.append(festBody(f, true), actions);
    cantEl.append(card);
  });
  document.getElementById("cantgo-section").style.display = cantSet.size ? "" : "none";
  // Nothing left in the left column: let the ranking take the full width.
  document.getElementById("vote-layout").classList.toggle(
    "pool-empty", !pool.length && !cantSet.size);

  document.getElementById("ranked-empty").style.display = n || !pool.length ? "none" : "";
  document.getElementById("all-done").style.display =
    n + cantSet.size === N_TOTAL ? "" : "none";
  document.getElementById("pool-section").style.display = pool.length ? "" : "none";
  document.getElementById("pool-count").textContent =
    pool.length ? `(${pool.length} left)` : "";
}

/* ---------- drag & drop (desktop) ---------- */

function dropIndex(clientY) {
  // 0-based insertion index among ranked rows other than the dragged one.
  const rows = [...rankedEl.querySelectorAll(".fest-item")]
    .filter(r => Number(r.dataset.fid) !== dragFid);
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i].getBoundingClientRect();
    if (clientY < r.top + r.height / 2) return i;
  }
  return rows.length;
}

const insertLine = el("li", "insert-line");

document.addEventListener("dragstart", e => {
  const src = e.target.closest && e.target.closest("[data-fid]");
  if (!src) return;
  dragFid = Number(src.dataset.fid);
  src.classList.add("dragging");
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", String(dragFid));
});

document.addEventListener("dragend", e => {
  const src = e.target.closest && e.target.closest("[data-fid]");
  if (src) src.classList.remove("dragging");
  insertLine.remove();
  rankedEl.classList.remove("drop-target");
  dragFid = null;
});

const dropZone = document.querySelector(".sec-ranking");
dropZone.addEventListener("dragover", e => {
  if (dragFid === null) return;
  e.preventDefault();
  rankedEl.classList.add("drop-target");
  const idx = dropIndex(e.clientY);
  const rows = [...rankedEl.querySelectorAll(".fest-item")]
    .filter(r => Number(r.dataset.fid) !== dragFid);
  if (idx < rows.length) rankedEl.insertBefore(insertLine, rows[idx]);
  else rankedEl.append(insertLine);
});
dropZone.addEventListener("dragleave", e => {
  if (!dropZone.contains(e.relatedTarget)) {
    insertLine.remove();
    rankedEl.classList.remove("drop-target");
  }
});
dropZone.addEventListener("drop", e => {
  if (dragFid === null) return;
  e.preventDefault();
  const fid = dragFid;
  const idx = dropIndex(e.clientY);
  insertLine.remove();
  rankedEl.classList.remove("drop-target");
  const current = flatIds().indexOf(fid);
  if (current !== idx) rank(fid, idx + 1);
});

render();
