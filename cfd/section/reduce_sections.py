#!/usr/bin/env python3
"""reduce_sections.py — stage-1 polars from the forceCoeffs histories of the section runs.

For each case: the mean and standard deviation of Cl, Cd, Cm(0.25c) over convective times 6-16, and the change
of the mean between the halves 6-11 and 11-16 (how settled the average is).

Usage:  python3 cfd/section/reduce_sections.py <runs/sections copy> [--out twin/data/cfd/section_polars.json]
        (copy only the small files from rikyu:  rsync -a --include '*/' --include 'coefficient.dat' --exclude '*')
"""
import argparse
import glob
import json
import os
import re

import numpy as np

T0, T1, TM = 6.0, 16.0, 11.0


def load(path):
    names, rows = None, []
    for line in open(path):
        if line.startswith("#"):
            h = line[1:].split()
            if h and h[0] == "Time":
                names = h
            continue
        rows.append([float(x) for x in line.split()])
    return names, np.array(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "twin", "data", "cfd", "section_polars.json"))
    a = ap.parse_args()
    cases = []
    for d in sorted(glob.glob(os.path.join(a.runs, "re*_t*_f*_a*"))):
        m = re.match(r"re(\d+)_t(\d+)_f(\d+)_a([+-]\d+)$", os.path.basename(d))
        files = sorted(glob.glob(os.path.join(d, "postProcessing", "coeffs", "*", "coefficient*.dat")))
        if not m or not files:
            continue
        names, D = None, []
        for p in files:                                   # restarts write a new time directory
            names, x = load(p)
            D.append(x)
        D = np.concatenate(D)
        D = D[np.argsort(D[:, 0], kind="stable")]
        t = D[:, 0]
        col = {n: D[:, names.index(n)] for n in ("Cl", "Cd", "CmPitch") if n in names}
        row = dict(re=int(m[1]), t=int(m[2]) / 1000, f=int(m[3]) / 1000, alpha=int(m[4]), t_end=round(float(t[-1]), 3))
        w, w1, w2 = (t >= T0) & (t <= T1), (t >= T0) & (t < TM), (t >= TM) & (t <= T1)
        if w.sum() < 10 or t[-1] < T1 - 0.05:              # still running: no partial averages in the table
            row["incomplete"] = True
        else:
            for n, v in col.items():
                key = {"CmPitch": "cm"}.get(n, n.lower())
                row[key] = round(float(v[w].mean()), 5)
                row[key + "_std"] = round(float(v[w].std()), 5)
                if w2.sum() > 10:
                    row[key + "_drift"] = round(float(v[w2].mean() - v[w1].mean()), 5)
        cases.append(row)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(dict(source="cfd/section (pimpleFoam LES WALE, 2.5D, span 0.2 c, averaged over t U/c = 6-16)",
                   cases=cases), open(a.out, "w"), indent=0)
    print("%d cases -> %s" % (len(cases), a.out))
    for r in cases:
        print("Re %5d t %.2f f %.2f a %+3d  cl %s cd %s" % (r["re"], r["t"], r["f"], r["alpha"], r.get("cl"), r.get("cd")))


if __name__ == "__main__":
    main()
