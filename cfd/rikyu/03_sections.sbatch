#!/bin/bash
# Stage 1: blade-section LES polars, PER cases side by side on one node (lines of cfd/section/cases.txt).
#   sbatch -A $ACCT --array=0-94 03_sections.sbatch               # all 380 cases, 4 per node
#   sbatch -A $ACCT --array=0 03_sections.sbatch pilot.txt         # another list
# Cases already finished (file `done`) are skipped; unfinished ones resume from their last write (every 2 c/U).
#SBATCH --job-name=cfd-sec
#SBATCH --time=1-00:00:00
#SBATCH --ntasks=144
#SBATCH --exclusive
#SBATCH --mem=400G
#SBATCH --output=logs/%x-%A_%a.log
set -eo pipefail
LIST=${1:-$W/cfd/section/cases.txt}; PER=${PER:-4}; NP=$((SLURM_NTASKS / PER))
set --                                   # the OpenFOAM bashrc would read the script arguments as its own
. "$W/cfd/rikyu/env.sh"
i0=$((${SLURM_ARRAY_TASK_ID:-0} * PER))
for k in $(seq 1 $PER); do
    line=$(sed -n "$((i0 + k))p" "$LIST"); [ -z "$line" ] && continue
    read -r name re alpha t f <<< "$line"
    C=$W/runs/sections/$name
    [ -f "$C/done" ] && { echo "$name: done before"; continue; }
    (
        if ls -d "$C"/processor0/[1-9]* >/dev/null 2>&1; then     # written every 2 c/U: resume from the latest time
            cd "$C"; mv log.pimpleFoam log.pimpleFoam.$(date +%s)
        else
            rm -rf "$C"; python3 "$W/cfd/section/make_section.py" --re $re --alpha $alpha --t $t --f $f --np $NP --out "$C"
            cd "$C"
            blockMesh > log.blockMesh 2>&1
            checkMesh > log.checkMesh 2>&1 || true
            setExprFields > log.setExprFields 2>&1 || echo "$name: setExprFields failed (no start-up noise)"
            decomposePar > log.decomposePar 2>&1
        fi
        t0=$(date +%s)
        srun --mpi=pmix --exact -n $NP -c 1 --mem=$((300 / PER))G pimpleFoam -parallel > log.pimpleFoam 2>&1
        echo "$name: $(( $(date +%s) - t0 )) s, $(grep -m1 -E '^ *cells:' log.checkMesh), $(grep -E 'Mesh OK|Failed' log.checkMesh)"
        rm -rf processor*/[1-9]*/uniform 2>/dev/null; touch done
    ) &
done
wait
