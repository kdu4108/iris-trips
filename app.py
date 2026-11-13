"""Iris Trips — ranked voting on the choir's 2027 festival destination.

Adapted from iris-ranking (song voting): same login, ballot model and
positional tabulation, scaled down to a handful of festivals.

Run:    python app.py create-admin <username> <pin>   # seed the first admin
        python app.py                                  # start the server
"""
import csv
import functools
import io
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import (Flask, abort, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash as _gph

import db
import tabulate as tab
from festivals import CODA_URL, IRIS_CONTRIBUTION_CHF

LOCAL_TZ = ZoneInfo("Europe/Zurich")


def hash_pin(pin):
    # pbkdf2 explicitly: macOS system Python 3.9 lacks hashlib.scrypt,
    # werkzeug's default.
    return _gph(pin, method="pbkdf2:sha256")


app = Flask(__name__)
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True)

_boot = db.connect()
db.init_db(_boot)
app.secret_key = db.get_setting(_boot, "secret_key")
_boot.close()


# ---------- request plumbing ----------

def get_conn():
    if "conn" not in g:
        g.conn = db.connect()
    return g.conn


@app.teardown_appcontext
def close_conn(exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


def current_user():
    uid = session.get("uid")
    if uid is None:
        return None
    return get_conn().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("landing"))
        g.user = user
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("landing"))
        if not user["is_admin"]:
            abort(403)
        g.user = user
        return f(*args, **kwargs)
    return wrapper


@app.template_global()
def asset(filename):
    """Static URL with an mtime cache-buster (phones cache CSS/JS for hours)."""
    try:
        v = int(os.stat(os.path.join(app.static_folder, filename)).st_mtime)
    except OSError:
        v = 0
    return url_for("static", filename=filename, v=v)


def local_deadline(close_at):
    """'Tue 25 Nov, 23:59' in Zurich time, or '' when there is no timer."""
    if not close_at:
        return ""
    try:
        dt = datetime.fromisoformat(close_at).astimezone(LOCAL_TZ)
    except ValueError:
        return ""
    return dt.strftime("%a %-d %b, %H:%M")


@app.context_processor
def inject_globals():
    conn = get_conn()
    close_at = db.get_setting(conn, "close_at")
    return {
        "me": current_user(),
        "voting_open": db.voting_is_open(conn),
        "close_at": close_at,
        "deadline": local_deadline(close_at),
        "reveal_open": db.reveal_is_open(conn),
        "coda_url": CODA_URL,
        "iris_chf": IRIS_CONTRIBUTION_CHF,
    }


# ---------- ballots <-> tabulate ----------

def user_groups(conn, user_id):
    """Ordered rank groups for one voter: [[festival_id, ...], ...]."""
    rows = conn.execute(
        "SELECT festival_id, position FROM ballot_items "
        "WHERE user_id = ? ORDER BY position, festival_id", (user_id,)).fetchall()
    groups, last = [], None
    for r in rows:
        if r["position"] != last:
            groups.append([])
            last = r["position"]
        groups[-1].append(r["festival_id"])
    return groups


def load_ballots(conn):
    """All voters' ballots as tabulate.Ballot (voter key = username)."""
    users = conn.execute("SELECT id, username FROM users").fetchall()
    return [tab.Ballot(voter=u["username"], groups=user_groups(conn, u["id"]))
            for u in users]


def all_festivals(conn):
    return conn.execute("SELECT * FROM festivals ORDER BY id").fetchall()


def festival_view(row):
    """Festival fields the UI needs, JSON-safe."""
    return {k: row[k] for k in ("id", "name", "place", "flag", "dates", "cost_chf",
                                "blurb", "hard_to_get_in")}


# ---------- auth (when2meet-style self-service) ----------

@app.route("/")
def landing():
    if current_user():
        return redirect(url_for("vote"))
    return render_template("landing.html", error=request.args.get("error"))


@app.route("/method")
def method():
    return render_template("method.html")


