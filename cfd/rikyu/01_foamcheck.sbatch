#!/bin/bash
# Smoke test of OpenFOAM v2512 on the compute nodes: the rotating-propeller tutorial (snappyHexMesh, AMI,
# pimpleFoam) for 200 steps, with NP ranks over the allocated nodes.
#   sbatch -A $ACCT -N 1 --ntasks-per-node=32 01_foamcheck.sbatch
#   sbatch -A $ACCT -N 2 --ntasks-per-node=72 --gpus=8 01_foamcheck.sbatch   (multi-node jobs must take all 4 GPUs per node)
#SBATCH --job-name=cfd-check
#SBATCH --time=01:00:00
#SBATCH --exclusive
#SBATCH --output=logs/%x-%j.log
set -eo pipefail
. "$W/cfd/rikyu/env.sh"; . "$WM_PROJECT_DIR/bin/tools/RunFunctions"
NP=$SLURM_NTASKS; C=$W/runs/foamcheck-$SLURM_JOB_ID
mkdir -p "$C"; cp -r "$FOAM_TUTORIALS/incompressible/pimpleFoam/RAS/propeller/." "$C"; cd "$C"
foamDictionary -entry endTime -set 0.002 system/controlDict >/dev/null
foamDictionary -entry writeInterval -set 0.002 system/controlDict >/dev/null
foamDictionary -entry numberOfSubdomains -set $NP system/decomposeParDict >/dev/null
foamDictionary -entry method -set scotch system/decomposeParDict >/dev/null
t0=$(date +%s); ./Allrun.pre >/dev/null; t1=$(date +%s)
checkMesh 2>&1 | grep -E "cells:|Mesh OK|Failed|\*\*\*" || true
decomposePar >log.decomposePar 2>&1; restore0Dir -processor >/dev/null
srun --mpi=pmix -n $NP pimpleFoam -parallel >log.pimpleFoam 2>&1 || mpirun -np $NP pimpleFoam -parallel >log.pimpleFoam 2>&1
t2=$(date +%s)
echo "nodes $SLURM_NNODES ranks $NP  mesh $((t1-t0)) s  solve $((t2-t1)) s"
grep -E "^Time =" log.pimpleFoam | tail -1; grep -E "ExecutionTime" log.pimpleFoam | tail -1
grep -iE "AMI.*weights|sum\(weights\)" log.pimpleFoam | tail -2
