# Iris Trips

Ranked voting on the choir's 2027 festival destination, adapted from
[iris-ranking](../iris-ranking). The login (name + PIN), ballot model and
tabulation are the same. Voters rank the 5 shortlisted festivals (1 = plan A), and
the admin results order them by positional (Borda-style) score with shrinkage and
statistical-tie flags. With only 5 options the results add **#1 votes**,
**last-place votes**, and a **head-to-head matrix** (with Condorcet winner) that
answers "if plan A falls through, which one next?".

What was dropped from iris-ranking: genres/vibes, blind spots, the UDM
workspace, proposal lists, score uploads, the "heard it" flag, the bisection
placer, and ties in the voter UI (the engine still handles them).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python app.py create-admin kevin <pin>   # seeds the 5 festivals on first boot
.venv/bin/python app.py                            # port 5000; or: python app.py 8080
```

As admin: **Voting & reveal** → set the deadline (pre-filled with 25 Nov 23:59, Zurich
time) → *Open voting*. Share the URL. When it closes, *Start the reveal* publishes a
#5 → #1 countdown, the head-to-head table and all ballots.

The festival list lives in `festivals.py` and is seeded into an **empty** database
only. To change it after first boot, delete `iris.db`. This also wipes all ballots.

## Layout

| File | What it is |
|---|---|
| `festivals.py` | The shortlist, Coda link, Iris's per-person contribution |
| `tabulate.py` | iris-ranking's engine minus blind spots, plus `pairwise` / `condorcet_winner` |
| `app.py` | Flask app: auth, ballot API, admin results/users/voting, reveal, CSV exports |
| `db.py` | SQLite schema + settings |
| `templates/`, `static/` | Voter UI (`vote.js`), `trips.css` on top of iris-ranking's `style.css` |
| `tests/` | iris-ranking's golden tabulation values + pairwise test + end-to-end smoke test |
