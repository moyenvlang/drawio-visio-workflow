#!/usr/bin/env python3
"""Wrap and validate draw.io files with pure Base64 diagram payloads."""

from __future__ import annotations

import argparse
import base64
import re
import sys
import uuid
import zlib
from pathlib import Path
from urllib.parse import quote, unquote
import xml.etree.ElementTree as ET


B64_RE = re.compile(r"^[A-Za-z0-9+/=]+$")


def encode_model(model_xml: str) -> str:
    ET.fromstring(model_xml)
    compressor = zlib.compressobj(level=9, wbits=-15)
    data = compressor.compress(quote(model_xml).encode("utf-8")) + compressor.flush()
    return base64.b64encode(data).decode("ascii")


def decode_payload(payload: str) -> str:
    payload = payload.strip()
    if "%" in payload:
        payload = unquote(payload)
    raw = base64.b64decode(payload, validate=True)
    return unquote(zlib.decompress(raw, -15).decode("utf-8"))


def diagram_payload(path: Path) -> str:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    diagram = root.find("diagram")
    if diagram is None or not (diagram.text or "").strip():
        raise ValueError("missing non-empty <diagram> payload")
    return (diagram.text or "").strip()


def validate_model(model_xml: str) -> list[str]:
    errors: list[str] = []
    model = ET.fromstring(model_xml)
    root = model.find("root")
    if root is None:
        return ["mxGraphModel missing <root>"]
    cells = root.findall("mxCell")
    by_id = {}
    for cell in cells:
        cid = cell.get("id")
        if not cid:
            errors.append("cell missing id")
            continue
        if cid in by_id:
            errors.append(f"duplicate id {cid!r}")
        by_id[cid] = cell
    for required in ("0", "1"):
        if required not in by_id:
            errors.append(f"missing required root cell {required!r}")
    for cell in cells:
        cid = cell.get("id")
        parent = cell.get("parent")
        if parent and parent not in by_id:
            errors.append(f"cell {cid!r} parent {parent!r} does not exist")
        if cell.get("vertex") == "1" and cell.find("mxGeometry") is None:
            errors.append(f"vertex {cid!r} missing mxGeometry")
        if cell.get("edge") == "1":
            for attr in ("source", "target"):
                ref = cell.get(attr)
                if not ref:
                    errors.append(f"edge {cid!r} missing {attr}")
                elif ref not in by_id:
                    errors.append(f"edge {cid!r} {attr} {ref!r} does not exist")
    return errors


def cmd_wrap(args: argparse.Namespace) -> int:
    model_xml = Path(args.model).read_text(encoding="utf-8")
    payload = encode_model(model_xml)
    root = ET.Element(
        "mxfile",
        {
            "host": "app.diagrams.net",
            "version": args.version,
            "agent": "drawio-visio-workflow",
        },
    )
    diagram = ET.SubElement(root, "diagram", {"id": args.id or str(uuid.uuid4()), "name": args.name})
    diagram.text = payload
    ET.indent(root, space="  ")
    Path(args.output).write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
    print(args.output)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.file)
    payload = diagram_payload(path)
    errors: list[str] = []
    if not B64_RE.fullmatch(payload):
        errors.append("<diagram> payload is not pure Base64")
    try:
        model_xml = decode_payload(payload)
    except Exception as exc:  # noqa: BLE001 - diagnostics for CLI users
        errors.append(f"cannot decode/decompress payload: {exc}")
        model_xml = ""
    if model_xml:
        try:
            errors.extend(validate_model(model_xml))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"decoded payload is not valid mxGraphModel XML: {exc}")
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"ok: {path}")
    return 0


def cmd_extract_model(args: argparse.Namespace) -> int:
    model_xml = decode_payload(diagram_payload(Path(args.file)))
    Path(args.output).write_text(model_xml, encoding="utf-8")
    print(args.output)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    wrap = sub.add_parser("wrap", help="wrap mxGraphModel XML into a .drawio file")
    wrap.add_argument("model")
    wrap.add_argument("-o", "--output", required=True)
    wrap.add_argument("--name", default="Page-1")
    wrap.add_argument("--id")
    wrap.add_argument("--version", default="24.7.17")
    wrap.set_defaults(func=cmd_wrap)

    validate = sub.add_parser("validate", help="validate a pure-Base64 .drawio file")
    validate.add_argument("file")
    validate.set_defaults(func=cmd_validate)

    extract = sub.add_parser("extract-model", help="decode a .drawio file to mxGraphModel XML")
    extract.add_argument("file")
    extract.add_argument("-o", "--output", required=True)
    extract.set_defaults(func=cmd_extract_model)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
