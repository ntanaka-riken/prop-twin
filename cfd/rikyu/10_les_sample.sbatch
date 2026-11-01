#!/bin/bash
# Sample the time-averaged LES field of one section case at a cloud of points (cfd/pinn/les_samples.py dict):
#   sbatch -A $ACCT cfd/rikyu/10_les_sample.sbatch <case name, e.g. re06000_t030_f030_a+04> <dict file>   (from $W)
#SBATCH --job-name=cfd-sample
#SBATCH --time=00:30:00
#SBATCH --ntasks=36
#SBATCH --mem=64G
#SBATCH --output=logs/%x-%j.log
set -eo pipefail
CASE=$1; DICT=$2
set --
. "$W/cfd/rikyu/env.sh"
C=$W/runs/sections/$CASE
cp "$DICT" "$C/system/sampleLES"
cd "$C"
srun --mpi=pmix -n "$SLURM_NTASKS" postProcess -parallel -latestTime -fields "(pMean UMean)" -dict system/sampleLES > log.sampleLES 2>&1
ls postProcessing/sampleLES/*/
