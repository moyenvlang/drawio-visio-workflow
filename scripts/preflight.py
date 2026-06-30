#!/usr/bin/env python3
"""Check local dependencies before draw.io to Visio conversion."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


REQUIRED_DRAWIO_VERSION = "26.0.16"


@dataclass
class Check:
    name: str
    status: str
    message: str
    impact: str = ""
    fix: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "impact": self.impact,
            "fix": self.fix,
        }


def run(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        timeout=timeout,
        check=False,
    )


def is_windows_or_wsl() -> bool:
    return os.name == "nt" or shutil.which("powershell.exe") is not None


def windows_ps(script: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return run(["powershell.exe", "-NoProfile", "-Command", script], timeout=timeout)


def drawio_candidates() -> list[str]:
    candidates: list[str] = []
    if is_windows_or_wsl():
        candidates.extend(
            [
                r"C:\Program Files\draw.io\draw.io.exe",
                r"C:\Program Files (x86)\draw.io\draw.io.exe",
            ]
        )
    for name in ("drawio", "draw.io"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    unique: list[str] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def path_exists(path: str) -> bool:
    if "\\" in path or ":" in path:
        if not is_windows_or_wsl():
            return False
        proc = windows_ps(f'Test-Path "{path}"', timeout=10)
        return proc.stdout.strip().endswith("True")
    return Path(path).exists() or shutil.which(path) is not None


def version_for(path: str) -> str | None:
    try:
        if "\\" in path or path.endswith(".exe"):
            proc = windows_ps(f'& "{path}" --version', timeout=20)
        else:
            proc = run([path, "--version"], timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped and any(ch.isdigit() for ch in stripped):
            return stripped
    return None


def check_drawio() -> Check:
    seen: list[tuple[str, str | None]] = []
    for candidate in drawio_candidates():
        if not path_exists(candidate):
            continue
        version = version_for(candidate)
        seen.append((candidate, version))
        if version == REQUIRED_DRAWIO_VERSION:
            return Check("drawio", "ok", f"draw.io {version} found", fix=candidate)
    if seen:
        found = ", ".join(f"{path} ({version or 'unknown'})" for path, version in seen)
        return Check(
            "drawio",
            "blocking",
            f"draw.io {REQUIRED_DRAWIO_VERSION} not found; found {found}",
            "Cannot reliably export final VSDX. Some newer draw.io builds may write invalid .vsdx output.",
            "Install or switch to draw.io Desktop 26.0.16.",
        )
    return Check(
        "drawio",
        "blocking",
        f"draw.io {REQUIRED_DRAWIO_VERSION} not found",
        "Cannot reliably export final VSDX.",
        "Install draw.io Desktop 26.0.16.",
    )


def check_visio_com() -> Check:
    if not is_windows_or_wsl():
        return Check(
            "visio_com",
            "degraded",
            "Microsoft Visio COM is only available on Windows",
            "VSDX can be generated, but true Visio preview validation cannot be completed.",
            "Run on Windows with Microsoft Visio Desktop installed for full validation.",
        )
    script = """
