#!/bin/bash
# Pack the decomposed fields of finished cases to cut the file count (the group quota counts files):
#   export W=...; sbatch -A $ACCT cfd/rikyu/11_pack_processors.sbatch [case dir ...]   (from $W; default: every case under runs/)
# For each case with processor*/: tar them into processors.tar, check that the archive lists as many entries as
# there were files and directories, then delete processor*/. Logs, postProcessing, system and constant stay as
# they are, so the reduce scripts still work. Restore with:  cd <case> && tar -xf processors.tar
# A case is skipped while it may still be in use: no "End" in the last 100 lines of its solver log, or any file written in
# the last 60 minutes. The test cases under runs/foamcheck-*, runs/meshtest-* and runs/sections/pilot_* were stopped by hand and have
# no "End"; they are packed anyway.
#SBATCH --job-name=cfd-pack
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=16G
#SBATCH --output=logs/%x-%j.log
set -eo pipefail
cd "$W/runs"

pack() {
    c=$1
    [ -d "$c/processor0" ] || return 0
    case $c in
        foamcheck-*|meshtest-*|sections/pilot_*) ;;
        *) tail -100 "$c"/log.*Foam 2>/dev/null | grep -q "^End" || { echo "skip (not finished) $c"; return 0; } ;;
    esac
    [ -z "$(find "$c" -newermt "-60 minutes" -print -quit)" ] || { echo "skip (written recently) $c"; return 0; }
    (
        cd "$c"
        n=$(find processor[0-9]* | wc -l)
        tar -cf processors.tar.part processor[0-9]*
        m=$(tar -tf processors.tar.part | wc -l)
        [ "$n" = "$m" ] || { echo "MISMATCH $c files $n archive $m"; rm -f processors.tar.part; exit 1; }
        mv processors.tar.part processors.tar
        rm -rf processor[0-9]*
        echo "packed $c $n"
    )
}
export -f pack

if [ $# -gt 0 ]; then
    printf "%s\n" "$@"
else
    { ls -d */processor0 */*/processor0 2>/dev/null || true; } | xargs -n1 dirname
fi | xargs -P "$SLURM_CPUS_PER_TASK" -I{} bash -c 'pack "$1"' _ {} || echo "some cases failed"
echo "files left under runs/: $(find . | wc -l)"
