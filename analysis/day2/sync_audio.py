#!/usr/bin/env python3
"""sync_audio.py — align a phone video with the host command log, then read the rotation rate per phase.

The brushes make broadband noise (1.5-12 kHz) only while current flows, so the log-energy envelope of
the soundtrack is a 0/1 "driven" signal. It is correlated with the driven intervals from the host log
(tools/run_sequence.py -> twin/data/*_hostlog.json) to find  video_time = host_time + offset.
Then the brush harmonic comb (twin/identify.py) gives the rotation rate inside each driven phase.
The Mac's Tink sound was meant for this too, but it is buried under the motor noise.

Used for IMG_5779 (offset +2.84 s), IMG_5780 (+2.10 s), IMG_5785 (+6.74 s).

Usage:
  python3 analysis/day2/sync_audio.py VIDEO.MOV twin/data/reverse_hostlog.json [--search -20 30]
Needs numpy scipy; the video soundtrack is extracted with macOS afconvert.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import wavfile
from scipy.signal import stft

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "twin"))
import identify as idf  # noqa: E402  (harmonic_sum / audio_track)


def soundtrack(video):
    wav = os.path.join(tempfile.mkdtemp(), "a.wav")
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@48000", "-c", "1", video, wav], check=True)
    fs, a = wavfile.read(wav)
    return fs, a.astype(float)


def driven_envelope(a, fs):
    f, t, Z = stft(a, fs, nperseg=2048, noverlap=1536)
    e = np.log(np.abs(Z)[(f > 1500) & (f < 12000)].sum(0) + 1)
    return t, (e - np.percentile(e, 5)) / (np.percentile(e, 95) - np.percentile(e, 5))


def driven_model(t, tx, off):
    m = np.zeros_like(t)
    for (t0, c0), (t1, _) in zip(tx, tx[1:] + [(1e9, "")]):
        if c0.startswith("dcm:speed"):
            m[(t >= t0 + off) & (t < t1 + off)] = 1
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video")
    ap.add_argument("hostlog")
    ap.add_argument("--search", nargs=2, type=float, default=(-20.0, 30.0), help="offset range to try (s)")
    ap.add_argument("--settle", type=float, default=1.5, help="skip this long after each command (s)")
    args = ap.parse_args()
    fs, a = soundtrack(args.video)
    log = json.load(open(args.hostlog))
    tx = [(t, c) for t, k, c in log if k == "tx" and c.startswith("dcm:")]
    t, e = driven_envelope(a, fs)
    corr, off = max((np.corrcoef(driven_model(t, tx, o), e)[0, 1], o)
                    for o in np.arange(args.search[0], args.search[1], 0.02)
                    if driven_model(t, tx, o).std() > 0)
    print("sync: corr %.3f, video = host %+.2f s" % (corr, off))
    for (t0, c0), (t1, _) in zip(tx, tx[1:]):
        if not c0.startswith("dcm:speed"):
            continue
        tr, good = idf.audio_track(a, fs, t0 + off + args.settle, t1 + off - 0.2, z_min=5.0, win=0.5, hop=0.25)
        fr = np.array([g[1] for g in good]) if good else np.array([np.nan])
        print("%-16s host %6.2f  comb locked %2d/%2d  f = %.2f +- %.2f Hz (%4.0f rpm)" % (
            c0, t0, len(good), len(tr), np.median(fr), np.std(fr), np.median(fr) * 60))


if __name__ == "__main__":
    main()
