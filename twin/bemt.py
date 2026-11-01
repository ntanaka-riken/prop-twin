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
T_BLADE = 0.9e-3                        # blade thickness, for t/c of the CFD polar
CFD_POLAR = None                        # SectionPolar from --polar: replaces the thin-plate formula, kL and kD become multipliers


class SectionPolar:
    """cl, cd of the stage-1 section LES (cfd/section, twin/data/cfd/section_polars.json), interpolated linearly in
    alpha, t/c and f/c and in log Re (clamped to the table). The table has f/c >= 0; f < 0 is the mirror image:
    cl(-f, a) = -cl(f, -a), cd(-f, a) = cd(f, -a)."""

    def __init__(self, path):
        rows = [r for r in json.load(open(path))["cases"] if "cl" in r]
        n = {}
        for r in rows:
            n.setdefault((r["re"], r["t"], r["f"]), set()).add(r["alpha"])
        combos = {(t, f) for _, t, f in n}
        nmax = {f: max(len(v) for k, v in n.items() if k[2] == f) for _, f in combos}
        part = {k[0] for k, v in n.items() if len(v) < nmax[k[2]]}
        part |= {re for re in {k[0] for k in n} if {(t, f) for r2, t, f in n if r2 == re} != combos}
        rows = [r for r in rows if r["re"] not in part]     # a Reynolds number still being computed is left out whole
        self.missing_re = sorted(part)
        self.re = sorted({r["re"] for r in rows})
        self.t = sorted({r["t"] for r in rows})
        self.f = sorted({r["f"] for r in rows})
        self.tab = {}
        for r in rows:
            self.tab.setdefault((r["re"], r["t"], r["f"]), []).append((r["alpha"], r["cl"], r["cd"]))
        for k, v in self.tab.items():
            v.sort()
            if k[2] == 0.0:                     # symmetric section: only alpha >= 0 was run
                v[:0] = [(-a, -cl, cd) for a, cl, cd in v[::-1] if a > 0]
            self.tab[k] = np.array(v)

    @staticmethod
    def _bracket(grid, x, log=False):
        if x <= grid[0] or len(grid) == 1:
            return [(grid[0], 1.0)]
        if x >= grid[-1]:
            return [(grid[-1], 1.0)]
        j = int(np.searchsorted(grid, x))
        a, b = grid[j - 1], grid[j]
        u = (math.log(x / a) / math.log(b / a)) if log else (x - a) / (b - a)
        return [(a, 1 - u), (b, u)]

    def __call__(self, alpha_deg, re, tc, f):
        s = -1.0 if f < 0 else 1.0
        a = s * alpha_deg
        cl = cd = 0.0
        for rv, wr in self._bracket(self.re, re, log=True):
            for tv, wt in self._bracket(self.t, tc):
                for fv, wf in self._bracket(self.f, abs(f)):
                    T = self.tab[(rv, tv, fv)]
                    w = wr * wt * wf
                    cl += w * np.interp(a, T[:, 0], T[:, 1])
                    cd += w * np.interp(a, T[:, 0], T[:, 2])
        return s * cl, cd


def polar(alpha, re, kL, kD, camber=0.0, tc=0.03):
    re = max(re, 1.0)
    if CFD_POLAR is not None:
        cl, cd = CFD_POLAR(math.degrees(alpha), re, tc, camber)
        return kL * cl, kD * cd
    return (kL * (re / RE0) ** KL_M * 2 * math.pi * (alpha + 2 * camber),
            kD * (2.656 / math.sqrt(re) + 2 * math.sin(alpha) ** 2))


def _pass(w, kL, kD, cam, kG):
    T = Qi = Qp = mdot = mdot_in = Pind = T_in = 0.0
    dist = []                               # per annulus: r, thrust, torque (SI), for the actuator disk of cfd/c3
    for x, c in zip(X, C):
        r = x * R
        Ut = w * r

        def f(phi):
            s = math.sin(phi)
            F = (2 / math.pi) * math.acos(math.exp(-B / 2 * (1 - x) / (x * s))) * \
                (2 / math.pi) * math.acos(math.exp(-B / 2 * (x - HUB) / (x * s)))
            U2 = Ut * Ut / math.cos(phi) ** 2
            cl, cd = polar(PITCH - phi, math.sqrt(U2) * c / NU, kL, kD, cam, T_BLADE / c)
            return 4 * math.pi * r * F * (Ut * math.tan(phi) / kG) ** 2 - 0.5 * U2 * B * c * (cl * math.cos(phi) - cd * s), F

        phi = brentq(lambda p: f(p)[0], 1e-5, PITCH + 2 * max(cam, 0.0))
        F = f(phi)[1]
        U2 = Ut * Ut / math.cos(phi) ** 2
        cl, cd = polar(PITCH - phi, math.sqrt(U2) * c / NU, kL, kD, cam, T_BLADE / c)
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
        dist.append((r, dT, q * (cl * math.sin(phi) + cd * math.cos(phi)) * r))
    return dict(dist=dist, T=T, Qi=Qi, Qp=Qp / kD, vw=T / mdot if mdot > 0 else 0.0, Pind=Pind,
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
    ap.add_argument("--polar", help="section polars from the stage-1 LES (twin/data/cfd/section_polars.json): print the "
                                    "thrust with kL = kD = 1, then fit kL as a multiplier on it")
    ap.add_argument("--camber", type=float, default=CAMBER, help="f/c, + helps forward (with --polar)")
    args = ap.parse_args()
    global KL_M, CFD_POLAR
    if args.polar:
        CFD_POLAR = SectionPolar(args.polar)
        print("CFD section polars (no fitted factor), f/c %+.3f:" % args.camber)
        print("  rpm   thrust gf (meas)   Q uN.m")
        for rpm, gf in THRUST:
            sv = solve(rpm * math.pi / 30, 1.0, 1.0, args.camber)
            print("  %4d   %5.3f  (%.3f)   %6.1f" % (rpm, sv["T"] / 9.80665e-3, gf, (sv["Qi"] + sv["Qp"]) * 1e6))
        kL, chi2 = fit_kL(1.0, args.camber)
        print("multiplier on the CFD lift that fits the balance: kL = %.3f (chi2 %.2f)" % (kL, chi2))
        return
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
