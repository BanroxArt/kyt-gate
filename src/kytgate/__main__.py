"""Command line: check, simulate, import-ofac, synth."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .gate import evaluate
from .lists import ListError, parse_ofac
from .model import TransferError
from .policy import RANK, PolicyError, load_policy
from .sim import compare, load_transfers, run, summarize, summary_md
from .synth import dumps, generate

NOTE = "Engineering checklist, not legal advice. Tested on synthetic data only."


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kytgate", description="Policy-as-code gate for token transfers.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="decide each transfer in a JSON Lines file")
    c.add_argument("transfers")
    c.add_argument("--policy", required=True)
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("simulate", help="replay transfers under a policy, optionally against a second one")
    s.add_argument("transfers")
    s.add_argument("--policy", required=True)
    s.add_argument("--compare")
    s.add_argument("--show", type=int, default=20, help="changed decisions to list")
    o = sub.add_parser(
        "import-ofac", help="extract digital currency addresses from OFAC SDN.CSV you downloaded"
    )
    o.add_argument("sdn_csv")
    o.add_argument("--comments", help="SDN_COMMENTS.CSV from the same publication")
    o.add_argument("--as-of", required=True, help="publication date of the files, YYYY-MM-DD")
    o.add_argument("--out", required=True)
    g = sub.add_parser("synth", help="write labelled synthetic transfers")
    g.add_argument("--out", required=True)
    g.add_argument("-n", type=int, default=1000)
    g.add_argument("--seed", type=int, default=7)
    a = p.parse_args(argv)
    try:
        if a.cmd == "synth":
            Path(a.out).write_text(dumps(generate(a.n, a.seed)), encoding="utf-8")
            print(f"wrote {a.n} synthetic transfers to {a.out}")
            return 0
        if a.cmd == "import-ofac":
            comments = Path(a.comments).read_text(encoding="utf-8", errors="replace") if a.comments else None
            imp = parse_ofac(Path(a.sdn_csv).read_text(encoding="utf-8", errors="replace"), comments)
            doc = {
                "name": "OFAC SDN digital currency addresses",
                "source": "OFAC SDN.CSV"
                + (" and SDN_COMMENTS.CSV" if comments else "")
                + ", downloaded by the user",
                "as_of": a.as_of,
                "entries": imp.entries,
            }
            Path(a.out).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
            print(f"{len(imp.entries)} addresses written to {a.out}")
            if imp.truncated_without_comments:
                print(
                    f"warning: {len(imp.truncated_without_comments)} entries hit the 1,000-character "
                    "remarks limit and no SDN_COMMENTS.CSV was given; addresses past the limit are missing",
                    file=sys.stderr,
                )
                return 3
            return 0
        pol = load_policy(a.policy)
        transfers = load_transfers(a.transfers)
        if a.cmd == "check":
            worst = "allow"
            for t in transfers:
                d = evaluate(t, pol)
                worst = max(worst, d.action, key=lambda x: RANK[x])
                if a.json:
                    print(
                        json.dumps(
                            {
                                "id": d.transfer_id,
                                "action": d.action,
                                "policy": d.policy,
                                "findings": [f.__dict__ for f in d.findings],
                            }
                        )
                    )
                else:
                    print(f"{d.transfer_id}: {d.action}")
                    for f in d.findings:
                        print(
                            f"  {f.rule} -> {f.action}: {f.detail}" + (f" [{f.source}]" if f.source else "")
                        )
            if not a.json:
                print(NOTE)
            return 0 if worst == "allow" else 2
        da = run(transfers, pol)
        print(summary_md(summarize(transfers, da)))
        if a.compare:
            pb = load_policy(a.compare)
            db = run(transfers, pb)
            print(summary_md(summarize(transfers, db)))
            changes = compare(transfers, da, db)
            print(
                f"{len(changes)} decisions change from {da[0].policy if da else ''} "
                f"to {db[0].policy if db else ''}:"
            )
            for ch in changes[: a.show]:
                extra = (" +" + ",".join(ch.rules_added)) if ch.rules_added else ""
                extra += (" -" + ",".join(ch.rules_removed)) if ch.rules_removed else ""
                print(f"- {ch.transfer_id} ({ch.label or 'unlabelled'}): {ch.before} -> {ch.after}{extra}")
        print(NOTE)
        return 0
    except (OSError, PolicyError, ListError, TransferError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
