"""Tabulation for the ranked-with-ties ballot model.

Shared with iris-ranking (song voting) — same positional scoring, shrinkage
and tie detection — with "song" read as "option" (here: festival). The
blind-spot analysis is dropped (no categories), and pairwise() is added: with
only a handful of options, head-to-head counts are cheap and informative.

A ballot is an ordered list of rank groups (first group = favorite). Most
groups hold a single option; a group with several options means they are tied
and share their averaged slot position (standard tied-ranks treatment).
Options a voter never placed are abstentions: excluded entirely (no score,
no denominator, no coverage).
"""
import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# T5 default shrinkage: w pseudo-ballots at the neutral prior 0.5.
DEFAULT_W = 3.0
NEUTRAL_PRIOR = 0.5


@dataclass
class Ballot:
    """One voter's ballot: ordered rank groups. groups=[[5],[2,7],[9]] means
    song 5 first, songs 2 and 7 tied for second/third, song 9 last.

    zero: options that score exactly 0 regardless of position (Iris Trips'
    "can't go"). They should also be placed as the last group, so they still
    count toward n, sit below everything ranked in slots/pairwise, and keep
    the ranked options' spacing the same as if they were ranked last."""
    voter: str
    groups: List[List[int]] = field(default_factory=list)
    zero: frozenset = field(default_factory=frozenset)

    @property
    def n(self) -> int:
        return sum(len(g) for g in self.groups)


def singles(song_ids: List[int]) -> List[List[int]]:
    """Convenience: a strict (tie-free) ballot's groups."""
    return [[sid] for sid in song_ids]


def ballot_slots(ballot: Ballot) -> Dict[int, float]:
    """Mean slot position for every placed song (1-indexed; ties share the
    mean of the slots their group occupies)."""
    slots: Dict[int, float] = {}
    slot = 1
    for group in ballot.groups:
        k = len(group)
        mean = slot + (k - 1) / 2.0
        for sid in group:
            slots[sid] = mean
        slot += k
    return slots


def positional_score(p: float, n: int) -> float:
    """T1: s = 1 - (p - 0.5) / n for (possibly fractional) slot position p."""
    return 1.0 - (p - 0.5) / n


def ballot_scores(ballot: Ballot) -> Dict[int, float]:
    """Per-ballot scores for every placed song (T1 + tied-ranks averaging)."""
    n = ballot.n
    if n == 0:
        return {}
    return {sid: 0.0 if sid in ballot.zero else positional_score(p, n)
            for sid, p in ballot_slots(ballot).items()}


def top_k_cutoff(n: int) -> int:
    """T7: personal top 5, but top ceil(n/2) for ballots with n < 10.
    The same cutoff is mirrored for the bottom-5 metric."""
    return 5 if n >= 10 else math.ceil(n / 2)


def shrink(raw: float, coverage: int, w: float) -> float:
    """T5: adjusted = (c*raw + w*0.5) / (c + w). w = 0 disables shrinkage."""
    if coverage == 0:
        return NEUTRAL_PRIOR
    return (coverage * raw + w * NEUTRAL_PRIOR) / (coverage + w)


@dataclass
class SongResult:
    song_id: int
    raw: Optional[float]        # mean positional score; None if coverage == 0
    adjusted: float             # T5 shrinkage-adjusted score
    coverage: int               # number of ballots that placed the song
    top5: int                   # T7 appearances in voters' personal top
    bottom5: int                # mirror metric: appearances in personal bottom
    scores: Dict[str, float] = field(default_factory=dict)  # voter -> s


def tabulate(ballots: List[Ballot], song_ids: List[int], w: float = DEFAULT_W) -> Dict[int, SongResult]:
    """Compute aggregates (T1-T5, T7 + bottom-5 mirror) for every song."""
    per_song_scores: Dict[int, Dict[str, float]] = {sid: {} for sid in song_ids}
    top5_counts: Dict[int, int] = {sid: 0 for sid in song_ids}
    bottom5_counts: Dict[int, int] = {sid: 0 for sid in song_ids}

    for b in ballots:
        n = b.n
        if n == 0:
            continue
        slots = ballot_slots(b)
        k = top_k_cutoff(n)
        for sid, p in slots.items():
            if sid not in per_song_scores:
                continue
            per_song_scores[sid][b.voter] = 0.0 if sid in b.zero else positional_score(p, n)
            if p <= k:
                top5_counts[sid] += 1
            if p > n - k:
                bottom5_counts[sid] += 1

    results: Dict[int, SongResult] = {}
    for sid in song_ids:
        scores = per_song_scores[sid]
        c = len(scores)
        raw = (sum(scores.values()) / c) if c else None
        adjusted = shrink(raw, c, w) if c else NEUTRAL_PRIOR
        results[sid] = SongResult(
            song_id=sid, raw=raw, adjusted=adjusted, coverage=c,
            top5=top5_counts[sid], bottom5=bottom5_counts[sid], scores=scores,
        )
    return results


