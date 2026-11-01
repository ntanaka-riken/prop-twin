#!/usr/bin/env python3
"""cfd_cost.py — the compute cost of every CFD run, for the comparison with PhysicsNeMo (docs/PHYSICSNEMO_PLAN.md).

Run on rikyu (stdlib only), reading the OpenFOAM logs under $W/runs:
  per case: mesh cells, MPI ranks, wall seconds of meshing and of the solver (summed over restarts), finished or not,
  and core-hours = ranks x wall / 3600.  Nodes are 144-core GB200 nodes; the 4 GPUs per node sit idle in the CFD
  but are allocated, so node-hours are reported too (a section case uses ranks/144 of a node).
With --sacct it also lists the Slurm jobs named cfd-* (job id, name, state, elapsed, nodes, cpus, gpus); user and
account columns are left out on purpose.

Usage (on rikyu):  python3 $W/cfd/bench/cfd_cost.py $W/runs [--sacct] > cost.json
       locally:    ssh rikyu 'python3 $W/cfd/bench/cfd_cost.py $W/runs --sacct' > twin/data/cfd/cost.json
"""
import glob
import json
import os
import re
import subprocess
import sys

CORES_PER_NODE = 144


def last_clock(path):
    """Final ClockTime of an OpenFOAM log (seconds), or None."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 20000))
            tail = f.read().decode(errors="replace")
    except OSError:
        return None
    m = re.findall(r"(?:ClockTime|Finished meshing in) = ([0-9.]+) s", tail)
    return float(m[-1]) if m else None


def last_time(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 20000))
            tail = f.read().decode(errors="replace")
    except OSError:
        return None
    m = re.findall(r"^Time = ([0-9.eE+-]+)", tail, re.M)
    return float(m[-1]) if m else None


def cells(case):
    for name in ("log.checkMesh", "log.checkMesh.final"):
        p = os.path.join(case, name)
        if os.path.exists(p):
            m = re.search(r"^\s*cells:\s+(\d+)", open(p, errors="replace").read(), re.M)
            if m:
                return int(m.group(1))
    return None


def ranks(case, log=None):
    n = len(glob.glob(os.path.join(case, "processor*")))
    if not n and log and os.path.exists(os.path.join(case, log)):    # processor dirs gone after reconstructParMesh (the PMIx noise pushes the header far down)
        with open(os.path.join(case, log), errors="replace") as f:
            m = re.search(r"^nProcs\s*:\s*(\d+)", f.read(), re.M)
        n = int(m.group(1)) if m else 0
    return n or 1


def solver_wall(case, solver):
    logs = glob.glob(os.path.join(case, "log." + solver)) + glob.glob(os.path.join(case, "log.%s.*" % solver))
    return sum(t for t in (last_clock(p) for p in logs) if t), last_time(os.path.join(case, "log." + solver))


def row(stage, case, solver, mesh_logs=(), mesh_from=None, done=None):
    np_ = ranks(case, "log." + solver)
    wall, t = solver_wall(case, solver)
    mesh_dir = mesh_from or case
    mesh_wall = sum(t for t in (last_clock(os.path.join(mesh_dir, l)) for l in mesh_logs) if t)
    r = dict(stage=stage, case=os.path.basename(case.rstrip("/")), cells=cells(mesh_dir), ranks=np_,
             solver_wall_s=round(wall), mesh_wall_s=round(mesh_wall), sim_time=t,
             core_h=round(np_ * wall / 3600, 2), node_h=round(np_ * wall / 3600 / CORES_PER_NODE, 3))
    if done is not None:
        r["done"] = done
    return r


def main():
    runs = sys.argv[1]
    out = []
    for c in sorted(glob.glob(os.path.join(runs, "sections", "re*"))):
        out.append(row("1-section-les", c, "pimpleFoam", ("log.blockMesh",), done=os.path.exists(os.path.join(c, "done"))))
    for m in sorted(glob.glob(os.path.join(runs, "mrf-mesh-L*"))):
        out.append(row("2-mrf-mesh", m, "snappyHexMesh"))
    mesh_of = {}                                       # run name -> mesh, from the run lists (name rpm dir model mesh)
    for lst in glob.glob(os.path.join(runs, "..", "cfd", "cases", "mrf_runs*.txt")):
        for line in open(lst):
            if line.split():
                mesh_of[line.split()[0]] = line.split()[4]
    for c in sorted(glob.glob(os.path.join(runs, "mrf", "*"))):
        m = mesh_of.get(os.path.basename(c))
        r = row("2-mrf-rans", c, "simpleFoam", mesh_from=m and os.path.join(runs, "mrf-mesh-L" + m))
        r["mesh"] = m
        out.append(r)
    for c in sorted(glob.glob(os.path.join(runs, "ami", "*"))):
        out.append(row("3-ami-" + ("les" if "_les_" in c else "urans"), c, "pimpleFoam",
                       ("log.blockMesh", "log.snappyHexMesh", "log.createPatch")))
    res = dict(source="cfd/bench/cfd_cost.py (OpenFOAM v2512 on rikyu GB200 nodes, 144 Grace cores; CFD uses CPUs only)",
               cores_per_node=CORES_PER_NODE, runs=out)
    if "--sacct" in sys.argv:
        q = subprocess.run(["sacct", "-X", "-n", "--parsable2", "-S", "2026-10-01", "--name",
                            "cfd-sec,cfd-mrf,cfd-mrfmesh,cfd-ami,cfd-mesh,cfd-pnemo",
                            "-o", "JobID,JobName,State,ElapsedRaw,NNodes,NCPUS,AllocTRES"],
                           capture_output=True, text=True).stdout
        jobs = []
        for line in q.splitlines():
            jid, name, state, el, nn, nc, tres = line.split("|")
            g = re.search(r"gres/gpu=(\d+)", tres)
            jobs.append(dict(job=jid, name=name, state=state, elapsed_s=int(el or 0), nodes=int(nn), cpus=int(nc),
                             gpus=int(g.group(1)) if g else 0, node_h=round(int(nn) * int(el or 0) / 3600, 2)))
        res["slurm_jobs"] = jobs
    json.dump(res, sys.stdout, indent=0)


if __name__ == "__main__":
    main()
