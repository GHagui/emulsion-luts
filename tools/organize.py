#!/usr/bin/env python3
"""
organize.py - builds the Emulsion LUT library: sorts the converted RawTherapee Film
Simulation LUTs and the original Emulsion LUTs by brand, film type and style, gives
them human-readable names, moves +/- strength variants into "Variations" subfolders
and adds a "00 Recommended" folder with general-purpose picks.

Usage:
    python organize.py RAWTHERAPEE_CUBES ORIGINAL_CUBES OUTPUT

    RAWTHERAPEE_CUBES  output of hald2cube.py run on the collection (bw/, colorslide/, ...)
    ORIGINAL_CUBES     output of film_luts.py
    OUTPUT             library folder to create (replaced if it exists)
"""
import argparse
import re
import shutil
from pathlib import Path

SOURCE_ORDER = ["bw", "colorslide", "negative_color", "negative_new", "negative_old",
                "instant_pro", "instant_consumer", "print", "various", "picturefx"]

VARIANT = re.compile(r"(_(\+{1,3}|-{1,3}))(_alt)?$|_alt$")

WORDS = {
    "kodak": "Kodak", "fuji": "Fuji", "agfa": "Agfa", "ilford": "Ilford", "rollei": "Rollei",
    "polaroid": "Polaroid", "lomography": "Lomography", "portra": "Portra", "nc": "NC",
    "vc": "VC", "uc": "UC", "tri-x": "Tri-X", "t-max": "T-Max", "tmax": "T-Max",
    "hp5": "HP5", "fp4": "FP4", "xp2": "XP2", "hps": "HPS", "apx": "APX", "bw": "BW",
    "cn": "CN", "hie": "HIE", "hs": "HS", "ir": "IR", "e-100": "E100", "gx": "GX",
    "vs": "VS", "xpro": "(Cross-Processed)", "x-pro": "X-Pro", "x-tra": "X-tra", "hg": "HG",
    "cold": "Cold", "cool": "Cool", "warm": "Warm", "negative": "Negative",
    "hc": "High Contrast", "early": "Early", "(expired)": "(Expired)", "alt": "(alt)",
    "plus": "Plus", "pan": "Pan", "f": "F", "ortho": "Ortho", "retro": "Retro",
    "tonal": "Tonal", "infra)": "Infra)", "(hs": "(HS",
}

SPECIAL = {
    "fuji_fp_100c": "Fuji FP-100C (alt)",
    "fuji_ilford_hp5": "Ilford HP5 (alt)",
    "fuji_ilford_delta_3200": "Ilford Delta 3200 (alt)",
}

CREATIVE_SPECIAL = {
    "60's": "60s", "60's_faded": "60s Faded", "60's_faded_alt": "60s Faded (alt)",
    "black_and_white": "Black and White", "hong_kong": "Hong Kong", "sutro_fx": "Sutro FX",
    "smooth_cromeish": "Smooth Chrome-ish", "vibrant_cromeish": "Vibrant Chrome-ish",
    "solarized_color2": "Solarized Color 2", "expired_polaroid": "Expired Polaroid",
    "goldfx_spring_breeze": "GoldFX Spring Breeze",
    "goldfx_bright_spring_breeze": "GoldFX Bright Spring Breeze",
    "goldfx_summer_heat": "GoldFX Summer Heat", "goldfx_bright_summer_heat": "GoldFX Bright Summer Heat",
    "goldfx_hot_summer_heat": "GoldFX Hot Summer Heat",
    "analogfx_anno_1870_color": "AnalogFX Anno 1870", "analogfx_sepia_color": "AnalogFX Sepia",
    "zilverfx_infrared": "ZilverFX Infrared", "zilverfx_vintage_b_w": "ZilverFX Vintage B&W",
}

PRINT_METHOD = {"constlmap": "soft map", "constlclip": "clip", "cuspclip": "cusp clip"}

