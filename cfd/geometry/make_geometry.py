#!/usr/bin/env python3
"""make_geometry.py — watertight CFD geometry of the propeller rig, from measured parameters.

Frame: metres, origin on the cup axis at table level, z up (the IMG_5782 scan frame, with its y-up turned
into z-up). Forward rotation is +Omega about +z and blows air up (away from the cup), as on the bench.

Parts (one STL solid each, so each becomes its own patch):
  blades    3 flat plates of thickness t with round edges; outline = CHORD table (photo), pitch 18 deg with no
            twist (IMG_5778 scan), leading edge swept back as in twin3d.html. The leading edge is the lower edge
            (forward rotation moves it ahead), so the upper face is the pressure side.
  hub       body of revolution: flat bottom, cylinder, elliptic cap (IMG_5782 scan: bottom ~2.5 mm above the
            cup top, top ~17 mm above it)
  motor     130-class can (r 10.2 mm) whose top stands 9 mm below the blade plane, bearing boss r 5 mm
  cup       inverted paper cup: solid frustum (base r 37.8 mm on the pan, rim r 24.8 mm, 92 mm high) whose top
            (the cup's bottom) is recessed 8.5 mm below the rim, with the motor standing in the recess
            (photos IMG_5751-5752; recess floor at 109 mm in the IMG_5782 scan)
  scale     kitchen scale as a box whose whole top is the weighing pan (top at 25.4 mm); approximate footprint
  board     breadboard + ESPr on the pan, a box; approximate
Blades and hub rotate; everything else is fixed. Forces on blades+hub+motor+cup+scale-top+board add up to the
balance reading.

Usage:  python3 cfd/geometry/make_geometry.py [--out DIR] [--param k=v ...]
        e.g. --param t=1.1e-3 pitch=17 h=0.012 camber=0.02
"""
import argparse
import json
import math
import os
import struct

import numpy as np

# half-chord / R vs r / R, flat photo of the propeller (twin3d.html CHORD)
CHORD = [[0.34, 0.25], [0.40, 0.311], [0.45, 0.359], [0.50, 0.396], [0.55, 0.417], [0.60, 0.442], [0.65, 0.459],
         [0.70, 0.46], [0.75, 0.461], [0.80, 0.454], [0.85, 0.433], [0.90, 0.381], [0.95, 0.235], [1.0, 0]]

NOMINAL = dict(
    R=0.032,            # tip radius (64.0 mm diameter, IMG_5782)
    root=0.31,          # blade root inside the hub, r/R
    pitch=18.0,         # geometric pitch, deg, constant (IMG_5778)
    t=0.9e-3,           # blade thickness (not measured; 0.8-1.2 mm from the 2.0 g mass)
    camber=0.0,         # max camber / chord, + bulges to the suction (lower) side = more forward thrust
    sweep=0.12,         # chord centre moves back by sweep * (r - root R)
    h=0.010,            # blade plane (pitch axis) above the cup top (IMG_5782: 9-12 mm)
    hub_r=0.345 * 0.032,
    hub_below=7.5e-3,   # hub bottom below the blade plane
    hub_cyl=1.5e-3,     # cylinder top above the blade plane
    hub_cap=5.0e-3,     # elliptic cap height
    blades=3,
    cup_z0=0.0254, cup_z1=0.1174, cup_r0=0.0378, cup_r1=0.0248,
    cup_recess=8.5e-3,  # rim above the recessed floor
    cup_wall=1.0e-3,    # rim wall thickness (paper ~0.4 mm; thickened for meshing)
    motor_r=0.0102, boss_r=0.005, motor_top_below=9.0e-3, boss_h=0.8e-3,
    scale_lx=0.240, scale_ly=0.150, scale_cx=-0.035, scale_cy=-0.010, scale_rot=-25.0,
    board_lx=0.080, board_ly=0.050, board_h=0.010, board_cx=0.055, board_cy=-0.075,
)


def half_chord(x):
    xs, ys = np.array(CHORD).T
    return np.interp(x, xs, ys, left=CHORD[0][1], right=0.0)


