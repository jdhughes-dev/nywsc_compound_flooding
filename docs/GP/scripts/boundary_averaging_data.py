"""Statistics behind the boundary-averaging figure, and their archive file.

The archive ../../data/GP/boundary_averaging[_<grid>].nc is committed so the figure
rebuilds without the simulation output, which is tens of gigabytes and is not in
version control. When that output is present the archive is recomputed rather than
trusted.

The same comparison is defined on more than one grid. Coarse is the default and
keeps the original archive name; a second grid writes beside it rather than over it,
so a conclusion can be checked for resolution dependence instead of assumed.
"""
import pathlib as pl
import sys

import numpy as np
import pandas as pd
import xarray as xr

HERE = pl.Path(__file__).resolve().parent
# docs/data/GP mirrors docs/GP, so a second manuscript brings its own data directory
# rather than sharing a flat one.
DATA = HERE.parents[1] / "data" / "GP"
RESULTS = HERE.parents[2] / "results" / "gp"

SPINUP_D = 5.0          # cold start; not a fair test of the model
M2_HOURS = 12.4206
NYQUIST_H = M2_HOURS / 2
DT_REF = 0.25 / 24
FT2MM = 304.8

# Interval tags and their length in days. The 15-minute run is not here because it
# is the reference; scoring it against itself would contribute a spurious zero.
TAGS = {"30.00M": 0.5 / 24, "01.00H": 1 / 24, "02.00H": 2 / 24,
        "04.00H": 4 / 24, "08.00H": 8 / 24, "01.00D": 1.0}


def _regular(prefix):
    """Scenario names for a sweep produced by run_sweep.py.

    Those are uniform -- every run carries the reduction as a --scenario-suffix --
    so the whole mapping follows from the grid prefix. The coarse sweep predates
    that convention and has to be spelled out instead.
    """
    return {t: (h, f"{prefix}_{t}_n244_instbnd", f"{prefix}_{t}_n244_meanbnd")
            for t, h in TAGS.items()}


# The 15-minute simulation is the finest run available and is the reference. A
# coarser one cannot serve: scoring the 30-minute simulation against it would judge
# a run by a standard it out-resolves. Both reductions of the reference are scored,
# because a conclusion that depends on which one is chosen is not a conclusion.
CONFIG = {
    "coarse": dict(
        archive="boundary_averaging.nc",
        refs={"15M instant": "gp_coarse_15.00M_n244",
              "15M mean": "gp_coarse_15.00M_n244_meanbnd"},
        # 02 and 04 use the _instbnd runs, which were verified bit-identical to the
        # pre-refactor results on every array.
        runs={
            "30.00M": (0.5 / 24, "gp_coarse_30.00M_n244", "gp_coarse_30.00M_n244_meanbnd"),
            "01.00H": (1 / 24, "gp_coarse_01.00H_n244", "gp_coarse_01.00H_n244_meanbnd"),
            "02.00H": (2 / 24, "gp_coarse_02.00H_n244_instbnd", "gp_coarse_02.00H_n244_meanbnd"),
            "04.00H": (4 / 24, "gp_coarse_04.00H_n244_instbnd", "gp_coarse_04.00H_n244_meanbnd"),
            "08.00H": (8 / 24, "gp_coarse_08.00H_n244", "gp_coarse_08.00H_n244_meanbnd"),
            "01.00D": (1.0, "gp_coarse_01.00D_n244", "gp_coarse_01.00D_n244_meanbnd"),
        },
    ),
    # The midres sweep also predates the --scenario-suffix convention, so its
    # instantaneous runs are the unsuffixed ones, uniformly -- unlike coarse, which
    # was partly re-run under the suffix while the reduction was being refactored.
    "medium": dict(
        archive="boundary_averaging_medium.nc",
        refs={"15M instant": "gp_medium_15.00M_n244",
              "15M mean": "gp_medium_15.00M_n244_meanbnd"},
        runs={t: (h, f"gp_medium_{t}_n244", f"gp_medium_{t}_n244_meanbnd")
              for t, h in TAGS.items()},
    ),
    "high": dict(
        archive="boundary_averaging_high.nc",
        refs={"15M instant": "gp_high_15.00M_n244_instbnd",
              "15M mean": "gp_high_15.00M_n244_meanbnd"},
        runs=_regular("gp_high"),
    ),
}
DEFAULT_GRID = "coarse"

UNITS = {"head_inst": "mm", "head_mean": "mm", "seep_inst": "ft3/d",
         "seep_mean": "ft3/d", "trac_inst": "1", "trac_mean": "1",
         "peak_inst": "1", "peak_mean": "1", "head_ratio": "1",
         "seep_ratio": "1", "trac_ratio": "1", "p9999_inst": "1",
         "p9999_mean": "1", "p999_inst": "1", "p999_mean": "1"}

# The reported peak is a max over the whole space-time field, and a max is the least
# robust statistic available. On the coarse mesh it lands in cell 1669 in every one
# of the twelve runs, at 7.9x the 99.99th percentile; on the highres mesh it lands in
# one of two cells at 54x. So the peak is a single-cell hot spot, and these
# percentiles are carried beside it as the field-wide amplitude it is not.
PCTL = (99.99, 99.9)


def archive_path(grid=DEFAULT_GRID):
    return DATA / CONFIG[grid]["archive"]


def required_runs(grid=DEFAULT_GRID):
    cfg = CONFIG[grid]
    return (list(cfg["refs"].values())
            + [r for _, i, m in cfg["runs"].values() for r in (i, m)])


