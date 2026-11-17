from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import EX
from hypothesis import given, settings
from hypothesis import strategies as st

from kytgate import compare, load_policy, load_transfers, run, summarize, transfer_from
from kytgate.__main__ import main
from kytgate.policy import RANK
from kytgate.synth import dumps, generate


def test_synth_is_deterministic_and_loads(tmp_path: Path) -> None:
    a, b = generate(200, 3), generate(200, 3)
    assert a == b and generate(200, 4) != a
    p = tmp_path / "t.jsonl"
    p.write_text(dumps(a))
    ts = load_transfers(p)
    assert len(ts) == 200 and {t.label for t in ts} == {"good", "bad"}


def test_base_policy_on_example_data() -> None:
    ts = load_transfers(EX / "transfers.jsonl")
    base, strict = load_policy(EX / "policy-base.toml"), load_policy(EX / "policy-strict.toml")
    sa, sb = summarize(ts, run(ts, base)), summarize(ts, run(ts, strict))
    assert sa.bad_total == sb.bad_total > 0
    assert sa.bad_total - sa.bad_stopped - sa.bad_reviewed == 0
    assert sb.bad_stopped >= sa.bad_stopped and sb.good_stopped >= sa.good_stopped
    assert sa.good_stopped == 0
    changes = compare(ts, run(ts, base), run(ts, strict))
    assert changes and all(c.before != c.after for c in changes)


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pol, tr = str(EX / "policy-base.toml"), str(EX / "transfers.jsonl")
    assert main(["simulate", tr, "--policy", pol, "--compare", str(EX / "policy-strict.toml")]) == 0
    out = capsys.readouterr().out
    assert "decisions change" in out and "synthetic data only" in out
    one = tmp_path / "one.jsonl"
    one.write_text((EX / "transfers.jsonl").read_text().splitlines()[0] + "\n")
    rc = main(["check", str(one), "--policy", pol, "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert rc in (0, 2) and doc["policy"] == "example-desk@2026-12-01"
    assert main(["synth", "--out", str(tmp_path / "s.jsonl"), "-n", "5"]) == 0
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "x"}\n')
    assert main(["check", str(bad), "--policy", pol]) == 1
    sdn = tmp_path / "SDN.CSV"
    sdn.write_text(
        '"1","A","-0- ","P","","","","","","","","Digital Currency Address - ETH 0x' + "12" * 20 + '; "\n'
    )
    out_list = tmp_path / "ofac.json"
    assert main(["import-ofac", str(sdn), "--as-of", "2026-11-14", "--out", str(out_list)]) == 0
    assert json.loads(out_list.read_text())["entries"][0]["category"] == "sanctioned"


@settings(max_examples=25, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10_000))
def test_strict_policy_never_loosens_a_decision(seed: int) -> None:
    ts = [transfer_from(d) for d in generate(80, seed)]
    base, strict = load_policy(EX / "policy-base.toml"), load_policy(EX / "policy-strict.toml")
    for a, b in zip(run(ts, base), run(ts, strict), strict=True):
        assert RANK[b.action] >= RANK[a.action]
