#!/usr/bin/env python3
"""Manage draw.io 26.0.16 preview, VSDX export, and round-trip checks."""

from __future__ import annotations

import argparse
import base64
from html import unescape
from html.parser import HTMLParser
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET
import zlib


REQUIRED_VERSION = "26.0.16"
REQUIRED_VSDX_ENTRIES = ("[Content_Types].xml", "visio/document.xml", "visio/pages/page1.xml")
HIGH_RISK_HTML_MARKERS = ("<b>", "<font", "<br", "color:white", "display:none", "visibility:hidden")
VSDX_COLOR_CELL_NAMES = {
    "Color",
    "FillForegnd",
    "FillBkgnd",
    "LineColor",
    "ShdwForegnd",
    "TextBkgnd",
    "QuickStyleLineColor",
    "QuickStyleFillColor",
    "QuickStyleShadowColor",
    "QuickStyleFontColor",
    "GradientStopColor",
    "GlowColor",
    "BevelDepthColor",
    "BevelContourColor",
}
HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{6})$")


OVERLAY_LABEL_RE = re.compile(
    r"<font[^>]*color\s*:\s*white[^>]*>\s*<b>(?P<overlay>.*?)</b>\s*</font>\s*<br\s*/?>\s*"
    r"<b>(?P<title>.*?)</b>\s*<br\s*/?>\s*"
    r"<font[^>]*?(?:font-size\s*:\s*(?P<desc_size>\d+)px)?[^>]*?(?:color\s*:\s*(?P<desc_color>#[0-9a-fA-F]{6}))?[^>]*>(?P<desc>.*?)</font>",
    re.IGNORECASE | re.DOTALL,
)
TITLE_DESC_RE = re.compile(
    r"^\s*<b>(?P<title>.*?)</b>\s*<br\s*/?>\s*"
    r"<font[^>]*?(?:font-size\s*:\s*(?P<desc_size>\d+)px)?[^>]*?(?:color\s*:\s*(?P<desc_color>#[0-9a-fA-F]{6}))?[^>]*>(?P<desc>.*?)</font>\s*$",
    re.IGNORECASE | re.DOTALL,
)


def is_native_windows() -> bool:
    return os.name == "nt"


def is_wsl() -> bool:
    if is_native_windows():
        return False
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return "microsoft" in release or "wsl" in release


def is_windows() -> bool:
    return is_native_windows() or (is_wsl() and shutil.which("powershell.exe") is not None)


def auto_install_supported() -> bool:
    return is_native_windows() or (is_wsl() and shutil.which("powershell.exe") is not None)


def manual_install_message() -> str:
    return (
        f"draw.io Desktop {REQUIRED_VERSION} not found. Automatic install is supported only for "
        "native Windows Python or WSL with powershell.exe and winget. Install manually, or run on "
        "Windows: winget install --id JGraph.Draw --exact --version 26.0.16 "
        "--accept-package-agreements --accept-source-agreements --silent --force"
    )


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def windows_ps(script: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["powershell.exe", "-NoProfile", "-Command", script], check=check)


def ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def to_windows_path(path: Path) -> str:
    absolute = str(path.absolute())
    match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", absolute)
    if match:
        drive = match.group(1).upper()
        rest = match.group(2).replace("/", "\\")
        return f"{drive}:\\{rest}"
    if absolute.startswith("/") and shutil.which("wslpath"):
        proc = run(["wslpath", "-w", absolute], check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    return absolute


def version_for(exe: str) -> str | None:
    try:
        if exe.endswith(".exe") or "\\" in exe:
            if is_windows():
                out = windows_ps(f'& "{exe}" --version', check=False).stdout
            else:
                out = run([exe, "--version"], check=False).stdout
        else:
            out = run([exe, "--version"], check=False).stdout
    except OSError:
        return None
    for line in out.splitlines():
        line = line.strip()
        if line and any(ch.isdigit() for ch in line):
            return line
    return None


def candidate_paths() -> list[str]:
    paths: list[str] = []
    if is_windows():
        paths.extend(
            [
                r"C:\Program Files\draw.io\draw.io.exe",
                r"C:\Program Files (x86)\draw.io\draw.io.exe",
            ]
        )
        local = os.environ.get("LOCALAPPDATA")
        if local:
            paths.append(str(Path(local) / "Programs" / "draw.io" / "draw.io.exe"))
    for name in ("drawio", "draw.io"):
        resolved = shutil.which(name)
        if resolved:
            paths.append(resolved)
    unique = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def find_drawio(required: bool = True) -> tuple[str, str] | None:
    for path in candidate_paths():
        if "\\" in path:
            exists = windows_ps(f'Test-Path "{path}"', check=False).stdout.strip().endswith("True")
            if not exists:
                continue
        elif not Path(path).exists() and shutil.which(path) is None:
            continue
        version = version_for(path)
        if version == REQUIRED_VERSION:
            return path, version
    if required:
        raise SystemExit(f"draw.io Desktop {REQUIRED_VERSION} not found")
    return None


def install_windows() -> None:
    if not auto_install_supported():
        raise SystemExit(manual_install_message())
    try:
        check = windows_ps("winget --version", check=False)
    except OSError as exc:
        raise SystemExit(f"PowerShell is not available; {manual_install_message()}") from exc
    if check.returncode != 0:
        raise SystemExit(
            f"winget is not available; install draw.io Desktop {REQUIRED_VERSION} manually, "
            "or rerun from native Windows/WSL after winget is available"
        )
    cmd = (
        "winget install --id JGraph.Draw --exact --version 26.0.16 "
        "--accept-package-agreements --accept-source-agreements --silent --force"
    )
    proc = windows_ps(cmd, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def ensure(install: bool = True) -> tuple[str, str]:
    found = find_drawio(required=False)
    if found:
        print(f"ok: {found[0]} ({found[1]})")
        return found
    if not install:
        raise SystemExit(f"draw.io Desktop {REQUIRED_VERSION} not found (--no-install)")
    install_windows()
    found = find_drawio(required=False)
    if not found:
        raise SystemExit(f"installed, but draw.io Desktop {REQUIRED_VERSION} was not found")
    print(f"ok: {found[0]} ({found[1]})")
    return found


def export_with_drawio(
    input_file: Path,
    output_file: Path,
    fmt: str,
    width: int | None = None,
    page_index: int | None = None,
    install: bool = True,
) -> None:
    exe, version = ensure(install=install)
    if is_windows() and "\\" in exe:
        script_parts = ["&", ps_single_quote(exe), "-x", "-f", ps_single_quote(fmt)]
        if width and fmt.lower() == "png":
            script_parts.extend(["--width", str(width)])
        if page_index is not None:
            script_parts.extend(["-p", str(page_index)])
        script_parts.extend(
            [
                "-o",
                ps_single_quote(to_windows_path(output_file)),
                ps_single_quote(to_windows_path(input_file)),
            ]
        )
        script = " ".join(script_parts)
        proc = windows_ps(script, check=False)
    else:
        cmd = [exe, "-x", "-f", fmt]
        if width and fmt.lower() == "png":
            cmd.extend(["--width", str(width)])
        if page_index is not None:
            cmd.extend(["-p", str(page_index)])
        cmd.extend(["-o", str(output_file), str(input_file)])
        proc = run(cmd, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    if not output_file.exists():
        raise SystemExit(f"output was not created: {output_file}")
    print(f"draw.io {version}: {output_file}")


def export_with_visio(vsdx_file: Path, output_file: Path, page: int = 1) -> None:
    if page < 1:
        raise SystemExit("--page must be 1 or greater")
    if not is_windows():
        raise SystemExit("Visio COM preview requires Windows with Microsoft Visio Desktop installed")
    if not vsdx_file.exists():
        raise SystemExit(f"missing file: {vsdx_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    input_path = ps_single_quote(to_windows_path(vsdx_file))
    output_path = ps_single_quote(to_windows_path(output_file))
    script = f"""
$ErrorActionPreference = 'Stop'
$inputPath = {input_path}
$outputPath = {output_path}
$visio = New-Object -ComObject Visio.Application
$visio.Visible = $false
try {{
    $doc = $visio.Documents.Open($inputPath)
    try {{
        $page = $doc.Pages.Item({page})
        $page.Export($outputPath)
    }} finally {{
        $doc.Saved = $true
        $doc.Close()
    }}
}} finally {{
    $visio.Quit()
}}
Write-Output "ok:visio-preview page={page}"
"""
    proc = windows_ps(script, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    if not output_file.exists():
        raise SystemExit(f"Visio preview was not created: {output_file}")
    print(f"Visio Desktop COM: {output_file}")


def export_all_with_visio(vsdx_file: Path, out_dir: Path, stem: str) -> list[Path]:
    if not is_windows():
        raise SystemExit("Visio COM preview requires Windows with Microsoft Visio Desktop installed")
    if not vsdx_file.exists():
        raise SystemExit(f"missing file: {vsdx_file}")
    out_dir.mkdir(parents=True, exist_ok=True)
    input_path = ps_single_quote(to_windows_path(vsdx_file))
    output_dir = ps_single_quote(to_windows_path(out_dir))
    stem_value = ps_single_quote(stem)
    script = f"""
$ErrorActionPreference = 'Stop'
$inputPath = {input_path}
$outputDir = {output_dir}
$stem = {stem_value}
$visio = New-Object -ComObject Visio.Application
$visio.Visible = $false
try {{
    $doc = $visio.Documents.Open($inputPath)
    try {{
        for ($i = 1; $i -le $doc.Pages.Count; $i++) {{
            $target = Join-Path $outputDir ("$stem.visio-page$i.png")
            $doc.Pages.Item($i).Export($target)
            Write-Output ("ok:visio-preview-page " + $i)
        }}
        Write-Output ("pages=" + $doc.Pages.Count)
    }} finally {{
        $doc.Saved = $true
        $doc.Close()
    }}
}} finally {{
    $visio.Quit()
}}
"""
    proc = windows_ps(script, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    match = re.search(r"pages=(\d+)", proc.stdout)
    if not match:
        raise SystemExit("Visio preview page count was not reported")
    count = int(match.group(1))
    outputs = [out_dir / f"{stem}.visio-page{idx}.png" for idx in range(1, count + 1)]
    missing = [path for path in outputs if not path.exists()]
    if missing:
        raise SystemExit("Visio preview was not created: " + ", ".join(str(path) for path in missing))
    for path in outputs:
        print(f"Visio Desktop COM: {path}")
    return outputs


def validate_vsdx(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"missing file: {path}")
    with path.open("rb") as fh:
        header = fh.read(5)
    if header.startswith(b"%PDF"):
        raise SystemExit(f"invalid VSDX: {path} contains PDF bytes")
    try:
        with ZipFile(path) as zf:
            names = set(zf.namelist())
    except BadZipFile as exc:
        raise SystemExit(f"invalid VSDX zip package: {exc}") from exc
    missing = [entry for entry in REQUIRED_VSDX_ENTRIES if entry not in names]
    if missing:
        raise SystemExit(f"invalid VSDX, missing entries: {', '.join(missing)}")
    print(f"ok: {path} is a VSDX package ({path.stat().st_size} bytes)")


def drawio_diagrams(path: Path) -> list[ET.Element]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    diagrams = root.findall("diagram")
    if not diagrams:
        raise SystemExit(f"missing <diagram> pages: {path}")
    return diagrams


def drawio_page_count(path: Path) -> int:
    return len(drawio_diagrams(path))


def drawio_page_names(path: Path) -> list[str]:
    names: list[str] = []
    for idx, diagram in enumerate(drawio_diagrams(path), 1):
        names.append(diagram.get("name") or f"Page {idx}")
    return names


class FigureIndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.figures: list[dict[str, str]] = []
        self.stack: list[dict[str, object]] = []

    @staticmethod
    def attr_map(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    @staticmethod
    def has_class(attrs: dict[str, str], name: str) -> bool:
        return name in (attrs.get("class") or "").split()

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = self.attr_map(attrs_list)
        current = self.stack[-1] if self.stack else None
        if self.has_class(attrs, "figure"):
            figure = {"id": attrs.get("id", ""), "title": "", "note": ""}
            self.figures.append(figure)
            self.stack.append({"tag": tag, "figure": figure, "capture": ""})
            return
        if current is not None:
            capture = ""
            if self.has_class(attrs, "figure-title"):
                capture = "title"
            elif self.has_class(attrs, "figure-note"):
                capture = "note"
            self.stack.append({"tag": tag, "figure": current["figure"], "capture": capture})

    def handle_endtag(self, tag: str) -> None:
        for idx in range(len(self.stack) - 1, -1, -1):
            if self.stack[idx].get("tag") == tag:
                del self.stack[idx:]
                return

    def handle_data(self, data: str) -> None:
        if not self.stack:
            return
        current = self.stack[-1]
        capture = current.get("capture")
        if capture not in {"title", "note"}:
            return
        text = " ".join(unescape(data).split())
        if not text:
            return
        figure = current["figure"]
        assert isinstance(figure, dict)
        existing = figure.get(capture, "")
        figure[capture] = f"{existing} {text}".strip() if existing else text


def html_figures(path: Path) -> list[dict[str, str]]:
    parser = FigureIndexParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.figures


def input_manifest_pages(source: Path, drawio: Path | None = None) -> tuple[str, list[dict[str, str]]]:
    suffix = source.suffix.lower()
    pages: list[dict[str, str]] = []
    if suffix in {".html", ".htm"}:
        input_type = "HTML"
        figures = html_figures(source)
        if figures:
            for idx, figure in enumerate(figures, 1):
                pages.append(
                    {
                        "index": str(idx),
                        "source": f"#{figure.get('id')}" if figure.get("id") else f"figure[{idx}]",
                        "title": figure.get("title") or f"Figure {idx}",
                        "note": figure.get("note") or "",
                    }
                )
        else:
            pages.append({"index": "1", "source": "whole document", "title": source.stem, "note": ""})
    elif suffix == ".drawio":
        input_type = "drawio"
        for idx, name in enumerate(drawio_page_names(source), 1):
            pages.append({"index": str(idx), "source": f"diagram[{idx}]", "title": name, "note": ""})
    elif suffix in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}:
        input_type = "image"
        pages.append({"index": "1", "source": source.name, "title": source.stem, "note": ""})
    else:
        input_type = "new/unknown"
        pages.append({"index": "1", "source": source.name, "title": source.stem, "note": ""})
    if drawio is not None and drawio.exists():
        names = drawio_page_names(drawio)
        if len(names) != len(pages):
            for idx, name in enumerate(names, 1):
                if idx <= len(pages):
                    pages[idx - 1]["drawio_title"] = name
                else:
                    pages.append({"index": str(idx), "source": "(no mapped source)", "title": name, "note": "", "drawio_title": name})
        else:
            for idx, name in enumerate(names):
                pages[idx]["drawio_title"] = name
    return input_type, pages


def write_manifest(source: Path, output: Path, drawio: Path | None = None, stem: str | None = None) -> Path:
    input_type, pages = input_manifest_pages(source, drawio)
    output.parent.mkdir(parents=True, exist_ok=True)
    artifact_stem = stem or (drawio.stem if drawio else source.stem)
    lines = [
        "# Conversion Worklist",
        "",
        f"- Source file: `{source}`",
        f"- Input type: `{input_type}`",
        f"- Identified pages: {len(pages)}",
        f"- Draw.io source: `{drawio}`" if drawio else "- Draw.io source: pending",
        "",
        "## Page Map",
        "",
    ]
    for page in pages:
        idx = page["index"]
        title = page.get("title", "")
        lines.extend(
            [
                f"### Page {idx}. {title}",
                "",
                f"- Source node: `{page.get('source', '')}`",
                f"- Draw.io page: `{page.get('drawio_title', f'Page {idx}')}`",
                f"- HTML/source screenshot: `out/{artifact_stem}.html-page{idx}.png`",
                f"- draw.io preview: `out/{artifact_stem}.drawio-page{idx}.png`",
                f"- Visio preview: `out/{artifact_stem}.visio-page{idx}.png`",
            ]
        )
        if "技术架构" in title or any(token in title for token in ("SaaS", "PaaS", "DaaS", "IaaS")):
            lines.append("- Special check: verify SaaS/PaaS/DaaS/IaaS labels do not wrap in Visio.")
        if page.get("note"):
            lines.append(f"- Source note: {page['note']}")
        lines.append("")
    lines.extend(
        [
            "## Required Checks",
            "",
            "- [ ] Original source remains unchanged.",
            "- [ ] `.drawio` encoding validation passed.",
            "- [ ] `audit-drawio` passed.",
            "- [ ] All draw.io page previews were exported.",
            "- [ ] Stage 1 completed per page.",
            "- [ ] VSDX exported with draw.io Desktop 26.0.16.",
            "- [ ] VSDX package validation passed.",
            "- [ ] All Visio COM page previews were exported, or COM unavailability was reported.",
            "- [ ] Stage 2 completed per page.",
            "- [ ] Important text styling was audited where relevant.",
            "- [ ] Scratch files and failed intermediate outputs were removed.",
            "",
            "Automatic visual comparison is triage. A `fail` result requires manual review; it blocks final delivery only when structural drift, missing text, color loss, clipping, or material layout shifts are confirmed.",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return output


def rgb_formula(hex_value: str) -> str:
    value = hex_value.lstrip("#")
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return f"RGB({red},{green},{blue})"


def normalize_vsdx_colors(path: Path, output: Path | None = None) -> int:
    validate_vsdx(path)
    target = output or path
    temp = target.with_suffix(target.suffix + ".tmp")
    ns_uri = "http://schemas.microsoft.com/office/visio/2012/main"
    ns = {"v": ns_uri}
    ET.register_namespace("", ns_uri)
    ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
    changed = 0
    with ZipFile(path, "r") as zin, ZipFile(temp, "w", ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith(".xml") and (info.filename.startswith("visio/pages/") or info.filename == "visio/document.xml"):
                root = ET.fromstring(data)
                for cell in root.findall(".//v:Cell", ns):
                    name = cell.get("N") or ""
                    value = cell.get("V") or ""
                    if name not in VSDX_COLOR_CELL_NAMES or not HEX_COLOR_RE.match(value):
                        continue
                    cell.set("F", rgb_formula(value))
                    # Keep V as the draw.io hex cache value; Visio needs a V value and uses F for reliable RGB interpretation.
                    cell.set("V", value)
                    changed += 1
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(info, data)
    temp.replace(target)
    print(f"normalized VSDX color cells with RGB formulas: {changed}")
    print(f"color-normalized: {target}")
    return changed


def direct_cell(shape: ET.Element, name: str, ns: dict[str, str]) -> ET.Element | None:
    for cell in shape.findall("v:Cell", ns):
        if cell.get("N") == name:
            return cell
    return None


def direct_cell_value(shape: ET.Element, name: str, ns: dict[str, str]) -> str | None:
    cell = direct_cell(shape, name, ns)
    return cell.get("V") if cell is not None else None


def set_direct_cell(shape: ET.Element, name: str, value: str, ns_uri: str) -> None:
    cell = None
    for candidate in shape.findall(f"{{{ns_uri}}}Cell"):
        if candidate.get("N") == name:
            cell = candidate
            break
    if cell is None:
        cell = ET.SubElement(shape, f"{{{ns_uri}}}Cell", {"N": name})
    cell.set("V", value)
    if "F" in cell.attrib:
        del cell.attrib["F"]


def is_vertical_or_special_text(shape: ET.Element, text: str, ns: dict[str, str]) -> bool:
    compact = "".join(text.split())
    line_count = text.count("\n") + text.count("\r")
    if compact and len(compact) <= 8 and line_count >= max(1, len(compact) - 1):
        return True
    if direct_cell(shape, "Angle", ns) is not None:
        return True
    if direct_cell(shape, "BeginX", ns) is not None or direct_cell(shape, "EndX", ns) is not None:
        return True
    return False


def normalize_vsdx_textxform(path: Path, output: Path | None = None) -> int:
    validate_vsdx(path)
    target = output or path
    temp = target.with_suffix(target.suffix + ".tmp")
    ns_uri = "http://schemas.microsoft.com/office/visio/2012/main"
    ns = {"v": ns_uri}
    ET.register_namespace("", ns_uri)
    ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
    changed = 0
    with ZipFile(path, "r") as zin, ZipFile(temp, "w", ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.startswith("visio/pages/page") and info.filename.endswith(".xml"):
                root = ET.fromstring(data)
                for shape in root.findall(".//v:Shape", ns):
                    text_el = shape.find("v:Text", ns)
                    if text_el is None:
                        continue
                    text = "".join(text_el.itertext())
                    if not text.strip() or is_vertical_or_special_text(shape, text, ns):
                        continue
                    width = direct_cell_value(shape, "Width", ns)
                    height = direct_cell_value(shape, "Height", ns)
                    if not width or not height:
                        continue
                    try:
                        width_f = float(width)
                        height_f = float(height)
                    except ValueError:
                        continue
                    if width_f <= 0 or height_f <= 0:
                        continue
                    half_width = f"{width_f / 2:.12g}"
                    half_height = f"{height_f / 2:.12g}"
                    full_width = f"{width_f:.12g}"
                    full_height = f"{height_f:.12g}"
                    desired = {
                        "TxtPinX": half_width,
                        "TxtPinY": half_height,
                        "TxtWidth": full_width,
                        "TxtHeight": full_height,
                        "TxtLocPinX": half_width,
                        "TxtLocPinY": half_height,
                    }
                    before = {key: direct_cell_value(shape, key, ns) for key in desired}
                    if before == desired:
                        continue
                    for key, value in desired.items():
                        set_direct_cell(shape, key, value, ns_uri)
                    changed += 1
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(info, data)
    temp.replace(target)
    print(f"normalized VSDX TextXForm cells: {changed}")
    print(f"textxform-normalized: {target}")
    return changed


def decode_drawio_model(path: Path) -> ET.Element:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    diagram = root.find("diagram")
    if diagram is None or not (diagram.text or "").strip():
        raise SystemExit(f"missing <diagram> payload: {path}")
    payload = (diagram.text or "").strip()
    if "<mxGraphModel" in payload:
        return ET.fromstring(payload)
    if "%" in payload:
        payload = unquote(payload)
    try:
        raw = base64.b64decode(payload, validate=True)
        xml = unquote(zlib.decompress(raw, -15).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"cannot decode draw.io payload: {exc}") from exc
    return ET.fromstring(xml)


def encode_drawio_model(model: ET.Element, output: Path, name: str = "Page-1") -> None:
    model_xml = ET.tostring(model, encoding="unicode", short_empty_elements=True)
    compressor = zlib.compressobj(level=9, wbits=-15)
    payload = base64.b64encode(compressor.compress(quote_xml(model_xml).encode("utf-8")) + compressor.flush()).decode("ascii")
    mxfile = ET.Element("mxfile", {"host": "app.diagrams.net", "version": "24.7.17", "agent": "drawio-visio-workflow"})
    diagram = ET.SubElement(mxfile, "diagram", {"id": "repaired-vsdx", "name": name})
    diagram.text = payload
    ET.indent(mxfile, space="  ")
    output.write_text(ET.tostring(mxfile, encoding="unicode"), encoding="utf-8")


def quote_xml(value: str) -> str:
    from urllib.parse import quote

    return quote(value)


def style_map(style: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in (style or "").split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            result[key] = value
    return result


def parse_style(style: str | None) -> list[tuple[str, str | None]]:
    items: list[tuple[str, str | None]] = []
    for part in (style or "").split(";"):
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            items.append((key, value))
        else:
            items.append((part, None))
    return items


def set_style_value(items: list[tuple[str, str | None]], key: str, value: str) -> None:
    for idx, (item_key, _) in enumerate(items):
        if item_key == key:
            items[idx] = (key, value)
            return
    items.append((key, value))


def style_text(items: list[tuple[str, str | None]]) -> str:
    seen: set[str] = set()
    parts: list[str] = []
    for key, value in items:
        if key in seen:
            continue
        seen.add(key)
        parts.append(key if value is None else f"{key}={value}")
    return ";".join(parts) + ";"


def strip_html_markers(value: str) -> str:
    return (
        value.replace("<br>", "\n")
        .replace("<br/>", "\n")
        .replace("<br />", "\n")
        .replace("&nbsp;", " ")
    )


def html_to_plain(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</p\s*>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    return (
        value.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .strip()
    )


def next_cell_id(existing: set[str], prefix: str = "repair") -> str:
    idx = 1
    while f"{prefix}{idx}" in existing:
        idx += 1
    cid = f"{prefix}{idx}"
    existing.add(cid)
    return cid


def float_attr(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(element.get(name, str(default)) or default)
    except ValueError:
        return default


def add_text_cell(
    root: ET.Element,
    existing: set[str],
    parent: str,
    value: str,
    x: float,
    y: float,
    width: float,
    height: float,
    font_size: str,
    font_color: str,
    bold: bool,
) -> None:
    cid = next_cell_id(existing)
    style = (
        "text;html=1;strokeColor=none;fillColor=none;whiteSpace=wrap;rounded=0;"
        f"fontFamily=Microsoft YaHei;fontSize={font_size};fontColor={font_color};"
        f"fontStyle={'1' if bold else '0'};align=center;verticalAlign=middle;spacing=0;"
    )
    cell = ET.SubElement(root, "mxCell", {"id": cid, "value": value, "style": style, "vertex": "1", "parent": parent})
    ET.SubElement(
        cell,
        "mxGeometry",
        {"x": f"{x:g}", "y": f"{y:g}", "width": f"{width:g}", "height": f"{height:g}", "as": "geometry"},
    )


def is_white_color(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return normalized in {"white", "#fff", "#ffffff", "rgb(255,255,255)", "rgb(255, 255, 255)"}


def is_visible_colored_fill(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return bool(normalized) and normalized not in {"none", "transparent", "#fff", "#ffffff", "white"}


def bbox_contains(outer: ET.Element, inner: ET.Element) -> bool:
    og = outer.find("mxGeometry")
    ig = inner.find("mxGeometry")
    if og is None or ig is None:
        return False
    ox, oy, ow, oh = (float_attr(og, "x"), float_attr(og, "y"), float_attr(og, "width"), float_attr(og, "height"))
    ix, iy, iw, ih = (float_attr(ig, "x"), float_attr(ig, "y"), float_attr(ig, "width"), float_attr(ig, "height"))
    return ox <= ix <= ox + ow and oy <= iy <= oy + oh and ix + iw <= ox + ow and iy + ih <= oy + oh


def repair_drawio(path: Path, output: Path) -> int:
    model = decode_drawio_model(path)
    root = model.find("root")
    if root is None:
        raise SystemExit("mxGraphModel missing <root>")
    existing = {cell.get("id", "") for cell in model.findall(".//mxCell") if cell.get("id")}
    repaired = 0
    color_splits = 0
    skipped = 0
    cells = list(model.findall(".//mxCell"))
    for cell in cells:
        value = cell.get("value") or ""
        if not value or cell.get("vertex") != "1":
            continue
        match = OVERLAY_LABEL_RE.search(value)
        kind = "overlay" if match else ""
        if match is None:
            match = TITLE_DESC_RE.search(value)
            kind = "title-desc" if match else ""
        if match is None:
            continue
        geometry = cell.find("mxGeometry")
        if geometry is None:
            skipped += 1
            continue
        title = html_to_plain(match.group("title"))
        desc = html_to_plain(match.group("desc"))
        if not title:
            skipped += 1
            continue
        parent = cell.get("parent", "1")
        x = float_attr(geometry, "x")
        y = float_attr(geometry, "y")
        width = float_attr(geometry, "width")
        height = float_attr(geometry, "height")
        style = style_map(cell.get("style"))
        title_size = style.get("fontSize", "18" if kind == "overlay" else "20")
        desc_size = match.groupdict().get("desc_size") or "13" if kind == "overlay" else match.groupdict().get("desc_size") or "14"
        desc_color = match.groupdict().get("desc_color") or "#5f6b7a"

        # Remove the risky mixed label from the card/background shape.
        cell.set("value", "")
        items = parse_style(cell.get("style"))
        set_style_value(items, "html", "1")
        set_style_value(items, "whiteSpace", "wrap")
        set_style_value(items, "fontStyle", "0")
        cell.set("style", style_text(items))

        if kind == "overlay":
            # If a separate overlay cell already exists inside the same card, keep it.
            overlay_text = html_to_plain(match.group("overlay"))
            has_overlay = any(
                other is not cell
                and other.get("parent") == parent
                and (other.get("value") or "").strip() == overlay_text
                and bbox_contains(cell, other)
                for other in cells
            )
            if not has_overlay and overlay_text:
                overlay_w = min(44, max(32, width * 0.22))
                overlay_h = min(30, max(24, height * 0.28))
                overlay_style = (
                    "rounded=0;whiteSpace=wrap;html=1;fillColor=#0284c7;strokeColor=#0284c7;"
                    "align=center;verticalAlign=middle;spacing=0;"
                )
                cid = next_cell_id(existing)
                overlay = ET.SubElement(
                    root,
                    "mxCell",
                    {"id": cid, "value": "", "style": overlay_style, "vertex": "1", "parent": parent},
                )
                overlay_x = x + (width - overlay_w) / 2
                overlay_y = y + 12
                ET.SubElement(
                    overlay,
                    "mxGeometry",
                    {
                        "x": f"{overlay_x:g}",
                        "y": f"{overlay_y:g}",
                        "width": f"{overlay_w:g}",
                        "height": f"{overlay_h:g}",
                        "as": "geometry",
                    },
                )
                add_text_cell(root, existing, parent, overlay_text, overlay_x, overlay_y, overlay_w, overlay_h, "17", "#ffffff", True)
            title_y = y + height * 0.42
            desc_y = y + height * 0.66
            add_text_cell(root, existing, parent, title, x + 8, title_y, width - 16, max(20, height * 0.22), title_size, style.get("fontColor", "#223047"), True)
            add_text_cell(root, existing, parent, desc, x + 8, desc_y, width - 16, max(18, height * 0.22), desc_size, desc_color, False)
        else:
            title_y = y + height * 0.24
            desc_y = y + height * 0.52
            add_text_cell(root, existing, parent, title, x + 8, title_y, width - 16, max(22, height * 0.26), title_size, style.get("fontColor", "#223047"), True)
            add_text_cell(root, existing, parent, desc, x + 8, desc_y, width - 16, max(22, height * 0.35), desc_size, desc_color, False)
        repaired += 1

    for cell in list(model.findall(".//mxCell")):
        value = cell.get("value") or ""
        if not value or cell.get("vertex") != "1":
            continue
        style = style_map(cell.get("style"))
        if not (is_visible_colored_fill(style.get("fillColor")) and is_white_color(style.get("fontColor"))):
            continue
        geometry = cell.find("mxGeometry")
        if geometry is None:
            skipped += 1
            continue
        text = html_to_plain(value)
        if not text:
            skipped += 1
            continue
        parent = cell.get("parent", "1")
        x = float_attr(geometry, "x")
        y = float_attr(geometry, "y")
        width = float_attr(geometry, "width")
        height = float_attr(geometry, "height")
        font_size = style.get("fontSize", "16")
        bold = style.get("fontStyle") == "1"

        cell.set("value", "")
        add_text_cell(root, existing, parent, text, x, y, width, height, font_size, "#ffffff", bold)
        color_splits += 1

    encode_drawio_model(model, output, "VSDX-repaired")
    print(f"repaired: {repaired} composite label(s), {color_splits} white-on-color label(s), skipped: {skipped}")
    print(output)
    return 0 if repaired or color_splits else 1


def audit_drawio(path: Path) -> int:
    model = decode_drawio_model(path)
    failures = 0
    warnings = 0
    for cell in model.findall(".//mxCell"):
        value = cell.get("value") or ""
        if not value:
            continue
        lower = value.lower()
        style = style_map(cell.get("style"))
        cid = cell.get("id", "(missing)")
        markers = [marker for marker in HIGH_RISK_HTML_MARKERS if marker in lower]
        has_html_bold = "<b>" in lower or "<strong>" in lower
        has_line_break = "<br" in lower
        has_font = "<font" in lower
        has_hidden_or_white = "color:white" in lower or "display:none" in lower or "visibility:hidden" in lower
        has_font_style = style.get("fontStyle") == "1"
        has_white_on_color_label = (
            cell.get("vertex") == "1"
            and is_visible_colored_fill(style.get("fillColor"))
            and is_white_color(style.get("fontColor"))
            and bool(html_to_plain(value))
        )
        # Treat simple vertical layer labels as lower risk: they use <br> only to stack characters.
        compact = strip_html_markers(value)
        text_chars = [ch for ch in compact if ch.strip() and ch not in "<>/=\"'"]
        likely_vertical_label = has_line_break and not has_html_bold and not has_font and len(text_chars) <= 8
        if has_white_on_color_label:
            failures += 1
            print(f"error: cell {cid} uses filled-shape label color for white-on-color text; split background and text cells: {value[:120]}")
        if has_hidden_or_white:
            failures += 1
            print(f"error: cell {cid} uses white/hidden placeholder-like text in label: {value[:120]}")
        if has_html_bold and not has_font_style:
            failures += 1
            print(f"error: cell {cid} relies on HTML bold without style fontStyle=1: {value[:120]}")
        if (has_font or (has_line_break and not likely_vertical_label)) and markers:
            # This is high-risk when it mixes multiple runs in one label.
            failures += 1
            print(f"error: cell {cid} contains composite/high-risk HTML label markers {markers}: {value[:120]}")
        elif markers:
            warnings += 1
            print(f"warning: cell {cid} contains HTML markers {markers}: {value[:120]}")
    if failures:
        print(f"failed: {failures} high-risk draw.io text structure(s), {warnings} warning(s)")
        return 1
    print(f"ok: {path} passed draw.io pre-export audit ({warnings} warning(s))")
    return 0


def cell_values(row: ET.Element, ns: dict[str, str]) -> dict[str, str]:
    return {cell.get("N", ""): cell.get("V", "") for cell in row.findall("v:Cell", ns)}


def audit_vsdx_text(path: Path, texts: list[str]) -> int:
    validate_vsdx(path)
    ns = {"v": "http://schemas.microsoft.com/office/visio/2012/main"}
    found = 0
    failures = 0
    with ZipFile(path) as zf:
        page_names = sorted(name for name in zf.namelist() if name.startswith("visio/pages/page") and name.endswith(".xml"))
        for page_name in page_names:
            page = ET.fromstring(zf.read(page_name))
            for shape in page.findall(".//v:Shape", ns):
                text_el = shape.find("v:Text", ns)
                if text_el is None:
                    continue
                shape_text = "".join(text_el.itertext())
                compact = "".join(shape_text.split())
                for target in texts:
                    if target not in compact:
                        continue
                    found += 1
                    rows = shape.findall("v:Section[@N='Character']/v:Row", ns)
                    styles = []
                    for row in rows:
                        values = cell_values(row, ns)
                        style = values.get("Style", "")
                        size = values.get("Size", "")
                        font = values.get("Font", "")
                        bold = False
                        try:
                            bold = bool(int(float(style)) & 1)
                        except ValueError:
                            pass
                        styles.append((row.get("IX", ""), style, bold, size, font))
                    has_bold = any(item[2] for item in styles)
                    status = "ok" if has_bold else "warning"
                    if not has_bold:
                        failures += 1
                    print(f"{status}: {target!r} in {page_name} shape {shape.get('ID')} bold={has_bold}")
                    for ix, style, bold, size, font in styles:
                        print(f"  char row IX={ix} Style={style or '(missing)'} bold={bold} Size={size or '(missing)'} Font={font or '(missing)'}")
    missing = [text for text in texts if text not in open_text_index(path)]
    for text in missing:
        print(f"warning: {text!r} not found in VSDX text")
        failures += 1
    if found == 0:
        print("warning: no requested text was found")
        failures += 1
    return 1 if failures else 0


def open_text_index(path: Path) -> str:
    chunks: list[str] = []
    with ZipFile(path) as zf:
        for name in zf.namelist():
            if name.startswith("visio/pages/page") and name.endswith(".xml"):
                chunks.append(zf.read(name).decode("utf-8", errors="ignore"))
    return "".join(chunks)


def source_dir_for(input_file: Path) -> Path:
    if input_file.parent.name == "out":
        return input_file.parent.parent
    return input_file.parent


def out_dir_for(input_file: Path) -> Path:
    return source_dir_for(input_file) / "out"


def output_dir_arg(args: argparse.Namespace, input_file: Path) -> Path:
    return Path(args.out_dir) if getattr(args, "out_dir", None) else out_dir_for(input_file)


def cmd_ensure(args: argparse.Namespace) -> int:
    ensure(install=not args.no_install)
    return 0


def script_path(name: str) -> Path:
    return Path(__file__).resolve().parent / name


def cmd_preflight(args: argparse.Namespace) -> int:
    cmd = [sys.executable, str(script_path("preflight.py")), "--out-dir", str(args.out_dir)]
    if args.task:
        cmd.extend(["--task", args.task])
    if args.no_install:
        cmd.append("--no-install")
    if args.json:
        cmd.append("--json")
    if args.strict:
        cmd.append("--strict")
    if args.continue_with_risk:
        cmd.append("--continue-with-risk")
    proc = run(cmd, check=False)
    print(proc.stdout, end="")
    return proc.returncode


def cmd_html_capture(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        str(script_path("html_capture.py")),
        args.html,
        "--selector",
        args.selector,
        "--width",
        str(args.width),
        "--scale",
        str(args.scale),
        "--wait-ms",
        str(args.wait_ms),
    ]
    if args.out:
        cmd.extend(["--out", args.out])
    if args.stem:
        cmd.extend(["--stem", args.stem])
    proc = run(cmd, check=False)
    print(proc.stdout, end="")
    return proc.returncode


def cmd_preview(args: argparse.Namespace) -> int:
    input_file = Path(args.input)
    out_dir = output_dir_arg(args, input_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.output:
        output_path = Path(args.output)
        output = output_path if output_path.parent != Path(".") else out_dir / output_path.name
    else:
        output = out_dir / f"{input_file.stem}.preview.png"
    page_index = args.page - 1 if args.page is not None else None
    export_with_drawio(Path(args.input), output, "png", args.width, page_index, install=not args.no_install)
    return 0


def cmd_preview_pages(args: argparse.Namespace) -> int:
    input_file = Path(args.input)
    out_dir = output_dir_arg(args, input_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.stem or input_file.stem
    count = drawio_page_count(input_file)
    outputs = []
    for idx in range(1, count + 1):
        output = out_dir / f"{stem}.drawio-page{idx}.png"
        export_with_drawio(input_file, output, "png", args.width, idx - 1, install=not args.no_install)
        outputs.append(output)
    print(f"exported draw.io page previews: {len(outputs)}")
    return 0


def cmd_export_vsdx(args: argparse.Namespace) -> int:
    input_file = Path(args.input)
    out_dir = out_dir_for(input_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / Path(args.output).name if args.output else out_dir / f"{input_file.stem}.vsdx"
    export_with_drawio(input_file, output, "vsdx", install=not args.no_install)
    validate_vsdx(output)
    normalize_vsdx_colors(output)
    normalize_vsdx_textxform(output)
    validate_vsdx(output)
    return 0


def cmd_validate_vsdx(args: argparse.Namespace) -> int:
    validate_vsdx(Path(args.file))
    return 0


def cmd_normalize_vsdx_colors(args: argparse.Namespace) -> int:
    normalize_vsdx_colors(Path(args.file), Path(args.output) if args.output else None)
    validate_vsdx(Path(args.output) if args.output else Path(args.file))
    return 0


def cmd_normalize_vsdx_textxform(args: argparse.Namespace) -> int:
    normalize_vsdx_textxform(Path(args.file), Path(args.output) if args.output else None)
    validate_vsdx(Path(args.output) if args.output else Path(args.file))
    return 0


def cmd_visio_preview(args: argparse.Namespace) -> int:
    input_file = Path(args.input)
    out_dir = output_dir_arg(args, input_file)
    if args.output:
        output_path = Path(args.output)
        output = output_path if output_path.parent != Path(".") else out_dir / output_path.name
    else:
        output = out_dir / f"{input_file.stem}.visio-preview.png"
    export_with_visio(input_file, output, args.page)
    return 0


def cmd_visio_preview_pages(args: argparse.Namespace) -> int:
    input_file = Path(args.input)
    out_dir = output_dir_arg(args, input_file)
    stem = args.stem or input_file.stem
    export_all_with_visio(input_file, out_dir, stem)
    return 0


def cmd_audit_drawio(args: argparse.Namespace) -> int:
    return audit_drawio(Path(args.file))


def cmd_repair_drawio(args: argparse.Namespace) -> int:
    input_file = Path(args.file)
    out_dir = out_dir_for(input_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output)
    output = output_path if output_path.parent != Path(".") else out_dir / output_path.name
    return repair_drawio(input_file, output)


def cmd_audit_text(args: argparse.Namespace) -> int:
    return audit_vsdx_text(Path(args.file), args.text)


def cmd_roundtrip_check(args: argparse.Namespace) -> int:
    input_file = Path(args.input)
    out_dir = out_dir_for(input_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = Path(args.evidence_dir) if args.evidence_dir else out_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stem = args.stem or input_file.stem
    drawio_png = evidence_dir / f"{stem}.drawio-preview.png"
    vsdx_file = out_dir / f"{stem}.vsdx"
    visio_png = evidence_dir / f"{stem}.visio-preview.png"

    audit_result = audit_drawio(input_file)
    if audit_result != 0 and not args.allow_risky:
        raise SystemExit("draw.io pre-export audit failed; use --allow-risky only for a clearly marked risk build")
    export_with_drawio(input_file, drawio_png, "png", args.width, args.page - 1, install=not args.no_install)
    export_with_drawio(input_file, vsdx_file, "vsdx", install=not args.no_install)
    validate_vsdx(vsdx_file)
    normalize_vsdx_colors(vsdx_file)
    normalize_vsdx_textxform(vsdx_file)
    validate_vsdx(vsdx_file)
    export_with_visio(vsdx_file, visio_png, args.page)
    print(f"manual check required: compare {drawio_png} with {visio_png} before approval")
    return 0


def cmd_worklist(args: argparse.Namespace) -> int:
    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"missing source file: {source}")
    drawio = Path(args.drawio) if args.drawio else None
    if drawio is not None and not drawio.exists():
        raise SystemExit(f"missing draw.io file passed with --drawio: {drawio}")
    out_dir = Path(args.out_dir) if args.out_dir else out_dir_for(source)
    cmd = [
        sys.executable,
        str(script_path("worklist.py")),
        "create",
        str(source),
        "--out-dir",
        str(out_dir),
    ]
    if drawio:
        cmd.extend(["--drawio", str(drawio)])
    if args.stem:
        cmd.extend(["--stem", args.stem])
    if args.json_output:
        cmd.extend(["--json-output", args.json_output])
    if args.output:
        cmd.extend(["--md-output", args.output])
    proc = run(cmd, check=False)
    print(proc.stdout, end="")
    return proc.returncode


def cmd_worklist_update(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        str(script_path("worklist.py")),
        "update-check",
        args.worklist_json,
        "--id",
        args.id,
        "--status",
        args.status,
    ]
    if args.message:
        cmd.extend(["--message", args.message])
    if args.md_output:
        cmd.extend(["--md-output", args.md_output])
    proc = run(cmd, check=False)
    print(proc.stdout, end="")
    return proc.returncode


def cmd_scratch_create(args: argparse.Namespace) -> int:
    cmd = [sys.executable, str(script_path("scratch.py")), "create", "--out-dir", args.out_dir]
    if args.run_id:
        cmd.extend(["--run-id", args.run_id])
    proc = run(cmd, check=False)
    print(proc.stdout, end="")
    return proc.returncode


def cmd_scratch_clean(args: argparse.Namespace) -> int:
    proc = run([sys.executable, str(script_path("scratch.py")), "clean", args.path], check=False)
    print(proc.stdout, end="")
    return proc.returncode


def cmd_final_clean(args: argparse.Namespace) -> int:
    cmd = [sys.executable, str(script_path("final_clean.py")), args.out_dir, "--stem", args.stem]
    if args.deliverables_only:
        cmd.append("--deliverables-only")
    if args.keep_evidence:
        cmd.append("--keep-evidence")
    if args.apply:
        cmd.append("--apply")
    proc = run(cmd, check=False)
    print(proc.stdout, end="")
    return proc.returncode


def cmd_validate_structure(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        str(script_path("validate_structure.py")),
        "--html",
        args.html,
        "--drawio",
        args.drawio,
    ]
    if args.report:
        cmd.extend(["--report", args.report])
    proc = run(cmd, check=False)
    print(proc.stdout, end="")
    return proc.returncode


def cmd_visual_triage(args: argparse.Namespace) -> int:
    cmd = [sys.executable, str(script_path("visual_triage.py")), "--report", args.report, "--mode", args.mode]
    if args.structure_report:
        cmd.extend(["--structure-report", args.structure_report])
    if args.baseline:
        cmd.extend(["--baseline", args.baseline])
    if args.candidate:
        cmd.extend(["--candidate", args.candidate])
    if args.pixel_report:
        cmd.extend(["--pixel-report", args.pixel_report])
    if args.diff:
        cmd.extend(["--diff", args.diff])
    proc = run(cmd, check=False)
    print(proc.stdout, end="")
    return proc.returncode


def cmd_patch_drawio(args: argparse.Namespace) -> int:
    cmd = [sys.executable, str(script_path("patch_drawio_geometry.py")), args.input]
    if args.output:
        cmd.extend(["--output", args.output])
    if args.page is not None:
        cmd.extend(["--page", str(args.page)])
    if args.match_id:
        cmd.extend(["--match-id", args.match_id])
    if args.match_text:
        cmd.extend(["--match-text", args.match_text])
    if args.match_value_regex:
        cmd.extend(["--match-value-regex", args.match_value_regex])
    if args.match_style_contains:
        cmd.extend(["--match-style-contains", args.match_style_contains])
    for item in args.set or []:
        cmd.extend(["--set", item])
    for item in args.set_style or []:
        cmd.extend(["--set-style", item])
    for item in args.delete_style or []:
        cmd.extend(["--delete-style", item])
    if args.list_matches:
        cmd.append("--list-matches")
    if args.dry_run:
        cmd.append("--dry-run")
    proc = run(cmd, check=False)
    print(proc.stdout, end="")
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    ensure_p = sub.add_parser("ensure", help="install/locate draw.io Desktop 26.0.16")
    ensure_p.add_argument("--no-install", action="store_true", help="only check for draw.io Desktop 26.0.16; do not install")
    ensure_p.set_defaults(func=cmd_ensure)

    preflight = sub.add_parser("preflight", help="check draw.io, Visio, screenshot, path, and output dependencies")
    preflight.add_argument("--out-dir", default="out")
    preflight.add_argument(
        "--task",
        choices=["drawio-only", "preview", "html", "vsdx", "roundtrip"],
        help="dependency scope for this run",
    )
    preflight.add_argument("--no-install", action="store_true", help="do not auto-install blocking draw.io dependency")
    preflight.add_argument("--json", action="store_true")
    preflight.add_argument("--strict", action="store_true")
    preflight.add_argument("--continue-with-risk", action="store_true")
    preflight.set_defaults(func=cmd_preflight)

    html_capture = sub.add_parser("html-capture", help="capture HTML diagram containers with Python Playwright Chromium")
    html_capture.add_argument("html")
    html_capture.add_argument("--selector", default=".figure")
    html_capture.add_argument("--out")
    html_capture.add_argument("--stem")
    html_capture.add_argument("--width", type=int, default=1600)
    html_capture.add_argument("--scale", type=float, default=1)
    html_capture.add_argument("--wait-ms", type=int, default=250)
    html_capture.set_defaults(func=cmd_html_capture)

    worklist = sub.add_parser("worklist", help="write a conversion worklist with source/page/artifact mapping")
    worklist.add_argument("source")
    worklist.add_argument("--drawio", help="generated or repaired .drawio file to map against the source")
    worklist.add_argument("-o", "--output", help="Markdown output path")
    worklist.add_argument("--json-output", help="JSON output path")
    worklist.add_argument("--out-dir")
    worklist.add_argument("--stem", help="artifact filename stem used in preview names")
    worklist.set_defaults(func=cmd_worklist)

    worklist_update = sub.add_parser("worklist-update", help="update a worklist check status")
    worklist_update.add_argument("worklist_json")
    worklist_update.add_argument("--id", required=True)
    worklist_update.add_argument("--status", required=True, choices=["pending", "pass", "fail", "skipped", "unavailable", "manual_review"])
    worklist_update.add_argument("--message", default="")
    worklist_update.add_argument("--md-output")
    worklist_update.set_defaults(func=cmd_worklist_update)

    scratch_create = sub.add_parser("scratch-create", help="create an out/.tmp/<run-id> scratch directory")
    scratch_create.add_argument("--out-dir", default="out")
    scratch_create.add_argument("--run-id")
    scratch_create.set_defaults(func=cmd_scratch_create)

    scratch_clean = sub.add_parser("scratch-clean", help="remove a scratch directory")
    scratch_clean.add_argument("path")
    scratch_clean.set_defaults(func=cmd_scratch_clean)

    final_clean = sub.add_parser("final-clean", help="remove non-deliverable files from out/ by stem whitelist")
    final_clean.add_argument("out_dir")
    final_clean.add_argument("--stem", required=True)
    final_clean.add_argument(
        "--deliverables-only",
        action="store_true",
        help="compatibility no-op; deliverables-only cleanup is the default",
    )
    final_clean.add_argument(
        "--keep-evidence",
        action="store_true",
        help="also keep root-level worklist and preview evidence for debugging",
    )
    final_clean.add_argument("--apply", action="store_true", help="delete files; default is dry-run")
    final_clean.set_defaults(func=cmd_final_clean)

    validate_structure = sub.add_parser("validate-structure", help="validate HTML-to-drawio structure without screenshots")
    validate_structure.add_argument("--html", required=True)
    validate_structure.add_argument("--drawio", required=True)
    validate_structure.add_argument("--report")
    validate_structure.set_defaults(func=cmd_validate_structure)

    visual_triage = sub.add_parser("visual-triage", help="structure-first visual triage wrapper")
    visual_triage.add_argument("--structure-report")
    visual_triage.add_argument("--baseline")
    visual_triage.add_argument("--candidate")
    visual_triage.add_argument("--mode", default="stage2-vsdx")
    visual_triage.add_argument("--report", required=True)
    visual_triage.add_argument("--pixel-report")
    visual_triage.add_argument("--diff")
    visual_triage.set_defaults(func=cmd_visual_triage)

    patch_drawio = sub.add_parser("patch-drawio", help="patch draw.io geometry, value, or style by explicit selectors")
    patch_drawio.add_argument("input")
    patch_drawio.add_argument("-o", "--output")
    patch_drawio.add_argument("--page", type=int)
    patch_drawio.add_argument("--match-id")
    patch_drawio.add_argument("--match-text")
    patch_drawio.add_argument("--match-value-regex")
    patch_drawio.add_argument("--match-style-contains")
    patch_drawio.add_argument("--set", action="append")
    patch_drawio.add_argument("--set-style", action="append")
    patch_drawio.add_argument("--delete-style", action="append")
    patch_drawio.add_argument("--list-matches", action="store_true")
    patch_drawio.add_argument("--dry-run", action="store_true")
    patch_drawio.set_defaults(func=cmd_patch_drawio)

    preview = sub.add_parser("preview", help="export a PNG preview")
    preview.add_argument("input")
    preview.add_argument("-o", "--output")
    preview.add_argument("--out-dir", help="directory for the preview when --output is a filename or omitted")
    preview.add_argument("--width", type=int, default=2000)
    preview.add_argument("--page", type=int, help="1-based draw.io page number to export")
    preview.add_argument("--no-install", action="store_true", help="do not auto-install draw.io Desktop 26.0.16")
    preview.set_defaults(func=cmd_preview)

    preview_pages = sub.add_parser("preview-pages", help="export one PNG preview per draw.io page")
    preview_pages.add_argument("input")
    preview_pages.add_argument("--out-dir", help="directory for generated page previews")
    preview_pages.add_argument("--width", type=int, default=2000)
    preview_pages.add_argument("--stem")
    preview_pages.add_argument("--no-install", action="store_true", help="do not auto-install draw.io Desktop 26.0.16")
    preview_pages.set_defaults(func=cmd_preview_pages)

    vsdx = sub.add_parser("export-vsdx", help="export and validate VSDX")
    vsdx.add_argument("input")
    vsdx.add_argument("-o", "--output")
    vsdx.add_argument("--no-install", action="store_true", help="do not auto-install draw.io Desktop 26.0.16")
    vsdx.set_defaults(func=cmd_export_vsdx)

    val = sub.add_parser("validate-vsdx", help="validate VSDX package structure")
    val.add_argument("file")
    val.set_defaults(func=cmd_validate_vsdx)

    norm = sub.add_parser("normalize-vsdx-colors", help="add RGB formulas to VSDX color cells while preserving hex V values")
    norm.add_argument("file")
    norm.add_argument("-o", "--output")
    norm.set_defaults(func=cmd_normalize_vsdx_colors)

    norm_text = sub.add_parser("normalize-vsdx-textxform", help="center normal VSDX text boxes inside their shapes")
    norm_text.add_argument("file")
    norm_text.add_argument("-o", "--output")
    norm_text.set_defaults(func=cmd_normalize_vsdx_textxform)

    visio_preview = sub.add_parser("visio-preview", help="export a PNG preview from VSDX using Microsoft Visio COM")
    visio_preview.add_argument("input")
    visio_preview.add_argument("-o", "--output")
    visio_preview.add_argument("--out-dir", help="directory for the preview when --output is a filename or omitted")
    visio_preview.add_argument("--page", type=int, default=1)
    visio_preview.set_defaults(func=cmd_visio_preview)

    visio_preview_pages = sub.add_parser("visio-preview-pages", help="export one PNG preview per VSDX page using Microsoft Visio COM")
    visio_preview_pages.add_argument("input")
    visio_preview_pages.add_argument("--out-dir", help="directory for generated Visio page previews")
    visio_preview_pages.add_argument("--stem")
    visio_preview_pages.set_defaults(func=cmd_visio_preview_pages)

    audit_drawio_p = sub.add_parser("audit-drawio", help="audit source .drawio for high-risk VSDX text structures")
    audit_drawio_p.add_argument("file")
    audit_drawio_p.set_defaults(func=cmd_audit_drawio)

    repair_drawio_p = sub.add_parser("repair-drawio", help="create a new .drawio with common composite labels split for VSDX")
    repair_drawio_p.add_argument("file")
    repair_drawio_p.add_argument("-o", "--output", required=True)
    repair_drawio_p.set_defaults(func=cmd_repair_drawio)

    audit = sub.add_parser("audit-text", help="check whether specified VSDX text has bold character styling")
    audit.add_argument("file")
    audit.add_argument("--text", action="append", required=True, help="text to find and audit; repeat for multiple labels")
    audit.set_defaults(func=cmd_audit_text)

    rt = sub.add_parser("roundtrip-check", help="export drawio preview, VSDX, and Visio-rendered preview")
    rt.add_argument("input")
    rt.add_argument("--stem")
    rt.add_argument("--evidence-dir", help="directory for draw.io and Visio PNG evidence; VSDX remains in out/")
    rt.add_argument("--width", type=int, default=2000)
    rt.add_argument("--page", type=int, default=1, help="1-based Visio page number to export as the preview")
    rt.add_argument("--allow-risky", action="store_true", help="continue even if draw.io pre-export audit fails")
    rt.add_argument("--no-install", action="store_true", help="do not auto-install draw.io Desktop 26.0.16")
    rt.set_defaults(func=cmd_roundtrip_check)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