$ErrorActionPreference = 'Stop'
$visio = New-Object -ComObject Visio.Application
$visio.Visible = $false
$visio.Quit()
Write-Output 'ok'
"""
    try:
        proc = windows_ps(script, timeout=30)
    except subprocess.TimeoutExpired:
        return Check(
            "visio_com",
            "degraded",
            "Visio COM check timed out",
            "VSDX can be generated, but true Visio preview validation cannot be completed.",
            "Install or repair Microsoft Visio Desktop.",
        )
    if proc.returncode == 0 and "ok" in proc.stdout:
        return Check("visio_com", "ok", "Visio COM is available")
    return Check(
        "visio_com",
        "degraded",
        "Visio COM is unavailable",
        "VSDX can be generated, but actual Microsoft Visio rendering is not verified.",
        "Install or repair Microsoft Visio Desktop.",
    )


def check_playwright_chromium() -> Check:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return Check(
            "html_capture",
            "degraded",
            f"Python Playwright is unavailable: {exc}",
            "HTML source screenshots cannot be captured automatically; visual fidelity may be less certain.",
            "Run: python -m pip install playwright && python -m playwright install chromium",
        )
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 800, "height": 600}, device_scale_factor=1)
            page.set_content("<html><body>ok</body></html>")
            browser.close()
        return Check("html_capture", "ok", "Python Playwright Chromium is available")
    except Exception as exc:  # noqa: BLE001
        return Check(
            "html_capture",
            "degraded",
            f"Python Playwright Chromium cannot start: {exc}",
            "HTML source screenshots cannot be captured automatically; visual fidelity may be less certain.",
            "Run: python -m playwright install chromium. On Linux/WSL also run: python -m playwright install-deps chromium",
        )


def check_output_dir(path: Path) -> Check:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="preflight-", dir=path, delete=True) as fh:
            fh.write(b"ok")
        return Check("output_dir", "ok", f"output directory is writable: {path}")
    except Exception as exc:  # noqa: BLE001
        return Check(
            "output_dir",
            "blocking",
            f"output directory is not writable: {path}: {exc}",
            "Converted files cannot be written.",
            "Choose a writable source/output directory.",
        )


def check_chinese_path(path: Path) -> Check:
    try:
        path.mkdir(parents=True, exist_ok=True)
        target = path / "中文路径测试.txt"
        target.write_text("ok", encoding="utf-8")
        ok = target.read_text(encoding="utf-8") == "ok"
        target.unlink(missing_ok=True)
        if ok:
            return Check("chinese_path", "ok", "Chinese path filesystem read/write works")
    except Exception as exc:  # noqa: BLE001
        return Check(
            "chinese_path",
            "warning",
            f"Chinese path test failed: {exc}",
            "Files may still generate, but logs or external tools may be less reliable with non-ASCII paths.",
            "Use an ASCII temporary stem if external tools fail.",
        )
    return Check("chinese_path", "warning", "Chinese path test did not round-trip cleanly")


def check_powershell_encoding() -> Check:
    if not shutil.which("powershell.exe"):
        return Check("powershell_encoding", "warning", "PowerShell is not available", "Windows COM checks are unavailable.")
    proc = windows_ps("[Console]::OutputEncoding.WebName; Write-Output '中文路径'", timeout=10)
    if proc.returncode == 0 and "中文路径" in proc.stdout:
        return Check("powershell_encoding", "ok", "PowerShell UTF-8 output appears usable")
    return Check(
        "powershell_encoding",
        "warning",
        "PowerShell output may garble Chinese paths",
        "Generated files may still be correct; validate by file existence and format, not console path text.",
    )


def build_result(out_dir: Path) -> dict[str, object]:
    checks = [
        check_drawio(),
        check_visio_com(),
        check_playwright_chromium(),
        check_output_dir(out_dir),
        check_chinese_path(out_dir),
        check_powershell_encoding(),
    ]
    blocking = [check for check in checks if check.status == "blocking"]
    degraded = [check for check in checks if check.status == "degraded"]
    warnings = [check for check in checks if check.status == "warning"]
    if blocking:
        status = "blocking"
    elif degraded:
        status = "degraded"
    elif warnings:
        status = "warning"
    else:
        status = "ok"
    return {
        "status": status,
        "checks": [check.as_dict() for check in checks],
        "blocking": [check.as_dict() for check in blocking],
        "degraded": [check.as_dict() for check in degraded],
        "warnings": [check.as_dict() for check in warnings],
    }


def print_human(result: dict[str, object]) -> None:
    print(f"preflight: {result['status']}")
    for check in result["checks"]:  # type: ignore[index]
        item = check  # type: ignore[assignment]
        print(f"- {item['name']}: {item['status']} - {item['message']}")
    blocking = result["blocking"]  # type: ignore[assignment]
    degraded = result["degraded"]  # type: ignore[assignment]
    if blocking or degraded:
        print("")
        print("Environment is incomplete.")
        if blocking:
            print("Blocking:")
            for item in blocking:
                print(f"- {item['name']}: {item['impact']}")
        if degraded:
            print("Can continue with reduced validation:")
            for item in degraded:
                print(f"- {item['name']}: {item['impact']}")
        print("")
        print("Options:")
        print("1. Fix the environment and rerun.")
        print("2. Continue conversion, accepting that fidelity may be affected.")
        print("3. Stop.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--json", action="store_true", help="print JSON only")
    parser.add_argument("--strict", action="store_true", help="return non-zero for degraded or warning checks")
    parser.add_argument("--continue-with-risk", action="store_true", help="return success for degraded checks but not blocking checks")
    args = parser.parse_args()

    result = build_result(args.out_dir)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result)

    status = result["status"]
    if status == "blocking":
        return 1
    if args.strict and status != "ok":
        return 1
    if status == "degraded" and not args.continue_with_risk:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
