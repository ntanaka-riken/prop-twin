"""Scale the IMG_5782 scan with the paper cup measured in the IMG_5755 scan (height 91.6, base 75.6, top 49.6 mm)."""
import numpy as np, cv2
from scipy.optimize import least_squares
d = np.load("frame.npz"); Q, col = d["Q"], d["col"]
hsv = cv2.cvtColor(col.astype(np.uint8)[None], cv2.COLOR_BGR2HSV)[0].astype(float)
yellow = (hsv[:, 0] > 18) & (hsv[:, 0] < 40) & (hsv[:, 1] > 90) & (hsv[:, 2] > 90)
# cup = dark brown wall; seed its axis from the propeller (yellow) centroid in xy
c0 = np.median(Q[yellow & (Q[:, 2] > 0.3), :2], 0)
r = np.hypot(*(Q[:, :2] - c0).T)
brown = (hsv[:, 2] < 110) & (hsv[:, 1] > 40) & (r < 0.2) & (Q[:, 2] > 0.12) & (Q[:, 2] < 0.47)
P = Q[brown]
# cone: radius linear in height, axis vertical at (cx, cy)
def res(p):
    cx, cy, r0, k = p
    return np.hypot(P[:, 0] - cx, P[:, 1] - cy) - (r0 + k * P[:, 2])
s = least_squares(res, [c0[0], c0[1], 0.15, -0.1], loss="soft_l1", f_scale=0.005)
cx, cy, r0, k = s.x
# pan top under the cup: lowest dense level of points just outside the cup base
ring = (np.hypot(Q[:, 0] - cx, Q[:, 1] - cy) > r0 + 0.02) & (np.hypot(Q[:, 0] - cx, Q[:, 1] - cy) < r0 + 0.08) & (Q[:, 2] > 0.03) & (Q[:, 2] < 0.2)
zpan = np.median(Q[ring, 2])
# cup top: highest brown wall point (90th..99th percentile of z on the wall)
ztop = np.percentile(P[:, 2], 99.5)
H = ztop - zpan
rb, rt = r0 + k * zpan, r0 + k * ztop
print("cone fit: axis (%.3f, %.3f), wall points %d, rms %.4f" % (cx, cy, len(P), np.sqrt(np.mean(s.fun ** 2))))
print("pan z %.3f, cup top z %.3f -> height %.4f units; diameters base %.4f, top %.4f units" % (zpan, ztop, H, 2 * rb, 2 * rt))
sh, sb, st = 91.6 / H, 75.6 / (2 * rb), 49.6 / (2 * rt)
print("mm/unit: from height %.1f, from base %.1f, from top %.1f" % (sh, sb, st))
np.savez("scale.npz", mm_per_unit=np.array([sh, sb, st]), axis=np.array([cx, cy]), zpan=zpan, ztop=ztop)