ORIGINALS = {
    "Kodak Gold 200 (Emulsion)": ["01 Kodak", "Color Negative"],
    "Kodak Ektar 100 (Emulsion)": ["01 Kodak", "Color Negative"],
    "Kodak Vision3 500T + 2383 (Emulsion)": ["01 Kodak", "Motion Picture"],
    "Kodak Vision3 250D + 2383 (Emulsion)": ["01 Kodak", "Motion Picture"],
    "CineStill 800T (Emulsion)": ["03 CineStill"],
    "CineStill 400D (Emulsion)": ["03 CineStill"],
}

RECOMMENDED = [
    ("Day - Kodak Portra 400", ("negative_new", "kodak_portra_400")),
    ("Day - Kodak Portra 160", ("negative_new", "kodak_portra_160")),
    ("Day - Kodak Gold 200", "Kodak Gold 200 (Emulsion)"),
    ("Day - Fuji 400H", ("negative_new", "fuji_400h")),
    ("Day - CineStill 400D", "CineStill 400D (Emulsion)"),
    ("Day - Fuji Superia 400", ("negative_old", "fuji_superia_400")),
    ("Cinema - Kodak Vision3 250D + 2383", "Kodak Vision3 250D + 2383 (Emulsion)"),
    ("Night - CineStill 800T", "CineStill 800T (Emulsion)"),
    ("Night - Kodak Portra 800", ("negative_new", "kodak_portra_800")),
    ("B&W - Ilford HP5 Plus 400", ("bw", "ilford_hp5_plus_400")),
    ("B&W - Kodak Tri-X 400", ("bw", "kodak_tri-x_400")),
]

README = """Emulsion LUT library

Expected input: regular Rec.709 video (not log), EXCEPT folder 09.

00 Recommended ......... copies of the looks that work on almost anything; start here
01 Kodak ............... Color Negative | Slide | Black & White | Motion Picture
02 Fujifilm ............ Color Negative | Slide | Black & White | Instant
03 CineStill ........... 800T (night/tungsten) and 400D (day)
04 Ilford / 05 Agfa / 06 Polaroid / 07 Rollei & Lomography
08 Creative ............ by style: warm, vintage, vibrant, monochrome, experimental
09 Print Film .......... Kodak 2383/2393, Fuji 3510/3513 - expect LOG (Cineon) input;
                         on Rec.709 video they look washed out.

"Variations" subfolders: the same stock stronger (+1, +2, +3) or softer (-1, -2, -3).
"(alt)": a second version of the same stock from another part of the original collection.
"(Emulsion)": LUTs built from scratch, inspired by the stock (not measured emulations).

Original RawTherapee Film Simulation collection: CC BY-SA 4.0
(Pat David, Marc Roovers, Juan Melara). https://github.com/cyangraphics/clut
"""


def nice(stem: str) -> str:
    if stem in SPECIAL:
        return SPECIAL[stem]
    m = re.fullmatch(r"(kodak|fuji)(\d{4})_(\w+)", stem)
    if m:
        return f"{m.group(1).capitalize()} {m.group(2)} ({PRINT_METHOD.get(m.group(3), m.group(3))})"
    parts = []
    for t in stem.split("_"):
        if t in WORDS:
            parts.append(WORDS[t])
        elif re.fullmatch(r"\+{1,3}", t):
            parts.append(f"+{len(t)}")
        elif re.fullmatch(r"-{1,3}", t):
            parts.append(f"-{len(t)}")
        elif any(c.isdigit() for c in t):
            parts.append(t.upper())
        else:
            parts.append(t.capitalize())
    return " ".join(parts)


def creative_name(stem: str) -> str:
    if stem in CREATIVE_SPECIAL:
        return CREATIVE_SPECIAL[stem]
    return " ".join("(alt)" if t == "alt" else t.capitalize() for t in stem.split("_"))


