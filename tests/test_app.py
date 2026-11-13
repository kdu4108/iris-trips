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


def test_cant_go():
    ids = sorted(fest_ids().values())
    a, b, c, d, e = ids
    admin = client()
    appmod.create_admin("kevin", "1234")
    login(admin, "kevin", "1234")
    admin.post("/admin/voting/open", data={"until": "2099-11-25T23:59"})

    v = client()
    login(v, "Lena", "4321")
    v.post("/api/rank", json={"festival_id": a, "position": 1})
    v.post("/api/rank", json={"festival_id": b, "position": 2})
    # Marking a ranked festival as can't-go takes it out of the ranking.
    st = v.post("/api/cant_go", json={"festival_id": b, "cant_go": True}).get_json()
    assert st == {"groups": [[a]], "cant_go": [b]}
    st = v.post("/api/cant_go", json={"festival_id": c, "cant_go": True}).get_json()
    assert st["cant_go"] == [b, c]
    # Ranking a can't-go festival clears the mark.
    st = v.post("/api/rank", json={"festival_id": c, "position": 2}).get_json()
    assert st == {"groups": [[a], [c]], "cant_go": [b]}
    # Undo returns it to the pool (neither ranked nor can't-go).
    st = v.post("/api/cant_go", json={"festival_id": b, "cant_go": False}).get_json()
    assert st == {"groups": [[a], [c]], "cant_go": []}
    v.post("/api/cant_go", json={"festival_id": d, "cant_go": True})
    v.post("/api/cant_go", json={"festival_id": e, "cant_go": True})

    # Tabulated ballot: ranking, then can't-go as one bottom tie group.
    conn = db.connect()
    uid = conn.execute("SELECT id FROM users WHERE username = 'Lena'").fetchone()["id"]
    assert appmod.full_groups(conn, uid) == [[a], [c], [d, e]]
    lena = next(bb for bb in appmod.load_ballots(conn) if bb.voter == "Lena")
    from tabulate import ballot_scores
    sc = ballot_scores(lena)
    # n = 4 (2 ranked + 2 can't go; one festival untouched)
    assert round(sc[a], 3) == 0.875 and round(sc[c], 3) == 0.625
    assert sc[d] == 0.0 and sc[e] == 0.0
    ctx = appmod.results_context(conn)
    row = {r["f"]["id"]: r for r in ctx["rows"]}
    assert row[d]["cant_go"] >= 1 and row[e]["cant_go"] >= 1
    assert "Lena,{},cant_go".format(row[d]["f"]["name"]) in \
        admin.get("/admin/export/ballots.csv").data.decode()
    # A voter with only can't-go marks contributes no #1 vote.
    v2 = client()
    login(v2, "Max", "4321")
    before = sum(r["firsts"] for r in ctx["rows"])
    v2.post("/api/cant_go", json={"festival_id": a, "cant_go": True})
    after = sum(r["firsts"] for r in appmod.results_context(conn)["rows"])
    assert after == before
    conn.close()
    assert "Can&#39;t go" in admin.get("/admin").data.decode() or "Can't go" in admin.get("/admin").data.decode()


def test_headshots_include_avif_and_dedupe():
    files = client().get("/api/headshots").get_json()
    stems = [os.path.splitext(f)[0].lower() for f in files]
    assert len(stems) == len(set(stems))          # one photo per person
    for name in ("hannah", "justina"):
        assert name in stems
