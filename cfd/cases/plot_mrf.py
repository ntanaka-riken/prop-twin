#!/usr/bin/env python3
"""plot_mrf.py — stage-2 MRF results against the balance and the BEMT (twin/data/cfd/mrf_runs.json -> mrf_vs_measured.png).

Usage:  python3 cfd/cases/plot_mrf.py [twin/data/cfd/mrf_runs.json]
"""
import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "twin"))
import bemt  # noqa: E402

BLUE, ORANGE, AQUA, INK, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#2b2b2b", "#e4e3df"
G = 9.80665e-3


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "twin", "data", "cfd", "mrf_runs.json")
    runs = [r for r in json.load(open(path))["runs"] if r["mesh"].startswith("0")]
    aero = json.load(open(os.path.join(ROOT, "twin", "params.json")))["aero"]
    bemt.KL_M = aero["kL_m"]
    rpm = [695, 1190, 1592, 2184, 3067]
    tw = [bemt.solve(n * math.pi / 30, aero["kL"], aero["kD"]) for n in rpm]
    tw1 = [bemt.solve(n * math.pi / 30, aero["kL"], 1.0) for n in rpm]
    twr = [bemt.solve(-n * math.pi / 30, aero["kL"], aero["kD_r"]) for n in rpm]

    def sel(model, d, key):
        rr = sorted((r for r in runs if r["model"] == model and r["dir"] == d), key=lambda r: r["rpm"])
        return [r["rpm"] for r in rr], [r[key] for r in rr]

    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
    for a in ax:
        a.grid(color=GRID, lw=0.8); a.set_axisbelow(True)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        a.set_xlabel("rpm")
    # forward
    a = ax[0]
    a.plot(rpm, [s["T"] / G for s in tw], color=AQUA, lw=2, label="BEMT twin (fitted to balance)")
    for model, ls, mk in (("kOmegaSSTLM", "-", "o"), ("kOmegaSST", "--", "s")):
        x, y = sel(model, 1, "thrust_gf"); a.plot(x, y, ls, color=BLUE, lw=2, marker=mk, ms=8, mfc="white" if ls == "--" else BLUE,
                                                   label="CFD rotor thrust (%s)" % ("SST-LM" if model.endswith("LM") else "SST"))
        x, y = sel(model, 1, "balance_gf"); a.plot(x, y, ls, color=ORANGE, lw=2, marker=mk, ms=8, mfc="white" if ls == "--" else ORANGE,
                                                    label="CFD balance (%s)" % ("SST-LM" if model.endswith("LM") else "SST"))
    a.plot(rpm, [dict(bemt.THRUST)[n] for n in rpm], "D", color=INK, ms=8, label="measured balance (IMG_5785)")
    a.set_title("Forward: thrust and balance reading (gf)", loc="left", fontsize=11)
    a.legend(fontsize=8, frameon=False)
    # reverse
    a = ax[1]
    a.axhline(0, color="#9a9890", lw=1)
    a.plot(rpm, [s["bal"] / G for s in twr], color=AQUA, lw=2, label="BEMT twin balance (eta 0.93)")
    for model, ls, mk in (("kOmegaSSTLM", "-", "o"), ("kOmegaSST", "--", "s")):
        x, y = sel(model, -1, "thrust_gf"); a.plot(x, [-v for v in y], ls, color=BLUE, lw=2, marker=mk, ms=8, mfc="white" if ls == "--" else BLUE,
                                                    label="CFD rotor force (%s)" % ("SST-LM" if model.endswith("LM") else "SST"))
        x, y = sel(model, -1, "balance_gf"); a.plot(x, y, ls, color=ORANGE, lw=2, marker=mk, ms=8, mfc="white" if ls == "--" else ORANGE,
                                                     label="CFD balance (%s)" % ("SST-LM" if model.endswith("LM") else "SST"))
    a.plot([3067], [-0.14], "D", color=INK, ms=8, label="measured balance, full speed (IMG_5779)")
    a.set_title("Reverse: balance reading (gf, + = reading rises)", loc="left", fontsize=11)
    a.legend(fontsize=8, frameon=False)
    # torque
    a = ax[2]
    a.plot(rpm, [(s["Qi"] + aero["kD"] * s["Qp"]) * 1e6 for s in tw], color=AQUA, lw=2, label="BEMT twin, kD = %.1f" % aero["kD"])
    a.plot(rpm, [(s["Qi"] + s["Qp"]) * 1e6 for s in tw1], ":", color=AQUA, lw=2, label="BEMT, kD = 1 (thin-plate drag)")
    for d, col, nm in ((1, BLUE, "forward"), (-1, ORANGE, "reverse")):
        x, y = sel("kOmegaSSTLM", d, "torque_uNm"); a.plot(x, y, "-", color=col, lw=2, marker="o", ms=8, label="CFD %s (SST-LM)" % nm)
    a.set_title("Aerodynamic torque (uN m)", loc="left", fontsize=11)
    a.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    out = os.path.join(os.path.dirname(path), "mrf_vs_measured.png")
    fig.savefig(out, dpi=110)
    print(out)


if __name__ == "__main__":
    main()
