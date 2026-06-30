#!/usr/bin/env python3
"""Structure-first visual triage wrapper for preview comparisons."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_visual_compare(args: argparse.Namespace) -> dict[str, object] | None:
    if not args.baseline or not args.candidate:
        return None
    script = Path(__file__).resolve().parent / "visual_compare.py"
    if not script.exists():
        return None
    tmp_report = args.pixel_report or (args.report.with_suffix(".pixel.json") if args.report else None)
    if tmp_report is None:
        return None
    cmd = [
        sys.executable,
        str(script),
        "--baseline",
        str(args.baseline),
        "--candidate",
        str(args.candidate),
        "--mode",
        args.mode,
        "--report",
        str(tmp_report),
    ]
    if args.diff:
        cmd.extend(["--diff", str(args.diff)])
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    pixel: dict[str, object] = {"returncode": proc.returncode, "stdout": proc.stdout}
    if tmp_report.exists():
        try:
            pixel.update(json.loads(tmp_report.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return pixel


def load_structure(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def decide(structure: dict[str, object] | None, pixel: dict[str, object] | None) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if structure:
        if structure.get("status") == "fail":
            reasons.append("structure validation failed")
            return "fail", reasons
        reasons.append("structure validation passed")
    if not pixel:
        return ("pass" if structure and structure.get("status") == "pass" else "manual_review"), reasons
    pixel_status = str(pixel.get("status", "unknown"))
    changed_ratio = float(pixel.get("changed_ratio", 0) or 0)
    mean_delta = float(pixel.get("mean_delta", 0) or 0)
    if pixel_status == "pass":
        reasons.append("pixel triage passed")
        return "pass", reasons
    if structure and structure.get("status") == "pass":
        reasons.append(
            "pixel triage differed, but structure passed; treat as manual review unless text, shapes, colors, clipping, or layout are materially wrong"
        )
        if changed_ratio < 0.28 and mean_delta < 45:
            return "manual_review", reasons
    reasons.append(f"pixel triage status={pixel_status}")
    return "manual_review", reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structure-report", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--mode", default="stage2-vsdx")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--pixel-report", type=Path)
    parser.add_argument("--diff", type=Path)
    args = parser.parse_args()

    structure = load_structure(args.structure_report)
    pixel = run_visual_compare(args)
    status, reasons = decide(structure, pixel)
    result = {"status": status, "reasons": reasons, "structure": structure, "pixel": pixel}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
