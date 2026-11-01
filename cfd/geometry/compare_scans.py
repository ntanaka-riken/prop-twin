#!/usr/bin/env python3
"""compare_scans.py — check the CFD geometry (make_geometry.py) against the two Object Capture scans.

1. Propeller alone (IMG_5778): the yellow point cloud and its 3-fold axis (axis.npz from the release zip
   scan_prop_IMG_5778.zip). The points are put on the axis, scaled to R = 32 mm, and the CAD rotor is fitted
   over rotation about the axis, flip (the propeller lay upside down or not) and axial offset. Then pitch,
   thickness and sweep are varied one at a time to see which values the scan prefers.
2. Rig on the balance (IMG_5782, rig_balance_mm.obj): radius-height profile of the cup, motor, hub and blade
   band against the CAD parts.

Usage:  python3 cfd/geometry/compare_scans.py <axis.npz> <rig_balance_mm.obj> [--out cfd/geometry/out]
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_geometry as mg  # noqa: E402

SCAN_R_UNITS = 0.18          # tip radius of the IMG_5778 cloud in scan units (twin/data/prop_pitch_IMG_5778.json)


def surface_points(T, step=0.25e-3):
    """sample triangles roughly every `step` metres."""
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    n = np.maximum(1, (area / step ** 2).astype(int))
    rng = np.random.default_rng(0)
    idx = np.repeat(np.arange(len(T)), n)
    u, v = rng.random(len(idx)), rng.random(len(idx))
    m = u + v > 1
    u[m], v[m] = 1 - u[m], 1 - v[m]
    return a[idx] + u[:, None] * (b[idx] - a[idx]) + v[:, None] * (c[idx] - a[idx])


def rotor_points(P):
    z_r = P["cup_z1"] + P["h"]
    T = np.concatenate([mg.blade(P, k) for k in range(P["blades"])] + [mg.hub(P)])
    return surface_points(T) - [0, 0, z_r]


def scan_local(npz):
    d = np.load(npz)
    a, c, Q = d["a"], d["c"], d["P"]
    z = a / np.linalg.norm(a)
    x = np.cross([0, 1.0, 0], z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    L = (Q - c) @ np.array([x, y, z]).T * (0.032 / SCAN_R_UNITS)
    return L - [0, 0, np.median(L[:, 2])]          # the fitted centre may sit anywhere along the axis


def fit_pose(S, cad):
    """best (flip, angle, dz) by mean clipped distance scan -> CAD."""
    tree = cKDTree(cad)
    best = None
    Sfull, S = S, S[::4]                                 # coarse search on a quarter of the points
    for flip in (1, -1):
        S1 = S * [1, flip, flip]
        def cost(phi, dz):
            cph, sph = math.cos(phi), math.sin(phi)
            S2 = S1 @ np.array([[cph, -sph, 0], [sph, cph, 0], [0, 0, 1]]).T + [0, 0, dz]
            d, _ = tree.query(S2, distance_upper_bound=3e-3, workers=-1)
            return np.mean(np.minimum(d, 3e-3) ** 2), d
        for phi0 in np.linspace(0, 2 * np.pi / 3, 24, endpoint=False):
            for dz in np.linspace(-6e-3, 6e-3, 9):
                c, _ = cost(phi0, dz)
                if best is None or c < best[0]:
                    best = (c, flip, phi0, dz)
    _, flip, phi, dz = best
    S1 = Sfull * [1, flip, flip]
    for _ in range(3):                                   # coordinate refinement
        phi = minimize_scalar(lambda p: cost_of(S1, tree, p, dz), bounds=(phi - 0.15, phi + 0.15), method="bounded").x
        dz = minimize_scalar(lambda q: cost_of(S1, tree, phi, q), bounds=(dz - 2e-3, dz + 2e-3), method="bounded").x
    cph, sph = math.cos(phi), math.sin(phi)
    S2 = S1 @ np.array([[cph, -sph, 0], [sph, cph, 0], [0, 0, 1]]).T + [0, 0, dz]
    return flip, phi, dz, S2


def cost_of(S1, tree, phi, dz):
    cph, sph = math.cos(phi), math.sin(phi)
    d, _ = tree.query(S1 @ np.array([[cph, -sph, 0], [sph, cph, 0], [0, 0, 1]]).T + [0, 0, dz], distance_upper_bound=3e-3, workers=-1)
    return np.mean(np.minimum(d, 3e-3) ** 2)


def stats(d):
    return dict(median_mm=round(float(np.median(d)) * 1e3, 2), p90_mm=round(float(np.percentile(d, 90)) * 1e3, 2),
                rms_clip3_mm=round(float(np.sqrt(np.mean(np.minimum(d, 3e-3) ** 2))) * 1e3, 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("axis_npz")
    ap.add_argument("rig_obj")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    a = ap.parse_args()
    P0 = dict(mg.NOMINAL)
    res = {}

    # ---- 1. propeller alone
    S = scan_local(a.axis_npz)
    S = S[np.hypot(S[:, 0], S[:, 1]) < 0.036]
    cad = rotor_points(P0)
    flip, phi, dz, S2 = fit_pose(S, cad)
    d, _ = cKDTree(cad).query(S2)
    rs = np.hypot(S2[:, 0], S2[:, 1])
    res["prop_nominal"] = dict(points=len(S2), flip=flip, **stats(d),
                               by_radius={"%.2f-%.2f R" % (lo, hi): stats(d[(rs >= lo * 0.032) & (rs < hi * 0.032)])
                                          for lo, hi in ((0, 0.345), (0.345, 0.6), (0.6, 0.85), (0.85, 1.2))})
    S1 = S * [1, flip, flip]
    sens = {}
    for key, vals in (("pitch", [14, 16, 18, 20, 22]), ("t", [0.6e-3, 0.9e-3, 1.2e-3, 1.5e-3]), ("sweep", [0.0, 0.12, 0.25]), ("camber", [-0.03, 0.0, 0.03])):
        row = {}
        for v in vals:
            P = dict(P0, **{key: v})
            c2 = rotor_points(P)
            tree = cKDTree(c2)
            ph, q = phi, dz                                   # re-fit the pose for each shape
            for _ in range(2):
                ph = minimize_scalar(lambda p: cost_of(S1, tree, p, q), bounds=(ph - 0.15, ph + 0.15), method="bounded").x
                q = minimize_scalar(lambda z: cost_of(S1, tree, ph, z), bounds=(q - 2e-3, q + 2e-3), method="bounded").x
            row[str(v)] = round(math.sqrt(cost_of(S1, tree, ph, q)) * 1e3, 3)
        sens[key] = row
    res["prop_sensitivity_rms_clip3_mm"] = sens

    # ---- 2. rig on the balance (y-up mm -> z-up m)
    V = np.array([[float(x) for x in l.split()[1:4]] for l in open(a.rig_obj) if l.startswith("v ")]) * 1e-3
    V = np.c_[V[:, 0], -V[:, 2], V[:, 1]]
    r, z = np.hypot(V[:, 0], V[:, 1]), V[:, 2]
    prof = []
    for z0 in np.arange(0.030, 0.140, 0.004):
        m = (z >= z0) & (z < z0 + 0.004) & (r < 0.045)
        if m.sum() < 10:
            continue
        cupr = P0["cup_r0"] + (P0["cup_r1"] - P0["cup_r0"]) * (z0 + 0.002 - P0["cup_z0"]) / (P0["cup_z1"] - P0["cup_z0"])
        prof.append(dict(z_mm=round((z0 + 0.002) * 1e3, 1), scan_r_p50_mm=round(float(np.median(r[m])) * 1e3, 1),
                         scan_r_p95_mm=round(float(np.percentile(r[m], 95)) * 1e3, 1),
                         cad_cup_r_mm=round(cupr * 1e3, 1) if z0 + 0.002 <= P0["cup_z1"] else None))
    z_r = P0["cup_z1"] + P0["h"]
    bl = np.concatenate([mg.blade(P0, k) for k in range(3)]).reshape(-1, 3)
    blr = np.hypot(bl[:, 0], bl[:, 1])
    band = (r > 0.014) & (r < 0.034) & (z > P0["cup_z1"] + 0.001)
    hubm = (r < 0.006) & (z > P0["cup_z1"])
    res["rig"] = dict(
        cup_profile=prof,
        blade_band_z_mm=dict(scan_p5_p50_p95=np.round(np.percentile(z[band], [5, 50, 95]) * 1e3, 1).tolist(),
                             cad_min_mid_max=np.round([bl[blr > 0.014, 2].min() * 1e3, z_r * 1e3, bl[blr > 0.014, 2].max() * 1e3], 1).tolist()),
        hub_top_z_mm=dict(scan_p98=round(float(np.percentile(z[hubm], 98)) * 1e3, 1) if hubm.any() else None,
                          cad=round((z_r + P0["hub_cyl"] + P0["hub_cap"]) * 1e3, 1)),
        recess_floor_z_mm=dict(scan_p25_r11_18=round(float(np.percentile(z[(r > 0.011) & (r < 0.018) & (z > 0.100) & (z < 0.121)], 25)) * 1e3, 1),
                               cad=round((P0["cup_z1"] - P0["cup_recess"]) * 1e3, 1)),
        prop_radius_mm=dict(scan_p99=round(float(np.percentile(r[band], 99)) * 1e3, 1), cad=P0["R"] * 1e3))
    json.dump(res, open(os.path.join(a.out, "compare_scans.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))

    # ---- figure
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(16, 5.4))
    ax[0].scatter(cad[::20, 0] * 1e3, cad[::20, 1] * 1e3, s=0.3, c="0.6", label="CAD")
    ax[0].scatter(S2[:, 0] * 1e3, S2[:, 1] * 1e3, s=1, c=np.minimum(d * 1e3, 2), cmap="viridis", label="scan (colour = distance, mm)")
    ax[0].set_aspect("equal"); ax[0].set_title("IMG_5778 propeller: top (mm)"); ax[0].legend(loc="upper right", fontsize=8)
    th = np.arctan2(S2[:, 1], S2[:, 0])
    ax[1].scatter(rs * 1e3, S2[:, 2] * 1e3, s=1, c="C1", label="scan")
    ax[1].scatter(np.hypot(cad[::10, 0], cad[::10, 1]) * 1e3, cad[::10, 2] * 1e3, s=0.3, c="0.5", label="CAD")
    ax[1].set_title("propeller: radius vs height (mm)"); ax[1].legend(fontsize=8)
    m = r < 0.05
    ax[2].scatter(r[m] * 1e3, z[m] * 1e3, s=1, c="0.7", label="IMG_5782 scan")
    for name, T in mg.build(P0)[:4]:
        q = surface_points(T, 0.6e-3)
        ax[2].scatter(np.hypot(q[:, 0], q[:, 1]) * 1e3, q[:, 2] * 1e3, s=0.2, label="CAD " + name)
    ax[2].set_xlim(0, 50); ax[2].set_ylim(95, 142); ax[2].set_aspect("equal"); ax[2].set_title("rig: radius vs height (mm)"); ax[2].legend(fontsize=7, loc="lower left")
    fig.tight_layout(); fig.savefig(os.path.join(a.out, "compare_scans.png"), dpi=110)


if __name__ == "__main__":
    main()
