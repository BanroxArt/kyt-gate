"""Replay transfers under one or two policies and summarize the difference.

With labelled synthetic data (``label`` = ``bad`` or ``good``) it also counts
how many bad transfers each policy stopped and how many good ones it held up,
which is the number a policy change should be argued with. On real data,
labels come from your own case outcomes; nothing here invents them.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .gate import Decision, evaluate
from .model import Transfer, TransferError, transfer_from
from .policy import ACTIONS, RANK, Policy

STOPPING = frozenset({"hold", "reject", "block"})


@dataclass
class Summary:
    policy: str
    count: Counter[str]
    cents: Counter[str]
    rules: Counter[str]
    bad_total: int = 0
    bad_stopped: int = 0
    bad_reviewed: int = 0
    good_total: int = 0
    good_stopped: int = 0
    good_reviewed: int = 0


def load_transfers(path: str | Path) -> list[Transfer]:
    out = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(transfer_from(json.loads(line)))
        except (json.JSONDecodeError, TransferError) as e:
            raise TransferError(f"{path}:{n}: {e}") from None
    return out


def run(transfers: Iterable[Transfer], p: Policy) -> list[Decision]:
    return [evaluate(t, p) for t in transfers]


def summarize(transfers: list[Transfer], decisions: list[Decision]) -> Summary:
    s = Summary(decisions[0].policy if decisions else "", Counter(), Counter(), Counter())
    for t, d in zip(transfers, decisions, strict=True):
        s.count[d.action] += 1
        s.cents[d.action] += t.amount_cents
        for r in d.rules():
            s.rules[r] += 1
        if t.label == "bad":
            s.bad_total += 1
            s.bad_stopped += d.action in STOPPING
            s.bad_reviewed += d.action == "review"
        elif t.label == "good":
            s.good_total += 1
            s.good_stopped += d.action in STOPPING
            s.good_reviewed += d.action == "review"
    return s


@dataclass(frozen=True)
class Change:
    transfer_id: str
    before: str
    after: str
    label: str
    rules_added: tuple[str, ...]
    rules_removed: tuple[str, ...]


def compare(transfers: list[Transfer], a: list[Decision], b: list[Decision]) -> list[Change]:
    out = []
    for t, x, y in zip(transfers, a, b, strict=True):
        if x.action != y.action:
            out.append(
                Change(
                    t.id,
                    x.action,
                    y.action,
                    t.label,
                    tuple(sorted(y.rules() - x.rules())),
                    tuple(sorted(x.rules() - y.rules())),
                )
            )
    out.sort(key=lambda c: (RANK[c.before] - RANK[c.after], c.transfer_id))
    return out


def summary_md(s: Summary) -> str:
    lines = [f"### {s.policy}", "", "| action | transfers | value |", "|---|---|---|"]
    for a in ACTIONS:
        lines.append(f"| {a} | {s.count[a]} | ${s.cents[a] / 100:,.2f} |")
    if s.bad_total or s.good_total:
        lines += [
            "",
            f"- labelled bad: {s.bad_total}, stopped {s.bad_stopped}, sent to review {s.bad_reviewed}, "
            f"let through {s.bad_total - s.bad_stopped - s.bad_reviewed}",
            f"- labelled good: {s.good_total}, stopped {s.good_stopped}, sent to review {s.good_reviewed}",
        ]
    if s.rules:
        lines += ["", "Rules that fired: " + ", ".join(f"{r} {n}" for r, n in sorted(s.rules.items()))]
    return "\n".join(lines) + "\n"
