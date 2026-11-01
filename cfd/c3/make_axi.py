#!/usr/bin/env python3
"""make_axi.py — task C3 in OpenFOAM: the rig as an axisymmetric wedge, the rotor as an actuator disk.

The classical counterpart of the C3 PINN (cfd/c3/pinn_axi.py), on the same simplified geometry:
  - axisymmetric about the cup axis (z up, table at z = 0), a 5 deg wedge, open room at r = 0.30 m and z = 0.48 m
    (the stage-3 box is 0.6 x 0.6 x 0.48 m);
  - cup (frustum with the 8.5 mm recess), motor, hub as in cfd/geometry/make_geometry.py (NOMINAL);
  - the scale as a disk of the same top area (r 0.107 m, the box is 0.24 x 0.15 m and off-centre); no breadboard;
  - the hub as a still wall (it turns in the stage-3 URANS; kept still so the PINN has the same problem);
  - the rotor as rings of body force (thrust and swirl) over 4 mm around the blade plane, from twin/data/cfd/c3_disk.json
    (cfd/c3/disk.py: BEMT shape, totals of the stage-3 URANS blade force and torque).
Solids are cut out of a graded block mesh (staircase on the cup's cone and the hub cap) by topoSet + subsetMesh,
one patch per part, so the forces come per part like the stage-3 balance.

  --turb sst           simpleFoam, k-omega SST (as the stage-3 URANS)
  --turb nu --nu-eff X laminar simpleFoam with a constant effective viscosity (the PINN's equations)

Usage:  python3 cfd/c3/make_axi.py --dir fwd --turb sst --out CASE [--refine 1]
        then in CASE: ./Allrun   (blockMesh, topoSet/subsetMesh per part, disk zones, simpleFoam)
"""
import argparse
import json
import math
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
WEDGE = 5.0                                    # deg
RHO = 1.2
NU = 1.52e-5
RPM = 3067
# geometry (m), cfd/geometry/make_geometry.py NOMINAL
CUP_Z0, CUP_Z1, CUP_R0, CUP_R1, RECESS, CUP_WALL = 0.0254, 0.1174, 0.0378, 0.0248, 8.5e-3, 1.0e-3
Z_ROT = CUP_Z1 + 0.010
MOTOR_R, BOSS_R, MOTOR_TOP, BOSS_H = 0.0102, 0.005, Z_ROT - 9.0e-3, 0.8e-3
HUB_R, HUB_B, HUB_C, HUB_CAP = 0.345 * 0.032, Z_ROT - 7.5e-3, Z_ROT + 1.5e-3, 5.0e-3
SCALE_R = math.sqrt(0.240 * 0.150 / math.pi)
R_OUT, Z_OUT = 0.30, 0.48
FLOOR = CUP_Z1 - RECESS
SLOPE = (CUP_R0 - CUP_R1) / (CUP_Z1 - CUP_Z0)


def grid(breaks, refine):
    """breaks: [(x, cell size at x)]; each interval graded geometrically from one size to the next."""
    iv = []
    for (x0, s0), (x1, s1) in zip(breaks[:-1], breaks[1:]):
        s0, s1 = s0 / refine, s1 / refine
        n = max(1, int(round(2 * (x1 - x0) / (s0 + s1))))
        iv.append((x0, x1, n, s1 / s0 if n > 1 else 1.0))
    return iv


