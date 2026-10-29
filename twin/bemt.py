#!/usr/bin/env python3
"""bemt.py — blade-element momentum model of the 3-blade toy propeller (static thrust, hover).

Geometry is measured, not fitted:
  chord   CHORD table (flat photo outline, = 2 x half-width; the IMG_5778 scan agrees within ~5 %)
  pitch   18 deg, constant along the span (IMG_5778 Object Capture scan, 3-blade mean at r/R 0.55-0.65,
          twist < ~3 deg; data/prop_pitch_IMG_5778.json)
  R       32 mm, hub 0.345 R, 3 blades
  camber  0 in the twin. The scan sections bulge up (dome side) by 0.05-0.15 c on 2 of 3 blades, which
          would make the camber work AGAINST forward thrust; but then even kL = 3 cannot reach the
          measured 1.9 gf for f/c >= 0.03, so the bulge is mostly spanwise curvature cut by the cylinders.
          Forward data allow -0.02 <= f/c (sign + = helps forward); the reverse run decides the sign.
Direction (sign of w): + = forward, air blown up away from the cup (balance reading rises);
  - = reverse, air blown down onto the cup top (Ø49.6 mm, 14 mm below the rotor plane):
      ground effect (Cheeseman-Bennett, scaled by the share of the mass flow that hits the cup)
        v_needed = v * (1 - (R/4z)^2 * phi)
      and the jet lands on the weighed cup and pan, so the balance sees only what escapes sideways:
        balance = -(1 - eta) T,  eta = 0.93 (IMG_5779: -0.14 g against the nominal 2.17 gf)
Each annulus solves hover momentum (Prandtl tip + hub loss) against blade-element forces:
  4 pi r F v^2 = 1/2 U^2 B c (cl cos phi - cd sin phi),   tan phi = v / (w r)
Aerofoil: thin plate at Re ~ 3e3-1.5e4,  cl = kL (Re/Re0)^m 2 pi (alpha +- 2 f/c),  cd = kD (2.656/sqrt(Re) + 2 sin^2 alpha)
  kL  lift efficiency at Re0 = 14977 (0.75 R, 3070 rpm): camber, high solidity sigma ~ 0.8, the cup under the rotor
  m   its Reynolds exponent (laminar separation weakens the lift as the blade slows): balance thrust grows
      as n^2.23, not n^2 (IMG_5785, thrust and speed measured together). kL and m are fitted to that run
  kD  drag multiplier: fitted with the motor in fit_joint.py (replaces the old c w|w|)
  kD_r  the same for reverse: 1.67 from the forward/reverse speed difference with the propeller on
        (IMG_5779, +0.57 %) after removing the motor's own asymmetry (propeller off, IMG_5780, -2.19 %)
Torque is split  Q = w^2 (kQi(w) + kD kQp(w)):  induced (lift tilted by the inflow) + profile (drag),
tabulated against w so the twin and the web pages only interpolate.

Usage:
  python3 twin/bemt.py                 # fit kL to the balance thrust, print T/Q/wake vs rpm
  python3 twin/bemt.py --kD 1.8 --write   # write the aero table (with that kD) into params.json
"""
import argparse
import json
import math
import os

import numpy as np
from scipy.optimize import brentq, minimize_scalar

HERE = os.path.dirname(os.path.abspath(__file__))
RHO, NU = 1.20, 1.52e-5                 # air at ~22 C
R, HUB, B = 0.032, 0.345, 3
PITCH = math.radians(18.0)
CAMBER = 0.0                            # f/c, signed: + helps forward (and hurts reverse)
Z_CUP, R_CUP = 0.014, 0.0248             # cup top below the rotor plane, its radius
ETA_PAN = 0.93                          # share of the reverse jet's momentum the weighed cup + pan stop (IMG_5779)
CHORD = [(0.34, 0.25), (0.40, 0.311), (0.45, 0.359), (0.50, 0.396), (0.55, 0.417), (0.60, 0.442),
         (0.65, 0.459), (0.70, 0.46), (0.75, 0.461), (0.80, 0.454), (0.85, 0.433), (0.90, 0.381),
         (0.95, 0.235), (1.0, 0.0)]      # (r/R, half-width/R), same table as twin3d.html
