# Contributing

Useful contributions:

- parsers for other public list formats
- test cases from public OFAC actions or FinCEN orders, with the document cited
- corrections to dates or scopes, with the primary source

Code changes:

- `ruff check .`, `ruff format --check .`, `python scripts/check.py`, `mypy` and `pytest -q` must pass.
- synthetic or public data only; never a real customer's address or transfer
- every legal date or threshold cites a primary source in docs/sources.md
- mypy --strict and the content lint must pass
- Synthetic data only. Never commit a real customer, account, address or case.
