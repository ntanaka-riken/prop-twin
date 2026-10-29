"""Pitch / camber of the yellow propeller from an Object Capture OBJ (prop lying on a table, 10-yen coin beside it).

level on the table plane -> yellow vertices = prop -> hub axis = table normal through the prop centroid ->
cut each blade with cylinders r = const, unwrap to (s = r*phi, z), fit a line (pitch) and a parabola (camber).
"""
import sys, numpy as np, cv2

def load_obj(path):
    V, VT, F = [], [], []
    for ln in open(path):
        if ln.startswith('v '): V.append([float(x) for x in ln.split()[1:4]])
        elif ln.startswith('vt '): VT.append([float(x) for x in ln.split()[1:3]])
        elif ln.startswith('f '):
            F.append([[int(p) if p else 0 for p in (t.split('/') + ['', ''])[:2]] for t in ln.split()[1:4]])
    return np.array(V), np.array(VT), np.array(F)

obj, tex = sys.argv[1], sys.argv[2]
V, VT, F = load_obj(obj)
T = cv2.imread(tex)
# per-vertex colour from the texture (first uv that references the vertex)
col = np.zeros((len(V), 3)); seen = np.zeros(len(V), bool)
for tri in F:
    for vi, ti in tri:
        if not seen[vi - 1] and ti:
            u, v = VT[ti - 1]; h, w = T.shape[:2]
            col[vi - 1] = T[int((1 - v) % 1 * (h - 1)), int(u % 1 * (w - 1))]; seen[vi - 1] = True
hsv = cv2.cvtColor(col.astype(np.uint8)[None], cv2.COLOR_BGR2HSV)[0].astype(float)
yellow = (hsv[:, 0] > 18) & (hsv[:, 0] < 40) & (hsv[:, 1] > 90) & (hsv[:, 2] > 90)
print('vertices', len(V), 'yellow', yellow.sum())

# table plane by RANSAC on non-yellow vertices
rng = np.random.default_rng(0); P = V[~yellow]; best = (0, None)
scale0 = np.ptp(V, axis=0).max()
for _ in range(3000):
    a, b, c = P[rng.choice(len(P), 3, replace=False)]
    n = np.cross(b - a, c - a); nn = np.linalg.norm(n)
    if nn < 1e-12: continue
    n /= nn; d = np.abs((P - a) @ n); k = (d < 2e-3 * scale0).sum()
    if k > best[0]: best = (k, (n, a))
n, a = best[1]
if (V[yellow] - a).mean(0) @ n < 0: n = -n                 # normal points up toward the prop
ex = np.cross(n, [1, 0, 0]); ex = ex if np.linalg.norm(ex) > .1 else np.cross(n, [0, 1, 0]); ex /= np.linalg.norm(ex); ey = np.cross(n, ex)
Q = np.c_[(V - a) @ ex, (V - a) @ ey, (V - a) @ n]           # table frame, z up
Y = Q[yellow & (Q[:, 2] > 0.3e-3 * scale0)]

# hub centre: densest/highest region; use centroid of the top 10 % (hub dome) in xy
top = Y[Y[:, 2] > np.percentile(Y[:, 2], 90)]
cx, cy = top[:, 0].mean(), top[:, 1].mean()
Y[:, 0] -= cx; Y[:, 1] -= cy
r = np.hypot(Y[:, 0], Y[:, 1]); phi = np.arctan2(Y[:, 1], Y[:, 0])
R = np.percentile(r, 99.8)
hubH = Y[:, 2].max()
print('R = %.4g units, hub top z = %.4g units (hub/R height %.3f)' % (R, hubH, hubH / R))

# coin scale check: non-yellow points 0.5-3 mm above table, away from the prop
Z = Q[~yellow]; Z = Z[(Z[:, 2] > 0.2 * hubH / 12) & (Z[:, 2] < 2.5 * hubH / 12)]
Z = Z[np.hypot(Z[:, 0] - cx, Z[:, 1] - cy) > 1.15 * R]
if len(Z) > 50:
    cz = np.median(Z[:, :2], 0); rc = np.hypot(*(Z[:, :2] - cz).T); rc = rc[rc < 3 * np.median(rc)]
    Dc = 2 * np.percentile(rc, 97)
    print('coin diameter %.4g units -> %.2f mm/unit -> prop D = %.1f mm, hub height %.1f mm' % (Dc, 23.5 / Dc, 2 * R * 23.5 / Dc, hubH * 23.5 / Dc))

# blade sectors from the angular histogram at mid-span
mid = (r > 0.55 * R) & (r < 0.8 * R)
h, e = np.histogram(phi[mid], 180, (-np.pi, np.pi)); hs = np.convolve(np.r_[h, h, h], np.ones(9) / 9, 'same')[180:360]
gaps = np.argsort(hs)[:1]
start = e[gaps[0]]
print('\n r/R  blade  pitch(deg)  camber f/c  chord/R  z_mid/R  n')
rows = []
for x in np.arange(0.40, 0.96, 0.05):
    sh = (r > (x - 0.02) * R) & (r < (x + 0.02) * R)
    ph = (phi[sh] - start) % (2 * np.pi); z = Y[sh, 2]
    for bl in range(3):
        m = (ph >= bl * 2 * np.pi / 3) & (ph < (bl + 1) * 2 * np.pi / 3)
        if m.sum() < 30: continue
        s = ph[m] * x * R; zz = z[m]
        # keep the upper surface only (thin sheet: per s-bin max z)
        bins = np.linspace(s.min(), s.max(), 25); idx = np.digitize(s, bins)
        S_, Z_ = [], []
        for k in np.unique(idx):
            q = idx == k
            if q.sum() >= 2: S_.append(s[q].mean()); Z_.append(zz[q].max())
        S_, Z_ = np.array(S_), np.array(Z_)
        if len(S_) < 6: continue
        p1 = np.polyfit(S_, Z_, 1); p2 = np.polyfit(S_ - S_.mean(), Z_, 2)
        c = np.hypot(np.ptp(S_), np.ptp(Z_))
        th = np.degrees(np.arctan(abs(p1[0])))
        f = abs(p2[0]) * (c / 2) ** 2 / c * np.cos(np.radians(th)) ** 2   # sagitta / chord
        rows.append((x, bl, th, f, c / R)); print(' %.2f   %d     %5.1f      %5.3f     %.3f   %.3f  %d' % (x, bl, th, f, c / R, Z_.mean() / R, m.sum()))
rows = np.array(rows)
np.save(obj.replace('.obj', '_pitch.npy'), rows)
for x in np.unique(rows[:, 0]):
    q = rows[rows[:, 0] == x]; print('r/R %.2f  pitch %.1f ± %.1f deg  f/c %.3f' % (x, q[:, 2].mean(), q[:, 2].std(), q[:, 3].mean()))
