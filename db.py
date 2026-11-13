"""SQLite persistence for Iris Trips."""
import os
import secrets
import sqlite3
from datetime import datetime, timezone

from festivals import FESTIVALS

DB_PATH = os.environ.get("IRIS_DB", os.path.join(os.path.dirname(__file__), "iris.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pin_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS festivals (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    place TEXT NOT NULL,
    flag TEXT NOT NULL DEFAULT '',
    dates TEXT NOT NULL,
    cost_chf INTEGER NOT NULL,
    blurb TEXT NOT NULL DEFAULT '',
    hard_to_get_in INTEGER NOT NULL DEFAULT 0
);
-- One row per (user, festival) the voter has placed. position is the
-- 1-based rank group (dense); the UI only makes strict rankings, but the
-- tabulation engine handles ties if they ever appear.
CREATE TABLE IF NOT EXISTS ballot_items (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    festival_id INTEGER NOT NULL REFERENCES festivals(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, festival_id)
);
-- Admin notes per festival (e.g. registration status).
CREATE TABLE IF NOT EXISTS notes (
    festival_id INTEGER PRIMARY KEY REFERENCES festivals(id) ON DELETE CASCADE,
    body TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    defaults = {
        "voting_open": "0",
        "close_at": "",          # ISO timestamp; empty = no timer
        "shrinkage_w": "3",      # pseudo-ballots at 0.5; 0 disables
        "reveal_open": "0",      # public results; enabling closes voting
        "secret_key": secrets.token_hex(32),
    }
    for k, v in defaults.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    if conn.execute("SELECT COUNT(*) FROM festivals").fetchone()[0] == 0:
        for f in FESTIVALS:
            conn.execute(
                "INSERT INTO festivals (name, place, flag, dates, cost_chf, blurb, "
                "hard_to_get_in) VALUES (?,?,?,?,?,?,?)",
                (f["name"], f["place"], f["flag"], f["dates"], f["cost_chf"],
                 f["blurb"], int(f["hard_to_get_in"])))
    conn.commit()


def get_setting(conn, key: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()


def voting_is_open(conn) -> bool:
    """Open flag, optionally bounded by a close_at timer."""
    if get_setting(conn, "voting_open") != "1":
        return False
    close_at = get_setting(conn, "close_at")
    if close_at:
        try:
            deadline = datetime.fromisoformat(close_at)
        except ValueError:
            return True
        if datetime.now(timezone.utc) >= deadline:
            return False
    return True


def reveal_is_open(conn) -> bool:
    """Public results: everyone (even logged out) may see all results."""
    return get_setting(conn, "reveal_open") == "1"
