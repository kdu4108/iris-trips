"""End-to-end smoke test: seeding, accounts, ranking flow, admin views, reveal, exports."""
import os
import sys
import tempfile

os.environ["IRIS_DB"] = os.path.join(tempfile.mkdtemp(), "iris-test.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod          # noqa: E402  (must come after IRIS_DB is set)
import db                     # noqa: E402
from festivals import FESTIVALS  # noqa: E402


def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def login(c, username, pin):
    return c.post("/auth", data={"username": username, "pin": pin}, follow_redirects=True)


def fest_ids():
    conn = db.connect()
    ids = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM festivals")}
    conn.close()
    return ids


def test_full_flow():
    ids = fest_ids()
    assert len(ids) == len(FESTIVALS) == 5
    baden = ids["Chorfestival Baden"]
    ascona = ids["Ascona Choral Academy"]
    preveza = ids["International Choral Festival of Preveza"]
    kerkrade = ids["CantaRode International Choral Festival"]
    capp = ids["International Cappadocia Choir Festival"]

    appmod.create_admin("kevin", "1234")
    admin = client()
    assert b"Results" in login(admin, "kevin", "1234").data

    # Voting closed: ranking is rejected.
    voter = client()
    r = login(voter, "Isabel", "9999")
    assert r.status_code == 200 and b"Chorfestival Baden" in r.data
    assert voter.post("/api/rank", json={"festival_id": baden, "position": 1}).status_code == 403

    # Open with a Zurich-time deadline.
    admin.post("/admin/voting/open", data={"until": "2099-11-25T23:59"})
    page = voter.get("/vote").data
    assert b"Voting closes" in page

    # Isabel ranks all five, then reorders.
    for k, fid in enumerate([ascona, baden, kerkrade, preveza, capp], start=1):
        st = voter.post("/api/rank", json={"festival_id": fid, "position": k}).get_json()
    assert st["groups"] == [[ascona], [baden], [kerkrade], [preveza], [capp]]
    st = voter.post("/api/rank", json={"festival_id": capp, "position": 2}).get_json()
    assert st["groups"] == [[ascona], [capp], [baden], [kerkrade], [preveza]]
    st = voter.post("/api/unrank", json={"festival_id": capp}).get_json()
    assert st["groups"] == [[ascona], [baden], [kerkrade], [preveza]]
    voter.post("/api/rank", json={"festival_id": capp, "position": 99})  # clamps to last

    # A second voter with a partial ballot.
    v2 = client()
    login(v2, "Tom", "5555")
    v2.post("/api/rank", json={"festival_id": baden, "position": 1})
    v2.post("/api/rank", json={"festival_id": ascona, "position": 2})

    # Wrong PIN is refused.
    assert b"Wrong PIN" in login(client(), "tom", "0000").data

    # Admin results: Ascona & Baden lead; voter can't see admin pages.
    assert voter.get("/admin").status_code == 403
    res = admin.get("/admin").data.decode()
    assert "Head-to-head" in res and "2 voter(s)" in res and "1 ranked all" in res
    ctx_rows = appmod.results_context(db.connect())["rows"]
    assert {ctx_rows[0]["f"]["id"], ctx_rows[1]["f"]["id"]} == {ascona, baden}

    # Notes, exports.
    admin.post(f"/admin/festival/{baden}/note", data={"body": "deadline 1 Dec"})
    assert "deadline 1 Dec" in admin.get("/admin").data.decode()
    ballots_csv = admin.get("/admin/export/ballots.csv").data.decode()
    assert "Tom,International Cappadocia Choir Festival,unranked" in ballots_csv
    assert admin.get("/admin/export/results.csv").data.decode().startswith("rank,festival")

    # Reveal: hidden from the public until enabled; enabling closes voting.
    assert client().get("/reveal").status_code == 302
    assert admin.get("/reveal").status_code == 200      # admin preview
    admin.post("/admin/reveal/open")
    pub = client().get("/reveal").data.decode()
    assert "Where is Iris going" in pub and "Isabel" in pub
    assert "deadline 1 Dec" not in pub                   # admin notes stay private
    assert voter.post("/api/rank", json={"festival_id": baden, "position": 1}).status_code == 403

    # Users page + ballot deletion.
    assert "/ 5" in admin.get("/admin/users").data.decode()
    conn = db.connect()
    tom = conn.execute("SELECT id FROM users WHERE username = 'Tom'").fetchone()["id"]
    conn.close()
    admin.post(f"/admin/users/{tom}/delete_ballot")
    assert appmod.results_context(db.connect())["n_voters"] == 1
