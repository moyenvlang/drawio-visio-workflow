#!/usr/bin/env python3
"""Manage draw.io 26.0.16 preview, VSDX export, and round-trip checks."""

from __future__ import annotations

import argparse
import base64
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


def is_windows() -> bool:
    return os.name == "nt" or shutil.which("powershell.exe") is not None


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def windows_ps(script: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["powershell.exe", "-NoProfile", "-Command", script], check=check)


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
    if not is_windows():
        raise SystemExit("automatic install is only implemented for Windows winget")
    check = windows_ps("winget --version", check=False)
    if check.returncode != 0:
        raise SystemExit("winget is not available; install draw.io Desktop 26.0.16 manually")
    cmd = (
        "winget install --id JGraph.Draw --exact --version 26.0.16 "
        "--accept-package-agreements --accept-source-agreements --silent --force"
    )
    proc = windows_ps(cmd, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def ensure() -> tuple[str, str]:
    found = find_drawio(required=False)
    if found:
        print(f"ok: {found[0]} ({found[1]})")
        return found
    install_windows()
    found = find_drawio(required=False)
    if not found:
        raise SystemExit(f"installed, but draw.io Desktop {REQUIRED_VERSION} was not found")
    print(f"ok: {found[0]} ({found[1]})")
    return found


def export_with_drawio(input_file: Path, output_file: Path, fmt: str, width: int | None = None) -> None:
    exe, version = ensure()
    if is_windows() and "\\" in exe:
        extra = f" --width {width}" if width and fmt.lower() == "png" else ""
        script = f'& "{exe}" -x -f {fmt}{extra} -o "{str(output_file)}" "{str(input_file)}"'
        proc = windows_ps(script, check=False)
    else:
        cmd = [exe, "-x", "-f", fmt]
        if width and fmt.lower() == "png":
            cmd.extend(["--width", str(width)])
        cmd.extend(["-o", str(output_file), str(input_file)])
        proc = run(cmd, check=False)
    print(proc.stdout)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    if not output_file.exists():
        raise SystemExit(f"output was not created: {output_file}")
    print(f"draw.io {version}: {output_file}")


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


def cmd_ensure(_: argparse.Namespace) -> int:
    ensure()
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    input_file = Path(args.input)
    out_dir = out_dir_for(input_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.output:
        output = out_dir / Path(args.output).name
    else:
        output = out_dir / f"{input_file.stem}.preview.png"
    export_with_drawio(Path(args.input), output, "png", args.width)
    return 0


def cmd_export_vsdx(args: argparse.Namespace) -> int:
    input_file = Path(args.input)
    out_dir = out_dir_for(input_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / Path(args.output).name if args.output else out_dir / f"{input_file.stem}.vsdx"
    export_with_drawio(input_file, output, "vsdx")
    validate_vsdx(output)
    normalize_vsdx_colors(output)
    validate_vsdx(output)
    return 0


def cmd_validate_vsdx(args: argparse.Namespace) -> int:
    validate_vsdx(Path(args.file))
    return 0


def cmd_normalize_vsdx_colors(args: argparse.Namespace) -> int:
    normalize_vsdx_colors(Path(args.file), Path(args.output) if args.output else None)
    validate_vsdx(Path(args.output) if args.output else Path(args.file))
    return 0


def cmd_audit_drawio(args: argparse.Namespace) -> int:
    return audit_drawio(Path(args.file))


def cmd_repair_drawio(args: argparse.Namespace) -> int:
    input_file = Path(args.file)
    out_dir = out_dir_for(input_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    return repair_drawio(input_file, out_dir / Path(args.output).name)


def cmd_audit_text(args: argparse.Namespace) -> int:
    return audit_vsdx_text(Path(args.file), args.text)


def cmd_roundtrip_check(args: argparse.Namespace) -> int:
    input_file = Path(args.input)
    out_dir = out_dir_for(input_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.stem or input_file.stem
    drawio_png = out_dir / f"{stem}.drawio-preview.png"
    vsdx_file = out_dir / f"{stem}.vsdx"
    vsdx_png = out_dir / f"{stem}.vsdx-preview.png"

    audit_result = audit_drawio(input_file)
    if audit_result != 0 and not args.allow_risky:
        raise SystemExit("draw.io pre-export audit failed; use --allow-risky only for a clearly marked risk build")
    export_with_drawio(input_file, drawio_png, "png", args.width)
    export_with_drawio(input_file, vsdx_file, "vsdx")
    validate_vsdx(vsdx_file)
    normalize_vsdx_colors(vsdx_file)
    validate_vsdx(vsdx_file)
    export_with_drawio(vsdx_file, vsdx_png, "png", args.width)
    print(f"manual check required: compare {drawio_png} with {vsdx_png} before approval")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    ensure_p = sub.add_parser("ensure", help="install/locate draw.io Desktop 26.0.16")
    ensure_p.set_defaults(func=cmd_ensure)

    preview = sub.add_parser("preview", help="export a PNG preview")
    preview.add_argument("input")
    preview.add_argument("-o", "--output")
    preview.add_argument("--width", type=int, default=2000)
    preview.set_defaults(func=cmd_preview)

    vsdx = sub.add_parser("export-vsdx", help="export and validate VSDX")
    vsdx.add_argument("input")
    vsdx.add_argument("-o", "--output")
    vsdx.set_defaults(func=cmd_export_vsdx)

    val = sub.add_parser("validate-vsdx", help="validate VSDX package structure")
    val.add_argument("file")
    val.set_defaults(func=cmd_validate_vsdx)

    norm = sub.add_parser("normalize-vsdx-colors", help="add RGB formulas to VSDX color cells while preserving hex V values")
    norm.add_argument("file")
    norm.add_argument("-o", "--output")
    norm.set_defaults(func=cmd_normalize_vsdx_colors)

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

    rt = sub.add_parser("roundtrip-check", help="export drawio preview, VSDX, and VSDX rendered preview")
    rt.add_argument("input")
    rt.add_argument("--stem")
    rt.add_argument("--width", type=int, default=2000)
    rt.add_argument("--allow-risky", action="store_true", help="continue even if draw.io pre-export audit fails")
    rt.set_defaults(func=cmd_roundtrip_check)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
