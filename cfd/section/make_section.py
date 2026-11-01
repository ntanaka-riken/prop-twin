#!/usr/bin/env python3
"""make_section.py — OpenFOAM case of one blade section for the stage-1 2.5D LES polars (standard library only).

Section: the make_geometry.py blade cut across the chord — a plate of constant thickness t with round leading
and trailing edges (stadium), its mid-line bent into a parabola of height f:  y_m = f (1 - (2x)^2).
Units are chord lengths and the free-stream speed (c = 1, U = 1, nu = 1/Re). The leading edge is at x = -0.5.
f > 0 bulges to the suction side at positive alpha, i.e. helps lift (the sign of `camber` in bemt.py and
make_geometry.py). The parabola is symmetric, so the polar of -f is that of +f mirrored: cl(-f, a) = -cl(f, -a),
and one camber sign is enough. Seen from the forward-turning rotor the IMG_5778 spoon bulge is f < 0; turning in
reverse, the same blade meets the flow with the edges swapped and its pressure side as suction side, i.e. f > 0.

Mesh: 8 blockMesh blocks — a body-fitted ring of thickness 0.5 c (grid lines normal to the wall, first cell
6e-4 c) and an outer ring to a circle of radius 15 c; spanwise periodic over 0.2 c (16 cells), about 0.6 M cells.
Flow: pimpleFoam, LES WALE, free-stream boundary at angle alpha, 16 convective times; forceCoeffs every step.

Usage:
  python3 make_section.py --re 15000 --alpha 8 --t 0.03 --f 0 --out <case dir> [--np 36]
  python3 make_section.py --list > cases.txt       # name re alpha t f, one case per line
"""
import argparse
import math
import os

HEAD = "FoamFile { version 2.0; format ascii; class %s; object %s; }\n"
D_IN, R_OUT, SPAN, NZ = 0.5, 15.0, 0.2, 16      # body-fitted ring, outer circle, span (all in c)
NU_SIDE, N_IN, N_OUT, DY1 = 120, 80, 60, 6e-4    # cells along each face, radial in/out, first wall cell
SIDE_GRADING = "((0.25 0.4 8) (0.5 0.2 1) (0.25 0.4 0.125))"   # clustered to both edges


def midline(s, t, f):
    """point and unit normal of the mid-line at x = s (s between the cap centres)."""
    y, dy = f * (1 - 4 * s * s), -8 * f * s
    n = math.hypot(1, dy)
    return (s, y), (-dy / n, 1 / n)


def surface(t, f, off, npts=240):
    """the closed curve at distance t/2 + off from the mid-line, clockwise from the upper leading-edge junction.
    Returns the 4 block edges (upper, trailing, lower, leading) as point lists sharing their end points. The
    junctions are the 45-degree points of the round edges, so that the edge blocks are not flat (blockMesh checks
    the blocks with straight sides)."""
    a, h = 0.5 - t / 2, t / 2 + off
    xs = [-a + 2 * a * i / npts for i in range(npts + 1)]
    up = [(p[0] + h * n[0], p[1] + h * n[1]) for p, n in map(lambda x: midline(x, t, f), xs)]
    lo = [(p[0] - h * n[0], p[1] - h * n[1]) for p, n in map(lambda x: midline(x, t, f), xs[::-1])]

    def cap(x, sign):
        (px, py), (nx, ny) = midline(x, t, f)
        th0 = math.atan2(ny, nx)
        m = 60
        pts = []
        for i in range(m + 1):      # clockwise half turn from +normal to -normal (trailing) or -normal to +normal
            th = th0 - math.pi * i / m if sign > 0 else th0 + math.pi - math.pi * i / m
            pts.append((px + h * math.cos(th), py + h * math.sin(th)))
        return pts
    te, le = cap(a, +1), cap(-a, -1)
    loop = up + te[1:] + lo[1:] + le[1:]                # closed: the last point is up[0]
    N, m = npts, len(te) - 1
    jb, jc, jd, ja = N + m // 4, N + 3 * m // 4, 2 * N + m + m // 4, 2 * N + m + 3 * m // 4
    return loop[ja:] + loop[1:jb + 1], loop[jb:jc + 1], loop[jc:jd + 1], loop[jd:ja + 1]


