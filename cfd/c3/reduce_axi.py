#!/usr/bin/env python3
"""reduce_axi.py — the balance reading of the C3 axisymmetric runs (make_axi.py), against the stage-3 URANS.

Per run: the vertical force on each solid (wedge x 360/5, mean over the last --avg fraction of the iterations), in gf
with the stage-3 sign (+ = balance reading rises), plus the disk (the blades: the force on the air, reversed).
  balance = disk + hub + motor + cup + scale   (no breadboard in C3)

Usage:  python3 cfd/c3/reduce_axi.py <runs/c3 copy> [--avg 0.25] [--out twin/data/cfd/c3_axi.json]
        (copy c3_case.json, result.txt, postProcessing/f_*/0/force.dat)
"""
import argparse
import glob
import json
import os

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
G = 9.80665e-3
PARTS = ("hub", "motor", "cup", "scale")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--avg", type=float, default=0.25)
    ap.add_argument("--out", default=os.path.join(ROOT, "twin", "data", "cfd", "c3_axi.json"))
    a = ap.parse_args()
    urans = {r["dir"]: r for r in json.load(open(os.path.join(ROOT, "twin", "data", "cfd", "ami_runs.json")))["runs"]}
    out = []
    for d in sorted(glob.glob(os.path.join(a.runs, "*", "c3_case.json"))):
        case = os.path.dirname(d)
        c = json.load(open(d))
        sgn = c["dir"]
        parts, sd = {}, {}
        for p in PARTS:
            f = np.loadtxt(os.path.join(case, "postProcessing", "f_" + p, "0", "force.dat"), comments="#")
            fz = -f[:, 3] * 360.0 / c["wedge_deg"] / G           # + = pushes down = reading rises
            k = max(1, int(len(fz) * a.avg))
            parts[p], sd[p] = round(float(fz[-k:].mean()), 4), round(float(fz[-k:].std()), 4)
        parts["disk"] = round(sgn * c["disk_T_gf"], 4)
        res = open(os.path.join(case, "result.txt")).read().split()
        r = dict(name=os.path.basename(case), dir=sgn, turb=c["turb"], nu_eff=c["nu_eff"] if c["turb"] == "nu" else None,
                 refine=c["refine"], wall_s=float(res[res.index("wall_s") + 1]), iterations=int(res[res.index("iterations") + 1]),
                 balance_gf=round(sum(parts.values()), 4), parts_gf=parts, sd_last_gf=sd)
        U = urans.get(sgn)
        if U:
            r["urans_balance_gf"] = U["balance_gf"] if sgn > 0 else -0.16     # reverse: revolutions 20-29 (cfd/README.md)
            r["urans_parts_gf"] = {k: U["balance_parts_gf"][k] for k in ("hub", "motor", "cup", "scale")}
        out.append(r)
        print("%-24s %s balance %+.3f gf (URANS %+.3f) | %s | %.0f s, %d it" % (
            r["name"], c["turb"], r["balance_gf"], r.get("urans_balance_gf", float("nan")),
            " ".join("%s %+.3f" % kv for kv in parts.items()), r["wall_s"], r["iterations"]))
    json.dump(dict(source="cfd/c3 (simpleFoam, axisymmetric 5 deg wedge, actuator disk from c3_disk.json)", runs=out),
              open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
