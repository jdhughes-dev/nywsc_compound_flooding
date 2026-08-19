"""Reclaim disk from the start-phase matrix, one start at a time.

Fifteen coupled runs are tens of gigabytes and the experiment reduces to a few
dozen numbers, so docs/GP/START_PHASE_EXPERIMENT.md ends with extract, verify,
delete.  This does the deleting, per start rather than at the end, because the
matrix needs about 100 GB it does not have unless the space comes back as it goes.

Two tiers, and only one of them is what the plan calls the run directory:

  the model working directories, dflow-fm/coarse/run_* and modflow/gp_chd/run_*,
  about 11 GB a run, holding FlowFM_his.nc and FlowFM_map.nc.  Nothing downstream
  reads them -- the notebook already copied everything any analysis wants into
  results/ -- so they go as soon as that copy is complete.

  and inside results/, dflow_tracer.nc (1.3 GB) and swmm.rpt (300 MB), which are
  95 percent of a results directory and which start_phase_data.py never opens: it
  reads gwf.obs.csv and swmm_q.npz and nothing else.  The rest of results/ stays
  until docs/data/GP/start_phase.nc is written and verified, since the archive is
  built from it.

Safety.  Only scenarios carrying the _t<HHMM> start tag are ever touched, asserted
per path rather than assumed from the glob.  dflow_tracer.nc is live data for the
untagged production runs -- boundary_averaging_data.py opens it for every scenario
in its CONFIG -- and deleting one of those would silently break Figure 7 and cost
a six-hour re-run.  A start is pruned only once all five of its runs have landed,
so the run in flight is never a candidate.

Idempotent: it re-reports as already-pruned rather than failing, which is what
makes --watch safe to restart after the laptop drops it.
"""
import argparse
import pathlib as pl
import re
import shutil
import sys
import time

sys.path.insert(0, str(pl.Path(__file__).resolve().parent))
import run_start_phase_matrix as m            # noqa: E402  the one list of runs

HERE = pl.Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = ROOT / "results" / "gp"
WORKDIRS = (ROOT / "dflow-fm" / "coarse", ROOT / "modflow" / "gp_chd")

# What a finished run must have before anything of it is deleted: exactly the two
# files start_phase_data.missing() requires, so pruning can never turn a completed
# run back into a missing one.
KEEP = ("gwf.obs.csv", "swmm_q.npz")
DROP = ("dflow_tracer.nc", "swmm.rpt")

TAGGED = re.compile(r"_t\d{4}$")


def scenarios_of(start):
    return [m.scenario_of(start, h, x) for h, _, x in m.MATRIX]


def complete(name):
    return all((RESULTS / name / f).is_file() for f in KEEP)


def _rm(path, freed):
    """Delete one path, refusing anything without a start tag in its name."""
    stem = path.name if path.is_dir() else path.parent.name
    if not TAGGED.search(stem):
        raise SystemExit(f"refusing to delete untagged path: {path}")
    size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) \
        if path.is_dir() else path.stat().st_size
    shutil.rmtree(path) if path.is_dir() else path.unlink()
    freed.append(size)
    return size


def prune_start(start, dry_run=False):
    """Prune one start if all five of its runs are in. Returns bytes freed."""
    names = scenarios_of(start)
    landed = [n for n in names if complete(n)]
    if len(landed) < len(names):
        print(f"  {start[8:12]}  {len(landed)}/{len(names)} runs in - waiting")
        return 0

    freed = []
    for name in names:
        for f in DROP:
            p = RESULTS / name / f
            if p.is_file():
                n = p.stat().st_size if dry_run else _rm(p, freed)
                if dry_run:
                    freed.append(n)
                print(f"  {'would drop' if dry_run else 'dropped'} "
                      f"{name}/{f}  {n / 2**30:.2f} GB")
        for base in WORKDIRS:
            d = base / f"run_{name}"
            if d.is_dir():
                if dry_run:
                    n = sum(p.stat().st_size for p in d.rglob("*") if p.is_file())
                    freed.append(n)
                else:
                    n = _rm(d, freed)
                print(f"  {'would remove' if dry_run else 'removed'} "
                      f"{d.relative_to(ROOT)}  {n / 2**30:.2f} GB")
    total = sum(freed)
    print(f"  {start[8:12]}  complete, "
          f"{'would free' if dry_run else 'freed'} {total / 2**30:.1f} GB"
          if total else f"  {start[8:12]}  complete, already pruned")
    return total


def pass_once(dry_run=False):
    print(f"pruning start-phase output under {RESULTS}")
    total = sum(prune_start(s, dry_run) for s, _ in m.STARTS)
    names = [n for s, _ in m.STARTS for n in scenarios_of(s)]
    done = all(complete(n) for n in names)
    pruned = all(not (RESULTS / n / f).is_file() for n in names for f in DROP) and         all(not (b / f"run_{n}").is_dir() for n in names for b in WORKDIRS)
    print(f"total {'would free' if dry_run else 'freed'} {total / 2**30:.1f} GB"
          f"{'  (matrix complete)' if done and pruned else ''}\n", flush=True)
    return done


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true",
                   help="report what would go, delete nothing")
    p.add_argument("--watch", type=float, metavar="MIN",
                   help="re-check every MIN minutes until all three starts are in")
    a = p.parse_args()
    while True:
        done = pass_once(a.dry_run)
        if done or not a.watch:
            return 0
        time.sleep(a.watch * 60.0)


if __name__ == "__main__":
    sys.exit(main())
