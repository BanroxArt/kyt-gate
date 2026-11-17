"""Addresses and the chains they belong to.

OFAC labels each digital currency address on the SDN List with the currency's
symbol ("Digital Currency Address - ETH", "- XBT", "- TRX" ...), per OFAC FAQ
563. An Ethereum-format address is the same account on every EVM chain, so
addresses listed under ETH, USDT, USDC, ARB, BSC and the like are matched on
any EVM chain. Everything else matches only within its own family.
"""

from __future__ import annotations

import re

EVM_TICKERS = frozenset(
    {"ETH", "ETC", "USDT", "USDC", "ARB", "BSC", "BNB", "MATIC", "POL", "BASE", "OP", "AVAX"}
)
FAMILY_BY_TICKER = {
    "XBT": "btc",
    "BTC": "btc",
    "TRX": "tron",
    "LTC": "ltc",
    "XMR": "xmr",
    "XRP": "xrp",
    "SOL": "sol",
}
EVM_CHAINS = frozenset({"eth", "arbitrum", "base", "optimism", "polygon", "bsc", "avalanche", "evm"})
_EVM = re.compile(r"^0x[0-9a-fA-F]{40}$")


def is_evm(address: str) -> bool:
    return bool(_EVM.match(address.strip()))


def family_of_chain(chain: str) -> str:
    c = chain.strip().lower()
    return "evm" if c in EVM_CHAINS else c


def family_of_ticker(ticker: str, address: str) -> str:
    t = ticker.strip().upper()
    if t in FAMILY_BY_TICKER:
        return FAMILY_BY_TICKER[t]
    if t in EVM_TICKERS or is_evm(address):
        return "evm"
    return t.lower()


def key(family: str, address: str) -> str:
    a = address.strip()
    return f"{family}:{a.lower() if family == 'evm' else a}"
