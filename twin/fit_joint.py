#!/usr/bin/env python3
"""fit_joint.py — fit K, R, L, rotor inertia, friction, aero drag and the brake drop to every run.

The propeller-off run (IMG_5759) is what makes K identifiable: with no load the motor runs near
V'/K, while the propeller run's load torque is known from the measured inertia (2.0 g on the balance)
times the filmed coast-down. Brake runs constrain V_bk (the L293D high-side + clamp-diode drop).

Observations (video-synced, see data/*_measured.json and README.md):
  A  prop,    100 %  steady            50.8 Hz   (IMG_5741..5744 drift 51.3 -> 48.6 with warm-up)
  B  prop,    coast stop from 50.8 Hz  0.757 s   (5741: 0.766, 5744: 0.749)
  C  prop,    brake stop from 49.1 Hz  0.724 s   (5744)
  D  prop,    100 % -> 20 % decel      44 video points + stop 0.976 s (5742)
  E  no prop, 100 %  steady            61.4 Hz   (5759 audio comb)
  F  no prop,  80 %  steady            44.6 Hz   (5759)
  G  no prop, coast stop from 61.4 Hz  0.278 s   (5759, 60 fps)
  H  no prop, brake stop from 61.4 Hz  0.244 s   (5759)
Ts is not fitted: it is set each time from the 47 % breakaway (README cold-start test).
--flag (with --bemt): the propeller-off runs E-H had a tape flag on the shaft; its drag gets its own term
c_flag w|w| (fitted) instead of hiding in b, and three more observations come in:
  E0  no prop, NO flag, 100 % steady   73.0 +- 0.8 Hz  (ADC ripple 73.6, audio 71.7-72.6; IMG_5780)
  Rb  no prop, reverse / forward - 1   -2.19 +- 0.11 %  (IMG_5780)       -> dV0_rev (extra bridge drop)
  Rp  prop,    reverse / forward - 1   +0.57 +- 0.25 %  (IMG_5779)       -> kD_r (reverse drag)
--bemt replaces the propeller's c w|w| by the BEMT table in params.json "aero" (bemt.py) and fits its
profile-drag multiplier kD instead of c.

Usage:  python3 twin/fit_joint.py [--write]
"""
import argparse
import json
import math
import os

import numpy as np
from scipy.optimize import brentq, least_squares

import motor_twin as mt

HERE = os.path.dirname(os.path.abspath(__file__))
TWO_PI = 2 * math.pi
J_PROP = 6.88e-7          # 2.0 g propeller, flat-photo outline, D = 64 mm (twin3d.html calculator)

# partial-duty steady speeds with the propeller, ADC tachometer adc:emf (data/adc/partial_duty_emf.json)
DUTY_RPM = {204: (2216, 80), 153: (1628, 67), 127: (1269, 40), 102: (712, 40)}
OBS = dict(A=(50.8, 1.0), B=(0.757, 0.02), C=(0.724, 0.035), E=(61.4, 0.3), F=(44.6, 0.5),
           G=(0.278, 0.02), H=(0.244, 0.02), Dstop=(0.976, 0.02))
NAMES = ["K", "R", "L", "Jr", "Tc", "c", "V_bk"]
FIX = {}                  # e.g. {"K": 6.06e-3} from the ADC back-EMF measurement (--fix-K)


def params(theta, base):
    P = dict(base)
    P.update(dict(zip(NAMES, np.exp(theta))))
    P.update(FIX)
    if "kD" in P:
        P["aero"] = dict(base["aero"], kD=P["kD"], kD_r=P.get("kD_r", base["aero"].get("kD_r", P["kD"])))
    return P


def with_breakaway(P, J):
    Q = dict(P, J=J, Ts=1e9)
    pl = mt.Plant(Q)
    for _ in range(60):
        pl._drive_period(0.47, 1.0 / Q["f_pwm"])
    return dict(Q, Ts=Q["K"] * pl.im)


def steady_dc(P):
    """100 % duty is plain DC: K (V' - K w)/(R + rd) = Tc + b w + Q_aero(w)  (rd i term folded into R + rd)."""
    Ron = P["R"] + P["rd"]
    f = lambda w: P["K"] * (P["Vs"] - P["V0"] - P["K"] * w) / Ron - P["Tc"] - P["b"] * w - mt.aero(P, w)[1]
    return brentq(f, 0.0, (P["Vs"] - P["V0"]) / P["K"])


def steady_dir(P, d):
    """steady_dc for either direction (reverse: extra bridge drop dV0_rev, reverse aero table)."""
    Q = dict(P, V0=P["V0"] + (P.get("dV0_rev", 0.0) if d < 0 else 0.0))
    Ron = Q["R"] + Q["rd"]
    f = lambda w: Q["K"] * (Q["Vs"] - Q["V0"] - Q["K"] * w) / Ron - Q["Tc"] - Q["b"] * w - mt.aero(Q, d * w)[1]
    return brentq(f, 0.0, (Q["Vs"] - Q["V0"]) / Q["K"])


