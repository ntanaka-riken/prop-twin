#!/bin/bash
# Stage 2 runs, one per node (lines "name rpm dir model mesh" of the list; mesh = <LEVEL>-<LAYERS>):
#   sbatch -A $ACCT --array=0-19 05_mrf_run.sbatch [$W/cfd/cases/mrf_runs.txt]
#SBATCH --job-name=cfd-mrf
#SBATCH --time=12:00:00
#SBATCH --ntasks=144
#SBATCH --exclusive
#SBATCH --output=logs/%x-%A_%a.log
set -eo pipefail
LIST=${1:-$W/cfd/cases/mrf_runs.txt}
set --                                   # the OpenFOAM bashrc would read the script arguments as its own
. "$W/cfd/rikyu/env.sh"
read -r name rpm dir model mesh <<< "$(sed -n "$(( ${SLURM_ARRAY_TASK_ID:-0} + 1 ))p" "$LIST")"
M=$W/runs/mrf-mesh-L$mesh; C=$W/runs/mrf/$name
rm -rf "$C"; mkdir -p "$C"; cp -r "$M"/{0.orig,system,Allrun} "$C/"; mkdir "$C/constant"
cp -r "$M"/constant/{polyMesh,transportProperties,turbulenceProperties.*,MRFProperties} "$C/constant/"
t0=$(date +%s); RPM=$rpm DIR=$dir MODEL=$model NP=$SLURM_NTASKS "$C/Allrun"; echo "$name: $(( $(date +%s) - t0 )) s"
tail -3 "$C/log.simpleFoam"
