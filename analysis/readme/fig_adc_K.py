#!/usr/bin/env python3
"""README 用の図: ESPr の ADC で逆起電力定数 K を直接測る(twin/adc_backemf.py と同じ処理)。

  python3 analysis/readme/fig_adc_K.py media/readme/adc_K.png

(a) dcm:off 直後の端子 A の電圧(5 kHz):PWM 駆動 → Hi-Z で逆起電力 Kω だけが残り、惰性で下がる
(b) 拡大:整流子 3 セグメントで 1 回転に 3 周期のリップル → 回転数
(c) 逆起電力(区間平均)vs 角速度(リップル基本波 / 3)→ 原点を通る直線の傾きが K
"""
import glob
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "twin"))
import adc_backemf as ab  # noqa: E402

plt.rcParams["font.family"] = ["Hiragino Sans"]
plt.rcParams["font.size"] = 10
out = sys.argv[1]
files = sorted(glob.glob(os.path.join(ROOT, "twin", "data", "adc", "coast_100pct_*.json")))

EX = files[1]                                              # run 1 slips its ripple tracking early (see panel c)
a = np.array(json.load(open(EX))["data"], float)
v = (a - np.median(a[-400:])) / 1023 * ab.GAIN
t = np.arange(len(v)) / ab.FS - 0.1                      # 0 = dcm:off

fig, axs = plt.subplots(1, 3, figsize=(13, 3.7), dpi=130, gridspec_kw={"width_ratios": [1.3, 1, 1], "wspace": 0.3})
ax = axs[0]
ax.plot(t * 1000, v, lw=0.5, color="#333")
ax.axvline(0, color="#d95f02", lw=0.8, ls="--"); ax.text(4, v.max() * 0.95, "dcm:off(出力 Hi-Z)", color="#d95f02", fontsize=9)
ax.set_xlim(-40, 400); ax.set_xlabel("dcm:off からの時刻 [ms]"); ax.set_ylabel("端子 A の電圧 [V]")
ax.set_title("(a) 惰性中の端子電圧 = 逆起電力 K ω\n(ADC 5 kHz、分圧 1/6 を戻した値)", loc="left", fontsize=10)

ax = axs[1]
m = (t > 0.010) & (t < 0.040)
ax.plot(t[m] * 1000, v[m], ".-", ms=2.5, lw=0.6, color="#333")
r = ab.track(EX)
w0 = np.interp(0.025, r[:, 0], r[:, 1]); fr = w0 / (2 * np.pi)
ax.set_xlabel("dcm:off からの時刻 [ms]"); ax.set_ylabel("電圧 [V]")
ax.set_title(f"(b) 拡大:整流子リップル 1 回転に 3 周期\n(25 ms 後で ≈ {3 * fr:.0f} Hz → {fr:.1f} 回転/s)", loc="left", fontsize=10)

ax = axs[2]
W, E = [], []
cols = ["#1b9e77", "#7570b3", "#e7298a"]
for k, p in enumerate(files):
    r = ab.track(p)
    ratio = r[:, 2] / r[:, 1]
    ref = np.median(ratio[(r[:, 0] > 0.01) & (r[:, 0] < 0.06)])
    ok = (r[:, 0] > 0.01) & (np.abs(ratio / ref - 1) < 0.08)
    bad = np.flatnonzero(~ok & (r[:, 0] > 0.01))
    if len(bad):
        ok &= r[:, 0] < r[bad[0], 0]
    if ok.sum() < 10:
        continue
    ax.plot(r[ok, 1], r[ok, 2], "o", ms=3, mfc="none", color=cols[k % 3], label=f"惰性停止 {k + 1}(dcm:off @ 100 %)")
    W += list(r[ok, 1]); E += list(r[ok, 2])
W, E = np.array(W), np.array(E)
K = (W @ E) / (W @ W)
xx = np.linspace(0, W.max() * 1.05, 10)
ax.plot(xx, K * xx, color="#d95f02", lw=1.2, label=f"K = {K:.3e} V·s/rad")
ax.set_xlim(0); ax.set_ylim(0)
ax.set_xlabel("角速度 ω [rad/s](リップル ÷ 3)"); ax.set_ylabel("逆起電力 [V](区間平均)")
ax.legend(fontsize=8, frameon=False, loc="upper left")
ax.set_title(f"(c) 逆起電力 ∝ ω:傾きが K\n(rms {100 * (E - K * W).std() / E.mean():.1f} %、電流計なしで決まる)", loc="left", fontsize=10)

fig.savefig(out, bbox_inches="tight")
print("wrote", out, "K", K)
