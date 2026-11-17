from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from conftest import EX, HOT, MIXER, SANCTIONED, USDQ, tx

from kytgate import Policy, PolicyError, evaluate, load_policy, policy_from
from kytgate.policy import GENIUS_DASP_DATE


def test_clean_transfer_is_allowed(base: Policy) -> None:
    d = evaluate(tx(), base)
    assert d.action == "allow" and d.findings == () and d.policy == "example-desk@2026-12-01"


def test_sanctioned_either_side_blocks(base: Policy) -> None:
    out = evaluate(tx(to=SANCTIONED), base)
    assert out.action == "block" and out.rules() == {"KG-LIST"}
    assert "EXAMPLE PERSON 1" in out.findings[0].detail and "as of 2026-11-30" in out.findings[0].source
    inbound = evaluate(
        tx(direction="in", **{"from": SANCTIONED.upper().replace("0X", "0x"), "to": HOT}), base
    )
    assert inbound.action == "block"


def test_category_action_from_policy(base: Policy) -> None:
    assert evaluate(tx(to=MIXER), base).action == "review"


def test_unlisted_token_and_genius_date(base: Policy) -> None:
    assert evaluate(tx(token="0x" + "99" * 20), base).rules() == {"KG-TOKEN-UNLISTED"}
    before = evaluate(tx(token=USDQ), base)
    assert before.action == "review" and before.rules() == {"KG-TOKEN-STATUS"}
    on = evaluate(tx(token=USDQ, ts=f"{GENIUS_DASP_DATE.isoformat()}T00:00:00Z"), base)
    assert on.action == "reject"
    assert dt.date(2028, 7, 18) == GENIUS_DASP_DATE


def test_stale_list(base: Policy) -> None:
    d = evaluate(tx(ts="2027-01-30T00:00:00Z"), base)
    assert d.action == "review" and d.rules() == {"KG-LIST-STALE"}
    assert evaluate(tx(ts="2026-12-30T00:00:00Z"), base).rules() == set()


def test_exposure_thresholds(base: Policy) -> None:
    def ex(cat: str, share: int, hops: int) -> list[dict[str, object]]:
        return [{"category": cat, "share_pct": share, "hops": hops, "source": "tool"}]

    assert evaluate(tx(exposure=ex("sanctioned", 10, 2)), base).action == "review"
    assert evaluate(tx(exposure=ex("sanctioned", 9, 2)), base).action == "allow"
    assert evaluate(tx(exposure=ex("sanctioned", 50, 3)), base).action == "allow"
    assert evaluate(tx(exposure=ex("gambling", 50, 1)), base).action == "allow"


MEXC = {"type": "vasp", "name": "MEXC Global", "domain": "mexc.com", "country": "SC"}


def test_special_measure_follows_the_effective_date(base: Policy) -> None:
    tr = {"originator": True, "beneficiary": True}
    before = evaluate(tx(ts="2026-12-09T23:59:00Z", counterparty=MEXC, travel_rule=tr), base)
    after = evaluate(tx(ts="2026-12-10T00:00:00Z", counterparty=MEXC, travel_rule=tr), base)
    assert before.rules() == after.rules() == {"KG-SPECIAL-MEASURE"}
    assert before.action == "review" and "pending" in before.findings[0].detail
    assert after.action == "reject" and "in_force" in after.findings[0].detail
    assert "9714" in after.findings[0].source
    plain = evaluate(
        tx(
            counterparty={"type": "vasp", "name": "Example Exchange A", "domain": "exchange-a.example"},
            travel_rule=tr,
        ),
        base,
    )
    assert plain.action == "allow"


def test_travel_rule_threshold(base: Policy) -> None:
    vasp = {"type": "vasp", "name": "Example Exchange A"}
    assert evaluate(tx(amount_cents=299_999, counterparty=vasp), base).action == "allow"
    d = evaluate(tx(amount_cents=300_000, counterparty=vasp, travel_rule={"originator": True}), base)
    assert d.rules() == {"KG-TRAVEL-RULE"} and "beneficiary" in d.findings[0].detail
    unhosted = evaluate(tx(amount_cents=900_000), base)
    assert unhosted.rules() == set()


def test_strictest_wins_and_findings_sorted(base: Policy) -> None:
    d = evaluate(tx(to=SANCTIONED, token="0x" + "99" * 20), base)
    assert d.action == "block" and [f.rule for f in d.findings] == ["KG-LIST", "KG-TOKEN-UNLISTED"]


def test_amount_review() -> None:
    p = policy_from(
        {
            "name": "p",
            "version": "1",
            "amount": {"review_over_cents": 1_000_000},
            "tokens": {"unlisted": "allow"},
        }
    )
    assert evaluate(tx(amount_cents=1_000_000), p).rules() == {"KG-AMOUNT"}
    assert evaluate(tx(amount_cents=999_999), p).action == "allow"


@pytest.mark.parametrize(
    "raw",
    [
        {"version": "1"},
        {"name": "p", "version": "1", "colour": 1},
        {"name": "p", "version": "1", "tokens": {"unlisted": "maybe"}},
        {"name": "p", "version": "1", "tokens": {"allow": [{"chain": "eth"}]}},
        {
            "name": "p",
            "version": "1",
            "tokens": {
                "allow": [
                    {"chain": "eth", "contract": "0x1", "symbol": "S", "issuer": "I", "status": "great"}
                ]
            },
        },
        {"name": "p", "version": "1", "tokens": {"require_permitted_from": "later"}},
        {"name": "p", "version": "1", "lists": {"path": "x"}},
        {"name": "p", "version": "1", "lists": [{"action": "block"}]},
        {"name": "p", "version": "1", "lists": [{"path": "missing.json"}]},
        {"name": "p", "version": "1", "categories": {"vibes": "allow"}},
        {"name": "p", "version": "1", "exposure": {"max_hops": -1}},
        {"name": "p", "version": "1", "special_measures": {"enabled": "yes"}},
        {"name": "p", "version": "1", "special_measures": {"actions": {"hit": "shrug"}}},
        {"name": "p", "version": "1", "travel_rule": {"threshold_cents": True}},
    ],
)
def test_bad_policies(raw: dict[str, object]) -> None:
    with pytest.raises(PolicyError):
        policy_from(raw, Path("/nonexistent"))


def test_csv_list_needs_metadata(tmp_path: Path) -> None:
    (tmp_path / "l.csv").write_text("address,ticker,category\n")
    with pytest.raises(PolicyError):
        policy_from({"name": "p", "version": "1", "lists": [{"path": "l.csv"}]}, tmp_path)


def test_example_policies_load() -> None:
    strict = load_policy(EX / "policy-strict.toml")
    assert strict.categories["mixer"] == "reject" and strict.travel_missing == "hold"
