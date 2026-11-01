#!/bin/bash
# Mesh test of the CFD geometry:  sbatch -A $ACCT 02_meshtest.sbatch
#SBATCH --job-name=cfd-mesh
#SBATCH --time=01:00:00
#SBATCH --ntasks=64
#SBATCH --exclusive
#SBATCH --output=logs/%x-%j.log
set -eo pipefail
. "$W/cfd/rikyu/env.sh"
C=$W/runs/meshtest-$SLURM_JOB_ID
cp -r "$W/cfd/cases/mesh_test" "$C"; mkdir -p "$C/constant/triSurface"; cp "$W"/cfd/geometry/out/*.stl "$C/constant/triSurface/"
t0=$(date +%s); NP=$SLURM_NTASKS "$C/Allrun"; t1=$(date +%s)
echo "mesh $((t1-t0)) s"; cat "$C/log.surfaceCheck"
grep -E "cells:|faces:|points:|Mesh OK|Failed|\*\*\*|Max skewness|Max non-orth" "$C/log.checkMesh"
grep -E "Snapped mesh|Layer mesh|Finished meshing" "$C/log.snappyHexMesh" | tail -3