def block_mesh(refine):
    rb = [(0, .5e-3), (MOTOR_R, .5e-3), (HUB_R, .5e-3), (CUP_R1 - CUP_WALL, .5e-3), (CUP_R1, .5e-3), (0.032, .5e-3),
          (CUP_R0, .6e-3), (0.06, 1.5e-3), (SCALE_R, 3e-3), (0.15, 4e-3), (R_OUT, 8e-3)]
    zb = [(0, 1.5e-3), (CUP_Z0, 1e-3), (0.067, 3e-3), (FLOOR, .5e-3), (CUP_Z1, .5e-3), (MOTOR_TOP, .5e-3),
          (HUB_B, .5e-3), (Z_ROT - 2e-3, .4e-3), (HUB_C, .4e-3), (Z_ROT + 2e-3, .4e-3), (HUB_C + HUB_CAP, .5e-3),
          (0.2, 3e-3), (Z_OUT, 8e-3)]
    ri, zi = grid(rb, refine), grid(zb, refine)
    rs = [x[0] for x in ri] + [ri[-1][1]]
    zs = [x[0] for x in zi] + [zi[-1][1]]
    h = math.radians(WEDGE / 2)
    verts, idx = [], {}
    for j, z in enumerate(zs):
        for i, r in enumerate(rs):
            for side, s in (("f", -1), ("b", 1)):
                if r == 0 and side == "b":
                    idx[i, j, side] = idx[i, j, "f"]            # on the axis the two sides are one point
                    continue
                idx[i, j, side] = len(verts)
                verts.append((r * math.cos(h), s * r * math.sin(h), z))
    blocks, front, back, table, room = [], [], [], [], []
    for j, (_, _, nz, gz) in enumerate(zi):
        for i, (_, _, nr, gr) in enumerate(ri):
            v = [idx[i, j, "f"], idx[i + 1, j, "f"], idx[i + 1, j, "b"], idx[i, j, "b"],
                 idx[i, j + 1, "f"], idx[i + 1, j + 1, "f"], idx[i + 1, j + 1, "b"], idx[i, j + 1, "b"]]
            blocks.append("hex (%s) (%d 1 %d) simpleGrading (%.5g 1 %.5g)" % (" ".join(map(str, v)), nr, nz, gr, gz))
            front.append((v[0], v[1], v[5], v[4]))
            back.append((v[3], v[7], v[6], v[2]))
            if j == 0:
                table.append((v[0], v[3], v[2], v[1]))
            if j == len(zi) - 1:
                room.append((v[4], v[5], v[6], v[7]))
            if i == len(ri) - 1:
                room.append((v[1], v[2], v[6], v[5]))
    f = lambda fs: " ".join("(%s)" % " ".join(map(str, x)) for x in fs)
    ncell = sum(x[2] for x in ri) * sum(x[2] for x in zi)
    return """FoamFile { version 2.0; format ascii; class dictionary; object blockMeshDict; }
scale 1;
vertices (
%s
);
blocks (
%s
);
boundary (
    front { type wedge; faces (%s); }
    back  { type wedge; faces (%s); }
    table { type wall; faces (%s); }
    room  { type patch; faces (%s); }
    scale { type wall; faces (); }
    cup   { type wall; faces (); }
    motor { type wall; faces (); }
    hub   { type wall; faces (); }
);
""" % ("\n".join("(%.9g %.9g %.9g)" % p for p in verts), "\n".join(blocks), f(front), f(back), f(table), f(room)), ncell


def cyl(z0, z1, r, r_in=0.0):
    return "{ source cylinderToCell; p1 (0 0 %.6g); p2 (0 0 %.6g); radius %.6g; innerRadius %.6g; }" % (z0, z1, r, r_in)


def cone(z0, r0, z1, r1):
    return ("{ source searchableSurfaceToCell; surfaceType searchableCone; surfaceName cone; point1 (0 0 %.6g); "
            "radius1 %.6g; innerRadius1 0; point2 (0 0 %.6g); radius2 %.6g; innerRadius2 0; }" % (z0, r0, z1, r1))


def parts():
    """(patch, [(action, source)]) for the solids, cut out in this order."""
    cap = [cyl(HUB_C + HUB_CAP * k / 5, HUB_C + HUB_CAP * (k + 1) / 5, HUB_R * math.sqrt(1 - ((k + 0.5) / 5) ** 2))
           for k in range(5)]
    return [
        ("scale", [("add", cyl(-1, CUP_Z0, SCALE_R))]),
        ("cup", [("add", cone(CUP_Z0, CUP_R0, CUP_Z1, CUP_R1)),
                 ("subtract", cone(FLOOR, CUP_R1 - CUP_WALL + SLOPE * RECESS, CUP_Z1 + 1e-3, CUP_R1 - CUP_WALL - SLOPE * 1e-3))]),
        ("motor", [("add", cyl(FLOOR - 1e-3, MOTOR_TOP, MOTOR_R)), ("add", cyl(MOTOR_TOP - 1e-4, MOTOR_TOP + BOSS_H, BOSS_R))]),
        ("hub", [("add", cyl(HUB_B, HUB_C, HUB_R))] + [("add", c) for c in cap]),
    ]


def topo_set(name, actions):
    lines = ["    { name %s; type cellSet; action new; source boxToCell; box (-1 -1 -1) (1 1 1); }" % ("keep_" + name),
             "    { name %s; type cellSet; action new; source boxToCell; box (2 2 2) (3 3 3); }" % name]
    for act, src in actions:
        lines.append("    { name %s; type cellSet; action %s; %s }" % (name, act, src[1:-1]))
    lines.append("    { name keep_%s; type cellSet; action subtract; source cellToCell; sets (%s); }" % (name, name))
    return "FoamFile { version 2.0; format ascii; class dictionary; object topoSetDict; }\nactions (\n%s\n);\n" % "\n".join(lines)


