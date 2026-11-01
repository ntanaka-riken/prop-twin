#!/bin/bash
# Task C3, classical side: the rig as an axisymmetric wedge with the rotor as an actuator disk (cfd/c3/make_axi.py), serial:
#   sbatch -A $ACCT cfd/rikyu/13_c3_axi.sbatch <name> --dir fwd --turb sst [--refine 1.5 ...]   (from $W)
# Output in $W/runs/c3/<name>; prints the wall time.
#SBATCH --job-name=cfd-c3
#SBATCH --time=02:00:00
#SBATCH --ntasks=1
#SBATCH --mem=8G
#SBATCH --output=logs/%x-%j.log
set -eo pipefail
NAME=$1; shift; ARGS=("$@")
set --                                   # the OpenFOAM bashrc would read the script arguments as its own
. "$W/cfd/rikyu/env.sh"
C=$W/runs/c3/$NAME; rm -rf "$C"
t0=$(date +%s)
python3 "$W/cfd/c3/make_axi.py" "${ARGS[@]}" --out "$C"
"$C/Allrun"
echo "$NAME wall_s $(( $(date +%s) - t0 )) iterations $(grep -c '^Time =' "$C/log.simpleFoam") $(grep -m1 -E '^ *cells:' "$C/log.checkMesh") $(grep -E 'Mesh OK|Failed' "$C/log.checkMesh")" | tee "$C/result.txt"
