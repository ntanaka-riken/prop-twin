#!/usr/bin/env python3
"""compare_c2.py — PINN task C2 (one network over the angle of attack) against the LES polar and OpenFOAM 2D.

Inputs (copies from rikyu): <runs/pinn>/c2_*/result.json and the result.txt files of the 2D OpenFOAM runs
(runs/section_steady, runs/section_transient2d). The LES polar is twin/data/cfd/section_polars.json.
Appends rows to twin/data/cfd/ml_bench.json and draws twin/data/cfd/pinn_c2.png.

Usage:  python3 cfd/pinn/compare_c2.py <runs/pinn copy> <section_steady copy> <section_transient2d copy>
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


def openfoam(d, mode):
    out = {}
    for p in glob.glob(os.path.join(d, "re%05d_t030_f030_a*_np4" % RE, "result.txt")):
        lines = open(p).read().split("\n")
        m = re.search(r"_a([+-]\d+)_np", p); al = int(m.group(1))
        head = dict(zip(lines[0].split()[1::2], lines[0].split()[2::2]))
        if mode == "steady":
            v = lines[1].split()
            out[al] = dict(cl=float(v[4]), cd=float(v[1]), s=float(head["solve_s"]), ok=head.get("converged") == "1")
        else:
            v = lines[1].split()
            out[al] = dict(cl=float(v[4]), cd=float(v[2]), s=float(head["solve_s"]), ok=True)
    return out


def main():
    runs, steady_d, trans_d = sys.argv[1:4]
    les = {r["alpha"]: r for r in json.load(open(os.path.join(DATA, "section_polars.json")))["cases"]
           if (r["re"], r["t"], r["f"]) == (RE, TC, FC) and "cl" in r}
    st, tr = openfoam(steady_d, "steady"), openfoam(trans_d, "transient2d")
    pinn = {}
    for p in glob.glob(os.path.join(runs, "c2_*", "result.json")):
        r = json.load(open(p)); pinn[os.path.basename(os.path.dirname(p))] = r
    alphas = sorted(set(a for r in pinn.values() for a in (x["alpha"] for x in r["polar"])))

    bench_path = os.path.join(DATA, "ml_bench.json")
    bench = [b for b in json.load(open(bench_path)) if b["task"] != "C2"]
    def err(cl, cd, al):
        L = les[al]
        return dict(cl_abs=round(cl - L["cl"], 4), cd_abs=round(cd - L["cd"], 5))
    for name, r in sorted(pinn.items()):
        bench.append(dict(task="C2", method=r["method"], run=name, n_train=r["n_data"] * len(r["data_angles"]),
                          data_angles=r["data_angles"], data_node_h=round(0.79 * len(r["data_angles"]), 2) if r["data_angles"] else 0,
                          train_node_h=round(r["train_s"] / 3600 / 4, 4), infer_s=r["eval_s_per_angle"],
                          wall_h_to_answer=round(r["wall_s"] / 3600, 3), hardware="1 GB200 (1/4 node)",
                          polar=[dict(x, err_vs_les=err(x["cl"], x["cd"], x["alpha"])) for x in r["polar"]]))
    for mode, tab, label in (("openfoam-2d-steady", st, "simpleFoam"), ("openfoam-2d-transient", tr, "pimpleFoam 16 c/U")):
        bench.append(dict(task="C2", method=mode, run="sweep", n_train=0, data_node_h=0, train_node_h=0, hardware="4 Grace cores per angle",
                          infer_s=round(sum(v["s"] for v in tab.values()) / max(1, len(tab)), 1),
                          polar=[dict(alpha=al, cl=round(v["cl"], 4), cd=round(v["cd"], 5), converged=v["ok"], solve_s=v["s"],
                                      err_vs_les=err(v["cl"], v["cd"], al)) for al, v in sorted(tab.items())],
                          notes=label))
    json.dump(bench, open(bench_path, "w"), indent=1)

    print("%-20s " % "alpha" + " ".join("%7d" % a for a in alphas))
    print("%-20s " % "LES cl" + " ".join("%7.3f" % les[a]["cl"] for a in alphas))
    print("%-20s " % "OF 2D steady cl" + " ".join(("%7.3f" % st[a]["cl"]) if a in st and st[a]["ok"] else "     --" for a in alphas))
    print("%-20s " % "OF 2D transient cl" + " ".join(("%7.3f" % tr[a]["cl"]) if a in tr else "     --" for a in alphas))
    for name, r in sorted(pinn.items()):
        pc = {x["alpha"]: x for x in r["polar"]}
        print("%-20s " % (name + " cl") + " ".join("%7.3f" % pc[a]["cl"] for a in alphas), " (%.0f min)" % (r["train_s"] / 60))
    print("%-20s " % "LES cd" + " ".join("%7.4f" % les[a]["cd"] for a in alphas))
    print("%-20s " % "OF 2D transient cd" + " ".join(("%7.4f" % tr[a]["cd"]) if a in tr else "     --" for a in alphas))
    for name, r in sorted(pinn.items()):
        pc = {x["alpha"]: x for x in r["polar"]}
        print("%-20s " % (name + " cd") + " ".join("%7.4f" % pc[a]["cd"] for a in alphas))
        if any("test_rel_l2" in x for x in r["polar"]):
            print("%-20s " % "  field u err" + " ".join(("%7.3f" % pc[a]["test_rel_l2"]["u"]) if "test_rel_l2" in pc[a] else "     --" for a in alphas))

    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    styles = {"c2_pinn": (MUTED, "PINN, no data"), "c2_pinndata_n100": (BLUE, "PINN + 100 pts at -4,0,4,8"),
              "c2_pinndata_n1000": (VIOLET, "PINN + 1000 pts at -4,0,4,8"), "c2_data_n100": (ORANGE, "data only, 100 pts"),
              "c2_data_n1000": ("#c4462a", "data only, 1000 pts")}
    for x, key in ((ax[0], "cl"), (ax[1], "cd")):
        x.grid(color=GRID, lw=0.8); x.set_axisbelow(True)
        for s in ("top", "right"):
            x.spines[s].set_visible(False)
        x.plot(alphas, [les[a][key] for a in alphas], "-", color=INK, lw=3, label="LES (truth)")
        xs = [a for a in alphas if a in tr]; x.plot(xs, [tr[a][key] for a in xs], "--", color=AQUA, lw=2, marker="D", ms=7, label="OpenFOAM 2D transient")
        xs = [a for a in alphas if a in st and st[a]["ok"]]; x.plot(xs, [st[a][key] for a in xs], "s", color=AQUA, ms=9, mfc="white", mew=2, label="OpenFOAM 2D steady (converged only)")
        for name, r in sorted(pinn.items()):
            col, lab = styles.get(name, (MUTED, name))
            pc = sorted(r["polar"], key=lambda z: z["alpha"])
            x.plot([z["alpha"] for z in pc], [z[key] for z in pc], "-o", color=col, lw=2, ms=6, label=lab)
        for a in (-4, 0, 4, 8):
            x.axvline(a, color=GRID, lw=6, zorder=0)
        x.set_xlabel("angle of attack (deg); grey bands: angles with data")
        x.set_title("%s, Re 6000, t/c 0.03, f/c 0.03" % key, loc="left", fontsize=11)
    ax[0].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    out = os.path.join(DATA, "pinn_c2.png")
    fig.savefig(out, dpi=110)
    print(out)


if __name__ == "__main__":
    main()
