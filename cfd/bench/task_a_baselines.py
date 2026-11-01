#!/usr/bin/env python3
"""task_a_baselines.py — task A of docs/PHYSICSNEMO_PLAN.md: the baselines a learned model has to beat.

Predicts the section coefficients cl, cd of held-out stage-1 LES cases (twin/data/cfd/section_polars.json) with
  interp   linear in alpha, t/c, f/c and log Re (bemt.SectionPolar on the training cases; clamped outside the table)
  gp       Gaussian process on (alpha, log Re, t/c, f/c), anisotropic RBF + white noise, one per coefficient
for fixed splits:
  alpha-odd    every other angle of attack held out (interpolation in alpha)
  re10000-out  Re 10 000 held out (interpolation in Re)
  re3000-ext   train on Re >= 6000, test on the finished Re 3000 cases (extrapolation)
and appends one row per (method, split) to twin/data/cfd/ml_bench.json, with the cost of the training data from
twin/data/cfd/cost.json.

Usage:  python3 cfd/bench/task_a_baselines.py
"""
import json
import math
import os
import sys
import tempfile
import time

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "twin"))
import bemt  # noqa: E402

DATA = os.path.join(ROOT, "twin", "data", "cfd")


def name(r):
    return "re%05d_t%03d_f%03d_a%+03d" % (r["re"], round(r["t"] * 1000), round(r["f"] * 1000), r["alpha"])


def splits(rows):
    full = [r for r in rows if r["re"] >= 6000]
    odd = lambda r: (r["alpha"] // 2) % 2 == 1
    return {
        "alpha-odd": ([r for r in full if not odd(r)], [r for r in full if odd(r)]),
        "re10000-out": ([r for r in full if r["re"] != 10000], [r for r in full if r["re"] == 10000]),
        "re3000-ext": (full, [r for r in rows if r["re"] == 3000]),
    }


def fit_interp(train):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(dict(cases=train), f)
    p = bemt.SectionPolar(f.name)
    os.unlink(f.name)
    return lambda r: p(r["alpha"], r["re"], r["t"], r["f"])


def features(r):
    return [r["alpha"] / 10, math.log(r["re"] / 10000), r["t"] * 20, r["f"] * 20]


def fit_gp(train):
    X, yl, yd = [], [], []
    for r in train:
        X.append(features(r)); yl.append(r["cl"]); yd.append(r["cd"])
        if r["f"] == 0 and r["alpha"] > 0:                     # symmetric section: only alpha >= 0 was run
            m = dict(r, alpha=-r["alpha"])
            X.append(features(m)); yl.append(-r["cl"]); yd.append(r["cd"])
    X = np.array(X)
    gps = []
    for y in (np.array(yl), np.array(yd)):
        k = ConstantKernel(1.0) * RBF(length_scale=[1, 1, 1, 1], length_scale_bounds=(1e-2, 1e2)) + WhiteKernel(1e-3, (1e-6, 1))
        gps.append(GaussianProcessRegressor(k, normalize_y=True, n_restarts_optimizer=2, random_state=0).fit(X, y))
    return lambda r: tuple(float(g.predict(np.array([features(r)]))[0]) for g in gps)


def main():
    rows = [r for r in json.load(open(os.path.join(DATA, "section_polars.json")))["cases"] if "cl" in r]
    cost = {c["case"]: c["node_h"] for c in json.load(open(os.path.join(DATA, "cost.json")))["runs"]
            if c["stage"] == "1-section-les"}
    bench_path = os.path.join(DATA, "ml_bench.json")
    bench = json.load(open(bench_path)) if os.path.exists(bench_path) else []
    bench = [b for b in bench if not (b["task"] == "A" and b["method"] in ("interp", "gp"))]   # rerun replaces
    print("%-7s %-12s %5s %5s | %8s %8s | %8s %8s | %6s" % ("method", "split", "train", "test", "cl MAE", "cl max",
                                                          "cd MAE", "cd max", "fit s"))
    for split, (train, test) in splits(rows).items():
        unc_cl = float(np.median([abs(r.get("cl_drift", 0)) for r in test]))
        unc_cd = float(np.median([abs(r.get("cd_drift", 0)) for r in test]))
        for method, fit in (("interp", fit_interp), ("gp", fit_gp)):
            t0 = time.time(); f = fit(train); t_fit = time.time() - t0
            t0 = time.time(); pred = [f(r) for r in test]; t_inf = (time.time() - t0) / len(test)
            el = np.array([p[0] - r["cl"] for p, r in zip(pred, test)])
            ed = np.array([p[1] - r["cd"] for p, r in zip(pred, test)])
            lo = np.array([abs(r["alpha"]) <= 8 for r in test])
            row = dict(task="A", method=method, split=split, train_frac=1.0, n_train=len(train), n_test=len(test),
                       data_node_h=round(sum(cost.get(name(r), 0) for r in train), 1),
                       train_node_h=round(t_fit / 3600, 6), infer_s=round(t_inf, 6), hardware="laptop CPU",
                       err_vs_cfd=dict(cl_mae=round(float(np.abs(el).mean()), 4), cl_max=round(float(np.abs(el).max()), 4),
                                       cd_mae=round(float(np.abs(ed).mean()), 5), cd_max=round(float(np.abs(ed).max()), 5),
                                       cl_mae_alpha_le8=round(float(np.abs(el[lo]).mean()), 4) if lo.any() else None,
                                       cd_mae_alpha_le8=round(float(np.abs(ed[lo]).mean()), 5) if lo.any() else None),
                       cfd_uncert=dict(cl_drift_median=round(unc_cl, 4), cd_drift_median=round(unc_cd, 5)))
            bench.append(row)
            print("%-7s %-12s %5d %5d | %8.4f %8.4f | %8.5f %8.5f | %6.2f   (alpha<=8: cl %.4f cd %.5f; CFD drift cl %.4f cd %.5f)" % (
                method, split, len(train), len(test), row["err_vs_cfd"]["cl_mae"], row["err_vs_cfd"]["cl_max"],
                row["err_vs_cfd"]["cd_mae"], row["err_vs_cfd"]["cd_max"], t_fit,
                row["err_vs_cfd"]["cl_mae_alpha_le8"] or 0, row["err_vs_cfd"]["cd_mae_alpha_le8"] or 0, unc_cl, unc_cd))
    json.dump(bench, open(bench_path, "w"), indent=1)


if __name__ == "__main__":
    main()
