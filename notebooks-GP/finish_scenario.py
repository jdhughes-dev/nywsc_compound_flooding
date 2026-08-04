#!/usr/bin/env python
"""Redo the post-run steps of step2 without re-running the coupled model.

The coupling loop is the expensive part -- 4 to 6 hours -- and it saves the
MODFLOW, SWMM and exchange-array results as soon as it finishes.  What comes
after is cheap by comparison but not free: trimming FlowFM_map.nc down to the
tracer file, and extracting the source-sink records out of FlowFM_his.nc.  Losing
the process anywhere in that tail leaves a scenario that is complete in every
expensive respect and unusable in the cheap ones.

That has happened twice.  The highres 08.00H run finished its 267 coupling steps
and died while writing dflow_tracer.nc; the highres 15.00M run finished all 8,544
steps and died six seconds into the same write, leaving a 48-byte stub.  Both
times FlowFM_map.nc was intact and complete, so nothing about the simulation
needed repeating -- only the post-processing.

This script is that post-processing, lifted from the notebook's final cells and
kept deliberately identical to them: same tracer variables, same UGRID write.  It
reads FlowFM_map.nc and FlowFM_his.nc from the run that already happened.

Usage
-----
    cd notebooks-GP
    python -u finish_scenario.py                          # highres 15-min scenario
    python -u finish_scenario.py --resolution medium --coupling-hours 4

Both steps are idempotent and skip themselves if their output already looks good,
so re-running after a partial recovery is safe.  --force redoes them anyway.
"""

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import argparse
import pathlib as pl
import sys

# The three fields the step3 notebooks read.  The full map carries ~30 variables;
# trimming is what takes a highres scenario from ~67 GB to ~8 GB.
TRACER_VARS = ("mesh2d_sewage", "mesh2d_waterdepth", "mesh2d_s1")

def extract_tracer(map_path, tracer_out, force):
    """Trim FlowFM_map.nc to the tracer file and verify it reopens as UGRID."""
    import xugrid

    # "Already done" means the file REOPENS AS UGRID, not that it is non-empty.  A
    # write killed in progress leaves a 48-byte netCDF header stub, which any
    # size-based guard happily accepts -- and the scenario then looks complete while
    # carrying an unreadable tracer.  That is exactly what happened on the first
    # recovery attempt for gp_high_15.00M_n244.
    if tracer_out.is_file() and not force:
        try:
            chk = xugrid.open_dataset(tracer_out)
            ncell = chk["mesh2d_nFaces"].size
            chk.close()
            print(f"tracer: {tracer_out.name} already valid "
                  f"({ncell:,} cells, {tracer_out.stat().st_size / 1e9:.2f} GB) - skipping")
            return
        except Exception as exc:
            print(f"tracer: {tracer_out.name} exists but is not readable as UGRID "
                  f"({type(exc).__name__}: {exc}) - rebuilding")

    if not map_path.is_file():
        raise SystemExit(
            f"FlowFM_map.nc not found at {map_path}. Without it the tracer cannot be "
            "rebuilt and the scenario must be re-run."
        )

    src_gb = map_path.stat().st_size / 1e9
    print(f"tracer: reading {map_path.name} ({src_gb:,.1f} GB) ...")
    ds = xugrid.open_dataset(map_path)
    keep = [v for v in TRACER_VARS if v in ds]
    missing = [v for v in TRACER_VARS if v not in ds]
    if missing:
        print(f"  WARNING: absent from the map file: {missing}")

    # MUST be .ugrid.to_netcdf(): a plain .to_netcdf() writes the data and the face
    # coordinates but DROPS the UGRID topology variable, and the result then fails
    # to reopen with "does not contain UGRID conventions data" -- which is exactly
    # what the step3 notebooks need to build the mesh.
    ds[keep].ugrid.to_netcdf(tracer_out)
    ds.close()

    # Verify before anyone deletes the 67 GB source on the strength of this file.
    chk = xugrid.open_dataset(tracer_out)
    ncell = chk["mesh2d_nFaces"].size
    ntime = chk.sizes.get("time", "?")
    chk.close()
    print(f"tracer: wrote {tracer_out}")
    print(f"  {keep}")
    print(f"  {ncell:,} cells, {ntime} times, "
          f"{tracer_out.stat().st_size / 1e9:,.2f} GB (from {src_gb:,.1f} GB)")
    print("  reopened as UGRID OK")


