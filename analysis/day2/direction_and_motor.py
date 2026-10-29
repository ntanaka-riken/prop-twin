#!/usr/bin/env python3
"""direction_and_motor.py — forward/reverse speed difference with warm-up drift removed, and what it means.

1. Full-speed comb frequencies from alternating forward/reverse runs are fitted with
     f = a + b (t - t_mean) + c * dir          (dir = +1 forward, -1 reverse)
   so a common warm-up drift cancels;  reverse - forward = -2 c.
     IMG_5779 (propeller on):   +0.29 +- 0.13 Hz (+0.57 %)
     IMG_5780 (propeller off):  -1.57 +- 0.08 Hz (-2.19 %)
2. The motor's own asymmetry (propeller off) is carried over to the propeller-on case under three
   hypotheses (reverse changes K / adds friction / adds bridge drop) with the twin's steady solution,
   and the remaining propeller-on difference is put on the reverse drag multiplier kD_r.
   (These numbers fed fit_joint.py --flag, which now fits dV0_rev and kD_r directly.)

Usage:  python3 analysis/day2/direction_and_motor.py
"""
import math
import os
import sys

import numpy as np
from scipy.optimize import brentq

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "twin"))
import motor_twin as mt  # noqa: E402

# (host time of the command, comb Hz, direction) from sync_audio.py
IMG_5779 = [(10, 51.56, 1), (21, 51.46, -1), (32, 51.10, 1), (43, 51.36, -1), (54, 50.88, 1), (65, 51.26, -1)]
IMG_5780 = [(5, 71.70, 1), (14, 70.49, -1), (23, 71.97, 1), (32, 70.58, -1), (41, 72.31, 1), (50, 70.77, -1),
            (59, 72.60, 1), (68, 70.93, -1)]


def direction_fit(rows):
    t = np.array([r[0] for r in rows], float)
    f = np.array([r[1] for r in rows])
    d = np.array([r[2] for r in rows])
    A = np.c_[np.ones(len(t)), t - t.mean(), d]
    c, *_ = np.linalg.lstsq(A, f, rcond=None)
    e = f - A @ c
    cov = (e @ e / (len(t) - 3)) * np.linalg.inv(A.T @ A)
    return -2 * c[2], 2 * math.sqrt(cov[2, 2]), c[0], c[1]


def steady(Q, aero=True):
    Ron = Q["R"] + Q["rd"]
    g = lambda w: Q["K"] * (Q["Vs"] - Q["V0"] - Q["K"] * w) / Ron - Q["Tc"] - Q["b"] * w - (mt.aero(Q, w)[1] if aero else 0)
    return brentq(g, 1, (Q["Vs"] - Q["V0"]) / Q["K"])


def main():
    for name, rows in (("IMG_5779 propeller on", IMG_5779), ("IMG_5780 propeller off", IMG_5780)):
        d, sd, a, b = direction_fit(rows)
        print("%-24s reverse - forward = %+.3f +- %.3f Hz (%+.2f %%), drift %+.4f Hz/s" % (name, d, sd, d / a * 100, b))
    P = mt.load_params()
    target = direction_fit(IMG_5780)[0] / direction_fit(IMG_5780)[2]
    bare = lambda Q: steady(Q, aero=False)
    prop = lambda Q: steady(Q, aero=True)
    wb0, wp0 = bare(P), prop(P)
    d1 = brentq(lambda d: bare(dict(P, K=P["K"] * (1 + d))) / wb0 - 1 - target, -0.1, 0.1)
    d2 = brentq(lambda d: bare(dict(P, Tc=P["Tc"] + d)) / wb0 - 1 - target, 0, 2e-4)
    d3 = brentq(lambda d: bare(dict(P, V0=P["V0"] + d)) / wb0 - 1 - target, -0.5, 0.5)
    print("motor asymmetry %.2f %% carried to the propeller-on case:" % (target * 100))
    print("  K x%.4f        -> %+.2f %%" % (1 + d1, (prop(dict(P, K=P["K"] * (1 + d1))) / wp0 - 1) * 100))
    print("  Tc +%.4f mN.m -> %+.2f %%" % (d2 * 1e3, (prop(dict(P, Tc=P["Tc"] + d2)) / wp0 - 1) * 100))
    print("  V0 +%.3f V     -> %+.2f %%" % (d3, (prop(dict(P, V0=P["V0"] + d3)) / wp0 - 1) * 100))


if __name__ == "__main__":
    main()
