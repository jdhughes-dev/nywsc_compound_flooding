#!/usr/bin/env python
"""Re-run a resolution's coupling-interval sweep, one scenario at a time.

Restartable by design.  A full sweep is many hours -- roughly 40 min per coarse
scenario and 100 min per midres one -- and this machine has hard-crashed under that
load more than once, so the driver is written to be re-launched rather than to be
babysat.  Re-running it skips every scenario that is already finished and picks up
where it left off; at most the scenario in flight is lost.

"Finished" means the results directory holds a mfsim.lst reporting the MODFLOW
version this run would use.  That is what makes a restart safe after the binaries
change: a scenario left over from an older MODFLOW is re-run rather than skipped.

Each scenario is handled in four steps:

  1. If a previous result exists at the canonical name and has not been preserved,
     rename it aside rather than letting run_scenario.py overwrite it.  Renaming
     costs nothing and results/ is not under version control, so an overwrite would
     be unrecoverable.
  2. Run it.
  3. Extract the source-sink records out of the his file.
  4. Delete FlowFM_map.nc once dflow_tracer.nc has been verified to reopen as
     UGRID.  Left in place these are ~11 GB per coarse scenario and ~25 GB per
     midres one, which would exhaust the disk long before the sweep finished.

A scenario that fails is logged and the sweep continues to the next one.

Usage
-----
    cd notebooks-GP
    python -u run_sweep.py --resolution coarse
    python -u run_sweep.py --resolution coarse medium
    python -u run_sweep.py --resolution high --dry-run
"""

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import argparse
import datetime
import pathlib as pl
import shutil
import subprocess
import sys
import time

HERE = pl.Path(__file__).resolve().parent

# Coarsest first: the cheap scenarios surface a problem before hours are spent.
COUPLING_HOURS = [24.0, 8.0, 4.0, 2.0, 1.0, 0.5, 0.25]

PRESERVE_SUFFIX = "_mf650bc"


def modflow_version_of(results_ws):
    """MODFLOW version string recorded in a finished scenario, or None."""
    lst = results_ws / "mfsim.lst"
    if not lst.is_file():
        return None
    for line in lst.read_text(errors="replace").splitlines()[:20]:
        if "VERSION 6" in line:
            return line.strip()
    return None


def target_version():
    """The version the next run will use, from the library run_scenario resolves."""
    sys.path.insert(0, str((HERE / "../common").resolve()))
    from liss_settings import libmf6

    exe = libmf6.parent / ("mf6.exe" if os.name == "nt" else "mf6")
    if not exe.is_file():
        return None
    try:
        out = subprocess.run([str(exe), "-v"], capture_output=True, text=True,
                             timeout=60).stdout
        for tok in out.split():
            if tok.count(".") == 2 and tok[0].isdigit():
                return tok
    except Exception:
        pass
    return None