NX = 40
X = HUB + (1 - HUB) * (np.arange(NX) + 0.5) / NX
DX = (1 - HUB) / NX
C = 2 * np.interp(X, *zip(*CHORD)) * R

# balance thrust with the speed logged at the same time (TEL), 6 s steps x 2 passes (IMG_5785, data/thrust_steps_IMG_5785.json).
# The earlier IMG_5769 set (1.90/0.84/0.48/0.20/0.10 gf) paired the readings with speeds from another session.
THRUST = [(3067, 1.675), (2184, 0.735), (1592, 0.385), (1190, 0.200), (695, 0.055)]   # rpm, gf
RE0 = 14977.0                           # Re at 0.75 R and 3070 rpm, where kL is quoted
KL_M = 0.0                              # Reynolds exponent of the lift efficiency (set by fit_kL_m / --m)


def polar(alpha, re, kL, kD, camber=0.0):
    re = max(re, 1.0)
    return (kL * (re / RE0) ** KL_M * 2 * math.pi * (alpha + 2 * camber),
            kD * (2.656 / math.sqrt(re) + 2 * math.sin(alpha) ** 2))


def _pass(w, kL, kD, cam, kG):
    T = Qi = Qp = mdot = mdot_in = Pind = T_in = 0.0
    for x, c in zip(X, C):
        r = x * R
        Ut = w * r

        def f(phi):
            s = math.sin(phi)
            F = (2 / math.pi) * math.acos(math.exp(-B / 2 * (1 - x) / (x * s))) * \
                (2 / math.pi) * math.acos(math.exp(-B / 2 * (x - HUB) / (x * s)))
            U2 = Ut * Ut / math.cos(phi) ** 2
            cl, cd = polar(PITCH - phi, math.sqrt(U2) * c / NU, kL, kD, cam)
            return 4 * math.pi * r * F * (Ut * math.tan(phi) / kG) ** 2 - 0.5 * U2 * B * c * (cl * math.cos(phi) - cd * s), F

        phi = brentq(lambda p: f(p)[0], 1e-5, PITCH + 2 * max(cam, 0.0))
        F = f(phi)[1]
        U2 = Ut * Ut / math.cos(phi) ** 2
        cl, cd = polar(PITCH - phi, math.sqrt(U2) * c / NU, kL, kD, cam)
        q = 0.5 * RHO * U2 * B * c * R * DX
        dT = q * (cl * math.cos(phi) - cd * math.sin(phi))
        v = Ut * math.tan(phi)
        dm = RHO * 2 * math.pi * r * R * DX * v * F
        T += dT
        Qi += q * cl * math.sin(phi) * r
        Qp += q * cd * math.cos(phi) * r
        mdot += dm
        Pind += dT * v
        if r < R_CUP:
            mdot_in += dm
            T_in += dT
    return dict(T=T, Qi=Qi, Qp=Qp / kD, vw=T / mdot if mdot > 0 else 0.0, Pind=Pind,
                phi_cup=mdot_in / mdot if mdot > 0 else 0.0, T_in=T_in)


def solve(w, kL, kD=1.0, camber=CAMBER, ground=True, eta=ETA_PAN):
    """Hover BEMT at |w| rad/s; the sign of w is the direction. Returns dict of totals (SI), magnitudes,
    plus 'bal' = signed force the balance sees (+ = reading rises, as forward)."""
    if w == 0:
        return dict(T=0.0, Qi=0.0, Qp=0.0, vw=0.0, Pind=0.0, phi_cup=0.0, T_in=0.0, kG=1.0, bal=0.0)
    d = 1 if w > 0 else -1
    cam = d * camber
    kG = 1.0
    if d > 0 or not ground:
        s = _pass(abs(w), kL, kD, cam, 1.0)
    else:                                   # reverse: the cup under the jet; phi needs a few passes
        phi = 0.5
        for _ in range(4):
            kG = 1 - (R / (4 * Z_CUP)) ** 2 * phi
            s = _pass(abs(w), kL, kD, cam, kG)
            phi = s["phi_cup"]
    s["kG"] = kG
    s["bal"] = s["T"] if d > 0 else -(1 - eta) * s["T"]
    return s


