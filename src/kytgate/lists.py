"""Address lists the user supplies: sanctions lists, attributions, their own
blocklists. Nothing here downloads or scrapes anything.

Formats:

- JSON: ``{"name", "source", "as_of", "entries": [{"address", "chain" or
  "ticker", "category", "label", "ref"}]}``.
- CSV with the header ``address,ticker,category,label,ref`` and the list's
  name, source and as-of date given on the command line or in the policy.
- OFAC's legacy ``SDN.CSV`` (plus ``SDN_COMMENTS.CSV``, which holds remarks
  past the 1,000-character limit of the remarks column), converted once with
  ``kytgate import-ofac`` into the JSON form.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .addr import family_of_chain, family_of_ticker, key

CATEGORIES = frozenset(
    {
        "sanctioned",
        "special_measure",
        "mixer",
        "darknet",
        "scam",
        "ransomware",
        "stolen_funds",
        "gambling",
        "exchange",
        "bridge",
        "own",
        "other",
    }
)


class ListError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    address: str
    family: str
    category: str
    label: str = ""
    ref: str = ""


@dataclass
class AddressList:
    name: str
    source: str
    as_of: dt.date
    entries: dict[str, Entry] = field(default_factory=dict)

    def get(self, family: str, address: str) -> Entry | None:
        return self.entries.get(key(family, address))

    def add(self, e: Entry) -> None:
        self.entries.setdefault(key(e.family, e.address), e)


def _date(v: Any, where: str) -> dt.date:
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        raise ListError(f"{where}: as_of must be YYYY-MM-DD (got {v!r})") from None


def _entry(d: dict[str, Any], where: str) -> Entry:
    addr = str(d.get("address", "")).strip()
    if not addr:
        raise ListError(f"{where}: missing address")
    cat = str(d.get("category", "other"))
    if cat not in CATEGORIES:
        raise ListError(f"{where}: category {cat!r} is not one of {sorted(CATEGORIES)}")
    if d.get("chain"):
        fam = family_of_chain(str(d["chain"]))
    elif d.get("ticker"):
        fam = family_of_ticker(str(d["ticker"]), addr)
    else:
        raise ListError(f"{where}: give chain or ticker")
    return Entry(addr, fam, cat, str(d.get("label", "")), str(d.get("ref", "")))


def list_from_json(raw: Any, where: str = "list") -> AddressList:
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        raise ListError(f"{where}: expected an object with an entries list")
    for k in ("name", "source", "as_of"):
        if not raw.get(k):
            raise ListError(f"{where}: missing {k} (every list needs a name, a source and an as-of date)")
    out = AddressList(str(raw["name"]), str(raw["source"]), _date(raw["as_of"], where))
    for i, d in enumerate(raw["entries"]):
        if not isinstance(d, dict):
            raise ListError(f"{where}: entry {i} is not an object")
        out.add(_entry(d, f"{where}: entry {i}"))
    return out


def list_from_csv(text: str, name: str, source: str, as_of: str) -> AddressList:
    out = AddressList(name, source, _date(as_of, name))
    rows = csv.DictReader(io.StringIO(text))
    need = {"address", "ticker", "category"}
    if not rows.fieldnames or not need <= set(rows.fieldnames):
        raise ListError(f"{name}: CSV header needs {sorted(need)}")
    for i, r in enumerate(rows, 2):
        out.add(_entry(dict(r), f"{name}: line {i}"))
    return out


def load_list(path: str | Path, name: str = "", source: str = "", as_of: str = "") -> AddressList:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".csv":
        if not (name and source and as_of):
            raise ListError(f"{p}: a CSV list needs name, source and as_of in the policy")
        return list_from_csv(text, name, source, as_of)
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise ListError(f"{p}: {e}") from None
    return list_from_json(raw, str(p))


# OFAC legacy CSV ---------------------------------------------------------------

_DCA = re.compile(r"Digital Currency Address - ([A-Z0-9]+)\s+([^\s;]+)")
REMARKS_LIMIT = 1000


@dataclass(frozen=True)
class OfacImport:
    entries: list[dict[str, str]]
    truncated_without_comments: list[str]


def parse_ofac(sdn_csv: str, comments_csv: str | None = None) -> OfacImport:
    """Digital currency addresses from OFAC's SDN.CSV (no header row) and
    SDN_COMMENTS.CSV. Remarks are the last column of SDN.CSV; the comments
    file carries ``ent_num, remarks_extended`` for remarks that did not fit."""
    extra: dict[str, str] = {}
    if comments_csv:
        for row in csv.reader(io.StringIO(comments_csv)):
            if len(row) >= 2:
                extra[row[0].strip()] = extra.get(row[0].strip(), "") + row[1]
    out: list[dict[str, str]] = []
    truncated: list[str] = []
    for row in csv.reader(io.StringIO(sdn_csv)):
        if len(row) < 12:
            continue
        ent, name, program, remarks = row[0].strip(), row[1].strip(), row[3].strip(), row[11]
        if remarks.strip() == "-0-":
            remarks = ""
        if len(remarks) >= REMARKS_LIMIT and ent not in extra:
            truncated.append(ent)
        text = remarks + extra.get(ent, "")
        for m in _DCA.finditer(text):
            out.append(
                {
                    "address": m.group(2),
                    "ticker": m.group(1),
                    "category": "sanctioned",
                    "label": name,
                    "ref": f"SDN ent_num {ent} [{program}]",
                }
            )
    return OfacImport(out, truncated)
