#!/usr/bin/env python3
"""README 用の図: IMG_5741 の音声 FFT から回転数を読むしくみ。

  python3 analysis/readme/fig_audio_fft.py <IMG_5741.mov> media/readme/audio_fft.png

(a) スペクトログラム: 通電中だけブラシ音の倍音コムが 2-14 kHz に立ち、dcm:off で消える
(b) 全次数の線を k·f_rot を中心に重ね合わせ: 0 で鋭いピーク
(c) 倍音和 H(f0) = mean_k L(k f0): 正しい f0 で鋭いピーク
(d) 50 ms ごとの f0 → 回転数。惰性の終わりは映像の羽根追跡
"""
import json
import os
import subprocess
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal as sg

plt.rcParams["font.family"] = ["Hiragino Sans"]
plt.rcParams["font.size"] = 10
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

mov, out = sys.argv[1], sys.argv[2]
wav = os.path.join(tempfile.mkdtemp(), "a.wav")
subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@48000", "-c", "1", mov, wav], check=True)
fs, a = wavfile.read(wav)
a = a.astype(float)
meas = json.load(open(os.path.join(ROOT, "twin", "data", "IMG_5741_measured.json")))
t_on, t_off, f_ss = meas["t_on"], meas["t_off"], meas["f_ss"]


def whitened(t0, w=0.2, N=1 << 18):
    i0, n = int(round(t0 * fs)), int(round(w * fs))
    x = a[i0:i0 + n] * np.hanning(n)
    X = np.abs(np.fft.rfft(x, N)) ** 2
    f = np.fft.rfftfreq(N, 1 / fs)
    L = np.log(X + 1e-9)
    L -= np.interp(f, f[::8], sg.medfilt(L[::8], 51))
    return f, L


def hsum(f, L, f0s, lo=2000, hi=14000):
    df = f[1]
    return np.array([L[np.round(np.arange(np.ceil(lo / f0), np.floor(hi / f0)) * f0 / df).astype(int)].mean()
                     for f0 in f0s])


fig = plt.figure(figsize=(12, 7.2), dpi=130)
gs = fig.add_gridspec(2, 3, height_ratios=[1.15, 1], hspace=0.42, wspace=0.28)

# (a) spectrogram
ax = fig.add_subplot(gs[0, :])
f, t, S = sg.spectrogram(a, fs, nperseg=4096, noverlap=3584, window="hann")
sel = f <= 15000
Sd = 10 * np.log10(S[sel] + 1e-12)
Sd -= np.median(Sd, axis=1, keepdims=True)                  # remove stationary room noise per bin
ax.pcolormesh(t, f[sel] / 1000, Sd, shading="auto", cmap="magma", vmin=-3, vmax=18, rasterized=True)
ax.set_xlim(1.5, 7.5); ax.set_ylabel("周波数 [kHz]"); ax.set_xlabel("動画の時刻 [s]")
for x, s in ((t_on, "dcm:speed 255"), (t_off, "dcm:off")):
    ax.axvline(x, color="w", lw=0.8, ls="--")
    ax.text(x + 0.04, 14.2, s, color="w", fontsize=9, va="top")
ax.text(t_off + 0.04, 12.6, "電流が止まるとコムが消える\n→ 惰性停止の開始時刻", color="w", fontsize=8.5, va="top")
ax.set_title("(a) iPhone の録音のスペクトログラム:通電中だけブラシ音の倍音コム(2–14 kHz)が立つ", loc="left", fontsize=10.5)

# (b) all comb lines folded onto one: mean_k L(k f0 + d) for d in [-f0/2, f0/2]
tm = 0.5 * (t_on + t_off)
fw, L = whitened(tm)
ax = fig.add_subplot(gs[1, 0])
f0s = np.arange(35, 75, 0.02)
h = hsum(fw, L, f0s)
j = np.argmax(h)
f0 = f0s[j]; df = fw[1]   # this window's own f_rot (the speed drifts 51.0-51.3 Hz)
d = np.linspace(-f0 / 2, f0 / 2, 301)
ks = np.arange(np.ceil(2000 / f0), np.floor(14000 / f0))
prof = np.array([L[np.round((ks * f0 + dd) / df).astype(int)].mean() for dd in d])
ax.plot(d, prof, color="#d95f02", lw=1.2)
ax.axvline(0, color="#999", lw=0.6, ls="--")
ax.set_xlabel("k·f_rot からのずれ [Hz]"); ax.set_ylabel("白色化したパワー(全次数の平均)")
ax.set_title(f"(b) 定常中(0.2 s 窓)の {len(ks)} 本の線(k = {ks[0]:.0f}–{ks[-1]:.0f})を\nk·{f0:.2f} Hz を中心に重ね合わせ", loc="left", fontsize=10)

# (c) harmonic sum
ax = fig.add_subplot(gs[1, 1])
ax.plot(f0s, h, lw=0.9, color="#1b9e77")
ax.annotate(f"{f0s[j]:.2f} Hz\n= {f0s[j] * 60:.0f} rpm", (f0s[j], h[j]), (f0s[j] + 4, h[j] * 0.85),
            arrowprops=dict(arrowstyle="->", lw=0.8), fontsize=9)
ax.set_xlabel("候補の回転周波数 f₀ [Hz]"); ax.set_ylabel("倍音和 H(f₀)")
ax.set_title("(c) 倍音和 H(f₀) = k について P(k·f₀) を平均\n正しい f₀ だけ全部の線に乗る", loc="left", fontsize=10)

# (d) rpm track
ax = fig.add_subplot(gs[1, 2])
ao = np.array(meas["audio_omega"]); vo = np.array(meas["video_omega"])
ax.plot(ao[:, 0], ao[:, 1] * 60 / (2 * np.pi), ".", ms=3, color="#d95f02", label="音声(倍音和、50 ms ごと)")
ax.plot(vo[:, 0], vo[:, 1] * 60 / (2 * np.pi), "o", ms=3, color="#7570b3", label="映像(羽根の追跡)")
ax.axvline(t_off, color="#999", lw=0.7, ls="--")
ax.set_xlim(t_on - 0.2, meas["t_stop"] + 0.4); ax.set_ylim(0, 3400)
ax.set_xlabel("動画の時刻 [s]"); ax.set_ylabel("回転数 [rpm]")
ax.legend(fontsize=8, loc="lower left", frameon=False)
ax.set_title("(d) 取り出した回転数\n(分解能 ≈ 0.02 Hz)", loc="left", fontsize=10)

fig.savefig(out, bbox_inches="tight")
print("wrote", out)
