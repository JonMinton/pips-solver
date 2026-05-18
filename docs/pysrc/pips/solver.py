"""Energy model and the energy-guided exact solver.

Every region constraint contributes an *energy*: zero exactly when the
constraint is satisfied, and a positive penalty that grows with the
distance to satisfaction (see ``Constraint.violation``).  A valid Pips
solution is an assignment of total energy 0.

The solver walks domino tilings of the board with depth-first search.
For each region it keeps an *admissible lower bound* on the energy still
achievable given the cells already filled (a partially-filled SUM region
can only reach a window of totals; ALL_EQUAL/ALL_DIFFERENT can only get
worse).  A branch is pruned the instant any region's lower bound exceeds
0 — it can no longer reach energy 0 — which makes the exact search fast.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Tuple

from .model import Cell, ConstraintKind, Puzzle, Solution

PIPS = range(0, 7)  # a domino half shows 0..6


class EnergyModel:
    """Scores any (partial or complete) value assignment."""

    def __init__(self, puzzle: Puzzle):
        self.puzzle = puzzle

    def energy(self, value: Dict[Cell, int]) -> int:
        total = 0
        for region in self.puzzle.regions.values():
            vals = [value[c] for c in region.cells if c in value]
            if len(vals) == len(region.cells):
                total += region.constraint.violation(vals)
        return total

    # ---- admissible per-region lower bound on remaining energy ---------
    @staticmethod
    def region_feasible(kind: ConstraintKind, target: Optional[int],
                         assigned: List[int], n_remaining: int) -> bool:
        """Can this region still reach zero energy?"""
        if kind is ConstraintKind.NONE:
            return True
        if kind is ConstraintKind.ALL_EQUAL:
            return len(set(assigned)) <= 1
        if kind is ConstraintKind.ALL_DIFFERENT:
            return len(set(assigned)) == len(assigned)
        cur = sum(assigned)
        lo, hi = cur, cur + 6 * n_remaining
        if kind is ConstraintKind.SUM_EQ:
            return lo <= target <= hi
        if kind is ConstraintKind.SUM_LT:
            return lo <= target - 1
        if kind is ConstraintKind.SUM_LE:
            return lo <= target
        if kind is ConstraintKind.SUM_GT:
            return hi >= target + 1
        if kind is ConstraintKind.SUM_GE:
            return hi >= target
        raise AssertionError(kind)


class _Search:
    def __init__(self, puzzle: Puzzle):
        self.p = puzzle
        self.cells = sorted(puzzle.cells)
        self.cellset = set(self.cells)
        self.region_of = puzzle.region_of
        self.regions = puzzle.regions
        # per-region running state
        self.r_vals: Dict[int, List[int]] = {rid: [] for rid in self.regions}
        self.r_remaining: Dict[int, int] = {
            rid: len(reg.cells) for rid, reg in self.regions.items()
        }
        self.avail: Counter = Counter(
            tuple(sorted(d)) for d in puzzle.dominoes
        )
        self.value: Dict[Cell, int] = {}
        self.placements: List[Tuple[Cell, Cell, Tuple[int, int]]] = []

    def _assign(self, cell: Cell, v: int) -> bool:
        rid = self.region_of[cell]
        self.value[cell] = v
        self.r_vals[rid].append(v)
        self.r_remaining[rid] -= 1
        reg = self.regions[rid]
        return EnergyModel.region_feasible(
            reg.constraint.kind, reg.constraint.target,
            self.r_vals[rid], self.r_remaining[rid],
        )

    def _unassign(self, cell: Cell) -> None:
        rid = self.region_of[cell]
        self.r_vals[rid].pop()
        self.r_remaining[rid] += 1
        del self.value[cell]

    def _first_free(self) -> Optional[Cell]:
        for c in self.cells:
            if c not in self.value:
                return c
        return None

    def solve(self) -> Optional[Solution]:
        u = self._first_free()
        if u is None:
            return Solution(value=dict(self.value),
                            placements=list(self.placements), energy=0)
        r, c = u
        for v in ((r + 1, c), (r, c + 1), (r - 1, c), (r, c - 1)):
            if v not in self.cellset or v in self.value:
                continue
            for shape in list(self.avail):
                if self.avail[shape] == 0:
                    continue
                a, b = shape
                orients = {(a, b), (b, a)}
                self.avail[shape] -= 1
                for va, vb in orients:
                    ok = self._assign(u, va)
                    if ok:
                        ok = self._assign(v, vb)
                        if ok:
                            self.placements.append((u, v, (va, vb)))
                            res = self.solve()
                            if res is not None:
                                return res
                            self.placements.pop()
                        self._unassign(v)
                    self._unassign(u)
                self.avail[shape] += 1
        return None


def solve(puzzle: Puzzle) -> Optional[Solution]:
    """Return an energy-0 solution, or ``None`` if the puzzle is infeasible."""
    puzzle.validate()
    return _Search(puzzle).solve()


def verify_solution(puzzle: Puzzle, sol: Solution) -> None:
    """Independently check that ``sol`` is a legitimate Pips solution.

    Raises ``AssertionError`` on any violation.  This does not trust the
    search: it re-checks tiling, the domino multiset, and every constraint.
    """
    covered: Dict[Cell, int] = {}
    for ca, cb, (va, vb) in sol.placements:
        assert ca in puzzle.region_of and cb in puzzle.region_of, "off-board"
        assert cb in puzzle.neighbors(ca), f"{ca},{cb} not adjacent"
        assert ca not in covered and cb not in covered, "cell covered twice"
        covered[ca], covered[cb] = va, vb
    assert set(covered) == set(puzzle.cells), "not every cell is covered"
    assert covered == sol.value, "value map disagrees with placements"

    used = Counter(tuple(sorted((va, vb))) for _, _, (va, vb) in sol.placements)
    assert used == Counter(tuple(sorted(d)) for d in puzzle.dominoes), \
        "domino multiset not used exactly"

    total = EnergyModel(puzzle).energy(sol.value)
    assert total == 0 and sol.energy == 0, f"non-zero energy {total}"
