# kyt-gate

A policy-as-code gate for stablecoin and token transfers. You write the policy in TOML: which tokens you accept, which address lists you screen against and how fresh they must be, how much indirect exposure is too much, what to do with counterparties under a FinCEN special measure, and when Travel Rule information is missing. `kytgate` turns each transfer into allow, review, hold, reject or block, with the rule and the source behind every finding. Then it replays a month of transfers under two versions of the policy so you can see what a change would have stopped and what it would have bothered.

Built and maintained by Art Akopian, CEO of [Banrox](https://banrox.com).

> **Engineering checklist, not legal advice.** The gate applies the rules you give it to the facts you give it. It does not decide what the law requires of you, it does not hold any sanctions data, and its blockchain exposure numbers are whatever your analytics provider reported. Tested on synthetic data only: every address, token contract, list, counterparty and transfer in this repository is made up, apart from names quoted from public FinCEN orders in the special-measures registry.

## Why

Screening a token transfer is several separate questions, and in most shops they live in different tools: a sanctions screen, a blockchain analytics score, a token allowlist kept in a spreadsheet, a Travel Rule check in the messaging vendor, and somebody's memory of which exchanges FinCEN has cut off. When a decision is questioned later, nobody can say which list version was used or why the threshold was 10%. Putting the whole decision in one versioned policy file, and replaying history against a proposed change before switching it on, fixes both.

Several dates matter in the next two years and are easy to get wrong:

- **Tornado Cash is no longer on the SDN list.** OFAC removed it on 2025-03-21 ([recent action](https://ofac.treasury.gov/recent-actions/20250321)). A list from before that date will still flag those addresses. That is why every list carries an `as_of` date and the policy a `max_age_days`.
- **FinCEN withdrew its proposed special measure on CVC mixing** on 2026-10-06 (91 FR 63513). There is no federal rule that treats mixer exposure as a reportable class of transactions. The example policy sends mixer exposure to review because a desk may choose to; that is a risk choice, not a legal requirement.
- **MEXC Global's section 9714 order takes effect 2026-12-10** (91 FR 72420). The order excludes MEXC's US offices and recognises that an institution may be unable to reject incoming CVC. The gate gets these dates and scopes from the [special-measures](https://github.com/BanroxArt/special-measures) registry; before the effective date a hit is "pending" and goes to review in the example policy.
- **The GENIUS Act has no velocity limits or cooling-off periods.** What it does say for a desk like this is sec. 3(b)(1): from three years after enactment, 2028-07-18, a digital asset service provider may not offer or sell a payment stablecoin to a person in the United States unless a permitted issuer issued it (sec. 3(b)(2) covers comparable foreign issuers). The token allowlist records each token's status, and the example policy reviews a non-permitted stablecoin before that date and rejects it on and after it.
- **Travel Rule.** 31 CFR 1010.410(f) applies to transmittals of $3,000 or more, and FinCEN's 2019 guidance (FIN-2019-G001) says it covers CVC transmittals between financial institutions. The gate checks it only when the counterparty is a VASP. Unhosted wallet transfers are outside it.

## How it decides

```text
transfer ──► token allowlist ──► address lists ──► exposure ──► special measures ──► Travel Rule ──► amount
                 │                    │               │                │                  │
           KG-TOKEN-*         KG-LIST, KG-LIST-STALE  KG-EXPOSURE  KG-SPECIAL-MEASURE   KG-TRAVEL-RULE
```

Every check that fires adds a finding with an action. The decision is the strictest finding: allow < review < hold < reject < block.

| rule | fires when | source in the finding |
|---|---|---|
| KG-TOKEN-UNLISTED | the token contract is not on the allowlist | your policy |
| KG-TOKEN-STATUS | the token's issuer is not permitted; action depends on the date | GENIUS Act sec. 3(b) |
| KG-LIST | sender or receiver is on a list; the list action and the category action, whichever is stricter | list name and `as_of` |
| KG-LIST-STALE | a list is older than its `max_age_days` on the transfer date | list name and `as_of` |
| KG-EXPOSURE | your analytics reported at least `min_share_pct` from a category within `max_hops` | the provider named in the transfer |
| KG-SPECIAL-MEASURE | the counterparty matches a FinCEN 311 or 9714 order by name or domain | order and Federal Register cite |
| KG-TRAVEL-RULE | VASP counterparty, at or over the threshold, originator or beneficiary information missing | 31 CFR 1010.410(f); FIN-2019-G001 |
| KG-AMOUNT | at or over `review_over_cents` | your policy |

EVM addresses are compared in lower case and match across EVM chains, so one listed address covers Ethereum, Arbitrum, Base and the rest. Other chains are compared exactly.

"Block" and "reject" are kept apart because OFAC treats them differently: blocked property is reported within 10 business days (31 CFR 501.603) and rejected transactions under 501.604. The gate only labels the decision; filing is yours.

## Use

```sh
pip install 'kytgate @ git+https://github.com/BanroxArt/kyt-gate'
kytgate check examples/transfers.jsonl --policy examples/policy-base.toml
kytgate check transfers.jsonl --policy policy.toml --json      # one decision per line
kytgate simulate examples/transfers.jsonl --policy examples/policy-base.toml \
    --compare examples/policy-strict.toml
kytgate import-ofac SDN.CSV --comments SDN_COMMENTS.CSV --as-of 2026-11-14 --out lists/ofac.json
kytgate synth --out synthetic.jsonl -n 5000
```

`check` exits 0 when everything is allowed, 2 when anything is not, 1 on an input error.

### Transfers

One JSON object per line:

```json
{"id": "t1", "ts": "2026-12-15T12:00:00Z", "direction": "out", "chain": "eth",
 "token": "0xa1a1...", "amount_cents": 500000, "from": "0x0c0c...", "to": "0x7777...",
 "counterparty": {"type": "vasp", "name": "Example Exchange A", "domain": "exchange-a.example", "country": "GB"},
 "travel_rule": {"originator": true, "beneficiary": false},
 "exposure": [{"category": "mixer", "share_pct": 12, "hops": 2, "source": "your analytics provider"}]}
```

Amounts are in cents of the dollar value at the time of the transfer. Exposure is whatever your analytics provider reported; the gate does not trace anything on chain. `label` (good or bad) is optional and only used by `simulate`.

### OFAC import

`import-ofac` reads `SDN.CSV` and `SDN_COMMENTS.CSV` that you downloaded from OFAC and pulls every `Digital Currency Address - TICKER address` out of the remarks, the format OFAC describes in [FAQ 563](https://ofac.treasury.gov/faqs/563). The remarks column is limited to 1,000 characters and OFAC puts the overflow in `SDN_COMMENTS.CSV` ([data specification](https://ofac.treasury.gov/system/files/126/dat_spec.txt)). If you leave the comments file out and any record hits the limit, the import warns and exits 3, because the addresses past the limit are missing. The tool never downloads anything itself.

### Comparing policies

On the 600 synthetic transfers in `examples/`, the stricter policy (mixer exposure rejected, exposure counted to 3 hops and 1%, missing Travel Rule information held) stops 45 of 57 bad transfers instead of 33, at the price of stopping 10 good ones and sending 12 more to review. 44 decisions change, and `simulate --compare` lists them, biggest escalation first. Those numbers describe the made-up data and nothing else; they show what the report looks like.

## What is real and what is not

Real, with sources in [docs/sources.md](docs/sources.md):

- The OFAC address format, the 1,000-character remarks limit, the Tornado Cash delisting, and the 501.603 and 501.604 reporting split.
- The special-measures dates and scopes, read from the published Federal Register documents by the special-measures package.
- The GENIUS Act sec. 3(b) date and the Travel Rule threshold.

Not real:

- Every address, token contract, issuer, exchange and list in `examples/` and `synth.py`. The "sanctions" list is made-up addresses with made-up names. Do not screen with it.
- The labels. "Bad" in the synthetic data means "the policy should stop it", not that anyone did anything wrong.
- Exposure figures. They imitate what an analytics provider returns; different providers give different numbers for the same address.

What the gate does not do: trace funds on chain, score wallets, file SARs or OFAC reports, or decide whether a transaction is suspicious. It records which rule fired and why, which is what an examiner or your own second line will ask for.

## Development

```sh
make check    # ruff, content lint, mypy --strict, pytest
python bench/run.py
```

MIT licence. Copyright (c) 2026 Banrox Inc.
