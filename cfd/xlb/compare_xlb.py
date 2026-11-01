#!/usr/bin/env python3
"""compare_xlb.py — the GPU lattice Boltzmann section runs (section_lbm.py) against the LES polar, OpenFOAM 2D and the PINNs.

Inputs (copies from rikyu): <runs/xlb>/*/result.json; optionally the result.txt files of the OpenFOAM 2D transient
runs (runs/section_transient2d). The LES polar is twin/data/cfd/section_polars.json, the PINN rows come from
twin/data/cfd/ml_bench.json (task C2). Appends task "CFD-GPU" rows to ml_bench.json and draws twin/data/cfd/xlb_c2.png.

Usage:  python3 cfd/xlb/compare_xlb.py <runs/xlb copy> [<section_transient2d copy>]
"""
import glob
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
DATA = os.path.join(ROOT, "twin", "data", "cfd")
BLUE, ORANGE, AQUA, VIOLET, INK, GRID, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#8a5cd1", "#2b2b2b", "#e4e3df", "#9a9890"
RE, TC, FC = 6000, 0.03, 0.03


def transient2d(d):
    out = {}
    for p in glob.glob(os.path.join(d, "re%05d_t030_f030_a*_np4" % RE, "result.txt")):
        lines = open(p).read().split("\n")
        al = int(re.search(r"_a([+-]\d+)_np", p).group(1))
        head = dict(zip(lines[0].split()[1::2], lines[0].split()[2::2]))
        v = lines[1].split()
        out[al] = dict(cl=float(v[4]), cd=float(v[2]), s=float(head["solve_s"]))
    return out


def main():
    runs = sys.argv[1]
    tr = transient2d(sys.argv[2]) if len(sys.argv) > 2 else {}
    les = {r["alpha"]: r for r in json.load(open(os.path.join(DATA, "section_polars.json")))["cases"]
           if (r["re"], r["t"], r["f"]) == (RE, TC, FC) and "cl" in r}
    rows = []
    for p in sorted(glob.glob(os.path.join(runs, "*", "result.json"))):
        r = json.load(open(p))
        if (r["re"], r["t"], r["f"]) != (RE, TC, FC):
            continue
        r["name"] = os.path.basename(os.path.dirname(p))
        rows.append(r)

    bench_path = os.path.join(DATA, "ml_bench.json")
    bench = json.load(open(bench_path))
    pinn = [b for b in bench if b["task"] == "C2" and b["method"] in ("pinn", "pinn+data", "data-only-nn")]
    bench = [b for b in bench if b["task"] != "CFD-GPU"]
    for r in rows:
        L = les.get(int(r["alpha"]))
        bench.append(dict(task="CFD-GPU", method=r["method"], run=r["name"], n_train=0, data_node_h=0, train_node_h=0,
                          hardware="1 GB200 (1/4 node)", re=r["re"], alpha=r["alpha"], n_per_chord=r["n_per_chord"],
                          cells=r["cells"], cl=r["cl"], cd=r["cd"], completed=r["completed"],
                          infer_s=r["solve_s"], wall_h_to_answer=round(r["wall_s"] / 3600, 4),
                          node_h=round(r["wall_s"] / 3600 / 4, 5), mlups=r["mlups"],
                          err_vs_les=dict(cl_abs=round(r["cl"] - L["cl"], 4), cd_abs=round(r["cd"] - L["cd"], 5))
                          if L and r["cl"] is not None else None))
    json.dump(bench, open(bench_path, "w"), indent=1)

    print("%-30s %5s %4s %9s %8s %8s %8s %8s %7s" % ("run", "alpha", "n", "cells", "cl", "LES", "cd", "LES", "s"))
    for r in sorted(rows, key=lambda r: (r["method"], r["n_per_chord"], r["alpha"])):
        L = les.get(int(r["alpha"]), {})
        print("%-30s %5.0f %4d %9d %8s %8.3f %8s %8.4f %7.0f%s" % (
            r["name"], r["alpha"], r["n_per_chord"], r["cells"], "%.3f" % r["cl"] if r["cl"] is not None else "--",
            L.get("cl", float("nan")), "%.4f" % r["cd"] if r["cd"] is not None else "--", L.get("cd", float("nan")),
            r["solve_s"], "" if r["completed"] else "  (not completed)"))

    series = sorted(set((r["method"], r["n_per_chord"]) for r in rows))
    alphas = [a for a in sorted(les) if -6 <= a <= 12]
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    for x, key in ((ax[0], "cl"), (ax[1], "cd")):
        x.grid(color=GRID, lw=0.8); x.set_axisbelow(True)
        for s in ("top", "right"):
            x.spines[s].set_visible(False)
        x.plot(alphas, [les[a][key] for a in alphas], "-", color=INK, lw=3, label="LES (truth), 3.3 h per angle on 36 cores")
        if tr:
            xs = sorted(tr); x.plot(xs, [tr[a][key] for a in xs], "--D", color=AQUA, lw=2, ms=7,
                                     label="OpenFOAM 2D transient, 8-13 min on 4 cores")
        for (m, n), col in zip(series, (ORANGE, BLUE, VIOLET, "#c4462a")):
            rr = sorted((r for r in rows if (r["method"], r["n_per_chord"]) == (m, n) and r["completed"] and r["args"]["h"] == 4.0),
                        key=lambda r: r["alpha"])
            if rr:
                t = sum(r["solve_s"] for r in rr) / len(rr)
                x.plot([r["alpha"] for r in rr], [r[key] for r in rr], "-o" if m.endswith("2d") else "s", color=col, lw=2, ms=8,
                       label="XLB LBM %s, %d cells/c, %.0f s per angle on 1 GPU" % (m[-2:].upper(), n, t))
        for b in pinn:
            if b["run"] == "c2_data_n1000":
                pc = sorted(b["polar"], key=lambda z: z["alpha"])
                x.plot([z["alpha"] for z in pc], [z[key] for z in pc], ":", color=MUTED, lw=2,
                       label="network on LES data at -4, 0, 4, 8 (C2, 1000 pts each)")
        x.set_xlabel("angle of attack (deg)")
        x.set_title("%s, Re 6000, t/c 0.03, f/c 0.03" % key, loc="left", fontsize=11)
    ax[0].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    out = os.path.join(DATA, "xlb_c2.png")
    fig.savefig(out, dpi=110)
    print(out)


if __name__ == "__main__":
    main()
