#!/usr/bin/env python3
"""reduce_ami.py — stage-3 forces from the rotating-mesh (AMI) runs, against the MRF and the balance.

Per run (directory name L<level>-<layers>_<mode>_<fwd|rev>_<rpm>): time averages from revolution AVG (default 8)
to the end of
  rotor thrust   T = -Fz(blades + hub) in the run's direction (+ = air pushed the way the rotor blows)
  rotor torque   Q = |Mz(blades + hub)|
  balance        -(Fz of blades, hub, motor, cup, scale, board) / g, in gf (+ = reading rises)
and the same quantities per revolution, to show how settled the average is.

Usage:  python3 cfd/cases/reduce_ami.py <runs/ami copy> [--avg 8] [--out twin/data/cfd/ami_runs.json]
        (copy only postProcessing/*/*/{force,moment}.dat)
"""
import argparse
import glob
import json
import os
import re

import numpy as np

G = 9.80665
WEIGHED = ("blades", "hub", "motor", "cup", "scale", "board")


def load(pp, part, what):
    rows = []
    for p in sorted(glob.glob(os.path.join(pp, part, "*", what + ".dat"))):     # restarts write a new time directory
        rows += [[float(x) for x in l.split()] for l in open(p) if l.strip() and not l.startswith("#")]
    a = np.array(rows)
    a = a[np.argsort(a[:, 0], kind="stable")]
    _, keep = np.unique(a[::-1, 0], return_index=True)                         # a restart repeats times: keep the last
    return a[len(a) - 1 - keep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--avg", type=float, default=8)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "twin", "data", "cfd", "ami_runs.json"))
    a = ap.parse_args()
    out = []
    for d in sorted(glob.glob(os.path.join(a.runs, "L*_*_*_*"))):
        m = re.match(r"L(\w+)-(\w+)_(\w+)_(fwd|rev)_(\d+)$", os.path.basename(d))
        if not m:
            continue
        rpm, sgn = int(m[5]), 1 if m[4] == "fwd" else -1
        pp = os.path.join(d, "postProcessing")
        F = {k: load(pp, k, "force") for k in WEIGHED + ("rotor",)}
        M = load(pp, "rotor", "moment")
        t = F["rotor"][:, 0]
        for k in WEIGHED:                                                       # common time axis
            F[k] = np.interp(t, F[k][:, 0], F[k][:, 3])
        Trev = 60.0 / rpm
        rev = t / Trev
        thrust = -sgn * F["rotor"][:, 3] / G * 1e3
        torque = np.abs(np.interp(t, M[:, 0], M[:, 3])) * 1e6
        bal = -sum(F[k] for k in WEIGHED) / G * 1e3
        w = rev >= a.avg
        per_rev = []
        for i in range(int(rev[-1])):
            s = (rev >= i) & (rev < i + 1)
            per_rev.append(dict(rev=i + 1, thrust_gf=round(float(thrust[s].mean()), 4), balance_gf=round(float(bal[s].mean()), 4),
                                torque_uNm=round(float(torque[s].mean()), 2)))
        out.append(dict(name=os.path.basename(d), mesh="%s-%s" % (m[1], m[2]), mode=m[3], rpm=rpm, dir=sgn,
                        revolutions=round(float(rev[-1]), 2), avg_from_rev=a.avg,
                        thrust_gf=round(float(thrust[w].mean()), 4), thrust_std_gf=round(float(thrust[w].std()), 4),
                        torque_uNm=round(float(torque[w].mean()), 2),
                        balance_gf=round(float(bal[w].mean()), 4), balance_std_gf=round(float(bal[w].std()), 4),
                        balance_parts_gf={k: round(float(-F[k][w].mean() / G * 1e3), 4) for k in WEIGHED},
                        per_revolution=per_rev))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(dict(source="cfd/cases/ami (pimpleFoam, rotating AMI mesh, time average from revolution %g)" % a.avg, runs=out),
              open(a.out, "w"), indent=1)
    for r in out:
        print("%-24s %5.1f rev | T %.3f gf (sd %.3f) | Q %.1f uN.m | bal %.3f gf (sd %.3f)" % (
            r["name"], r["revolutions"], r["thrust_gf"], r["thrust_std_gf"], r["torque_uNm"], r["balance_gf"], r["balance_std_gf"]))
        print("   parts", r["balance_parts_gf"])
        print("   per rev bal", [p["balance_gf"] for p in r["per_revolution"]])
        print("   per rev T  ", [p["thrust_gf"] for p in r["per_revolution"]])


if __name__ == "__main__":
    main()
