#!/bin/bash
# Convert a container image (arm64) to SIF:  sbatch -A $ACCT 00_pull.sbatch <image> <name>
#SBATCH --job-name=cfd-pull
#SBATCH --gpus=1
#SBATCH --time=03:00:00
#SBATCH --output=logs/%x-%j.log
set -euo pipefail
export APPTAINER_CACHEDIR=/tmp/apptainer-cache
mkdir -p "$W/images"; SIF=$W/images/${2:?name}.sif
[ -s "$SIF" ] || { apptainer pull --tmpdir /tmp "$SIF.part.$SLURM_JOB_ID" "docker://${1:?image}"; mv "$SIF.part.$SLURM_JOB_ID" "$SIF"; }
apptainer exec --nv "$SIF" bash -c 'python -c "import torch,sys;print(sys.version, torch.__version__, torch.cuda.get_device_name(0))"; pip list 2>/dev/null | grep -i -E "physicsnemo|^torch |warp|dgl|torch.geometric|transformer.engine|pyvista|vtk"'
