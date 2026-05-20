"""Classical-CV parser: NYT Pips screenshot -> :class:`~pips.model.Puzzle`.

Pipeline (no ML, no network):

1. find the thin separator rule splitting the board from the domino tray;
2. infer the square cell lattice (pitch via valley autocorrelation,
   phase by locking cell centres onto the fill bumps);
3. classify every lattice position by its colour: white = hole, a warm
   low-chroma beige = a free (no-constraint) cell, otherwise a coloured
   region cell.  Region cells are clustered by colour;
4. detect the saturated tag markers, read each constraint glyph, and
   attach it to the nearest coloured cell's region;
5. read the domino tray by counting pip blobs in each half-tile.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

from .glyphs import GlyphRecognizer, isolate_glyph
from .model import Constraint, ConstraintKind, Puzzle, Region

WHITE = 245       # min channel >= WHITE  -> background / hole
TAG_SAT = 80      # max-min saturation above this -> a vivid tag marker
SAME_REGION_T = 30.0  # max RGB gap between adjacent cells of one region
COLOR_TOL = 42.0      # max residual to the [beige, tag] colour segment
                      # (coarse hue filter; spatial proximity disambiguates)


@dataclass
class ParseResult:
    puzzle: Puzzle
    debug: Dict


def _local_max(img: np.ndarray, k: int) -> np.ndarray:
    pad = k // 2
    P = np.pad(img, pad, mode="edge")
    out = img.copy()
    for dy in range(-pad, pad + 1):
        for dx in range(-pad, pad + 1):
            out = np.maximum(
                out, P[pad + dy: pad + dy + img.shape[0],
                       pad + dx: pad + dx + img.shape[1]]
            )
    return out


def _find_separator(a: np.ndarray) -> int:
    """Row index of the full-width thin grey rule under the board."""
    mn = a.min(axis=2)
    mx = a.max(axis=2)
    nonwhite = mn < WHITE
    gray = nonwhite & ((mx - mn) < 22) & (mn >= 150) & (mn <= 243)
    frac = gray.mean(axis=1)
    return int(np.argmax(frac))


def _pitch(poly: np.ndarray, lum: np.ndarray,
           bbox: Tuple[int, int, int, int]) -> int:
    """Cell pitch in px.

    Autocorrelation has peaks at the fundamental period *and* every
    harmonic (2p, 3p, ...).  The fundamental is what we want, so return
    the smallest lag whose autocorr value is within 80% of the maximum.
    """
    x0, y0, x1, y1 = bbox
    valley = ((_local_max(lum, 9) - lum > 4) & poly).astype(float)
    sig = valley[y0:y1 + 1, x0:x1 + 1].sum(axis=0)
    sig = sig - sig.mean()
    ac = np.correlate(sig, sig, "full")[len(sig) - 1:]
    lo, hi = 28, min(len(ac) - 1, 240)
    peak = float(ac[lo:hi + 1].max())
    thresh = 0.80 * peak
    for L in range(lo, hi + 1):
        if ac[L] >= thresh and ac[L] >= ac[L - 1] and ac[L] >= ac[L + 1]:
            return L
    return int(np.argmax(ac[lo:hi + 1])) + lo


def _slot(a: np.ndarray, cy: int, cx: int, r: int):
    """Sample a lattice slot.

    Returns ``(white_fraction, coverage, dominant_colour)`` where coverage
    is the fraction of the patch occupied by a single uniform colour — high
    only when a solid cell tile fills the slot.
    """
    H, W, _ = a.shape
    patch = a[max(0, cy - r): min(H, cy + r),
              max(0, cx - r): min(W, cx + r)].reshape(-1, 3)
    if patch.size == 0:
        return 1.0, 0.0, np.zeros(3)
    sub = patch[::3]
    wf = float((sub.min(axis=1) >= 243).mean())
    dom = np.median(sub, axis=0)
    cov = float((np.linalg.norm(sub - dom, axis=1) < 16).mean())
    return wf, cov, dom


def _is_cell(wf: float, cov: float) -> bool:
    return wf < 0.35 and cov > 0.60


def _seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Distance from point ``p`` to the segment ``a``--``b`` in RGB space."""
    ab = b - a
    denom = float(ab @ ab)
    t = 0.0 if denom == 0 else float((p - a) @ ab) / denom
    t = max(0.0, min(1.0, t))
    return float(np.linalg.norm(p - (a + t * ab)))


