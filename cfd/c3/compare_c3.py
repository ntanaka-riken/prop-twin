#!/usr/bin/env python3
"""compare_c3.py — task C3: the balance reading from the actuator-disk runs (OpenFOAM wedge, PINN) against the stage-3
URANS and the measurement, and the wake profiles.

Inputs: twin/data/cfd/c3_axi.json (reduce_axi.py), copies of <runs/pinn>/c3_*/{result.json,fields.npz} and of the
OpenFOAM line samples <runs/c3>/<case>/postProcessing/lines/<last>/*.xy.
Appends task "C3" rows to twin/data/cfd/ml_bench.json and draws twin/data/cfd/c3.png.

Usage:  python3 cfd/c3/compare_c3.py <runs/pinn copy> <runs/c3 copy>
"""
import glob
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
DATA = os.path.join(ROOT, "twin", "data", "cfd")
BLUE, ORANGE, AQUA, VIOLET, RED, INK, GRID, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#8a5cd1", "#c4462a", "#2b2b2b", "#e4e3df", "#9a9890"
MEASURED = {1: 1.675, -1: -0.14}
URANS = {1: 0.746, -1: -0.16}
URANS_NODE_H = {1: 14 * 2, -1: 28 * 2}           # 2 nodes, 14 h (15 rev) / 28 h (30 rev)