def disk_zones(disk):
    z0, z1 = disk["z_disk"] - disk["thickness"] / 2, disk["z_disk"] + disk["thickness"] / 2
    lines = []
    for k, g in enumerate(disk["fwd"]["rings"]):
        lines.append("    { name ring%d; type cellSet; action new; %s }" % (k, cyl(z0, z1, g["r1"], g["r0"])[1:-1]))
        lines.append("    { name ring%d; type cellZoneSet; action new; source setToCellZone; set ring%d; }" % (k, k))
    return "FoamFile { version 2.0; format ascii; class dictionary; object topoSetDict; }\nactions (\n%s\n);\n" % "\n".join(lines)


def fv_options(disk, d):
    """Body force on the air = minus the force on the blades: thrust along +z d (air pushed the way the rotor blows),
    swirl along the rotation (+theta d; on the wedge's mid-plane theta is +y). Kinematic (divided by rho), total per
    ring in the 5 deg wedge."""
    frac = WEDGE / 360.0
    out = []
    for k, g in enumerate(disk["fwd" if d > 0 else "rev"]["rings"]):
        rm = 0.5 * (g["r0"] + g["r1"])
        fz, ft = d * g["T"] * frac / RHO, d * g["Q"] / rm * frac / RHO
        out.append("ring%d { type vectorSemiImplicitSource; selectionMode cellZone; cellZone ring%d; volumeMode absolute;\n"
                   "    sources { U { explicit (0 %.6e %.6e); implicit 0; } } }" % (k, k, ft, fz))
    return "FoamFile { version 2.0; format ascii; class dictionary; object fvOptions; }\n" + "\n".join(out) + "\n"


def field(name, cls, dim, internal, bcs):
    b = "\n".join("    %s { %s }" % kv for kv in bcs)
    return ("FoamFile { version 2.0; format ascii; class %s; object %s; }\ndimensions %s;\ninternalField uniform %s;\n"
            "boundaryField {\n    \"(front|back)\" { type wedge; }\n%s\n}\n" % (cls, name, dim, internal, b))


