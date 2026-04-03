from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import List, Dict, Tuple


@dataclass
class BallotType:
    count: int
    groups: List[List[int]]  # weak-order groups from best to worst


def parse_groups(text: str) -> List[List[int]]:
    groups: List[List[int]] = []
    i = 0
    while i < len(text):
        while i < len(text) and text[i] in " ,":
            i += 1
        if i >= len(text):
            break

        if text[i] == "{":
            j = text.find("}", i)
            inside = text[i + 1 : j].strip()
            group = (
                [] if inside == "" else [int(x) for x in inside.split(",") if x.strip()]
            )
            groups.append(group)
            i = j + 1
        else:
            j = i
            while j < len(text) and text[j] not in ", ":
                j += 1
            groups.append([int(text[i:j])])
            i = j
    return groups


def load_cat_file(path: str | Path) -> Tuple[Dict[int, str], List[BallotType]]:
    path = Path(path)
    candidate_names: Dict[int, str] = {}
    raw_ballots: List[BallotType] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("# ALTERNATIVE NAME"):
            m = re.match(r"# ALTERNATIVE NAME (\d+): (.*)", line)
            if m is None:
                raise ValueError(f"Could not parse alternative name line: {line}")
            candidate_names[int(m.group(1))] = m.group(2).strip()
            continue
        if line.startswith("#"):
            continue

        count_text, ranking_text = line.split(":", 1)
        raw_ballots.append(
            BallotType(count=int(count_text), groups=parse_groups(ranking_text))
        )

    all_candidates = sorted(candidate_names)

    # Any candidate omitted from a ballot is treated as tied in the last position.
    ballots: List[BallotType] = []
    for ballot in raw_ballots:
        seen = set(c for group in ballot.groups for c in group)
        missing = [c for c in all_candidates if c not in seen]
        groups = [list(group) for group in ballot.groups]
        if missing:
            groups.append(missing)
        ballots.append(BallotType(count=ballot.count, groups=groups))

    return candidate_names, ballots


def plurality_scores(
    ballots: List[BallotType],
    candidate_ids: List[int],
) -> Dict[int, float]:
    """
    Compute Plurality scores for all candidates (first-place votes only).

    Each ballot contributes its full weight to the top-ranked candidate.
    For weak orders, if multiple candidates share the top position, the
    ballot weight is split equally among them (fractional top-split).
    """
    scores: Dict[int, float] = {c: 0.0 for c in candidate_ids}

    for ballot in ballots:
        for group in ballot.groups:
            if len(group) == 0:
                continue
            share = ballot.count / len(group)
            for candidate in group:
                scores[candidate] += share
            break  # only the top group counts

    return scores


def rank_level_scores(
    ballots: List[BallotType],
    candidate_ids: List[int],
) -> Dict[int, List[float]]:
    """
    Compute per-rank scores for each candidate across all rank levels.

    scores[candidate][k] is the total ballot weight for which the candidate
    appears in rank group k (0-indexed). Used for lexicographic tiebreaking.
    For weak orders, ballot weight is split equally among tied candidates
    within the same group.
    """
    max_groups = max((len(b.groups) for b in ballots), default=0)
    scores: Dict[int, List[float]] = {c: [0.0] * max_groups for c in candidate_ids}

    for ballot in ballots:
        for rank, group in enumerate(ballot.groups):
            if not group:
                continue
            share = ballot.count / len(group)
            for candidate in group:
                scores[candidate][rank] += share

    return scores


if __name__ == "__main__":
    cat_path = "00073-00000002.cat"
    names, ballots = load_cat_file(cat_path)

    candidate_ids = sorted(names)
    first_place = plurality_scores(ballots, candidate_ids)
    by_rank = rank_level_scores(ballots, candidate_ids)

    # Sort lexicographically: rank-0 score descending, then rank-1, rank-2, …
    ranking = sorted(
        candidate_ids,
        key=lambda c: by_rank[c],
        reverse=True,
    )

    print("Plurality ranking (with lexicographic tiebreaking):")
    for pos, candidate_id in enumerate(ranking, start=1):
        print(f"  {pos}. {names[candidate_id]} — score: {first_place[candidate_id]:.2f}")

    winner_id = ranking[0]
    print(f"\nWinner: {names[winner_id]} with plurality score {first_place[winner_id]:.2f}")
