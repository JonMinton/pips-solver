"""Pips solver: parse a NYT Pips screenshot and solve it with an energy model."""
from .model import Puzzle, Region, Constraint, ConstraintKind, Solution
from .parser import parse_screenshot
from .solver import solve, verify_solution

__all__ = [
    "Puzzle",
    "Region",
    "Constraint",
    "ConstraintKind",
    "Solution",
    "parse_screenshot",
    "solve",
    "verify_solution",
]
