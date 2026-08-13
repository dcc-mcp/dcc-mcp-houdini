"""Compose the licensed input and a redacted real-Houdini validation capture."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

CANVAS = (1600, 900)
BG = "#10151a"
PANEL = "#1a2229"
TEXT = "#edf2f4"
MUTED = "#9eabb4"
ACCENT = "#f3a712"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        Path("C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental") / ("Arial Bold.ttf" if bold else "Arial.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    raise FileNotFoundError("No supported showcase font is installed")


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image.convert("RGB"), size, Image.Resampling.LANCZOS)


def compose(reference_path: Path, houdini_path: Path, output_path: Path) -> None:
    reference = Image.open(reference_path)
    houdini = Image.open(houdini_path)

    # The captured title bar contains a local scene path. Remove it while keeping
    # the genuine Houdini menu bar, Scene View, parameters, node graph, and timeline.
    houdini = houdini.crop((0, 23, houdini.width, houdini.height))

    canvas = Image.new("RGB", CANVAS, BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((54, 42), "HONEYBEE SCAN QUALITY GATE", font=_font(38, bold=True), fill=TEXT)
    draw.text(
        (54, 94),
        "Licensed multiview input compared with a UV-preserving Houdini viewport proxy",
        font=_font(21),
        fill=MUTED,
    )

    left_box = (54, 156, 540, 730)
    right_box = (566, 156, 1546, 730)
    draw.rounded_rectangle(left_box, radius=14, fill=PANEL)
    draw.rounded_rectangle(right_box, radius=14, fill=PANEL)

    ref_panel = _fit(reference, (left_box[2] - left_box[0] - 24, left_box[3] - left_box[1] - 70))
    hud_panel = _fit(houdini, (right_box[2] - right_box[0] - 24, right_box[3] - right_box[1] - 70))
    canvas.paste(ref_panel, (left_box[0] + 12, left_box[1] + 54))
    canvas.paste(hud_panel, (right_box[0] + 12, right_box[1] + 54))

    draw.text((left_box[0] + 18, left_box[1] + 14), "LICENSED MULTIVIEW INPUT", font=_font(22, bold=True), fill=ACCENT)
    draw.text(
        (right_box[0] + 18, right_box[1] + 14), "REAL HOUDINI 22 VALIDATION", font=_font(22, bold=True), fill=ACCENT
    )

    draw.text((54, 775), "1,281,475-face retained component", font=_font(24, bold=True), fill=TEXT)
    draw.text((566, 775), "249,999-face UV proxy + source texture", font=_font(24, bold=True), fill=TEXT)
    draw.text(
        (54, 824),
        "Engineering evidence only: pin, fixture base, occluded anatomy, and scan damage remain visible.",
        font=_font(21),
        fill=MUTED,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "WEBP", quality=80, method=6)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("houdini", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    compose(args.reference, args.houdini, args.output)


if __name__ == "__main__":
    main()
