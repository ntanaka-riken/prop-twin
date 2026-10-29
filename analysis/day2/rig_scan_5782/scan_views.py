"""IMG_5782 rig-on-balance scan: per-vertex colour from the texture, table plane by RANSAC, views."""
import numpy as np, cv2, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
V, VT, F = [], [], []
for ln in open("rig_balance.obj"):
    if ln.startswith("v "): V.append([float(x) for x in ln.split()[1:4]])
    elif ln.startswith("vt "): VT.append([float(x) for x in ln.split()[1:3]])
    elif ln.startswith("f "): F.append([[int(p) if p else 0 for p in (t.split("/") + ["", ""])[:2]] for t in ln.split()[1:4]])
V, VT = np.array(V), np.array(VT); T = cv2.imread("Texture_diffuseColor.png"); h, w = T.shape[:2]
col = np.zeros((len(V), 3)); seen = np.zeros(len(V), bool)
for tri in F:
    for vi, ti in tri:
        if not seen[vi - 1] and ti:
            u, v = VT[ti - 1]; col[vi - 1] = T[int((1 - v) % 1 * (h - 1)), int(u % 1 * (w - 1))]; seen[vi - 1] = True
rng = np.random.default_rng(0); best = (0, None); sc = np.ptp(V, 0).max()
for _ in range(4000):
    a, b, c = V[rng.choice(len(V), 3, replace=False)]; n = np.cross(b - a, c - a); nn = np.linalg.norm(n)
    if nn < 1e-12: continue
    n /= nn; k = (np.abs((V - a) @ n) < 2e-3 * sc).sum()
    if k > best[0]: best = (k, (n, a))
n, a = best[1]
d = (V - a) @ n
if np.median(d) < 0: n = -n; d = -d          # most of the scene above the plane
ex = np.cross(n, [1, 0, 0]); ex /= np.linalg.norm(ex); ey = np.cross(n, ex)
Q = np.c_[(V - a) @ ex, (V - a) @ ey, d]
np.savez("frame.npz", Q=Q, col=col, n=n, a=a)
print("vertices", len(V), "plane inliers %.0f %%" % (100 * best[0] / len(V)), "extent", np.round(np.ptp(Q, 0), 3))
sub = np.random.default_rng(1).choice(len(Q), min(len(Q), 60000), replace=False)
fig, ax = plt.subplots(1, 3, figsize=(18, 6.5))
ax[0].scatter(Q[sub, 0], Q[sub, 1], c=col[sub][:, ::-1] / 255, s=0.6); ax[0].set_aspect("equal"); ax[0].set_title("top (true colour)")
ax[1].scatter(Q[sub, 0], Q[sub, 2], c=col[sub][:, ::-1] / 255, s=0.6); ax[1].set_aspect("equal"); ax[1].set_title("side x-z")
ax[2].scatter(Q[sub, 1], Q[sub, 2], c=col[sub][:, ::-1] / 255, s=0.6); ax[2].set_aspect("equal"); ax[2].set_title("side y-z")
plt.tight_layout(); plt.savefig("views_raw.png", dpi=70)
