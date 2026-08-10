#!/usr/bin/env python
"""Run one step2 coupled scenario headlessly, streaming output to a log file.

The notebook remains the single source of truth: this script converts
step2_run_coupled_models.ipynb to Python at run time, rewrites only the top-level
configuration assignments, and executes the result.  Nothing is duplicated, so the
runner cannot drift out of sync with the notebook the way a checked-in
`nbconvert --to script` copy would.

Why a script at all: a full 89-day run is 4-6 h, and this laptop hard-crashes
under that load (see the bugcheck history -- four dirty reboots, no dump ever
captured).  `nbconvert --execute` buffers cell output into the .ipynb and writes
it at the end, so a crash loses the entire record.  Here every line is flushed to
the log as it is produced, so a reboot leaves a log that says exactly how far the
run got.

Usage
-----
    cd notebooks-GP
    python -u run_scenario.py                      # defaults: the pending highres 15-min run
    python -u run_scenario.py --smoke-days 2       # short validation first
    python -u run_scenario.py --resolution medium --coupling-hours 4

Defaults reproduce `gp_high_15.00M_n244`, the one scenario the 8/3 crash took out
of the highres sweep.
"""

import os

# MUST precede numpy: the Intel OpenMP runtime is loaded twice (numpy/MKL from the
# conda env, then MODFLOW resolving the same dll out of the D-Flow dll directory
# that the notebook prepends to PATH).  Without this MF6 aborts the whole process
# with "OMP: Error #15" on the first coupling step.  The notebook sets it too, but
# this runner imports numpy during preflight, before the notebook code runs.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import argparse
import datetime
import pathlib as pl
import re
import sys
import time

NOTEBOOK = "step2_run_coupled_models.ipynb"

# Every knob this script is allowed to override, mapped to the argparse dest that
# supplies it.  Each name must appear exactly once as a top-level assignment in the
# converted notebook or the run aborts -- a silent miss would run the wrong scenario
# for six hours.
OVERRIDES = {
    "domain": "domain",
    "boundary_condition": "boundary_condition",
    "resolution": "resolution",
    "mf_couple_freq_hours": "coupling_hours",
    "n_junctions": "junctions",
    "junction_seed": "junction_seed",
    "pipe_leakance": "leakance",
    "smoke_test_days": "smoke_days",
    "scenario_suffix": "scenario_suffix",
    "coastal_boundary_averaging": "coastal_averaging",
}


class Tee:
    """Write to a stream and a log file, flushing both on every write.

    Unbuffered by design: the point is that the log survives a hard reboot mid-run.
    The coupling loop redraws its progress line with a bare '\\r', which would
    collapse the whole run into one unreadable line in a file, so carriage returns
    become newlines in the log only -- the terminal still gets the in-place redraw.
    """

    def __init__(self, stream, log):
        self.stream = stream
        self.log = log

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
        self.log.write(data.replace("\r", "\n"))
        self.log.flush()
        return len(data)

    def flush(self):
        self.stream.flush()
        self.log.flush()

    def isatty(self):
        return self.stream.isatty()


def notebook_source(path):
    """Convert the notebook to plain Python."""
    import nbformat
    from nbconvert import PythonExporter

    nb = nbformat.read(path, as_version=4)
    src, _ = PythonExporter().from_notebook_node(nb)

    # The notebook is pure Python today, but a stray %magic or !shell line would
    # convert to a get_ipython() call that dies under a plain interpreter.  Catch it
    # here rather than 40 minutes into a run.
    bad = [
        f"  line {i}: {ln.strip()}"
        for i, ln in enumerate(src.splitlines(), 1)
        if "get_ipython" in ln
    ]
    if bad:
        raise SystemExit(
            f"{path.name} contains IPython magics that cannot run as a script:\n"
            + "\n".join(bad)
        )
    return src


def apply_overrides(src, values):
    """Rewrite the top-level config assignments, asserting each is hit exactly once.

    Anchored at column 0, so assignments inside function bodies are never touched.
    """
    for name, value in values.items():
        pattern = re.compile(rf"^{re.escape(name)}\s*=.*$", re.MULTILINE)
        src, n = pattern.subn(
            f"{name} = {value!r}  # set by run_scenario.py", src, count=0
        )
        if n != 1:
            raise SystemExit(
                f"expected exactly 1 top-level '{name} = ...' in {NOTEBOOK}, found {n}. "
                "The notebook's configuration cell changed; update OVERRIDES."
            )
    return src


