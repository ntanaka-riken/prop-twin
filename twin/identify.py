#!/usr/bin/env python3
"""identify.py — extract omega(t) from an iPhone video of the rig and fit the twin's parameters.

Two independent sensors are pulled out of one .mov:
  * audio  : the brushes make a harmonic comb (lines at k * f_rot, k ~ 40..270, i.e. 2-14 kHz)
             while current flows. A harmonic-sum search over f0 gives f_rot every 50 ms with
             ~0.02 Hz resolution. The comb vanishes the instant the bridge coasts (i = 0), which
             also time-stamps the dcm:off edge.
  * video  : the yellow propeller is segmented in HSV, the disc ellipse is fitted (perspective
             unwarp), and the polar blade profile is cross-correlated frame-to-frame. With 3 blades
             at 30 fps the angle step is unambiguous below 60 deg/frame (~5 rev/s), i.e. the end of
             the coast-down. The last moving frame time-stamps the stop.

Fit (coast-down, i = 0):  J dw/dt = -Tc - c w^2  ->  alpha = Tc/J from the low-speed deceleration,
beta = c/J from the total coast time. With priors for J and K (see params.json) the steady speed
at 100 % duty then fixes R, and the README's breakaway duty (45-50 %) fixes Ts.

Requires: numpy scipy opencv-python-headless; audio is decoded with macOS `afconvert`.

Usage:
  python3 twin/identify.py IMG_5741.mov                  # print measurements and fit
  python3 twin/identify.py IMG_5741.mov --write          # also update data/*.json and params.json
"""
import argparse
import json
import math
import os
import subprocess
import tempfile

import cv2
import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal as sg
from scipy.optimize import brentq

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- audio
def load_audio(mov):
    wav = os.path.join(tempfile.mkdtemp(), "a.wav")
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@48000", "-c", "1", mov, wav],
                   check=True)
    fs, a = wavfile.read(wav)
    return fs, a.astype(float)


def harmonic_sum(a, fs, t0, w, f0s, lo=2000, hi=14000):
    i0, n = int(round(t0 * fs)), int(round(w * fs))
    x = a[i0:i0 + n] * np.hanning(n)
    N = 1 << 18
    X = np.abs(np.fft.rfft(x, N)) ** 2
    f = np.fft.rfftfreq(N, 1 / fs)
    L = np.log(X + 1e-9)
    L -= np.interp(f, f[::8], sg.medfilt(L[::8], 51))      # whiten: keep only the comb
    df = f[1]
    out = np.empty(len(f0s))
    for j, f0 in enumerate(f0s):
        k = np.arange(np.ceil(lo / f0), np.floor(hi / f0))
        out[j] = L[np.round(k * f0 / df).astype(int)].mean()
    return out


def audio_track(a, fs, t_from, t_to, z_min=6.0, win=0.2, hop=0.05):
    f0s = np.arange(35, 75, 0.02)
    track = []
    for t0 in np.arange(t_from, t_to - win, hop):
        h = harmonic_sum(a, fs, t0, win, f0s)
        j = np.argmax(h)
        z = (h[j] - np.median(h)) / h.std()
        track.append((t0 + win / 2, f0s[j], z))
    good = [(t, f) for t, f, z in track if z >= z_min]
    return track, good



# ---------------------------------------------------------------- video
def yellow(f):
    h = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    return ((h[..., 0] > 18) & (h[..., 0] < 42) & (h[..., 1] > 60) & (h[..., 2] > 120)).astype(np.uint8)


def video_track(mov, spin_frames, search_frames, xlim=(300, 1150), ylim=700):
    v = cv2.VideoCapture(mov)
    fps = v.get(cv2.CAP_PROP_FPS)

    def frame(i):
        v.set(cv2.CAP_PROP_POS_FRAMES, i)
        return v.read()[1]

    acc = None
    for i in range(*spin_frames):                 # blurred disc while spinning = full ellipse
        y = yellow(frame(i)).astype(np.float32)
        acc = y if acc is None else acc + y
    m = (acc > 0.27 * (spin_frames[1] - spin_frames[0])).astype(np.uint8)
    m[:, :xlim[0]] = 0; m[:, xlim[1]:] = 0; m[ylim:, :] = 0
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    (cx, cy), (MA, ma), ang = cv2.fitEllipse(max(cs, key=cv2.contourArea))
    th = math.radians(ang)
    angs = np.deg2rad(np.arange(0, 360, 1.0))
    rs = np.linspace(0.45, 0.95, 20)

    def profile(f):
        y = yellow(f).astype(np.float32)
        prof = np.empty(len(angs))
        for j, p in enumerate(angs):
            u, w = rs * np.cos(p), rs * np.sin(p)
            X = cx + MA / 2 * u * np.cos(th) - ma / 2 * w * np.sin(th)
            Y = cy + MA / 2 * u * np.sin(th) + ma / 2 * w * np.cos(th)
            prof[j] = y[np.clip(Y.astype(int), 0, y.shape[0] - 1),
                        np.clip(X.astype(int), 0, y.shape[1] - 1)].mean()
        return prof

    # onset: first frame whose saturated-yellow area inside the disc box drops (blur starts)
    x0, x1 = int(cx - MA / 2), int(cx + MA / 2)
    y0, y1 = int(cy - ma / 2), int(cy + ma / 2)
    frac = []
    for i in range(spin_frames[0]):
        h = cv2.cvtColor(frame(i)[max(y0, 0):y1, max(x0, 0):x1], cv2.COLOR_BGR2HSV)
        frac.append(((h[..., 1] > 150) & (h[..., 0] > 20) & (h[..., 0] < 40)).mean())
    frac = np.array(frac)
    mid = (np.median(frac[:10]) + frac[-5:].mean()) / 2
    onset = int(np.flatnonzero(frac < mid)[0])

    steps, prev = [], None
    for i in range(*search_frames):
        p = profile(frame(i))
        contrast = p.std()
        p = p - p.mean()
        if prev is not None:
            cc = [np.dot(np.roll(prev, k), p) for k in range(-60, 60)]
            steps.append((i, np.argmax(cc) - 60, contrast))
        prev = p
    # blades are "sharp" once contrast is near its at-rest value; keep those steps only
    c_rest = steps[-1][2]
    sharp = [(i, d) for i, d, c in steps if c > 0.75 * c_rest]
    moving = [(i, d) for i, d in sharp if d != 0]
    stop_frame = moving[-1][0] + 0.5 if moving else None
    # one direction of rotation: take the sign of the last (slowest, unaliased) steps
    sgn = np.sign(sum(d for _, d in moving[-3:])) if moving else 1
    omega = [((i - 0.5) / fps, abs(math.radians(d) * fps)) for i, d in moving if np.sign(d) == sgn]
    return dict(fps=fps, ellipse=[cx, cy, MA, ma, ang], steps=steps, onset_t=(onset - 0.5) / fps,
                stop_t=stop_frame / fps if stop_frame else None, omega=omega)


