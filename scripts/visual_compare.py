#!/usr/bin/env python3
"""Compare preview images for draw.io/Visio visual review.

This is a lightweight first-pass visual gate. It intentionally avoids external
dependencies, so it supports common non-interlaced 8-bit PNG files, PPM files,
and any extra formats available through Python's stdlib tkinter build. The
output is a JSON report and an optional PPM diff image. Use the result as an
automatic triage signal, not as the only approval.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RGBImage:
    width: int
    height: int
    pixels: list[tuple[int, int, int]]

    def get(self, x: int, y: int) -> tuple[int, int, int]:
        return self.pixels[y * self.width + x]


def clamp(value: int) -> int:
    return max(0, min(255, value))


def read_token(data: bytes, pos: int) -> tuple[bytes, int]:
    while pos < len(data):
        if data[pos:pos + 1] == b"#":
            while pos < len(data) and data[pos:pos + 1] not in {b"\n", b"\r"}:
                pos += 1
        elif data[pos:pos + 1].isspace():
            pos += 1
        else:
            break
    start = pos
    while pos < len(data) and not data[pos:pos + 1].isspace():
        pos += 1
    return data[start:pos], pos


def load_ppm(path: Path) -> RGBImage:
    data = path.read_bytes()
    magic, pos = read_token(data, 0)
    if magic not in {b"P6", b"P3"}:
        raise ValueError("not a PPM image")
    width_b, pos = read_token(data, pos)
    height_b, pos = read_token(data, pos)
    max_b, pos = read_token(data, pos)
    width = int(width_b)
    height = int(height_b)
    max_value = int(max_b)
    if max_value <= 0 or max_value > 255:
        raise ValueError("only 8-bit PPM is supported")
    while pos < len(data) and data[pos:pos + 1].isspace():
        pos += 1
    pixels: list[tuple[int, int, int]] = []
    if magic == b"P6":
        raw = data[pos:pos + width * height * 3]
        if len(raw) < width * height * 3:
            raise ValueError("truncated PPM data")
        for idx in range(0, len(raw), 3):
            pixels.append((raw[idx], raw[idx + 1], raw[idx + 2]))
    else:
        values = data[pos:].split()
        if len(values) < width * height * 3:
            raise ValueError("truncated PPM data")
        for idx in range(0, width * height * 3, 3):
            pixels.append((int(values[idx]), int(values[idx + 1]), int(values[idx + 2])))
    return RGBImage(width, height, pixels)


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def load_png(path: Path) -> RGBImage:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG image")
    pos = 8
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        chunk_data = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(">IIBBBBB", chunk_data)
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None or bit_depth is None or color_type is None or interlace is None:
        raise ValueError("PNG missing IHDR")
    if bit_depth != 8 or interlace != 0:
        raise ValueError("only non-interlaced 8-bit PNG is supported")
    channels_by_type = {0: 1, 2: 3, 6: 4}
    if color_type not in channels_by_type:
        raise ValueError("only grayscale, RGB, and RGBA PNG color types are supported")
    channels = channels_by_type[color_type]
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    rows: list[bytearray] = []
    offset = 0
    previous = bytearray(stride)
    for _y in range(height):
        if offset >= len(raw):
            raise ValueError("truncated PNG data")
        filter_type = raw[offset]
        offset += 1
        current = bytearray(raw[offset:offset + stride])
        offset += stride
        if len(current) != stride:
            raise ValueError("truncated PNG row")
        for idx in range(stride):
            left = current[idx - channels] if idx >= channels else 0
            up = previous[idx]
            upper_left = previous[idx - channels] if idx >= channels else 0
            if filter_type == 0:
                value = current[idx]
            elif filter_type == 1:
                value = (current[idx] + left) & 0xFF
            elif filter_type == 2:
                value = (current[idx] + up) & 0xFF
            elif filter_type == 3:
                value = (current[idx] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                value = (current[idx] + paeth(left, up, upper_left)) & 0xFF
            else:
                raise ValueError(f"unsupported PNG filter type {filter_type}")
            current[idx] = value
        rows.append(current)
        previous = current
    pixels: list[tuple[int, int, int]] = []
    for row in rows:
        for idx in range(0, len(row), channels):
            if color_type == 0:
                gray = row[idx]
                pixels.append((gray, gray, gray))
            else:
                pixels.append((row[idx], row[idx + 1], row[idx + 2]))
    return RGBImage(width, height, pixels)


def load_with_tk(path: Path) -> RGBImage:
    try:
        from tkinter import TclError, Tk, PhotoImage
    except ModuleNotFoundError as exc:
        raise RuntimeError("tkinter is not available") from exc
    root = Tk()
    root.withdraw()
    try:
        image = PhotoImage(file=str(path))
        width = image.width()
        height = image.height()
        pixels: list[tuple[int, int, int]] = []
        for y in range(height):
            for x in range(width):
                value = image.get(x, y)
                if isinstance(value, tuple):
                    r, g, b = value[:3]
                else:
                    parts = value.split()
                    r, g, b = (int(parts[0]), int(parts[1]), int(parts[2]))
                pixels.append((r, g, b))
        return RGBImage(width, height, pixels)
    finally:
        root.destroy()


def load_image(path: Path) -> RGBImage:
    try:
        return load_png(path)
    except Exception:
        pass
    try:
        return load_ppm(path)
    except Exception:
        pass
    try:
        return load_with_tk(path)
    except Exception as exc:
        raise SystemExit(f"cannot load image {path}: install Tk image support or provide PPM input ({exc})") from exc


def background_color(img: RGBImage) -> tuple[int, int, int]:
    samples = [img.get(0, 0), img.get(img.width - 1, 0), img.get(0, img.height - 1), img.get(img.width - 1, img.height - 1)]
    return tuple(sorted(channel)[len(channel) // 2] for channel in zip(*samples))


def color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt(sum((a[idx] - b[idx]) ** 2 for idx in range(3)))


def crop_background(img: RGBImage, tolerance: float = 18.0) -> RGBImage:
    bg = background_color(img)
    min_x, min_y = img.width, img.height
    max_x, max_y = -1, -1
    for y in range(img.height):
        for x in range(img.width):
            if color_distance(img.get(x, y), bg) > tolerance:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x < min_x or max_y < min_y:
        return img
    pad = 8
    min_x = max(0, min_x - pad)
    min_y = max(0, min_y - pad)
    max_x = min(img.width - 1, max_x + pad)
    max_y = min(img.height - 1, max_y + pad)
    width = max_x - min_x + 1
    height = max_y - min_y + 1
    pixels = [img.get(x, y) for y in range(min_y, max_y + 1) for x in range(min_x, max_x + 1)]
    return RGBImage(width, height, pixels)


def resize_nearest(img: RGBImage, width: int, height: int) -> RGBImage:
    if img.width == width and img.height == height:
        return img
    pixels: list[tuple[int, int, int]] = []
    for y in range(height):
        src_y = min(img.height - 1, int(y * img.height / height))
        for x in range(width):
            src_x = min(img.width - 1, int(x * img.width / width))
            pixels.append(img.get(src_x, src_y))
    return RGBImage(width, height, pixels)


def normalize_pair(a: RGBImage, b: RGBImage, target_width: int, crop: bool) -> tuple[RGBImage, RGBImage]:
    if crop:
        a = crop_background(a)
        b = crop_background(b)
    a_h = max(1, round(a.height * target_width / a.width))
    b_h = max(1, round(b.height * target_width / b.width))
    height = max(a_h, b_h)
    return resize_nearest(a, target_width, height), resize_nearest(b, target_width, height)


def diff_threshold_for(mode: str) -> int:
    if mode.startswith("stage2"):
        return 30
    return 38


def status_for(mode: str, changed_ratio: float, mean_delta: float, regions: int) -> str:
    if mode.startswith("stage2"):
        if changed_ratio <= 0.015 and mean_delta <= 4.5:
            return "pass"
        if changed_ratio >= 0.10 or mean_delta >= 18 or regions >= 20:
            return "fail"
        return "review_required"
    if changed_ratio <= 0.025 and mean_delta <= 6.0:
        return "pass"
    if changed_ratio >= 0.18 or mean_delta >= 24 or regions >= 30:
        return "fail"
    return "review_required"


def connected_regions(mask: list[bool], width: int, height: int) -> list[tuple[int, int, int, int, int]]:
    seen = [False] * len(mask)
    regions: list[tuple[int, int, int, int, int]] = []
    for idx, value in enumerate(mask):
        if not value or seen[idx]:
            continue
        stack = [idx]
        seen[idx] = True
        min_x = max_x = idx % width
        min_y = max_y = idx // width
        count = 0
        while stack:
            cur = stack.pop()
            count += 1
            x = cur % width
            y = cur // width
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    continue
                nidx = ny * width + nx
                if mask[nidx] and not seen[nidx]:
                    seen[nidx] = True
                    stack.append(nidx)
        if count >= 24:
            regions.append((min_x, min_y, max_x - min_x + 1, max_y - min_y + 1, count))
    regions.sort(key=lambda item: item[4], reverse=True)
    return regions


def write_ppm(path: Path, img: RGBImage) -> None:
    with path.open("wb") as fh:
        fh.write(f"P6\n{img.width} {img.height}\n255\n".encode("ascii"))
        for r, g, b in img.pixels:
            fh.write(struct.pack("BBB", clamp(r), clamp(g), clamp(b)))


def compare(args: argparse.Namespace) -> int:
    baseline = load_image(Path(args.baseline))
    candidate = load_image(Path(args.candidate))
    baseline_n, candidate_n = normalize_pair(baseline, candidate, args.width, not args.no_crop)
    threshold = args.pixel_threshold if args.pixel_threshold is not None else diff_threshold_for(args.mode)
    deltas: list[float] = []
    mask: list[bool] = []
    diff_pixels: list[tuple[int, int, int]] = []
    for a, b in zip(baseline_n.pixels, candidate_n.pixels):
        delta = color_distance(a, b)
        deltas.append(delta)
        changed = delta > threshold
        mask.append(changed)
        if changed:
            # Red heatmap overlay on a light copy of the candidate pixel.
            diff_pixels.append((255, max(0, b[1] // 3), max(0, b[2] // 3)))
        else:
            gray = int(sum(b) / 3)
            diff_pixels.append((gray, gray, gray))
    changed_count = sum(mask)
    total = len(mask) or 1
    changed_ratio = changed_count / total
    mean_delta = sum(deltas) / total
    max_delta = max(deltas) if deltas else 0
    regions = connected_regions(mask, baseline_n.width, baseline_n.height)
    status = status_for(args.mode, changed_ratio, mean_delta, len(regions))
    report = {
        "status": status,
        "mode": args.mode,
        "baseline": str(args.baseline),
        "candidate": str(args.candidate),
        "normalized_width": baseline_n.width,
        "normalized_height": baseline_n.height,
        "pixel_threshold": threshold,
        "changed_ratio": round(changed_ratio, 6),
        "mean_delta": round(mean_delta, 3),
        "max_delta": round(max_delta, 3),
        "changed_regions": [
            {"x": x, "y": y, "width": w, "height": h, "pixels": count}
            for x, y, w, h, count in regions[: args.max_regions]
        ],
        "note": "Automatic triage only. Review diff image for structural changes and allowed decorative differences.",
    }
    if args.diff:
        diff_img = RGBImage(baseline_n.width, baseline_n.height, diff_pixels)
        Path(args.diff).parent.mkdir(parents=True, exist_ok=True)
        write_ppm(Path(args.diff), diff_img)
        report["diff_image"] = str(args.diff)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if status in {"pass", "review_required"} else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="source/reference image")
    parser.add_argument("--candidate", required=True, help="candidate preview image")
    parser.add_argument("--mode", default="stage1", choices=["stage1-html", "stage1-drawio", "stage1-image", "stage1-new", "stage2-vsdx", "stage1", "stage2"])
    parser.add_argument("--report", help="write JSON report")
    parser.add_argument("--diff", help="write PPM diff image")
    parser.add_argument("--width", type=int, default=900, help="normalized comparison width")
    parser.add_argument("--pixel-threshold", type=int, help="override per-pixel RGB distance threshold")
    parser.add_argument("--max-regions", type=int, default=12, help="number of changed regions to include in report")
    parser.add_argument("--no-crop", action="store_true", help="disable background trimming before comparison")
    return compare(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
