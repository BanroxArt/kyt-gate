"""Transfers as the gate sees them."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any


class TransferError(ValueError):
    pass


@dataclass(frozen=True)
class Exposure:
    category: str
    share_pct: int
    hops: int
    source: str


@dataclass(frozen=True)
class Counterparty:
    type: str = "unknown"  # vasp, unhosted, unknown
    name: str = ""
    domain: str = ""
    country: str = ""


@dataclass(frozen=True)
class Transfer:
    id: str
    ts: int
    direction: str  # in or out, from the screening institution's side
    chain: str
    token: str
    amount_cents: int
    sender: str
    receiver: str
    counterparty: Counterparty = Counterparty()
    originator_info: bool = False
    beneficiary_info: bool = False
    exposure: tuple[Exposure, ...] = ()
    label: str = ""  # ground truth on synthetic data: "bad" or "good"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def day(self) -> dt.date:
        return dt.datetime.fromtimestamp(self.ts, dt.UTC).date()

    @property
    def other_side(self) -> str:
        return self.sender if self.direction == "in" else self.receiver


_FIELDS = {
    "id",
    "ts",
    "direction",
    "chain",
    "token",
    "amount_cents",
    "from",
    "to",
    "counterparty",
    "travel_rule",
    "exposure",
    "label",
    "note",
}


def _ts(v: Any, where: str) -> int:
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    if isinstance(v, str):
        try:
            t = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise TransferError(f"{where}: bad ts {v!r}") from None
        if t.tzinfo is None:
            raise TransferError(f"{where}: ts {v!r} needs a UTC offset")
        return int(t.timestamp())
    raise TransferError(f"{where}: bad ts {v!r}")


def transfer_from(d: Any) -> Transfer:
    if not isinstance(d, dict):
        raise TransferError("transfer must be an object")
    where = f"transfer {d.get('id')!r}"
    bad = set(d) - _FIELDS
    if bad:
        raise TransferError(f"{where}: unknown fields {sorted(bad)}")
    for k in ("id", "ts", "direction", "chain", "token", "amount_cents", "from", "to"):
        if k not in d:
            raise TransferError(f"{where}: missing {k}")
    if d["direction"] not in ("in", "out"):
        raise TransferError(f"{where}: direction is in or out")
    amt = d["amount_cents"]
    if isinstance(amt, bool) or not isinstance(amt, int) or amt < 0:
        raise TransferError(f"{where}: amount_cents must be a non-negative integer")
    cp = d.get("counterparty", {})
    if not isinstance(cp, dict) or set(cp) - {"type", "name", "domain", "country"}:
        raise TransferError(f"{where}: counterparty has type, name, domain, country")
    if cp.get("type", "unknown") not in ("vasp", "unhosted", "unknown"):
        raise TransferError(f"{where}: counterparty.type is vasp, unhosted or unknown")
    tr = d.get("travel_rule", {})
    if not isinstance(tr, dict) or set(tr) - {"originator", "beneficiary"}:
        raise TransferError(f"{where}: travel_rule has originator and beneficiary (true or false)")
    exps = []
    for e in d.get("exposure", []):
        if not isinstance(e, dict) or not {"category", "share_pct", "hops", "source"} <= set(e):
            raise TransferError(f"{where}: exposure entries need category, share_pct, hops and source")
        exps.append(Exposure(str(e["category"]), int(e["share_pct"]), int(e["hops"]), str(e["source"])))
    return Transfer(
        id=str(d["id"]),
        ts=_ts(d["ts"], where),
        direction=d["direction"],
        chain=str(d["chain"]),
        token=str(d["token"]),
        amount_cents=amt,
        sender=str(d["from"]),
        receiver=str(d["to"]),
        counterparty=Counterparty(
            str(cp.get("type", "unknown")),
            str(cp.get("name", "")),
            str(cp.get("domain", "")),
            str(cp.get("country", "")),
        ),
        originator_info=bool(tr.get("originator", False)),
        beneficiary_info=bool(tr.get("beneficiary", False)),
        exposure=tuple(exps),
        label=str(d.get("label", "")),
    )
