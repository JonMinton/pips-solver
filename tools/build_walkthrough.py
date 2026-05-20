"""Generate a step-by-step visual walkthrough of the *easy* puzzle.

Writes PNG/SVG files plus a ``manifest.json`` to ``docs/walkthrough/easy/``;
the writeup page reads the manifest and shows the steps with a slider.
"""
import json
import os
import sys
from typing import Tuple

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pips.parser import parse
from pips.render import solution_layout
from pips.solver import solve

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "walkthrough", "easy")
SRC = os.path.join(ROOT, "example-screenshots", "easy-example.png")
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _save(name: str, img: Image.Image) -> None:
    img.save(os.path.join(OUT, name))


def build_svg(layout: dict, count: int) -> str:
    """Mirror of the JS ``buildSVG`` so static frames look identical."""
    CS, INS, PAD, GY = 46, 5, 14, 26
    H_COL, V_COL = "#2f6f9f", "#c8762a"
    offsets, totalW, totalH = [], 0, PAD
    for cl in layout["clusters"]:
        w = (cl["maxc"] - cl["minc"] + 1) * CS
        h = (cl["maxr"] - cl["minr"] + 1) * CS
        offsets.append(totalH)
        totalH += h + GY
        totalW = max(totalW, w)
    totalH += PAD - GY
    totalW += 2 * PAD
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {totalW} {totalH}" '
        f'font-family="ui-monospace,Menlo,monospace">'
    ]
    placed = 0
    for ci, cl in enumerate(layout["clusters"]):
        oy = offsets[ci]
        def cxf(c, _o=oy, _cl=cl):
            return PAD + (c - _cl["minc"]) * CS
        def cyf(r, _o=oy, _cl=cl):
            return _o + (r - _cl["minr"]) * CS
        for cell in cl["cells"]:
            r, g, b = cell["color"]
            parts.append(
                f'<rect x="{cxf(cell["c"])}" y="{cyf(cell["r"])}" '
                f'width="{CS}" height="{CS}" rx="7" '
                f'fill="rgb({r},{g},{b})" fill-opacity="0.55" '
                f'stroke="#e3ddd5"/>')
        for p in cl["placements"]:
            if placed >= count:
                break
            placed += 1
            horiz = p["orient"] == "H"
            r0 = min(p["a"][0], p["b"][0])
            c0 = min(p["a"][1], p["b"][1])
            x = cxf(c0) + INS
            y = cyf(r0) + INS
            w = (2 if horiz else 1) * CS - 2 * INS
            h = (1 if horiz else 2) * CS - 2 * INS
            col = H_COL if horiz else V_COL
            parts.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
                f'rx="9" fill="#fdfdfb" fill-opacity="0.65" '
                f'stroke="{col}" stroke-width="3"/>')
            if horiz:
                parts.append(
                    f'<line x1="{x+w/2}" y1="{y+4}" '
                    f'x2="{x+w/2}" y2="{y+h-4}" stroke="{col}" '
                    f'stroke-width="1.5" stroke-dasharray="3 3"/>')
            else:
                parts.append(
                    f'<line x1="{x+4}" y1="{y+h/2}" '
                    f'x2="{x+w-4}" y2="{y+h/2}" stroke="{col}" '
                    f'stroke-width="1.5" stroke-dasharray="3 3"/>')
            for cc, rr, v in ((p["a"][1], p["a"][0], p["va"]),
                              (p["b"][1], p["b"][0], p["vb"])):
                parts.append(
                    f'<text x="{cxf(cc)+CS/2}" y="{cyf(rr)+CS/2}" '
                    f'font-size="20" font-weight="700" '
                    f'fill="#26211d" text-anchor="middle" '
                    f'dominant-baseline="central">{v}</text>')
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)

    src = Image.open(SRC).convert("RGB")
    res = parse(SRC)
    puzzle = res.puzzle
    debug = res.debug
    sol = solve(puzzle)

    crop = debug.get("crop_bbox")
    cx0, cy0 = (crop[0], crop[1]) if crop else (0, 0)

    def cropped(box: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
        x0, y0, x1, y1 = box
        return (x0 + cx0, y0 + cy0, x1 + cx0, y1 + cy0)

    # Step 1: the original screenshot, no overlay.
    _save("01-original.png", src.copy())

    # Step 2: locator (puzzle crop box + separator rule).
    img = src.copy()
    d = ImageDraw.Draw(img)
    if crop:
        d.rectangle(crop, outline="#7a4fb0", width=4)
    sep_y = debug["separator"] + cy0
    d.line([(0, sep_y), (src.width, sep_y)], fill="#7a4fb0", width=3)
    _save("02-locator.png", img)

    # Step 3: cell lattice (pitch + phase locked).
    img = src.copy()
    d = ImageDraw.Draw(img, "RGBA")
    pitch = debug["pitch"]
    for (r, c), (cx, cy) in debug["cell_xy"].items():
        ox, oy = cx + cx0, cy + cy0
        half = pitch // 2
        d.rectangle([ox - half, oy - half, ox + half, oy + half],
                    outline=(122, 79, 176, 220), width=3)
        d.ellipse([ox - 5, oy - 5, ox + 5, oy + 5],
                  fill=(122, 79, 176, 255))
    _save("03-lattice.png", img)

    # Step 4: region segmentation (cells re-coloured + region letter).
    img = src.copy()
    d = ImageDraw.Draw(img, "RGBA")
    for (r, c), (cx, cy) in debug["cell_xy"].items():
        ox, oy = cx + cx0, cy + cy0
        half = pitch // 2 - 4
        rid = puzzle.region_of[(r, c)]
        col = puzzle.regions[rid].color
        d.rounded_rectangle(
            [ox - half, oy - half, ox + half, oy + half],
            radius=10, fill=(col[0], col[1], col[2], 165),
            outline=(0, 0, 0, 80), width=2)
        d.text((ox - 8, oy - 12), LETTERS[rid % 52], fill="#26211d")
    _save("04-regions.png", img)

    # Step 5: constraint tags (saturated diamonds + recognised text).
    img = src.copy()
    d = ImageDraw.Draw(img)
    for bbox, label, rid in debug["tags"]:
        tx0, ty0, tx1, ty1 = cropped(bbox)
        d.rectangle([tx0, ty0, tx1, ty1], outline="#d68b00", width=3)
        d.text((tx0, ty1 + 4), f'{label} -> region {rid}',
               fill="#a06400")
    _save("05-tags.png", img)

    # Step 6: domino tray (each tile outlined + parsed pip pair).
    img = src.copy()
    d = ImageDraw.Draw(img)
    for dom, info in zip(puzzle.dominoes, debug["domino_conf"]):
        dx0, dy0, dx1, dy1 = cropped(info["bbox"])
        d.rectangle([dx0, dy0, dx1, dy1], outline="#2f6f9f", width=3)
        d.text((dx0 + 4, dy0 - 18), f'[{dom[0]}|{dom[1]}]',
               fill="#1a456e")
    _save("06-dominoes.png", img)

    # Step 7..(7+N): solver placement playback as SVG snapshots.
    layout = solution_layout(puzzle, sol)
    N = sum(len(cl["placements"]) for cl in layout["clusters"])
    for i in range(N + 1):
        with open(os.path.join(OUT, f"07-solver-{i:02d}.svg"), "w") as fh:
            fh.write(build_svg(layout, i))

    captions = [
        ("01-original.png",
         "Step 1 — the original screenshot, as the parser first sees it."),
        ("02-locator.png",
         "Step 2 — the puzzle-locator. A warm-beige board container "
         "is detected (purple rectangle); the horizontal separator "
         "rule (line) divides board from domino tray."),
        ("03-lattice.png",
         "Step 3 — the cell lattice. Cell pitch is recovered from "
         "the autocorrelation of inter-cell brightness valleys, then "
         "the grid phase is locked by sliding it to maximise tile "
         "coverage. Each solid square is a detected cell, with a dot "
         "at its centre."),
        ("04-regions.png",
         "Step 4 — region segmentation. Orthogonally-adjacent cells of "
         "near-equal colour are merged into one region; the letter "
         "marks distinct regions."),
        ("05-tags.png",
         "Step 5 — constraint tags. Saturated diamonds carry a "
         "white-on-colour glyph; that glyph is isolated, split into "
         "characters and matched against a small template library. "
         "Each tag is then Hungarian-assigned to its region."),
        ("06-dominoes.png",
         "Step 6 — the tray. Each domino tile is detected as a "
         "near-white rounded rectangle; the tile is split in two and "
         "the dark pip blobs counted on each half."),
    ]
    for i in range(N + 1):
        captions.append((
            f"07-solver-{i:02d}.svg",
            f"Step 7 — energy-model solver: {i} of {N} dominoes placed. "
            "The solver walks tilings depth-first, pruning the instant "
            "any region's per-region energy lower bound exceeds zero."))

    with open(os.path.join(OUT, "manifest.json"), "w") as fh:
        json.dump([{"src": p, "caption": c} for p, c in captions], fh,
                  indent=2)
    print(f"wrote {len(captions)} steps to {OUT}")


if __name__ == "__main__":
    main()