def creative_style(stem: str) -> str:
    s = stem.lower()
    if any(k in s for k in ("mono", "black_and_white", "sepia", "b_w")):
        return "Monochrome"
    if any(k in s for k in ("alien", "solarized", "infrared", "purple", "pink", "rotate", "bleach")):
        return "Experimental"
    if any(k in s for k in ("golden", "warm", "sunny", "summer", "orange", "goldfx")):
        return "Warm & Golden"
    if any(k in s for k in ("60's", "fade", "expired", "vintage", "retro", "nostalgic", "mute",
                            "light_blown", "anno_1870")):
        return "Vintage & Faded"
    return "Vibrant & Contrast"


def place(source: str, stem: str):
    """Returns (folder list, display name)."""
    s = stem.lower()
    if source == "print":
        return ["09 Print Film (LOG input)"], nice(stem)
    if source in ("various", "picturefx"):
        return ["08 Creative", creative_style(stem)], creative_name(stem)

    name = nice(stem)
    if s.startswith("generic_"):
        s = s[len("generic_"):]
        name = nice(stem[len("generic_"):]) + " (Generic)"
        if s.startswith("kodachrome"):
            s, name = "kodak_" + s, "Kodak " + name
    bw = source == "bw" or any(k in s for k in (
        "tri-x", "tmax", "t-max", "bw_400", "neopan", "acros", "delta", "hp5", "px-100uv",
        "fp-3000b", "polaroid_664", "polaroid_665", "polaroid_667", "polaroid_672"))
    if "ilford" in s:
        return ["04 Ilford"], name
    if s.startswith("kodak"):
        sub = "Black & White" if bw else ("Slide" if source == "colorslide" else "Color Negative")
        return ["01 Kodak", sub], name
    if s.startswith("fuji"):
        if "fp-100c" in s or "fp_100c" in s or "fp-3000b" in s:
            sub = "Instant"
        elif bw:
            sub = "Black & White"
        elif source == "colorslide" and "xpro" not in s:
            sub = "Slide"
        else:
            sub = "Color Negative"
        return ["02 Fujifilm", sub], name
    if s.startswith("polaroid"):
        return ["06 Polaroid", "Black & White" if bw else "Color"], name
    if s.startswith("agfa"):
        return ["05 Agfa"], name
    if s.startswith(("rollei", "lomography")):
        return ["07 Rollei & Lomography"], name
    return ["10 Other"], name


def main():
    p = argparse.ArgumentParser(description="Build the organized Emulsion LUT library")
    p.add_argument("rawtherapee", type=Path)
    p.add_argument("originals", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()

    if args.output.exists():
        shutil.rmtree(args.output)
    used, origin, total = set(), {}, 0

    def copy(src: Path, folders, name, variant: bool):
        nonlocal total
        folder = args.output.joinpath(*folders)
        if variant:
            folder = folder / "Variations"
        folder.mkdir(parents=True, exist_ok=True)
        final = name
        while (folder / f"{final}.cube").as_posix().lower() in used:
            final += " (alt)"
        target = folder / f"{final}.cube"
        used.add(target.as_posix().lower())
        shutil.copy2(src, target)
        total += 1
        return target

    for source in SOURCE_ORDER:
        for f in sorted((args.rawtherapee / source).glob("*.cube")):
            folders, name = place(source, f.stem)
            variant = bool(VARIANT.search(f.stem)) and source not in ("various", "picturefx", "print")
            origin.setdefault((source, f.stem), copy(f, folders, name, variant))
    for f in sorted(args.originals.glob("*.cube")):
        origin.setdefault(f.stem, copy(f, ORIGINALS[f.stem], f.stem, False))

    rec = args.output / "00 Recommended"
    rec.mkdir(parents=True)
    for name, key in RECOMMENDED:
        shutil.copy2(origin[key], rec / f"{name}.cube")
    (args.output / "README.txt").write_text(README, encoding="utf-8")
    print(f"{total} LUTs organized + {len(RECOMMENDED)} recommended -> {args.output}")


if __name__ == "__main__":
    main()
