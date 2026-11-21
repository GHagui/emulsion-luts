#!/usr/bin/env python3
"""
test_sheet.py - renders a comparison sheet: applies each .cube in a folder (read from
the file, trilinear interpolation) to a color chart, a gray ramp and a hue sweep.

Usage:
    python test_sheet.py LUT_FOLDER OUTPUT.png
"""
import argparse
import colorsys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# approximate ColorChecker Classic patches (8-bit sRGB)
CHART = np.array([
    [115, 82, 68], [194, 150, 130], [98, 122, 157], [87, 108, 67], [133, 128, 177], [103, 189, 170],
    [214, 126, 44], [80, 91, 166], [193, 90, 99], [94, 60, 108], [157, 188, 64], [224, 163, 46],
    [56, 61, 150], [70, 148, 73], [175, 54, 60], [231, 199, 31], [187, 86, 149], [8, 133, 161],
    [243, 243, 242], [200, 200, 200], [160, 160, 160], [122, 122, 121], [85, 85, 85], [52, 52, 52],
]) / 255.0


def read_cube(path):
    lines = open(path).read().splitlines()
    n = int(next(x for x in lines if x.startswith("LUT_3D_SIZE")).split()[1])
    data = np.loadtxt([x for x in lines if x and (x[0].isdigit() or x[0] == "-")])
    return data.reshape(n, n, n, 3)  # [b, g, r]


def apply_cube(lut, img):
    n = lut.shape[0]
    p = np.clip(img, 0, 1) * (n - 1)
    i0 = np.minimum(np.floor(p).astype(int), n - 2)
    f = p - i0
    r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]
    fr, fg, fb = f[..., 0:1], f[..., 1:2], f[..., 2:3]
    out = 0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = (fr if dr else 1 - fr) * (fg if dg else 1 - fg) * (fb if db else 1 - fb)
                out = out + w * lut[b0 + db, g0 + dg, r0 + dr]
    return out


def test_image(width=960):
    h_chart, h_ramp, h_hue = 160, 40, 120
    img = np.zeros((h_chart + h_ramp + h_hue, width, 3))
    cw = width // 6
    for i, c in enumerate(CHART):
        y, x = divmod(i, 6)
        img[y * 40:(y + 1) * 40, x * cw:(x + 1) * cw] = c
    x = np.linspace(0, 1, width)
    img[h_chart:h_chart + h_ramp] = x[None, :, None]
    for yy in range(h_hue):
        t = yy / (h_hue - 1)
        s = 1 - 0.7 * t
        v = 1 - 0.45 * np.sin(np.pi * t)
        img[h_chart + h_ramp + yy] = [colorsys.hsv_to_rgb(h, s, v) for h in x]
    return img


def main():
    p = argparse.ArgumentParser(description="Render a LUT comparison sheet")
    p.add_argument("folder", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()

    files = sorted(args.folder.glob("*.cube"))
    base = test_image()
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    rows = [("Original (Rec.709)", base)] + [(f.stem, apply_cube(read_cube(f), base)) for f in files]
    h = base.shape[0] + 26
    sheet = Image.new("RGB", (base.shape[1], h * len(rows)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(rows):
        sheet.paste(Image.fromarray((np.clip(im, 0, 1) * 255 + 0.5).astype(np.uint8)), (0, i * h + 26))
        d.text((8, i * h + 4), name, fill=(235, 235, 235), font=font)
    sheet.save(args.output)
    print("saved", args.output)


if __name__ == "__main__":
    main()
