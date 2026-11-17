"""Evaluate one transfer against a policy.

Every finding carries a rule ID, the action the policy assigns to it, and
where the fact came from (which list and its as-of date, which special
measure, which exposure source). The decision is the strictest action of
any finding, or ``allow`` when there are none.

Actions, mildest first: ``allow``, ``review`` (let it through, a person
looks after), ``hold`` (do not release until a person decides), ``reject``
(refuse to process) and ``block`` (take control of the funds and keep them;
for OFAC, a blocked-property report is due within 10 business days under
31 CFR 501.603, and a rejected transaction is reported under 501.604).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import specialmeasures as sm

from .addr import family_of_chain
from .model import Transfer
from .policy import ACTIONS, RANK, Policy


@dataclass(frozen=True)
class Finding:
    rule: str
    action: str
    detail: str
    source: str = ""


@dataclass(frozen=True)
class Decision:
    transfer_id: str
    action: str
    findings: tuple[Finding, ...]
    policy: str

    def rules(self) -> set[str]:
        return {f.rule for f in self.findings}


@lru_cache(maxsize=1)
def _registry() -> sm.Registry:
    return sm.load()


def _strictest(actions: list[str]) -> str:
    return max(actions, key=lambda a: RANK[a]) if actions else "allow"


def evaluate(t: Transfer, p: Policy) -> Decision:
    out: list[Finding] = []
    fam = family_of_chain(t.chain)

    # 1. Token allowlist and GENIUS Act status.
    tok = p.token(t.chain, t.token)
    if tok is None:
        if p.unlisted_token != "allow":
            out.append(
                Finding(
                    "KG-TOKEN-UNLISTED", p.unlisted_token, f"{t.token} on {t.chain} is not on the allowlist"
                )
            )
    elif tok.status != "permitted" and tok.status != "foreign-comparable":
        after = t.day >= p.require_permitted_from
        out.append(
            Finding(
                "KG-TOKEN-STATUS",
                p.not_permitted_after if after else p.not_permitted_before,
                f"{tok.symbol} ({tok.issuer}) has status {tok.status}; "
                f"{'on or after' if after else 'before'} {p.require_permitted_from.isoformat()}",
                "GENIUS Act sec. 3(b)",
            )
        )

    # 2. Address lists, for both ends of the transfer.
    for ref in p.lists:
        lst = ref.lst
        age = (t.day - lst.as_of).days
        if age > ref.max_age_days:
            out.append(
                Finding(
                    "KG-LIST-STALE",
                    ref.stale,
                    f"{lst.name} is {age} days old on the transfer date (limit {ref.max_age_days})",
                    lst.source,
                )
            )
        for side, address in (("sender", t.sender), ("receiver", t.receiver)):
            e = lst.get(fam, address)
            if e is None:
                continue
            action = _strictest([a for a in (ref.action, p.categories.get(e.category)) if a])
            out.append(
                Finding(
                    "KG-LIST",
                    action,
                    f"{side} {address} is on {lst.name} as {e.category}"
                    + (f" ({e.label})" if e.label else "")
                    + (f", {e.ref}" if e.ref else ""),
                    f"{lst.source} as of {lst.as_of.isoformat()}",
                )
            )

    # 3. Indirect exposure reported by whatever tool the user runs.
    for ex in t.exposure:
        if (
            ex.hops <= p.exposure_max_hops
            and ex.share_pct >= p.exposure_min_share_pct
            and ex.category in p.exposure
        ):
            out.append(
                Finding(
                    "KG-EXPOSURE",
                    p.exposure[ex.category],
                    f"{ex.share_pct}% {ex.category} exposure at {ex.hops} hops",
                    ex.source,
                )
            )

    # 4. FinCEN special measures on the counterparty VASP, as of the transfer date.
    cp = t.counterparty
    if p.sm_enabled and (cp.name or cp.domain):
        hits = sm.screen(
            _registry(), sm.Counterparty(name=cp.name, country=cp.country, domain=cp.domain), t.day
        )
        for h in hits:
            out.append(
                Finding(
                    "KG-SPECIAL-MEASURE",
                    p.sm[h.disposition.value],
                    f"counterparty {cp.name or cp.domain} matches {h.target} ({h.method.value}, "
                    f"{h.status.value} on {t.day.isoformat()})",
                    f"section {h.authority}, {h.cite}",
                )
            )

    # 5. Travel Rule data between financial institutions.
    if cp.type == "vasp" and t.amount_cents >= p.travel_threshold_cents:
        missing = [
            n for n, ok in (("originator", t.originator_info), ("beneficiary", t.beneficiary_info)) if not ok
        ]
        if missing:
            out.append(
                Finding(
                    "KG-TRAVEL-RULE",
                    p.travel_missing,
                    f"{' and '.join(missing)} information missing at or above "
                    f"${p.travel_threshold_cents / 100:,.0f}",
                    "31 CFR 1010.410(f); FIN-2019-G001",
                )
            )

    # 6. Size.
    if p.review_over_cents is not None and t.amount_cents >= p.review_over_cents:
        out.append(Finding("KG-AMOUNT", "review", f"amount at or above ${p.review_over_cents / 100:,.0f}"))

    out.sort(key=lambda f: (-RANK[f.action], f.rule))
    assert all(f.action in ACTIONS for f in out)
    return Decision(t.id, _strictest([f.action for f in out]), tuple(out), f"{p.name}@{p.version}")
