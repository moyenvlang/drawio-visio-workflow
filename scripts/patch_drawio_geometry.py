#!/usr/bin/env python3
"""Patch draw.io cell geometry, value, and style by explicit selectors."""

from __future__ import annotations

import argparse
import base64
import json
import re
import zlib
from pathlib import Path
from urllib.parse import quote, unquote
import xml.etree.ElementTree as ET


def decode_payload(payload: str) -> str:
    payload = payload.strip()
    if "<mxGraphModel" in payload:
        return payload
    if "%" in payload:
        payload = unquote(payload)
    raw = base64.b64decode(payload, validate=True)
    return unquote(zlib.decompress(raw, -15).decode("utf-8"))


def encode_payload(model_xml: str) -> str:
    ET.fromstring(model_xml)
    compressor = zlib.compressobj(level=9, wbits=-15)
    data = compressor.compress(quote(model_xml).encode("utf-8")) + compressor.flush()
    return base64.b64encode(data).decode("ascii")


def load_drawio(path: Path) -> tuple[ET.Element, list[ET.Element]]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    diagrams = root.findall("diagram")
    if not diagrams:
        raise SystemExit(f"missing draw.io pages: {path}")
    models = [ET.fromstring(decode_payload(diagram.text or "")) for diagram in diagrams]
    return root, models


def save_drawio(root: ET.Element, models: list[ET.Element], output: Path) -> None:
    diagrams = root.findall("diagram")
    for diagram, model in zip(diagrams, models):
        diagram.text = encode_payload(ET.tostring(model, encoding="unicode", short_empty_elements=True))
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    output.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")


def plain(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    return unquote(value).strip()


def style_items(style: str | None) -> list[tuple[str, str | None]]:
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


def style_text(items: list[tuple[str, str | None]]) -> str:
    parts = [key if value is None else f"{key}={value}" for key, value in items]
    return ";".join(parts) + (";" if parts else "")


def set_style(style: str | None, assignments: list[str], deletes: list[str]) -> str:
    items = style_items(style)
    for key in deletes:
        items = [(item_key, value) for item_key, value in items if item_key != key]
    for assignment in assignments:
        if "=" not in assignment:
            raise SystemExit(f"style assignment must be key=value: {assignment}")
        key, value = assignment.split("=", 1)
        for index, (item_key, _) in enumerate(items):
            if item_key == key:
                items[index] = (key, value)
                break
        else:
            items.append((key, value))
    return style_text(items)


def matches(cell: ET.Element, args: argparse.Namespace) -> bool:
    if args.match_id and cell.get("id") != args.match_id:
        return False
    value = plain(cell.get("value") or "")
    if args.match_text and args.match_text not in value:
        return False
    if args.match_value_regex and not re.search(args.match_value_regex, value):
        return False
    style = cell.get("style") or ""
    if args.match_style_contains and args.match_style_contains not in style:
        return False
    return True


def ensure_geometry(cell: ET.Element) -> ET.Element:
    geometry = cell.find("mxGeometry")
    if geometry is None:
        geometry = ET.SubElement(cell, "mxGeometry", {"as": "geometry"})
    return geometry


def apply_set(cell: ET.Element, assignments: list[str]) -> None:
    geometry_keys = {"x", "y", "width", "height"}
    for assignment in assignments:
        if "=" not in assignment:
            raise SystemExit(f"assignment must be key=value: {assignment}")
        key, value = assignment.split("=", 1)
        if key in geometry_keys:
            ensure_geometry(cell).set(key, value)
        elif key == "value":
            cell.set("value", value)
        else:
            cell.set(key, value)


def cell_summary(page: int, cell: ET.Element) -> dict[str, object]:
    geometry = cell.find("mxGeometry")
    return {
        "page": page,
        "id": cell.get("id"),
        "value": plain(cell.get("value") or ""),
        "style": cell.get("style") or "",
        "geometry": dict(geometry.attrib) if geometry is not None else {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--page", type=int, help="1-based page number")
    parser.add_argument("--match-id")
    parser.add_argument("--match-text")
    parser.add_argument("--match-value-regex")
    parser.add_argument("--match-style-contains")
    parser.add_argument("--set", action="append", default=[], help="set x/y/width/height/value or cell attribute; repeatable")
    parser.add_argument("--set-style", action="append", default=[], help="set style key=value; repeatable")
    parser.add_argument("--delete-style", action="append", default=[], help="delete style key; repeatable")
    parser.add_argument("--list-matches", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not any([args.match_id, args.match_text, args.match_value_regex, args.match_style_contains]):
        raise SystemExit("provide at least one matcher")
    if not args.list_matches and not args.dry_run and not args.output:
        raise SystemExit("--output is required unless --list-matches or --dry-run is used")

    root, models = load_drawio(args.input)
    selected_pages = [args.page] if args.page else list(range(1, len(models) + 1))
    summaries: list[dict[str, object]] = []
    changed = 0
    for page in selected_pages:
        if page < 1 or page > len(models):
            raise SystemExit(f"page out of range: {page}")
        for cell in models[page - 1].findall(".//mxCell"):
            if not matches(cell, args):
                continue
            summaries.append(cell_summary(page, cell))
            if args.list_matches:
                continue
            apply_set(cell, args.set)
            if args.set_style or args.delete_style:
                cell.set("style", set_style(cell.get("style"), args.set_style, args.delete_style))
            changed += 1

    print(json.dumps({"matches": summaries, "changed": changed}, ensure_ascii=False, indent=2))
    if args.list_matches or args.dry_run:
        return 0
    if changed == 0:
        raise SystemExit("no matching cells were changed")
    save_drawio(root, models, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
