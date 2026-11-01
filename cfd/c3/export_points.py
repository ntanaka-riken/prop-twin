#!/usr/bin/env python3
"""export_points.py — point data for the C3 PINN from an OpenFOAM wedge run (make_axi.py): data pool and test set.

Reads the latest time of CASE (ascii C from `postProcess -func writeCellCentres`, U, p) and keeps the cells within
r < 0.12 m, z < 0.25 m (the cup, the rotor and the wake). Shuffled, the first --pool cells are the data pool (the PINN
takes the first n), the next --test cells are the test set it never sees.
  pool_rz, test_rz   (r, z) in m
  pool_v, test_v     u_r, u_theta, u_z (m/s), p (Pa, gauge to the room)

Usage:  python3 cfd/c3/export_points.py <case copy> <out.npz> [--pool 10000 --test 5000]
"""
import argparse
import glob
import os
import re

import numpy as np

RHO = 1.2


def read_field(path):
    txt = open(path).read()
    m = re.search(r"internalField\s+nonuniform\s+List<(\w+)>\s*(\d+)\s*\(", txt)
    n, i = int(m.group(2)), m.end()
    body = txt[i:txt.index("\n)", i)]
    if m.group(1) == "vector":
        return np.array(re.findall(r"\(([^)]*)\)", body), dtype=object)[:n].astype(str), n
    return np.array(body.split()[:n], float), n


def vectors(path):
    rows, n = read_field(path)
    return np.array([r.split() for r in rows], float)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("out")
    ap.add_argument("--pool", type=int, default=10000)
    ap.add_argument("--test", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    t = max((d for d in glob.glob(os.path.join(a.case, "[0-9]*")) if os.path.exists(os.path.join(d, "C"))),
            key=lambda d: float(os.path.basename(d)))
    C, U = vectors(os.path.join(t, "C")), vectors(os.path.join(t, "U"))
    p = read_field(os.path.join(t, "p"))[0] * RHO
    r = np.hypot(C[:, 0], C[:, 1])
    keep = np.where((r < 0.12) & (C[:, 2] < 0.25))[0]
    keep = np.random.default_rng(a.seed).permutation(keep)
    rz = np.stack([r, C[:, 2]], 1)
    v = np.concatenate([U, p[:, None]], 1)
    P, T = keep[:a.pool], keep[a.pool:a.pool + a.test]
    np.savez_compressed(a.out, pool_rz=rz[P], pool_v=v[P], test_rz=rz[T], test_v=v[T], time=os.path.basename(t))
    print("%s: time %s, %d cells in the region, pool %d, test %d" % (a.case, os.path.basename(t), len(keep), len(P), len(T)))


if __name__ == "__main__":
    main()
