# Reproducing the manuscript

`Hughesetal_AWR_LISSCoupling.tex` is built from eight figures, eight archived summaries,
and 46 coupled simulations. Each of those is a layer, and a rebuild can start at any
of them:

| start from | needs | takes |
|---|---|---|
| the document | figures already in `figures/` | seconds |
| the figures | the archives in `../data/GP` — **committed** | ~2 minutes |
| the archives | `results/gp` and `logs/` from the simulations | ~40 minutes |
| the simulations | the models, and patience | ~4 days, ~300 GB |

Only the first two are possible from a clone of this repository, and they are the
two that matter for checking the document: the archives are committed precisely so
that the figures rebuild without the simulation output, which is hundreds of
gigabytes and is not version controlled.

```
cd docs/GP/scripts
python rebuild_manuscript.py --check      # what can this machine rebuild from?
python rebuild_manuscript.py              # figures + document  (the usual case)
python rebuild_manuscript.py --stage archives   # also recompute the summaries
python rebuild_manuscript.py --all-grids  # plus the medium/fine supporting figures
python rebuild_manuscript.py --submission # also write submission/Figure_N.pdf
```

`--submission` writes the figures as separate files named the way the journal
asks for them. The numbering is read from the `.aux` the run just wrote and the
label-to-file mapping from the `.tex`, not from any list in the driver: LaTeX
numbers by the order captions appear in the source, which is not the order the
figures are built in, and numbering by build order would mislabel four of the
seven. Font embedding is verified with `pdffonts`, since a figure that fails
that is rejected at submission rather than at build time. `submission/` is
derived and is not version controlled.

It also writes `Graphical_Abstract.pdf`, which the journal requires and the
document does not include. That one is copied after the numbering check rather
than through it: it is not cited in the `.tex`, so it has no number to be given.
It is drawn at 13.28 by 5.31 cm, the journal's 1328 by 531 px at 254 dpi and
just over the 13 by 5 cm it must stay legible at, so it is drawn at the size it
will be read at rather than at one it will be reduced from.

`--check` reports what is present and whether each archive's inputs are complete.
Where they are not, the data modules fall back to the committed archive rather than
overwriting it with a partial recomputation, so `--stage archives` on an incomplete
tree is safe but does nothing.

Rebuilding the figures needs a network connection for the base map on
`coupling_region.pdf`. Without one the figure is drawn without it and a warning is
printed; nothing else changes.

## Running the simulations

This is the expensive layer and it is not driven by `rebuild_manuscript.py`. Use
`run_sweep.py`, which runs one resolution's sweep a scenario at a time, and is
written to be re-launched rather than babysat: it skips every scenario already
finished at the current MODFLOW version, so an interrupted sweep is resumed by
issuing the same command again. At most the scenario in flight is lost, and if that
one died after its coupling loop finished, `finish_scenario.py` recovers it from the
D-Flow FM map file without re-simulating.

Add `--dry-run` to any of these to see the plan, the per-scenario grid, junction
count and exchange frequency, and a time estimate, without running anything.

```
cd notebooks-GP

# 21 simulations, averaged coastal boundary — the reduction adopted in the paper
python -u run_sweep.py --resolution coarse medium high \
    --coastal-averaging mean --scenario-suffix _meanbnd

# 21 simulations, instantaneous coastal boundary — the incumbent formulation
python -u run_sweep.py --resolution high \
    --coastal-averaging instant --scenario-suffix _instbnd
```

Two sets of runs sit outside `run_sweep.py` because its interval list does not carry
them:

```
# 6 h and 12 h on the coarse grid, which place the transition (4 simulations)
for H in 6 12; do
  for R in "instant _instbnd" "mean _meanbnd"; do
    set -- $R
    python -u run_scenario.py --resolution coarse --coupling-hours $H \
        --coastal-averaging $1 --scenario-suffix $2
  done
done

# half the sewer junctions, with leakance raised to hold total conductance fixed
python -u run_scenario.py --resolution medium --coupling-hours 2 \
    --junctions 122 --leakance 0.1292 \
    --coastal-averaging mean --scenario-suffix _meanbnd
```

### Scenario naming is not uniform, for historical reasons

The instantaneous runs on the coarse and medium grids predate the
`--scenario-suffix` convention and carry no suffix; two coarse intervals were later
re-run as `_instbnd`, and the fine grid was run entirely under `_instbnd`. The
mapping from grid and interval to directory name is written out in `CONFIG` in
`scripts/boundary_averaging_data.py`, which is the authority. A reproduction from
scratch is cleaner if every instantaneous run is given `--scenario-suffix _instbnd`
and `CONFIG` is updated to match.

### Cost

Measured on one workstation, running sequentially:

| grid | cells | per scenario | retained | map file, transient |
|---|---|---|---|---|
| coarse | 6,491 | 35–73 min | ~2 GB | 11.5 GB |
| medium | 16,666 | 93–119 min | 4.4 GB | 29.4 GB |
| fine | 41,091 | 229–284 min | 9.7 GB | 72.3 GB |

The map file is deleted after each scenario, once its tracer has been verified to
reopen as UGRID, so only one exists at a time. Retaining every scenario needs about
240 GB and the peak is roughly 310 GB.

## What is in here

```
Hughesetal_AWR_LISSCoupling.tex   the manuscript
figures/                          the eight figures it includes, as PDF, plus
                                  graphical_abstract.pdf, which it does not
../data/GP/*.nc                   the archived summaries the figures are drawn from
scripts/
  rebuild_manuscript.py           the driver described above
  *_data.py                       compute an archive from results/ or logs/
  make_*_figure.py                draw one figure from an archive
  start_phase_analysis.py         standalone: whether the simulation start time
                                  decides which boundary reduction scores better
  make_graphical_abstract.py      draw the graphical abstract from two of them
```

The graphical abstract reads the same archives as Figures 3 and 8, and reduces
them rather than restating them, so it cannot come to disagree with the
document. It is redrawn whenever the figures are.

**Nothing under `docs/` may depend on `results/`, or on a D-Flow run directory, at
draw time.** That holds for every figure and every analysis here, whether or not the
manuscript includes it: the simulation output is hundreds of gigabytes, is not
version controlled, and the run directories are deleted once their results are
extracted, so anything that reads them cannot be rebuilt from a clone. The pattern
is the one the `*_data.py` modules already follow -- recompute from `results/` when
it is present, write a small `.nc` under `../data/GP`, and read that `.nc` when it
is not. `pick_start_times.py` is the same shape for the same reason, even though it
draws nothing: it needs one station of simulated water level, which it archives
rather than re-reading a run directory that is meant to be deleted.

Each `*_data.py` writes exactly one archive and each `make_*_figure.py` draws exactly
one figure, so a single figure can be redrawn on its own. The figure scripts that
read an archive take `--no-refresh`, which draws from the archive as committed rather
than recomputing it; `rebuild_manuscript.py` uses that, so redrawing a figure never
silently recomputes a summary just because the simulation output happens to be
present.

Statistics and figures each have one implementation, in `scripts/`. The step3
notebooks in `notebooks-GP/` call the same modules rather than carrying their own
copies, which is what keeps the notebook and the manuscript from disagreeing.