@app.route("/auth", methods=["POST"])
def auth():
    username = (request.form.get("username") or "").strip()
    pin = request.form.get("pin") or ""
    if not username or len(username) > 40:
        return redirect(url_for("landing", error="Please enter a name."))
    if len(pin) < 4:
        return redirect(url_for("landing", error="PIN must be at least 4 characters."))
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user is None:
        conn.execute(
            "INSERT INTO users (username, pin_hash, is_admin, created_at) VALUES (?,?,0,?)",
            (username, hash_pin(pin), db.utcnow()))
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    elif not check_password_hash(user["pin_hash"], pin):
        return redirect(url_for("landing",
                                error="Wrong PIN for that name. (New voter? Pick an unused name.)"))
    session["uid"] = user["id"]
    session.permanent = True
    return redirect(url_for("vote"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("landing"))


# ---------- voter view ----------

def display_order(conn, user_id):
    """Unranked festivals are shown in a per-voter shuffle (stable across
    sessions), so no option benefits from always being listed first."""
    fests = list(all_festivals(conn))
    random.Random(f"iris-trips:{user_id}").shuffle(fests)
    return fests


def ballot_state(conn, user_id):
    return {"groups": user_groups(conn, user_id)}


@app.route("/vote")
@login_required
def vote():
    conn = get_conn()
    fests = [festival_view(f) for f in display_order(conn, g.user["id"])]
    return render_template("vote.html",
                           festivals_json=json.dumps(fests),
                           state_json=json.dumps(ballot_state(conn, g.user["id"])))


def _require_open(conn):
    if not db.voting_is_open(conn):
        abort(403, description="Voting is closed.")


def _renumber(conn, user_id):
    """Keep group ranks dense: 1..G."""
    rows = conn.execute(
        "SELECT festival_id, position FROM ballot_items "
        "WHERE user_id = ? ORDER BY position, festival_id", (user_id,)).fetchall()
    rank, last = 0, None
    for r in rows:
        if r["position"] != last:
            rank += 1
            last = r["position"]
        if r["position"] != rank:
            conn.execute(
                "UPDATE ballot_items SET position = ? WHERE user_id = ? AND festival_id = ?",
                (rank, user_id, r["festival_id"]))


def _remove(conn, user_id, festival_id):
    conn.execute("DELETE FROM ballot_items WHERE user_id = ? AND festival_id = ?",
                 (user_id, festival_id))
    _renumber(conn, user_id)


def _place(conn, user_id, festival_id, position):
    """Insert/move festival_id to 1-based rank `position` (strict)."""
    if conn.execute("SELECT 1 FROM festivals WHERE id = ?", (festival_id,)).fetchone() is None:
        abort(404)
    _remove(conn, user_id, festival_id)
    ngroups = len(user_groups(conn, user_id))
    position = max(1, min(int(position), ngroups + 1))
    conn.execute("UPDATE ballot_items SET position = position + 1 "
                 "WHERE user_id = ? AND position >= ?", (user_id, position))
    conn.execute("INSERT INTO ballot_items (user_id, festival_id, position, updated_at) "
                 "VALUES (?,?,?,?)", (user_id, festival_id, position, db.utcnow()))
    conn.commit()


@app.route("/api/rank", methods=["POST"])
@login_required
def api_rank():
    conn = get_conn()
    _require_open(conn)
    data = request.get_json(force=True)
    _place(conn, g.user["id"], int(data["festival_id"]), int(data["position"]))
    return jsonify(ballot_state(conn, g.user["id"]))


@app.route("/api/unrank", methods=["POST"])
@login_required
def api_unrank():
    conn = get_conn()
    _require_open(conn)
    data = request.get_json(force=True)
    _remove(conn, g.user["id"], int(data["festival_id"]))
    conn.commit()
    return jsonify(ballot_state(conn, g.user["id"]))


@app.route("/api/headshots")
def api_headshots():
    # For the 🐣 easter egg: list of headshot filenames.
    d = os.path.join(app.static_folder, "headshots")
    files = sorted(f for f in os.listdir(d)
                   if f.lower().endswith((".jpeg", ".jpg", ".png"))) if os.path.isdir(d) else []
    return jsonify(files)


# ---------- results (shared by admin view, reveal, exports) ----------

def sparkline_svg(scores, bins=5, width=50, height=16):
    """Histogram of per-ballot scores s in [0,1]; left = low, right = high.
    5 bins: with 5 options and full ballots, each bin is one rank."""
    counts = [0] * bins
    for s in scores.values():
        counts[min(bins - 1, int(s * bins))] += 1
    peak = max(counts) or 1
    bw = width / bins
    bars = []
    for i, c in enumerate(counts):
        h = round(height * c / peak, 1)
        bars.append(f'<rect x="{round(i * bw, 1)}" y="{height - h}" '
                    f'width="{round(bw - 1, 1)}" height="{h}"/>')
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" aria-hidden="true">{"".join(bars)}</svg>')


def results_context(conn):
    fests = all_festivals(conn)
    ids = [f["id"] for f in fests]
    ballots = load_ballots(conn)
    try:
        w = float(db.get_setting(conn, "shrinkage_w"))
    except ValueError:
        w = tab.DEFAULT_W
    results = tab.tabulate(ballots, ids, w=w)
    ordered = sorted(results.values(), key=lambda r: r.adjusted, reverse=True)
    tie_of = {}
    for gi, group in enumerate(tab.tie_groups(ordered, ballots), start=1):
        for fid in group:
            tie_of[fid] = gi

    # With ~5 options, "#1 votes" and "last-place votes" say more than a
    # top-5 count would (everything is in everyone's top 5).
    firsts = {fid: 0 for fid in ids}
    lasts = {fid: 0 for fid in ids}
    for b in ballots:
        if b.n >= 2:
            for fid in b.groups[0]:
                firsts[fid] += 1
            for fid in b.groups[-1]:
                lasts[fid] += 1
        elif b.n == 1:
            firsts[b.groups[0][0]] += 1

    wins = tab.pairwise(ballots, ids)
    fest_by_id = {f["id"]: f for f in fests}
    notes = {r["festival_id"]: r["body"] for r in conn.execute("SELECT * FROM notes")}
    voters = [b for b in ballots if b.n > 0]

    rows = []
    for rank, res in enumerate(ordered, start=1):
        fid = res.song_id    # tabulate's generic "song" id = festival id
        rows.append({
            "rank": rank, "f": fest_by_id[fid], "res": res,
            "firsts": firsts[fid], "lasts": lasts[fid],
            "tie_group": tie_of.get(fid),
            "spark": sparkline_svg(res.scores),
            "note": notes.get(fid, ""),
        })
    order = [r["f"]["id"] for r in rows]
    matrix = [{"f": fest_by_id[a],
               "cells": [None if a == b else {"w": wins[a][b], "l": wins[b][a]}
                         for b in order]}
              for a in order]
    cw = tab.condorcet_winner(wins) if voters else None
    return {"rows": rows, "w": w, "n_voters": len(voters),
            "n_complete": sum(1 for b in voters if b.n >= len(ids)),
            "n_options": len(ids), "matrix": matrix, "order": order,
            "condorcet": fest_by_id[cw] if cw else None, "ballots": voters,
            "fest_by_id": fest_by_id}


@app.route("/admin")
@admin_required
def admin_results():
    return render_template("admin_results.html", **results_context(get_conn()))


@app.route("/admin/setw", methods=["POST"])
@admin_required
def admin_setw():
    try:
        w = float(request.form.get("w", "3"))
        if w < 0:
            raise ValueError
    except ValueError:
        abort(400)
    db.set_setting(get_conn(), "shrinkage_w", str(w))
    return redirect(url_for("admin_results"))


@app.route("/admin/festival/<int:fid>/note", methods=["POST"])
@admin_required
def admin_festival_note(fid):
    conn = get_conn()
    if conn.execute("SELECT 1 FROM festivals WHERE id = ?", (fid,)).fetchone() is None:
        abort(404)
    conn.execute("INSERT INTO notes (festival_id, body, updated_at) VALUES (?,?,?) "
                 "ON CONFLICT(festival_id) DO UPDATE SET body = excluded.body, "
                 "updated_at = excluded.updated_at",
                 (fid, request.form.get("body", "").strip(), db.utcnow()))
    conn.commit()
    return redirect(url_for("admin_results"))


# ---------- admin: users ----------

@app.route("/admin/users")
@admin_required
def admin_users():
    conn = get_conn()
    users = conn.execute(
        """SELECT u.*, COUNT(b.festival_id) AS ranked_ct
           FROM users u LEFT JOIN ballot_items b ON b.user_id = u.id
           GROUP BY u.id ORDER BY u.username COLLATE NOCASE""").fetchall()
    return render_template("admin_users.html", users=users,
                           n_options=len(all_festivals(conn)))


@app.route("/admin/users/<int:uid>/reset_pin", methods=["POST"])
@admin_required
def admin_reset_pin(uid):
    pin = request.form.get("pin") or ""
    if len(pin) < 4:
        abort(400, description="PIN must be at least 4 characters.")
    conn = get_conn()
    conn.execute("UPDATE users SET pin_hash = ? WHERE id = ?", (hash_pin(pin), uid))
    conn.commit()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:uid>/promote", methods=["POST"])
@admin_required
def admin_promote(uid):
    conn = get_conn()
    conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (uid,))
    conn.commit()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:uid>/delete_ballot", methods=["POST"])
