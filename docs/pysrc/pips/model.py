"""Data model for a Pips puzzle.

A puzzle is an irregular board of unit cells laid on a square lattice.
Cells are grouped into coloured *regions*, each carrying a *constraint*.
The player must tile every cell with a given multiset of dominoes (each
domino covers two orthogonally-adjacent cells) so that all region
constraints are satisfied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

Cell = Tuple[int, int]  # (row, col) on the lattice


class ConstraintKind(Enum):
    """The kinds of region constraint that appear in NYT Pips."""

    NONE = "none"          # no constraint (cells still must be covered)
    SUM_EQ = "sum_eq"      # sum of pips in region == target
    SUM_LT = "sum_lt"      # sum < target
    SUM_LE = "sum_le"      # sum <= target
    SUM_GT = "sum_gt"      # sum > target
    SUM_GE = "sum_ge"      # sum >= target
    ALL_EQUAL = "all_eq"   # every cell in the region holds the same pip value
    ALL_DIFFERENT = "all_ne"  # every cell holds a distinct pip value


@dataclass(frozen=True)
class Constraint:
    kind: ConstraintKind
    target: Optional[int] = None  # only used by the SUM_* kinds

    def describe(self) -> str:
        k = self.kind
        if k is ConstraintKind.NONE:
            return "(free)"
        if k is ConstraintKind.ALL_EQUAL:
            return "= (all equal)"
        if k is ConstraintKind.ALL_DIFFERENT:
            return "≠ (all different)"
        sym = {
            ConstraintKind.SUM_EQ: "=",
            ConstraintKind.SUM_LT: "<",
            ConstraintKind.SUM_LE: "≤",
            ConstraintKind.SUM_GT: ">",
            ConstraintKind.SUM_GE: "≥",
        }[k]
        return f"sum {sym} {self.target}"

    def violation(self, values: List[int]) -> int:
        """Energy contribution: 0 iff satisfied, else a positive penalty
        that grows with the distance to satisfaction (used by the energy
        model both as the objective and as a pruning bound)."""
        k = self.kind
        if k is ConstraintKind.NONE:
            return 0
        if k is ConstraintKind.ALL_EQUAL:
            if not values:
                return 0
            top = max(set(values), key=values.count)
            return sum(1 for v in values if v != top)
        if k is ConstraintKind.ALL_DIFFERENT:
            return len(values) - len(set(values))
        s = sum(values)
        t = self.target
        if k is ConstraintKind.SUM_EQ:
            return abs(s - t)
        if k is ConstraintKind.SUM_LT:
            return max(0, s - (t - 1))
        if k is ConstraintKind.SUM_LE:
            return max(0, s - t)
        if k is ConstraintKind.SUM_GT:
            return max(0, (t + 1) - s)
        if k is ConstraintKind.SUM_GE:
            return max(0, t - s)
        raise AssertionError(k)


@dataclass
class Region:
    rid: int
    constraint: Constraint
    cells: List[Cell] = field(default_factory=list)
    color: Tuple[int, int, int] = (0, 0, 0)  # representative RGB (debug)


@dataclass
class Puzzle:
    """Parsed puzzle ready to be solved."""

    cells: List[Cell]                       # every coverable cell
    region_of: Dict[Cell, int]              # cell -> region id
    regions: Dict[int, Region]              # region id -> Region
    dominoes: List[Tuple[int, int]]         # multiset of (a, b) pip pairs

    def neighbors(self, cell: Cell) -> List[Cell]:
        r, c = cell
        cand = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
        cs = set(self.cells)
        return [n for n in cand if n in cs]

    def edges(self) -> List[Tuple[Cell, Cell]]:
        """All orthogonal cell pairs a domino could occupy."""
        cs = set(self.cells)
        out = []
        for (r, c) in self.cells:
            for nb in ((r + 1, c), (r, c + 1)):
                if nb in cs:
                    out.append(((r, c), nb))
        return out

    def validate(self) -> None:
        if len(self.cells) != 2 * len(self.dominoes):
            raise ValueError(
                f"cell count {len(self.cells)} != 2 x domino count "
                f"{len(self.dominoes)}"
            )
        for cell in self.cells:
            if cell not in self.region_of:
                raise ValueError(f"cell {cell} has no region")


@dataclass
class Solution:
    """A solved board: each cell -> pip value, plus the domino placements."""

    value: Dict[Cell, int]
    placements: List[Tuple[Cell, Cell, Tuple[int, int]]]
    energy: int  # 0 for a valid solution
