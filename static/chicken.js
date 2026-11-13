/* 🐣 easter egg: hold the chick button to grow an egg — the longer the hold,
   the bigger the hatchling. Heads bounce off walls and each other. Press and
   hold a head to charge it with energy; release to send it flying — a full
   charge is explosive and shockwaves the whole flock. Refresh to clear. */
"use strict";
(() => {
  const btn = document.getElementById("chick-btn");
  if (!btn) return;

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const MIN_SIZE = 56, MAX_SIZE = 150, MAX_HOLD_MS = 2800;
  const MAX_CHARGE_MS = 2000;
  let shots = null;
  const heads = [];
  let raf = null;

  async function getShots() {
    if (shots) return shots;
    try {
      const resp = await fetch("/api/headshots");
      shots = resp.ok ? await resp.json() : [];
    } catch (e) {
      shots = [];
    }
    return shots;
  }

  /* ---------- physics ---------- */

  function collide(a, b) {
    const ra = a.size / 2, rb = b.size / 2;
    const dx = (b.x + rb) - (a.x + ra);
    const dy = (b.y + rb) - (a.y + ra);
    const d = Math.hypot(dx, dy);
    const minD = ra + rb;
    if (d <= 0 || d >= minD) return;
    const nx = dx / d, ny = dy / d;
    // mass ~ area; a held head is effectively immovable
    const ma = ra * ra * (a.held ? 1e6 : 1);
    const mb = rb * rb * (b.held ? 1e6 : 1);
    const overlap = minD - d;
    a.x -= nx * overlap * (mb / (ma + mb));
    a.y -= ny * overlap * (mb / (ma + mb));
    b.x += nx * overlap * (ma / (ma + mb));
    b.y += ny * overlap * (ma / (ma + mb));
    const rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
    if (rel >= 0) return;
    const imp = -2 * rel / (1 / ma + 1 / mb);
    a.vx -= imp * nx / ma;
    a.vy -= imp * ny / ma;
    b.vx += imp * nx / mb;
    b.vy += imp * ny / mb;
  }

  function tick() {
    const W = window.innerWidth, H = window.innerHeight;
    for (const h of heads) {
      if (h.held) { h.vx = 0; h.vy = 0; continue; }
      h.x += h.vx;
      h.y += h.vy;
      if (h.x <= 0) { h.x = 0; h.vx = Math.abs(h.vx); }
      if (h.x >= W - h.size) { h.x = W - h.size; h.vx = -Math.abs(h.vx); }
      if (h.y <= 0) { h.y = 0; h.vy = Math.abs(h.vy); }
      if (h.y >= H - h.size) { h.y = H - h.size; h.vy = -Math.abs(h.vy); }
    }
    for (let i = 0; i < heads.length; i++) {
      for (let j = i + 1; j < heads.length; j++) collide(heads[i], heads[j]);
    }
    if (charge.head) {
      // growing glow while charging
      const t = chargeT();
      charge.head.el.style.boxShadow =
        `0 0 ${10 + 45 * t}px ${4 + 12 * t}px rgba(181, 137, 0, ${0.35 + 0.5 * t}), ` +
        `0 3px 10px rgba(0, 0, 0, 0.28)`;
    }
    for (const h of heads) {
      if (!h.held) {
        // ease back toward cruising speed after bursts/collisions
        const s = Math.hypot(h.vx, h.vy);
        if (s > 0.01) {
          const f = 1 + (h.cruise - s) / s * 0.012;
          h.vx *= f;
          h.vy *= f;
        }
        h.angle += h.vx * (56 / h.size);   // bigger heads roll slower
      }
      h.el.style.transform = `translate(${h.x}px, ${h.y}px) rotate(${h.angle}deg)`;
    }
    raf = requestAnimationFrame(tick);
  }

  /* ---------- charge-a-head (hold to power up, release to launch) ---------- */

  const charge = { head: null, start: 0 };

  function chargeT() {
    return Math.min(performance.now() - charge.start, MAX_CHARGE_MS) / MAX_CHARGE_MS;
  }

  function releaseCharge() {
    const h = charge.head;
    if (!h) return;
    const t = chargeT();
    charge.head = null;
    h.held = false;
    h.el.classList.remove("charging");
    h.el.style.boxShadow = "";
    const speed = 7 + 38 * t * t;   // quadratic: a full charge is explosive
    const ang = Math.random() * 2 * Math.PI;
    h.vx = speed * Math.cos(ang);
    h.vy = speed * Math.sin(ang);
    h.el.classList.remove("burst", "mega-burst");
    void h.el.offsetWidth;   // restart the flash animation
    h.el.classList.add(t > 0.85 ? "mega-burst" : "burst");
    if (t > 0.85) {
      // shockwave: everyone else gets knocked away too
      const cx = h.x + h.size / 2, cy = h.y + h.size / 2;
      for (const o of heads) {
        if (o === h || o.held) continue;
        const dx = o.x + o.size / 2 - cx, dy = o.y + o.size / 2 - cy;
        const d = Math.max(Math.hypot(dx, dy), 40);
        const push = 2600 * t / d;   // stronger when closer
        o.vx += dx / d * push;
        o.vy += dy / d * push;
      }
    }
  }

  function release(src, x, y, size) {
    const el = document.createElement("div");
    el.className = "chick-head";
    el.style.width = el.style.height = size + "px";
    el.style.backgroundImage = `url("${src}")`;
    document.body.appendChild(el);
    const speed = 2.2 + Math.random() * 2.2;
    const dir = Math.PI * (1.1 + Math.random() * 0.8);   // launch up-ish
    const h = {
      el, size,
      x: Math.max(0, Math.min(x, window.innerWidth - size)),
      y: Math.max(0, Math.min(y, window.innerHeight - size)),
      vx: speed * Math.cos(dir),
      vy: speed * Math.sin(dir) - 1.5,
      angle: Math.random() * 360,
      cruise: 1.8 + Math.random() * 1.8,
      held: false,
    };
    if (Math.abs(h.vx) < 0.8) h.vx = h.vx < 0 ? -0.8 : 0.8;
    heads.push(h);
    el.style.transform = `translate(${h.x}px, ${h.y}px) rotate(${h.angle}deg)`;

    el.addEventListener("pointerdown", e => {
      e.preventDefault();
      e.stopPropagation();
      if (charge.head) return;
      charge.head = h;
      charge.start = performance.now();
      h.held = true;
      el.classList.add("charging");
    });

    if (!reduced && !raf) raf = requestAnimationFrame(tick);
  }

  /* ---------- hold-to-grow hatching ---------- */

  const hold = { egg: null, start: 0, raf: null, src: null, active: false };

  function eggSizeFor(ms) {
    const t = Math.min(ms, MAX_HOLD_MS) / MAX_HOLD_MS;
    return 42 + t * 100;   // egg font-size px
  }

  function headSizeFor(ms) {
    const t = Math.min(ms, MAX_HOLD_MS) / MAX_HOLD_MS;
    return Math.round(MIN_SIZE + t * (MAX_SIZE - MIN_SIZE));
  }

  async function startHold() {
    if (hold.active || hold.egg) return;
    hold.active = true;
    const list = await getShots();
    if (!list.length || !hold.active) { hold.active = false; return; }
    hold.src = "/static/headshots/" +
      list[Math.floor(Math.random() * list.length)];
    new Image().src = hold.src;   // preload while the egg grows

    const rect = btn.getBoundingClientRect();
    const egg = document.createElement("div");
    egg.className = "chick-egg";
    egg.textContent = "🥚";
    // anchor bottom-center above the button so growth expands upward
    egg.style.right = (window.innerWidth - rect.right) + "px";
    egg.style.bottom = (window.innerHeight - rect.top + 10) + "px";
    egg.style.fontSize = eggSizeFor(0) + "px";
    document.body.appendChild(egg);
    hold.egg = egg;
    hold.start = performance.now();

    const grow = () => {
      if (!hold.egg) return;
      hold.egg.style.fontSize = eggSizeFor(performance.now() - hold.start) + "px";
      hold.raf = requestAnimationFrame(grow);
    };
    if (!reduced) hold.raf = requestAnimationFrame(grow);
  }

  function endHold() {
    if (!hold.active) return;
    hold.active = false;
    if (!hold.egg) return;   // released before the shots list arrived
    cancelAnimationFrame(hold.raf);
    const heldMs = performance.now() - hold.start;
    const size = headSizeFor(heldMs);
    const egg = hold.egg;
    const src = hold.src;
    hold.egg = null;
    egg.textContent = "🐣";
    egg.classList.add("hatch");
    setTimeout(() => {
      const r = egg.getBoundingClientRect();
      egg.remove();
      release(src, r.left + r.width / 2 - size / 2, r.top - size / 3, size);
    }, reduced ? 0 : 380);
  }

  btn.addEventListener("pointerdown", e => {
    e.preventDefault();
    startHold();
  });
  window.addEventListener("pointerup", () => { endHold(); releaseCharge(); });
  window.addEventListener("pointercancel", () => { endHold(); releaseCharge(); });
  // Keyboard activation (Enter/Space fires click without pointer events).
  btn.addEventListener("keydown", e => {
    if ((e.key === "Enter" || e.key === " ") && !hold.active) {
      e.preventDefault();
      startHold();
    }
  });
  btn.addEventListener("keyup", e => {
    if (e.key === "Enter" || e.key === " ") endHold();
  });
})();
