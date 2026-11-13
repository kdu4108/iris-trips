/* Iris Trips voter UI — a strict ranking of a handful of festivals.
   Tap "Rank it" to append, ▲▼ to reorder, ✕ to unrank, drag on desktop.
   Auto-saves every change; shade ∝ positional score, as in iris-ranking. */
"use strict";

let state = INITIAL_STATE;             // {groups: [[festivalId], ...]}
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

/* ---------- rendering ---------- */

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function festBody(f) {
  const body = el("div", "fest-body");
  const head = el("div", "fest-head");
  head.append(el("span", "fest-flag", f.flag), el("span", "title", f.name));
  body.append(head);
  const meta = el("div", "meta");
  meta.textContent = `${f.place} · ${f.dates}`;
  body.append(meta);
  const facts = el("div", "fest-facts");
  const share = Math.max(0, f.cost_chf - IRIS_CHF);
  const cost = el("span", "fact cost", `~${f.cost_chf} CHF p.p.`);
  cost.title = `Estimated total per person. With Iris covering ~${IRIS_CHF} CHF, ` +
               `your share would be about ${share} CHF (subject to change).`;
  facts.append(cost);
  if (f.hard_to_get_in) facts.append(el("span", "fact hard", "might be hard to get in"));
  body.append(facts);
  body.append(el("div", "fest-blurb", f.blurb));
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
    li.append(pos, festBody(f), controls);
    if (fid === justPlaced) li.classList.add("just-placed");
    rankedEl.append(li);
  });
  justPlaced = null;

  const rankedSet = new Set(ids);
  const pool = FESTIVALS.filter(f => !rankedSet.has(f.id));
  poolEl.innerHTML = "";
  pool.forEach(f => {
    const card = el("div", "pool-card fest-card");
    card.dataset.fid = f.id;
    card.draggable = VOTING_OPEN;
    const actions = el("div", "pool-actions");
    const btn = el("button", "primary", `Rank it as #${n + 1}`);
    btn.type = "button";
    btn.disabled = !VOTING_OPEN;
    btn.addEventListener("click", () => rank(f.id, n + 1));
    actions.append(btn);
    card.append(festBody(f), actions);
    poolEl.append(card);
  });

  document.getElementById("ranked-empty").style.display = n ? "none" : "";
  document.getElementById("band-legend").style.display = n > 1 ? "" : "none";
  document.getElementById("all-done").style.display = n === N_TOTAL ? "" : "none";
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