def write_case(out, d, turb, nu_eff, refine, iters):
    disk = json.load(open(os.path.join(ROOT, "twin", "data", "cfd", "c3_disk.json")))
    for sub in ("0", "constant", "system"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
    w = lambda p, s: open(os.path.join(out, p), "w").write(s)
    bm, ncell = block_mesh(refine)
    w("system/blockMeshDict", bm)
    for name, acts in parts():
        w("system/topoSetDict.%s" % name, topo_set(name, acts))
    w("system/topoSetDict.disk", disk_zones(disk))
    w("constant/fvOptions", fv_options(disk, d))
    w("0/U", field("U", "volVectorField", "[0 1 -1 0 0 0 0]", "(0 0 0)", [
        ("\"(table|scale|cup|motor|hub)\"", "type noSlip;"), ("room", "type pressureInletOutletVelocity; value uniform (0 0 0);")]))
    w("0/p", field("p", "volScalarField", "[0 2 -2 0 0 0 0]", "0", [
        ("\"(table|scale|cup|motor|hub)\"", "type zeroGradient;"),
        ("room", "type totalPressure; p0 uniform 0; value uniform 0;")]))
    sw = "\"(table|scale|cup|motor|hub)\""
    if turb == "sst":
        w("0/k", field("k", "volScalarField", "[0 2 -2 0 0 0 0]", "1.5e-4", [
            (sw, "type fixedValue; value uniform 1e-12;"), ("room", "type inletOutlet; inletValue uniform 1.5e-4; value uniform 1.5e-4;")]))
        w("0/omega", field("omega", "volScalarField", "[0 0 -1 0 0 0 0]", "10", [
            (sw, "type omegaWallFunction; value uniform 10;"), ("room", "type inletOutlet; inletValue uniform 10; value uniform 10;")]))
        w("0/nut", field("nut", "volScalarField", "[0 2 -1 0 0 0 0]", "0", [
            (sw, "type nutLowReWallFunction; value uniform 0;"), ("room", "type calculated; value uniform 0;")]))
        w("constant/turbulenceProperties", "FoamFile { version 2.0; format ascii; class dictionary; object turbulenceProperties; }\n"
          "simulationType RAS;\nRAS { RASModel kOmegaSST; turbulence on; printCoeffs on; }\n")
        nu = NU
    else:
        w("constant/turbulenceProperties", "FoamFile { version 2.0; format ascii; class dictionary; object turbulenceProperties; }\n"
          "simulationType laminar;\n")
        nu = nu_eff
    w("constant/transportProperties", "FoamFile { version 2.0; format ascii; class dictionary; object transportProperties; }\n"
      "transportModel Newtonian;\nnu %.6g;\n" % nu)
    fo = "\n".join("    f_%s { type forces; libs (forces); patches (%s); rho rhoInf; rhoInf %.2f; CofR (0 0 0); writeControl timeStep; writeInterval 10; }"
                   % (p, p, RHO) for p in ("table", "scale", "cup", "motor", "hub"))
    probes = ("    lines { type sets; libs (sampling); writeControl writeTime; interpolationScheme cellPoint; setFormat raw; fields (U p);\n"
              "      sets ( %s ); }" % " ".join(
                  "z%03d { type uniform; axis distance; start (0 0 %.4f); end (0.1 0 %.4f); nPoints 201; }" % (round(z * 1e3), z, z)
                  for z in (Z_ROT + 0.01, Z_ROT + 0.03, Z_ROT + 0.06, Z_ROT - 0.004)))
    w("system/controlDict", """FoamFile { version 2.0; format ascii; class dictionary; object controlDict; }
application simpleFoam;
startFrom latestTime; startTime 0; stopAt endTime; endTime %d; deltaT 1;
writeControl timeStep; writeInterval %d; purgeWrite 2; writeFormat ascii; writePrecision 8; runTimeModifiable true;
functions {
%s
%s
}
""" % (iters, iters // 4, fo, probes))
    turb_div = "    div(phi,k) bounded Gauss linearUpwind grad(k);\n    div(phi,omega) bounded Gauss linearUpwind grad(omega);\n"
    w("system/fvSchemes", """FoamFile { version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes { default steadyState; }
gradSchemes { default cellLimited Gauss linear 1; }
divSchemes { default none;
    div(phi,U) bounded Gauss linearUpwindV grad(U);
%s    div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes { default Gauss linear limited 0.5; }
interpolationSchemes { default linear; }
snGradSchemes { default limited 0.5; }
wallDist { method meshWave; }
""" % turb_div)
    w("system/fvSolution", """FoamFile { version 2.0; format ascii; class dictionary; object fvSolution; }
solvers {
    p { solver GAMG; smoother GaussSeidel; tolerance 1e-8; relTol 0.05; }
    "(U|k|omega)" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-9; relTol 0.1; }
}
SIMPLE { nNonOrthogonalCorrectors 0; consistent yes; residualControl { p 1e-6; U 1e-7; "(k|omega)" 1e-7; } }
relaxationFactors { equations { U 0.7; ".*" 0.5; } fields { p 0.5; } }
""")
    w("Allrun", """#!/bin/bash
set -e
cd "$(dirname "$0")"
blockMesh > log.blockMesh 2>&1
for part in scale cup motor hub; do
    topoSet -dict system/topoSetDict.$part > log.topoSet.$part 2>&1
    subsetMesh keep_$part -patch $part -overwrite > log.subsetMesh.$part 2>&1
done
rm -rf constant/polyMesh/sets 0/polyMesh 2>/dev/null || true
topoSet -dict system/topoSetDict.disk > log.topoSet.disk 2>&1
checkMesh > log.checkMesh 2>&1 || true
simpleFoam > log.simpleFoam 2>&1
""")
    os.chmod(os.path.join(out, "Allrun"), 0o755)
    json.dump(dict(dir=d, turb=turb, nu_eff=nu_eff, refine=refine, iters=iters, wedge_deg=WEDGE, block_cells=ncell,
                   scale_r=SCALE_R, disk_T_gf=disk["fwd" if d > 0 else "rev"]["T_gf"]),
              open(os.path.join(out, "c3_case.json"), "w"), indent=1)
    return ncell


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", choices=("fwd", "rev"), default="fwd")
    ap.add_argument("--turb", choices=("sst", "nu"), default="sst")
    ap.add_argument("--nu-eff", type=float, default=1.5e-3, help="m^2/s, with --turb nu")
    ap.add_argument("--refine", type=float, default=1.0)
    ap.add_argument("--iters", type=int, default=4000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    n = write_case(a.out, 1 if a.dir == "fwd" else -1, a.turb, a.nu_eff, a.refine, a.iters)
    print("%s: %d block cells before the cut" % (a.out, n))


if __name__ == "__main__":
    main()
