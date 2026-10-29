#!/usr/bin/env python3
"""compare_runs.py — replay both filmed runs in the twin and plot against the measurements.

  python3 twin/compare_runs.py [out.png]      (needs matplotlib)
"""
import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import motor_twin as mt

HERE = os.path.dirname(os.path.abspath(__file__))
RPM = 30 / math.pi


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "data", "compare_runs.png")
    P = mt.load_params()
    m1 = json.load(open(os.path.join(HERE, "data", "IMG_5741_measured.json")))
    m2 = json.load(open(os.path.join(HERE, "data", "IMG_5742_measured.json")))
    runs = [
        ("IMG_5741: 100 % for 2 s, then coast", m1,
         [(m1["t_on"], "dcm:speed 255"), (m1["t_off"], "dcm:off")], 7.5,
         [("audio comb", m1["audio_omega"], "C1."), ("video blades", m1["video_omega"], "C3o")]),
        ("IMG_5742: 100 % for 3 s, then 20 % (sync LED)", m2,
         [(m2["t_full"], "dcm:speed 255"), (m2["t_20"], "dcm:speed 51"), (m2["t_off"], "dcm:off")], 14,
         [("audio comb (mean)", [(m2["t_full"] + 1.0, 2 * math.pi * m2["f_full"]),
                                 (m2["t_20"] - 0.05, 2 * math.pi * m2["f_at_20"])], "C1s"),
          ("video blades 60 fps", m2["video_omega_20pct"], "C3o")]),
    ]
    fig, axs = plt.subplots(2, 1, figsize=(10, 7.5))
    for ax, (title, m, script, T, marks) in zip(axs, runs):
        r = mt.simulate(script, T, P)
        ax.plot(r["t"], [w * RPM for w in r["w"]], lw=2, label="twin")
        for lab, pts, st in marks:
            ax.plot([p[0] for p in pts], [p[1] * RPM for p in pts], st, ms=4, label=lab)
        for t, c in script:
            ax.axvline(t, color="0.7", lw=0.8)
            ax.text(t, 3300, " " + c, fontsize=8, color="0.4", clip_on=True)
        ax.set_title(title, fontsize=10, loc="left")
        ax.set_ylabel("rpm"); ax.set_ylim(-100, 3600); ax.legend(loc="center right", fontsize=8)
        ax.set_xlim(script[0][0] - 0.5, min(T, script[-1][0] + 1.5) if len(script) > 2 else T)
    axs[1].set_xlim(m2["t_full"] - 0.5, m2["t_stop"] + 1.0)
    axs[1].set_xlabel("video time [s]")
    plt.tight_layout(); plt.savefig(out, dpi=100)
    print("plot ->", out)


if __name__ == "__main__":
    main()
