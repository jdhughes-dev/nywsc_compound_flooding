"""Statistics behind the boundary-averaging figure, and their archive file.

The archive ../../data/GP/boundary_averaging.nc is committed so the figure rebuilds
without the simulation output, which is tens of gigabytes and is not in version
control. When that output is present the archive is recomputed rather than trusted.
"""
import pathlib as pl

import numpy as np
import pandas as pd
import xarray as xr

HERE = pl.Path(__file__).resolve().parent
# docs/data/GP mirrors docs/GP, so a second manuscript brings its own data directory
# rather than sharing a flat one.
NC = HERE.parents[1] / "data" / "GP" / "boundary_averaging.nc"
RESULTS = HERE.parents[2] / "results" / "gp"

SPINUP_D = 5.0          # cold start; not a fair test of the model
M2_HOURS = 12.4206
NYQUIST_H = M2_HOURS / 2
DT_REF = 0.25 / 24
FT2MM = 304.8

# The 15-minute simulation is the finest run available and is the reference. A
# coarser one cannot serve: scoring the 30-minute simulation against it would judge
# a run by a standard it out-resolves.
REFS = {"15M instant": "gp_coarse_15.00M_n244",
        "15M mean": "gp_coarse_15.00M_n244_meanbnd"}
# 02 and 04 use the _instbnd runs, which were verified bit-identical to the
# pre-refactor results on every array.
RUNS = {
    "30.00M": (0.5 / 24, "gp_coarse_30.00M_n244", "gp_coarse_30.00M_n244_meanbnd"),
    "01.00H": (1 / 24, "gp_coarse_01.00H_n244", "gp_coarse_01.00H_n244_meanbnd"),
    "02.00H": (2 / 24, "gp_coarse_02.00H_n244_instbnd", "gp_coarse_02.00H_n244_meanbnd"),
    "04.00H": (4 / 24, "gp_coarse_04.00H_n244_instbnd", "gp_coarse_04.00H_n244_meanbnd"),
    "08.00H": (8 / 24, "gp_coarse_08.00H_n244", "gp_coarse_08.00H_n244_meanbnd"),
    "01.00D": (1.0, "gp_coarse_01.00D_n244", "gp_coarse_01.00D_n244_meanbnd"),
}

UNITS = {"head_inst": "mm", "head_mean": "mm", "seep_inst": "ft3/d",
         "seep_mean": "ft3/d", "trac_inst": "1", "trac_mean": "1",
         "peak_inst": "1", "peak_mean": "1", "head_ratio": "1",
         "seep_ratio": "1", "trac_ratio": "1"}


def required_runs():
    return list(REFS.values()) + [r for _, i, m in RUNS.values() for r in (i, m)]


def missing(results=RESULTS):
    """Run directories that are absent or incomplete."""
    out = []
    for run in required_runs():
        d = results / run
        if not all((d / f).is_file() for f in
                   ("gwf.obs.csv", "swmm_q.npz", "dflow_tracer.nc")):
            out.append(run)
    return out


def _heads(results, run):
    d = pd.read_csv(results / run / "gwf.obs.csv")
    return d["time"].to_numpy(), d.drop(columns=["time"]).to_numpy()


def _seep(results, run, dt):
    """swmm_q key jdx is the coupling step ending at (jdx+1)*dt."""
    z = np.load(results / run / "swmm_q.npz")
    ks = sorted(z.files, key=int)
    return (np.arange(len(ks)) + 1) * dt, np.array([z[k] for k in ks])


def _tracer(results, run):
    with xr.open_dataset(results / run / "dflow_tracer.nc") as d:
        return d["mesh2d_sewage"].values


def _rmse(rt, rv, t, v):
    """Reference interpolated onto the test times; the step counts differ by a
    factor of 96 between the 15-minute reference and the daily run."""
    m = t >= SPINUP_D
    t, v = t[m], v[m]
    ri = np.column_stack([np.interp(t, rt, rv[:, j]) for j in range(v.shape[1])])
    return float(np.sqrt(((v - ri) ** 2).mean()))


