#!/usr/bin/env python3
"""
film_luts.py - generates film-stock-inspired 3D LUTs (.cube) for Rec.709 / gamma 2.4
input and output (a Rec.709 timeline in DaVinci Resolve).

Model (per stock):
  1. Decode Rec.709 (gamma 2.4) to relative linear light (middle gray = 0.18).
  2. Balance / sensitivity: per-channel offset in stops (e.g. tungsten balance).
  3. Per-channel characteristic curve in the log domain (stops): per-channel contrast
     around middle gray -> color crossover (shadows drift one way, highlights the other),
     with a soft toe (black floor) and a soft shoulder (ceiling).
  4. Oklab: overall saturation, saturation by luminance (shadows / highlights),
     localized hue shifts and per-hue lightness.
  5. Back to Rec.709 with soft gamut compression (desaturates instead of clipping).

These are NOT measured emulations: parameters follow each stock's known character.

Usage:
    python film_luts.py OUTPUT_DIR [--size 33]
"""
import argparse
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MIDDLE_GRAY = 0.18
GAMMA = 2.4


# ---------------------------------------------------------------- helpers
def smin(a, b, k):
    """smooth minimum (k in stops)"""
    m = np.minimum(a, b)
    return m - k * np.log1p(np.exp(-np.abs(a - b) / k))


def smax(a, b, k):
    return -smin(-a, -b, k)


M_LMS = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                  [0.2119034982, 0.6806995451, 0.1073969566],
                  [0.0883024619, 0.2817188376, 0.6299787005]])
M_LAB = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                  [1.9779984951, -2.4285922050, 0.4505937099],
                  [0.0259040371, 0.7827717662, -0.8086757660]])
M_LMS_INV = np.linalg.inv(M_LMS)
M_LAB_INV = np.linalg.inv(M_LAB)


def linear_to_oklab(rgb):
    return np.cbrt(rgb @ M_LMS.T) @ M_LAB.T


def oklab_to_linear(lab):
    return ((lab @ M_LAB_INV.T) ** 3) @ M_LMS_INV.T


def hue_weight(h, center_deg, width_deg):
    d = (h - np.radians(center_deg) + np.pi) % (2 * np.pi) - np.pi
    return np.exp(-0.5 * (d / np.radians(width_deg)) ** 2)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- parameters
@dataclass
class FilmStock:
    name: str
    filename: str
    description: str
    balance: tuple = (0.0, 0.0, 0.0)      # stops (R, G, B), before the curve
    contrast: tuple = (1.0, 1.0, 1.0)     # per channel, pivot at middle gray
    tint: tuple = (0.0, 0.0, 0.0)         # post-curve offset in stops
    ceiling: float = 2.55                 # stops above middle gray
    shoulder: float = 0.35                # shoulder softness
    floor: tuple = (-9.0, -9.0, -9.0)     # black floor per channel (stops below gray)
    toe: float = 0.8                      # toe softness
    saturation: float = 1.0
    shadow_sat: float = 1.0               # multiplier in shadows
    highlight_sat: float = 1.0            # multiplier in highlights
    # list of (center deg, width deg, hue shift deg, chroma gain, delta L) in Oklab
    hue_tweaks: list = field(default_factory=list)


