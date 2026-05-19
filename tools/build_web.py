"""Assemble the GitHub Pages site in ``docs/``.

The browser app runs the *unmodified* ``pips`` package under Pyodide, so
this just copies the Python sources, the glyph templates and the example
screenshots next to the static front-end.  Run after changing ``pips/``.
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")

PKG_FILES = [
    "__init__.py", "model.py", "parser.py", "solver.py",
    "glyphs.py", "render.py", "webapi.py", "_glyph_templates.json",
]
PUZZLES = ["easy-example.png", "medium-example.png",
           "hard-example.png", "hard-example-2.png"]


def main() -> None:
    pkg_dst = os.path.join(DOCS, "pysrc", "pips")
    os.makedirs(pkg_dst, exist_ok=True)
    for f in PKG_FILES:
        shutil.copy(os.path.join(ROOT, "pips", f),
                    os.path.join(pkg_dst, f))

    pz_dst = os.path.join(DOCS, "puzzles")
    os.makedirs(pz_dst, exist_ok=True)
    for f in PUZZLES:
        shutil.copy(os.path.join(ROOT, "example-screenshots", f),
                    os.path.join(pz_dst, f))

    # manifest the front-end fetches to populate the Pyodide filesystem
    with open(os.path.join(DOCS, "pysrc", "manifest.json"), "w") as fh:
        json.dump(PKG_FILES, fh)

    # GitHub Pages runs Jekyll, which drops files starting with "_"
    # (our _glyph_templates.json).  Disable it.
    open(os.path.join(DOCS, ".nojekyll"), "w").close()

    print(f"web assets written to {DOCS}/ "
          f"({len(PKG_FILES)} pkg files, {len(PUZZLES)} puzzles)")


if __name__ == "__main__":
    main()
