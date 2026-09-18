#!/bin/bash
# Resume the manuscript sweep: run whatever is not yet verified.
#
# run_manuscript_sweep.py skips any scenario whose tracer already reopens as UGRID,
# so re-issuing this is safe at any point and at most repeats the run that was in
# flight. It carries the campaign's accumulated run time across restarts, so a stop
# for a deadline, a bugcheck or an overnight pause does not reset the totals.
#
# A deadline is an hour the machine must be idle by. The sweep will not begin a
# scenario whose worst observed time for that grid, times the safety factor, would
# run past it; the run already in flight is always allowed to finish.
#
#   tools/resume_sweep.sh                                  everything, no deadline
#   tools/resume_sweep.sh coarse,medium                    those grids only
#   tools/resume_sweep.sh all 2026-09-18T06:00             stop short of Friday 06:00
#
set -u
cd "$(dirname "$0")/.."

GRIDS="${1:-coarse,medium,high}"
[ "$GRIDS" = "all" ] && GRIDS="coarse,medium,high"
DEADLINE="${2:-}"
CONDA="C:/Users/jdhug/miniforge3/condabin/conda.bat"
LOG="logs/manuscript_sweep_resume_$(date +%Y%m%d_%H%M).log"

if [ -n "$(tasklist //FI 'IMAGENAME eq python.exe' //FO CSV 2>/dev/null | tail -n +2)" ]; then
  echo "python is already running -- refusing to start a second simulation"
  exit 1
fi

ARGS=(--grids "$GRIDS")
if [ -n "$DEADLINE" ]; then
  ARGS+=(--deadline "$DEADLINE")
  echo "deadline: $DEADLINE"
fi

echo "resuming into $LOG"
nohup "$CONDA" run -n liss --no-capture-output \
    python -u tools/run_manuscript_sweep.py "${ARGS[@]}" > "$LOG" 2>&1 &
disown
echo "started pid $!; poll with: python tools/sweep_status.py"
