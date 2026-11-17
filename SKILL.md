---
name: kyt-gate
description: Write, check and compare a screening policy for stablecoin and token transfers (token allowlist and GENIUS Act status, address lists with freshness dates, exposure thresholds, FinCEN 311 and 9714 special measures, Travel Rule completeness) and explain each allow, review, hold, reject or block decision with its rule and source. Use when a compliance, payments or treasury team wants to screen token transfers, import OFAC digital currency addresses from files they downloaded, or see what a policy change would stop before switching it on. Uses the kytgate package from this repo. Engineering checklist only, not legal advice.
---

# kyt-gate

You help a team turn its screening rules into a policy file and test it. You do not decide what the law requires of them, and you never supply sanctions data yourself.

## 1. Lists

- Sanctions addresses come from OFAC's own files. Ask the user to download SDN.CSV and SDN_COMMENTS.CSV, then run `kytgate import-ofac SDN.CSV --comments SDN_COMMENTS.CSV --as-of <publication date> --out lists/ofac.json`. If it exits 3, the comments file is missing and some addresses were cut off.
- Never type addresses into a sanctions list from memory or from a news article. Tornado Cash was delisted on 2025-03-21; old lists still carry it.
- Other lists (attribution, own wallets) are CSV or JSON with a name, source and as_of date. Set `max_age_days` for each.

## 2. Policy

- Start from examples/policy-base.toml. For each token, record the issuer and its status under the GENIUS Act: permitted, foreign-comparable, not-permitted or unknown. Do not guess a status; use "unknown" until the user confirms it from the regulator's list.
- Keep risk choices and legal requirements apart when you explain the file. Mixer exposure, exposure thresholds and amount reviews are risk choices. The FinCEN CVC mixing proposal was withdrawn on 2026-10-06. The GENIUS Act has no velocity limits or cooling-off periods.
- `block` and `reject` mean different OFAC reports (31 CFR 501.603 and 501.604). Use block for SDN matches.

## 3. Test

- `kytgate simulate history.jsonl --policy current.toml --compare proposed.toml`. Labels in the history file should come from the team's own case outcomes.
- Report how many bad transfers the change newly stops, how many good ones it newly stops, and the review volume it adds. Read out a few changed decisions so the user can judge them.

## 4. Run

- `kytgate check transfers.jsonl --policy policy.toml --json` gives one decision per line with findings. Keep the policy name and version with every stored decision.

End with: engineering checklist, not legal advice; tested on synthetic data only.
