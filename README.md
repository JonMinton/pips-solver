# pips-solver

Solve [NYT Pips](https://www.nytimes.com/games/pips) puzzles directly from a
screenshot — no manual transcription.

A Pips puzzle is a constrained-optimisation problem: an irregular board of
cells, grouped into coloured regions each carrying a constraint (a target
sum, `<N`/`>N`, "all equal" `=`, or "all different" `≠`), must be fully
tiled with a given multiset of dominoes (each domino covers two
orthogonally-adjacent cells).

This project has two parts.

### 1. Image parser — `pips/parser.py`, `pips/glyphs.py`

A classical computer-vision pipeline (no ML, no network):

1. find the thin separator rule between the board and the domino tray;
2. recover the cell **pitch** from the periodic inter-cell valleys
   (autocorrelation — scale-robust) and lock the lattice **phase** by
   maximising solid-tile coverage, so it handles irregular polyomino
   boards;
3. classify each lattice slot by colour (white = hole, a warm low-chroma
   beige = a free cell, otherwise a coloured region) and cluster the
   region colours;
4. detect the saturated tag markers, isolate and recognise each white
   constraint glyph against a template library, and attach it to its
   region using the fact that a region's fill is its tag colour
   alpha-blended over beige (so the fill lies on the segment
   `[beige, tag colour]`);
5. read the tray by counting pip blobs in each half-tile.

The glyph templates are built once from the screenshots by
`tools/build_templates.py` and committed as `pips/_glyph_templates.json`.

### 2. Energy-model solver — `pips/solver.py`

Every region constraint contributes an **energy**: zero exactly when
satisfied, growing with the distance to satisfaction
(`Constraint.violation`). A valid solution has total energy 0. The solver
walks domino tilings depth-first and keeps an *admissible lower bound* on
the energy each region can still reach given the cells already filled; a
branch is pruned the moment any region can no longer reach 0. This makes
the search both exact and fast.

## Usage

```bash
pip install -r requirements.txt
python solve.py example-screenshots/easy-example.png --debug
python solve.py example-screenshots/medium-example.png
pytest -q                       # end-to-end acceptance tests
```

## Status

Validated end to end against both example screenshots
(`tests/test_examples.py`): the parser reads the exact board, every
constraint and every domino, and the solver returns an **independently
verified** energy-0 solution (`verify_solution` re-checks tiling, the
domino multiset and all constraints). Solve time is sub-millisecond
(easy) to ~20 ms (medium); parsing a screenshot takes a couple of seconds.

### Scope / extending

The template library currently covers the glyphs present in the two
example screenshots (`5 6 8 9 < = ≠`). Other digits or `>` would just
need adding to `tools/build_templates.py` and rebuilding. The CV
thresholds assume the standard NYT Pips rendering.