def fit_kL(kD, camber=CAMBER):
    w = [rpm * math.pi / 30 for rpm, _ in THRUST]
    g = [gf for _, gf in THRUST]
    sd = [0.05 + 0.05 * x for x in g]            # 0.1 g display step (averaged over 16 readings) + 5 %

    def cost(kL):
        return sum(((solve(wi, kL, kD, camber)["T"] / 9.80665e-3 - gi) / si) ** 2 for wi, gi, si in zip(w, g, sd))
    r = minimize_scalar(cost, bounds=(0.1, 3.0), method="bounded")
    return r.x, r.fun


def fit_kL_m(kD, camber=CAMBER):
    """Fit kL and the Reynolds exponent m together (sets the module-level KL_M)."""
    global KL_M

    def cost(m):
        global KL_M
        KL_M = m
        return fit_kL(kD, camber)[1]
    r = minimize_scalar(cost, bounds=(0.0, 1.5), method="bounded", options=dict(xatol=1e-3))
    KL_M = r.x
    kL, chi2 = fit_kL(kD, camber)
    return kL, KL_M, chi2


def table(kL, kD, wmax=500.0, n=21, kD_r=None):
    """Coefficient tables over |w|; keys with '_r' are the reverse direction. kB = balance force / w^2 (signed)."""
    W = np.linspace(0, wmax, n)
    out = dict(w=[round(x, 1) for x in W])
    for d, suf in ((1, ""), (-1, "_r")):
        rows = [solve(d * max(wi, 5.0), kL, kD if d > 0 or kD_r is None else kD_r) for wi in W]
        w2 = np.maximum(W, 5.0) ** 2
        out["kT" + suf] = [float("%.4g" % (r["T"] / s)) for r, s in zip(rows, w2)]
        out["kQi" + suf] = [float("%.4g" % (r["Qi"] / s)) for r, s in zip(rows, w2)]
        out["kQp" + suf] = [float("%.4g" % (r["Qp"] / s)) for r, s in zip(rows, w2)]
        out["kV" + suf] = [float("%.4g" % (r["vw"] / max(wi, 5.0))) for r, wi in zip(rows, W)]
        out["kB" + suf] = [float("%.4g" % (r["bal"] / s)) for r, s in zip(rows, w2)]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kD", type=float, default=1.0, help="profile-drag multiplier (from fit_joint.py --bemt)")
    ap.add_argument("--kD-r", type=float, default=None, help="reverse profile-drag multiplier (default: same as --kD)")
    ap.add_argument("--write", action="store_true", help="write the aero table into params.json")
    ap.add_argument("--reverse", action="store_true", help="also predict the reverse direction (sensitivity to camber / cup)")
    ap.add_argument("--m", type=float, default=None, help="hold the Reynolds exponent of the lift (default: fit it with kL)")
    args = ap.parse_args()
    global KL_M
    if args.m is None:
        kL, m, chi2 = fit_kL_m(args.kD)
    else:
        KL_M = args.m
        kL, chi2 = fit_kL(args.kD)
    print("kL = %.3f, m = %.3f (kD = %.2f), chi2 = %.2f over %d thrust points" % (kL, KL_M, args.kD, chi2, len(THRUST)))
    A = math.pi * R * R
    print("  rpm   thrust gf (meas)   Q_ind uN.m  Q_prof uN.m   wake m/s   P_air mW   FM")
    for rpm in (695, 1190, 1592, 2184, 3067, 3700):
        w = rpm * math.pi / 30
        s = solve(w, kL, args.kD)
        Q = s["Qi"] + args.kD * s["Qp"]
        meas = dict(THRUST).get(rpm)
        fm = s["T"] ** 1.5 / math.sqrt(2 * RHO * A) / (Q * w)
        print("  %4d   %5.2f  %-6s        %6.1f      %6.1f       %4.2f      %5.1f    %.2f" % (
            rpm, s["T"] / 9.80665e-3, "(%.2f)" % meas if meas else "", s["Qi"] * 1e6, args.kD * s["Qp"] * 1e6,
            s["vw"], s["Pind"] * 1e3, fm))
    w = 3070 * math.pi / 30
    s = solve(w, kL, args.kD)
    print("equivalent at 3070 rpm: kT = %.3g N s^2, c = %.3g N m s^2 (old: kT 1.70e-7, c 2.85e-9)" % (
        s["T"] / w ** 2, (s["Qi"] + args.kD * s["Qp"]) / w ** 2))
    if args.reverse:
        reverse_report(kL, args.kD)
    if args.write:
        pj = json.load(open(os.path.join(HERE, "params.json")))
        pj["aero"] = dict(model="bemt.py: hover BEMT, pitch 18 deg, CHORD outline, R 32 mm, thin plate polar, "
                                "camber %.2f, reverse with cup ground effect" % CAMBER,
                          kL=float("%.4g" % kL), kL_m=float("%.4g" % KL_M), Re0=RE0, kD=args.kD, kD_r=args.kD_r or args.kD, **table(kL, args.kD, kD_r=args.kD_r),
                          note="cl = kL (Re/Re0)^kL_m 2 pi alpha; by |w|, '_r' = reverse: T = kT w^2 (air up forward, down reverse), Q = (kQi + kD kQp) w^2, "
                               "far-wake speed = kV |w|, balance force = kB w^2 (+ = reading rises); linear interpolation")
        json.dump(pj, open(os.path.join(HERE, "params.json"), "w"), indent=1, ensure_ascii=False)
        print("wrote params.json aero table")


