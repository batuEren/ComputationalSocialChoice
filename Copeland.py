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


def pairwise_margins(
    ballots: List[BallotType],
    candidate_ids: List[int],
) -> Dict[Tuple[int, int], int]:
    """
    Compute pairwise vote counts for every ordered pair (i, j).

    pairwise[(i, j)] = total weighted votes where i is ranked strictly above j.
    Candidates in the same group on a ballot are considered indifferent (a tie).
    """
    pairwise: Dict[Tuple[int, int], int] = {
        (i, j): 0
        for i in candidate_ids
        for j in candidate_ids
        if i != j
    }

    for ballot in ballots:
        # Build a rank mapping: candidate -> group index (lower = better)
        rank: Dict[int, int] = {}
        for group_idx, group in enumerate(ballot.groups):
            for candidate in group:
                rank[candidate] = group_idx

        for i in candidate_ids:
            for j in candidate_ids:
                if i == j:
                    continue
                if rank[i] < rank[j]:  # i ranked strictly above j
                    pairwise[(i, j)] += ballot.count

    return pairwise


def copeland_scores(
    ballots: List[BallotType],
    candidate_ids: List[int],
) -> Dict[int, float]:
    """
    Compute Copeland scores for all candidates.

    For each pair (i, j):
      - If more voters prefer i over j than j over i: i gets +1, j gets -1.
      - If equally many prefer i over j as j over i: both get 0.

    A candidate's Copeland score is the sum of outcomes across all pairwise contests.
    """
    margins = pairwise_margins(ballots, candidate_ids)
    scores: Dict[int, float] = {c: 0.0 for c in candidate_ids}

    # Iterate over each unordered pair once and assign wins/losses/ties
    for idx, i in enumerate(candidate_ids):
        for j in candidate_ids[idx + 1 :]:
            votes_i_over_j = margins[(i, j)]
            votes_j_over_i = margins[(j, i)]

            if votes_i_over_j > votes_j_over_i:
                scores[i] += 1
                scores[j] -= 1
            elif votes_j_over_i > votes_i_over_j:
                scores[j] += 1
                scores[i] -= 1
            # else: pairwise tie — no points awarded

    return scores


if __name__ == "__main__":
    cat_path = "00073-00000002.cat"
    names, ballots = load_cat_file(cat_path)

    candidate_ids = sorted(names)
    scores = copeland_scores(ballots, candidate_ids)

    # Sort by score descending
    ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    print("Copeland ranking:")
    for rank, (candidate_id, score) in enumerate(ranking, start=1):
        print(f"  {rank}. {names[candidate_id]} — score: {score:+.0f}")

    winner_id, winner_score = ranking[0]
    print(f"\nWinner: {names[winner_id]} with Copeland score {winner_score:+.0f}")