def tracer_is_valid(results_ws):
    import xugrid

    p = results_ws / "dflow_tracer.nc"
    if not p.is_file():
        return False
    try:
        ds = xugrid.open_dataset(p)
        ds["mesh2d_nFaces"].size
        ds.close()
        return True
    except Exception:
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resolution", nargs="+", default=["coarse"],
                   choices=("coarse", "medium", "high"))
    p.add_argument("--domain", default="gp")
    p.add_argument("--junctions", type=int, default=500)
    p.add_argument("--coastal-averaging", default="mean",
                   choices=("mean", "instant"),
                   help="how D-Flow FM stage and depth are reduced to the MODFLOW "
                        "coastal boundary over a coupling interval")
    p.add_argument("--scenario-suffix", default="",
                   help="append to every scenario id, so a sweep under one "
                        "reduction lands beside a sweep under the other")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would run, and stop")
    p.add_argument("--keep-map", action="store_true",
                   help="do not delete FlowFM_map.nc after the tracer is verified")
    args = p.parse_args()

    os.chdir(HERE)
    sys.path.insert(0, str((HERE / "../common").resolve()))
    from liss_settings import (get_results_path, get_modflow_coupling_tag,
                               get_dflow_control_path)
    from swmm_mf_connect import intersect_points_grid

    n_conn = intersect_points_grid(domain=args.domain, boundary_condition="chd",
                                   n_junctions=args.junctions)[0]
    want = target_version()
    print(f"MODFLOW version the runs will use: {want or 'unknown'}")
    print(f"connections: {args.junctions} requested -> {n_conn} resolved\n")

    todo, done = [], []
    for res in args.resolution:
        for hours in COUPLING_HOURS:
            ws = get_results_path(args.domain, res, hours, n_conn)
            # The suffix has to reach the results path, not just run_scenario.py.
            # "Finished" is decided by the MODFLOW version found in this directory,
            # so without it a sweep under a second reduction would look at the first
            # one's output, find the target version, and skip every scenario.
            if args.scenario_suffix:
                ws = ws.parent / (ws.name + args.scenario_suffix)
            have = modflow_version_of(ws)
            if have and want and want in have:
                done.append((res, hours, ws, have))
            else:
                todo.append((res, hours, ws, have))

    for res, hours, ws, have in done:
        print(f"  skip  {ws.name:<26} already at {have}")
    print()
    for res, hours, ws, have in todo:
        print(f"  RUN   {ws.name:<26} currently {have or 'not run'}")
    print(f"\n{len(todo)} to run, {len(done)} already current")

    if args.dry_run or not todo:
        return 0

    t_sweep = time.perf_counter()
    failed = []
    for i, (res, hours, ws, _) in enumerate(todo, 1):
        tag = get_modflow_coupling_tag(hours)
        print("\n" + "=" * 74)
        print(f"[{i}/{len(todo)}] {ws.name}   {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
        print("=" * 74, flush=True)

        # 1. preserve any prior result -- results/ is not version controlled
        preserved = ws.parent / (ws.name + PRESERVE_SUFFIX)
        if ws.is_dir() and any(ws.iterdir()) and not preserved.exists():
            shutil.move(str(ws), str(preserved))
            print(f"  preserved prior result -> {preserved.name}", flush=True)
        elif ws.is_dir() and preserved.exists():
            shutil.rmtree(ws)
            print(f"  prior result already preserved; removed the retry leftover",
                  flush=True)

        # 2. run
        t0 = time.perf_counter()
        rc = subprocess.run(
            [sys.executable, "-u", "run_scenario.py",
             "--resolution", res, "--coupling-hours", str(hours),
             "--junctions", str(args.junctions), "--domain", args.domain,
             "--coastal-averaging", args.coastal_averaging,
             "--scenario-suffix", args.scenario_suffix],
            cwd=str(HERE),
        ).returncode
        mins = (time.perf_counter() - t0) / 60.0
        if rc != 0:
            print(f"  FAILED after {mins:.1f} min (exit {rc}) - continuing", flush=True)
            failed.append(ws.name)
            continue
        print(f"  ran in {mins:.1f} min", flush=True)

        # 3. source-sink records
        subprocess.run(
            [sys.executable, "-u", "finish_scenario.py",
             "--resolution", res, "--coupling-hours", str(hours),
             "--junctions", str(args.junctions), "--domain", args.domain,
             "--scenario-suffix", args.scenario_suffix, "--skip-tracer"],
            cwd=str(HERE),
        )

        # 4. reclaim the map file, but only against a verified tracer
        if not args.keep_map:
            base = get_dflow_control_path(args.domain, res).parent.resolve()
            mapf = base.parent / f"run_{ws.name}" / "output" / "FlowFM_map.nc"
            if not mapf.is_file():
                print("  no FlowFM_map.nc to remove", flush=True)
            elif tracer_is_valid(ws):
                gb = mapf.stat().st_size / 1e9
                mapf.unlink()
                print(f"  removed FlowFM_map.nc ({gb:,.1f} GB), tracer verified",
                      flush=True)
            else:
                print("  KEEPING FlowFM_map.nc - dflow_tracer.nc did not reopen as "
                      "UGRID, so the run still needs recovering", flush=True)

    print("\n" + "=" * 74)
    print(f"sweep finished in {(time.perf_counter() - t_sweep) / 60.0:.1f} min")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