FLAG = {}                 # --flag: observations that need the flag split


def stop_time(Q, w0, cmd, T=3.0):
    r = mt.simulate([], T, Q, init={"w": w0, "cmd": cmd if cmd != "dcm:off" else "dcm:off"})
    return next((t for t, w in zip(r["t"], r["w"]) if t > 0 and w == 0.0), T)


def residuals(theta, base, m2, verbose=False):
    P = params(theta, base)
    prop = with_breakaway(dict(P), J_PROP + P["Jr"])
    bare = with_breakaway(dict(P, c=P.get("cf", 0.0), aero=None), P["Jr"])   # IMG_5759: flag on the shaft
    out = {}
    if FLAG:
        nof = dict(bare, c=0.0)
        out["E0"] = steady_dc(nof) / TWO_PI
        out["Rb"] = steady_dir(nof, -1) / steady_dir(nof, 1) - 1
        out["Rp"] = steady_dir(prop, -1) / steady_dir(prop, 1) - 1
    out["A"] = steady_dc(prop) / TWO_PI
    out["E"] = steady_dc(bare) / TWO_PI
    r = mt.simulate([(0, "dcm:speed 204")], 2.5, bare, init={"w": TWO_PI * 44.0})
    out["F"] = float(np.mean(r["w"][-500:])) / TWO_PI
    out["B"] = stop_time(prop, TWO_PI * 50.8, "dcm:off")
    out["C"] = stop_time(dict(prop), TWO_PI * 49.1, "dcm:brake")
    out["G"] = stop_time(bare, TWO_PI * 61.4, "dcm:off")
    out["H"] = stop_time(bare, TWO_PI * 61.4, "dcm:brake")
    r = mt.simulate([], 1.6, prop, init={"w": TWO_PI * m2["f_at_20"], "cmd": "dcm:speed 51"})
    dt = r["t"][1]
    err = [r["w"][min(int(round((t - m2["t_20"]) / dt)), len(r["w"]) - 1)] - w for t, w in m2["video_omega_20pct"]]
    out["Dstop"] = next((t for t, w in zip(r["t"], r["w"]) if t > 0.05 and w == 0.0), 2.0)
    for duty, (rpm, sd) in DUTY_RPM.items():
        r = mt.simulate([(0, "dcm:speed 255"), (1.2, "dcm:speed %d" % duty)], 3.2, prop)
        out["rpm%d" % duty] = float(np.mean(r["w"][-300:])) * 30 / math.pi
    res = [(out[k] - v) / s for k, (v, s) in OBS.items()]
    res += [(out[k] - v) / s for k, (v, s) in FLAG.items()]
    res += [(out["rpm%d" % d] - rpm) / sd for d, (rpm, sd) in DUTY_RPM.items()]
    res.append(math.sqrt(sum(e * e for e in err) / len(err)) / 5.0)       # D curve RMS, 5 rad/s
    if verbose:
        return out, math.sqrt(sum(e * e for e in err) / len(err)), prop, bare
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--fix-K", type=float, help="hold K at a measured value (ADC back-EMF)")
    ap.add_argument("--free-V0", action="store_true", help="fit the L293D bridge drop V0 too")
    ap.add_argument("--free-rd", action="store_true", help="fit the L293D drop slope rd too")
    ap.add_argument("--free-b", action="store_true", help="fit a viscous friction term b*w too")
    ap.add_argument("--bemt", action="store_true", help="propeller load from the BEMT table; fit kD instead of c")
    ap.add_argument("--flag", action="store_true", help="split the tape-flag drag from b; add E0, Rb, Rp (needs --bemt)")
    args = ap.parse_args()
    if args.flag:
        FLAG.update(E0=(73.0, 0.8), Rb=(-0.0219, 0.0011), Rp=(0.0057, 0.0025))
    if args.bemt:
        NAMES[NAMES.index("c")] = "kD"
    if args.fix_K:
        FIX["K"] = args.fix_K
    if args.free_V0:
        NAMES.append("V0")
    if args.free_rd:
        NAMES.append("rd")
    if args.free_b:
        NAMES.append("b")
    pj = json.load(open(os.path.join(HERE, "params.json")))
    base = {k: v["value"] for k, v in pj["params"].items()}
    if args.bemt:
        base["aero"] = pj["aero"]
    m2 = json.load(open(os.path.join(HERE, "data", "IMG_5742_measured.json")))
    x0 = [8.5e-3, 9.0, 3e-3, 1.4e-7, 1.9e-4, 3.0 if args.bemt else 5e-9, 2.4] + ([1.8] if "V0" in NAMES else []) + ([0.6] if "rd" in NAMES else []) + ([2e-7] if "b" in NAMES else [])
    lo = [1e-3, 1.0, 1e-4, 1e-9, 1e-5, 0.1 if args.bemt else 1e-10, 0.5] + ([0.5] if "V0" in NAMES else []) + ([0.01] if "rd" in NAMES else []) + ([1e-10] if "b" in NAMES else [])
    hi = [3e-2, 40.0, 5e-2, 2e-6, 3e-3, 30.0 if args.bemt else 1e-7, 4.5] + ([3.5] if "V0" in NAMES else []) + ([20.0] if "rd" in NAMES else []) + ([5e-6] if "b" in NAMES else [])
    if args.flag:
        NAMES.extend(["cf", "kD_r", "dV0_rev"])
        x0 += [3e-9, base["aero"].get("kD_r", 1.7), base.get("dV0_rev", 0.06)]
        lo += [1e-11, 0.1, 1e-3]
        hi += [1e-7, 30.0, 0.5]
    if args.fix_K:
        x0[0] = args.fix_K
    x0, lo, hi = np.log(x0), np.log(lo), np.log(hi)
    sol = least_squares(residuals, x0, args=(base, m2), bounds=(lo, hi), diff_step=0.02, x_scale=1.0)
    out, rms, prop, bare = residuals(sol.x, base, m2, verbose=True)
    P = params(sol.x, base)
    print("fit (cost %.3f):" % sol.cost)
    for k in NAMES:
        print("  %-5s %.4g%s" % (k, P[k], "  (fixed)" if k in FIX else ""))
    print("  Ts    %.4g (from 47 %% breakaway)   J_total(prop) %.3g" % (prop["Ts"], prop["J"]))
    print("observation    model    measured")
    for k, (v, s) in OBS.items():
        print("  %-6s %9.3f %9.3f   (%+.1f sigma)" % (k, out[k], v, (out[k] - v) / s))
    for d, (rpm, sd) in DUTY_RPM.items():
        k = "rpm%d" % d
        print("  %-6s %9.0f %9.0f   (%+.1f sigma)" % (k, out[k], rpm, (out[k] - rpm) / sd))
    for k, (v, s) in FLAG.items():
        print("  %-6s %9.4f %9.4f   (%+.1f sigma)" % (k, out[k], v, (out[k] - v) / s))
    print("  D rms  %.1f rad/s" % rms)
    # Jacobian-based 1-sigma (relative) uncertainties
    try:
        Jm = sol.jac
        cov = np.linalg.inv(Jm.T @ Jm)
        print("relative 1-sigma:", {k: "%.0f%%" % (100 * math.sqrt(cov[i, i])) for i, k in enumerate(NAMES)})
    except np.linalg.LinAlgError:
        pass
    wA = TWO_PI * out["A"]
    i_prop = (prop["Tc"] + prop["b"] * wA + mt.aero(prop, wA)[1]) / P["K"]
    print("currents: prop 100 %% %.3f A, no-load %.3f A, stall DC %.3f A" % (
        i_prop, P["Tc"] / P["K"], (P["Vs"] - P["V0"]) / (P["R"] + P["rd"])))
    if args.write:
        src = "fit: joint (fit_joint.py) over prop + propeller-off runs"
        for k in NAMES:
            if k in FIX:
                pj["params"][k]["value"] = float("%.4g" % P[k])
                pj["params"][k]["source"] = "measured: ADC back-EMF vs commutator-ripple speed (3 ripples/rev), 2 coast-downs, rms 0.5 %"
                continue
            if k in ("kD", "kD_r"):
                pj["aero"][k] = float("%.4g" % P[k])
                continue
            if k == "cf":
                pj["params"]["c_flag"] = dict(value=float("%.4g" % P[k]), unit="N*m*s^2/rad^2",
                                              source="fit: drag of the tape flag on the bare shaft in IMG_5759 (fit_joint.py --flag); not part of the motor")
                continue
            if k == "dV0_rev":
                pj["params"][k]["value"] = float("%.4g" % P[k])
                pj["params"][k]["source"] = "fit: joint --flag, from the propeller-off reverse/forward ratio -2.19 % (IMG_5780); extra L293D drop in reverse"
                continue
            key = k if k != "Jr" else None
            if key:
                pj["params"][k]["value"] = float("%.4g" % P[k])
                pj["params"][k]["source"] = src
        pj["params"]["J"]["value"] = float("%.4g" % prop["J"])
        pj["params"]["J"]["source"] = "measured prop 6.88e-7 (2.0 g x outline) + fitted rotor %.3g" % P["Jr"]
        pj["params"]["Ts"]["value"] = float("%.4g" % prop["Ts"])
        pj["params"]["Ts"]["source"] = "47 % breakaway with the joint-fit plant"
        pj["rotor_J"] = float("%.4g" % P["Jr"])
        pj["fit_joint"] = {k: float("%.4g" % out[k]) for k in out}
        pj["fit_joint"]["D_rms_rad_s"] = float("%.3g" % rms)
        json.dump(pj, open(os.path.join(HERE, "params.json"), "w"), indent=1, ensure_ascii=False)
        print("wrote params.json")


if __name__ == "__main__":
    main()
