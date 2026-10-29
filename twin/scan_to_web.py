#!/usr/bin/env python3
"""scan_to_web.py — turn the Object Capture scan (OBJ + texture) into compact web data for twin3d.html.

Steps (numbers come from the scan itself, see twin/README.md "3D モデル"):
  1. level: RANSAC plane on the beige table faces -> rotate its normal to +Y
  2. axis : cup = brown faces; least-squares circle centre with radius linear in height
  3. scale: minimum-area rectangle of the white breadboard faces = 82.5 x 54.5 mm
  4. cut  : within CUT_R_MM of the axis, drop faces above the cup top and yellow faces above
            CUT_Y_MM (the propeller lump: thin glossy blades do not reconstruct)
            -> twin3d.html draws a parametric motor + rotor there
  5. crop : keep a square of +-CROP_MM around the rig
  6. write: rig_mesh.json = base64 of header(int32 nv, ni) + float32 xyz (mm) + float32 uv
            + uint32 idx, rig_tex.jpg (2048 px), rig_meta.json

Usage:
  python3 twin/scan_to_web.py SCAN_DIR [OUT_DIR]      (SCAN_DIR holds rig.obj + Texture_diffuseColor.png)
"""
import base64
import json
import os
import sys

import cv2
import numpy as np
from scipy.spatial import cKDTree

BOARD_MM = (82.5, 54.5)          # 400-hole half-size breadboard (30 rows)
CUT_Y_MM, CUT_R_MM = 80.0, 45.0
CROP_MM = 190.0


def load_obj(path):
    V, T, Fv, Ft = [], [], [], []
    for line in open(path):
        if line.startswith("v "):
            V.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("vt "):
            T.append([float(x) for x in line.split()[1:3]])
        elif line.startswith("f "):
            p = [x.split("/") for x in line.split()[1:4]]
            Fv.append([int(a[0]) - 1 for a in p])
            Ft.append([int(a[1]) - 1 for a in p])
    return np.array(V), np.array(T), np.array(Fv), np.array(Ft)


