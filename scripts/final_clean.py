#!/usr/bin/env python3
"""Remove non-deliverable files from an out/ directory by stem whitelist."""

from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path


EVIDENCE_KEEP_PATTERNS = (
    "{stem}.vsdx",
    "{stem}.drawio",
    "{stem}.worklist.md",
    "{stem}.worklist.json",
    "{stem}.drawio-page*.png",
    "{stem}.visio-page*.png",
    "{stem}.drawio-preview.png",
    "{stem}.visio-preview.png",
)

DELIVERABLE_KEEP_PATTERNS = (
    "{stem}.vsdx",
    "{stem}.drawio",
)


def matches_any(name: str, patterns: tuple[str, ...], stem: str) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern.format(stem=stem)) for pattern in patterns)


def scan(out_dir: Path, stem: str, patterns: tuple[str, ...]) -> tuple[list[Path], list[Path]]:
    if not out_dir.exists():
        raise SystemExit(f"missing out directory: {out_dir}")
    if not out_dir.is_dir():
        raise SystemExit(f"not a directory: {out_dir}")

    keep: list[Path] = []
    remove: list[Path] = []
    for path in sorted(out_dir.iterdir(), key=lambda item: item.name):
        if path.is_dir():
            continue
        if matches_any(path.name, patterns, stem):
            keep.append(path)
        else:
            remove.append(path)
    return keep, remove


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--stem", required=True)
    parser.add_argument(
        "--deliverables-only",
        action="store_true",
        help="compatibility no-op; deliverables-only cleanup is the default",
    )
    parser.add_argument(
        "--keep-evidence",
        action="store_true",
        help="also keep root-level worklist and preview evidence; use only for debugging or failed runs",
    )
    parser.add_argument("--apply", action="store_true", help="delete non-whitelisted files; default is dry-run")
    args = parser.parse_args()

    patterns = EVIDENCE_KEEP_PATTERNS if args.keep_evidence else DELIVERABLE_KEEP_PATTERNS
    keep, remove = scan(args.out_dir, args.stem, patterns)
    print(f"final-clean: out_dir={args.out_dir} stem={args.stem}")
    print("scope: all root files")
    print("mode: evidence-retaining" if args.keep_evidence else "mode: deliverables-only")
    print("keep:")
    for path in keep:
        print(f"  {path}")
    print("remove:")
    for path in remove:
        print(f"  {path}")

    if args.apply:
        for path in remove:
            path.unlink()
        print(f"deleted: {len(remove)}")
    else:
        print(f"dry-run: would delete {len(remove)} file(s); pass --apply to delete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
