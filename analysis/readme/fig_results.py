#!/usr/bin/env python3
"""README 用の図: 現行ツイン(twin/params.json)と実測の比較。

  python3 analysis/readme/fig_results.py media/readme/results.png

(a) 部分 duty の定常回転数:ADC 回転計 adc:emf(data/adc/partial_duty_emf.json)vs ツイン
(b) 推力:天秤 + TEL 回転数(IMG_5785)vs BEMT。旧モデル kT·ω² も破線で
(c) 閉ループ回転数制御 rpm:set 1500→2500→1000→2000:実機 TEL(data/rpm_ctl_run1.json)vs ツイン
"""
import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "twin"))
import motor_twin as mt  # noqa: E402

plt.rcParams["font.family"] = ["Hiragino Sans"]
plt.rcParams["font.size"] = 10
D = os.path.join(ROOT, "twin", "data")
P = mt.load_params()
RPM = 60 / (2 * math.pi)
out = sys.argv[1]

fig, axs = plt.subplots(1, 3, figsize=(13, 3.9), dpi=130, gridspec_kw={"width_ratios": [1, 1, 1.5], "wspace": 0.3})

# (a) partial duty: step down 255 -> 77 like the adc:emf run, 3 s per step
rows = json.load(open(os.path.join(D, "adc", "partial_duty_emf.json")))["summary"]["rows"]
duties = [r["duty"] for r in rows]
script = [(0.0, "dcm:speed 255")] + [(3.0 * (k + 1), f"dcm:speed {d}") for k, d in enumerate(duties[1:])]
sim = mt.simulate(script, 3.0 * len(duties), P)
t, w = np.array(sim["t"]), np.array(sim["w"])
twin = [w[(t > 3.0 * k + 2.4) & (t < 3.0 * (k + 1))].mean() * RPM for k in range(len(duties))]
ax = axs[0]
x = [d / 255 * 100 for d in duties]
ax.errorbar(x, [r["rpm"] for r in rows], yerr=[r["rpm_se"] for r in rows], fmt="o", ms=5, color="#d95f02",
            capsize=3, label="実測(ADC 回転計 adc:emf)")
ax.plot(x, twin, "s-", ms=4, color="#1b9e77", mfc="none", label="ツイン")
ax.set_xlabel("duty [%]"); ax.set_ylabel("定常回転数 [rpm]"); ax.set_ylim(-100, 3400)
ax.legend(fontsize=8, frameon=False, loc="upper left")
ax.set_title("(a) 部分 duty の定常回転数\n100 % から段階的に下げる(30 % で停止)", loc="left", fontsize=10)

# (b) thrust vs rpm
st = json.load(open(os.path.join(D, "thrust_steps_IMG_5785.json")))["steps"]
ax = axs[1]
rr = np.linspace(0, 3300, 200)
bal = [mt.aero(P, r / RPM)[3] / 9.80665 * 1000 for r in rr]
ax.plot(rr, bal, color="#1b9e77", label="BEMT(Re 依存の揚力)")
ax.plot(rr, P["kT"] * (rr / RPM) ** 2 / 9.80665 * 1000, "--", color="#999", lw=0.9, label="旧モデル kT·ω²")
for s in st:
    ax.plot(s["rpm"], s["balance_g"], "o", ms=5, color="#d95f02", mfc="none")
ax.plot([], [], "o", color="#d95f02", mfc="none", label="実測(天秤 + TEL、2 回)")
ax.set_xlabel("回転数 [rpm]"); ax.set_ylabel("推力 [gf]")
ax.legend(fontsize=8, frameon=False, loc="upper left")
ax.set_title("(b) 推力 ∝ n^2.23:低速で揚力が落ちる\n(IMG_5785、6 s ごとの段階)", loc="left", fontsize=10)

# (c) closed loop
run = json.load(open(os.path.join(D, "rpm_ctl_run1.json")))
ax = axs[2]
tel = run["tel"]                                          # [host s, board ms, duty, rpm, filtered rpm, ref]
tt = np.array([r[0] for r in tel]); rp = np.array([r[3] for r in tel]); rf = np.array([r[4] for r in tel])
ax.plot(tt, rp, ".", ms=2.5, color="#d95f02", alpha=0.6, label="実機 回転計(TEL、50 ms ごと)")
ax.plot(tt, rf, color="#d95f02", lw=0.9, label="実機 フィルタ後")
script = [(a, c) for a, k, c in run["log"] if k == "tx" and not c.startswith("tel")]
sim = mt.simulate(script, max(tt) + 0.5, P)
ax.plot(sim["t"], np.array(sim["w"]) * RPM, color="#1b9e77", lw=1.2, label="ツイン(同じ rpm:set)")
ref = [(a, float(c.split()[1])) for a, c in script if c.startswith("rpm:set")]
for (a, r), nxt in zip(ref, ref[1:] + [(max(tt), None)]):
    ax.hlines(r, a, nxt[0], color="#333", lw=0.8)
ax.set_xlabel("時刻 [s]"); ax.set_ylabel("回転数 [rpm]")
ax.legend(fontsize=8, frameon=False, loc="lower right")
ax.set_title("(c) 閉ループ回転数制御 rpm:set(FF + PI)\n1500 → 2500 → 1000 → 2000 rpm を ±1 % で保持", loc="left", fontsize=10)

fig.savefig(out, bbox_inches="tight")
print("wrote", out)