@admin_required
def admin_delete_ballot(uid):
    conn = get_conn()
    conn.execute("DELETE FROM ballot_items WHERE user_id = ?", (uid,))
    conn.commit()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:uid>/delete_account", methods=["POST"])
@admin_required
def admin_delete_account(uid):
    if uid == g.user["id"]:
        abort(400, description="You cannot delete your own account.")
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit()
    return redirect(url_for("admin_users"))


# ---------- admin: voting control ----------

@app.route("/admin/voting", methods=["GET"])
@admin_required
def admin_voting():
    conn = get_conn()
    return render_template("admin_voting.html",
                           open_flag=db.get_setting(conn, "voting_open") == "1",
                           reveal_flag=db.reveal_is_open(conn))


@app.route("/admin/voting/open", methods=["POST"])
@admin_required
def admin_voting_open():
    """Open voting with an optional deadline: either a local date-time
    (Zurich) or a number of hours from now. Re-opening replaces the timer."""
    conn = get_conn()
    until = (request.form.get("until") or "").strip()
    hours = (request.form.get("hours") or "").strip()
    close = None
    try:
        if until:
            close = datetime.fromisoformat(until).replace(tzinfo=LOCAL_TZ)
        elif hours:
            close = datetime.now(timezone.utc) + timedelta(hours=float(hours))
    except ValueError:
        abort(400)
    db.set_setting(conn, "close_at",
                   close.astimezone(timezone.utc).isoformat() if close else "")
    db.set_setting(conn, "voting_open", "1")
    return redirect(url_for("admin_voting"))


