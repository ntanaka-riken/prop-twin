#!/bin/bash
# Lattice Boltzmann runs (cfd/xlb, XLB on Warp) on one GPU in the PhysicsNeMo container:
#   sbatch -A $ACCT cfd/rikyu/12_xlb.sbatch <name> section_lbm.py --re 6000 --alpha 4 --t 0.03 --f 0.03 --n 256
# (from $W; output in $W/runs/xlb/<name>). XLB is not in the image; install it once, outside the image:
#   python -I -m pip install --target $W/pylib/site --no-deps xlb jax jaxlib ml_dtypes opt_einsum trimesh
#   python -I -m pip install --target $W/pylib/warp-1.11 --no-deps warp-lang==1.11.1     (XLB 0.3.1 needs wp.mat)
#SBATCH --job-name=cfd-xlb
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --gpus=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --output=logs/%x-%j.log
set -eo pipefail
NAME=$1; SCRIPT=$2; shift 2
IMG=${IMG:-$(ls "$W"/images/physicsnemo-*.sif | tail -1)}
OUT=$W/runs/xlb/$NAME; mkdir -p "$OUT"
cd "$OUT"
echo "$NAME: $SCRIPT $* (image $(basename "$IMG"), job $SLURM_JOB_ID)" | tee "$OUT/cmd.txt"
t0=$(date +%s)
apptainer exec --nv --bind "$W" --env XLB_SITE="$W/pylib/site" --env XLB_WARP="$W/pylib/warp-1.11" --env JAX_PLATFORMS=cpu "$IMG" \
    python -I "$W/cfd/xlb/$SCRIPT" "$@" --out "$OUT" 2>&1 | grep --line-buffered -v -E "^(WARNING|INFO)" | tee "$OUT/log.txt"
echo "wall $(( $(date +%s) - t0 )) s" | tee -a "$OUT/log.txt"
