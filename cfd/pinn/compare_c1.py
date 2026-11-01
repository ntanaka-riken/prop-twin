#!/usr/bin/env python3
"""compare_c1.py — PINN task C1 against the stage-1 LES: cl, cd, cost, and the training history.

Reads the PINN results (<runs/pinn copy>/<name>/result.json) and the LES polars (section_polars.json files; the
first one that has the case wins), appends one row per PINN run to twin/data/cfd/ml_bench.json, and draws
twin/data/cfd/pinn_c1.png (cl and cd against training time, with the LES mean and its spread).

Usage:  python3 cfd/pinn/compare_c1.py <runs/pinn copy> [polars.json ...]
"""
import glob
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
DATA = os.path.join(ROOT, "twin", "data", "cfd")
BLUE, ORANGE, AQUA, VIOLET, INK, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#8a5cd1", "#2b2b2b", "#e4e3df"


def les_case(polars, re, alpha, t, f):
    for p in polars:
        for r in json.load(open(p))["cases"]:
            if (r["re"], r["alpha"], r["t"], r["f"]) == (re, alpha, t, f) and "cl" in r:
                return r
    return None


def main():
    runs = sys.argv[1]
    polars = sys.argv[2:] or [os.path.join(DATA, "section_polars.json")]
    cost = {c["case"]: c for c in json.load(open(os.path.join(DATA, "cost.json")))["runs"] if c["stage"] == "1-section-les"}
    bench_path = os.path.join(DATA, "ml_bench.json")
    bench = json.load(open(bench_path)) if os.path.exists(bench_path) else []
    results = []
    for p in sorted(glob.glob(os.path.join(runs, "*", "result.json"))):
        r = json.load(open(p))
        r["name"] = os.path.basename(os.path.dirname(p))
        if r.get("task") != "C1" or r["args"]["steps"] < 1000:
            continue
        ref = les_case(polars, int(r["re"]), int(r["alpha"]), r["t"], r["f"])
        r["les"] = ref
        results.append(r)
        bench = [b for b in bench if not (b["task"] == "C1" and b.get("run") == r["name"])]
        case = "re%05d_t%03d_f%03d_a%+03d" % (r["re"], round(r["t"] * 1000), round(r["f"] * 1000), r["alpha"])
        c = cost.get(case, {})
        row = dict(task="C1", method="pinn", run=r["name"], split="-", n_train=0, data_node_h=0,
                   train_node_h=round(r["train_s"] / 3600 / 4, 4), infer_s=None, wall_h_to_answer=round(r["wall_s"] / 3600, 3),
                   hardware="1 GB200 (1/4 node)", re=r["re"], alpha=r["alpha"], cl=r["cl"], cd=r["cd"],
                   params=dict((k, r["args"][k]) for k in ("steps", "width", "depth", "n_int", "n_near", "w_wall", "lr")))
        if ref:
            row["les"] = dict(cl=ref["cl"], cd=ref["cd"], cl_std=ref["cl_std"], cd_std=ref["cd_std"],
                              node_h=c.get("node_h"), wall_h=round(c.get("solver_wall_s", 0) / 3600, 2) if c else None)
            row["err_vs_cfd"] = dict(cl_rel=round(r["cl"] / ref["cl"] - 1, 3) if abs(ref["cl"]) > 0.05 else None,
                                     cd_rel=round(r["cd"] / ref["cd"] - 1, 3))
        bench.append(row)
        print("%-22s Re %5d  cl %.4f cd %.5f | LES cl %s cd %s | %.0f s training" % (
            r["name"], r["re"], r["cl"], r["cd"], ref and ref["cl"], ref and ref["cd"], r["train_s"]))
    json.dump(bench, open(bench_path, "w"), indent=1)

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    cols = [BLUE, ORANGE, AQUA, VIOLET]
    for a, key, lab in ((ax[0], "cl", "cl"), (ax[1], "cd", "cd")):
        a.grid(color=GRID, lw=0.8); a.set_axisbelow(True)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        for col, r in zip(cols, results):
            h = r["history"]
            a.plot([x["s"] / 60 for x in h], [x[key] for x in h], color=col, lw=2, label=r["name"])
            if r["les"]:
                m, sd = r["les"][key], r["les"][key + "_std"]
                a.axhline(m, color=col, lw=1.5, ls="--")
                a.axhspan(m - sd, m + sd, color=col, alpha=0.08)
        a.set_xlabel("training time (min, 1 GPU)")
        a.set_title("%s: PINN (solid) and LES mean +- std (dashed, band)" % lab, loc="left", fontsize=11)
    ax[0].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    out = os.path.join(DATA, "pinn_c1.png")
    fig.savefig(out, dpi=110)
    print(out)


if __name__ == "__main__":
    main()