def main():
    p = argparse.ArgumentParser(
        description="Run one step2 coupled scenario headlessly.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--domain", default="gp")
    p.add_argument("--boundary-condition", default="chd", choices=("chd", "ghb"))
    p.add_argument("--resolution", default="high", choices=("coarse", "medium", "high"))
    p.add_argument(
        "--coupling-hours",
        type=float,
        default=0.25,
        help="MODFLOW <-> D-Flow FM coupling interval in hours (0.25 = 15.00M)",
    )
    p.add_argument("--junctions", type=int, default=500,
                   help="requested SWMM <-> MODFLOW connections (capped to those available)")
    p.add_argument(
        "--leakance",
        type=float,
        default=0.0655,
        help="pipe leakance 1/d; held constant across the coarse/medium/high sweeps "
             "so grid differences are purely resolution",
    )
    p.add_argument(
        "--smoke-days",
        type=float,
        default=None,
        help="shorten the D-Flow computation to N days and tag the scenario "
             "'_smoke<N>d'; omit for the full run",
    )
    p.add_argument(
        "--junction-seed",
        type=int,
        default=0,
        help="seed for the SWMM junction draw; only has an effect when --junctions "
             "is below the number available. A non-zero seed tags the scenario "
             "'_s<seed>' automatically, so ensemble members cannot overwrite each "
             "other. 0 is the value that was hard-coded before this existed",
    )
    p.add_argument(
        "--scenario-suffix",
        default="",
        help="append to the scenario id so a variant run lands beside an existing "
             "scenario instead of overwriting it (e.g. '_bcfull')",
    )
    p.add_argument(
        "--coastal-averaging",
        default="mean",
        choices=("mean", "instant"),
        help="how D-Flow FM stage and depth are reduced to the MODFLOW coastal "
             "boundary over a coupling interval: 'mean' time-averages, weighted by "
             "the wetted fraction; 'instant' takes the end-of-interval value, which "
             "is what every scenario before 2026-08 used",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="run even if the results directory already holds a completed scenario",
    )
    p.add_argument(
        "--log-dir",
        default="../logs",
        help="where the run log is written (created if absent)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve and print the scenario, then stop without running anything",
    )
    args = p.parse_args()

    here = pl.Path(__file__).resolve().parent
    os.chdir(here)  # the notebook resolves ../common, ../swmm, ../data relative to cwd

    nb_path = here / NOTEBOOK
    if not nb_path.is_file():
        raise SystemExit(f"notebook not found: {nb_path}")

    sys.path.insert(0, str((here / "../common").resolve()))
    from liss_settings import (
        get_results_path,
        get_modflow_coupling_tag,
        get_dflow_control_path,
    )
    from swmm_mf_connect import intersect_points_grid

    # ---- preflight ---------------------------------------------------------
    # n_connections is resolved by the spatial join, not by --junctions, and the
    # scenario name / tracer bc / results path all key on it.  Resolve it here so
    # the guards below check the real scenario rather than an assumed count.
    n_connections, _, _, _, possible = intersect_points_grid(
        domain=args.domain,
        boundary_condition=args.boundary_condition,
        n_junctions=args.junctions,
        seed=args.junction_seed,
    )
    # The seed only selects anything when the draw is a subsample. Asking for the
    # whole set returns every junction whatever the seed, so a seed tag there would
    # invent a distinct scenario for an identical model.
    subsampled = n_connections < len(possible)

    tag = get_modflow_coupling_tag(args.coupling_hours)
    results_ws = get_results_path(
        args.domain, args.resolution, args.coupling_hours, n_connections
    )
    scenario = results_ws.name
    if args.smoke_days:
        scenario += f"_smoke{args.smoke_days:g}d"
        results_ws = results_ws.parent / scenario
    if args.scenario_suffix:
        scenario += args.scenario_suffix
        results_ws = results_ws.parent / scenario
    # Applied here rather than left to --scenario-suffix, because an ensemble whose
    # members are distinguished by hand is an ensemble whose members eventually
    # overwrite one another. Seed 0 is unlabelled so that every scenario produced
    # before the seed existed keeps its name.
    if subsampled and args.junction_seed != 0:
        scenario += f"_s{args.junction_seed}"
        results_ws = results_ws.parent / scenario

    # The sewer forcing is written through the API every user time step, so no
    # per-scenario series is read and none is produced.  The only file involved is
    # the base model's own Sewer_sourcesink.bc, which travels with the run
    # directory; the notebook asserts its tracersewageDelta is 1000 before running.
    base_bc = (
        get_dflow_control_path(args.domain, args.resolution).parent / "Sewer_sourcesink.bc"
    ).resolve()
    if not base_bc.is_file():
        raise SystemExit(
            f"the base model has no Sewer_sourcesink.bc: {base_bc}\n"
            "D-Flow FM will not initialize a [SourceSink] without a discharge key, "
            "and the sewage tracer concentration comes from that file."
        )

    # A completed scenario is ~18 files / ~8 GB, so make clobbering deliberate.
    existing = list(results_ws.glob("*")) if results_ws.is_dir() else []
    if existing and not args.force:
        raise SystemExit(
            f"{results_ws} already holds {len(existing)} files -- refusing to overwrite "
            f"a completed scenario. Pass --force to re-run it."
        )

    if args.dry_run:
        # Everything above is read-only, so this reports exactly what the real run
        # would do without wiping a run directory or touching the tracer forcing.
        print(f"scenario     : {scenario}")
        print(f"results ->   : {results_ws}")
        print(f"connections  : {args.junctions} requested -> {n_connections} resolved")
        print(f"coupling     : {args.coupling_hours} h  ({tag})")
        print(f"leakance     : {args.leakance} 1/d")
        print(f"smoke days   : {args.smoke_days if args.smoke_days else 'None (full run)'}")
        print(f"sewer forcing: {base_bc.name} (base model; tracersewageDelta only)")
        print(f"results dir  : {len(existing)} existing files")
        apply_overrides(notebook_source(nb_path),
                        {n: getattr(args, d) for n, d in OVERRIDES.items()})
        print("dry run OK - notebook converts and all overrides applied")
        return 0

    log_dir = (here / args.log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{scenario}_{stamp}.log"

    values = {name: getattr(args, dest) for name, dest in OVERRIDES.items()}
    src = apply_overrides(notebook_source(nb_path), values)

    # No snapshot/restore of the sewer forcing is needed any more: the run neither
    # reads a per-scenario series nor writes one, so a smoke test or a suffixed
    # variant cannot leave anything behind for the next run to pick up.

    # ---- run ---------------------------------------------------------------
    t0 = time.perf_counter()
    with open(log_path, "w", encoding="utf-8") as log:
        stdout, stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = Tee(stdout, log), Tee(stderr, log)
        try:
            print(f"scenario     : {scenario}")
            print(f"started      : {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
            print(f"log          : {log_path}")
            print(f"results ->   : {results_ws}")
            print(f"connections  : {args.junctions} requested -> {n_connections} resolved")
            print(f"coupling     : {args.coupling_hours} h  ({tag})")
            print(f"leakance     : {args.leakance} 1/d")
            print(f"smoke days   : {args.smoke_days if args.smoke_days else 'None (full run)'}")
            print(f"sewer forcing: {base_bc.name} (base model; tracersewageDelta only)")
            print("-" * 72)

            ns = {"__name__": "__main__", "__file__": str(nb_path)}
            exec(compile(src, str(nb_path), "exec"), ns)

            print("-" * 72)
            print(f"OK  {scenario}  in {(time.perf_counter() - t0) / 60.0:.1f} min")
            rc = 0
        except BaseException:
            import traceback

            print("-" * 72)
            print(f"FAILED  {scenario}  after {(time.perf_counter() - t0) / 60.0:.1f} min")
            traceback.print_exc()
            rc = 1
        finally:
            sys.stdout, sys.stderr = stdout, stderr

    print(f"\nlog: {log_path}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
