#!/bin/bash
# Resume the manuscript sweep: run whatever is not yet verified, with no deadline.
#
# The Friday run was started with --deadline, so it stops rather than beginning a
# scenario it cannot finish in time. This picks up the rest. run_manuscript_sweep.py
# skips any scenario whose tracer already reopens as UGRID, so re-issuing this is
# safe at any point and at most repeats the run that was in flight.
#
#   tools/resume_sweep.sh              every grid, everything outstanding
#   tools/resume_sweep.sh high         one grid only
#
set -u
cd "$(dirname "$0")/.."

GRIDS="${1:-coarse,medium,high}"
CONDA="C:/Users/jdhug/miniforge3/condabin/conda.bat"
LOG="logs/manuscript_sweep_resume_$(date +%Y%m%d_%H%M).log"

if [ -n "$(tasklist //FI 'IMAGENAME eq python.exe' //FO CSV 2>/dev/null | tail -n +2)" ]; then
  echo "python is already running -- refusing to start a second simulation"
  exit 1
fi

echo "resuming into $LOG"
"$CONDA" run -n liss --no-capture-output python -u tools/run_manuscript_sweep.py \
    --grids "$GRIDS" > "$LOG" 2>&1 &
echo "started; poll with: python tools/sweep_status.py"
