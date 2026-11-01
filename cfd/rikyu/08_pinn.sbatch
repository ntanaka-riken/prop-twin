#!/bin/bash
# PINN runs (cfd/pinn) on one GPU in the PhysicsNeMo container:
#   sbatch -A $ACCT cfd/rikyu/08_pinn.sbatch <name> c1_section.py --re 6000 --alpha 4 --t 0.03 --f 0.03
# (from $W; output in $W/runs/pinn/<name>, the image is the newest $W/images/physicsnemo-*.sif unless IMG is set)
#SBATCH --job-name=cfd-pnemo
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --gpus=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --output=logs/%x-%j.log
set -eo pipefail
NAME=$1; SCRIPT=$2; shift 2
IMG=${IMG:-$(ls "$W"/images/physicsnemo-*.sif | tail -1)}
OUT=$W/runs/pinn/$NAME; mkdir -p "$OUT"
cd "$OUT"                                  # python -I: no script dir or cwd on sys.path; the script adds cfd/section itself
echo "$NAME: $SCRIPT $* (image $(basename "$IMG"), job $SLURM_JOB_ID)" | tee "$OUT/cmd.txt"
t0=$(date +%s)
apptainer exec --nv --bind "$W" "$IMG" python -I "$W/cfd/pinn/$SCRIPT" "$@" --out "$OUT" 2>&1 | grep --line-buffered -v -E "^(WARNING|INFO)" | tee "$OUT/log.txt"
echo "wall $(( $(date +%s) - t0 )) s" | tee -a "$OUT/log.txt"
