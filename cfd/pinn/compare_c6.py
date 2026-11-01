#!/usr/bin/env python3
"""compare_c6.py — PINN task C6 (PINN + sparse LES points) against a network fitted to the same points only.

Reads <runs/pinn copy>/c6_*/result.json, appends one row per run to twin/data/cfd/ml_bench.json, and draws
twin/data/cfd/pinn_c6.png: the error on unseen points and cl, cd against the number of data points.

Usage:  python3 cfd/pinn/compare_c6.py <runs/pinn copy> [--les-cl 0.552 --les-cd 0.0548]
"""
import argparse
import glob
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
DATA = os.path.join(ROOT, "twin", "data", "cfd")
BLUE, ORANGE, INK, GRID, MUTED = "#2a78d6", "#eb6834", "#2b2b2b", "#e4e3df", "#9a9890"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--les-cl", type=float, default=0.55188)
    ap.add_argument("--les-cd", type=float, default=0.05483)
    a = ap.parse_args()
    rows = []
    for p in glob.glob(os.path.join(a.runs, "c6_*", "result.json")):
        r = json.load(open(p)); r["name"] = os.path.basename(os.path.dirname(p))
        rows.append(r)
    bench_path = os.path.join(DATA, "ml_bench.json")
    bench = [b for b in json.load(open(bench_path)) if b["task"] != "C6"]
    for r in sorted(rows, key=lambda r: (r["method"], r["n_data"])):
        bench.append(dict(task="C6", method=r["method"], run=r["name"], n_train=r["n_data"], data_node_h=0.79,
                          train_node_h=round(r["train_s"] / 3600 / 4, 4), wall_h_to_answer=round(r["wall_s"] / 3600, 3),
                          hardware="1 GB200 (1/4 node)", re=r["re"], alpha=r["alpha"], cl=r["cl"], cd=r["cd"],
                          err_vs_cfd=dict(cl_rel=round(r["cl"] / a.les_cl - 1, 3), cd_rel=round(r["cd"] / a.les_cd - 1, 3),
                                          field_rel_l2=r["test_rel_l2"]["test"], wall_rel_l2=r["test_rel_l2"]["wall"]),
                          notes="data: LES mean field (spanwise-averaged) at n random points, half within 0.3 c of the "
                                "section; data_node_h is the one LES case they come from"))
        print("%-16s n %5d  cl %.3f (%+.0f%%) cd %.4f (%+.0f%%)  u %.3f v %.3f p %.3f  wall p %.3f  %4.0f s" % (
            r["method"], r["n_data"], r["cl"], 100 * (r["cl"] / a.les_cl - 1), r["cd"], 100 * (r["cd"] / a.les_cd - 1),
            *(r["test_rel_l2"]["test"][k] for k in "uvp"), r["test_rel_l2"]["wall"]["p"], r["train_s"]))
    json.dump(bench, open(bench_path, "w"), indent=1)

    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    for x in ax:
        x.grid(color=GRID, lw=0.8); x.set_axisbelow(True); x.set_xscale("log"); x.set_xlabel("LES data points used")
        for s in ("top", "right"):
            x.spines[s].set_visible(False)
    for method, col, lab in (("pinn-primitive", BLUE, "PINN + data (14 min)"), ("data-only-nn", ORANGE, "network on data only (24 s)")):
        rr = sorted((r for r in rows if r["method"] == method), key=lambda r: r["n_data"])
        n = [r["n_data"] for r in rr]
        ax[0].plot(n, [r["test_rel_l2"]["test"]["u"] for r in rr], "-o", color=col, lw=2, ms=7, label=lab + ": u")
        ax[0].plot(n, [r["test_rel_l2"]["test"]["p"] for r in rr], "--s", color=col, lw=2, ms=7, mfc="white", label=lab + ": p")
        ax[1].plot(n, [r["cl"] for r in rr], "-o", color=col, lw=2, ms=7, label=lab)
        ax[2].plot(n, [r["cd"] for r in rr], "-o", color=col, lw=2, ms=7, label=lab)
    ax[0].set_yscale("log"); ax[0].set_title("Relative L2 error on 4945 unseen points", loc="left", fontsize=11)
    ax[1].axhline(a.les_cl, color=INK, lw=1.5, ls="--"); ax[1].axhline(0.531, color=MUTED, lw=1.5, ls=":")
    ax[1].set_title("cl (dashed: LES 0.552, dotted: OpenFOAM 2D steady)", loc="left", fontsize=11)
    ax[2].axhline(a.les_cd, color=INK, lw=1.5, ls="--"); ax[2].axhline(0.0526, color=MUTED, lw=1.5, ls=":")
    ax[2].set_title("cd", loc="left", fontsize=11)
    ax[0].legend(fontsize=8, frameon=False); ax[1].legend(fontsize=8, frameon=False)
    fig.suptitle("C6: section Re 6000, alpha 4 deg, data from the LES mean field", x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    out = os.path.join(DATA, "pinn_c6.png")
    fig.savefig(out, dpi=110)
    print(out)


if __name__ == "__main__":
    main()
