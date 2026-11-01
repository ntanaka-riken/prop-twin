"""geom.py — the blade section as a polygon for the PINN scripts (numpy only; the outline is make_section.surface)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "section"))
from make_section import surface  # noqa: E402

X0, X1, Y0, Y1 = -2.0, 4.0, -2.0, 2.0        # the PINN domain (chord lengths)


def wall_loop(t, f):
    """the section outline as a closed polygon (clockwise), its outward unit normals and segment lengths."""
    up, te, lo, le = surface(t, f, 0.0, npts=400)
    loop = np.array(up + te[1:] + lo[1:] + le[1:-1])
    nxt = np.roll(loop, -1, axis=0)
    d = nxt - loop
    ds = np.hypot(d[:, 0], d[:, 1])
    n = np.stack([-d[:, 1], d[:, 0]], 1) / ds[:, None]          # clockwise loop: (-dy, dx) points out of the body
    mid = 0.5 * (loop + nxt)
    return loop, mid, n, ds


def inside(pts, poly):
    """even-odd ray casting, chunked."""
    res = np.zeros(len(pts), bool)
    px, py = poly[:, 0], poly[:, 1]
    qx, qy = np.roll(px, -1), np.roll(py, -1)
    for i in range(0, len(pts), 20000):
        x, y = pts[i:i + 20000, :1], pts[i:i + 20000, 1:]
        cond = (py > y) != (qy > y)
        xint = px + (y - py) * (qx - px) / np.where(qy == py, 1e-30, qy - py)
        res[i:i + 20000] = (cond & (x < xint)).sum(1) % 2 == 1
    return res
