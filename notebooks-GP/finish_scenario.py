#!/usr/bin/env python
"""Redo the two post-run steps of step2 without re-running the coupled model.

The coupling loop is the expensive part -- 4 to 6 hours -- and it saves the
MODFLOW, SWMM and exchange-array results as soon as it finishes.  What comes
after is cheap by comparison but not free: trimming FlowFM_map.nc down to the
tracer file, then regenerating the scenario's sewer forcing from the SWMM output.
Losing the process anywhere in that tail leaves a scenario that is complete in
every expensive respect and unusable in the two cheap ones.

That has now happened twice.  The highres 08.00H run finished its 267 coupling
steps and died while writing dflow_tracer.nc; the highres 15.00M run finished all
8,544 steps at 17:42 and died six seconds into the same write, leaving a 0-byte
dflow_tracer.nc and no .bc.  Both times FlowFM_map.nc was intact and complete, so
nothing about the simulation needed repeating -- only the post-processing.

This script is that post-processing, lifted from the notebook's final cells and
kept deliberately identical to them: same tracer variables, same UGRID write, same
splice rule, same authoritative .bc location.  It reads FlowFM_map.nc and
swmm/<domain>/<domain>_sewer.out from the run that already happened.

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
import datetime
import pathlib as pl
import shutil
import sys

# The three fields the step3 notebooks read.  The full map carries ~30 variables;
# trimming is what takes a highres scenario from ~67 GB to ~8 GB.
TRACER_VARS = ("mesh2d_sewage", "mesh2d_waterdepth", "mesh2d_s1")

TRACER_CONC = 1000.0  # kg/m3 sewage tracer, matching update_files.py


def read_bc(path):
    """Read a Sewer_sourcesink .bc back as (times, discharge, tracer).

    Mirrors write_bc: a [General] header then two [Forcing] blocks sharing one
    time column -- sourcesink_discharge first, then sourcesink_tracersewageDelta.
    Copied from the notebook so the splice below behaves identically.
    """
    blocks, cur = [], None
    for line in pl.Path(path).read_text().splitlines():
        s = line.strip()
        if s.startswith("[Forcing]"):
            cur = []
            blocks.append(cur)
            continue
        if cur is None or not s or "=" in s or s.startswith("["):
            continue
        parts = s.split()
        if len(parts) >= 2:
            try:
                cur.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    assert len(blocks) == 2, f"{path}: expected 2 [Forcing] blocks, found {len(blocks)}"
    t0 = [t for t, _ in blocks[0]]
    t1 = [t for t, _ in blocks[1]]
    assert t0 == t1, f"{path}: the two [Forcing] blocks have different time columns"
    return t0, [v for _, v in blocks[0]], [v for _, v in blocks[1]]


def read_mdu(path):
    cfg = {}
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = [s.strip() for s in line.split("=", 1)]
        cfg[k.lower()] = v.split("#")[0].strip()
    return cfg


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


def regenerate_bc(args, here, results_ws, dflow_working, n_connections, tag, force):
    """Rebuild the scenario sewer forcing from this run's SWMM output."""
    import pyswmm
    from swmm.toolkit.shared_enum import NodeAttribute

    sys.path.append(str((here / f"../data/{args.domain.upper()}").resolve()))
    from update_files import write_bc, source_id, ref_time

    tracer_dir = (here / f"../data/{args.domain.upper()}").resolve()
    bc_out = tracer_dir / f"Sewer_sourcesink_{args.resolution}_n{n_connections:03d}__{tag}.bc"
    seed = tracer_dir / f"Sewer_sourcesink_n{n_connections:03d}__{tag}.bc"

    if bc_out.is_file() and not force:
        print(f"bc: {bc_out.name} already present - skipping")
        return

    # The splice source is whatever the RUN read, which for a first run of a
    # scenario is the seed.  If bc_out already exists this is a re-run and it is
    # its own source, matching the notebook's iteration rule.
    src = bc_out if bc_out.is_file() else seed
    if not src.is_file():
        raise SystemExit(f"no tracer forcing to splice against: {src}")

    mdu = read_mdu(dflow_working / "FlowFM.mdu")
    ref = datetime.datetime.strptime(mdu["refdate"].split()[0], "%Y%m%d")
    fmt = "%Y%m%d%H%M%S"
    # get_start_time()/get_end_time() return seconds since RefDate, which is exactly
    # StartDateTime/StopDateTime measured from it -- so the window is recoverable
    # from the .mdu without the BMI.
    t0 = (datetime.datetime.strptime(mdu["startdatetime"], fmt) - ref).total_seconds()
    t1 = (datetime.datetime.strptime(mdu["stopdatetime"], fmt) - ref).total_seconds()

    ref_cfg = datetime.datetime.strptime(ref_time, "%Y-%m-%d %H:%M:%S")
    assert ref_cfg == ref, (
        f"update_files.ref_time ({ref_cfg}) must match the D-Flow RefDate ({ref}); "
        "otherwise the .bc time column is offset from the model clock"
    )

    swmm_out = (here / f"../swmm/{args.domain}/{args.domain}_sewer.out").resolve()
    if not swmm_out.is_file():
        raise SystemExit(
            f"{swmm_out} not found. The notebook deletes it at the START of a run, so "
            "it only exists if the run that produced this scenario was the last one."
        )

    # gp_sewer.inp declares FLOW_UNITS CMS, so TOTAL_INFLOW is already m3/s.
    with pyswmm.Output(str(swmm_out)) as out:
        series = out.node_series(args.outfall, NodeAttribute.TOTAL_INFLOW)
        new_times = [(t - ref).total_seconds() for t in series.keys()]
        new_q = list(series.values())

    # Splice rather than replace: this run simulated only the D-Flow window, so keep
    # whatever the source held outside it.
    old_times, old_q, _ = read_bc(src)
    merged = [(t, q) for t, q in zip(old_times, old_q) if t < t0 or t > t1]
    inside = [(t, q) for t, q in zip(new_times, new_q) if t0 <= t <= t1]
    merged.extend(inside)
    merged.sort(key=lambda r: r[0])

    times = [t for t, _ in merged]
    discharge = [q for _, q in merged]
    assert times == sorted(times), "spliced time column is not monotonic"
    assert len(set(times)) == len(times), "spliced time column has duplicates"
    if not inside:
        raise SystemExit(
            "no SWMM points fell inside the D-Flow window - the .out does not "
            "correspond to this scenario's run"
        )

    write_bc(bc_out, source_id, times, discharge, [TRACER_CONC] * len(times),
             ref_time=ref_time)
    shutil.copy2(bc_out, results_ws / bc_out.name)

    print(f"bc: wrote {bc_out}")
    print(f"  copy for the record -> {results_ws / bc_out.name}")
    print(f"  outfall {args.outfall}; {len(inside):,} new points inside the window, "
          f"{len(merged) - len(inside):,} kept from {src.name} outside it")
    print(f"  window     {t0:>15,.0f} -> {t1:>15,.0f} s since {ref_time}")
    print(f"  file spans {times[0]:>15,.0f} -> {times[-1]:>15,.0f} s "
          f"({(times[-1] - times[0]) / 86400.0:.1f} d, {len(times):,} points)")
    if times[0] > t0:
        print(f"  WARNING: series starts {(times[0] - t0) / 86400.0:.2f} d after the "
              "D-Flow window opens")
    if times[-1] < t1:
        print(f"  WARNING: series ends {(t1 - times[-1]) / 86400.0:.2f} d before the "
              "D-Flow window closes")


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
    p.add_argument("--force", action="store_true",
                   help="redo both steps even if their outputs already exist")
    p.add_argument("--skip-tracer", action="store_true")
    p.add_argument("--skip-bc", action="store_true")
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
    if not args.skip_bc:
        regenerate_bc(args, here, results_ws, dflow_working, n_connections, tag, args.force)
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
