#!/usr/bin/env python3
"""Rebuild semantic HTML architecture diagrams as VSDX-friendly draw.io files.

This converter is intentionally structure-aware. It supports HTML diagrams that
use semantic containers such as figure, canvas, layer, grid, card, axis, bus,
tech-axis, data-flow, and desc panels. It fails loudly for unsupported HTML
instead of producing a misleading visual approximation.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
import uuid
import zlib
import xml.etree.ElementTree as ET


COLORS = {
    "ink": "#142033",
    "muted": "#34495f",
    "line": "#cfd8e3",
    "navy": "#1f5a89",
    "navy_line": "#18496f",
    "blue": "#d9eaf7",
    "blue_line": "#5b9bd5",
    "green": "#e2f0d9",
    "green_line": "#70ad47",
    "yellow": "#fff2cc",
    "yellow_line": "#d6b656",
    "orange": "#fce4d6",
    "orange_line": "#ed7d31",
    "purple": "#eadcf8",
    "purple_line": "#8064a2",
    "gray": "#f3f5f8",
    "gray_line": "#8a8a8a",
    "white": "#ffffff",
    "desc": "#fbfdff",
}

CARD_COLORS = {
    "orange": (COLORS["orange"], COLORS["orange_line"]),
    "purple": (COLORS["purple"], COLORS["purple_line"]),
    "green": (COLORS["green"], COLORS["green_line"]),
    "yellow": (COLORS["yellow"], COLORS["yellow_line"]),
    "blue": (COLORS["blue"], COLORS["blue_line"]),
    "gray": (COLORS["gray"], COLORS["gray_line"]),
}

LEFT_MARGIN = 36
CONTENT_RIGHT = 1420
RIGHT_MARGIN = 36
PAGE_WIDTH = CONTENT_RIGHT + RIGHT_MARGIN


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node | str"] = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def has_class(self, name: str) -> bool:
        return name in self.classes

    def text(self) -> str:
        parts: list[str] = []

        def walk(node: Node | str) -> None:
            if isinstance(node, str):
                value = " ".join(unescape(node).split())
                if value:
                    parts.append(value)
                return
            for child in node.children:
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

    def direct_class(self, name: str) -> list["Node"]:
        return [child for child in self.children if isinstance(child, Node) and child.has_class(name)]


class TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for idx in range(len(self.stack) - 1, 0, -1):
            if self.stack[idx].tag == tag:
                del self.stack[idx:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].children.append(data)

    def handle_entityref(self, name: str) -> None:
        self.stack[-1].children.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.stack[-1].children.append(f"&#{name};")


def fmt(value: float) -> str:
    if abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return f"{value:.1f}"


def vertical(value: str) -> str:
    return "\n".join(list(value))


def card_theme(card: Node) -> str:
    for name in CARD_COLORS:
        if card.has_class(name):
            return name
    return "gray"


def grid_cols(grid: Node, fallback: int) -> int:
    for cls in grid.classes:
        if cls.startswith("cols-"):
            try:
                return int(cls.removeprefix("cols-"))
            except ValueError:
                pass
    return fallback


def card_data(card: Node) -> tuple[str, str, str]:
    title = ""
    body = ""
    for node in card.elements():
        if node.tag == "strong" and not title:
            title = node.text()
        elif node.tag == "span" and not body:
            body = node.text()
    return title or card.text(), body, card_theme(card)


class DrawioBuilder:
    def __init__(self, page_width: int = PAGE_WIDTH, page_height: int = 760) -> None:
        self.model = ET.Element(
            "mxGraphModel",
            {
                "dx": "1422",
                "dy": "794",
                "grid": "1",
                "gridSize": "10",
                "guides": "1",
                "tooltips": "1",
                "connect": "1",
                "arrows": "1",
                "fold": "1",
                "page": "1",
                "pageScale": "1",
                "pageWidth": str(page_width),
                "pageHeight": str(page_height),
                "math": "0",
                "shadow": "0",
            },
        )
        self.root = ET.SubElement(self.model, "root")
        ET.SubElement(self.root, "mxCell", {"id": "0"})
        ET.SubElement(self.root, "mxCell", {"id": "1", "parent": "0"})
        self.next_id = 2

    def new_id(self, prefix: str) -> str:
        value = f"{prefix}-{self.next_id}"
        self.next_id += 1
        return value

    def rect(self, x: float, y: float, w: float, h: float, fill: str, stroke: str, prefix: str, extra: str = "") -> None:
        cell = ET.SubElement(
            self.root,
            "mxCell",
            {
                "id": self.new_id(prefix),
                "value": "",
                "style": f"rounded=0;whiteSpace=wrap;html=0;fillColor={fill};strokeColor={stroke};fontFamily=Microsoft YaHei;{extra}",
                "vertex": "1",
                "parent": "1",
            },
        )
        ET.SubElement(cell, "mxGeometry", {"x": fmt(x), "y": fmt(y), "width": fmt(w), "height": fmt(h), "as": "geometry"})

    def text(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        value: str,
        size: int,
        color: str,
        bold: bool,
        align: str = "center",
        valign: str = "middle",
        prefix: str = "text",
    ) -> None:
        cell = ET.SubElement(
            self.root,
            "mxCell",
            {
                "id": self.new_id(prefix),
                "value": value,
                "style": (
                    "text=1;html=0;strokeColor=none;fillColor=none;"
                    f"align={align};verticalAlign={valign};whiteSpace=wrap;rounded=0;"
                    f"fontFamily=Microsoft YaHei;fontSize={size};fontColor={color};"
                    f"fontStyle={'1' if bold else '0'};spacing=2;"
                ),
                "vertex": "1",
                "parent": "1",
            },
        )
        ET.SubElement(cell, "mxGeometry", {"x": fmt(x), "y": fmt(y), "width": fmt(w), "height": fmt(h), "as": "geometry"})

    def header(self, title: str, note: str) -> None:
        self.text(LEFT_MARGIN, 22, 980, 36, title, 24, COLORS["ink"], True, "left", "middle", "title")
        self.text(1030, 28, 390, 28, note, 12, "#31557f", False, "right", "middle", "note")

    def card(self, x: float, y: float, w: float, h: float, title: str, body: str, theme: str) -> None:
        fill, stroke = CARD_COLORS.get(theme, CARD_COLORS["gray"])
        self.rect(x, y, w, h, fill, stroke, "cardbg")
        self.text(x + 8, y + 8, w - 16, 20, title, 15, COLORS["ink"], True, "center", "middle", "cardtitle")
        self.text(x + 8, y + 32, w - 16, h - 38, body, 12, COLORS["muted"], False, "center", "middle", "cardbody")

    def bus(self, x: float, y: float, w: float, h: float, value: str) -> None:
        self.rect(x, y, w, h, "#fff7d6", COLORS["navy"], "busbg", "strokeWidth=2;")
        self.text(x + 12, y + 6, w - 24, h - 12, value, 12, "#17365d", True, "center", "middle", "bustext")

    def layer(
        self,
        y: float,
        h: float,
        label: str,
        cards: list[tuple[str, str, str]],
        cols: int,
        label_x: float,
        label_w: float,
        body_x: float,
        body_w: float,
        bus_text: str | None,
    ) -> None:
        self.rect(label_x, y, label_w, h, COLORS["navy"], COLORS["navy_line"], "labelbg")
        self.text(label_x + 8, y + 6, label_w - 16, h - 12, label, 16, COLORS["white"], True, "center", "middle", "labeltext")
        self.rect(body_x, y, body_w, h, COLORS["white"], COLORS["line"], "layerbody")
        inner_x = body_x + 12
        inner_w = body_w - 24
        gap = 10
        card_w = (inner_w - gap * (cols - 1)) / cols
        for idx, (title, body, theme) in enumerate(cards):
            self.card(inner_x + idx * (card_w + gap), y + 12, card_w, 68, title, body, theme)
        if bus_text:
            self.bus(inner_x, y + h - 32, inner_w, 24, bus_text)

    def desc_cards(self, y: float, h: float, cards: list[tuple[str, str]]) -> None:
        if not cards:
            return
        x = LEFT_MARGIN
        right = CONTENT_RIGHT
        gap = 12
        width = (right - x - gap * (len(cards) - 1)) / len(cards)
        for idx, (title, body) in enumerate(cards):
            xx = x + idx * (width + gap)
            self.rect(xx, y, width, h, COLORS["desc"], COLORS["line"], "descbg")
            self.text(xx + 12, y + 8, width - 24, 22, title, 15, COLORS["ink"], True, "left", "middle", "desctitle")
            self.text(xx + 12, y + 34, width - 24, h - 42, body, 12, COLORS["muted"], False, "left", "top", "descbody")


def encode_model(model: ET.Element) -> str:
    xml = ET.tostring(model, encoding="unicode", short_empty_elements=True)
    compressor = zlib.compressobj(level=9, wbits=-15)
    raw = compressor.compress(quote(xml).encode("utf-8")) + compressor.flush()
    return base64.b64encode(raw).decode("ascii")


def title_note(figure: Node) -> tuple[str, str]:
    title = figure.first_class("figure-title")
    note = figure.first_class("figure-note")
    return (title.text() if title else "Diagram", note.text() if note else "")


def desc_data(figure: Node) -> list[tuple[str, str]]:
    desc = figure.first_class("desc")
    if not desc:
        return []
    result: list[tuple[str, str]] = []
    for card in desc.direct_class("desc-card"):
        title = ""
        body = ""
        for node in card.elements():
            if node.tag == "h3" and not title:
                title = node.text()
            elif node.tag == "p" and not body:
                body = node.text()
        result.append((title or card.text(), body))
    return result


def layer_data(layer: Node) -> tuple[str, list[tuple[str, str, str]], int, str | None]:
    label = layer.first_class("layer-label")
    body = layer.first_class("layer-body")
    if not label or not body:
        raise ValueError("layer is missing layer-label or layer-body")
    grid = body.first_class("grid")
    cards: list[tuple[str, str, str]] = []
    cols = 1
    if grid:
        card_nodes = grid.direct_class("card")
        cards = [card_data(card) for card in card_nodes]
        cols = grid_cols(grid, len(cards) or 1)
    bus = None
    direct_bus = body.direct_class("bus")
    if direct_bus:
        bus = direct_bus[0].text()
    return label.text(), cards, cols, bus


def layer_height(bus: str | None, default: int = 92) -> int:
    return 118 if bus else default


def build_standard(figure: Node) -> tuple[str, ET.Element]:
    title, note = title_note(figure)
    canvas = figure.first_class("canvas")
    if not canvas:
        raise ValueError(f"{title}: missing canvas")
    layers = canvas.direct_class("layer")
    builder = DrawioBuilder(page_height=760)
    builder.header(title, note)
    y = 88
    last_bottom = y
    for layer in layers:
        label, cards, cols, bus = layer_data(layer)
        h = layer_height(bus)
        builder.layer(y, h, label, cards, cols, LEFT_MARGIN, 128, 176, 1244, bus)
        last_bottom = y + h
        y += h + 10
    desc = desc_data(figure)
    desc_y = last_bottom + 20
    builder.desc_cards(desc_y, 98 if max((len(body) for _, body in desc), default=0) > 120 else 92, desc)
    builder.model.set("pageHeight", str(int(desc_y + 126)))
    return title, builder.model


def build_logic(figure: Node) -> tuple[str, ET.Element]:
    title, note = title_note(figure)
    axis_wrap = figure.first_class("axis-wrap")
    if not axis_wrap:
        raise ValueError(f"{title}: missing axis-wrap")
    axes = axis_wrap.direct_class("axis")
    if len(axes) != 2:
        raise ValueError(f"{title}: expected exactly 2 side axes, found {len(axes)}")
    middle = next((child for child in axis_wrap.children if isinstance(child, Node) and not child.has_class("axis")), None)
    if middle is None:
        raise ValueError(f"{title}: missing axis-wrap center track")
    layers = middle.direct_class("layer")
    builder = DrawioBuilder(page_height=760)
    builder.header(title, note)

    left_x = LEFT_MARGIN
    axis_w = 58
    gap = 10
    outer_right = CONTENT_RIGHT
    center_left = left_x + axis_w + gap
    right_axis_x = outer_right - axis_w
    center_right = right_axis_x - gap
    label_w = 128
    label_body_gap = 12
    label_x = center_left
    body_x = label_x + label_w + label_body_gap
    body_w = center_right - body_x

    y = 88
    layer_specs = []
    for layer in layers:
        label, cards, cols, bus = layer_data(layer)
        h = layer_height(bus)
        layer_specs.append((label, cards, cols, bus, h))
    axis_h = sum(spec[4] for spec in layer_specs) + 10 * (len(layer_specs) - 1)

    builder.rect(left_x, y, axis_w, axis_h, COLORS["white"], "#222222", "axisbg")
    builder.text(left_x + 11, y + 54, 36, axis_h - 108, vertical(axes[0].text()), 20, COLORS["ink"], True, "center", "middle", "axistext")
    builder.rect(right_axis_x, y, axis_w, axis_h, COLORS["white"], "#222222", "axisbg")
    builder.text(right_axis_x + 11, y + 54, 36, axis_h - 108, vertical(axes[1].text()), 20, COLORS["ink"], True, "center", "middle", "axistext")

    last_bottom = y
    for label, cards, cols, bus, h in layer_specs:
        builder.layer(y, h, label, cards, cols, label_x, label_w, body_x, body_w, bus)
        last_bottom = y + h
        y += h + 10
    desc = desc_data(figure)
    desc_y = last_bottom + 20
    builder.desc_cards(desc_y, 92, desc)
    return title, builder.model


def build_tech(figure: Node) -> tuple[str, ET.Element]:
    title, note = title_note(figure)
    rows = figure.all_class("tech-axis")
    builder = DrawioBuilder(page_height=720)
    builder.header(title, note)
    y = 88
    last_bottom = y
    for row in rows:
        label = row.first_class("tech-label")
        body = row.first_class("tech-body")
        if not label or not body:
            raise ValueError(f"{title}: tech-axis missing label or body")
        grid = body.first_class("grid")
        cards = [card_data(card) for card in grid.direct_class("card")] if grid else []
        cols = grid_cols(grid, len(cards) or 1) if grid else 1
        bus_node = body.direct_class("bus")
        bus = bus_node[0].text() if bus_node else None
        h = 120 if bus or cols >= 4 and len(cards) >= 4 else 92
        builder.rect(LEFT_MARGIN, y, 72, h, "#f6f6f6", "#333333", "techlabelbg")
        builder.text(46, y + 12, 52, h - 24, vertical(label.text()), 22, "#17365d", True, "center", "middle", "techlabel")
        builder.rect(120, y, 1300, h, COLORS["white"], "#8d99a6", "techbody", "dashed=1;")
        inner_x = 132
        inner_w = 1276
        gap = 10
        card_w = (inner_w - gap * (cols - 1)) / cols
        for idx, (card_title, card_body, theme) in enumerate(cards):
            builder.card(inner_x + idx * (card_w + gap), y + 12, card_w, 68, card_title, card_body, theme)
        if bus:
            builder.bus(inner_x, y + h - 34, inner_w, 24, bus)
        last_bottom = y + h
        y += h + 10
    desc = desc_data(figure)
    builder.desc_cards(last_bottom + 20, 92, desc)
    return title, builder.model


def build_data(figure: Node) -> tuple[str, ET.Element]:
    title, note = title_note(figure)
    flow = figure.first_class("data-flow")
    if not flow:
        raise ValueError(f"{title}: missing data-flow")
    cols = flow.direct_class("data-col")
    builder = DrawioBuilder(page_height=720)
    builder.header(title, note)
    left = LEFT_MARGIN
    right = CONTENT_RIGHT
    gap = 10
    col_w = (right - left - gap * (len(cols) - 1)) / len(cols)
    for idx, col in enumerate(cols):
        x = left + idx * (col_w + gap)
        head = col.first_class("data-head")
        builder.rect(x, 88, col_w, 410, COLORS["white"], COLORS["line"], "datacol")
        builder.rect(x, 88, col_w, 44, COLORS["navy"], COLORS["navy_line"], "dataheadbg")
        builder.text(x + 8, 96, col_w - 16, 28, head.text() if head else "", 17, COLORS["white"], True, "center", "middle", "datahead")
        for card_idx, card in enumerate(col.direct_class("card")):
            card_title, card_body, theme = card_data(card)
            builder.card(x + 10, 142 + card_idx * 84, col_w - 20, 74, card_title, card_body, theme)
    canvas = figure.first_class("canvas")
    bus_node = canvas.direct_class("bus") if canvas else []
    if bus_node:
        builder.bus(LEFT_MARGIN, 512, 1384, 48, bus_node[0].text())
    desc = desc_data(figure)
    builder.desc_cards(576, 98, desc)
    return title, builder.model


def build_figure(figure: Node) -> tuple[str, ET.Element]:
    canvas = figure.first_class("canvas")
    if not canvas:
        raise ValueError("figure missing canvas")
    if canvas.has_class("logic") or figure.first_class("axis-wrap"):
        return build_logic(figure)
    if figure.first_class("tech-axis"):
        return build_tech(figure)
    if figure.first_class("data-flow"):
        return build_data(figure)
    return build_standard(figure)


def write_drawio(models: list[tuple[str, ET.Element]], output: Path) -> None:
    mxfile = ET.Element("mxfile", {"host": "app.diagrams.net", "version": "24.7.17", "agent": "drawio-visio-workflow"})
    for name, model in models:
        diagram = ET.SubElement(mxfile, "diagram", {"id": str(uuid.uuid4()), "name": name})
        diagram.text = encode_model(model)
    ET.indent(mxfile, space="  ")
    output.write_text(ET.tostring(mxfile, encoding="unicode"), encoding="utf-8")


def validate_model_bounds(models: list[tuple[str, ET.Element]]) -> None:
    for name, model in models:
        page_width = float(model.get("pageWidth") or "0")
        min_x: float | None = None
        max_right = 0.0
        for cell in model.findall(".//mxCell"):
            geometry = cell.find("mxGeometry")
            if geometry is None:
                continue
            x = float(geometry.get("x") or "0")
            width = float(geometry.get("width") or "0")
            if width <= 0:
                continue
            min_x = x if min_x is None else min(min_x, x)
            max_right = max(max_right, x + width)
        if min_x is None:
            raise ValueError(f"{name}: generated diagram has no positioned cells")
        left_gap = min_x
        right_gap = page_width - max_right
        if max_right > page_width + 0.1:
            raise ValueError(f"{name}: generated content exceeds page width ({max_right:.1f} > {page_width:.1f})")
        if abs(left_gap - right_gap) > 12:
            raise ValueError(
                f"{name}: generated page has asymmetric horizontal margins "
                f"(left={left_gap:.1f}, right={right_gap:.1f}); check HTML right-boundary mapping"
            )


def cmd_convert(args: argparse.Namespace) -> int:
    html_path = Path(args.html)
    text = html_path.read_text(encoding="utf-8")
    parser = TreeParser()
    parser.feed(text)
    figures = [node for node in parser.root.elements() if node.has_class("figure")]
    if not figures:
        raise SystemExit("no semantic diagram containers found: expected elements with class='figure'")
    models = [build_figure(figure) for figure in figures]
    validate_model_bounds(models)
    output = Path(args.output) if args.output else html_path.parent / "out" / f"{html_path.stem}.drawio"
    output.parent.mkdir(parents=True, exist_ok=True)
    write_drawio(models, output)
    print(output)
    print(f"converted figures: {len(models)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", help="source HTML file")
    parser.add_argument("-o", "--output", help="output .drawio path; defaults to out/<html-stem>.drawio")
    args = parser.parse_args()
    return cmd_convert(args)


if __name__ == "__main__":
    raise SystemExit(main())
