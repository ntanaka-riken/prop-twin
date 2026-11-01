#!/usr/bin/env python3
"""c3_axi.py — PINN task C3 of docs/PHYSICSNEMO_PLAN.md: the rig around an actuator disk, axisymmetric, no data.

The same problem as the OpenFOAM wedge runs of cfd/c3/make_axi.py with --turb nu: steady incompressible flow in
(r, z) with swirl, a constant effective viscosity, the rotor as rings of body force (twin/data/cfd/c3_disk.json),
still walls on the table, scale, cup, motor and hub, p = 0 on the room boundary (r = 0.30 m, z = 0.48 m).
Nondimensional with the tip radius R = 32 mm, U = 2 m/s and the air density.

  network   inputs (r^2, z), outputs a, b, c, p;  u_r = r phi a,  u_theta = r phi b,  u_z = phi c,
            phi = 1 - exp(-d / delta), d the distance to the walls: no slip and the axis conditions (u_r = u_theta = 0,
            d u_z / dr = 0 at r = 0) hold exactly; only the room pressure is a penalty term
  equations PhysicsNeMo PDE (sympy) + PhysicsInformer (autodiff): continuity, r, theta, z momentum
  balance   vertical traction (pressure + viscous) on each solid, times 2 pi r, plus the disk (the blades' force),
            in gf with the stage-3 sign (+ = the reading rises)

Usage (in the PhysicsNeMo container, one GPU):
  python -I c3_axi.py --dir fwd --nu-eff 1.5e-3 --steps 20000 --out DIR
Writes DIR/result.json (balance and parts, timings, history) and DIR/fields.npz (a field grid and the probe lines).
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "c3"))
from geom import inside  # noqa: E402
import make_axi as M  # noqa: E402

RT = 0.032                      # length scale: tip radius (m)
UR = 2.0                        # velocity scale (m/s)
G = 9.80665e-3                  # N per gf


class AxiNS(PDE):
    """steady incompressible Navier-Stokes in (r, z) with swirl, unit density, body force (fr = 0, ft, fz)."""
    name = "AxiNS"

    def __init__(self, nu):
        self.dim = 2
        r, z = Symbol("x"), Symbol("y")
        u, v, w, p = (Function(n)(r, z) for n in ("u", "v", "w", "p"))
        ft, fz = Function("ft")(r, z), Function("fz")(r, z)
        lap = lambda q: q.diff(r, 2) + q.diff(r) / r + q.diff(z, 2)
        adv = lambda q: u * q.diff(r) + w * q.diff(z)
        self.equations = {
            "continuity": u.diff(r) + u / r + w.diff(z),
            "momentum_r": adv(u) - v * v / r + p.diff(r) - nu * (lap(u) - u / r ** 2),
            "momentum_t": adv(v) + u * v / r - nu * (lap(v) - v / r ** 2) - ft,
            "momentum_z": adv(w) + p.diff(z) - nu * lap(w) - fz,
        }


def outline():
    """per part: the wetted wall as a polyline in (r, z) metres, walked with the fluid on the left, and the solid as a
    closed polygon for the inside test."""
    rin = M.CUP_R1 - M.CUP_WALL + M.SLOPE * M.RECESS
    cap = [(M.HUB_R * math.cos(q), M.HUB_C + M.HUB_CAP * math.sin(q)) for q in np.linspace(0, math.pi / 2, 16)]
    walls = {
        "table": [(M.SCALE_R, 0.0), (M.R_OUT, 0.0)],
        "scale": [(M.CUP_R0, M.CUP_Z0), (M.SCALE_R, M.CUP_Z0), (M.SCALE_R, 0.0)],
        "cup": [(M.MOTOR_R, M.FLOOR), (rin, M.FLOOR), (M.CUP_R1 - M.CUP_WALL, M.CUP_Z1), (M.CUP_R1, M.CUP_Z1), (M.CUP_R0, M.CUP_Z0)],
        "motor": [(0.0, M.MOTOR_TOP + M.BOSS_H), (M.BOSS_R, M.MOTOR_TOP + M.BOSS_H), (M.BOSS_R, M.MOTOR_TOP),
                  (M.MOTOR_R, M.MOTOR_TOP), (M.MOTOR_R, M.FLOOR)],
        "hub": cap[::-1] + [(M.HUB_R, M.HUB_B), (0.0, M.HUB_B)],
    }
    solids = [
        [(0, 0), (M.SCALE_R, 0), (M.SCALE_R, M.CUP_Z0), (0, M.CUP_Z0)],
        [(0, M.CUP_Z0), (M.CUP_R0, M.CUP_Z0), (M.CUP_R1, M.CUP_Z1), (M.CUP_R1 - M.CUP_WALL, M.CUP_Z1), (rin, M.FLOOR), (0, M.FLOOR)],
        [(0, M.FLOOR - 1e-3), (M.MOTOR_R, M.FLOOR - 1e-3), (M.MOTOR_R, M.MOTOR_TOP), (M.BOSS_R, M.MOTOR_TOP),
         (M.BOSS_R, M.MOTOR_TOP + M.BOSS_H), (0, M.MOTOR_TOP + M.BOSS_H)],
        [(0, M.HUB_B), (M.HUB_R, M.HUB_B)] + cap,
    ]
    return walls, [np.array(s) / RT for s in solids]


def segments(walls, n_per_mm=4):
    """midpoints, outward (into the fluid) normals, lengths and part index of the wall pieces, nondimensional."""
    mids, nrm, ds, part = [], [], [], []
    for k, (name, pts) in enumerate(walls.items()):
        for (r0, z0), (r1, z1) in zip(pts[:-1], pts[1:]):
            L = math.hypot(r1 - r0, z1 - z0)
            n = max(1, int(L * 1e3 * n_per_mm))
            t = (np.arange(n) + 0.5) / n
            mids.append(np.stack([r0 + t * (r1 - r0), z0 + t * (z1 - z0)], 1))
            # walking along the polyline with the fluid on the left: the normal into the fluid is (-dz, dr)
            nrm.append(np.tile([-(z1 - z0) / L, (r1 - r0) / L], (n, 1)))
            ds.append(np.full(n, L / n))
            part.append(np.full(n, k))
    return np.concatenate(mids) / RT, np.concatenate(nrm), np.concatenate(ds) / RT, np.concatenate(part)


class Net(torch.nn.Module):
    def __init__(self, width, depth, wall_pts, delta):
        super().__init__()
        layers, n = [], 2
        for _ in range(depth):
            layers += [torch.nn.Linear(n, width), torch.nn.Tanh()]
            n = width
        layers.append(torch.nn.Linear(n, 4))
        self.mlp = torch.nn.Sequential(*layers)
        self.A, self.B = wall_pts                      # wall segments (M, 2) for the distance
        self.delta = delta
        self.rmax, self.zmax = M.R_OUT / RT, M.Z_OUT / RT

    def dist(self, rz):
        ab = self.B - self.A
        ap = rz[:, None, :] - self.A[None]
        s = ((ap * ab).sum(-1) / (ab * ab).sum(-1)).clamp(0, 1)
        return (ap - s[..., None] * ab).norm(dim=-1).min(1).values

    def forward(self, rz):
        r, z = rz[:, :1], rz[:, 1:]
        x = torch.cat([2 * (r / self.rmax) ** 2 - 1, 2 * z / self.zmax - 1], 1)
        o = self.mlp(x)
        phi = (1 - torch.exp(-self.dist(rz) / self.delta))[:, None]
        return torch.cat([r * phi * o[:, :1], r * phi * o[:, 1:2], phi * o[:, 2:3], o[:, 3:4]], 1)


def disk_force(disk, d, rz, e=0.3e-3):
    """kinematic body force (ft, fz) on the air, nondimensional, smoothed over e (m) at the disk's edges."""
    D = disk["fwd" if d > 0 else "rev"]
    r = np.array(D["r"])
    dr = r[1] - r[0]
    vol = 2 * math.pi * r * dr * disk["thickness"]
    az = d * np.array(D["dT"]) / (M.RHO * vol)               # m/s^2
    at = d * np.array(D["dQ"]) / r / (M.RHO * vol)
    rr, zz = rz[:, 0] * RT, rz[:, 1] * RT
    sig = lambda x: 0.5 * (1 + np.tanh(x / (2 * e)))
    win = (sig(rr - disk["r_hub"]) * sig(disk["r_tip"] - rr) * sig(zz - (disk["z_disk"] - disk["thickness"] / 2))
           * sig(disk["z_disk"] + disk["thickness"] / 2 - zz))
    s = RT / UR ** 2
    fz = np.interp(rr, r, az, left=az[0], right=az[-1]) * win * s
    ft = np.interp(rr, r, at, left=at[0], right=at[-1]) * win * s
    return ft, fz


