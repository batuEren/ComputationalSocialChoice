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


def borda_scores(
    ballots: List[BallotType],
    candidate_ids: List[int],
) -> Dict[int, float]:
    """
    Compute Borda scores for all candidates.

    With n candidates, a strict ranking assigns n-1 points to rank 1,
    n-2 to rank 2, ..., 0 to rank n.

    For weak orders (tied groups), each candidate in the tied group receives
    the average of the Borda points that would have been assigned to the
    positions they collectively occupy (standard average-rank Borda).
    """
    n = len(candidate_ids)
    scores: Dict[int, float] = {c: 0.0 for c in candidate_ids}

    for ballot in ballots:
        # Track which ordinal position we are filling next (0-indexed from the top).
        position = 0
        for group in ballot.groups:
            group_size = len(group)
            if group_size == 0:
                continue
            # Positions occupied by this group: position, position+1, ..., position+group_size-1
            # Borda points for each position: (n-1-position), (n-2-position), ...
            # Average points for candidates in this tied group:
            total_points = sum((n - 1 - (position + k)) for k in range(group_size))
            avg_points = total_points / group_size
            for candidate in group:
                scores[candidate] += ballot.count * avg_points
            position += group_size

    return scores


if __name__ == "__main__":
    cat_path = "00073-00000002.cat"
    names, ballots = load_cat_file(cat_path)

    candidate_ids = sorted(names)
    scores = borda_scores(ballots, candidate_ids)

    # Sort by score descending
    ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    print("Borda ranking:")
    for rank, (candidate_id, score) in enumerate(ranking, start=1):
        print(f"  {rank}. {names[candidate_id]} — score: {score:.2f}")

    winner_id, winner_score = ranking[0]
    print(f"\nWinner: {names[winner_id]} with Borda score {winner_score:.2f}")