def solve_ratio(first, length, n):
    """per-cell growth r with first*(r^n - 1)/(r - 1) = length."""
    lo, hi = 1.0 + 1e-9, 2.0
    for _ in range(200):
        r = 0.5 * (lo + hi)
        if first * (r ** n - 1) / (r - 1) > length:
            hi = r
        else:
            lo = r
    return r


def block_mesh(t, f, nz=NZ, side="cyclic"):
    s0, s1 = surface(t, f, 0.0), surface(t, f, D_IN)
    corners0 = [s0[k][0] for k in range(4)]
    corners1 = [s1[k][0] for k in range(4)]
    ang = [math.atan2(p[1], p[0]) for p in corners1]
    corners2 = [(R_OUT * math.cos(q), R_OUT * math.sin(q)) for q in ang]
    r_in = solve_ratio(DY1, D_IN, N_IN)
    last_in = DY1 * r_in ** (N_IN - 1)
    r_out = solve_ratio(last_in * r_in, R_OUT - D_IN - 0.5, N_OUT)
    E_in, E_out = r_in ** (N_IN - 1), r_out ** (N_OUT - 1)
    n_cap = max(16, round(math.pi * t / 4 / 1.5e-3))   # a quarter turn of the round edge
    ncell = [NU_SIDE, n_cap, NU_SIDE, n_cap]
    grad_t = [SIDE_GRADING, "1", SIDE_GRADING, "1"]

    V = []
    for z in (0.0, SPAN):
        V += [(x, y, z) for x, y in corners0 + corners1 + corners2]
    o = 12                                             # offset of the z = SPAN plane
    blocks, edges = [], []
    for k in range(4):
        i, j = k, (k + 1) % 4
        for ring, (a, b, E, nr) in enumerate(((0, 4, E_in, N_IN), (4, 8, E_out, N_OUT))):
            g = grad_t[k]
            blocks.append("hex (%d %d %d %d %d %d %d %d) (%d %d %d) edgeGrading (%s %s %s %s  %g %g %g %g  1 1 1 1)"
                          % (a + i, a + j, b + j, b + i, a + i + o, a + j + o, b + j + o, b + i + o,
                             ncell[k], nr, nz, g, g, g, g, E, E, E, E))
        for z, zo in ((0.0, 0), (SPAN, o)):
            for curve, base in ((s0, 0), (s1, 4)):
                pts = curve[k][1:-1]
                edges.append("polyLine %d %d (%s)" % (base + i + zo, base + j + zo,
                                                      " ".join("(%.8f %.8f %g)" % (x, y, z) for x, y in pts)))
            qm = 0.5 * (ang[i] + ang[j] + (2 * math.pi if ang[j] > ang[i] else 0))
            edges.append("arc %d %d (%.8f %.8f %g)" % (8 + i + zo, 8 + j + zo, R_OUT * math.cos(qm), R_OUT * math.sin(qm), z))
    wall = " ".join("(%d %d %d %d)" % (i, (i + 1) % 4, (i + 1) % 4 + o, i + o) for i in range(4))
    far = " ".join("(%d %d %d %d)" % (8 + (i + 1) % 4, 8 + i, 8 + i + o, 8 + (i + 1) % 4 + o) for i in range(4))
    front = " ".join("(%d %d %d %d)" % (a + i, b + i, b + (i + 1) % 4, a + (i + 1) % 4) for i in range(4) for a, b in ((0, 4), (4, 8)))
    back = " ".join("(%d %d %d %d)" % (a + i + o, a + (i + 1) % 4 + o, b + (i + 1) % 4 + o, b + i + o) for i in range(4) for a, b in ((0, 4), (4, 8)))
    txt = HEAD % ("dictionary", "blockMeshDict")
    txt += "// t/c %g, f/c %g: wall ring %g c (%d cells, first %g c, ratio %.4f), outer ring to r %g c (%d cells, ratio %.4f)\n" % (
        t, f, D_IN, N_IN, DY1, r_in, R_OUT, N_OUT, r_out)
    txt += "convertToMeters 1;\nvertices (\n%s\n);\n" % "\n".join("(%.8f %.8f %g)" % v for v in V)
    txt += "blocks (\n%s\n);\nedges (\n%s\n);\n" % ("\n".join(blocks), "\n".join(edges))
    pair = ("type cyclic; neighbourPatch back;", "type cyclic; neighbourPatch front;") if side == "cyclic" else ("type empty;",) * 2
    txt += ("boundary (\n section { type wall; faces (%s); }\n farfield { type patch; faces (%s); }\n"
            " front { %s faces (%s); }\n back { %s faces (%s); }\n);\n"
            % (wall, far, pair[0], front, pair[1], back))
    return txt, sum(ncell) * (N_IN + N_OUT) * nz


