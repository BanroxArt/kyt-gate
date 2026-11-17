"""Policy files (TOML). Unknown keys are errors, so a typo cannot quietly
leave a default in place."""

from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .addr import family_of_chain
from .lists import CATEGORIES, AddressList, ListError, load_list

ACTIONS = ("allow", "review", "hold", "reject", "block")
RANK = {a: i for i, a in enumerate(ACTIONS)}
TOKEN_STATUSES = frozenset({"permitted", "foreign-comparable", "not-permitted", "unknown"})
# GENIUS Act sec. 3(b)(1): three years after enactment on July 18, 2025.
GENIUS_DASP_DATE = dt.date(2028, 7, 18)


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    chain_family: str
    contract: str
    symbol: str
    issuer: str
    status: str


@dataclass(frozen=True)
class ListRef:
    lst: AddressList
    action: str | None
    max_age_days: int = 7
    stale: str = "review"


@dataclass
class Policy:
    name: str
    version: str
    tokens: dict[tuple[str, str], Token]
    unlisted_token: str = "reject"
    require_permitted_from: dt.date = GENIUS_DASP_DATE
    not_permitted_after: str = "reject"
    not_permitted_before: str = "allow"
    lists: list[ListRef] = field(default_factory=list)
    categories: dict[str, str] = field(default_factory=dict)
    exposure_max_hops: int = 2
    exposure_min_share_pct: int = 5
    exposure: dict[str, str] = field(default_factory=dict)
    sm_enabled: bool = True
    sm: dict[str, str] = field(default_factory=dict)
    travel_threshold_cents: int = 300_000
    travel_missing: str = "hold"
    review_over_cents: int | None = None

    def token(self, chain: str, contract: str) -> Token | None:
        return self.tokens.get((family_of_chain(chain), contract.strip().lower()))


DEFAULT_CATEGORIES = {
    "sanctioned": "block",
    "special_measure": "reject",
    "mixer": "review",
    "darknet": "reject",
    "ransomware": "block",
    "stolen_funds": "hold",
    "scam": "hold",
    "gambling": "review",
    "exchange": "allow",
    "bridge": "allow",
    "own": "allow",
    "other": "review",
}
DEFAULT_EXPOSURE = {"sanctioned": "review", "ransomware": "review", "darknet": "review", "mixer": "review"}
DEFAULT_SM = {"hit": "reject", "review": "review", "pending": "review", "watch": "allow", "info": "allow"}


def _action(v: Any, where: str) -> str:
    if v not in ACTIONS:
        raise PolicyError(f"{where}: action must be one of {', '.join(ACTIONS)} (got {v!r})")
    return str(v)


def _keys(d: Any, allowed: set[str], where: str) -> dict[str, Any]:
    if not isinstance(d, dict):
        raise PolicyError(f"{where}: expected a table")
    bad = set(d) - allowed
    if bad:
        raise PolicyError(f"{where}: unknown keys {sorted(bad)}")
    return d


