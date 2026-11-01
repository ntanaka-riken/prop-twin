# OpenFOAM v2512 (spack, aarch64) on rikyu.  source cfd/rikyu/env.sh
# The work directory and the Slurm account come from the environment, not from this repository:
#   export W=<data dir>/proptwin-cfd  ACCT=<project>   (sbatch -A $ACCT ...)
FOAM=/shared/software/spack-1.2.0/opt/spack/linux-neoverse_v2/openfoam-2512-lrbixw3wjx5mtvrnwg7xgwsgkbgz7c7a
MPI=/shared/software/spack-1.2.0/opt/spack/linux-neoverse_v2/openmpi-5.0.10-rbeeyvi7id2d3fwzcmn6pli5ad2o2jm4
export PATH=$MPI/bin:$PATH LD_LIBRARY_PATH=$MPI/lib:${LD_LIBRARY_PATH:-}
set +u; . $FOAM/etc/bashrc   # the OpenFOAM scripts need set +u