STOCKS = [
    FilmStock(
        name="Kodak Gold 200", filename="Kodak Gold 200 (Emulsion)",
        description="warm, golden, olive greens, pastel skies; lab-scan look",
        balance=(0.10, 0.02, -0.16), contrast=(1.04, 1.06, 1.00), tint=(0.03, 0.0, -0.06),
        ceiling=2.35, shoulder=0.45, floor=(-7.4, -7.5, -7.9), toe=0.9,
        saturation=1.12, shadow_sat=0.92, highlight_sat=0.78,
        hue_tweaks=[
            (140, 30, -16, 0.92, 0.00),   # greens -> olive-yellow, less vivid
            (105, 22, -6, 1.10, 0.01),    # golden yellows
            (55, 22, 0, 1.06, 0.01),      # golden skin
            (245, 35, -8, 0.88, 0.02),    # blues -> pastel cyan, lighter
        ],
    ),
    FilmStock(
        name="Kodak Ektar 100", filename="Kodak Ektar 100 (Emulsion)",
        description="high saturation, deep blues, warm reds, dense blacks",
        balance=(0.03, 0.0, -0.02), contrast=(1.12, 1.12, 1.10), tint=(0.02, 0.0, 0.0),
        ceiling=2.45, shoulder=0.30, floor=(-9.5, -9.5, -9.3), toe=0.7,
        saturation=1.32, shadow_sat=1.0, highlight_sat=0.85,
        hue_tweaks=[
            (255, 35, -8, 1.12, -0.05),   # deeper, slightly cyan blues
            (210, 25, 0, 1.08, -0.02),    # dense sky / cyan
            (28, 20, 4, 1.10, 0.0),       # warm reds
            (60, 18, -4, 0.95, 0.0),      # restrain skin (Ektar pushes skin red)
            (140, 30, 4, 1.05, -0.01),    # rich, slightly cool greens
        ],
    ),
    FilmStock(
        name="CineStill 800T", filename="CineStill 800T (Emulsion)",
        description="tungsten: cool/cyan in neutral light, warm practicals, lifted blacks",
        balance=(-0.22, 0.0, 0.26), contrast=(1.06, 1.0, 0.90), tint=(0.0, 0.03, 0.04),
        ceiling=2.40, shoulder=0.40, floor=(-8.2, -7.7, -7.5), toe=0.9,
        saturation=0.96, shadow_sat=0.85, highlight_sat=0.80,
        hue_tweaks=[
            (55, 25, -4, 1.10, 0.01),     # warm oranges / practical lights
            (215, 30, -10, 1.08, -0.01),  # blues -> teal
            (148, 22, 18, 0.85, 0.0),     # greens -> blue-green
            (0, 18, 6, 1.05, 0.0),        # reds / neon slightly toward magenta-red
        ],
    ),
    FilmStock(
        name="Kodak Vision3 500T", filename="Kodak Vision3 500T + 2383 (Emulsion)",
        description="tungsten with 2383 print: dense blacks, teal shadows, warm skin",
        balance=(-0.14, 0.0, 0.16), contrast=(1.16, 1.12, 1.04), tint=(0.02, 0.01, -0.01),
        ceiling=2.30, shoulder=0.30, floor=(-10.0, -9.6, -9.2), toe=0.75,
        saturation=1.02, shadow_sat=0.80, highlight_sat=0.72,
        hue_tweaks=[
            (55, 22, -3, 1.08, 0.0),      # warm skin
            (100, 22, -10, 1.0, 0.0),     # yellows -> orange (2383)
            (240, 35, -14, 0.95, -0.02),  # blues -> cyan
            (148, 22, 14, 0.82, -0.01),   # greens -> teal, restrained
            (25, 18, 2, 1.12, -0.01),     # rich reds
        ],
    ),
    FilmStock(
        name="CineStill 400D", filename="CineStill 400D (Emulsion)",
        description="neutral daylight, low contrast, wide latitude, restrained saturation",
        balance=(0.03, 0.0, -0.03), contrast=(0.92, 0.92, 0.91), tint=(0.01, 0.0, -0.01),
        ceiling=2.70, shoulder=0.55, floor=(-7.8, -7.8, -7.7), toe=1.0,
        saturation=0.95, shadow_sat=0.92, highlight_sat=0.85,
        hue_tweaks=[
            (55, 22, 0, 1.04, 0.01),      # soft, natural skin
            (140, 30, -6, 0.92, 0.0),     # calm greens
            (245, 30, -4, 0.95, 0.01),
        ],
    ),
    FilmStock(
        name="Kodak Vision3 250D", filename="Kodak Vision3 250D + 2383 (Emulsion)",
        description="daylight with 2383 print: cinema contrast, rich reds and yellows",
        balance=(0.04, 0.0, -0.04), contrast=(1.12, 1.10, 1.06), tint=(0.02, 0.0, -0.02),
        ceiling=2.35, shoulder=0.32, floor=(-9.8, -9.5, -9.2), toe=0.75,
        saturation=1.06, shadow_sat=0.82, highlight_sat=0.75,
        hue_tweaks=[
            (55, 22, -2, 1.06, 0.0),      # warm skin
            (100, 22, -9, 1.04, 0.0),     # yellows -> orange
            (25, 18, 2, 1.10, -0.01),     # rich reds
            (240, 35, -12, 0.95, -0.02),  # blues -> cyan
            (148, 22, 10, 0.88, -0.01),   # greens slightly teal
        ],
    ),
]


