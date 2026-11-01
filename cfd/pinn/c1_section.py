#!/usr/bin/env python3
"""c1_section.py — PINN task C1 of docs/PHYSICSNEMO_PLAN.md: steady 2D flow past one blade section, no data.

The same nondimensional problem as the stage-1 LES (cfd/section/make_section.py): chord 1 from x = -0.5 to 0.5,
freestream speed 1 at angle alpha (the section is fixed, the flow is turned), nu = 1/Re, a stadium section of
thickness t with parabolic camber f.  The steady incompressible Navier-Stokes residuals come from PhysicsNeMo
(physicsnemo.sym PDE + PhysicsInformer, autodiff); the point sampling, boundary conditions and force integration
are written here, because the core package has no geometry module.

  domain  x in [-2, 4], y in [-2, 2]; inflow velocity on the left, top and bottom, p = 0 on the right
  wall    u = v = 0 on the section
  loss    mean squared residuals (continuity, x and y momentum) + weighted boundary terms
  forces  cl, cd from the pressure and viscous traction on the section (autodiff gradients at the wall)

Two forms (--form):
  primitive  the network gives u, v, p; the wall and the far field are penalty terms (the textbook PINN)
  psi        the network gives a stream function and p, u = dpsi/dy, v = -dpsi/dx (mass conserved exactly), and
             psi = c + phi(d)^2 (psi_inf + N) with d the distance to the section and phi = 1 - exp(-d/delta),
             so that u = v = 0 on the wall exactly (c is learned). Optional L-BFGS polishing after Adam.

Usage (in the PhysicsNeMo container, on one GPU):
  python -I c1_section.py --re 6000 --alpha 4 --t 0.03 --f 0.03 --steps 20000 --out DIR
Writes DIR/result.json (cl, cd, timings, loss history) and DIR/fields.npz (surface pressure, a coarse field grid).
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np
import torch
from sympy import Function, Symbol

from physicsnemo.sym.eq.pde import PDE
from physicsnemo.sym.eq.phy_informer import PhysicsInformer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geom import X0, X1, Y0, Y1, inside, wall_loop  # noqa: E402


class NavierStokes2D(PDE):
    """steady incompressible Navier-Stokes, unit density."""
    name = "NavierStokes2D"

    def __init__(self, nu):
        self.dim = 2
        x, y = Symbol("x"), Symbol("y")
        u, v, p = (Function(n)(x, y) for n in ("u", "v", "p"))
        self.equations = {
            "continuity": u.diff(x) + v.diff(y),
            "momentum_x": u * u.diff(x) + v * u.diff(y) + p.diff(x) - nu * (u.diff(x, 2) + u.diff(y, 2)),
            "momentum_y": u * v.diff(x) + v * v.diff(y) + p.diff(y) - nu * (v.diff(x, 2) + v.diff(y, 2)),
        }


class Net(torch.nn.Module):
    def __init__(self, width, depth, n_out=3):
        super().__init__()
        layers, n = [], 2
        for _ in range(depth):
            layers += [torch.nn.Linear(n, width), torch.nn.Tanh()]
            n = width
        layers.append(torch.nn.Linear(n, n_out))
        self.mlp = torch.nn.Sequential(*layers)
        self.register_buffer("c", torch.tensor([(X0 + X1) / 2, (Y0 + Y1) / 2]))
        self.register_buffer("s", torch.tensor([(X1 - X0) / 2, (Y1 - Y0) / 2]))

    def forward(self, xy):
        return self.mlp((xy - self.c) / self.s)


class PsiNet(torch.nn.Module):
    """stream-function form with the no-slip wall built in (see the module docstring). forward(xy) returns u, v, p
    like Net; xy must require grad (u, v are derivatives of psi)."""

    def __init__(self, width, depth, t, f, alpha, delta):
        super().__init__()
        self.mlp = Net(width, depth, n_out=2)
        self.c = torch.nn.Parameter(torch.zeros(()))
        a = 0.5 - t / 2
        xs = np.linspace(-a, a, 201)
        mid = np.stack([xs, f * (1 - 4 * xs * xs)], 1)                # the mid-line; the section is d_mid = t/2
        self.register_buffer("A", torch.tensor(mid[:-1], dtype=torch.float32))
        self.register_buffer("B", torch.tensor(mid[1:], dtype=torch.float32))
        self.h, self.delta = t / 2, delta
        self.ca, self.sa = math.cos(alpha), math.sin(alpha)

    def dist(self, xy):
        ab = self.B - self.A                                          # (M, 2)
        ap = xy[:, None, :] - self.A[None]                            # (N, M, 2)
        s = ((ap * ab).sum(-1) / (ab * ab).sum(-1)).clamp(0, 1)
        d = (ap - s[..., None] * ab).norm(dim=-1).min(1).values
        return (d - self.h).clamp_min(0)

    def forward(self, xy):
        out = self.mlp(xy)
        phi = 1 - torch.exp(-self.dist(xy) / self.delta)
        psi_inf = xy[:, 1] * self.ca - xy[:, 0] * self.sa
        psi = self.c + phi ** 2 * (psi_inf + out[:, 0])
        g = torch.autograd.grad(psi.sum(), xy, create_graph=True)[0]
        return torch.stack([g[:, 1], -g[:, 0], out[:, 1]], 1)


def sample(rng, n_int, n_near, n_wall, n_edge, poly, mid, nrm, ds):
    # interior: uniform in the box plus a band near the section (cluster towards the wall)
    a = rng.uniform([X0, Y0], [X1, Y1], (int(n_int * 1.05), 2))
    a = a[~inside(a, poly)][:n_int]
    k = rng.choice(len(mid), n_near, p=ds / ds.sum())
    dist = 0.25 * rng.uniform(0, 1, n_near) ** 2.5 + 1e-4
    b = mid[k] + dist[:, None] * nrm[k]
    wake = np.stack([rng.uniform(0.5, X1, n_near // 2), rng.normal(0, 0.15, n_near // 2)], 1)   # wake band
    interior = np.concatenate([a, b, wake])
    interior = interior[~inside(interior, poly)]
    # wall: points on the polygon segments, weighted by length
    k = rng.choice(len(mid), n_wall, p=ds / ds.sum())
    u = rng.uniform(0, 1, n_wall)[:, None]
    wall = poly[k] + u * (np.roll(poly, -1, axis=0)[k] - poly[k])
    # outer edges: inflow (left, top, bottom) and outflow (right)
    m = n_edge // 4
    inflow = np.concatenate([np.stack([np.full(m, X0), rng.uniform(Y0, Y1, m)], 1),
                             np.stack([rng.uniform(X0, X1, m), np.full(m, Y1)], 1),
                             np.stack([rng.uniform(X0, X1, m), np.full(m, Y0)], 1)])
    outflow = np.stack([np.full(m, X1), rng.uniform(Y0, Y1, m)], 1)
    return interior, wall, inflow, outflow


def forces(net, mid, nrm, ds, nu, alpha, dev):
    """cl, cd, and the surface pressure from the traction on the section (n out of the body, into the fluid)."""
    xy = torch.tensor(mid, dtype=torch.float32, device=dev, requires_grad=True)
    out = net(xy)
    u, v, p = out[:, 0], out[:, 1], out[:, 2]
    gu = torch.autograd.grad(u.sum(), xy, retain_graph=True)[0]
    gv = torch.autograd.grad(v.sum(), xy)[0]
    n = torch.tensor(nrm, dtype=torch.float32, device=dev)
    sxx, syy, sxy = 2 * nu * gu[:, 0], 2 * nu * gv[:, 1], nu * (gu[:, 1] + gv[:, 0])
    # force of the fluid on the body = integral of (-p I + 2 nu S) . n, n the body's outward normal
    tx = -p * n[:, 0] + sxx * n[:, 0] + sxy * n[:, 1]
    ty = -p * n[:, 1] + sxy * n[:, 0] + syy * n[:, 1]
    w = torch.tensor(ds, dtype=torch.float32, device=dev)
    Fx, Fy = float((tx * w).sum().detach()), float((ty * w).sum().detach())
    ca, sa = math.cos(alpha), math.sin(alpha)
    lift, drag = -Fx * sa + Fy * ca, Fx * ca + Fy * sa
    return 2 * lift, 2 * drag, p.detach().cpu().numpy()


def losses(net, pi, interior, wall, inflow, outflow, U, w_wall):
    out = net(interior)
    res = pi.forward({"coordinates": interior, "u": out[:, 0:1], "v": out[:, 1:2], "p": out[:, 2:3]})
    l_pde = sum((res[k] ** 2).mean() for k in ("continuity", "momentum_x", "momentum_y"))
    ow, oi, oo = net(wall), net(inflow), net(outflow)
    l_wall = (ow[:, :2] ** 2).mean()
    l_in = ((oi[:, 0] - U[0]) ** 2).mean() + ((oi[:, 1] - U[1]) ** 2).mean()
    l_out = (oo[:, 2] ** 2).mean()
    return l_pde + w_wall * l_wall + l_in + l_out, l_pde, l_wall, l_in, l_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--re", type=float, default=6000)
    ap.add_argument("--alpha", type=float, default=4)
    ap.add_argument("--t", type=float, default=0.03)
    ap.add_argument("--f", type=float, default=0.03)
    ap.add_argument("--steps", type=int, default=20000)
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
    ap.add_argument("--form", choices=("primitive", "psi"), default="primitive")
    ap.add_argument("--delta", type=float, default=0.1, help="psi form: length of the wall factor phi")
    ap.add_argument("--lbfgs", type=int, default=0, help="L-BFGS iterations after Adam (full batch, last sample)")
    ap.add_argument("--data", help="task C6: npz of LES mean-field points (les_samples.py collect)")
    ap.add_argument("--n-data", type=int, default=0, help="number of pool points used as data (the first n)")
    ap.add_argument("--w-data", type=float, default=10.0)
    ap.add_argument("--no-pde", action="store_true", help="data only: drop the equations (and boundary terms)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t_start = time.time()
    dev = torch.device("cuda")
    torch.backends.cuda.matmul.allow_tf32 = False                 # second derivatives: keep full fp32
    torch.manual_seed(a.seed)
    rng = np.random.default_rng(a.seed)
    nu, alpha = 1.0 / a.re, math.radians(a.alpha)
    U = (math.cos(alpha), math.sin(alpha))
    poly, mid, nrm, ds = wall_loop(a.t, a.f)
    assert not inside(mid + 1e-4 * nrm, poly).any(), "normals must point out of the body"

    net = (Net(a.width, a.depth) if a.form == "primitive" else PsiNet(a.width, a.depth, a.t, a.f, alpha, a.delta)).to(dev)
    pi = PhysicsInformer(["continuity", "momentum_x", "momentum_y"], NavierStokes2D(nu), "autodiff", device=dev)
    opt = torch.optim.Adam(net.parameters(), lr=a.lr)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: 0.01 ** (s / a.steps))     # 1e-3 -> 1e-5
    T = lambda z: torch.tensor(z, dtype=torch.float32, device=dev)

    D = np.load(a.data) if a.data else None
    if D is not None and a.n_data:
        dxy, duvp = T(D["pool_xy"][:a.n_data]), T(D["pool_uvp"][:a.n_data])
    else:
        dxy = duvp = None

    def total(interior, wall, inflow, outflow):
        if a.no_pde:
            z = torch.zeros((), device=dev)
            loss, l_pde, l_wall, l_in, l_out = z, z, z, z, z
        else:
            loss, l_pde, l_wall, l_in, l_out = losses(net, pi, interior, wall, inflow, outflow, U, a.w_wall)
        l_data = ((net(dxy.requires_grad_(True)) - duvp) ** 2).mean() if dxy is not None else torch.zeros((), device=dev)
        return loss + a.w_data * l_data, l_pde, l_wall, l_in, l_out, l_data

    hist, t_train = [], time.time()
    for step in range(a.steps + 1):
        if step % a.resample == 0:
            interior, wall, inflow, outflow = (T(z).requires_grad_(True) for z in sample(rng, a.n_int, a.n_near, a.n_wall, a.n_edge, poly, mid, nrm, ds))
        loss, l_pde, l_wall, l_in, l_out, l_data = total(interior, wall, inflow, outflow)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step(); sched.step()
        if step % 500 == 0:
            cl, cd, _ = forces(net, mid, nrm, ds, nu, alpha, dev)
            h = dict(step=step, s=round(time.time() - t_train, 1), loss=float(loss), pde=float(l_pde), wall=float(l_wall),
                     inflow=float(l_in), outflow=float(l_out), data=float(l_data), cl=round(cl, 4), cd=round(cd, 5))
            hist.append(h)
            print(json.dumps(h), flush=True)
    if a.lbfgs:
        lb = torch.optim.LBFGS(net.parameters(), lr=1.0, max_iter=a.lbfgs, history_size=50, line_search_fn="strong_wolfe",
                               tolerance_grad=1e-12, tolerance_change=1e-14)

        def closure():
            lb.zero_grad(set_to_none=True)
            l = total(interior, wall, inflow, outflow)[0]
            l.backward()
            return l
        lb.step(closure)
        loss, l_pde, l_wall, l_in, l_out, l_data = total(interior, wall, inflow, outflow)
        cl, cd, _ = forces(net, mid, nrm, ds, nu, alpha, dev)
        h = dict(step="lbfgs", data=float(l_data), s=round(time.time() - t_train, 1), loss=float(loss), pde=float(l_pde), wall=float(l_wall),
                 inflow=float(l_in), outflow=float(l_out), cl=round(cl, 4), cd=round(cd, 5))
        hist.append(h)
        print(json.dumps(h), flush=True)
    torch.cuda.synchronize()
    t_train = time.time() - t_train

    cl, cd, p_wall = forces(net, mid, nrm, ds, nu, alpha, dev)
    gx, gy = np.meshgrid(np.linspace(X0, X1, 301), np.linspace(Y0, Y1, 201))
    g = np.stack([gx.ravel(), gy.ravel()], 1)
    fg = np.concatenate([net(T(g[i:i + 20000]).requires_grad_(True)).detach().cpu().numpy() for i in range(0, len(g), 20000)])
    fg[inside(g, poly)] = np.nan
    dy = gy[1, 0] - gy[0, 0]
    flux_in, flux_out = float(np.nansum(fg[:, 0].reshape(gx.shape)[:, 0]) * dy), float(np.nansum(fg[:, 0].reshape(gx.shape)[:, -1]) * dy)
    np.savez_compressed(os.path.join(a.out, "fields.npz"), wall_xy=mid, wall_n=nrm, wall_p=p_wall,
                        grid_x=gx, grid_y=gy, u=fg[:, 0].reshape(gx.shape), v=fg[:, 1].reshape(gx.shape), p=fg[:, 2].reshape(gx.shape))
    test = {}
    if D is not None:                                      # error on points the training never saw
        for name in ("test", "wall"):
            pr = np.concatenate([net(T(D[name + "_xy"][i:i + 20000]).requires_grad_(True)).detach().cpu().numpy()
                                 for i in range(0, len(D[name + "_xy"]), 20000)])
            ref = D[name + "_uvp"]
            test[name] = {k: round(float(np.linalg.norm(pr[:, j] - ref[:, j]) / np.linalg.norm(ref[:, j] - (0 if k != "p" else ref[:, j].mean()))), 4)
                          for j, k in enumerate(("u", "v", "p"))}
        print("relative L2 error on unseen points:", json.dumps(test), flush=True)
    res = dict(task="C6" if a.data else "C1", n_data=a.n_data, no_pde=a.no_pde, test_rel_l2=test, method=("data-only-nn" if a.no_pde else "pinn-" + a.form), flux_in=round(flux_in, 4), flux_out=round(flux_out, 4), re=a.re, alpha=a.alpha, t=a.t, f=a.f, cl=round(cl, 4), cd=round(cd, 5),
               train_s=round(t_train, 1), wall_s=round(time.time() - t_start, 1), gpu=torch.cuda.get_device_name(0),
               n_params=sum(p.numel() for p in net.parameters()), args=vars(a), history=hist)
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print("cl %.4f cd %.5f, %.0f s training" % (cl, cd, t_train))


if __name__ == "__main__":
    main()
