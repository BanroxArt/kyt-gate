"""Time the gate on synthetic transfers with the example policies."""

from __future__ import annotations

import time
from pathlib import Path

from kytgate import load_policy, run, transfer_from
from kytgate.synth import generate

EX = Path(__file__).resolve().parents[1] / "examples"


def main() -> None:
    pol = load_policy(EX / "policy-base.toml")
    run([transfer_from(d) for d in generate(10, 1)], pol)  # warm the special-measures registry
    for n in (1_000, 10_000, 100_000):
        ts = [transfer_from(d) for d in generate(n, 1)]
        t0 = time.perf_counter()
        run(ts, pol)
        dt = time.perf_counter() - t0
        print(f"{n:>7} transfers: {dt:.2f} s, {dt / n * 1e6:.1f} us each")


if __name__ == "__main__":
    main()
