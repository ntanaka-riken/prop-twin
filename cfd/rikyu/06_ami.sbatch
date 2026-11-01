#!/bin/bash
# Stage 3: rotating-mesh (AMI) LES of the whole rig, meshed and run in one allocation:
#   sbatch -A $ACCT -N 4 --gpus=16 --export=ALL,MODE=urans,LEVEL=0,RPM=3067,DIR=1,REVS=15,AVG=8 06_ami.sbatch
#   sbatch -A $ACCT -N 8 --gpus=32 --export=ALL,MODE=urans,LEVEL=1,RPM=3067,DIR=-1 06_ami.sbatch
# (multi-node jobs must take all 4 GPUs per node). Resubmitting the same LEVEL/RPM/DIR continues the run.
#SBATCH --job-name=cfd-ami
#SBATCH --time=1-00:00:00
#SBATCH --ntasks-per-node=144
#SBATCH --exclusive
#SBATCH --output=logs/%x-%j.log
set -eo pipefail
. "$W/cfd/rikyu/env.sh"
MODE=${MODE:-urans}; LEVEL=${LEVEL:-0}; LAYERS=${LAYERS:-abs}; DIR=${DIR:-1}; RPM=${RPM:-3067}; NP=$SLURM_NTASKS
tag=$([ "$DIR" -gt 0 ] && echo fwd || echo rev); C=$W/runs/ami/L$LEVEL-${LAYERS}_${MODE}_${tag}_$RPM
if [ ! -f "$C/log.checkMesh" ]; then
    rm -rf "$C"; mkdir -p "$W/runs/ami"; cp -r "$W/cfd/cases/ami" "$C"
    mkdir -p "$C/constant/triSurface"; cp "$W"/cfd/geometry/out/*.stl "$C/constant/triSurface/"
    t0=$(date +%s); LEVEL=$LEVEL LAYERS=$LAYERS NP=$NP "$C/Allmesh"; echo "mesh $(( $(date +%s) - t0 )) s on $NP ranks"
    grep -E "cells:|Mesh OK|Failed|\*\*\*" "$C/log.checkMesh"
    grep -A5 "overall thickness" "$C/log.snappyHexMesh" | grep -E "^(blades|hub)" | tail -2
    grep -E "AMI" "$C/log.checkMesh" | head -4
fi
t0=$(date +%s); MODE=$MODE RPM=$RPM DIR=$DIR REVS=${REVS:-30} AVG=${AVG:-15} NP=$NP "$C/Allrun"; echo "run $(( $(date +%s) - t0 )) s"
tail -3 "$C/log.pimpleFoam"