# ---------------------------------------------------------------- fit
def fit(meas, priors):
    w0 = 2 * math.pi * meas["f_ss"]
    T = meas["t_stop"] - meas["t_off"]
    vo = sorted(meas["video_omega"])
    if len(vo) >= 2:      # low-speed (friction-dominated) deceleration
        alpha = (vo[0][1] - vo[-1][1]) / (vo[-1][0] - vo[0][0])
    else:
        alpha = priors["alpha_default"]
    beta = brentq(lambda b: math.atan(w0 * math.sqrt(b / alpha)) / math.sqrt(alpha * b) - T,
                  1e-7, 10.0)
    J, K = priors["J"], priors["K"]
    Vs, V0, rd = priors["Vs"], priors["V0"], priors["rd"]
    Tc, c = alpha * J, beta * J
    i_ss = (Tc + c * w0 ** 2) / K
    R = (Vs - V0 - K * w0) / i_ss - rd
    d_b = priors["d_breakaway"]
    i_b = d_b * (Vs - V0) / (R + d_b * rd)
    Ts = K * i_b
    return dict(alpha=alpha, beta=beta, coast_T=T, w_ss=w0, Tc=Tc, c=c, R=R, i_ss=i_ss, Ts=Ts,
                i_breakaway=i_b, tau_mech=J / (K * K / R + 2 * c * w0))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mov")
    ap.add_argument("--audio-window", nargs=2, type=float, default=(2.7, 5.6))
    ap.add_argument("--spin-frames", nargs=2, type=int, default=(100, 130))
    ap.add_argument("--search-frames", nargs=2, type=int, default=(150, 200))
    ap.add_argument("--on-seconds", type=float, default=2.0,
                    help="how long the bridge was driven (from the serial command log)")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    fs, a = load_audio(args.mov)
    track, good = audio_track(a, fs, *args.audio_window)
    t_on, t_off = good[0][0], good[-1][0]
    f_ss = float(np.mean([f for t, f in good if t > t_off - 0.5]))
    vid = video_track(args.mov, args.spin_frames, args.search_frames)
    # bridge on = first blurred frame; bridge off = on + commanded duration. (A band-energy
    # edge is no good for "off": the coasting propeller keeps hissing in the same band.)
    t_on_edge = vid["onset_t"]
    t_off_edge = t_on_edge + args.on_seconds
    print("bridge on %.3f s (video onset) .. off %.3f s (+%.2f s commanded); "
          "comb lock ends %.2f s" % (t_on_edge, t_off_edge, args.on_seconds, t_off))
    meas = dict(source=os.path.basename(args.mov), f_ss=f_ss, t_on=t_on_edge, t_off=t_off_edge,
                t_stop=vid["stop_t"], audio_omega=[(t, 2 * math.pi * f) for t, f in good],
                video_omega=vid["omega"], ellipse=vid["ellipse"])
    print("audio comb locked %.2f..%.2f s, f_ss=%.2f Hz (%.0f rpm)" % (t_on, t_off, f_ss, f_ss * 60))
    print("coast start (comb end) %.2f s, stop (video) %.3f s" % (t_off_edge, vid["stop_t"]))
    print("video low-speed omega:", [(round(t, 3), round(w, 1)) for t, w in vid["omega"]])

    pp = os.path.join(HERE, "params.json")
    pj = json.load(open(pp))
    priors = {k: v["value"] for k, v in pj["params"].items()}
    priors.update(pj["identification_priors"])
    r = fit(meas, priors)
    for k, v in r.items():
        print("  %-12s %.4g" % (k, v))

    if args.write:
        os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
        with open(os.path.join(HERE, "data", "IMG_5741_measured.json"), "w") as f:
            json.dump(meas, f, indent=1)
        for k in ("R", "Tc", "c", "Ts"):
            pj["params"][k]["value"] = float("%.4g" % r[k])
        pj["fit"] = {k: float("%.4g" % v) for k, v in r.items()}
        with open(pp, "w") as f:
            json.dump(pj, f, indent=1, ensure_ascii=False)
        print("wrote data/IMG_5741_measured.json and params.json")


if __name__ == "__main__":
    main()