def label(r):
    if r["method"] == "data-only-nn":
        return "data only, %d pts" % r["n_data"]
    s = "PINN"
    if r["n_data"]:
        s += " + %d pts" % r["n_data"]
    if r["args"].get("edge", 3e-4) != 3e-4 or r["args"]["steps"] != 20000:
        s += " (edge %.0f mm, %dk steps)" % (r["args"]["edge"] * 1e3, r["args"]["steps"] // 1000)
    return s


def colour(r):
    if r["method"] == "data-only-nn":
        return MUTED
    if r["n_data"]:
        return RED if r["n_data"] < 1000 else VIOLET
    return ORANGE if r["args"].get("edge", 3e-4) == 3e-4 else "#d9a21b"


def main():
    pinn_dir, of_dir = sys.argv[1], sys.argv[2]
    of = json.load(open(os.path.join(DATA, "c3_axi.json")))["runs"]
    pinn = []
    for p in sorted(glob.glob(os.path.join(pinn_dir, "c3_*", "result.json"))):
        r = json.load(open(p))
        r["name"] = os.path.basename(os.path.dirname(p))
        r.setdefault("n_data", 0)                  # runs from before the data option
        r.setdefault("method", "pinn-axi")
        pinn.append(r)

    bench_path = os.path.join(DATA, "ml_bench.json")
    bench = [b for b in json.load(open(bench_path)) if b["task"] != "C3"]
    for d in (1, -1):
        bench.append(dict(task="C3", method="urans-ami", dir=d, balance_gf=URANS[d], measured_gf=MEASURED[d],
                          hardware="2 nodes x 144 cores", node_h=URANS_NODE_H[d], wall_h_to_answer=URANS_NODE_H[d] / 2))
    for r in of:
        bench.append(dict(task="C3", method="openfoam-axi-disk-" + r["turb"], run=r["name"], dir=r["dir"], nu_eff=r["nu_eff"],
                          balance_gf=r["balance_gf"], parts_gf=r["parts_gf"], err_vs_urans_gf=round(r["balance_gf"] - URANS[r["dir"]], 3),
                          hardware="1 core", wall_h_to_answer=round(r["wall_s"] / 3600, 4), node_h=round(r["wall_s"] / 3600 / 144, 6)))
    for r in pinn:
        bench.append(dict(task="C3", method=r["method"], run=r["name"], dir=r["dir"], nu_eff=r["nu_eff"], n_train=r["n_data"],
                          balance_gf=r["balance_gf"], parts_gf=r["parts_gf"], err_vs_urans_gf=round(r["balance_gf"] - URANS[r["dir"]], 3),
                          test_rel_l2_vs_openfoam_nu=r.get("test_rel_l2"), hardware="1 GB200 (1/4 node)",
                          train_node_h=round(r["train_s"] / 3600 / 4, 4), wall_h_to_answer=round(r["wall_s"] / 3600, 3)))
    json.dump(bench, open(bench_path, "w"), indent=1)

    print("%-34s %4s %9s %9s %8s  %s" % ("run", "dir", "balance", "vs URANS", "time", "parts (gf) / test error vs OpenFOAM-nu"))
    for d in (1, -1):
        print("%-34s %4d %+9.3f %9s %8s  measured %+.3f" % ("URANS (stage 3)", d, URANS[d], "", "%dh x2n" % (URANS_NODE_H[d] / 2), MEASURED[d]))
        for r in [x for x in of if x["dir"] == d]:
            print("%-34s %4d %+9.3f %+9.3f %7.0fs  %s" % ("OpenFOAM " + r["name"], d, r["balance_gf"], r["balance_gf"] - URANS[d], r["wall_s"],
                                                       " ".join("%s %+.2f" % kv for kv in r["parts_gf"].items())))
        for r in [x for x in pinn if x["dir"] == d]:
            print("%-34s %4d %+9.3f %+9.3f %7.0fs  %s | %s" % (label(r), d, r["balance_gf"], r["balance_gf"] - URANS[d], r["wall_s"],
                                                           " ".join("%s %+.2f" % kv for kv in r["parts_gf"].items()), json.dumps(r.get("test_rel_l2"))))

    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8), gridspec_kw=dict(width_ratios=[1.1, 1]))
    x = ax[0]
    x.grid(axis="x", color=GRID, lw=0.8); x.set_axisbelow(True)
    rows = [("measured", MEASURED, INK), ("URANS, rotating blades", URANS, INK)]
    for r in of:
        if r["turb"] == "sst" or abs((r["nu_eff"] or 0) - 1.5e-3) < 1e-9:
            rows.append(("OpenFOAM disk, " + ("SST" if r["turb"] == "sst" else "nu_eff 1.5e-3"), {r["dir"]: r["balance_gf"]}, AQUA))
    for r in pinn:
        rows.append((label(r), {r["dir"]: r["balance_gf"]}, colour(r)))
    merged = {}
    for name, v, col in rows:
        merged.setdefault(name, [{}, col])[0].update(v)
    names = list(merged)
    for k, name in enumerate(names):
        v, col = merged[name]
        for d, mk in ((1, "o"), (-1, "s")):
            if d in v:
                x.plot(np.clip(v[d], -1.5, 3.0), k, mk, color=col, ms=9, mfc=col if d > 0 else "white", mew=2)
    for d in (1, -1):
        x.axvspan(URANS[d] - 0.3, URANS[d] + 0.3, color=BLUE, alpha=0.08)
    x.set_yticks(range(len(names))); x.set_yticklabels(names, fontsize=8); x.invert_yaxis()
    x.set_xlim(-1.6, 3.1)
    x.set_xlabel("balance reading (gf); filled = forward, open = reverse; band = URANS +/- 0.3 gf")
    x.set_title("C3: the balance with the rotor as a disk", loc="left", fontsize=11)
    for s in ("top", "right"):
        x.spines[s].set_visible(False)

    x = ax[1]
    x.grid(color=GRID, lw=0.8); x.set_axisbelow(True)
    key = "z157"
    for case, col, lab in (("fwd_nu1.5e-3", AQUA, "OpenFOAM disk, nu_eff 1.5e-3"), ("fwd_sst", BLUE, "OpenFOAM disk, SST")):
        f = sorted(glob.glob(os.path.join(of_dir, case, "postProcessing", "lines", "*", key + "_p_U.xy")),
                   key=lambda p: float(p.split(os.sep)[-2]))
        if f:
            o = np.loadtxt(f[-1])
            x.plot(o[:, 0] * 1e3, o[:, 4], "-", color=col, lw=2.5, label=lab)
    for r in [r for r in pinn if r["dir"] == 1]:
        col = colour(r)
        q = np.load(os.path.join(pinn_dir, r["name"], "fields.npz"))[key]
        x.plot(q[:, 0] * 1e3, q[:, 4], "--", color=col, lw=2, label=label(r))
    x.axhline(0, color=INK, lw=0.8)
    x.set_xlabel("r (mm)"); x.set_ylabel("u_z (m/s), + = up")
    x.set_title("forward, axial speed 30 mm above the rotor", loc="left", fontsize=11)
    x.legend(fontsize=8, frameon=False)
    for s in ("top", "right"):
        x.spines[s].set_visible(False)
    fig.tight_layout()
    out = os.path.join(DATA, "c3.png")
    fig.savefig(out, dpi=110)
    print(out)


if __name__ == "__main__":
    main()
