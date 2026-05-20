# pips-solver

Solve [NYT Pips](https://www.nytimes.com/games/pips) puzzles directly from a
screenshot — no manual transcription.

**▶ Live web app: https://jonminton.github.io/pips-solver/**
Pick Easy / Medium / Hard / Hard·Day 2, upload a screenshot, or paste an
image URL; it shows the parsed board, the dominoes, the parse/solve times,
and a **graphical solution** — the solved board drawn as an SVG where each
domino is a rounded tile, blue for horizontal and orange for vertical. The
browser runs the *unmodified* Python parser and solver via
[Pyodide](https://pyodide.org) — no server, identical results to the CLI.

A Pips puzzle is a constrained-optimisation problem: an irregular board of
cells, grouped into coloured regions each carrying a constraint (a target
sum, `<N`/`>N`, "all equal" `=`, or "all different" `≠`), must be fully
tiled with a given multiset of dominoes (each domino covers two
orthogonally-adjacent cells).

This project has two parts.

### 1. Image parser — `pips/parser.py`, `pips/glyphs.py`

A classical computer-vision pipeline (no ML, no network):

1. find the thin separator rule between the board and the domino tray;
2. split the board into its disconnected **clusters** (a hard puzzle is
   several independent pieces that are *not* on a shared lattice),
   recover the cell **pitch** from the periodic inter-cell valleys
   (autocorrelation — scale-robust) and lock each cluster's lattice
   **phase** independently by maximising solid-tile coverage;
3. classify each lattice slot by colour (white = hole, a warm low-chroma
   beige = a free cell, otherwise a coloured region) and segment regions
   as connected components of equal-colour cells (so same-colour regions
   that are spatially apart stay distinct);
4. detect the saturated tag markers, isolate and recognise each white
   constraint glyph against a template library, and assign tags to
   regions optimally (Hungarian) on a cost that combines the
   `[beige, tag colour]` blend-line residual with spatial proximity —
   colour separates differently-hued neighbours, proximity separates
   regions that share a tag colour;
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

### 3. Web app — `docs/` (GitHub Pages)

`docs/` is a static site that loads Pyodide, pulls in numpy/scipy/Pillow
and the `pips` package, and calls `pips.webapi.run` in the browser.
Rebuild its assets after changing `pips/` with
`python tools/build_web.py`. Pages serves `main:/docs`; a `.nojekyll`
file keeps `_glyph_templates.json` from being dropped by Jekyll.

## Usage

```bash
pip install -r requirements.txt
python solve.py example-screenshots/easy-example.png --debug
python solve.py example-screenshots/medium-example.png
python solve.py example-screenshots/hard-example.png
pytest -q                       # end-to-end acceptance tests
```

## Status

Validated end to end against five example screenshots —
easy (8 cells / 4 dominoes), medium (14 / 7), hard (a 7-piece
disconnected board, 28 / 14, 19 regions), a second hard puzzle
(2 pieces, 26 / 13), and a third hard puzzle (2 pieces sharing a single
container rim, 30 / 15, 12 regions). For each one the parser reads the
exact board, every constraint and every domino, and the solver returns
an **independently verified** energy-0 solution (`verify_solution`
re-checks tiling, the domino multiset and all constraints — see
`tests/test_examples.py`, 15 tests). Solve time is a few milliseconds;
parsing a screenshot takes a couple of seconds.

### Scope / extending

The glyph template library is built from the example screenshots and
covers `0`–`9` (those that appear), `< > =` and `≠`. New glyphs just
need adding to `tools/build_templates.py` and a rebuild. The CV
thresholds assume the standard NYT Pips rendering.
