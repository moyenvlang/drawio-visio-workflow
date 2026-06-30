#!/usr/bin/env python3
"""Create and update conversion worklists."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET


STATUS_VALUES = {"pending", "pass", "fail", "skipped", "unavailable", "manual_review"}


class FigureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.figures: list[dict[str, str]] = []
        self.stack: list[dict[str, object]] = []

    @staticmethod
    def attrs(items: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in items}

    @staticmethod
    def has_class(attrs: dict[str, str], name: str) -> bool:
        return name in (attrs.get("class") or "").split()

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = self.attrs(attrs_list)
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
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].get("tag") == tag:
                del self.stack[index:]
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
    parser = FigureParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.figures


def drawio_pages(path: Path) -> list[str]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    pages = root.findall("diagram")
    if not pages:
        raise SystemExit(f"missing <diagram> pages: {path}")
    return [page.get("name") or f"Page {index}" for index, page in enumerate(pages, 1)]


def detect_pages(source: Path, drawio: Path | None, stem: str) -> tuple[str, list[dict[str, object]]]:
    suffix = source.suffix.lower()
    pages: list[dict[str, object]] = []
    if suffix in {".html", ".htm"}:
        input_type = "HTML"
        figures = html_figures(source)
        if not figures:
            figures = [{"id": "", "title": source.stem, "note": ""}]
        for index, figure in enumerate(figures, 1):
            pages.append(
                {
                    "index": index,
                    "source": f"#{figure.get('id')}" if figure.get("id") else f"figure[{index}]",
                    "title": figure.get("title") or f"Figure {index}",
                    "note": figure.get("note") or "",
                    "html_screenshot": f"out/{stem}.html-page{index}.png",
                    "drawio_preview": f"out/{stem}.drawio-page{index}.png",
                    "visio_preview": f"out/{stem}.visio-page{index}.png",
                }
            )
    elif suffix == ".drawio":
        input_type = "drawio"
        for index, name in enumerate(drawio_pages(source), 1):
            pages.append(
                {
                    "index": index,
                    "source": f"diagram[{index}]",
                    "title": name,
                    "note": "",
                    "drawio_preview": f"out/{stem}.drawio-page{index}.png",
                    "visio_preview": f"out/{stem}.visio-page{index}.png",
                }
            )
    elif suffix in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}:
        input_type = "image"
        pages.append({"index": 1, "source": source.name, "title": source.stem, "note": ""})
    else:
        input_type = "new/unknown"
        pages.append({"index": 1, "source": source.name, "title": source.stem, "note": ""})

    if drawio and drawio.exists():
        names = drawio_pages(drawio)
        for index, name in enumerate(names, 1):
            if index <= len(pages):
                pages[index - 1]["drawio_page"] = name
            else:
                pages.append({"index": index, "source": "(no mapped source)", "title": name, "note": "", "drawio_page": name})
    for page in pages:
        page.setdefault("drawio_page", f"Page {page['index']}")
    return input_type, pages


def default_checks() -> list[dict[str, str]]:
    return [
        {"id": "source_unchanged", "label": "Original source remains unchanged.", "status": "pending", "message": ""},
        {"id": "drawio_encoding", "label": ".drawio encoding validation passed.", "status": "pending", "message": ""},
        {"id": "audit_drawio", "label": "audit-drawio passed.", "status": "pending", "message": ""},
        {"id": "drawio_previews", "label": "All draw.io page previews were exported.", "status": "pending", "message": ""},
        {"id": "stage1", "label": "Stage 1 source-to-drawio validation completed per page.", "status": "pending", "message": ""},
        {"id": "vsdx_export", "label": "VSDX exported with draw.io Desktop 26.0.16.", "status": "pending", "message": ""},
        {"id": "vsdx_validation", "label": "VSDX package validation passed.", "status": "pending", "message": ""},
        {"id": "visio_previews", "label": "All Visio COM page previews were exported, or unavailability was reported.", "status": "pending", "message": ""},
        {"id": "stage2", "label": "Stage 2 drawio-to-Visio validation completed per page.", "status": "pending", "message": ""},
        {"id": "important_text", "label": "Important text styling was audited where relevant.", "status": "pending", "message": ""},
        {"id": "scratch_cleanup", "label": "Scratch files and failed intermediate outputs were removed.", "status": "pending", "message": ""},
    ]


def create_worklist(source: Path, drawio: Path | None, stem: str | None, out_dir: Path) -> dict[str, object]:
    artifact_stem = stem or (drawio.stem if drawio else source.stem)
    input_type, pages = detect_pages(source, drawio, artifact_stem)
    return {
        "schema": "drawio-visio-worklist/v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": str(source),
        "input_type": input_type,
        "drawio": str(drawio) if drawio else None,
        "vsdx": None,
        "artifact_stem": artifact_stem,
        "out_dir": str(out_dir),
        "pages": pages,
        "checks": default_checks(),
        "notes": [],
    }


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def save(data: dict[str, object], json_path: Path, md_path: Path | None = None) -> None:
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if md_path:
        md_path.write_text(render_markdown(data), encoding="utf-8")


def update_check(data: dict[str, object], check_id: str, status: str, message: str) -> None:
    if status not in STATUS_VALUES:
        raise SystemExit(f"invalid status {status!r}; expected one of {sorted(STATUS_VALUES)}")
    checks = data.get("checks")
    if not isinstance(checks, list):
        raise SystemExit("worklist missing checks")
    for check in checks:
        if isinstance(check, dict) and check.get("id") == check_id:
            check["status"] = status
            check["message"] = message
            return
    raise SystemExit(f"unknown check id: {check_id}")


def status_box(status: str) -> str:
    return {
        "pending": "[ ]",
        "pass": "[x]",
        "fail": "[!]",
        "skipped": "[-]",
        "unavailable": "[!]",
        "manual_review": "[~]",
    }.get(status, "[ ]")


def render_markdown(data: dict[str, object]) -> str:
    lines = [
        "# Conversion Worklist",
        "",
        f"- Source file: `{data.get('source')}`",
        f"- Input type: `{data.get('input_type')}`",
        f"- Identified pages: {len(data.get('pages', []))}",
        f"- Draw.io source: `{data.get('drawio')}`" if data.get("drawio") else "- Draw.io source: pending",
    ]
    if data.get("vsdx"):
        lines.append(f"- VSDX output: `{data.get('vsdx')}`")
    lines.extend(["", "## Page Map", ""])
    for page in data.get("pages", []):
        if not isinstance(page, dict):
            continue
        lines.extend(
            [
                f"### Page {page.get('index')}. {page.get('title', '')}",
                "",
                f"- Source node: `{page.get('source', '')}`",
                f"- Draw.io page: `{page.get('drawio_page', '')}`",
            ]
        )
        if page.get("html_screenshot"):
            lines.append(f"- HTML/source screenshot: `{page.get('html_screenshot')}`")
        if page.get("drawio_preview"):
            lines.append(f"- draw.io preview: `{page.get('drawio_preview')}`")
        if page.get("visio_preview"):
            lines.append(f"- Visio preview: `{page.get('visio_preview')}`")
        title = str(page.get("title", ""))
        if "技术架构" in title or any(token in title for token in ("SaaS", "PaaS", "DaaS", "IaaS")):
            lines.append("- Special check: verify SaaS/PaaS/DaaS/IaaS labels do not wrap in Visio.")
        if page.get("note"):
            lines.append(f"- Source note: {page.get('note')}")
        lines.append("")
    lines.extend(["## Required Checks", ""])
    for check in data.get("checks", []):
        if not isinstance(check, dict):
            continue
        message = f" {check.get('message')}" if check.get("message") else ""
        lines.append(f"- {status_box(str(check.get('status')))} {check.get('label')}{message}")
    notes = data.get("notes", [])
    if notes:
        lines.extend(["", "## Notes", ""])
        for note in notes:
            lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "Automatic visual comparison is triage. A `fail` result requires manual review; it blocks final delivery only when structural drift, missing text, color loss, clipping, or material layout shifts are confirmed.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create", help="create worklist JSON and Markdown")
    create.add_argument("source", type=Path)
    create.add_argument("--drawio", type=Path)
    create.add_argument("--stem")
    create.add_argument("--out-dir", type=Path)
    create.add_argument("--json-output", type=Path)
    create.add_argument("--md-output", type=Path)

    update = sub.add_parser("update-check", help="update one check status")
    update.add_argument("worklist_json", type=Path)
    update.add_argument("--id", required=True)
    update.add_argument("--status", required=True, choices=sorted(STATUS_VALUES))
    update.add_argument("--message", default="")
    update.add_argument("--md-output", type=Path)

    args = parser.parse_args()
    if args.cmd == "create":
        if not args.source.exists():
            raise SystemExit(f"missing source file: {args.source}")
        if args.drawio is not None and not args.drawio.exists():
            raise SystemExit(f"missing draw.io file: {args.drawio}")
        out_dir = args.out_dir or args.source.parent / "out"
        stem = args.stem or (args.drawio.stem if args.drawio else args.source.stem)
        json_path = args.json_output or out_dir / f"{args.source.stem}.worklist.json"
        md_path = args.md_output or out_dir / f"{args.source.stem}.worklist.md"
        data = create_worklist(args.source, args.drawio, stem, out_dir)
        save(data, json_path, md_path)
        print(json_path)
        print(md_path)
    elif args.cmd == "update-check":
        data = load(args.worklist_json)
        update_check(data, args.id, args.status, args.message)
        md_path = args.md_output or args.worklist_json.with_suffix(".md")
        save(data, args.worklist_json, md_path)
        print(args.worklist_json)
        print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
