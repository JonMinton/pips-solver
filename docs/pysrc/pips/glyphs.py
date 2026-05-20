"""Recognition of the white constraint glyph inside a coloured tag marker.

The tag is a solid, highly-saturated diamond/pentagon with white text
punched out of it.  We isolate that text, split it into characters, and
classify each against a small template library (built once from real
screenshots by ``tools/build_templates.py``).  The recognised token
sequence is mapped onto a :class:`~pips.model.Constraint`.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

import numpy as np
from PIL import Image
from scipy import ndimage

from .model import Constraint, ConstraintKind

NORM = 28  # templates and queries are normalised to NORM x NORM
_TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "_glyph_templates.json")


def isolate_glyph(rgb: np.ndarray, tag_mask: np.ndarray) -> np.ndarray:
    """Return a boolean mask of the white glyph inside one tag.

    ``rgb`` is an (H, W, 3) crop around a tag; ``tag_mask`` is the boolean
    mask of that tag's saturated solid colour within the same crop.  The
    glyph is the set of bright pixels that lie *inside* the solid tag shape
    (recovered by closing the text holes).
    """
    solid = ndimage.binary_closing(tag_mask, structure=np.ones((15, 15)))
    solid = ndimage.binary_fill_holes(solid)
    bright = rgb.min(axis=2) > 180
    glyph = solid & ~tag_mask & bright
    # drop antialiasing specks
    lab, n = ndimage.label(glyph)
    for c in range(1, n + 1):
        if (lab == c).sum() < 8:
            glyph[lab == c] = False
    return glyph


def _crop(mask: np.ndarray) -> Optional[np.ndarray]:
    ys, xs = np.where(mask)
    if ys.size == 0:
        return None
    return mask[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]


def _normalize(mask: np.ndarray) -> np.ndarray:
    """Aspect-preserving square pad, then resize to NORM x NORM bits."""
    m = _crop(mask)
    if m is None:
        return np.zeros((NORM, NORM), bool)
    h, w = m.shape
    side = max(h, w)
    canvas = np.zeros((side, side), bool)
    canvas[(side - h) // 2: (side - h) // 2 + h,
           (side - w) // 2: (side - w) // 2 + w] = m
    img = Image.fromarray(canvas.astype(np.uint8) * 255).resize(
        (NORM, NORM), Image.NEAREST
    )
    return np.array(img) > 127


def split_chars(glyph: np.ndarray) -> List[np.ndarray]:
    """Split a glyph into character groups by empty-column gaps."""
    m = _crop(glyph)
    if m is None:
        return []
    colsum = m.sum(axis=0)
    groups, run = [], None
    for x, v in enumerate(colsum):
        if v > 0:
            run = x if run is None else run
            last = x
        elif run is not None:
            groups.append((run, last))
            run = None
    if run is not None:
        groups.append((run, last))
    # merge groups separated by only a 1px gap (antialiasing splits)
    merged = []
    for g in groups:
        if merged and g[0] - merged[-1][1] <= 2:
            merged[-1] = (merged[-1][0], g[1])
        else:
            merged.append(list(g))
    return [m[:, a: b + 1] for a, b in merged]


class GlyphRecognizer:
    def __init__(self, templates: Optional[Dict[str, List[np.ndarray]]] = None):
        self.templates = templates if templates is not None else load_templates()

    def classify(self, char: np.ndarray) -> tuple:
        """Return ``(label, best_score, second_best_score)``."""
        q = _normalize(char)
        best, best_name, second = -1.0, "?", -1.0
        for name, samples in self.templates.items():
            local = max(float((q == t).mean()) for t in samples)
            if local > best:
                second = best
                best, best_name = local, name
            elif local > second:
                second = local
        return best_name, best, second

    def recognize(self, glyph: np.ndarray):
        """Return ``(Constraint, info)`` where info has ``score`` (the
        worst per-char template-match score in the glyph) and
        ``margin`` (the smallest best-vs-runner-up gap)."""
        chars = split_chars(glyph)
        if not chars:
            return Constraint(ConstraintKind.NONE), {"score": 0.0, "margin": 0.0}
        triples = [self.classify(c) for c in chars]
        labels = [t[0] for t in triples]
        score = min(t[1] for t in triples)
        margin = min(t[1] - t[2] for t in triples)

        info = {"score": score, "margin": margin, "labels": list(labels)}
        if labels == ["="]:
            return Constraint(ConstraintKind.ALL_EQUAL), info
        if labels == ["!="]:
            return Constraint(ConstraintKind.ALL_DIFFERENT), info

        comparator = None
        if labels[0] in ("<", ">"):
            comparator = labels[0]
            labels = labels[1:]

        digits = "".join(c for c in labels if c.isdigit())
        if not digits:
            return Constraint(ConstraintKind.NONE), info
        target = int(digits)
        if comparator == "<":
            return Constraint(ConstraintKind.SUM_LT, target), info
        if comparator == ">":
            return Constraint(ConstraintKind.SUM_GT, target), info
        return Constraint(ConstraintKind.SUM_EQ, target), info


def load_templates() -> Dict[str, List[np.ndarray]]:
    with open(_TEMPLATES_PATH) as fh:
        raw = json.load(fh)
    out: Dict[str, List[np.ndarray]] = {}
    for name, samples in raw.items():
        out[name] = [np.array(s, bool) for s in samples]
    return out


def save_templates(templates: Dict[str, List[np.ndarray]]) -> None:
    raw = {n: [s.astype(int).tolist() for s in samples]
           for n, samples in templates.items()}
    with open(_TEMPLATES_PATH, "w") as fh:
        json.dump(raw, fh)
