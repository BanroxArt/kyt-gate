from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kytgate import Policy, Transfer, load_policy, transfer_from

EX = Path(__file__).resolve().parents[1] / "examples"
USDX = "0x" + "a1" * 20
USDQ = "0x" + "b2" * 20
HOT = "0x" + "0c" * 20
SANCTIONED = "0x" + "d0" * 20
MIXER = "0x" + "e0" * 20


@pytest.fixture(scope="session")
def base() -> Policy:
    return load_policy(EX / "policy-base.toml")


def tx(**kw: Any) -> Transfer:
    d: dict[str, Any] = {
        "id": "t1",
        "ts": "2026-12-15T12:00:00Z",
        "direction": "out",
        "chain": "eth",
        "token": USDX,
        "amount_cents": 50_000,
        "from": HOT,
        "to": "0x" + "77" * 20,
        "counterparty": {"type": "unhosted"},
    }
    d.update(kw)
    return transfer_from(d)