def sample(rng, n_far, n_near, n_disk, n_band, solids, wall_mid, wall_n):
    R1, Z1 = M.R_OUT / RT, M.Z_OUT / RT
    a = rng.uniform([0, 0], [R1, Z1], (n_far, 2))
    b = rng.uniform([0, 2.0], [3.0, 7.0], (n_near, 2))                  # around the cup top, the rotor and the wake
    c = rng.uniform([M.HUB_R / RT - 0.1, 3.8], [1.1, 4.2], (n_disk, 2))  # the disk
    k = rng.integers(0, len(wall_mid), n_band)
    e = wall_mid[k] + (0.3 * rng.uniform(0, 1, n_band) ** 2 + 1e-3)[:, None] * wall_n[k]
    p = np.concatenate([a, b, c, e])
    p[:, 0] = np.clip(p[:, 0], 1e-3, R1)
    keep = np.ones(len(p), bool)
    for s in solids:
        keep &= ~inside(p, s)
    m = 2000
    room = np.concatenate([np.stack([np.full(m, R1), rng.uniform(0, Z1, m)], 1),
                           np.stack([rng.uniform(1e-3, R1, m), np.full(m, Z1)], 1)])
    return p[keep], room


def wall_forces(net, mid, nrm, ds, part, nu, dev, names):
    """vertical force of the air on each part, N (full circle), from the traction (-p I + 2 nu S) . n."""
    rz = torch.tensor(mid, dtype=torch.float32, device=dev, requires_grad=True)
    o = net(rz)
    u, w, p = o[:, 0], o[:, 2], o[:, 3]
    gu = torch.autograd.grad(u.sum(), rz, retain_graph=True)[0]
    gw = torch.autograd.grad(w.sum(), rz)[0]
    n = torch.tensor(nrm, dtype=torch.float32, device=dev)
    # the body's outward normal is the fluid-side normal n; force on the body = integral of sigma . n
    tz = -p * n[:, 1] + nu * (gu[:, 1] + gw[:, 0]) * n[:, 0] + 2 * nu * gw[:, 1] * n[:, 1]
    fz = (tz.detach().cpu().numpy() * 2 * math.pi * mid[:, 0] * ds) * M.RHO * UR ** 2 * RT ** 2
    return {nm: float(fz[part == k].sum()) for k, nm in enumerate(names)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", choices=("fwd", "rev"), default="fwd")
    ap.add_argument("--nu-eff", type=float, default=1.5e-3, help="effective kinematic viscosity, m^2/s")
    ap.add_argument("--steps", type=int, default=20000)
    ap.add_argument("--width", type=int, default=256)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--n-far", type=int, default=20000)
    ap.add_argument("--n-near", type=int, default=30000)
    ap.add_argument("--n-disk", type=int, default=8000)
    ap.add_argument("--n-band", type=int, default=20000)
    ap.add_argument("--delta", type=float, default=0.05, help="length of the wall factor phi (in R)")
    ap.add_argument("--w-room", type=float, default=10.0)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--resample", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--edge", type=float, default=0.3e-3, help="smoothing of the disk's edges, m")
    ap.add_argument("--data", help="npz of points of the OpenFOAM run with the same equations (cfd/c3/export_points.py)")
    ap.add_argument("--n-data", type=int, default=0, help="number of pool points used as data (the first n)")
    ap.add_argument("--w-data", type=float, default=10.0)
    ap.add_argument("--no-pde", action="store_true", help="data only: drop the equations and the room term")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t_start = time.time()
    dev = torch.device("cuda")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.manual_seed(a.seed)
    rng = np.random.default_rng(a.seed)
    d = 1 if a.dir == "fwd" else -1
    nu = a.nu_eff / (UR * RT)
    disk = json.load(open(os.path.join(ROOT, "twin", "data", "cfd", "c3_disk.json")))

    walls, solids = outline()
    names = list(walls)
    mid, nrm, ds, part = segments(walls)
    T = lambda x: torch.tensor(x, dtype=torch.float32, device=dev)
    segA = np.concatenate([np.array(p[:-1]) for p in walls.values()]) / RT
    segB = np.concatenate([np.array(p[1:]) for p in walls.values()]) / RT
    net = Net(a.width, a.depth, (T(segA), T(segB)), a.delta).to(dev)
    pi = PhysicsInformer(["continuity", "momentum_r", "momentum_t", "momentum_z"], AxiNS(nu), "autodiff", device=dev)
    opt = torch.optim.Adam(net.parameters(), lr=a.lr)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: 0.01 ** (s / a.steps))
    disk_gf = d * disk["fwd" if d > 0 else "rev"]["T_gf"]
    scale = np.array([UR, UR, UR, M.RHO * UR ** 2])
    D = np.load(a.data) if a.data else None
    if D is not None and a.n_data:
        drz, dval = T(D["pool_rz"][:a.n_data] / RT), T(D["pool_v"][:a.n_data] / scale)
    else:
        drz = dval = None

    def balance():
        f = wall_forces(net, mid, nrm, ds, part, nu, dev, names)
        parts = {k: round(-f[k] / G, 4) for k in names if k != "table"}
        parts["disk"] = round(disk_gf, 4)
        return round(sum(parts.values()), 4), parts

    hist, t_train = [], time.time()
    for step in range(a.steps + 1):
        if step % a.resample == 0:
            pts, room = sample(rng, a.n_far, a.n_near, a.n_disk, a.n_band, solids, mid, nrm)
            ft, fz = disk_force(disk, d, pts, a.edge)
            pts, room, ft, fz = T(pts).requires_grad_(True), T(room), T(ft)[:, None], T(fz)[:, None]
        z0 = torch.zeros((), device=dev)
        l_data = ((net(drz) - dval) ** 2).mean() if drz is not None else z0
        if a.no_pde:
            loss = l_pde = l_room = z0
            loss = a.w_data * l_data
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step(); sched.step()
            if step % 1000 == 0:
                bal, parts = balance()
                h = dict(step=step, s=round(time.time() - t_train, 1), loss=float(loss), data=float(l_data), balance_gf=bal, parts_gf=parts)
                hist.append(h)
                print(json.dumps(h), flush=True)
            continue
        o = net(pts)
        res = pi.forward({"coordinates": pts, "x": pts[:, 0:1], "y": pts[:, 1:2], "u": o[:, 0:1], "v": o[:, 1:2], "w": o[:, 2:3], "p": o[:, 3:4], "ft": ft, "fz": fz})
        l_pde = sum((res[k] ** 2).mean() for k in ("continuity", "momentum_r", "momentum_t", "momentum_z"))
        l_room = (net(room)[:, 3] ** 2).mean()
        loss = l_pde + a.w_room * l_room + a.w_data * l_data
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step(); sched.step()
        if step % 1000 == 0:
            bal, parts = balance()
            h = dict(step=step, s=round(time.time() - t_train, 1), loss=float(loss), pde=float(l_pde), room=float(l_room),
                     data=float(l_data), balance_gf=bal, parts_gf=parts)
            hist.append(h)
            print(json.dumps(h), flush=True)
    torch.cuda.synchronize()
    t_train = time.time() - t_train

    bal, parts = balance()
    ev = lambda q: np.concatenate([net(T(q[i:i + 20000])).detach().cpu().numpy() for i in range(0, len(q), 20000)]) * scale
    gr, gz = np.meshgrid(np.linspace(1e-3, 0.12, 241), np.linspace(0.0, 0.25, 501))
    g = np.stack([gr.ravel(), gz.ravel()], 1) / RT
    fg = ev(g)
    for s in solids:
        fg[inside(g, s)] = np.nan
    lines = {}
    for dz in (0.01, 0.03, 0.06, -0.004):
        z = M.Z_ROT + dz
        q = np.stack([np.linspace(1e-4, 0.1, 201), np.full(201, z)], 1)
        lines["z%03d" % round(z * 1e3)] = np.concatenate([q, ev(q / RT)], 1)
    np.savez_compressed(os.path.join(a.out, "fields.npz"), r=gr, z=gz, ur=fg[:, 0].reshape(gr.shape), ut=fg[:, 1].reshape(gr.shape),
                        uz=fg[:, 2].reshape(gr.shape), p=fg[:, 3].reshape(gr.shape), **lines)
    test = {}
    if D is not None:                                      # error on OpenFOAM points the training never saw
        pr, ref = ev(D["test_rz"] / RT), D["test_v"]
        test = {k: round(float(np.linalg.norm(pr[:, j] - ref[:, j]) / np.linalg.norm(ref[:, j] - (ref[:, j].mean() if k == "p" else 0))), 4)
                for j, k in enumerate(("ur", "ut", "uz", "p"))}
        print("relative L2 error on unseen points:", json.dumps(test), flush=True)
    res = dict(task="C3", method="data-only-nn" if a.no_pde else "pinn-axi", n_data=a.n_data, test_rel_l2=test, dir=d, nu_eff=a.nu_eff, balance_gf=bal, parts_gf=parts,
               train_s=round(t_train, 1), wall_s=round(time.time() - t_start, 1), gpu=torch.cuda.get_device_name(0),
               n_params=sum(p.numel() for p in net.parameters()), args=vars(a), history=hist)
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print("balance %+.3f gf  %s, %.0f s training" % (bal, json.dumps(parts), t_train))


if __name__ == "__main__":
    main()