def tie_threshold(ballots: List[Ballot], c_min: int) -> float:
    """T6: delta = 1 / (median n_v * c_min); infinite-ish when no data."""
    ns = [b.n for b in ballots if b.n > 0]
    if not ns or c_min == 0:
        return float("inf")
    n_med = statistics.median(ns)
    return 1.0 / (n_med * c_min)


def tie_groups(ordered: List[SongResult], ballots: List[Ballot]) -> List[List[int]]:
    """T6: chain adjacent songs (in adjusted-score order) whose gap is below
    delta. Returns groups of song_ids with len >= 2 (statistically tied)."""
    groups: List[List[int]] = []
    current: List[SongResult] = []
    for prev, cur in zip(ordered, ordered[1:]):
        c_min = min(prev.coverage, cur.coverage)
        delta = tie_threshold(ballots, c_min)
        if abs(prev.adjusted - cur.adjusted) < delta and c_min > 0:
            if not current:
                current = [prev]
            current.append(cur)
        else:
            if len(current) >= 2:
                groups.append([r.song_id for r in current])
            current = []
    if len(current) >= 2:
        groups.append([r.song_id for r in current])
    return groups


def average_ranks(values: List[float]) -> List[float]:
    """Tied-ranks (average) 1-based ranking of values; smallest value = rank 1."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        mean = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = mean
        i = j + 1
    return ranks


def spearman(slots_a: Dict[int, float], slots_b: Dict[int, float]) -> Optional[float]:
    """Spearman rho between two voters over their commonly placed songs.

    Each voter's slot vector is restricted to the common songs and re-ranked
    with average ranks (tie-aware) — raw slots would bias voters with
    different ballot sizes. None if fewer than 2 common songs or either
    restricted vector is constant (e.g. all common songs in one tie group).
    """
    common = sorted(slots_a.keys() & slots_b.keys())
    if len(common) < 2:
        return None
    ra = average_ranks([slots_a[s] for s in common])
    rb = average_ranks([slots_b[s] for s in common])
    mean_a = sum(ra) / len(ra)
    mean_b = sum(rb) / len(rb)
    da = [x - mean_a for x in ra]
    db = [x - mean_b for x in rb]
    denom = math.sqrt(sum(x * x for x in da) * sum(x * x for x in db))
    if denom == 0:
        return None
    return sum(x * y for x, y in zip(da, db)) / denom


def taste_matches(ballots: List[Ballot], min_overlap: int = 5) -> Dict[str, dict]:
    """For each voter who placed songs, the other voters with the highest
    (taste twin) and lowest (taste nemesis) spearman() over their commonly
    placed songs. Pairs with fewer than min_overlap common songs or undefined
    rho are skipped; voters with no eligible pair are omitted.

    Returns {voter: {"twin": m, "nemesis": m}} with m = {"name", "rho",
    "overlap"}. With a single eligible partner, twin and nemesis coincide.
    """
    active = [(b.voter, ballot_slots(b)) for b in ballots if b.n > 0]
    out: Dict[str, dict] = {}
    for i, (voter, slots) in enumerate(active):
        best = worst = None
        for j, (other, other_slots) in enumerate(active):
            if i == j:
                continue
            overlap = len(slots.keys() & other_slots.keys())
            if overlap < min_overlap:
                continue
            rho = spearman(slots, other_slots)
            if rho is None:
                continue
            m = {"name": other, "rho": rho, "overlap": overlap}
            if best is None or rho > best["rho"]:
                best = m
            if worst is None or rho < worst["rho"]:
                worst = m
        if best:
            out[voter] = {"twin": best, "nemesis": worst}
    return out


def pairwise(ballots: List[Ballot], ids: List[int]) -> Dict[int, Dict[int, int]]:
    """Head-to-head counts: wins[a][b] = number of ballots ranking a strictly
    above b. Only ballots that placed both count; an unplaced option is an
    abstention, not a loss (consistent with positional scoring)."""
    wins: Dict[int, Dict[int, int]] = {a: {b: 0 for b in ids if b != a} for a in ids}
    for ballot in ballots:
        slots = ballot_slots(ballot)
        for a in ids:
            for b in ids:
                if a != b and a in slots and b in slots and slots[a] < slots[b]:
                    wins[a][b] += 1
    return wins


def condorcet_winner(wins: Dict[int, Dict[int, int]]) -> Optional[int]:
    """The option that beats every other head-to-head, if one exists."""
    for a, row in wins.items():
        if row and all(row[b] > wins[b][a] for b in row):
            return a
    return None
