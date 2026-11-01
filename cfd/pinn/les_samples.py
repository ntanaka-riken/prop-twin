#!/usr/bin/env python3
"""les_samples.py — point data from the stage-1 LES mean field, for PINN task C6 (PINN with sparse data).

  dict     write an OpenFOAM function-object file that samples UMean, pMean at a cloud of points: a training pool
           (half uniform in the PINN domain, half within 0.3 c of the section), a separate test set, and points just
           off the wall; each at 8 spanwise planes, averaged later (the LES is 2.5D)
  collect  read the sampled raw file and write an npz: xy, u, v, p for the pool, the test set and the wall

Usage:
  python3 les_samples.py dict --t 0.03 --f 0.03 --out system/sampleLES        (then in the case:
      srun -n 36 postProcess -parallel -latestTime -dict system/sampleLES)
  python3 les_samples.py collect <postProcessing/sampleLES/<time>/pts_pMean_UMean.xy> --out les_points.npz
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geom import X0, X1, Y0, Y1, inside, wall_loop  # noqa: E402

N_POOL, N_TEST, N_WALL, ZS = 20000, 5000, 400, [0.0125 + 0.025 * k for k in range(8)]


def points(t, f, seed=1):
    rng = np.random.default_rng(seed)
    poly, mid, nrm, ds = wall_loop(t, f)

    def draw(n):
        a = rng.uniform([X0, Y0], [X1, Y1], (n, 2))
        k = rng.choice(len(mid), n, p=ds / ds.sum())
        b = mid[k] + (0.003 + 0.3 * rng.uniform(0, 1, n) ** 2)[:, None] * nrm[k]
        xy = np.concatenate([a, b])
        xy = xy[~inside(xy, poly)]
        return xy[rng.permutation(len(xy))][:n]
    pool, test = draw(N_POOL), draw(N_TEST)
    k = np.linspace(0, len(mid) - 1, N_WALL).astype(int)
    wall = mid[k] + 2e-4 * nrm[k]
    return dict(pool=pool, test=test, wall=wall)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("dict", "collect"))
    ap.add_argument("raw", nargs="?")
    ap.add_argument("--t", type=float, default=0.03)
    ap.add_argument("--f", type=float, default=0.03)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    P = points(a.t, a.f)
    allxy = np.concatenate([P["pool"], P["test"], P["wall"]])
    if a.mode == "dict":
        pts = "\n".join("(%.7f %.7f %.5f)" % (x, y, z) for z in ZS for x, y in allxy)
        txt = ("FoamFile { version 2.0; format ascii; class dictionary; object sampleLES; }\n"
               "functions\n{\n    sampleLES\n    {\n        type sets; libs (sampling); interpolationScheme cellPoint; setFormat raw;\n"
               "        fields (pMean UMean);\n        sets\n        {\n            pts { type cloud; axis xyz; points (\n%s\n); }\n"
               "        }\n    }\n}\n" % pts)
        open(a.out, "w").write(txt)
        print("%d points x %d planes -> %s" % (len(allxy), len(ZS), a.out))
        return
    raw = np.loadtxt(a.raw)                                   # x y z pMean UMean_x UMean_y UMean_z
    key = {(round(x, 5), round(y, 5)): i for i, (x, y) in enumerate(allxy)}
    acc = np.zeros((len(allxy), 4)); n = np.zeros(len(allxy))
    for r in raw:
        i = key.get((round(r[0], 5), round(r[1], 5)))
        if i is not None:
            acc[i] += [r[4], r[5], r[3], 1.0][:3] + [0.0]; n[i] += 1
    ok = n > 0
    val = np.full((len(allxy), 3), np.nan)
    val[ok] = acc[ok, :3] / n[ok, None]
    out, i0 = {}, 0
    for name in ("pool", "test", "wall"):
        m = len(P[name])
        sel = slice(i0, i0 + m); good = ok[sel]
        out[name + "_xy"] = P[name][good]
        out[name + "_uvp"] = val[sel][good]
        print("%s: %d of %d points sampled" % (name, good.sum(), m))
        i0 += m
    np.savez_compressed(a.out, **out)
    print(a.out)


if __name__ == "__main__":
    main()
