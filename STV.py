from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import List, Dict, Tuple


@dataclass
class BallotType:
    count: int
    groups: List[List[int]]  # weak-order groups from best to worst


@dataclass
class RoundResult:
    scores: Dict[int, float]
    eliminated: int
    tied_for_last: List[int]


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

    # Assumption:
    # any candidate omitted from a ballot is treated as tied in the last position.
    ballots: List[BallotType] = []
    for ballot in raw_ballots:
        seen = set(c for group in ballot.groups for c in group)
        missing = [c for c in all_candidates if c not in seen]
        groups = [list(group) for group in ballot.groups]
        if missing:
            groups.append(missing)
        ballots.append(BallotType(count=ballot.count, groups=groups))

    return candidate_names, ballots


def resolve_elimination_tie(
    tied_candidates: List[int],
    previous_rounds: List[RoundResult],
    fallback: str = "lowest_id",
) -> int:
    """
    Break a tie for elimination by looking at earlier-round STV scores.

    We compare the tied candidates in the most recent previous round first.
    The candidate with the lower earlier score is eliminated.
    If still tied, keep moving backward through older rounds.
    If still tied everywhere, use candidate ID as a deterministic fallback.
    """
    remaining = list(tied_candidates)

    for rnd in reversed(previous_rounds):
        min_prev_score = min(rnd.scores[c] for c in remaining)
        remaining = [
            c for c in remaining if abs(rnd.scores[c] - min_prev_score) < 1e-12
        ]
        if len(remaining) == 1:
            return remaining[0]

    if fallback == "lowest_id":
        return min(remaining)
    if fallback == "highest_id":
        return max(remaining)

    raise ValueError("fallback must be 'lowest_id' or 'highest_id'")


def stv_fractional(
    ballots: List[BallotType],
    candidate_ids: List[int],
    tie_break: str = "history_lowest_id",
) -> Tuple[List[RoundResult], List[int]]:
    """
    STV for weak orders using fractional top-split.

    Ballot ties:
    In each round, each ballot is assigned to the highest-ranked active group.
    If several active candidates are tied in that top group, the ballot is split equally.

    Elimination ties:
    If multiple candidates tie for the lowest round score, break the tie by:
    1. comparing their scores in earlier rounds (most recent first),
    2. then using candidate ID as final fallback.
    """
    active = set(candidate_ids)
    rounds: List[RoundResult] = []

    while len(active) > 1:
        scores = {c: 0.0 for c in active}

        # Compute normal STV round scores
        for ballot in ballots:
            for group in ballot.groups:
                top_active = [c for c in group if c in active]
                if top_active:
                    share = ballot.count / len(top_active)
                    for c in top_active:
                        scores[c] += share
                    break

        min_score = min(scores.values())
        tied_for_last = [c for c, s in scores.items() if abs(s - min_score) < 1e-12]

        if len(tied_for_last) == 1:
            eliminated = tied_for_last[0]
        elif tie_break == "lowest_id":
            eliminated = min(tied_for_last)
        elif tie_break == "highest_id":
            eliminated = max(tied_for_last)
        elif tie_break == "history_lowest_id":
            eliminated = resolve_elimination_tie(
                tied_for_last, rounds, fallback="lowest_id"
            )
        elif tie_break == "history_highest_id":
            eliminated = resolve_elimination_tie(
                tied_for_last, rounds, fallback="highest_id"
            )
        else:
            raise ValueError(
                "tie_break must be one of "
                "'lowest_id', 'highest_id', "
                "'history_lowest_id', 'history_highest_id'"
            )

        rounds.append(
            RoundResult(
                scores=scores,
                eliminated=eliminated,
                tied_for_last=tied_for_last,
            )
        )
        active.remove(eliminated)

    return rounds, sorted(active)


if __name__ == "__main__":
    cat_path = "00073-00000002.cat"
    names, ballots = load_cat_file(cat_path)

    rounds, winners = stv_fractional(
        ballots,
        sorted(names),
        tie_break="history_lowest_id",
    )

    print("Winner(s):")
    for w in winners:
        print(f"{w}: {names[w]}")

    print("\nElimination order:")
    for i, rnd in enumerate(rounds, start=1):
        print(
            f"Round {i}: eliminate {rnd.eliminated} ({names[rnd.eliminated]}) "
            f"with STV score: {rnd.scores[rnd.eliminated]:.6f}"
        )
