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
pytest -q                       # per-image parser + solver unit tests
sh tools/install_hooks.sh       # one-off: arm the pre-deploy test gate
```

## Tests & the pre-deploy gate

Every example screenshot has two unit tests in `tests/test_examples.py`:
a **parser test** (exact cell count, domino multiset and region
constraints) and a **solver test** (an independently-verified energy-0
solution with the exact solved cell values). The expected output for
each image is an explicit golden file in `tests/expected/` — regenerate
with `python tools/build_test_expectations.py` when a behaviour change
is intentional.

These run automatically **before every deployment**: a push to `origin`
is what triggers the GitHub Pages build, so the `.githooks/pre-push`
hook runs `tools/run_pre_deploy_tests.py` first. If any test fails the
push is blocked, a failure record is written to `test-results/`
(`latest.md` / `latest.json` plus a timestamped copy) and a summary is
printed. Arm the hook once per clone with `sh tools/install_hooks.sh`.

## Daily capture (optional macro)

`tools/daily_capture_and_solve.py` is a self-contained Playwright
script that, run on your machine, opens Chromium against
`https://www.nytimes.com/games/pips`, clicks each difficulty in turn,
takes a full-page screenshot, runs the parser+solver on each, and
writes a per-day JSON report to `test-results/daily/`.

One-time setup:

```bash
pip install playwright
python -m playwright install chromium
python tools/daily_capture_and_solve.py        # *headed* the first time so
                                                # you can log in if NYT prompts
```

Subsequent runs (and the launchd job below) use `--headless`. The
browser profile persists at `.browser-profile/` so the login sticks.

To run automatically once a day on macOS, install the launchd plist:

```bash
mkdir -p ~/Library/LaunchAgents
cp tools/launchd/com.jonminton.pips-solver.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.jonminton.pips-solver.daily.plist
```

The job fires at 09:30 local each day and writes its console output
to `test-results/daily/launchd.{out,err}`. Edit the `Hour`/`Minute`
keys in the plist to change the schedule. If NYT redesigns the
difficulty buttons and the script can't find them, override with
`--easy`, `--medium`, `--hard` (any Playwright selector — CSS, text=,
role=, etc.).

## Status

Validated end to end against eight example screenshots — five desktop
(easy 8 cells/4 dominoes, medium 14/7, hard a 7-piece board 28/14,
hard·2 26/13, hard·3 30/15) and three phone screenshots
(mobile easy/medium/hard). For each one the parser reads the board and
the solver returns an **independently verified** energy-0 solution.
Two of the mobile images have one constraint tag each that the parser
reads wrong at very small scale — surfaced live by the app's Help-Me
review mode and documented in the golden files.

### Scope / extending

The glyph template library is built from the example screenshots and
covers `0`–`9` (those that appear), `< > =` and `≠`. New glyphs just
need adding to `tools/build_templates.py` and a rebuild. The CV
thresholds assume the standard NYT Pips rendering.
