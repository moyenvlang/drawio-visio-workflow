#!/usr/bin/env python3
"""Manage scratch directories under out/.tmp."""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path


def create_scratch(out_dir: Path, run_id: str | None = None) -> Path:
    run = run_id or time.strftime("%Y%m%d-%H%M%S")
    target = out_dir / ".tmp" / run
    target.mkdir(parents=True, exist_ok=False)
    return target


def cleanup_scratch(path: Path) -> None:
    resolved = path.resolve()
    if ".tmp" not in resolved.parts:
        raise SystemExit(f"refusing to remove non-scratch path: {path}")
    if resolved.exists():
        shutil.rmtree(resolved)
    parent = resolved.parent
    if parent.name == ".tmp" and parent.exists() and not any(parent.iterdir()):
        parent.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create", help="create an out/.tmp/<run-id> directory")
    create.add_argument("--out-dir", type=Path, default=Path("out"))
    create.add_argument("--run-id")

    clean = sub.add_parser("clean", help="remove a scratch directory")
    clean.add_argument("path", type=Path)

    args = parser.parse_args()
    if args.cmd == "create":
        print(create_scratch(args.out_dir, args.run_id))
    elif args.cmd == "clean":
        cleanup_scratch(args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
