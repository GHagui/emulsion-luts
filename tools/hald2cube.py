#!/usr/bin/env python3
"""
hald2cube.py - converts HaldCLUT images (PNG/TIFF, e.g. the RawTherapee Film Simulation
collection) into .cube 3D LUTs for DaVinci Resolve and other apps.

Usage:
    python hald2cube.py INPUT OUTPUT [--size 33]

    INPUT   a .png/.tif file or a folder (scanned recursively)
    OUTPUT  destination folder (subfolder structure is preserved)
    --size  points per axis in the .cube (default 33; 65 for more precision,
            0 to keep the HaldCLUT's native size)

Requires: numpy and Pillow (pip install numpy pillow)
Optional: opencv-python, to read 16-bit HaldCLUTs without losing precision.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

EXTENSIONS = {".png", ".tif", ".tiff"}


def read_image(path: Path) -> np.ndarray:
    """Returns float32 array (height, width, 3) in 0..1."""
    try:
        import cv2  # reads 8 and 16 bit correctly

        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if img is not None:
            if img.ndim == 2:
                img = np.stack([img] * 3, axis=-1)
            img = img[..., :3][..., ::-1]  # BGR(A) -> RGB
            peak = 65535.0 if img.dtype == np.uint16 else 255.0
            return img.astype(np.float32) / peak
    except ImportError:
        pass

    from PIL import Image

    with Image.open(path) as im:
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        arr = np.asarray(im)[..., :3]
    return arr.astype(np.float32) / 255.0


def hald_to_lut(img: np.ndarray) -> np.ndarray:
    """Converts a Hald image into a LUT shaped (N_b, N_g, N_r, 3)."""
    height, width, _ = img.shape
    if height != width:
        raise ValueError(f"image is not square ({width}x{height})")
    level = round(width ** (1 / 3))
    if level ** 3 != width:
        raise ValueError(f"width {width} is not a perfect cube - not a HaldCLUT")
    n = level * level
    # Hald order: index = r + g*N + b*N*N, read row by row (red varies fastest)
    return img.reshape(-1, 3).reshape(n, n, n, 3)


def resample(lut: np.ndarray, size: int) -> np.ndarray:
    """Trilinear resampling of the LUT to `size` points per axis."""
    n = lut.shape[0]
    if size == n:
        return lut
    pos = np.linspace(0, n - 1, size)
    i0 = np.floor(pos).astype(int)
    i1 = np.minimum(i0 + 1, n - 1)
    f = (pos - i0).astype(np.float32)

    def along(a, axis):
        a0 = np.take(a, i0, axis=axis)
        a1 = np.take(a, i1, axis=axis)
        shape = [1] * a.ndim
        shape[axis] = size
        w = f.reshape(shape)
        return a0 * (1 - w) + a1 * w

    return along(along(along(lut, 0), 1), 2)


def write_cube(lut: np.ndarray, target: Path, title: str) -> None:
    n = lut.shape[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(lut.reshape(-1, 3), 0.0, 1.0)
    with open(target, "w", encoding="ascii", errors="replace", newline="\n") as fh:
        fh.write(f'TITLE "{title}"\n')
        fh.write(f"LUT_3D_SIZE {n}\n")
        fh.write("DOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n")
        np.savetxt(fh, data, fmt="%.6f")


def convert(path: Path, input_root: Path, output: Path, size: int) -> Path:
    lut = hald_to_lut(read_image(path))
    if size:
        lut = resample(lut, size)
    rel = path.relative_to(input_root) if input_root.is_dir() else Path(path.name)
    target = (output / rel).with_suffix(".cube")
    write_cube(lut, target, path.stem)
    return target


def main() -> int:
    p = argparse.ArgumentParser(description="Convert HaldCLUTs to .cube")
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--size", type=int, default=33)
    args = p.parse_args()

    if args.input.is_dir():
        files = sorted(x for x in args.input.rglob("*") if x.suffix.lower() in EXTENSIONS)
    else:
        files = [args.input]
    if not files:
        print("No HaldCLUTs found.", file=sys.stderr)
        return 1

    ok = failed = 0
    for f in files:
        try:
            target = convert(f, args.input, args.output, args.size)
            ok += 1
            print(f"OK    {f.name} -> {target}")
        except Exception as e:  # keep going with the rest
            failed += 1
            print(f"ERROR {f.name}: {e}", file=sys.stderr)
    print(f"\n{ok} converted, {failed} failed.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
