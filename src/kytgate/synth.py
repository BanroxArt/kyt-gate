"""Synthetic transfers with known labels, for trying policies.

Every address is made up (a repeated byte or a counter), and the sanctioned
and mixer lists in examples/lists are made up to match. The special-measures
cases use real FinCEN orders from the special-measures registry, by name
only, because the point is to see the effective dates work.
"""

from __future__ import annotations

import datetime as dt
import json
import random
from typing import Any

USDX = "0x" + "a1" * 20  # example permitted token
USDQ = "0x" + "b2" * 20  # example token whose issuer is not permitted
SANCTIONED = ["0x" + f"{0xD0 + i:02x}" * 20 for i in range(4)]
MIXER = ["0x" + f"{0xE0 + i:02x}" * 20 for i in range(3)]
OUR_HOT = "0x" + "0c" * 20
EXCHANGES = [("Example Exchange A", "exchange-a.example"), ("Example Exchange B", "exchange-b.example")]


def _addr(rng: random.Random) -> str:
    return "0x" + "".join(f"{rng.randrange(256):02x}" for _ in range(20))


def _ts(day: dt.date, rng: random.Random) -> str:
    t = dt.datetime(day.year, day.month, day.day, rng.randrange(24), rng.randrange(60), tzinfo=dt.UTC)
    return t.isoformat().replace("+00:00", "Z")


def generate(
    n: int = 1000, seed: int = 7, start: dt.date = dt.date(2026, 12, 1), days: int = 30
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []

    def add(label: str, kind: str, **kw: Any) -> None:
        day = start + dt.timedelta(days=kw.pop("day", rng.randrange(days)))
        d: dict[str, Any] = {
            "id": f"t{len(out) + 1:05d}",
            "ts": _ts(day, rng),
            "direction": kw.pop("direction", rng.choice(["in", "out"])),
            "chain": "eth",
            "token": kw.pop("token", USDX),
            "amount_cents": kw.pop("amount_cents", rng.randrange(20, 5_000) * 100),
            "label": label,
            "note": kind,
        }
        other = kw.pop("other", _addr(rng))
        d["from"], d["to"] = (other, OUR_HOT) if d["direction"] == "in" else (OUR_HOT, other)
        d.update(kw)
        out.append(d)

    for _ in range(n):
        r = rng.random()
        if r < 0.70:
            add("good", "ordinary unhosted wallet", counterparty={"type": "unhosted"})
        elif r < 0.80:
            name, dom = rng.choice(EXCHANGES)
            amt = rng.randrange(1_000, 20_000) * 100
            add(
                "good",
                "exchange with Travel Rule data",
                amount_cents=amt,
                counterparty={"type": "vasp", "name": name, "domain": dom, "country": "US"},
                travel_rule={"originator": True, "beneficiary": True},
            )
        elif r < 0.84:
            add(
                "good",
                "small old mixer exposure",
                counterparty={"type": "unhosted"},
                exposure=[
                    {
                        "category": "mixer",
                        "share_pct": rng.randrange(1, 4),
                        "hops": 3,
                        "source": "example-tool",
                    }
                ],
            )
        elif r < 0.87:
            name, dom = rng.choice(EXCHANGES)
            add(
                "good",
                "exchange, Travel Rule data missing",
                amount_cents=rng.randrange(3_000, 20_000) * 100,
                counterparty={"type": "vasp", "name": name, "domain": dom, "country": "US"},
            )
        elif r < 0.90:
            add("bad", "sanctioned address", other=rng.choice(SANCTIONED), counterparty={"type": "unhosted"})
        elif r < 0.93:
            add("bad", "mixer address", other=rng.choice(MIXER), counterparty={"type": "unhosted"})
        elif r < 0.95:
            add(
                "bad",
                "heavy indirect sanctioned exposure",
                counterparty={"type": "unhosted"},
                exposure=[
                    {
                        "category": "sanctioned",
                        "share_pct": rng.randrange(20, 90),
                        "hops": 2,
                        "source": "example-tool",
                    }
                ],
            )
        elif r < 0.98:
            # MEXC Global's section 9714 order takes effect 2026-12-10; before
            # that date the payment is lawful and labelled good.
            day = rng.randrange(days)
            add(
                "bad" if start + dt.timedelta(days=day) >= dt.date(2026, 12, 10) else "good",
                "MEXC Global counterparty",
                day=day,
                counterparty={"type": "vasp", "name": "MEXC Global", "domain": "mexc.com", "country": "SC"},
                travel_rule={"originator": True, "beneficiary": True},
            )
        else:
            add("good", "token from a non-permitted issuer", token=USDQ, counterparty={"type": "unhosted"})
    return out


def dumps(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
