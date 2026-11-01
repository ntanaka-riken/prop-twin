#!/usr/bin/env python3
"""reduce_mrf.py — stage-2 forces from the MRF runs, against the balance and the BEMT.

Per run: the mean over the last 1000 iterations (and its drift from the 1000 before) of
  rotor thrust   T = -Fz(blades + hub) in the run's direction (+ = air pushed the way the rotor blows)
  rotor torque   Q = |Mz(blades + hub)|
  balance        -(Fz of blades, hub, motor, cup, scale, board) / g, in gf (+ = reading rises)

Usage:  python3 cfd/cases/reduce_mrf.py <runs/mrf copy> [--out twin/data/cfd/mrf_runs.json]
        (copy only postProcessing/*/0/{force,moment}.dat and the run list cfd/cases/mrf_runs.txt)
"""
import argparse
import json
import os

import numpy as np

G = 9.80665
HERE = os.path.dirname(os.path.abspath(__file__))
WEIGHED = ("blades", "hub", "motor", "cup", "scale", "board")
THRUST = dict([(3067, 1.675), (2184, 0.735), (1592, 0.385), (1190, 0.200), (695, 0.055)])   # bemt.py, IMG_5785


def load(path):
    rows = [l.split() for l in open(path) if l.strip() and not l.startswith("#")]
    return np.array([[float(x) for x in r] for r in rows])


def window(x, n=1000):
    last, prev = x[-n:], x[-2 * n:-n]
    return float(last.mean()), float(last.mean() - prev.mean()) if len(prev) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--list", default=os.path.join(HERE, "mrf_runs.txt"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "..", "twin", "data", "cfd", "mrf_runs.json"))
    a = ap.parse_args()
    out = []
    for line in open(a.list):
        name, rpm, d, model, mesh = line.split()
        rpm, d = int(rpm), int(d)
        pp = os.path.join(a.runs, name, "postProcessing")
        if not os.path.isdir(os.path.join(pp, "rotor")):
            continue
        F = {k: load(os.path.join(pp, k, "0", "force.dat")) for k in WEIGHED + ("rotor",)}
        M = load(os.path.join(pp, "rotor", "0", "moment.dat"))
        it = int(F["rotor"][-1, 0])
        T, dT = window(-d * F["rotor"][:, 3])
        Q, dQ = window(np.abs(M[:, 3]))
        n = min(len(F[k]) for k in WEIGHED)
        bal, dbal = window(-sum(F[k][:n, 3] for k in WEIGHED) / G * 1e3)
        parts = {k: round(window(-F[k][:, 3] / G * 1e3)[0], 4) for k in WEIGHED}
        row = dict(name=name, rpm=rpm, dir=d, model=model, mesh=mesh, iterations=it,
                   thrust_gf=round(T / G * 1e3, 4), thrust_drift_gf=round(dT / G * 1e3, 4) if dT is not None else None,
                   torque_uNm=round(Q * 1e6, 2), torque_drift_uNm=round(dQ * 1e6, 2) if dQ is not None else None,
                   balance_gf=round(bal, 4), balance_drift_gf=round(dbal, 4) if dbal is not None else None,
                   balance_parts_gf=parts, measured_forward_balance_gf=THRUST.get(rpm) if d > 0 else None)
        out.append(row)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(dict(source="cfd/cases/mrf (simpleFoam + MRF, last 1000 iterations)", runs=out), open(a.out, "w"), indent=1)
    print("%-18s %5s %6s | %8s %8s | %8s %8s | %7s" % ("run", "iter", "", "T gf", "drift", "bal gf", "meas", "Q uN.m"))
    for r in out:
        print("%-18s %5d %6s | %8.3f %8s | %8.3f %8s | %7.1f" % (
            r["name"], r["iterations"], "", r["thrust_gf"], r["thrust_drift_gf"], r["balance_gf"],
            r["measured_forward_balance_gf"] if r["measured_forward_balance_gf"] is not None else "", r["torque_uNm"]))


if __name__ == "__main__":
    main()