def write_case(out, re, alpha, t, f, np_, steady=False, transient2d=False):
    ca, sa = math.cos(math.radians(alpha)), math.sin(math.radians(alpha))
    U = "(%.10f %.10f 0)" % (ca, sa)
    files = {}
    bm, ncells = block_mesh(t, f, *((1, "empty") if steady or transient2d else ()))
    files["system/blockMeshDict"] = bm
    files["system/controlDict"] = HEAD % ("dictionary", "controlDict") + """// section Re %g, alpha %g deg, t/c %g, f/c %g (%d cells)
application pimpleFoam; startFrom latestTime; startTime 0; stopAt endTime; endTime 16;
deltaT 1e-4; adjustTimeStep yes; maxCo 0.9; maxDeltaT 0.01;
writeControl runTime; writeInterval 2; purgeWrite 1; writeFormat binary; writePrecision 8; timePrecision 6; runTimeModifiable true;
functions
{
    coeffs
    {
        type forceCoeffs; libs (forces); patches (section); rho rhoInf; rhoInf 1; CofR (-0.25 0 0);
        liftDir (%.10f %.10f 0); dragDir (%.10f %.10f 0); pitchAxis (0 0 1);
        magUInf 1; lRef 1; Aref %g; writeControl timeStep; writeInterval 1; log false;
    }
    average
    {
        type fieldAverage; libs (fieldFunctionObjects); timeStart 6; writeControl writeTime;
        fields ( U { mean on; prime2Mean on; base time; } p { mean on; prime2Mean on; base time; } );
    }
    wallShear { type wallShearStress; libs (fieldFunctionObjects); patches (section); writeControl writeTime; }
}
""" % (re, alpha, t, f, ncells, -sa, ca, ca, sa, SPAN)
    files["system/fvSchemes"] = HEAD % ("dictionary", "fvSchemes") + """ddtSchemes { default backward; }
gradSchemes { default Gauss linear; }
divSchemes { default none; div(phi,U) Gauss LUST grad(U); div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes { default Gauss linear corrected; } interpolationSchemes { default linear; } snGradSchemes { default corrected; }
wallDist { method meshWave; }
"""
    files["system/fvSolution"] = HEAD % ("dictionary", "fvSolution") + """solvers
{
    p { solver GAMG; smoother GaussSeidel; tolerance 1e-6; relTol 0.05; }
    pFinal { $p; relTol 0; }
    "U.*" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0; }
}
PIMPLE { nOuterCorrectors 1; nCorrectors 2; nNonOrthogonalCorrectors 0; }
"""
    files["system/decomposeParDict"] = HEAD % ("dictionary", "decomposeParDict") + "numberOfSubdomains %d; method scotch;\n" % np_
    files["system/setExprFieldsDict"] = HEAD % ("dictionary", "setExprFieldsDict") + """// small random start-up noise near the section, so that the flow can leave 2D
expressions
(
    U { field U; dimensions [0 1 -1 0 0 0 0]; condition #{ mag(pos()) < 3 #};
        expression #{ vector(%.10f, %.10f, 0) + 0.05*vector(rand() - 0.5, rand() - 0.5, rand() - 0.5) #}; }
);
"""
    files["system/setExprFieldsDict"] %= (ca, sa)
    files["constant/transportProperties"] = HEAD % ("dictionary", "transportProperties") + "transportModel Newtonian; nu %.10g;\n" % (1.0 / re)
    files["constant/turbulenceProperties"] = HEAD % ("dictionary", "turbulenceProperties") + \
        "simulationType LES;\nLES { LESModel WALE; turbulence on; printCoeffs on; delta cubeRootVol; cubeRootVolCoeffs { deltaCoeff 1; } }\n"
    cyc = "front { type cyclic; } back { type cyclic; }"
    if transient2d:                              # one cell thick, laminar, time-accurate (same run and averaging as the LES)
        cyc = "front { type empty; } back { type empty; }"
        files["constant/turbulenceProperties"] = HEAD % ("dictionary", "turbulenceProperties") + "simulationType laminar;\n"
        del files["system/setExprFieldsDict"]
    if steady:                                   # one cell thick, laminar, steady: the fast classical baseline
        cyc = "front { type empty; } back { type empty; }"
        files["system/controlDict"] = HEAD % ("dictionary", "controlDict") + """// 2D steady laminar section Re %g, alpha %g deg, t/c %g, f/c %g (%d cells)
application simpleFoam; startFrom latestTime; startTime 0; stopAt endTime; endTime 5000; deltaT 1;
writeControl timeStep; writeInterval 5000; purgeWrite 1; writeFormat binary; runTimeModifiable true;
functions
{
    coeffs
    {
        type forceCoeffs; libs (forces); patches (section); rho rhoInf; rhoInf 1; CofR (-0.25 0 0);
        liftDir (%.10f %.10f 0); dragDir (%.10f %.10f 0); pitchAxis (0 0 1);
        magUInf 1; lRef 1; Aref %g; writeControl timeStep; writeInterval 1; log false;
    }
}
""" % (re, alpha, t, f, ncells, -sa, ca, ca, sa, SPAN)
        files["system/fvSchemes"] = HEAD % ("dictionary", "fvSchemes") + """ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes { default none; div(phi,U) bounded Gauss linearUpwind grad(U); div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes { default Gauss linear corrected; } interpolationSchemes { default linear; } snGradSchemes { default corrected; }
"""
        files["system/fvSolution"] = HEAD % ("dictionary", "fvSolution") + """solvers
{
    p { solver GAMG; smoother GaussSeidel; tolerance 1e-8; relTol 0.05; }
    U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-9; relTol 0.1; }
}
SIMPLE { consistent yes; nNonOrthogonalCorrectors 0; residualControl { p 1e-6; U 1e-7; } }
relaxationFactors { equations { U 0.9; } fields { p 1; } }
"""
        files["constant/turbulenceProperties"] = HEAD % ("dictionary", "turbulenceProperties") + "simulationType laminar;\n"
        del files["system/setExprFieldsDict"]
    files["0/U"] = HEAD % ("volVectorField", "U") + """dimensions [0 1 -1 0 0 0 0]; internalField uniform %s;
boundaryField { section { type noSlip; } farfield { type freestreamVelocity; freestreamValue uniform %s; } %s }
""" % (U, U, cyc)
    files["0/p"] = HEAD % ("volScalarField", "p") + """dimensions [0 2 -2 0 0 0 0]; internalField uniform 0;
boundaryField { section { type zeroGradient; } farfield { type freestreamPressure; freestreamValue uniform 0; } %s }
""" % cyc
    files["0/nut"] = HEAD % ("volScalarField", "nut") + """dimensions [0 2 -1 0 0 0 0]; internalField uniform 0;
boundaryField { section { type nutLowReWallFunction; value uniform 0; } farfield { type calculated; value uniform 0; } %s }
""" % cyc
    for k, v in files.items():
        p = os.path.join(out, k)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(v)
    return ncells


def case_list():
    rows = []
    for re in (3000, 6000, 10000, 15000, 20000):
        for t in (0.03, 0.05):
            for f in (0.0, 0.03):
                for a in (range(0, 25, 2) if f == 0 else range(-24, 25, 2)):
                    rows.append("re%05d_t%03d_f%03d_a%+03d %d %d %g %g" % (re, round(t * 1000), round(f * 1000), a, re, a, t, f))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--re", type=float)
    ap.add_argument("--alpha", type=float)
    ap.add_argument("--t", type=float, default=0.03)
    ap.add_argument("--f", type=float, default=0.0)
    ap.add_argument("--np", type=int, default=36)
    ap.add_argument("--out")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--steady", action="store_true", help="2D (one cell, empty sides), steady laminar simpleFoam")
    ap.add_argument("--transient2d", action="store_true", help="2D (one cell, empty sides), laminar pimpleFoam, 16 c/U")
    a = ap.parse_args()
    if a.list:
        print("\n".join(case_list()))
        return
    n = write_case(a.out, a.re, a.alpha, a.t, a.f, a.np, a.steady, a.transient2d)
    print("%s: %d cells" % (a.out, n))


if __name__ == "__main__":
    main()
