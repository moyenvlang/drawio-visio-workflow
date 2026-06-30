#!/usr/bin/env python3
"""Validate source-to-drawio structure without relying on screenshots."""

from __future__ import annotations

import argparse
import base64
import json
import re
import zlib
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
import xml.etree.ElementTree as ET


@dataclass
class PageStructure:
    title: str
    texts: list[str]
    cards: int
    buses: int
    desc_cards: int
    axes: int
    tech_labels: int
    data_heads: int


class Node:
    def __init__(self, tag: str, attrs: dict[str, str] | None = None) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[Node | str] = []

    @property
    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def has_class(self, name: str) -> bool:
        return name in self.classes

    def text(self) -> str:
        parts: list[str] = []

        def walk(item: Node | str) -> None:
            if isinstance(item, str):
                text = " ".join(unescape(item).split())
                if text:
                    parts.append(text)
                return
            for child in item.children:
                walk(child)

        walk(self)
        return " ".join(parts).strip()

    def elements(self) -> list["Node"]:
        result: list[Node] = []

        def walk(node: Node) -> None:
            result.append(node)
            for child in node.children:
                if isinstance(child, Node):
                    walk(child)

        walk(self)
        return result

    def first_class(self, name: str) -> "Node | None":
        for node in self.elements():
            if node.has_class(name):
                return node
        return None

    def all_class(self, name: str) -> list["Node"]:
        return [node for node in self.elements() if node.has_class(name)]


class TreeParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].children.append(data)

    def handle_entityref(self, name: str) -> None:
        self.stack[-1].children.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.stack[-1].children.append(f"&#{name};")


def compact(text: str) -> str:
    return "".join(text.split())


def semantic_texts(figure: Node) -> list[str]:
    texts: list[str] = []
    for node in figure.elements():
        if node.tag in {"h2", "h3", "strong", "span"} or any(
            node.has_class(name)
            for name in ("figure-title", "figure-note", "layer-label", "axis", "tech-label", "data-head", "bus")
        ):
            text = node.text()
            if text:
                texts.append(text)
    return texts


def html_structures(path: Path) -> list[PageStructure]:
    parser = TreeParser()
    parser.feed(path.read_text(encoding="utf-8"))
    figures = [node for node in parser.root.elements() if node.has_class("figure")]
    result: list[PageStructure] = []
    for figure in figures:
        title_node = figure.first_class("figure-title")
        result.append(
            PageStructure(
                title=title_node.text() if title_node else figure.text()[:60],
                texts=semantic_texts(figure),
                cards=len(figure.all_class("card")),
                buses=len(figure.all_class("bus")),
                desc_cards=len(figure.all_class("desc-card")),
                axes=len(figure.all_class("axis")),
                tech_labels=len(figure.all_class("tech-label")),
                data_heads=len(figure.all_class("data-head")),
            )
        )
    return result


def decode_payload(payload: str) -> str:
    payload = payload.strip()
    if "<mxGraphModel" in payload:
        return payload
    if "%" in payload:
        payload = unquote(payload)
    raw = base64.b64decode(payload, validate=True)
    return unquote(zlib.decompress(raw, -15).decode("utf-8"))


def drawio_models(path: Path) -> list[ET.Element]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    diagrams = root.findall("diagram")
    if not diagrams:
        raise SystemExit(f"missing draw.io pages: {path}")
    return [ET.fromstring(decode_payload(diagram.text or "")) for diagram in diagrams]


TAG_RE = re.compile(r"<[^>]+>")


def plain(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = TAG_RE.sub("", value)
    return unescape(value).strip()


def drawio_page_text(model: ET.Element) -> str:
    values: list[str] = []
    for cell in model.findall(".//mxCell"):
        value = plain(cell.get("value") or "")
        if value:
            values.append(value)
    return "\n".join(values)


def drawio_bounds_ok(model: ET.Element) -> list[str]:
    errors: list[str] = []
    try:
        width = float(model.get("pageWidth", "0") or "0")
        height = float(model.get("pageHeight", "0") or "0")
    except ValueError:
        return ["page width/height is invalid"]
    for cell in model.findall(".//mxCell[@vertex='1']"):
        geo = cell.find("mxGeometry")
        if geo is None:
            continue
        try:
            x = float(geo.get("x", "0") or "0")
            y = float(geo.get("y", "0") or "0")
            w = float(geo.get("width", "0") or "0")
            h = float(geo.get("height", "0") or "0")
        except ValueError:
            errors.append(f"cell {cell.get('id')} has invalid geometry")
            continue
        if w < 0 or h < 0:
            errors.append(f"cell {cell.get('id')} has negative size")
        if width and (x + w < -5 or x > width + 5):
            errors.append(f"cell {cell.get('id')} is outside page width")
        if height and (y + h < -5 or y > height + 5):
            errors.append(f"cell {cell.get('id')} is outside page height")
    return errors


def validate_html_to_drawio(html: Path, drawio: Path) -> dict[str, object]:
    source_pages = html_structures(html)
    models = drawio_models(drawio)
    errors: list[str] = []
    warnings: list[str] = []
    page_reports: list[dict[str, object]] = []
    if len(source_pages) != len(models):
        errors.append(f"page count mismatch: HTML figures={len(source_pages)} drawio pages={len(models)}")
    for index, source in enumerate(source_pages[: len(models)], 1):
        text_index = compact(drawio_page_text(models[index - 1]))
        missing: list[str] = []
        for text in source.texts:
            token = compact(text)
            if token and token not in text_index:
                missing.append(text)
        bound_errors = drawio_bounds_ok(models[index - 1])
        if missing:
            errors.append(f"page {index} missing {len(missing)} source text item(s)")
        if bound_errors:
            errors.extend(f"page {index}: {item}" for item in bound_errors)
        report = {
            "page": index,
            "title": source.title,
            "source_counts": {
                "cards": source.cards,
                "buses": source.buses,
                "desc_cards": source.desc_cards,
                "axes": source.axes,
                "tech_labels": source.tech_labels,
                "data_heads": source.data_heads,
                "texts": len(source.texts),
            },
            "missing_texts": missing[:20],
            "bounds_errors": bound_errors,
        }
        if missing and len(missing) > 20:
            report["missing_texts_truncated"] = len(missing) - 20
        page_reports.append(report)
        if source.tech_labels:
            for label in ("SaaS", "PaaS", "DaaS", "IaaS"):
                if label not in text_index:
                    warnings.append(f"page {index} expected technology label {label}")
    status = "fail" if errors else "pass"
    return {"status": status, "errors": errors, "warnings": warnings, "pages": page_reports}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--drawio", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    result = validate_html_to_drawio(args.html, args.drawio)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