# ---------------------------------------------------------------- mesh helpers
def tube(rings, close_start=True, close_end=True):
    """rings: (n_ring, n_pt, 3) closed loops -> triangles (watertight with fan caps)."""
    n, m, _ = rings.shape
    tris = []
    for i in range(n - 1):
        a, b = rings[i], rings[i + 1]
        for j in range(m):
            k = (j + 1) % m
            tris.append((a[j], b[j], b[k]))
            tris.append((a[j], b[k], a[k]))
    for ring, flip, on in ((rings[0], False, close_start), (rings[-1], True, close_end)):
        if not on:
            continue
        c = ring.mean(0)
        for j in range(m):
            k = (j + 1) % m
            tris.append((c, ring[k], ring[j]) if flip else (c, ring[j], ring[k]))
    T = np.array(tris)
    if signed_volume(T) < 0:
        T = T[:, ::-1]
    return T


def revolve(profile, n=96):
    """profile: [(r, z)] from bottom axis to top axis -> closed body of revolution."""
    ph = np.linspace(0, 2 * np.pi, n, endpoint=False)
    (_, z0), (_, z1) = profile[0], profile[-1]
    rings = np.array([[(r * math.cos(p), r * math.sin(p), z) for p in ph] for r, z in profile[1:-1]])
    T = tube(rings, close_start=False, close_end=False)
    if signed_volume(T) < 0:                     # tube() only fixes closed bodies; orient the side by hand
        T = T[:, ::-1]
    lo, hi = np.array([0, 0, z0]), np.array([0, 0, z1])
    a, b = rings[0], rings[-1]
    caps = [(lo, a[(j + 1) % n], a[j]) for j in range(n)] + [(hi, b[j], b[(j + 1) % n]) for j in range(n)]
    T = np.concatenate([T, np.array(caps)])
    return T if signed_volume(T) > 0 else T[:, ::-1]