def compute(results=RESULTS):
    tr = {k: _tracer(results, v) for k, v in REFS.items()}
    for iv, (_, ri, rm) in RUNS.items():
        tr[f"{iv} inst"] = _tracer(results, ri)
        tr[f"{iv} mean"] = _tracer(results, rm)

    rows = []
    for rlabel, rrun in REFS.items():
        rht, rhv = _heads(results, rrun)
        rst, rsv = _seep(results, rrun, DT_REF)
        for iv, (dt, r_i, r_m) in RUNS.items():
            rows.append(dict(
                ref=rlabel, interval=iv, hours=dt * 24,
                head_inst=_rmse(rht, rhv, *_heads(results, r_i)) * FT2MM,
                head_mean=_rmse(rht, rhv, *_heads(results, r_m)) * FT2MM,
                seep_inst=_rmse(rst, rsv, *_seep(results, r_i, dt)),
                seep_mean=_rmse(rst, rsv, *_seep(results, r_m, dt)),
                trac_inst=float(np.sqrt(np.nanmean((tr[f"{iv} inst"] - tr[rlabel]) ** 2))),
                trac_mean=float(np.sqrt(np.nanmean((tr[f"{iv} mean"] - tr[rlabel]) ** 2))),
                peak_inst=float(np.nanmax(tr[f"{iv} inst"])),
                peak_mean=float(np.nanmax(tr[f"{iv} mean"])),
            ))
    stats = pd.DataFrame(rows)
    for q in ("head", "seep", "trac"):
        stats[f"{q}_ratio"] = stats[f"{q}_inst"] / stats[f"{q}_mean"]

    ds = stats.set_index(["ref", "interval"]).to_xarray()
    hours = ds["hours"].isel(ref=0).values
    ds = ds.drop_vars("hours").assign_coords(hours=("interval", hours))
    ds["hours"].attrs = {"units": "hours", "long_name": "coupling interval"}
    for v, u in UNITS.items():
        if v in ds:
            ds[v].attrs["units"] = u
    ds.attrs = {
        "title": "Coupled-solution error against a 15-minute reference, by boundary "
                 "reduction and coupling interval",
        "summary": "RMSE of the coarse-grid coupled solution relative to a 15-minute "
                   "reference, for an end-of-interval (inst) and a wetted-fraction "
                   "time-averaged (mean) reduction of the D-Flow FM coastal "
                   "boundary. Both a sampled and an averaged reference are scored; "
                   "they agree, so the comparison does not depend on that choice.",
        "source": "docs/GP/scripts/boundary_averaging_data.py",
        "grid": "coarse",
        "spinup_days_excluded": SPINUP_D,
        "m2_period_hours": M2_HOURS,
        "m2_nyquist_hours": NYQUIST_H,
        "peak_reference_concentration": float(np.nanmax(tr["15M instant"])),
    }
    return ds


def load_or_refresh(results=RESULTS, nc=NC, force=False):
    """Recompute from results/ when the runs are there, otherwise read the archive.

    Returns (dataset, source), source being 'results' or 'archive'. The caller is
    expected to report which, so a stale archive is never mistaken for fresh output.
    """
    gaps = missing(results)
    if gaps and not force:
        if not nc.is_file():
            raise FileNotFoundError(
                f"neither the archive {nc} nor the simulation output exists; "
                f"missing runs: {', '.join(gaps)}")
        # decode_timedelta=False is required, not tidiness. "hours" is a CF time
        # unit, so the hours coordinate is otherwise decoded to timedelta64 and
        # comes back as 86400000000000 for the daily interval. The refresh path
        # uses the in-memory dataset and never sees it, so this only bites the
        # reader who has the archive and not the simulation output -- which is the
        # whole audience the archive exists for.
        return xr.open_dataset(nc, decode_timedelta=False), "archive"
    ds = compute(results)
    nc.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(nc)
    return ds, "results"


if __name__ == "__main__":
    ds, src = load_or_refresh()
    print(f"{'refreshed from results/' if src == 'results' else 'read archive'}: {NC}")
    if src == "archive":
        print("  missing runs:", ", ".join(missing()))
    print(ds)
