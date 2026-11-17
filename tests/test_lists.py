from __future__ import annotations

import pytest

from kytgate import ListError, list_from_csv, list_from_json, parse_ofac
from kytgate.addr import family_of_chain, family_of_ticker, key

EVM = "0x" + "Ab" * 20


def test_evm_addresses_match_across_evm_chains_and_case() -> None:
    lst = list_from_json(
        {"name": "n", "source": "s", "as_of": "2026-11-01", "entries": [{"address": EVM, "ticker": "USDT"}]}
    )
    assert lst.get("evm", EVM.lower()) is not None
    assert lst.get(family_of_chain("arbitrum"), EVM.upper().replace("0X", "0x")) is not None
    assert lst.get("tron", EVM) is None
    assert family_of_ticker("XBT", "1abc") == "btc"
    assert key("btc", "1AbC") != key("btc", "1abc")


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {"entries": []},
        {"name": "n", "source": "s", "entries": []},
        {"name": "n", "source": "s", "as_of": "soon", "entries": []},
        {"name": "n", "source": "s", "as_of": "2026-11-01", "entries": [{"ticker": "ETH"}]},
        {"name": "n", "source": "s", "as_of": "2026-11-01", "entries": [{"address": EVM}]},
        {
            "name": "n",
            "source": "s",
            "as_of": "2026-11-01",
            "entries": [{"address": EVM, "chain": "eth", "category": "vibes"}],
        },
        {"name": "n", "source": "s", "as_of": "2026-11-01", "entries": ["x"]},
    ],
)
def test_bad_lists(raw: object) -> None:
    with pytest.raises(ListError):
        list_from_json(raw)


def test_csv() -> None:
    lst = list_from_csv(f"address,ticker,category,label,ref\n{EVM},ETH,mixer,M,r\n", "n", "s", "2026-11-01")
    e = lst.get("evm", EVM)
    assert e is not None and e.category == "mixer" and e.label == "M"
    with pytest.raises(ListError):
        list_from_csv("addr,chain\n", "n", "s", "2026-11-01")


def _sdn_row(ent: str, name: str, remarks: str) -> str:
    cells = [ent, name, "-0- ", "CYBER4", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", "-0- ", remarks]
    return ",".join(f'"{c}"' for c in cells) + "\n"


def test_ofac_remarks_and_comments() -> None:
    eth = "0x" + "12" * 20
    btc = "bc1qexampleexampleexampleexample0000000"
    remarks = (
        f"Website example.test; Digital Currency Address - XBT {btc}; "
        f"alt. Digital Currency Address - ETH {eth}; Organization Type: x."
    )
    sdn = _sdn_row("1001", "EXAMPLE CO", remarks)
    sdn += _sdn_row("1002", "NO CRYPTO LTD", "-0- ")
    long = "x" * (1000 - len("; Digital")) + "; Digital"
    sdn += _sdn_row("1003", "LONG REMARKS", long)
    imp = parse_ofac(sdn)
    assert [(e["ticker"], e["address"]) for e in imp.entries] == [("XBT", btc), ("ETH", eth)]
    assert imp.entries[0]["ref"] == "SDN ent_num 1001 [CYBER4]"
    assert imp.truncated_without_comments == ["1003"]
    tron = "T" + "Q" * 33
    comments = f'"1003"," Currency Address - TRX {tron}; alt."\n'
    imp2 = parse_ofac(sdn, comments)
    assert ("TRX", tron) in [(e["ticker"], e["address"]) for e in imp2.entries]
    assert imp2.truncated_without_comments == []
