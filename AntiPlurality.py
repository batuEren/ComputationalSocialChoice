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


def anti_plurality_scores(
    ballots: List[BallotType],
    candidate_ids: List[int],
) -> Dict[int, float]:
    """
    Compute Anti-Plurality (veto) scores for all candidates.

    Each ballot casts one veto against the last-ranked candidate(s).
    A candidate's score is the total ballot weight they did NOT receive a veto from,
    i.e., score = total_votes - vetoes_received.

    For weak orders, if multiple candidates share the last position, the veto
    weight is split equally among them (fractional bottom-split).
    """
    total_votes = sum(ballot.count for ballot in ballots)
    vetoes: Dict[int, float] = {c: 0.0 for c in candidate_ids}

    for ballot in ballots:
        # Find the last non-empty group — these are the bottom-ranked candidates
        for group in reversed(ballot.groups):
            if len(group) == 0:
                continue
            share = ballot.count / len(group)
            for candidate in group:
                vetoes[candidate] += share
            break  # only the bottom group receives the veto

    # Score = total votes minus vetoes received
    scores: Dict[int, float] = {c: total_votes - vetoes[c] for c in candidate_ids}
    return scores


if __name__ == "__main__":
    cat_path = "00073-00000002.cat"
    names, ballots = load_cat_file(cat_path)

    candidate_ids = sorted(names)
    scores = anti_plurality_scores(ballots, candidate_ids)

    # Sort by score descending
    ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    print("Anti-Plurality ranking:")
    for rank, (candidate_id, score) in enumerate(ranking, start=1):
        print(f"  {rank}. {names[candidate_id]} — score: {score:.2f}")

    winner_id, winner_score = ranking[0]
    print(f"\nWinner: {names[winner_id]} with anti-plurality score {winner_score:.2f}")