@app.route("/admin/voting/close", methods=["POST"])
@admin_required
def admin_voting_close():
    conn = get_conn()
    db.set_setting(conn, "voting_open", "0")
    db.set_setting(conn, "close_at", "")
    return redirect(url_for("admin_voting"))


@app.route("/admin/reveal/open", methods=["POST"])
@admin_required
def admin_reveal_open():
    # Publishing results freezes them: close voting and clear any timer.
    conn = get_conn()
    db.set_setting(conn, "voting_open", "0")
    db.set_setting(conn, "close_at", "")
    db.set_setting(conn, "reveal_open", "1")
    return redirect(url_for("admin_voting"))


@app.route("/admin/reveal/close", methods=["POST"])
@admin_required
def admin_reveal_close():
    db.set_setting(get_conn(), "reveal_open", "0")
    return redirect(url_for("admin_voting"))


# ---------- reveal: public results ----------

@app.route("/reveal")
def reveal():
    """Public once enabled; admins may always preview. Admin notes stay out."""
    conn = get_conn()
    user = current_user()
    if not db.reveal_is_open(conn) and not (user and user["is_admin"]):
        return redirect(url_for("landing"))
    ctx = results_context(conn)
    fest_by_id = ctx["fest_by_id"]
    ballots_view = []
    for b in sorted(ctx["ballots"], key=lambda b: b.voter.lower()):
        ballots_view.append({"voter": b.voter,
                             "entries": [fest_by_id[fid] for grp in b.groups for fid in grp]})
    countdown = [{
        "rank": r["rank"], "name": r["f"]["name"], "place": r["f"]["place"],
        "flag": r["f"]["flag"], "dates": r["f"]["dates"],
        "adjusted": round(r["res"].adjusted, 3), "firsts": r["firsts"],
        "tied_with_prev": r["tie_group"] is not None and any(
            o["rank"] == r["rank"] + 1 and o["tie_group"] == r["tie_group"]
            for o in ctx["rows"]),
    } for r in reversed(ctx["rows"])]
    return render_template(
        "reveal.html", **ctx, ballots_view=ballots_view,
        twins=tab.taste_matches(ctx["ballots"], min_overlap=3),
        countdown_json=json.dumps(countdown).replace("</", "<\\/"))


# ---------- admin: CSV export ----------

def _csv_response(filename, header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return app.response_class(
        buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/admin/export/ballots.csv")
@admin_required
def export_ballots():
    conn = get_conn()
    names = {f["id"]: f["name"] for f in all_festivals(conn)}
    rows = []
    for b in load_ballots(conn):
        slots = tab.ballot_slots(b)
        for fid, name in names.items():
            rows.append([b.voter, name, f"{slots[fid]:g}" if fid in slots else "unranked"])
    return _csv_response("ballots.csv", ["voter", "festival", "position"], rows)


@app.route("/admin/export/results.csv")
@admin_required
def export_results():
    ctx = results_context(get_conn())
    rows = [[r["rank"], r["f"]["name"], r["f"]["place"],
             "" if r["res"].raw is None else round(r["res"].raw, 4),
             round(r["res"].adjusted, 4), r["res"].coverage, r["firsts"], r["lasts"]]
            for r in ctx["rows"]]
    return _csv_response(
        "results.csv",
        ["rank", "festival", "place", "raw_score", "adjusted_score", "coverage",
         "first_place_votes", "last_place_votes"], rows)


# ---------- CLI ----------

def create_admin(username, pin):
    conn = db.connect()
    db.init_db(conn)
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.execute("UPDATE users SET pin_hash = ?, is_admin = 1 WHERE id = ?",
                     (hash_pin(pin), existing["id"]))
    else:
        conn.execute(
            "INSERT INTO users (username, pin_hash, is_admin, created_at) VALUES (?,?,1,?)",
            (username, hash_pin(pin), db.utcnow()))
    conn.commit()
    print(f"Admin account ready: {username}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "create-admin":
        if len(sys.argv) != 4:
            sys.exit("Usage: python app.py create-admin <username> <pin>")
        create_admin(sys.argv[2], sys.argv[3])
    else:
        app.run(host="0.0.0.0", port=int(sys.argv[1]) if len(sys.argv) > 1 else 5000,
                debug=False)
