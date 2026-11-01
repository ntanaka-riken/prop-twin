#!/usr/bin/env python3
"""disk.py — the actuator disk of task C3: the rotor as a ring of body forces, from the BEMT (twin/bemt.py).

The radial shape of the thrust and the torque comes from the BEMT with the stage-1 LES polars (no fitted factor, no
ground effect: the cup is in the flow solution). The totals are scaled to the blade forces of the stage-3 URANS
(blades only: the hub is a solid body in C3), so C3 tests the flow around the cup and the balance, not the BEMT.

Writes twin/data/cfd/c3_disk.json:
  per direction (fwd / rev): r [m], dT, dQ per annulus (N, N m), the totals of the BEMT and of the URANS,
  and the same in NZ coarse rings for the OpenFOAM cell zones.

Usage:  python3 cfd/c3/disk.py [--rings 8]
"""
import argparse
import json
import math
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "twin"))
import bemt  # noqa: E402

G = 9.80665e-3              # N per gf
RPM = 3067
# stage-3 URANS (twin/data/cfd/ami_runs.json, L0-abs_urans_*_3067): force on the blades alone (gf) and rotor torque (uN m)
URANS = dict(fwd=dict(blades_gf=1.4855, torque_uNm=155.94), rev=dict(blades_gf=1.85, torque_uNm=164.56))
Z_DISK = 0.1174 + 0.010     # blade plane: cup top + h (cfd/geometry/make_geometry.py NOMINAL)
THICK = 4.0e-3              # axial thickness of the disk (the blades span ~9 mm axially at 0.75 R)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rings", type=int, default=8)
    a = ap.parse_args()
    bemt.CFD_POLAR = bemt.SectionPolar(os.path.join(ROOT, "twin", "data", "cfd", "section_polars.json"))
    out = dict(source="twin/bemt.py with the stage-1 LES polars (kL = kD = 1, no ground effect), %d rpm; totals scaled "
                      "to the stage-3 URANS blade force and rotor torque" % RPM,
               z_disk=Z_DISK, thickness=THICK, r_hub=bemt.HUB * bemt.R, r_tip=bemt.R, rpm=RPM)
    w = RPM * math.pi / 30
    for d, key in ((1, "fwd"), (-1, "rev")):
        s = bemt.solve(d * w, 1.0, 1.0, ground=False)
        r = [x[0] for x in s["dist"]]
        T0, Q0 = sum(x[1] for x in s["dist"]), sum(x[2] for x in s["dist"])
        kT = URANS[key]["blades_gf"] * G / T0
        kQ = URANS[key]["torque_uNm"] * 1e-6 / Q0
        dT = [x[1] * kT for x in s["dist"]]
        dQ = [x[2] * kQ for x in s["dist"]]
        edges = [bemt.HUB * bemt.R + (bemt.R - bemt.HUB * bemt.R) * i / a.rings for i in range(a.rings + 1)]
        rings = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            sel = [i for i, ri in enumerate(r) if lo <= ri < hi]
            rings.append(dict(r0=round(lo, 6), r1=round(hi, 6), T=sum(dT[i] for i in sel), Q=sum(dQ[i] for i in sel)))
        out[key] = dict(direction=d, bemt_T_gf=round(T0 / G, 4), bemt_Q_uNm=round(Q0 * 1e6, 2),
                        T_gf=URANS[key]["blades_gf"], Q_uNm=URANS[key]["torque_uNm"],
                        r=[round(x, 6) for x in r], dT=dT, dQ=dQ, rings=rings)
        print("%s: BEMT %.3f gf %.1f uN m -> URANS %.3f gf %.1f uN m; peak dT at r = %.1f mm" % (
            key, T0 / G, Q0 * 1e6, URANS[key]["blades_gf"], URANS[key]["torque_uNm"], 1e3 * r[dT.index(max(dT))]))
    p = os.path.join(ROOT, "twin", "data", "cfd", "c3_disk.json")
    json.dump(out, open(p, "w"), indent=1)
    print(p)


if __name__ == "__main__":
    main()
