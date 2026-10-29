"""Write the IMG_5782 scan levelled (table = z 0, z up), scaled to mm (paper cup), origin on the cup axis."""
import json, numpy as np, cv2, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
fr = np.load("frame.npz"); sc = np.load("scale.npz")
n, a = fr["n"], fr["a"]; s = float(np.mean(sc["mm_per_unit"])); cx, cy = sc["axis"]
ex = np.cross(n, [1, 0, 0]); ex /= np.linalg.norm(ex); ey = np.cross(n, ex)
out = []
for ln in open("rig_balance.obj"):
    if ln.startswith("v "):
        p = np.array([float(x) for x in ln.split()[1:4]]) - a
        x, y, z = (p @ ex - cx) * s, (p @ ey - cy) * s, (p @ n) * s
        out.append("v %.3f %.3f %.3f\n" % (x, z, -y))          # three.js style: y up
    elif ln.startswith("vn "):
        q = np.array([float(x) for x in ln.split()[1:4]])
        out.append("vn %.5f %.5f %.5f\n" % (q @ ex, q @ n, -(q @ ey)))
    elif ln.startswith("mtllib"):
        out.append("mtllib rig_balance_mm.mtl\n")
    else:
        out.append(ln)
open("rig_balance_mm.obj", "w").writelines(out)
open("rig_balance_mm.mtl", "w").write(open("rig_balance.mtl").read())
Q, col = fr["Q"], fr["col"]
X = np.c_[(Q[:, 0] - cx) * s, (Q[:, 1] - cy) * s, Q[:, 2] * s]
hsv = cv2.cvtColor(col.astype(np.uint8)[None], cv2.COLOR_BGR2HSV)[0].astype(float)
yel = (hsv[:, 0] > 18) & (hsv[:, 0] < 40) & (hsv[:, 1] > 90) & (hsv[:, 2] > 90) & (X[:, 2] > 100)
ry = np.hypot(X[yel, 0], X[yel, 1])
meta = dict(source="IMG_5782.MOV, 228 of 1076 frames, RealityKit Object Capture full", units="mm",
            mm_per_scan_unit=round(s, 1), scale_checks=dict(cup_height=round(float(sc["mm_per_unit"][0]), 1),
            cup_base=round(float(sc["mm_per_unit"][1]), 1), cup_top=round(float(sc["mm_per_unit"][2]), 1)),
            scale_note="paper cup from the IMG_5755 scan: height 91.6, base 75.6, top 49.6 mm",
            balance_pan_height_mm=round(float(sc["zpan"]) * s, 1), cup_top_height_mm=round(float(sc["ztop"]) * s, 1),
            propeller=dict(diameter_mm_p99=round(2 * float(np.percentile(ry, 99)), 1), top_height_mm=round(float(np.percentile(X[yel, 2], 99)), 1),
                           height_above_cup_top_mm=round(float(np.percentile(X[yel, 2], 50)) - float(sc["ztop"]) * s, 1)),
            frame="origin on the cup axis at table level; x/z horizontal, y up (OBJ written y-up)")
json.dump(meta, open("rig_balance_meta.json", "w"), indent=1)
print(json.dumps(meta, indent=1))
sub = np.random.default_rng(1).choice(len(X), min(len(X), 60000), replace=False)
fig, ax = plt.subplots(1, 2, figsize=(15, 6.5))
ax[0].scatter(X[sub, 0], X[sub, 1], c=col[sub][:, ::-1] / 255, s=0.6); ax[0].set_aspect("equal"); ax[0].set_title("IMG_5782 scan, top (mm)")
ax[1].scatter(X[sub, 0], X[sub, 2], c=col[sub][:, ::-1] / 255, s=0.6); ax[1].set_aspect("equal"); ax[1].set_title("side (mm)"); ax[1].set_ylim(-60, 220)
for a_ in ax: a_.grid(alpha=.3)
plt.tight_layout(); plt.savefig("rig_balance_views_mm.png", dpi=75)
