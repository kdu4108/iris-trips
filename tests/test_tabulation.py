"""Golden acceptance values from PRD 'Voting Method & Tabulation' §4.

Any implementation must reproduce these exactly. The PRD's No-thanks bucket
is expressed here as an ordinary bottom tie group (identical scoring, per
Decision log Q2 / T2).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tabulate import (
    Ballot, average_ranks, ballot_scores, ballot_slots, condorcet_winner, pairwise, shrink,
    singles, spearman, tabulate, taste_matches, tie_threshold, top_k_cutoff,
)


def test_michelle_worked_example():
    # Michelle places 12 songs: ranks 9 strictly, ties 3 at the bottom.
    b = Ballot(voter="michelle", groups=singles(range(1, 10)) + [[10, 11, 12]])
    assert b.n == 12
    s = ballot_scores(b)
    assert math.isclose(s[1], 1 - 0.5 / 12)            # 0.958...
    assert round(s[1], 3) == 0.958
    assert math.isclose(s[9], 1 - 8.5 / 12)            # 0.292
    assert round(s[9], 3) == 0.292
    # Bottom tie occupies slots 10-12, mean 11 -> s = 1 - 10.5/12 = 0.125
    for sid in (10, 11, 12):
        assert math.isclose(s[sid], 0.125)
    # The other 28 songs get nothing from her ballot.
    assert len(s) == 12


def test_mid_list_ties():
    # [1] > [2 = 3] > [4]: the tie occupies slots 2-3 (mean 2.5).
    b = Ballot(voter="x", groups=[[1], [2, 3], [4]])
    s = ballot_scores(b)
    assert math.isclose(s[1], 1 - 0.5 / 4)     # 0.875
    assert math.isclose(s[2], 1 - 2.0 / 4)     # 0.5
    assert math.isclose(s[3], s[2])
    assert math.isclose(s[4], 1 - 3.5 / 4)     # 0.125
    slots = ballot_slots(b)
    assert slots[2] == slots[3] == 2.5


def test_shrinkage_worked_example():
    # Song X: 14 voters, raw 0.71 -> adjusted (14*0.71 + 3*0.5)/17 = 0.673
    assert round(shrink(0.71, 14, w=3), 3) == 0.673
    # Song Y: 3 voters, raw 0.90 -> adjusted (3*0.90 + 3*0.5)/6 = 0.700
    assert round(shrink(0.90, 3, w=3), 3) == 0.700
    # w = 0 disables shrinkage (Decision log Q3).
    assert shrink(0.71, 14, w=0) == 0.71


def test_top5_cutoff():
    assert top_k_cutoff(40) == 5
    assert top_k_cutoff(10) == 5
    assert top_k_cutoff(9) == 5   # ceil(9/2)
    assert top_k_cutoff(7) == 4
    assert top_k_cutoff(2) == 1


def test_enthusiasm_example_t7():
    # Song Z (#1-#3 for 8 voters, ~#25 for 12 others) -> top-5 appearances = 8.
    songs = list(range(1, 41))
    ballots = []
    for i in range(8):
        ranked = [1] + [s for s in songs if s != 1][:29]   # Z at #1
        ballots.append(Ballot(voter=f"fan{i}", groups=singles(ranked[:30])))
    for i in range(12):
        others = [s for s in songs if s != 1]
        ranked = others[:24] + [1] + others[24:29]         # Z at #25
        ballots.append(Ballot(voter=f"meh{i}", groups=singles(ranked)))
    res = tabulate(ballots, songs)
    assert res[1].top5 == 8


def test_bottom5_mirror():
    # 12 placed: 9 strict + 3-way bottom tie (slots 10-12, mean 11 > 12-5).
    b = Ballot(voter="m", groups=singles(range(1, 10)) + [[10, 11, 12]])
    res = tabulate([b], list(range(1, 13)))
    for sid in (10, 11, 12):
        assert res[sid].bottom5 == 1
    assert res[8].bottom5 == 1 and res[9].bottom5 == 1   # slots 8, 9 > 7
    assert res[7].bottom5 == 0                           # slot 7 = n - k
    assert res[1].bottom5 == 0 and res[1].top5 == 1
    # Short ballot mirror: n=6 -> cutoff 3: bottom 3 counted.
    b2 = Ballot(voter="s", groups=singles([1, 2, 3, 4, 5, 6]))
    res2 = tabulate([b2], [1, 2, 3, 4, 5, 6])
    assert res2[6].bottom5 == 1 and res2[4].bottom5 == 1
    assert res2[3].bottom5 == 0 and res2[1].top5 == 1 and res2[4].top5 == 0


def test_edge_cases():
    # n = 0 contributes nothing.
    assert ballot_scores(Ballot(voter="x")) == {}
    # An all-tied ballot: single group of 3, mean slot 2 -> s = 0.5 each.
    s = ballot_scores(Ballot(voter="x", groups=[[1, 2, 3]]))
    assert all(math.isclose(v, 0.5) for v in s.values())
    # One-song ballot: s = 0.5.
    s = ballot_scores(Ballot(voter="x", groups=[[7]]))
    assert math.isclose(s[7], 0.5)
    # Two-song ballot: 0.75 / 0.25 (L5).
    s = ballot_scores(Ballot(voter="x", groups=singles([1, 2])))
    assert math.isclose(s[1], 0.75) and math.isclose(s[2], 0.25)


def test_tie_threshold():
    ballots = [Ballot(voter="a", groups=singles([1, 2, 3, 4])),
               Ballot(voter="b", groups=singles([1, 2]) + [[3, 4, 5, 6]]),
               Ballot(voter="c", groups=[[1]])]
    # median n = 4; c_min = 2 -> delta = 1/8
    assert math.isclose(tie_threshold(ballots, 2), 1 / 8)


def test_average_ranks():
    assert average_ranks([10.0, 30.0, 20.0]) == [1.0, 3.0, 2.0]
    # Ties share the mean of the ranks they occupy.
    assert average_ranks([1.0, 2.5, 2.5, 4.0]) == [1.0, 2.5, 2.5, 4.0]
    assert average_ranks([5.0, 5.0, 5.0]) == [2.0, 2.0, 2.0]
    assert average_ranks([]) == []


def test_spearman():
    a = ballot_slots(Ballot(voter="a", groups=singles([1, 2, 3, 4, 5])))
    same = ballot_slots(Ballot(voter="b", groups=singles([1, 2, 3, 4, 5])))
    rev = ballot_slots(Ballot(voter="c", groups=singles([5, 4, 3, 2, 1])))
    assert math.isclose(spearman(a, same), 1.0)
    assert math.isclose(spearman(a, rev), -1.0)
    # Hand-computed tie case: [1] > [2=3] > [4] vs strict 1,2,3,4.
    # Restricted ranks (1,2,3,4) vs (1,2.5,2.5,4) -> rho = 4.5/sqrt(22.5).
    strict = ballot_slots(Ballot(voter="s", groups=singles([1, 2, 3, 4])))
    tied = ballot_slots(Ballot(voter="t", groups=[[1], [2, 3], [4]]))
    assert math.isclose(spearman(strict, tied), 4.5 / math.sqrt(22.5))
    # Only the common songs matter: extra placements don't change rho.
    longer = ballot_slots(Ballot(voter="l", groups=singles([9, 1, 8, 2, 3, 4, 5, 7])))
    assert math.isclose(spearman(a, longer), 1.0)
    # Undefined: overlap < 2, or a constant restricted vector (all one tie).
    assert spearman(a, ballot_slots(Ballot(voter="x", groups=[[1]]))) is None
    assert spearman(a, ballot_slots(Ballot(voter="x", groups=[[1, 2, 3]]))) is None


def test_taste_matches():
    ballots = [
        Ballot(voter="ann", groups=singles([1, 2, 3, 4, 5])),
        Ballot(voter="ben", groups=singles([1, 2, 3, 5, 4])),
        Ballot(voter="con", groups=singles([5, 4, 3, 2, 1])),
        Ballot(voter="empty"),
    ]
    m = taste_matches(ballots, min_overlap=5)
    # ann <-> ben: d^2 = 2 -> rho = 1 - 12/120 = 0.9. con vs ann: reversed,
    # rho = -1. con vs ben: d^2 = 38 -> rho = 1 - 228/120 = -0.9.
    assert m["ann"]["twin"]["name"] == "ben"
    assert math.isclose(m["ann"]["twin"]["rho"], 0.9)
    assert m["ann"]["nemesis"]["name"] == "con"
    assert math.isclose(m["ann"]["nemesis"]["rho"], -1.0)
    assert m["ben"]["twin"]["name"] == "ann" and m["ben"]["twin"]["overlap"] == 5
    assert m["ben"]["nemesis"]["name"] == "con"
    assert math.isclose(m["ben"]["nemesis"]["rho"], -0.9)
    assert m["con"]["twin"]["name"] == "ben" and m["con"]["nemesis"]["name"] == "ann"
    assert "empty" not in m
    # A single eligible partner: twin and nemesis coincide.
    pair = taste_matches(ballots[:2], min_overlap=5)
    assert pair["ann"]["twin"] == pair["ann"]["nemesis"]
    # min_overlap gates pairs entirely.
    assert taste_matches(ballots, min_overlap=6) == {}
    # An all-tied ballot has no defined rho with anyone -> omitted.
    blob = [Ballot(voter="ann", groups=singles([1, 2, 3, 4, 5])),
            Ballot(voter="tie", groups=[[1, 2, 3, 4, 5]])]
    assert taste_matches(blob, min_overlap=5) == {}


def test_pairwise_and_condorcet():
    ballots = [
        Ballot("a", singles([1, 2, 3])),
        Ballot("b", singles([2, 1, 3])),
        Ballot("c", singles([1, 3])),          # abstains on 2
        Ballot("d", [[3], [1, 2]]),            # 1 and 2 tied: no win either way
    ]
    w = pairwise(ballots, [1, 2, 3])
    assert w[1][2] == 1 and w[2][1] == 1       # a vs b split; d tied; c abstains
    assert w[1][3] == 3 and w[3][1] == 1
    assert w[2][3] == 2 and w[3][2] == 1
    assert condorcet_winner(w) is None         # 1 and 2 tie head-to-head
    ballots.append(Ballot("e", singles([1, 2, 3])))
    assert condorcet_winner(pairwise(ballots, [1, 2, 3])) == 1


def test_zero_scored_cant_go():
    # Ranked festivals keep their spacing as if can't-go filled the bottom
    # slots; every can't-go scores exactly 0, however many there are.
    b = Ballot("v", singles([1, 2, 3]) + [[4, 5]], zero=frozenset({4, 5}))
    s = ballot_scores(b)
    assert [round(s[i], 3) for i in (1, 2, 3)] == [0.9, 0.7, 0.5]
    assert s[4] == 0.0 and s[5] == 0.0
    b = Ballot("w", [[1], [2, 3, 4, 5]], zero=frozenset({2, 3, 4, 5}))
    assert round(ballot_scores(b)[1], 3) == 0.9
    assert all(ballot_scores(b)[i] == 0.0 for i in (2, 3, 4, 5))
    # Only can't-go marks: those festivals still get 0 (not a neutral 0.5).
    b = Ballot("x", [[1, 2]], zero=frozenset({1, 2}))
    res = tabulate([b], [1, 2, 3], w=0)
    assert res[1].raw == 0.0 and res[2].raw == 0.0 and res[3].coverage == 0
    # Still below every ranked option head-to-head, no wins among themselves.
    w = pairwise([Ballot("v", singles([1]) + [[2, 3]], zero=frozenset({2, 3}))], [1, 2, 3])
    assert w[1][2] == 1 and w[2][3] == 0 and w[3][2] == 0
