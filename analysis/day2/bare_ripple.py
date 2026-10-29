#!/usr/bin/env python3
"""bare_ripple.py — propeller-off full speed from the ADC commutator ripple (3 ripples per revolution).

Reads twin/data/adc/bare_coast_{1,2}.json (tools/bare_speed_adc.py: adc:cap 200 4000 500 dcm:off, 5 kHz,
drive for the first 0.1 s, then coast) and prints the strongest ripple lines in the drive part and in the
first 40 ms of the coast. Result: 220.8 Hz / 3 = 73.6 Hz, which settled that the audio comb (71.7 Hz,
IMG_5780) was the fundamental and not twice 35.85 Hz, and that the tape flag of IMG_5759 cost ~12 Hz.

Usage:  python3 analysis/day2/bare_ripple.py
"""
import json
import os

import numpy as np
import scipy.signal as sg

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
FS = 5000.0
GAIN = 6.0 * 12280 / 12000          # raw/1023 -> TOUT V -> terminal A (x6) -> back-EMF (270 ohm drop)

for k in (1, 2):
    a = np.array(json.load(open(os.path.join(ROOT, "twin/data/adc/bare_coast_%d.json" % k)))["data"], float)
    v = (a - np.median(a[-400:])) / 1023 * GAIN
    for lab, x in (("drive", v[:480]), ("coast 0-40 ms", v[505:705])):
        y = sg.detrend(x) * np.hanning(len(x))
        f = np.fft.rfftfreq(65536, 1 / FS)
        X = np.abs(np.fft.rfft(y, 65536))
        m = (f > 60) & (f < 400)
        top = []
        for j in np.argsort(X * m)[::-1]:
            if all(abs(f[j] - p) > 8 for p, _ in top):
                top.append((f[j], X[j] / X[m].max()))
            if len(top) == 4:
                break
        print("run %d %-13s peaks: %s  mean %.2f V" % (k, lab, " ".join("%.1f Hz(%.2f)" % p for p in top), x.mean()))
