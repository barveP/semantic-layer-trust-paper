"""Result-set comparison shared by the gates and (later) the grader.

Rules (draft; frozen with the grader):
- Row order is ignored unless `ordered` is set.
- Column names are ignored; column order is ignored (columns are matched by trying
  every permutation of the candidate's columns, which is cheap for <= 4 columns).
- Numbers compare with math.isclose(rel_tol, abs_tol); everything else compares as str.
"""
import itertools
import math
from decimal import Decimal

REL_TOL = 1e-9
ABS_TOL = 1e-9


def _norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    return str(v)


def _key(row):
    # Sort key that keeps numbers and strings apart and puts None first.
    return tuple((0, 0.0, "") if v is None else (1, v, "") if isinstance(v, float) else (2, 0.0, v)
                 for v in row)


def _close(a, b, rel_tol, abs_tol):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)
    return a == b


def same_result(rows_a, rows_b, ordered=False, rel_tol=REL_TOL, abs_tol=ABS_TOL):
    a = [tuple(_norm(v) for v in r) for r in rows_a]
    b = [tuple(_norm(v) for v in r) for r in rows_b]
    if len(a) != len(b):
        return False
    if not a:
        return True
    if len(a[0]) != len(b[0]):
        return False
    if not ordered:
        a = sorted(a, key=_key)
    for perm in itertools.permutations(range(len(b[0]))):
        bp = [tuple(r[i] for i in perm) for r in b]
        if not ordered:
            bp = sorted(bp, key=_key)
        if all(_close(x, y, rel_tol, abs_tol) for ra, rb in zip(a, bp) for x, y in zip(ra, rb)):
            return True
    return False