def _locate_puzzle(a: np.ndarray):
    """Find the puzzle (board + domino tray) inside a full screenshot.

    Phone screenshots wrap the puzzle in app/browser chrome.  The board
    is always a rounded warm-beige container that stands out clearly
    from neutral grey UI; the tray sits directly below it.  Returns the
    bounding box ``(x0, y0, x1, y1)`` to crop to, or ``None`` if the
    image is already tight (so the caller leaves it alone).
    """
    H, W, _ = a.shape
    R, B = a[..., 0], a[..., 2]
    mn = a.min(axis=2); sat = a.max(axis=2) - mn
    warm = (R - B > 8) & (sat < 50) & (mn > 150) & (mn < 240)
    lab, n = ndimage.label(warm)
    if n == 0:
        return None
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    biggest = float(sizes.max())
    # only count the board containers (large warm components)
    boards = [i + 1 for i, v in enumerate(sizes)
              if v >= max(2000, 0.10 * biggest)]
    bmask = np.isin(lab, boards)
    bys, bxs = np.where(bmask)
    by0, by1 = int(bys.min()), int(bys.max())
    bx0, bx1 = int(bxs.min()), int(bxs.max())
    bh = by1 - by0

    # if the warm region already fills most of the image, no crop needed
    if (by1 - by0) > 0.85 * H and (bx1 - bx0) > 0.7 * W:
        return None

    # Locate the domino tray: search the whole area below the board for
    # *grey-scale* tile-like components (the dominoes are near-white tiles
    # with dark pip dots, all grey-scale).  Colourful UI (Photos
    # thumbnails, accent icons) is excluded by saturation; very wide/thin
    # UI rules (e.g. a browser URL bar) by aspect ratio.
    pad = max(20, bh // 6)
    zy0 = by1 + 5
    zy1 = H
    zx0 = 0                              # dominoes often extend wider
    zx1 = W                              # than the board itself
    tx0 = tx1 = ty0 = ty1 = None
    if zy0 < zy1:
        zone = a[zy0:zy1, zx0:zx1]
        zmn = zone.min(axis=2)
        zsat = zone.max(axis=2) - zmn
        zlab, zn = ndimage.label(zmn < 250)
        size_lo = 200
        size_hi = 0.5 * bh * bh
        keep = []
        for i in range(1, zn + 1):
            m = zlab == i
            cnt = int(m.sum())
            if not (size_lo < cnt < size_hi):
                continue
            if float(zsat[m].mean()) > 30:    # not greyscale -> UI image
                continue
            ys, xs = np.where(m)
            cw = int(xs.max() - xs.min()) + 1
            ch = int(ys.max() - ys.min()) + 1
            asp = max(cw, ch) / max(1, min(cw, ch))
            # a domino tile is ~2:1 (or 1:2 if vertical); reject squares
            # (UI icons) and very thin bars (URL bars).
            if not (1.5 <= asp <= 2.5):
                continue
            keep.append(i)
        if keep:
            # Take only the first y-band (= the tray right below the
            # board); tile-like things further down belong to app UI.
            comps = []
            for i in keep:
                ys, xs = np.where(zlab == i)
                comps.append((int(ys.min()), int(ys.max()),
                              int(xs.min()), int(xs.max())))
            comps.sort()
            tile_h = comps[0][1] - comps[0][0] + 1
            gap = max(40, tile_h)             # tiles in one band sit close
            band0_top = comps[0][0]
            band0_bot = comps[0][1]
            band = [comps[0]]
            for c in comps[1:]:
                if c[0] <= band0_bot + gap:
                    band.append(c)
                    band0_bot = max(band0_bot, c[1])
                else:
                    break
            ty0 = band0_top + zy0
            ty1 = band0_bot + zy0
            tx0 = min(c[2] for c in band) + zx0
            tx1 = max(c[3] for c in band) + zx0
    PAD = 24
    Y0 = max(0, by0 - PAD)
    Y1 = min(H, (ty1 if ty1 is not None else by1) + PAD)
    X0 = max(0, min(bx0, tx0 if tx0 is not None else bx0) - PAD)
    X1 = min(W, max(bx1, tx1 if tx1 is not None else bx1) + PAD)
    return (X0, Y0, X1, Y1)


def _scaled(pitch: int) -> dict:
    """Pixel thresholds that scale with the detected cell pitch.

    All other constants (saturation, RGB distances, white cutoff) are
    colour properties of the rendering, not dimensions, so they stay
    fixed; everything below depends on how many pixels a cell occupies.
    """
    p2 = pitch * pitch
    return {
        "tag_min": max(120, int(0.06 * p2)),     # min tag-marker area
        "tag_max": max(2000, int(0.8 * p2)),     # max single-tag area
                                                  # (super-blobs above this
                                                  # are split via erosion)
        "erode_n": max(3, pitch // 8),           # cluster-splitting radius
        "cluster_min": max(400, int(0.18 * p2)),
        "tile_min": max(600, int(0.30 * p2)),    # domino-tile non-bg area
        "pip_min": max(3, int(p2 / 500.0)),      # one pip-dot area
        "valley_k": max(5, pitch // 11),         # luminance local-max kernel
        "inner_m": max(3, pitch // 16),          # domino half inner margin
    }


def _parse_dominoes(a: np.ndarray, s: int, pitch: int) -> List[Tuple[int, int]]:
    th = _scaled(pitch)
    tray = a[s + 3:]
    gray = tray.mean(axis=2)
    lab, n = ndimage.label(gray < 248)
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    tiles = [i + 1 for i, v in enumerate(sizes) if v > th["tile_min"]]
    tiles.sort(key=lambda i: (np.where(lab == i)[1].min()))
    dominoes: List[Tuple[int, int]] = []
    for i in tiles:
        ys, xs = np.where(lab == i)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        sub = gray[y0:y1 + 1, x0:x1 + 1]
        h, w = sub.shape
        if w >= h:                       # horizontal tile: left | right
            halves = [sub[:, : w // 2], sub[:, w // 2:]]
        else:                            # vertical tile: top | bottom
            halves = [sub[: h // 2, :], sub[h // 2:, :]]
        counts = []
        for half in halves:
            m = th["inner_m"]
            inner = half[m:-m, m:-m] if min(half.shape) > 2 * m else half
            pl, pn = ndimage.label(inner < 110)
            psz = ndimage.sum(np.ones_like(pl), pl, range(1, pn + 1))
            counts.append(int(sum(1 for v in psz if v > th["pip_min"])))
        dominoes.append((counts[0], counts[1]))
    return dominoes


def parse_screenshot(path: str, debug: bool = False) -> Puzzle:
    return parse(path, debug=debug).puzzle


def parse(path: str, debug: bool = False) -> ParseResult:
    a = np.array(Image.open(path).convert("RGB")).astype(int)
    bbox = _locate_puzzle(a)
    if bbox is not None:
        x0, y0, x1, y1 = bbox
        a = a[y0:y1, x0:x1]
    H, W, _ = a.shape
    mn = a.min(axis=2)
    sat = a.max(axis=2) - mn
    lum = a.mean(axis=2)

    s = _find_separator(a)
    board = np.zeros((H, W), bool)
    board[: s - 2] = True
    white = mn >= WHITE
    poly = (~white) & board

    # pitch from the periodic inter-cell valleys (scale-robust)
    ys, xs = np.where(poly & (sat <= TAG_SAT))
    pitch = _pitch(poly, lum, (xs.min(), ys.min(), xs.max(), ys.max()))
    rad = max(8, int(pitch * 0.30))
    step = max(2, pitch // 26)

    # A Pips board can be several disconnected pieces.  Two pieces
    # sometimes share a thin beige rim/bridge, which makes the poly
    # mask connected even though no dominoes can cross.  Erode the poly
    # mask by ~12 px to strip thin rims/bridges; cell tiles (~80 px)
    # easily survive, so cluster IDs come from a cell-bearing core.
    th = _scaled(pitch)
    eroded = ndimage.binary_erosion(poly, iterations=th["erode_n"])
    clab, cn = ndimage.label(eroded)
    csz = ndimage.sum(np.ones_like(clab), clab, range(1, cn + 1))
    big = [i + 1 for i, v in enumerate(csz) if v > th["cluster_min"]]
    lut = np.zeros(cn + 1, dtype=np.int64)
    for new_id, old_id in enumerate(big, start=1):
        lut[old_id] = new_id
    clab = lut[clab]
    clusters = list(range(1, len(big) + 1))

    raw: Dict[Tuple[int, int], np.ndarray] = {}
    xy: Dict[Tuple[int, int], Tuple[int, int]] = {}
    GAP = 1000  # keeps cluster coordinate spaces non-adjacent

    for k, ci in enumerate(clusters):
        cm = (clab == ci) & poly
        cys, cxs = np.where(cm)
        bx0, bx1, by0, by1 = cxs.min(), cxs.max(), cys.min(), cys.max()
        n_r = (by1 - by0) // pitch + 2
        n_c = (bx1 - bx0) // pitch + 2

        def cell_at(cyy, cxx):
            if not (by0 <= cyy <= by1 and bx0 <= cxx <= bx1):
                return None
            if clab[cyy, cxx] != ci:        # must be inside *this* piece
                return None
            wf, cov, dom = _slot(a, cyy, cxx, rad)
            if not _is_cell(wf, cov) or dom.max() - dom.min() > 100:
                return None  # white/gap/mixed, or a saturated tag marker
            return dom

        best = (-1.0, 0, 0)
        for oy in range(0, pitch, step):
            for ox in range(0, pitch, step):
                score = 0.0
                for i in range(n_r):
                    cyy = by0 + oy + int((i + 0.5) * pitch)
                    for j in range(n_c):
                        cxx = bx0 + ox + int((j + 0.5) * pitch)
                        if cell_at(cyy, cxx) is not None:
                            score += 1
                if score > best[0]:
                    best = (score, ox, oy)
        _, ox, oy = best

        local = {}
        for i in range(n_r):
            cyy = by0 + oy + int((i + 0.5) * pitch)
            for j in range(n_c):
                cxx = bx0 + ox + int((j + 0.5) * pitch)
                dom = cell_at(cyy, cxx)
                if dom is not None:
                    local[(i, j)] = (dom, (cxx, cyy))
        if not local:
            continue
        rmn = min(r for r, _ in local)
        cmn = min(c for _, c in local)
        for (i, j), (dom, ctr) in local.items():
            key = (k * GAP + i - rmn, j - cmn)
            raw[key] = dom
            xy[key] = ctr

    cells = sorted(raw.keys())

    # ---- regions: connected components of equal-colour cells ------------
    # (handles same-colour regions that are spatially apart, and the
    # disconnected board clusters of hard puzzles)
    region_of: Dict[Tuple[int, int], int] = {}
    rid = 0
    for start in cells:
        if start in region_of:
            continue
        stack = [start]
        region_of[start] = rid
        while stack:
            r, c = stack.pop()
            for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if (nb in raw and nb not in region_of
                        and np.linalg.norm(raw[nb] - raw[(r, c)])
                        < SAME_REGION_T):
                    region_of[nb] = rid
                    stack.append(nb)
        rid += 1

    rids = sorted(set(region_of.values()))
    rep = {k: np.mean([raw[c] for c in cells if region_of[c] == k], axis=0)
           for k in rids}
    # a region with no constraint tag is warm, bright and low-chroma
    free = {
        k for k, r in rep.items()
        if (r[0] >= r[2] - 4) and (r.max() - r.min() < 30) and r.min() > 170
    }

    # ---- tags & constraints --------------------------------------------
    # A region's fill is its tag colour alpha-blended over a beige base, so
    # it sits on the segment [base, tag_colour]; combine that colour test
    # with spatial proximity (multiple regions can share a tag colour).
    free_cols = [raw[c] for c in cells if region_of[c] in free]
    base = (np.mean(free_cols, axis=0) if free_cols
            else np.array([220.0, 204.0, 196.0]))

    # Tag detection.  Normally each tag is its own connected component
    # of saturated pixels, but at small (mobile) scales a tag can get
    # pixel-connected to its region's dashed border and gluing several
    # tags into one super-blob.  We split such super-blobs by filling
    # the glyph holes (closing), eroding to break thin connections
    # between tags, and re-growing each seed inside its own bbox.
    rec = GlyphRecognizer()
    sat_mask = (sat > TAG_SAT) & board
    tlab, tn = ndimage.label(sat_mask)

    def _tag_candidates_from_super(blob: np.ndarray):
        K = max(7, pitch // 10)
        closed = ndimage.binary_closing(blob, structure=np.ones((K, K)))
        E = max(3, pitch // 22)
        seeds = ndimage.binary_erosion(closed, iterations=E)
        sl, sn_ = ndimage.label(seeds)
        for sid in range(1, sn_ + 1):
            seed = sl == sid
            ys_, xs_ = np.where(seed)
            if ys_.size < max(40, th["tag_min"] // 10):
                continue
            sy0, sy1, sx0, sx1 = ys_.min(), ys_.max(), xs_.min(), xs_.max()
            ipad = E + 14                # generous box so the tag's
            Y0 = max(0, sy0 - ipad)       # full body (and glyph) survive
            Y1 = min(H, sy1 + ipad + 1)
            X0 = max(0, sx0 - ipad)
            X1 = min(W, sx1 + ipad + 1)
            local = np.zeros_like(blob)
            local[Y0:Y1, X0:X1] = True
            grown = ndimage.binary_dilation(seed, iterations=E + 2)
            yield grown & sat_mask & local

    found = []  # (constraint, solid_colour, (cx, cy), bbox)
    for t in range(1, tn + 1):
        blob = tlab == t
        sz = int(blob.sum())
        if sz < th["tag_min"]:
            continue
        masks = ([blob] if sz <= th["tag_max"]
                 else list(_tag_candidates_from_super(blob)))
        for tag_mask in masks:
            tys, txs = np.where(tag_mask)
            if not (th["tag_min"] <= tys.size <= th["tag_max"]):
                continue
            ty0, ty1 = int(tys.min()), int(tys.max())
            tx0, tx1 = int(txs.min()), int(txs.max())
            tw, td = tx1 - tx0 + 1, ty1 - ty0 + 1
            if max(tw, td) > 2.2 * min(tw, td):
                continue
            pad = 4
            Y0c = max(0, ty0 - pad); Y1c = min(H, ty1 + pad + 1)
            X0c = max(0, tx0 - pad); X1c = min(W, tx1 + pad + 1)
            cons = rec.recognize(isolate_glyph(
                a[Y0c:Y1c, X0c:X1c], tag_mask[Y0c:Y1c, X0c:X1c]))
            if cons.kind is ConstraintKind.NONE:
                continue                  # empty-glyph -> not a real tag
            solid = np.median(a[tag_mask], axis=0)
            found.append((cons, solid, (txs.mean(), tys.mean()),
                          (tx0, ty0, tx1, ty1)))

    # Optimal tag<->region assignment.  Cost combines the colour residual
    # to the [beige, tag] blend line with the spatial gap from the tag to
    # the region (in pitch units).  Colour separates differently-hued
    # neighbours; proximity separates regions that share a tag colour.
    constrained = [k for k in rids if k not in free]
    cost = np.full((len(found), len(constrained)), 1e6)
    for ti, (_, solid, (tcx, tcy), _) in enumerate(found):
        for ki, k in enumerate(constrained):
            cres = _seg_dist(rep[k], base, solid)
            if cres > COLOR_TOL:
                continue                      # different hue -> forbidden
            d = min(((xy[c][0] - tcx) ** 2 + (xy[c][1] - tcy) ** 2) ** 0.5
                    for c in cells if region_of[c] == k)
            cost[ti, ki] = cres + 10.0 * (d / pitch)
    constraints: Dict[int, Constraint] = {}
    tag_region: Dict[int, int] = {}
    if found and constrained:
        rows, cidx = linear_sum_assignment(cost)
        for ti, ki in zip(rows, cidx):
            if cost[ti, ki] < 1e6:
                constraints[constrained[ki]] = found[ti][0]
                tag_region[ti] = constrained[ki]
    tag_dbg = [
        (found[ti][3], found[ti][0].describe(), tag_region.get(ti))
        for ti in range(len(found))
    ]

    regions: Dict[int, Region] = {}
    for k in rids:
        regions[k] = Region(
            rid=k, constraint=constraints.get(k, Constraint(ConstraintKind.NONE)),
            cells=[c for c in cells if region_of[c] == k],
            color=tuple(int(v) for v in rep[k]),
        )

    dominoes = _parse_dominoes(a, s, pitch)
    puzzle = Puzzle(cells=cells, region_of=region_of,
                    regions=regions, dominoes=dominoes)

    from .render import render_puzzle
    dbg = dict(separator=s, pitch=pitch, n_clusters=len(clusters),
               tags=tag_dbg, base=tuple(int(v) for v in base),
               n_free=len(free), n_regions=len(rids),
               ascii=render_puzzle(puzzle))
    return ParseResult(puzzle=puzzle, debug=dbg)
