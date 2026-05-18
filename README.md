# pips-solver

Solve [NYT Pips](https://www.nytimes.com/games/pips) puzzles directly from a
screenshot.

Pips puzzles are a constrained-optimisation problem: an irregular board of
cells, grouped into coloured regions each carrying a constraint (a target
sum, `<N`/`>N`, "all equal" `=`, or "all different" `≠`), must be fully
tiled with a given multiset of dominoes.

This project has two parts:

1. **Image parser** (`pips/parser.py`, `pips/glyphs.py`) — a classical
   computer-vision pipeline (no ML, no network) that turns a screenshot
   into a `Puzzle`: it finds the board, infers the cell lattice, segments
   regions by colour, reads each region's constraint glyph, and counts the
   pips on every domino in the tray.
2. **Energy-model solver** (`pips/solver.py`) — every region constraint
   contributes an *energy* that is zero exactly when satisfied and grows
   with the distance to satisfaction. The solver searches domino tilings,
   using the energy as both the objective and an admissible pruning bound,
   so it is exact (it returns an energy-0 solution) and fast.

## Usage

```bash
pip install -r requirements.txt
python solve.py example-screenshots/easy-example.png
python solve.py example-screenshots/medium-example.png --debug
```

## Status

See `tests/test_examples.py` — the parser + solver are validated end to end
against the two example screenshots.