def missing(results=RESULTS, grid=DEFAULT_GRID):
    """Run directories that are absent or incomplete."""
    out = []
    for run in required_runs(grid):
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


def _field_rmse(a, b, block=512):
    """RMSE between two tracer fields, accumulated over blocks of timesteps.

    A whole-array `(a - b) ** 2` needs two temporaries the size of the inputs. On
    the highres mesh each field is 2.8 GB, so that alone is 8.4 GB resident on top
    of the fields themselves; blocking keeps the temporaries negligible and the
    result is the same sum.
    """
    total, count = 0.0, 0
    for s in range(0, a.shape[0], block):
        d = a[s:s + block] - b[s:s + block]
        np.square(d, out=d)
        total += float(np.nansum(d))
        count += int(np.count_nonzero(~np.isnan(d)))
    return float(np.sqrt(total / count))


def _amplitudes(a):
    """Max and upper-tail percentiles of a tracer field.

    overwrite_input lets the percentile partition in place. That destroys the
    array, so the max is taken first and the caller must be done with it -- worth
    the care because the alternative is a second 2.8 GB copy on the highres mesh.
    """
    mx = float(np.nanmax(a))
    p = np.nanpercentile(a.ravel(), PCTL, overwrite_input=True)
    return (mx, *(float(x) for x in p))


def _tracer_stats(results, runs, refs):
    """Peak, upper-tail amplitude, and per-reference RMSE for every run under test.

    The reference fields stay resident and each test field is loaded once, scored
    against both, and released. Holding all fourteen fields at once is 6.2 GB on
    the coarse mesh but 39 GB on the highres one -- more than the machine has --
    and the peak here is instead three fields.
    """
    ref = {k: _tracer(results, v) for k, v in refs.items()}
    out = {}
    for iv, (_, r_i, r_m) in runs.items():
        for kind, run in (("inst", r_i), ("mean", r_m)):
            a = _tracer(results, run)
            # RMSE first: _amplitudes consumes the array.
            for rlabel in refs:
                out[iv, kind, rlabel] = _field_rmse(a, ref[rlabel])
            (out[iv, kind, "peak"], out[iv, kind, "p9999"],
             out[iv, kind, "p999"]) = _amplitudes(a)
            del a
    # Last, because scoring every run above needs the references intact.
    reference = _amplitudes(ref[next(iter(refs))])
    return out, reference


def compute(results=RESULTS, grid=DEFAULT_GRID):
    cfg = CONFIG[grid]
    refs, runs = cfg["refs"], cfg["runs"]
    trac, (peak_ref, p9999_ref, p999_ref) = _tracer_stats(results, runs, refs)

    rows = []
    for rlabel, rrun in refs.items():
        rht, rhv = _heads(results, rrun)
        rst, rsv = _seep(results, rrun, DT_REF)
        for iv, (dt, r_i, r_m) in runs.items():
            rows.append(dict(
                ref=rlabel, interval=iv, hours=dt * 24,
                head_inst=_rmse(rht, rhv, *_heads(results, r_i)) * FT2MM,
                head_mean=_rmse(rht, rhv, *_heads(results, r_m)) * FT2MM,
                seep_inst=_rmse(rst, rsv, *_seep(results, r_i, dt)),
                seep_mean=_rmse(rst, rsv, *_seep(results, r_m, dt)),
                trac_inst=trac[iv, "inst", rlabel],
                trac_mean=trac[iv, "mean", rlabel],
                peak_inst=trac[iv, "inst", "peak"],
                peak_mean=trac[iv, "mean", "peak"],
                p9999_inst=trac[iv, "inst", "p9999"],
                p9999_mean=trac[iv, "mean", "p9999"],
                p999_inst=trac[iv, "inst", "p999"],
                p999_mean=trac[iv, "mean", "p999"],
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
        "summary": f"RMSE of the {grid}-grid coupled solution relative to a 15-minute "
                   "reference, for an end-of-interval (inst) and a wetted-fraction "
                   "time-averaged (mean) reduction of the D-Flow FM coastal "
                   "boundary. Both a sampled and an averaged reference are scored; "
                   "they agree, so the comparison does not depend on that choice. "
                   "peak_* is a single-cell max and p9999_*/p999_* are the "
                   "field-wide amplitude; they do not tell the same story.",
        "source": "docs/GP/scripts/boundary_averaging_data.py",
        "grid": grid,
        "spinup_days_excluded": SPINUP_D,
        "m2_period_hours": M2_HOURS,
        "m2_nyquist_hours": NYQUIST_H,
        "peak_reference_concentration": peak_ref,
        "p9999_reference_concentration": p9999_ref,
        "p999_reference_concentration": p999_ref,
    }
    return ds


def load_or_refresh(results=RESULTS, nc=None, force=False, grid=DEFAULT_GRID):
    """Recompute from results/ when the runs are there, otherwise read the archive.

    Returns (dataset, source), source being 'results' or 'archive'. The caller is
    expected to report which, so a stale archive is never mistaken for fresh output.
    """
    nc = archive_path(grid) if nc is None else nc
    gaps = missing(results, grid)
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
    ds = compute(results, grid)
    nc.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(nc)
    return ds, "results"


if __name__ == "__main__":
    grid = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GRID
    ds, src = load_or_refresh(grid=grid)
    print(f"{'refreshed from results/' if src == 'results' else 'read archive'}: "
          f"{archive_path(grid)}")
    if src == "archive":
        print("  missing runs:", ", ".join(missing(grid=grid)))
    print(ds)