def box(cx, cy, lx, ly, z0, z1, rot_deg=0.0):
    a = math.radians(rot_deg)
    u, v = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
    cs = [np.r_[np.array([cx, cy]) + sx * lx / 2 * u + sy * ly / 2 * v] for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    rings = np.array([[(c[0], c[1], z) for c in cs] for z in (z0, z1)])
    return tube(rings)


def signed_volume(T):
    return float(np.einsum("ij,ij->i", T[:, 0], np.cross(T[:, 1], T[:, 2])).sum() / 6)


def check_closed(T, tol=1e-9):
    """every edge used exactly twice, once each way (consistent orientation)."""
    key = np.round(T / tol).astype(np.int64)
    edges = {}
    for t in key:
        for i in range(3):
            a, b = tuple(t[i]), tuple(t[(i + 1) % 3])
            edges[(a, b)] = edges.get((a, b), 0) + 1
    bad = sum(1 for (a, b), c in edges.items() if c != 1 or edges.get((b, a), 0) != 1)
    return bad


def write_stl(path, solids):
    with open(path, "w") as f:
        for name, T in solids:
            f.write("solid %s\n" % name)
            for a, b, c in T:
                nrm = np.cross(b - a, c - a)
                nrm = nrm / (np.linalg.norm(nrm) or 1)
                f.write(" facet normal %.6e %.6e %.6e\n  outer loop\n" % tuple(nrm))
                for p in (a, b, c):
                    f.write("   vertex %.8e %.8e %.8e\n" % tuple(p))
                f.write("  endloop\n endfacet\n")
            f.write("endsolid %s\n" % name)


# ---------------------------------------------------------------- parts
def blade(P, k, nr=90, ns=64):
    R, t, th = P["R"], P["t"], math.radians(P["pitch"])
    z_r = P["cup_z1"] + P["h"]
    psi = 2 * math.pi * k / P["blades"]
    er, et, ez = np.array([math.cos(psi), math.sin(psi), 0]), np.array([-math.sin(psi), math.cos(psi), 0]), np.array([0, 0, 1.0])
    cdir = math.cos(th) * et - math.sin(th) * ez          # towards the leading edge (lower edge)
    ndir = math.sin(th) * et + math.cos(th) * ez          # pressure side (upper face)
    x0 = P["root"]
    xs = x0 + (1 - x0) * (1 - np.cos(np.linspace(0, np.pi / 2, nr)))   # clustered at the tip
    # stadium section: straight part + round edges, cut at the tip where the chord falls below the thickness
    u = np.linspace(0, 2 * np.pi, ns, endpoint=False)
    rings = []
    for x in xs:
        c = max(2 * half_chord(x) * R, t * 1.02)
        s0 = -P["sweep"] * (x - x0) * R
        a = c / 2 - t / 2                                   # half length of the straight part
        pts = []
        for ui in u:                                       # walk the stadium boundary by arc parameter
            per = 4 * a + math.pi * t
            L = ui / (2 * math.pi) * per
            if L < 2 * a:                                   # upper face, LE -> TE
                s, n = a - L, t / 2
            elif L < 2 * a + math.pi * t / 2:               # TE semicircle
                q = (L - 2 * a) / (t / 2)
                s, n = -a - t / 2 * math.sin(q), t / 2 * math.cos(q)
            elif L < 4 * a + math.pi * t / 2:               # lower face, TE -> LE
                s, n = -a + (L - 2 * a - math.pi * t / 2), -t / 2
            else:                                           # LE semicircle
                q = (L - 4 * a - math.pi * t / 2) / (t / 2)
                s, n = a + t / 2 * math.sin(q), -t / 2 * math.cos(q)
            n -= P["camber"] * c * (1 - (2 * s / c) ** 2) if abs(s) < c / 2 else 0.0
            pts.append(x * R * er + (s0 + s) * cdir + n * ndir + z_r * ez)
        rings.append(pts)
    return tube(np.array(rings))


def hub(P, n=24):
    z_r = P["cup_z1"] + P["h"]
    r, zb, zc, cap = P["hub_r"], z_r - P["hub_below"], z_r + P["hub_cyl"], P["hub_cap"]
    prof = [(0, zb), (r, zb), (r, zc)]
    for q in np.linspace(0, np.pi / 2, n)[1:-1]:
        prof.append((r * math.cos(q), zc + cap * math.sin(q)))
    prof.append((0, zc + cap))
    return revolve(prof)


def motor(P):
    z_r = P["cup_z1"] + P["h"]
    zt = z_r - P["motor_top_below"]
    zb = min(P["cup_z1"] - P["cup_recess"], zt) - 3e-3     # buried in the recess floor
    return revolve([(0, zb), (P["motor_r"], zb), (P["motor_r"], zt), (P["boss_r"], zt), (P["boss_r"], zt + P["boss_h"]), (0, zt + P["boss_h"])])


def cup(P):
    z0, z1, d, w = P["cup_z0"], P["cup_z1"], P["cup_recess"], P["cup_wall"]
    slope = (P["cup_r0"] - P["cup_r1"]) / (z1 - z0)            # outer radius grows downwards
    return revolve([(0, z0), (P["cup_r0"], z0), (P["cup_r1"], z1), (P["cup_r1"] - w, z1),
                    (P["cup_r1"] - w + slope * d, z1 - d), (0, z1 - d)])


def build(P):
    parts = [("blades", np.concatenate([blade(P, k) for k in range(P["blades"])])), ("hub", hub(P)), ("motor", motor(P)), ("cup", cup(P)),
             ("scale", box(P["scale_cx"], P["scale_cy"], P["scale_lx"], P["scale_ly"], 0.0, P["cup_z0"], P["scale_rot"])),
             ("board", box(P["board_cx"], P["board_cy"], P["board_lx"], P["board_ly"], P["cup_z0"], P["cup_z0"] + P["board_h"], P["scale_rot"]))]
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    ap.add_argument("--param", nargs="*", default=[])
    a = ap.parse_args()
    P = dict(NOMINAL)
    for kv in a.param:
        k, v = kv.split("=")
        P[k] = type(NOMINAL[k])(float(v))
    os.makedirs(a.out, exist_ok=True)
    parts = build(P)
    info = dict(params=P, parts={})
    for name, T in parts:
        info["parts"][name] = dict(triangles=len(T), volume_mm3=round(signed_volume(T) * 1e9, 1), open_edges=check_closed(T) if name != "blades" else
                                   sum(check_closed(blade(P, k)) for k in range(P["blades"])))
        write_stl(os.path.join(a.out, name + ".stl"), [(name, T)])
    rot = info["parts"]["blades"]["volume_mm3"] + info["parts"]["hub"]["volume_mm3"]
    info["rotor_volume_mm3"] = round(rot, 1)
    info["rotor_mass_g_if_solid"] = {"PS 1.05": round(rot * 1.05e-3, 2), "PP 0.91": round(rot * 0.91e-3, 2)}
    info["note"] = "the real hub is a shell, so the solid-hub mass overestimates; blades alone: %.2f g at 1.05 g/cm3" % (info["parts"]["blades"]["volume_mm3"] * 1.05e-3)
    json.dump(info, open(os.path.join(a.out, "geometry.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in info.items() if k != "params"}, indent=1))


if __name__ == "__main__":
    main()
