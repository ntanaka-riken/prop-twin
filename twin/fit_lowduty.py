#!/usr/bin/env python3
"""fit_lowduty.py — joint fit of the coast-down (IMG_5741) and the 20 % duty run (IMG_5742).

IMG_5741 alone gives Tc/J and c/J (unpowered coast). IMG_5742 adds a 100 % -> 20 % step that
slows the rotor from 50.8 Hz to a stop in ~1 s while current still flows; with the PWM-resolved
plant that run is what fixes the winding inductance L (how little current a 0.2 ms pulse gets).

For each (alpha = Tc/J, L) on a grid:
  beta = c/J  <- total coast time in IMG_5741        (same closed form as identify.py)
  R           <- steady speed at 100 % (DC, L-independent)
  Ts          <- breakaway at 47 % duty, now with the PWM-resolved stall current
  cost        <- RMS error of omega(t) after the 20 % step + stop-time error (IMG_5742)

Usage:
  python3 twin/fit_lowduty.py            # print the best fit and the checks
  python3 twin/fit_lowduty.py --write    # also update params.json
"""
import argparse
import json
import math
import os

from scipy.optimize import brentq

import motor_twin as mt

HERE = os.path.dirname(os.path.abspath(__file__))


def derived(P, m1, alpha, L):
    w0 = 2 * math.pi * m1["f_ss"]
    T = m1["t_stop"] - m1["t_off"]
    beta = brentq(lambda b: math.atan(w0 * math.sqrt(b / alpha)) / math.sqrt(alpha * b) - T,
                  1e-7, 10.0)
    Q = dict(P, L=L, Tc=alpha * P["J"], c=beta * P["J"])
    i_ss = (Q["Tc"] + Q["c"] * w0 ** 2) / Q["K"]
    Q["R"] = (Q["Vs"] - Q["V0"] - Q["K"] * w0) / i_ss - Q["rd"]
    pl = mt.Plant(dict(Q, Ts=1e9))          # stalled rotor: periodic steady state at 47 %
    for _ in range(50):
        pl._drive_period(P["d_breakaway"], 1.0 / Q["f_pwm"])
    Q["Ts"] = Q["K"] * pl.im
    return Q, beta


def run_20(Q, m2, T=1.6):
    t20 = m2["t_20"]
    w_init = 2 * math.pi * m2["f_at_20"]
    r = mt.simulate([], T, Q, init={"w": w_init, "cmd": "dcm:speed 51"})
    dt = r["t"][1]
    err = []
    for t, w in m2["video_omega_20pct"]:
        k = int(round((t - t20) / dt))
        err.append(r["w"][min(k, len(r["w"]) - 1)] - w)
    stop = next((t for t, w in zip(r["t"], r["w"]) if t > 0.05 and w == 0.0), None)
    return r, err, stop


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    pj = json.load(open(os.path.join(HERE, "params.json")))
    P = {k: v["value"] for k, v in pj["params"].items()}
    P.update(pj["identification_priors"])
    m1 = json.load(open(os.path.join(HERE, "data", "IMG_5741_measured.json")))
    m2 = json.load(open(os.path.join(HERE, "data", "IMG_5742_measured.json")))
    stop_meas = m2["t_stop"] - m2["t_20"]

    best = None
    for alpha in range(120, 401, 10):
        for Lmh in [round(0.1 * 1.15 ** k, 3) for k in range(30)]:
            Q, beta = derived(P, m1, alpha, Lmh * 1e-3)
            if Q["R"] <= 0:
                continue
            r, err, stop = run_20(Q, m2)
            rms = math.sqrt(sum(e * e for e in err) / len(err))
            cost = rms + 100 * abs((stop if stop else 2.0) - stop_meas)
            if best is None or cost < best[0]:
                best = (cost, alpha, Lmh, beta, Q, rms, stop)
    cost, alpha, Lmh, beta, Q, rms, stop = best
    print("best: alpha=Tc/J=%.0f  L=%.2f mH  beta=%.4f" % (alpha, Lmh, beta))
    print("  R=%.2f ohm  tau_e=L/R=%.2f ms  Tc=%.3g  c=%.3g  Ts=%.3g N*m" % (
        Q["R"], Q["L"] / Q["R"] * 1e3, Q["Tc"], Q["c"], Q["Ts"]))
    print("  20%% run: omega RMS error %.1f rad/s, stop %.3f s after step (measured %.3f)" % (
        rms, stop if stop else float("nan"), stop_meas))
    for pct in (20, 40, 45, 50, 60, 100):          # cold start from rest
        r = mt.simulate([(0, "dcm:speed %d" % (pct * 255 // 100))], 2.5, Q)
        print("  cold start %3d%%: %5.0f rpm, <i>=%.3f A" % (pct, r["w"][-1] * 30 / math.pi, r["i"][-1]))
    for pct in (20, 30, 40, 50):                   # sustain after full speed
        r = mt.simulate([(0, "dcm:speed 255"), (1.5, "dcm:speed %d" % (pct * 255 // 100))], 4, Q)
        print("  100%% -> %d%%: %5.0f rpm" % (pct, r["w"][-1] * 30 / math.pi))

    if args.write:
        for k, src in (("L", "fit: 20 % duty run IMG_5742 (PWM-resolved plant)"),
                       ("Tc", None), ("c", None), ("R", None),
                       ("Ts", "fit: breakaway at 47 % duty with PWM-resolved stall current")):
            pj["params"][k]["value"] = float("%.4g" % Q[k])
            if src:
                pj["params"][k]["source"] = src
        pj["params"]["Tc"]["source"] = "fit: joint coast-down (IMG_5741) + 20 % run (IMG_5742) x J"
        pj["fit_lowduty"] = dict(alpha=alpha, L_mH=Lmh, beta=float("%.4g" % beta),
                                 rms_rad_s=float("%.3g" % rms), stop_s=stop, stop_meas_s=stop_meas)
        with open(os.path.join(HERE, "params.json"), "w") as f:
            json.dump(pj, f, indent=1, ensure_ascii=False)
        print("wrote params.json")


if __name__ == "__main__":
    main()
