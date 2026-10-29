#!/usr/bin/env python3
"""thrust_checks.py — the two thrust checks of day 2 against the twin.

boot   IMG_5781: boot-sequence button over Web Serial (5 s: 50 %, ramp to 100 % in 5 s, 11 s off), balance
       tared. Video = boot time - 1.5 s. The balance display lags; a dead time + first-order lag and a thrust
       scale are fitted to the 11 readings.
steps  IMG_5785 + twin/data/thrust_steps3_hostlog.json: 6 s steps 100/80/60/50/40 % twice, balance read over the
       last 4 s of each step (display_crops.py), speed from the TEL tachometer over the same window. Shows the
       n^2.23 growth and tests a Reynolds-dependent lift efficiency kL (Re/Re0)^m (now in bemt.py).

Usage:  python3 analysis/day2/thrust_checks.py boot|steps
"""
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "twin"))
import motor_twin as mt  # noqa: E402

G = 9.80665e-3
BOOT_READINGS = [(5.2, 0.1), (5.8, 0.2), (6.4, 0.4), (6.8, 0.5), (7.4, 0.7), (8.0, 0.8), (8.4, 1.0),
                 (9.0, 1.4), (9.6, 1.8), (10.0, 1.4), (10.6, 0.0)]          # video s, g (IMG_5781)


def boot():
    P = mt.load_params()
    r = mt.simulate([], 12.5, P, boot=True)
    t = np.array(r["t"]) - 1.5
    T = np.array(r["thr"]) / G
    dt = t[1] - t[0]
    meas = np.array(BOOT_READINGS)

    def model(scale, d, tau):
        y = np.zeros_like(T)
        for k in range(1, len(T)):
            y[k] = y[k - 1] + (T[k] - y[k - 1]) * dt / tau
        return np.interp(meas[:, 0] - d, t, y) * scale
    best = min((np.sqrt(np.mean((np.round(model(s, d, tau), 1) - meas[:, 1]) ** 2)), s, d, tau)
               for s in np.arange(0.7, 1.31, 0.05) for d in np.arange(0, 1.21, 0.1) for tau in (0.05, 0.2, 0.4, 0.6, 0.8))
    print("best: rms %.2f g, thrust x%.2f, dead time %.1f s, lag %.2f s" % best)
    print("twin thrust at the measured full speed 3058 rpm: %.2f gf (balance peak 1.8 g)" %
          (mt.aero(P, 3058 * math.pi / 30)[0] / G))


def steps():
    P = mt.load_params()
    L = json.load(open(os.path.join(ROOT, "twin/data/thrust_steps3_hostlog.json")))
    d = json.load(open(os.path.join(ROOT, "twin/data/thrust_steps_IMG_5785.json")))["steps"]
    tel = [(t, dict(kv.split("=") for kv in c.split()[1:])) for t, k, c in L if k == "rx" and c.startswith("TEL")]
    cmds = [(t, c) for t, k, c in L if k == "tx" and c.startswith("dcm:")]
    print("duty  TEL rpm (recomputed)  balance g  twin gf at that rpm")
    for s in d:
        rpms = []
        for (t0, c0), (t1, _) in zip(cmds, cmds[1:]):
            if c0 == "dcm:speed %d" % s["duty"]:
                rpms.append(np.mean([float(x["rpm"]) for t, x in tel if t1 - 4.0 <= t < t1 - 0.1]))
        n = np.mean(rpms)
        print(" %3d     %5.0f               %.2f        %.2f" % (s["duty"], n, s["balance_mean"],
                                                               mt.aero(P, n * math.pi / 30)[0] / G))
    n = np.array([s["rpm_mean"] for s in d][:4], float)
    b = np.array([s["balance_mean"] for s in d][:4])
    print("balance ~ n^%.2f over 100-50 %%" % np.polyfit(np.log(n), np.log(b), 1)[0])


if __name__ == "__main__":
    {"boot": boot, "steps": steps}[sys.argv[1] if len(sys.argv) > 1 else "steps"]()
