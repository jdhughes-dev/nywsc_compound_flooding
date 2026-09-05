#!/bin/bash
# Coastal-seepage set for one resolution, strictly one simulation at a time.
#
# Usage: tools/run_seep.sh coarse|medium|high
#
# Ordered so the first run answers the question: the 15-minute reference compares
# directly against its published counterpart with no coupling-interval confound.
#
# Resumable. run_scenario.py refuses to overwrite a completed scenario, so re-issuing
# this command after a crash skips what finished and at most repeats the run in flight.
#
# Each run's FlowFM_map.nc is reclaimed as soon as its tracer verifies. Without that
# the maps accumulate -- 11 GB a run on coarse, 28 on midres, 72 on highres -- and the
# midres set had filled the disk to 97 percent by its fourth run.
set -u
cd "$(dirname "$0")/.."

RES="${1:-}"
case "$RES" in
  coarse|medium|high) ;;
  *) echo "usage: $0 coarse|medium|high"; exit 2 ;;
esac

CONDA="C:/Users/jdhug/miniforge3/condabin/conda.bat"

for spec in "0.25 mean _meanbnd" "24 mean _meanbnd" "8 mean _meanbnd" \
            "0.25 instant _instbnd" "24 instant _instbnd" "8 instant _instbnd"; do
  set -- $spec
  if [ -n "$(pgrep -f 'run_scenario.py' 2>/dev/null)" ]; then
    echo "another run is live, refusing to start a second"; exit 1
  fi
  echo "=== $(date +%H:%M:%S)  ${RES}  ${1} h  ${2} ==="
  "$CONDA" run -n liss --no-capture-output python -u notebooks-GP/run_scenario.py \
      --resolution "$RES" --coupling-hours "$1" --coastal-averaging "$2" \
      --scenario-suffix "$3" --coastal-seepage
  rc=$?
  echo "=== $(date +%H:%M:%S)  rc=$rc ==="
  [ $rc -ne 0 ] && { echo "stopping on failure"; exit $rc; }

  # Only ever deletes a map whose tracer opens as UGRID and carries times.
  "$CONDA" run -n liss --no-capture-output python -u tools/reclaim_maps.py \
      --resolution "$RES"
  df -h /c | tail -1
done
echo "${RES} SEEPAGE SET COMPLETE $(date +%H:%M:%S)"