# ---------------------------------------------------------------- model
def apply(stock: FilmStock, v: np.ndarray) -> np.ndarray:
    """v: (..., 3) Rec.709 gamma 2.4 in 0..1 -> same encoding."""
    lin = np.clip(v, 0, 1) ** GAMMA
    E = np.log2(np.maximum(lin, 1e-7) / MIDDLE_GRAY) + np.array(stock.balance)
    y = E * np.array(stock.contrast) + np.array(stock.tint)
    y = smin(y, stock.ceiling, stock.shoulder)
    y = smax(y, np.array(stock.floor), stock.toe)
    rgb = MIDDLE_GRAY * np.exp2(y)

    lab = linear_to_oklab(rgb)
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    C = np.hypot(a, b)
    h = np.arctan2(b, a)

    sat = stock.saturation * (
        1 + (stock.shadow_sat - 1) * (1 - smoothstep(0.15, 0.45, L))
        + (stock.highlight_sat - 1) * smoothstep(0.78, 1.0, L)
    )
    dh = np.zeros_like(h)
    gain = np.ones_like(C)
    dL = np.zeros_like(L)
    chroma_w = smoothstep(0.0, 0.06, C)  # leave neutrals alone
    for center, width, shift, chroma_gain, delta_l in stock.hue_tweaks:
        w = hue_weight(h, center, width)
        dh += w * np.radians(shift)
        gain *= 1 + w * (chroma_gain - 1)
        dL += w * delta_l * chroma_w
    h2 = h + dh * chroma_w
    C2 = C * sat * gain
    lab2 = np.stack([L + dL, C2 * np.cos(h2), C2 * np.sin(h2)], axis=-1)
    out = compress_gamut(oklab_to_linear(lab2))
    return np.clip(out, 0, 1) ** (1 / GAMMA)


def compress_gamut(rgb, limit=1.3, threshold=0.88, power=1.2):
    """Smooth gamut compression (in the spirit of the ACES Reference Gamut Compression):
    pulls out-of-gamut colors in without kinks, then softly compresses the max channel
    above 1 while keeping channel ratios."""
    ach = rgb.max(axis=-1, keepdims=True)
    safe = np.maximum(np.abs(ach), 1e-9)
    d = (ach - rgb) / safe
    s = (limit - threshold) / (((1 - threshold) / (limit - threshold)) ** (-power) - 1) ** (1 / power)
    x = np.maximum(d - threshold, 0) / s
    dc = np.where(d > threshold, threshold + s * x / (1 + x ** power) ** (1 / power), d)
    rgb = ach - dc * safe
    k0 = 0.88
    a = ach[..., 0]
    a2 = np.where(a > k0, k0 + (1 - k0) * np.tanh((a - k0) / (1 - k0)), a)
    return rgb * (a2 / np.maximum(a, 1e-9))[..., None]


def lattice(n):
    x = np.linspace(0, 1, n)
    b, g, r = np.meshgrid(x, x, x, indexing="ij")  # red varies fastest
    return np.stack([r, g, b], axis=-1).reshape(-1, 3)


def write_cube(stock: FilmStock, folder: Path, n=33) -> Path:
    data = apply(stock, lattice(n))
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{stock.filename}.cube"
    with open(target, "w", encoding="ascii", newline="\n") as fh:
        fh.write(f'TITLE "{stock.name} (Emulsion) - Rec.709 g2.4 in/out"\n')
        fh.write(f"# {stock.description}\n")
        fh.write(f"LUT_3D_SIZE {n}\nDOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n")
        np.savetxt(fh, data, fmt="%.6f")
    return target


def main():
    p = argparse.ArgumentParser(description="Generate the Emulsion film-inspired LUTs")
    p.add_argument("output", type=Path)
    p.add_argument("--size", type=int, default=33)
    args = p.parse_args()
    for stock in STOCKS:
        print("OK", write_cube(stock, args.output, args.size))


if __name__ == "__main__":
    main()
