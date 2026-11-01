#!/usr/bin/env python3
"""section_lbm.py — the stage-1 blade section with the lattice Boltzmann method on one GPU (XLB, Warp backend).

The GPU counterpart of the OpenFOAM section runs (cfd/section/make_section.py): same outline (geom.wall_loop), same
units (c = 1, U = 1, nu = 1/Re), same averaging window (cl, cd over t = 6-16 c/U). The section is rotated by -alpha
in a uniform stream along +x, so the force on it is directly drag (x) and lift (y).

  2D (default)  D2Q9 on a uniform grid of --n cells per chord
  --span 0.2    D3Q27 with the spanwise direction periodic over 0.2 c, like the LES

Collision KBC (entropic, stable at tau close to 1/2). Inlet: regularized velocity; top and bottom: equilibrium at the
free stream; outlet: extrapolation; section: halfway bounce-back (staircase), force by momentum exchange.
The domain is [--x0, --x1] x [-H, H] chord lengths around the mid-chord.

Usage (in the PhysicsNeMo container, XLB installed with pip --target $XLB_SITE, one GPU):
  python -I section_lbm.py --re 6000 --alpha 4 --t 0.03 --f 0.03 --n 256 --out OUT
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

# python -I ignores PYTHONPATH. XLB 0.3.1 and jax live in a pip --target dir ($XLB_SITE); XLB needs an older Warp than
# the image's (it uses wp.mat, gone in 1.16), installed in its own --target dir ($XLB_WARP) and loaded first.
if os.environ.get("XLB_WARP"):
    sys.path.insert(0, os.environ["XLB_WARP"])
if os.environ.get("XLB_SITE"):
    sys.path.append(os.environ["XLB_SITE"])
import warp as wp  # noqa: E402

import xlb  # noqa: E402
from xlb.compute_backend import ComputeBackend  # noqa: E402
from xlb.precision_policy import PrecisionPolicy  # noqa: E402
from xlb.grid import grid_factory  # noqa: E402
from xlb.operator.stepper import IncompressibleNavierStokesStepper  # noqa: E402
from xlb.operator.boundary_condition import (EquilibriumBC, ExtrapolationOutflowBC, HalfwayBounceBackBC,  # noqa: E402
                                             RegularizedBC)
from xlb.operator import Operator  # noqa: E402
from xlb.operator.force.momentum_transfer import MomentumTransfer  # noqa: E402
from xlb.helper.initializers import initialize_eq  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pinn"))
from geom import inside, wall_loop  # noqa: E402


class MomentumTransferND(MomentumTransfer):
    """XLB's MomentumTransfer kernel unchanged, except that the rest population is found for D2Q9 too (0.3.1 reads a
    third velocity component, which D2Q9 does not have)."""

    def _construct_warp(self):
        from typing import Any
        _c = self.velocity_set.c
        _opp_indices = self.velocity_set.opp_indices
        _f_vec = wp.vec(self.velocity_set.q, dtype=self.compute_dtype)
        _u_vec = wp.vec(self.velocity_set.d, dtype=self.compute_dtype)
        _missing_mask_vec = wp.vec(self.velocity_set.q, dtype=wp.uint8)
        _no_slip_id = self.no_slip_bc_instance.id
        _zero_index = wp.int32(int(np.where((np.asarray(self.velocity_set._c) == 0).all(0))[0][0]))

        @wp.kernel
        def kernel(
            f_0: wp.array4d(dtype=Any),
            f_1: wp.array4d(dtype=Any),
            bc_mask: wp.array4d(dtype=wp.uint8),
            missing_mask: wp.array4d(dtype=wp.bool),
            force: wp.array(dtype=Any),
        ):
            i, j, k = wp.tid()
            index = wp.vec3i(i, j, k)
            _boundary_id = bc_mask[0, index[0], index[1], index[2]]
            _missing_mask = _missing_mask_vec()
            for l in range(self.velocity_set.q):
                if missing_mask[l, index[0], index[1], index[2]]:
                    _missing_mask[l] = wp.uint8(1)
                else:
                    _missing_mask[l] = wp.uint8(0)
            is_edge = wp.bool(False)
            if _boundary_id == wp.uint8(_no_slip_id):
                if _missing_mask[_zero_index] == wp.uint8(0):
                    is_edge = wp.bool(True)
            m = _u_vec()
            if is_edge:
                f_post_collision = _f_vec()
                for l in range(self.velocity_set.q):
                    f_post_collision[l] = f_0[l, index[0], index[1], index[2]]
                timestep = 0
                f_post_stream = self.stream.warp_functional(f_0, index)
                f_post_stream = self.no_slip_bc_instance.warp_functional(index, timestep, _missing_mask, f_0, f_1, f_post_collision, f_post_stream)
                for d in range(self.velocity_set.d):
                    m[d] = self.compute_dtype(0.0)
                    for l in range(self.velocity_set.q):
                        if _missing_mask[l] == wp.uint8(1):
                            phi = f_post_collision[_opp_indices[l]] + f_post_stream[l]
                            if _c[d, _opp_indices[l]] == 1:
                                m[d] += phi
                            elif _c[d, _opp_indices[l]] == -1:
                                m[d] -= phi
            wp.atomic_add(force, 0, m)

        return None, kernel

    @Operator.register_backend(ComputeBackend.WARP)          # XLB looks implementations up by class name
    def warp_implementation(self, f_0, f_1, bc_mask, missing_mask):
        force = wp.zeros((1), dtype=wp.vec(self.velocity_set.d, dtype=self.compute_dtype))
        wp.launch(self.warp_kernel, inputs=[f_0, f_1, bc_mask, missing_mask, force], dim=f_0.shape[1:])
        return force.numpy()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--re", type=float, default=6000)
    ap.add_argument("--alpha", type=float, default=4)
    ap.add_argument("--t", type=float, default=0.03)
    ap.add_argument("--f", type=float, default=0.03)
    ap.add_argument("--n", type=int, default=256, help="cells per chord")
    ap.add_argument("--u", type=float, default=0.05, help="free-stream speed in lattice units (Mach = u * sqrt(3))")
    ap.add_argument("--x0", type=float, default=-3.0)
    ap.add_argument("--x1", type=float, default=7.0)
    ap.add_argument("--h", type=float, default=4.0)
    ap.add_argument("--span", type=float, default=0.0, help="0: 2D; > 0: 3D, periodic over this span (c)")
    ap.add_argument("--t-end", type=float, default=16.0)
    ap.add_argument("--t-avg", type=float, default=6.0)
    ap.add_argument("--samples-per-c", type=int, default=50, help="force samples per convective time")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t_start = time.time()

    three_d = a.span > 0
    N, U = a.n, a.u
    nu = U * N / a.re
    omega = 1.0 / (3.0 * nu + 0.5)
    nx, ny = int(round((a.x1 - a.x0) * N)), int(round(2 * a.h * N))
    nz = max(1, int(round(a.span * N))) if three_d else 1
    shape = (nx, ny, nz) if three_d else (nx, ny)

    backend, prec = ComputeBackend.WARP, PrecisionPolicy.FP32FP32
    vs = (xlb.velocity_set.D3Q27 if three_d else xlb.velocity_set.D2Q9)(precision_policy=prec, compute_backend=backend)
    xlb.init(velocity_set=vs, default_backend=backend, default_precision_policy=prec)
    grid = grid_factory(shape, compute_backend=backend)

    # the section, rotated nose-up by alpha against the stream (geom.wall_loop is at alpha 0, mid-chord at the origin)
    poly, _, _, _ = wall_loop(a.t, a.f)
    ar = math.radians(a.alpha)
    rot = np.array([[math.cos(ar), math.sin(ar)], [-math.sin(ar), math.cos(ar)]])
    poly = poly @ rot.T
    lo, hi = poly.min(0) - 2.0 / N, poly.max(0) + 2.0 / N
    i0, i1 = int(math.floor((lo[0] - a.x0) * N)), int(math.ceil((hi[0] - a.x0) * N))
    j0, j1 = int(math.floor((lo[1] + a.h) * N)), int(math.ceil((hi[1] + a.h) * N))
    I, J = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
    I, J = I.ravel(), J.ravel()
    pts = np.stack([a.x0 + (I + 0.5) / N, -a.h + (J + 0.5) / N], 1)
    solid = inside(pts, poly)
    si, sj = I[solid], J[solid]
    if three_d:
        k = np.arange(nz)
        body = [np.repeat(si, nz).tolist(), np.repeat(sj, nz).tolist(), np.tile(k, len(si)).tolist()]
    else:
        body = [si.tolist(), sj.tolist()]

    # faces by hand: XLB's bounding_box_indices names the z faces bottom/top in 3D, and remove_edges would also drop the
    # z = 0 and z = nz - 1 rows of the inlet; here the far field is y = 0 and y = ny - 1 and z is left periodic
    def face(ix, iy):
        axes = [np.arange(n)[s] for n, s in zip(shape, (ix, iy, slice(None)))]
        return [g.ravel().tolist() for g in np.meshgrid(*axes, indexing="ij")]
    inner_y = slice(1, ny - 1)
    u_in = (U, 0.0, 0.0) if three_d else (U, 0.0)
    far = [a_ + b_ for a_, b_ in zip(face(slice(None), 0), face(slice(None), ny - 1))]
    # XLB 0.3.1's RegularizedBC and ExtrapolationOutflowBC are off by 5-7 % in density from the first step in 3D (exact
    # or 5 % and settling in 2D) and the run blows up within ~0.4 c/U, even without the section; in 3D the inlet and
    # the outlet are an equilibrium at the free stream instead (the outlet is 6.5 c behind the section)
    inlet, outlet = face(0, inner_y), face(nx - 1, inner_y)
    if three_d:
        far = [x + y + z for x, y, z in zip(far, inlet, outlet)]
        bcs = [EquilibriumBC(rho=1.0, u=u_in, indices=far), HalfwayBounceBackBC(indices=body)]
    else:
        bcs = [RegularizedBC("velocity", prescribed_value=u_in, indices=inlet), EquilibriumBC(rho=1.0, u=u_in, indices=far),
               ExtrapolationOutflowBC(indices=outlet), HalfwayBounceBackBC(indices=body)]
    wall = bcs[-1]
    stepper = IncompressibleNavierStokesStepper(grid=grid, boundary_conditions=bcs, collision_type="KBC")

    def init_uniform(grid_, vset, pp, cb):
        rho = grid_.create_field(cardinality=1, fill_value=1.0, dtype=pp.compute_precision)
        u = np.zeros((vset.d,) + tuple(rho.shape[1:]), np.float32)
        u[0] = U
        u = wp.array(u, dtype=pp.compute_precision.wp_dtype)
        f = grid_.create_field(cardinality=vset.q, dtype=pp.store_precision)
        return initialize_eq(f, grid_, vset, pp, cb, rho=rho, u=u)

    f_0, f_1, bc_mask, missing_mask = stepper.prepare_fields(initializer=init_uniform)
    force = MomentumTransferND(wall)
    wp.synchronize()
    t_setup = time.time() - t_start

    steps_per_c = N / U
    n_steps = int(round(a.t_end * steps_per_c))
    every = max(1, int(round(steps_per_c / a.samples_per_c)))
    q = 0.5 * U * U * N * nz                       # dynamic pressure x chord x span, lattice units (rho = 1)
    hist = []
    print(json.dumps(dict(shape=shape, cells=int(np.prod(shape)), nu=nu, tau=1 / omega, steps=n_steps, solid=int(solid.sum()))),
          flush=True)
    t0 = time.time()
    for step in range(n_steps):
        f_0, f_1 = stepper(f_0, f_1, bc_mask, missing_mask, omega, step)
        f_0, f_1 = f_1, f_0
        if (step + 1) % every == 0:
            F = force(f_0, f_1, bc_mask, missing_mask)
            tc = (step + 1) / steps_per_c
            hist.append((round(tc, 4), float(F[0]) / q, float(F[1]) / q))
            if not np.isfinite(F).all():
                print(json.dumps(dict(diverged_at=tc)), flush=True)
                break
            if len(hist) % (a.samples_per_c * 2) == 0:
                print(json.dumps(dict(t=round(tc, 2), cd=round(hist[-1][1], 5), cl=round(hist[-1][2], 4),
                                      s=round(time.time() - t0, 1))), flush=True)
    wp.synchronize()
    t_solve = time.time() - t0

    h = np.array(hist)
    w = h[:, 0] >= a.t_avg
    ok = bool(np.isfinite(h[:, 1:]).all() and h[-1, 0] >= a.t_end - every / steps_per_c)
    res = dict(method="xlb-lbm-%s" % ("3d" if three_d else "2d"), re=a.re, alpha=a.alpha, t=a.t, f=a.f, n_per_chord=N,
               u_lattice=U, tau=round(1 / omega, 6), shape=list(shape), cells=int(np.prod(shape)), steps=len(hist) * every,
               completed=ok, cd=round(float(h[w, 1].mean()), 5) if w.any() else None,
               cl=round(float(h[w, 2].mean()), 4) if w.any() else None,
               sd=dict(cd=round(float(h[w, 1].std()), 5), cl=round(float(h[w, 2].std()), 4)) if w.any() else None,
               setup_s=round(t_setup, 1), solve_s=round(t_solve, 1), wall_s=round(time.time() - t_start, 1),
               mlups=round(np.prod(shape) * len(hist) * every / t_solve / 1e6, 1),
               gpu=wp.get_device().name, args=vars(a), history=hist)
    json.dump(res, open(os.path.join(a.out, "result.json"), "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("cl", "cd", "sd", "solve_s", "mlups", "completed")}), flush=True)


if __name__ == "__main__":
    main()
