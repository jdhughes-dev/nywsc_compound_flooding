#!/bin/bash
# Coarse coastal-seepage set, strictly one simulation at a time.
# Ordered so the first run answers the question: the 15-minute reference compares
# directly against its published counterpart with no coupling-interval confound.
cd "$(dirname "$0")/.."
CONDA="C:/Users/jdhug/miniforge3/condabin/conda.bat"
for spec in "0.25 mean _meanbnd" "24 mean _meanbnd" "8 mean _meanbnd" \
            "0.25 instant _instbnd" "24 instant _instbnd" "8 instant _instbnd"; do
  set -- $spec
  if [ -n "$(pgrep -f 'run_scenario.py' 2>/dev/null)" ]; then
    echo "another run is live, refusing to start a second"; exit 1
  fi
  echo "=== $(date +%H:%M:%S)  ${1} h  ${2} ==="
  "$CONDA" run -n liss --no-capture-output python -u notebooks-GP/run_scenario.py \
      --resolution coarse --coupling-hours "$1" --coastal-averaging "$2" \
      --scenario-suffix "$3" --coastal-seepage
  rc=$?
  echo "=== $(date +%H:%M:%S)  rc=$rc ==="
  [ $rc -ne 0 ] && { echo "stopping on failure"; exit $rc; }
done
echo "COARSE SEEPAGE SET COMPLETE $(date +%H:%M:%S)"
