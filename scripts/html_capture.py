#!/usr/bin/env python3
"""Capture HTML diagram containers with Python Playwright Chromium."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def file_url(path: Path) -> str:
    return path.resolve().as_uri()


def capture(
    html: Path,
    selector: str,
    out_dir: Path,
    stem: str,
    width: int,
    scale: float,
    wait_ms: int,
) -> list[Path]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "Python Playwright is required for HTML screenshots. "
            "Install with: python -m pip install playwright && python -m playwright install chromium"
        ) from exc

    if not html.exists():
        raise SystemExit(f"missing HTML file: {html}")
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    manifest: list[dict[str, object]] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": 1200}, device_scale_factor=scale)
            page.goto(file_url(html), wait_until="load")
            page.wait_for_timeout(wait_ms)
            page.evaluate("document.fonts ? document.fonts.ready : Promise.resolve()")
            count = page.locator(selector).count()
            if count == 0:
                raise SystemExit(f"selector matched no elements: {selector}")
            for index in range(count):
                locator = page.locator(selector).nth(index)
                locator.wait_for(state="visible")
                output = out_dir / f"{stem}.html-page{index + 1}.png"
                locator.screenshot(path=str(output))
                outputs.append(output)
                manifest.append({"page": index + 1, "selector": selector, "output": str(output)})
                print(output)
            browser.close()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "HTML screenshot capture failed. Continue conversion only if you accept that "
            f"HTML-to-drawio visual fidelity is less certain. Cause: {exc}"
        ) from exc
    (out_dir / f"{stem}.html-capture.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--selector", default=".figure", help="CSS selector to capture once per matched element")
    parser.add_argument("--out", type=Path, default=None, help="output directory; defaults to out beside the HTML file")
    parser.add_argument("--stem", help="output filename stem; defaults to HTML stem")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--scale", type=float, default=1)
    parser.add_argument("--wait-ms", type=int, default=250)
    args = parser.parse_args()

    out_dir = args.out or args.html.parent / "out"
    stem = args.stem or args.html.stem
    outputs = capture(args.html, args.selector, out_dir, stem, args.width, args.scale, args.wait_ms)
    print(f"captured HTML screenshots: {len(outputs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
