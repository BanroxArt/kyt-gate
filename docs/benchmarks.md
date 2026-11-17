# Benchmarks

`python bench/run.py` evaluates synthetic transfers against `examples/policy-base.toml` (two lists, exposure, special measures, Travel Rule). Measured on 2026-11-16 on an 8-vCPU Linux VM with CPython 3.13:

| transfers | time | per transfer |
|---|---|---|
| 1,000 | 0.02 s | about 25 us |
| 10,000 | 0.21 s | about 21 us |
| 100,000 | 2.1 s | about 21 us |

List lookups are dictionary lookups, so list size barely matters. Special-measures screening normalises the counterparty name on every call and is most of the cost; a desk that screens millions of transfers a day can cache by counterparty. Loading the policy and lists happens once and is not in these numbers.