def steady_full(P, d, kL, kD, camber, ground=True):
    """100 % steady speed (DC): K (V' - K w)/(R + rd) = Tc + b w + Q_aero(w), direction d."""
    Ron = P["R"] + P["rd"]
    def g(w):
        s = solve(d * w, kL, kD, camber, ground)
        return P["K"] * (P["Vs"] - P["V0"] - P["K"] * w) / Ron - P["Tc"] - P["b"] * w - (s["Qi"] + kD * s["Qp"])
    w = brentq(g, 1.0, (P["Vs"] - P["V0"]) / P["K"])
    return w, solve(d * w, kL, kD, camber, ground)


def reverse_report(kL0, kD):
    """100 % forward vs reverse with the joint-fit motor; sensitivity to the camber sign and the cup."""
    pj = json.load(open(os.path.join(HERE, "params.json")))
    P = {k: v["value"] for k, v in pj["params"].items()}
    print("\n100 %% steady, forward vs reverse (kD %.2f; kL refitted to the forward thrust for each camber)" % kD)
    print("  f/c    kL    | fwd rpm  T gf  | rev rpm  T gf  Q uN.m  kG    balance gf (eta %.2f)" % ETA_PAN)
    for cam in (0.0, -0.02, 0.02, 0.05):
        kL = fit_kL(kD, cam)[0]
        wf, f = steady_full(P, 1, kL, kD, cam)
        for ground in (True, False):
            wr, r = steady_full(P, -1, kL, kD, cam, ground)
            print("  %+.2f  %.3f | %5.0f  %5.2f  | %5.0f  %5.2f  %6.1f  %.2f   %+.2f%s" % (
                cam, kL, wf * 30 / math.pi, f["T"] / 9.80665e-3, wr * 30 / math.pi, r["T"] / 9.80665e-3,
                (r["Qi"] + kD * r["Qp"]) * 1e6, r["kG"], r["bal"] / 9.80665e-3, "" if ground else "   (no cup effect)"))


if __name__ == "__main__":
    main()