def _int(v: Any, where: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise PolicyError(f"{where}: expected a non-negative integer")
    return v


def _action_map(d: Any, allowed: set[str], base: dict[str, str], where: str) -> dict[str, str]:
    out = dict(base)
    for k, v in _keys(d, allowed, where).items():
        out[k] = _action(v, f"{where}.{k}")
    return out


def policy_from(raw: dict[str, Any], base_dir: Path = Path(".")) -> Policy:
    _keys(
        raw,
        {
            "name",
            "version",
            "tokens",
            "lists",
            "categories",
            "exposure",
            "special_measures",
            "travel_rule",
            "amount",
        },
        "policy",
    )
    if not raw.get("name") or not raw.get("version"):
        raise PolicyError("policy: name and version are required, so every decision can name the policy")
    t = _keys(
        raw.get("tokens", {}),
        {"unlisted", "require_permitted_from", "not_permitted_after", "not_permitted_before", "allow"},
        "tokens",
    )
    tokens: dict[tuple[str, str], Token] = {}
    for i, a in enumerate(t.get("allow", [])):
        a = _keys(a, {"chain", "contract", "symbol", "issuer", "status"}, f"tokens.allow[{i}]")
        for k in ("chain", "contract", "symbol", "issuer", "status"):
            if not a.get(k):
                raise PolicyError(f"tokens.allow[{i}]: missing {k}")
        if a["status"] not in TOKEN_STATUSES:
            raise PolicyError(f"tokens.allow[{i}].status: one of {sorted(TOKEN_STATUSES)}")
        fam = family_of_chain(a["chain"])
        tokens[(fam, a["contract"].strip().lower())] = Token(
            fam, a["contract"], a["symbol"], a["issuer"], a["status"]
        )
    rpf = t.get("require_permitted_from", GENIUS_DASP_DATE)
    if isinstance(rpf, str):
        try:
            rpf = dt.date.fromisoformat(rpf)
        except ValueError:
            raise PolicyError("tokens.require_permitted_from: YYYY-MM-DD") from None
    if not isinstance(rpf, dt.date):
        raise PolicyError("tokens.require_permitted_from: a date")
    lists: list[ListRef] = []
    raw_lists = raw.get("lists", [])
    if not isinstance(raw_lists, list):
        raise PolicyError("lists: use [[lists]] entries")
    for i, lr in enumerate(raw_lists):
        lr = _keys(lr, {"path", "action", "name", "source", "as_of", "max_age_days", "stale"}, f"lists[{i}]")
        if "path" not in lr:
            raise PolicyError(f"lists[{i}]: path is required")
        try:
            lst = load_list(
                base_dir / lr["path"], lr.get("name", ""), lr.get("source", ""), str(lr.get("as_of", ""))
            )
        except (OSError, ListError) as e:
            raise PolicyError(f"lists[{i}]: {e}") from None
        lists.append(
            ListRef(
                lst,
                _action(lr["action"], f"lists[{i}].action") if "action" in lr else None,
                _int(lr.get("max_age_days", 7), f"lists[{i}].max_age_days"),
                _action(lr.get("stale", "review"), f"lists[{i}].stale"),
            )
        )
    ex = _keys(raw.get("exposure", {}), {"max_hops", "min_share_pct", "actions"}, "exposure")
    sm = _keys(raw.get("special_measures", {}), {"enabled", "actions"}, "special_measures")
    if "enabled" in sm and not isinstance(sm["enabled"], bool):
        raise PolicyError("special_measures.enabled: true or false")
    tr = _keys(raw.get("travel_rule", {}), {"threshold_cents", "missing"}, "travel_rule")
    am = _keys(raw.get("amount", {}), {"review_over_cents"}, "amount")
    return Policy(
        name=str(raw["name"]),
        version=str(raw["version"]),
        tokens=tokens,
        unlisted_token=_action(t.get("unlisted", "reject"), "tokens.unlisted"),
        require_permitted_from=rpf,
        not_permitted_after=_action(t.get("not_permitted_after", "reject"), "tokens.not_permitted_after"),
        not_permitted_before=_action(t.get("not_permitted_before", "allow"), "tokens.not_permitted_before"),
        lists=lists,
        categories=_action_map(raw.get("categories", {}), set(CATEGORIES), DEFAULT_CATEGORIES, "categories"),
        exposure_max_hops=_int(ex.get("max_hops", 2), "exposure.max_hops"),
        exposure_min_share_pct=_int(ex.get("min_share_pct", 5), "exposure.min_share_pct"),
        exposure=_action_map(ex.get("actions", {}), set(CATEGORIES), DEFAULT_EXPOSURE, "exposure.actions"),
        sm_enabled=sm.get("enabled", True),
        sm=_action_map(sm.get("actions", {}), set(DEFAULT_SM), DEFAULT_SM, "special_measures.actions"),
        travel_threshold_cents=_int(tr.get("threshold_cents", 300_000), "travel_rule.threshold_cents"),
        travel_missing=_action(tr.get("missing", "hold"), "travel_rule.missing"),
        review_over_cents=_int(am["review_over_cents"], "amount.review_over_cents")
        if "review_over_cents" in am
        else None,
    )


def load_policy(path: str | Path) -> Policy:
    p = Path(path)
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise PolicyError(f"{p}: {e}") from None
    return policy_from(raw, p.parent)
