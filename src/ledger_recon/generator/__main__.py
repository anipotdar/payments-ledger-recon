"""CLI.

python -m ledger_recon.generator generate --out data
python -m ledger_recon.generator release --data data --through 2026-10-07
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ledger_recon.generator.config import GeneratorConfig
from ledger_recon.generator.run import generate, release


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ledger-gen")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write landing files and ground truth")
    g.add_argument("--out", type=Path, default=Path("data"))
    g.add_argument("--seed", type=int, default=GeneratorConfig.seed)
    g.add_argument("--start", type=date.fromisoformat, default=GeneratorConfig.start_date)
    g.add_argument("--days", type=int, default=GeneratorConfig.days)
    g.add_argument("--merchants", type=int, default=GeneratorConfig.merchants)
    g.add_argument("--payments-per-day", type=int, default=GeneratorConfig.payments_per_day)

    r = sub.add_parser("release", help="copy partitions up to a date into the inbox")
    r.add_argument("--data", type=Path, default=Path("data"))
    r.add_argument("--through", type=date.fromisoformat, required=True)
    r.add_argument("--inbox", type=Path, default=None)

    args = parser.parse_args(argv)

    if args.cmd == "generate":
        cfg = GeneratorConfig(
            seed=args.seed,
            start_date=args.start,
            days=args.days,
            merchants=args.merchants,
            payments_per_day=args.payments_per_day,
        )
        manifest = generate(cfg, args.out)
        print(json.dumps({"rows": manifest["rows"], "defects": manifest["defects"]}, indent=2))
        return 0

    copied = release(args.data, args.through, args.inbox)
    print(f"released {len(copied)} new files through {args.through}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