def main():
    scan = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "3d")
    os.makedirs(out, exist_ok=True)
    V, T, Fv, Ft = load_obj(os.path.join(scan, "rig.obj"))
    tex = cv2.imread(os.path.join(scan, "Texture_diffuseColor.png"))
    th, tw = tex.shape[:2]
    uvc = T[Ft].mean(1)
    col = tex[np.clip(((1 - uvc[:, 1]) * (th - 1)).astype(int), 0, th - 1),
              np.clip((uvc[:, 0] * (tw - 1)).astype(int), 0, tw - 1)]
    hsv = cv2.cvtColor(col[None].astype(np.uint8), cv2.COLOR_BGR2HSV)[0].astype(float)
    C = V[Fv].mean(1)

    # 1. level on the table plane
    P = C[(hsv[:, 1] < 70) & (hsv[:, 2] > 150)]
    rng = np.random.default_rng(0)
    best = None
    for _ in range(400):
        s = P[rng.choice(len(P), 3, replace=False)]
        n = np.cross(s[1] - s[0], s[2] - s[0])
        if np.linalg.norm(n) < 1e-12:
            continue
        n /= np.linalg.norm(n)
        k = (np.abs((P - s[0]) @ n) < 0.004).sum()
        if best is None or k > best[0]:
            best = (k, n, s[0])
    _, n, p0 = best
    inl = P[np.abs((P - p0) @ n) < 0.004]
    c0 = inl.mean(0)
    n = np.linalg.svd(inl - c0)[2][2]
    n = n if n[1] > 0 else -n
    y = np.array([0, 1.0, 0])
    ax = np.cross(n, y)
    sa, ca = np.linalg.norm(ax), n @ y
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    Rm = np.eye(3) + K + K @ K * ((1 - ca) / sa ** 2)
    Cr = (C - c0) @ Rm.T

    # 2. cup axis
    B = Cr[(hsv[:, 0] > 3) & (hsv[:, 0] < 25) & (hsv[:, 1] > 60) & (hsv[:, 2] < 140) & (Cr[:, 1] > 0.02)]
    for _ in range(5):
        A = np.c_[2 * B[:, 0], 2 * B[:, 2], np.ones(len(B)), B[:, 1], B[:, 1] ** 2]
        sol = np.linalg.lstsq(A, B[:, 0] ** 2 + B[:, 2] ** 2, rcond=None)[0]
        cx, cz = sol[0], sol[1]
        rr = np.hypot(B[:, 0] - cx, B[:, 2] - cz)
        res = np.abs(rr - np.poly1d(np.polyfit(B[:, 1], rr, 1))(B[:, 1]))
        B = B[res < np.percentile(res, 90)]
    cone = np.polyfit(B[:, 1], np.hypot(B[:, 0] - cx, B[:, 2] - cz), 1)

    # 3. scale from the breadboard
    rc = np.hypot(Cr[:, 0] - cx, Cr[:, 2] - cz)
    sel = ((Cr[:, 1] > 0.004) & (Cr[:, 1] < 0.06) & (rc > 0.165) & (rc < 0.42)
           & (hsv[:, 1] < 45) & (hsv[:, 2] > 190))
    Q = Cr[sel][:, [0, 2]].astype(np.float32)
    # keep the densest cluster (the board), not stray white bits (cable ties, laptop edge)
    tree = cKDTree(Q)
    groups = -np.ones(len(Q), int)
    g = 0
    for i in range(len(Q)):
        if groups[i] >= 0:
            continue
        stack = [i]
        groups[i] = g
        while stack:
            j = stack.pop()
            for k in tree.query_ball_point(Q[j], 0.02):
                if groups[k] < 0:
                    groups[k] = g
                    stack.append(k)
        g += 1
    Q = Q[groups == np.bincount(groups).argmax()]
    nb = np.array([len(x) for x in cKDTree(Q).query_ball_point(Q, 0.015)])
    (_, _), (w, h), _ = cv2.minAreaRect(Q[nb >= 6])
    L, S = max(w, h), min(w, h)
    mm = 0.5 * (BOARD_MM[0] / L + BOARD_MM[1] / S)

    # world: mm, origin on the table under the cup axis, +Y up
    Vw = ((V - c0) @ Rm.T - np.array([cx, 0, cz])) * mm
    Cw = (Cr - np.array([cx, 0, cz])) * mm
    top_mm = B[:, 1].max() * mm
    rw = np.hypot(Cw[:, 0], Cw[:, 2])
    yellow = (hsv[:, 0] > 18) & (hsv[:, 0] < 42) & (hsv[:, 1] > 80)
    keep = ~(((Cw[:, 1] > top_mm + 0.8) & (rw < CUT_R_MM)) | (yellow & (Cw[:, 1] > CUT_Y_MM) & (rw < CUT_R_MM)))
    keep &= (np.abs(Cw[:, 0]) < CROP_MM) & (np.abs(Cw[:, 2]) < CROP_MM) & (Cw[:, 1] > -5)

    # 6. unweld (v, vt) pairs -> one web vertex each
    pairs = np.stack([Fv[keep].ravel(), Ft[keep].ravel()], 1)
    uniq, inv = np.unique(pairs, axis=0, return_inverse=True)
    pos = Vw[uniq[:, 0]].astype(np.float32)
    uv = T[uniq[:, 1]].astype(np.float32)
    idx = inv.astype(np.uint32).ravel()
    blob = (np.array([len(pos), len(idx)], np.int32).tobytes() + pos.tobytes() + uv.tobytes()
            + idx.tobytes())
    with open(os.path.join(out, "rig_mesh.json"), "w") as f:   # base64: artifacts serve no .bin
        json.dump({"format": "int32 nv,ni | float32 xyz[nv] mm | float32 uv[nv] | uint32 idx[ni]",
                   "b64": base64.b64encode(blob).decode()}, f)
    cv2.imwrite(os.path.join(out, "rig_tex.jpg"), cv2.resize(tex, (2048, 2048), interpolation=cv2.INTER_AREA),
                [cv2.IMWRITE_JPEG_QUALITY, 82])
    meta = dict(units="mm", mm_per_scan_unit=round(float(mm), 2),
                board_fit_scan_units=[round(float(L), 4), round(float(S), 4)],
                board_scale_long_short=[round(BOARD_MM[0] / L, 1), round(BOARD_MM[1] / S, 1)],
                cup=dict(height_mm=round(float(B[:, 1].max() * mm), 1),
                         r_table_mm=round(float(np.polyval(cone, 0) * mm), 1),
                         r_top_mm=round(float(np.polyval(cone, B[:, 1].max()) * mm), 1)),
                vertices=int(len(pos)), triangles=int(len(idx) // 3), cut=[CUT_Y_MM, CUT_R_MM])
    json.dump(meta, open(os.path.join(out, "rig_meta.json"), "w"), indent=1)
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