def extract_source_sink(dflow_working, results_ws, force):
    """Copy the source-sink records out of FlowFM_his.nc into a small file.

    D-Flow FM already records what the sewer source actually delivered --
    prescribed and current discharge, cumulative volume, the per-his-interval
    average, and the domain water-balance term. That is the authoritative record
    of the tracer inflow, better than anything reconstructed afterwards, but it
    lives in an 80+ MB his file that step2 does not copy into results/.

    Keeping the whole his file per scenario would add ~1.7 GB across the sweep for
    a handful of series, so only the source_sink variables are kept. Compressed
    that is well under 1 MB against 82.9 MB for the full file.
    """
    import xarray as xr

    out = results_ws / "source_sink_his.nc"
    if out.is_file() and not force:
        print(f"source sink: {out.name} already present "
              f"({out.stat().st_size / 1e6:.2f} MB) - skipping")
        return

    his = dflow_working / "output" / "FlowFM_his.nc"
    if not his.is_file():
        print(f"source sink: no his file at {his} - skipping")
        return

    ds = xr.open_dataset(his)
    keep = [v for v in ds.variables
            if v.startswith("source_sink") or v == "water_balance_source_sink"]
    if not keep:
        print(f"source sink: no source_sink variables in {his.name} - skipping")
        ds.close()
        return

    sub = ds[keep]
    # Chunk sizes MUST be set explicitly. xarray otherwise inherits the his file's
    # own chunk layout, which is tuned for that file's shape and is pathological for
    # a (ntime, 1) slice: writing with inherited chunks gives 6.1 MB, and turning on
    # zlib without fixing them makes it WORSE at 6.8 MB -- both far above the 1.2 MB
    # of actual data. With a sane time chunk it comes out at 0.61 MB.
    enc = {}
    for v in sub.data_vars:
        if sub[v].dtype.kind != "f" or not sub[v].shape:
            continue
        chunks = tuple(min(s, 4096) if i == 0 else s
                       for i, s in enumerate(sub[v].shape))
        enc[v] = {"zlib": True, "complevel": 4, "chunksizes": chunks}
    sub.to_netcdf(out, encoding=enc)
    ds.close()
    print(f"source sink: wrote {out.name} "
          f"({out.stat().st_size / 1e6:.2f} MB from {his.stat().st_size / 1e6:.1f} MB), "
          f"{len(keep)} variables")


def main():
    p = argparse.ArgumentParser(
        description="Rebuild the tracer file and sewer forcing for an already-run scenario.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--domain", default="gp")
    p.add_argument("--boundary-condition", default="chd", choices=("chd", "ghb"))
    p.add_argument("--resolution", default="high", choices=("coarse", "medium", "high"))
    p.add_argument("--coupling-hours", type=float, default=0.25)
    p.add_argument("--junctions", type=int, default=500)
    p.add_argument("--outfall", default="O3",
                   help="SWMM outfall driving the D-Flow tracer")
    p.add_argument("--scenario-suffix", default="",
                   help="append to the scenario id, matching run_scenario.py's "
                        "--scenario-suffix, so a variant run can be finished too")
    p.add_argument("--force", action="store_true",
                   help="redo both steps even if their outputs already exist")
    p.add_argument("--skip-tracer", action="store_true")
    p.add_argument("--skip-source-sink", action="store_true")
    args = p.parse_args()

    here = pl.Path(__file__).resolve().parent
    os.chdir(here)
    sys.path.insert(0, str((here / "../common").resolve()))
    from liss_settings import (
        get_results_path,
        get_modflow_coupling_tag,
        get_dflow_control_path,
    )
    from swmm_mf_connect import intersect_points_grid

    n_connections = intersect_points_grid(
        domain=args.domain,
        boundary_condition=args.boundary_condition,
        n_junctions=args.junctions,
    )[0]
    tag = get_modflow_coupling_tag(args.coupling_hours)
    results_ws = get_results_path(
        args.domain, args.resolution, args.coupling_hours, n_connections
    )
    scenario = results_ws.name
    if args.scenario_suffix:
        # Mirror step2: the suffix is appended to the scenario id, so it renames the
        # results directory AND both run directories.
        scenario += args.scenario_suffix
        results_ws = results_ws.parent / scenario

    if not results_ws.is_dir():
        raise SystemExit(
            f"{results_ws} does not exist - there is no completed run to finish."
        )

    # Resolve the run directory exactly as the notebook does -- via liss_settings and
    # then a sibling of the base scenario dir.  The directory name does NOT track the
    # resolution keyword ('high' lives under dflow-fm/highres/), so building the path
    # from the keyword would silently miss.
    dflow_base = get_dflow_control_path(args.domain, args.resolution).parent.resolve()
    dflow_working = (dflow_base.parent / f"run_{scenario}").resolve()
    map_path = dflow_working / "output" / "FlowFM_map.nc"

    print(f"scenario : {scenario}")
    print(f"results  : {results_ws}")
    print(f"run dir  : {dflow_working}")
    print("-" * 72)

    if not args.skip_tracer:
        extract_tracer(map_path, results_ws / "dflow_tracer.nc", args.force)
    if not args.skip_source_sink:
        extract_source_sink(dflow_working, results_ws, args.force)

    print("-" * 72)
    files = sorted(results_ws.glob("*"))
    total = sum(f.stat().st_size for f in files) / 1e9
    print(f"{scenario}: {len(files)} files, {total:,.2f} GB")
    # A killed write leaves a header stub, not a zero-byte file, so flag anything
    # implausibly small rather than only the empty case.
    stubs = [f"{f.name} ({f.stat().st_size} B)" for f in files if f.stat().st_size < 1024]
    if stubs:
        print(f"  WARNING: truncated or stub files present: {stubs}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
