#!/usr/bin/env python3
"""c2_param.py — PINN task C2 of docs/PHYSICSNEMO_PLAN.md: one network for a range of angles of attack.

The C1 problem (c1_section.py) with alpha as a third input: u, v, p = N(x, y, alpha). The equations are enforced
at points whose alpha is drawn uniformly from [--amin, --amax], so the physics covers every angle; LES data
(les_samples.py collect, one npz per angle) can be added at a few training angles only. After training, cl and cd
are integrated on the section at every angle of --eval, and the field error is measured on the unseen test points
of every angle that has LES data.

Modes:  default         equations + boundary terms (+ data if --data-angles is given)
        --no-pde        data only (the network is fitted to the LES points at the training angles)

Usage (in the PhysicsNeMo container, one GPU):
  python -I c2_param.py --data-dir DIR --data-angles -4,0,4,8 --n-data 100 --eval -4,-2,0,2,4,6,8,10 --out OUT
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np
import torch

from physicsnemo.sym.eq.phy_informer import PhysicsInformer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c1_section import NavierStokes2D, sample  # noqa: E402
from geom import X0, X1, Y0, Y1, inside, wall_loop  # noqa: E402

A_SCALE = 10.0                                        # alpha (degrees) / A_SCALE is the third input


class ParamNet(torch.nn.Module):
    def __init__(self, width, depth):
        super().__init__()
        layers, n = [], 3
        for _ in range(depth):
            layers += [torch.nn.Linear(n, width), torch.nn.Tanh()]
            n = width
        layers.append(torch.nn.Linear(n, 3))
        self.mlp = torch.nn.Sequential(*layers)
        self.register_buffer("c", torch.tensor([(X0 + X1) / 2, (Y0 + Y1) / 2]))
        self.register_buffer("s", torch.tensor([(X1 - X0) / 2, (Y1 - Y0) / 2]))

    def forward(self, xy, alpha_deg):
        return self.mlp(torch.cat([(xy - self.c) / self.s, alpha_deg[:, None] / A_SCALE], 1))


def forces(net, mid, nrm, ds, nu, alpha_deg, dev):
    xy = torch.tensor(mid, dtype=torch.float32, device=dev, requires_grad=True)
    al = torch.full((len(mid),), float(alpha_deg), device=dev)
    out = net(xy, al)
    u, v, p = out[:, 0], out[:, 1], out[:, 2]
    gu = torch.autograd.grad(u.sum(), xy, retain_graph=True)[0]
    gv = torch.autograd.grad(v.sum(), xy)[0]
    n = torch.tensor(nrm, dtype=torch.float32, device=dev)
    sxx, syy, sxy = 2 * nu * gu[:, 0], 2 * nu * gv[:, 1], nu * (gu[:, 1] + gv[:, 0])
    tx = -p * n[:, 0] + sxx * n[:, 0] + sxy * n[:, 1]
    ty = -p * n[:, 1] + sxy * n[:, 0] + syy * n[:, 1]
    w = torch.tensor(ds, dtype=torch.float32, device=dev)
    Fx, Fy = float((tx * w).sum().detach()), float((ty * w).sum().detach())
    a = math.radians(alpha_deg)
    return 2 * (-Fx * math.sin(a) + Fy * math.cos(a)), 2 * (Fx * math.cos(a) + Fy * math.sin(a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--re", type=float, default=6000)
    ap.add_argument("--t", type=float, default=0.03)
    ap.add_argument("--f", type=float, default=0.03)
    ap.add_argument("--amin", type=float, default=-5)
    ap.add_argument("--amax", type=float, default=11)
    ap.add_argument("--eval", default="-4,-2,0,2,4,6,8,10")
    ap.add_argument("--data-dir", help="directory with les_points_re*_a*.npz")
    ap.add_argument("--data-angles", default="", help="angles whose LES points are used, e.g. -4,0,4,8")
    ap.add_argument("--n-data", type=int, default=100, help="points per training angle")
    ap.add_argument("--w-data", type=float, default=10.0)
    ap.add_argument("--no-pde", action="store_true")
    ap.add_argument("--steps", type=int, default=10000)
    ap.add_argument("--width", type=int, default=256)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--n-int", type=int, default=40000)
    ap.add_argument("--n-near", type=int, default=40000)
    ap.add_argument("--n-wall", type=int, default=4000)
    ap.add_argument("--n-edge", type=int, default=4000)
    ap.add_argument("--w-wall", type=float, default=10.0)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--resample", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t_start = time.time()
    dev = torch.device("cuda")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.manual_seed(a.seed)
    rng = np.random.default_rng(a.seed)
    nu = 1.0 / a.re
    poly, mid, nrm, ds = wall_loop(a.t, a.f)
    T = lambda z: torch.tensor(np.asarray(z), dtype=torch.float32, device=dev)
    case = lambda al: "re%05d_t%03d_f%03d_a%+03d" % (a.re, round(a.t * 1000), round(a.f * 1000), al)
    load = lambda al: np.load(os.path.join(a.data_dir, "les_points_%s.npz" % case(al)))

    train_angles = [int(x) for x in a.data_angles.split(",") if x]
    dxy, dal, duvp = [], [], []
    for al in train_angles:
        D = load(al)
        dxy.append(D["pool_xy"][:a.n_data]); dal.append(np.full(len(dxy[-1]), al)); duvp.append(D["pool_uvp"][:a.n_data])
    if train_angles:
        dxy, dal, duvp = T(np.concatenate(dxy)), T(np.concatenate(dal)), T(np.concatenate(duvp))

    net = ParamNet(a.width, a.depth).to(dev)
    pi = PhysicsInformer(["continuity", "momentum_x", "momentum_y"], NavierStokes2D(nu), "autodiff", device=dev)
    opt = torch.optim.Adam(net.parameters(), lr=a.lr)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: 0.01 ** (s / a.steps))

    def draw():
        interior, wall, inflow, outflow = sample(rng, a.n_int, a.n_near, a.n_wall, a.n_edge, poly, mid, nrm, ds)
        al = lambda z: rng.uniform(a.amin, a.amax, len(z))
        return [(T(z).requires_grad_(True), T(al(z))) for z in (interior, wall, inflow, outflow)]

    hist, t_train = [], time.time()
    zero = torch.zeros((), device=dev)
    for step in range(a.steps + 1):
        if step % a.resample == 0:
            (ixy, ial), (wxy, wal), (fxy, fal), (oxy, oal) = draw()
        if a.no_pde:
            l_pde = l_wall = l_bc = zero
        else:
            out = net(ixy, ial)
            res = pi.forward({"coordinates": ixy, "u": out[:, 0:1], "v": out[:, 1:2], "p": out[:, 2:3]})
            l_pde = sum((res[k] ** 2).mean() for k in ("continuity", "momentum_x", "momentum_y"))
            l_wall = (net(wxy, wal)[:, :2] ** 2).mean()
            oi = net(fxy, fal)
            r = torch.deg2rad(fal)
            l_bc = ((oi[:, 0] - torch.cos(r)) ** 2).mean() + ((oi[:, 1] - torch.sin(r)) ** 2).mean() + (net(oxy, oal)[:, 2] ** 2).mean()
        l_data = ((net(dxy, dal) - duvp) ** 2).mean() if train_angles else zero
        loss = l_pde + a.w_wall * l_wall + l_bc + a.w_data * l_data
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step(); sched.step()
        if step % 1000 == 0:
            cl4, cd4 = forces(net, mid, nrm, ds, nu, 4.0, dev)
            h = dict(step=step, s=round(time.time() - t_train, 1), loss=float(loss), pde=float(l_pde), wall=float(l_wall),
                     bc=float(l_bc), data=float(l_data), cl_a4=round(cl4, 4), cd_a4=round(cd4, 5))
            hist.append(h)
            print(json.dumps(h), flush=True)
    torch.cuda.synchronize()
    t_train = time.time() - t_train

    t0 = time.time()
    polar = []
    for al in [int(x) for x in a.eval.split(",")]:
        cl, cd = forces(net, mid, nrm, ds, nu, al, dev)
        row = dict(alpha=al, cl=round(cl, 4), cd=round(cd, 5), trained_with_data=al in train_angles)
        if a.data_dir and os.path.exists(os.path.join(a.data_dir, "les_points_%s.npz" % case(al))):
            D = load(al)
            pr = net(T(D["test_xy"]).requires_grad_(True), T(np.full(len(D["test_xy"]), al))).detach().cpu().numpy()
            ref = D["test_uvp"]
            row["test_rel_l2"] = {k: round(float(np.linalg.norm(pr[:, j] - ref[:, j]) / np.linalg.norm(ref[:, j] - (ref[:, j].mean() if k == "p" else 0))), 4)
                                  for j, k in enumerate("uvp")}
        polar.append(row)
        print(json.dumps(row), flush=True)
    t_eval = time.time() - t0
    res = dict(task="C2", method="data-only-nn" if a.no_pde else ("pinn+data" if train_angles else "pinn"),
               re=a.re, t=a.t, f=a.f, data_angles=train_angles, n_data=a.n_data if train_angles else 0,
               train_s=round(t_train, 1), eval_s_per_angle=round(t_eval / len(polar), 3), wall_s=round(time.time() - t_start, 1),
               gpu=torch.cuda.get_device_name(0), args=vars(a), polar=polar, history=hist)
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
