#!/bin/bash
# Stage 2 mesh:  sbatch -A $ACCT --export=ALL,LEVEL=0,LAYERS=abs 04_mrf_mesh.sbatch   -> $W/runs/mrf-mesh-L$LEVEL-$LAYERS
#SBATCH --job-name=cfd-mrfmesh
#SBATCH --time=04:00:00
#SBATCH --ntasks=144
#SBATCH --exclusive
#SBATCH --output=logs/%x-%j.log
set -eo pipefail
. "$W/cfd/rikyu/env.sh"
LEVEL=${LEVEL:-0}; LAYERS=${LAYERS:-abs}; C=$W/runs/mrf-mesh-L$LEVEL-$LAYERS
rm -rf "$C"; cp -r "$W/cfd/cases/mrf" "$C"; mkdir -p "$C/constant/triSurface"; cp "$W"/cfd/geometry/out/*.stl "$C/constant/triSurface/"
t0=$(date +%s); LEVEL=$LEVEL LAYERS=$LAYERS NP=$SLURM_NTASKS "$C/Allmesh"; echo "mesh $(( $(date +%s) - t0 )) s"
grep -E "cells:|Mesh OK|Failed|\*\*\*|Max skewness|non-orthogonality Max" "$C/log.checkMesh"
sed -n '/patch.*faces.*layers.*overall thickness/,/^$/p' "$C/log.snappyHexMesh" | tail -12
grep -E "cellZone|rotor" "$C/log.topoSet" | tail -3
