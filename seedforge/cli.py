"""Command-line interface for SEEDFORGE.

Subcommands:
  gen     Generate synthetic data from a schema JSON file.
  verify  Generate, then assert referential integrity (FKs resolve).

Global:
  --version
  --format {table,json}
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List, Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import Schema, Generator, SeedForgeError, verify_integrity


def _load_schema(path: str) -> Schema:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise SeedForgeError(f"schema file not found: {path}")
    except json.JSONDecodeError as e:
        raise SeedForgeError(f"invalid JSON in {path}: {e}")
    return Schema.from_dict(data)


def _print_table(data: Dict[str, List[dict]]) -> None:
    for tname, rows in data.items():
        print(f"# {tname} ({len(rows)} rows)")
        if not rows:
            print("  (empty)")
            print()
            continue
        cols = list(rows[0].keys())
        widths = {c: len(c) for c in cols}
        for r in rows:
            for c in cols:
                widths[c] = max(widths[c], len(str(r.get(c, ""))))
        header = "  ".join(c.ljust(widths[c]) for c in cols)
        print("  " + header)
        print("  " + "  ".join("-" * widths[c] for c in cols))
        for r in rows:
            print("  " + "  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))
        print()


def _cmd_gen(args: argparse.Namespace) -> int:
    schema = _load_schema(args.schema)
    data = Generator(schema, seed=args.seed).generate()
    if args.format == "json":
        print(json.dumps(data, indent=2, default=str))
    else:
        _print_table(data)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    schema = _load_schema(args.schema)
    data = Generator(schema, seed=args.seed).generate()
    problems = verify_integrity(schema, data)
    total = sum(len(v) for v in data.values())
    report = {
        "ok": not problems,
        "tables": {k: len(v) for k, v in data.items()},
        "total_rows": total,
        "broken_refs": problems,
    }
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        status = "OK" if report["ok"] else "FAILED"
        print(f"integrity: {status}")
        for k, v in report["tables"].items():
            print(f"  {k}: {v} rows")
        print(f"  total: {total} rows")
        for p in problems:
            print(f"  BROKEN: {p}")
    return 0 if report["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Synthetic test-data generator with referential integrity.",
    )
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument("--format", choices=["table", "json"], default="table",
                   help="output format (default: table)")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("gen", help="generate synthetic data from a schema")
    g.add_argument("schema", help="path to schema JSON file")
    g.add_argument("--seed", type=int, default=0, help="master seed (default: 0)")
    g.set_defaults(func=_cmd_gen)

    v = sub.add_parser("verify", help="generate and verify referential integrity")
    v.add_argument("schema", help="path to schema JSON file")
    v.add_argument("--seed", type=int, default=0, help="master seed (default: 0)")
    v.set_defaults(func=_cmd_verify)
    return p


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SeedForgeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
