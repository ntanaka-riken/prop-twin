#!/usr/bin/env python3
"""adc_backemf.py — K from the ESPr ADC: back-EMF (mean voltage) vs speed (commutator ripple).

Wiring: terminal A -> 10k -> TOUT -> 2k -> GND, terminal B -> 270 -> GND (see WIRING.md).
Capture with the firmware's adc:cap, e.g.  python3 tools/adc_capture.py "dcm:speed 255" 2
"adc:cap 200 4000 500 dcm:off" twin/data/adc/coast_100pct_1.json   (5 kHz, dcm:off at 0.1 s)

While coasting the L293D outputs are Hi-Z, so terminal A = back-EMF K*w (less 2.2 % in the 270
ohm reference). The 3-segment commutator puts 3 ripple cycles per revolution on it, so the ripple
fundamental / 3 is the rotation rate. The fundamental is tracked downward from the value in the
drive section (search 80-102 % of the previous estimate) to avoid octave slips.

Usage:  python3 twin/adc_backemf.py twin/data/adc/coast_100pct_*.json
"""
import json
import sys

import numpy as np
import scipy.signal as sg

FS = 5000.0
GAIN = 6.0 * 12280 / 12000      # raw/1023 -> TOUT V -> terminal A (x6) -> back-EMF (270 ohm drop)


def spectrum(x):
    y = sg.detrend(x) * np.hanning(len(x))
    return np.fft.rfftfreq(32768, 1 / FS), np.abs(np.fft.rfft(y, 32768))


def hsum(f, X, q, k=4):
    return np.log(X[np.round(np.arange(1, k + 1) * q / f[1]).astype(int)] + 1e-12).mean()


def track(path, t_cmd=0.1):
    a = np.array(json.load(open(path))["data"], float)
    v = (a - np.median(a[-400:])) / 1023 * GAIN
    f, X = spectrum(v[:int((t_cmd - 0.004) * FS)])
    cand = np.arange(150, 230, 0.1)
    prev = cand[np.argmax([hsum(f, X, q, 6) for q in cand])]
    rows = []
    for tc in np.arange(0.006, 0.40, 0.004):
        n = int(max(0.016, min(0.06, 4.0 / prev)) * FS)
        i0 = int((tc + t_cmd) * FS) - n // 2
        x = v[i0:i0 + n]
        if x.mean() < 0.08 or prev < 12:
            break
        f, X = spectrum(x)
        cand = np.arange(0.80 * prev, 1.02 * prev, 0.05)
        prev = cand[int(np.argmax([hsum(f, X, q) for q in cand]))]
        rows.append((tc, 2 * np.pi * prev / 3, x.mean()))
    return np.array(rows)


def main():
    W, E = [], []
    for p in sys.argv[1:]:
        r = track(p)
        # keep the section before the first octave slip: emf/w must stay near its early value
        ratio = r[:, 2] / r[:, 1]
        ref = np.median(ratio[(r[:, 0] > 0.01) & (r[:, 0] < 0.06)])
        ok = (r[:, 0] > 0.01) & (np.abs(ratio / ref - 1) < 0.08)
        first_bad = np.flatnonzero(~ok & (r[:, 0] > 0.01))
        if len(first_bad):
            ok &= r[:, 0] < r[first_bad[0], 0]
        print("%s: %d clean points, w %.0f-%.0f rad/s" % (p, ok.sum(), r[ok, 1].min(), r[ok, 1].max()))
        if ok.sum() < 10:
            print("   skipped: tracking slipped too early")
            continue
        W += list(r[ok, 1]); E += list(r[ok, 2])
    W, E = np.array(W), np.array(E)
    K = (W @ E) / (W @ W)
    k1, b = np.polyfit(W, E, 1)
    print("K = %.4e V*s/rad (through origin), free line K=%.4e b=%+.3f V, rms %.3f V" % (
        K, k1, b, (E - K * W).std()))


if __name__ == "__main__":
    main()
