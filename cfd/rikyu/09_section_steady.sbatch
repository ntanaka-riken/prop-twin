#!/bin/bash
# 2D laminar section, the fast classical baselines for the PINN tasks (make_section.py):
#   sbatch -A $ACCT --ntasks=4 cfd/rikyu/09_section_steady.sbatch <re> <alpha> <t> <f> [steady|transient2d]   (from $W)
#   steady       simpleFoam, until the residuals drop (or 5000 iterations)
#   transient2d  pimpleFoam, 16 c/U like the LES; cl, cd averaged over t = 6-16
# Output in $W/runs/section_<mode>/re<re>_t<t>_f<f>_a<alpha>_np<ntasks>; prints the wall time of each step.
#SBATCH --job-name=cfd-steady
#SBATCH --time=02:00:00
#SBATCH --ntasks=4
#SBATCH --mem=16G
#SBATCH --output=logs/%x-%j.log
set -eo pipefail
RE=$1; ALPHA=$2; T=$3; F=$4; MODE=${5:-steady}; NP=$SLURM_NTASKS
set --                                   # the OpenFOAM bashrc would read the script arguments as its own
. "$W/cfd/rikyu/env.sh"
name=$(printf "re%05d_t%03d_f%03d_a%+03d_np%d" "$RE" "$(python3 -c "print(round($T*1000))")" "$(python3 -c "print(round($F*1000))")" "$ALPHA" "$NP")
C=$W/runs/section_$MODE/$name; rm -rf "$C"
SOLVER=$([ "$MODE" = steady ] && echo simpleFoam || echo pimpleFoam)
t0=$(date +%s.%N)
python3 "$W/cfd/section/make_section.py" --$MODE --re "$RE" --alpha "$ALPHA" --t "$T" --f "$F" --np "$NP" --out "$C"
cd "$C"
blockMesh > log.blockMesh 2>&1
t1=$(date +%s.%N)
if [ "$NP" -gt 1 ]; then
    decomposePar > log.decomposePar 2>&1
    srun --mpi=pmix -n "$NP" $SOLVER -parallel > log.$SOLVER 2>&1
else
    $SOLVER > log.$SOLVER 2>&1
fi
t2=$(date +%s.%N)
it=$(grep -c "^Time =" log.$SOLVER); conv=$(grep -c "SIMPLE solution converged" log.$SOLVER || true)
echo "$name mesh_s $(python3 -c "print(round($t1-$t0,1))") solve_s $(python3 -c "print(round($t2-$t1,1))") steps $it converged $conv" | tee result.txt
if [ "$MODE" = steady ]; then
    tail -1 postProcessing/coeffs/0/coefficient.dat | tee -a result.txt
else                                     # columns: Time Cd ... Cl (5th)
    awk '!/^#/ && $1 >= 6 { n++; cd += $2; cl += $5; cd2 += $2*$2; cl2 += $5*$5 }
         END { printf "mean_6_16 cd %.5f cl %.4f sd cd %.5f cl %.4f\n", cd/n, cl/n, sqrt(cd2/n-(cd/n)^2), sqrt(cl2/n-(cl/n)^2) }' \
        postProcessing/coeffs/0/coefficient.dat | tee -a result.txt
fi
