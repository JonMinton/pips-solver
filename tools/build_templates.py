"""Build the glyph template library from the example screenshots.

Run once; commits ``pips/_glyph_templates.json``.  The labels below are
the ground truth read from the two NYT Pips screenshots.  Glyph isolation
and character splitting reuse the exact runtime code in ``pips.glyphs``.
"""
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pips.glyphs import _normalize, isolate_glyph, save_templates, split_chars
from pips.parser import TAG_SAT, _find_separator

# tag glyphs in ndimage.label order (size > 800), per screenshot
EXPECTED = {
    "example-screenshots/easy-example.png": [["6"], ["<", "5"], ["9"]],
    "example-screenshots/medium-example.png": [
        ["="], ["8"], ["!="], ["<", "5"], ["="],
    ],
    "example-screenshots/hard-example.png": [
        [">", "1"], ["7"], [">", "2"], [">", "2"], ["<", "2"],
        ["1", "1"], [">", "1", "1"], ["3"], ["3"], ["7"],
        ["3"], [">", "4"], ["<", "2"], ["1", "4"], ["="],
    ],
}


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    templates: dict = {}
    for rel, expected in EXPECTED.items():
        a = np.array(Image.open(os.path.join(root, rel)).convert("RGB")).astype(int)
        H, W, _ = a.shape
        sat = a.max(axis=2) - a.min(axis=2)
        s = _find_separator(a)
        board = np.zeros((H, W), bool)
        board[: s - 2] = True
        lab, n = ndimage.label((sat > TAG_SAT) & board)
        blobs = [t for t in range(1, n + 1) if (lab == t).sum() >= 800]
        assert len(blobs) == len(expected), (rel, len(blobs), len(expected))
        for t, labels in zip(blobs, expected):
            ys, xs = np.where(lab == t)
            pad = 4
            Y0, Y1 = max(0, ys.min() - pad), min(H, ys.max() + pad + 1)
            X0, X1 = max(0, xs.min() - pad), min(W, xs.max() + pad + 1)
            glyph = isolate_glyph(a[Y0:Y1, X0:X1], lab[Y0:Y1, X0:X1] == t)
            chars = split_chars(glyph)
            assert len(chars) == len(labels), (rel, labels, len(chars))
            for ch, name in zip(chars, labels):
                templates.setdefault(name, []).append(_normalize(ch))

    save_templates(templates)
    print("templates:", {k: len(v) for k, v in sorted(templates.items())})


if __name__ == "__main__":
    main()
