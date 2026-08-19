"""Start-phase experiment: does the start instant decide which representation wins?

Section 9.1 says that which of sampling and averaging is more accurate below the
Nyquist limit is a property of the two and not of the instant the run begins. That
is argued from the boundary water level, which is not what the claim is about, so
docs/GP/START_PHASE_EXPERIMENT.md sets out a coupled test of it: three start
instants besides the production control, at 4- and 6-hour coupling, under both
representations, each scored against its own 15-minute reference.

This module reduces those runs to the few dozen numbers the claim turns on -- the
root-mean-square head error against that start's own reference, the mean of that
error, and the same two for aquifer-sewer seepage -- and archives them, so the run
directories can be deleted. They are tens of gigabytes and are not worth keeping.

Two things decide whether a number here means anything.

A run is only ever compared against a 15-minute reference begun at the same
instant. MODFLOW's clock is relative, so t=0 is each run's own start, and comparing
a shifted run against the production reference would difference two calendars and
report the result as error. That is the mistake this experiment is most able to
make, and it is why every start carries its own reference.

And the shifted runs are shorter than the control: the stop is held while the start
moves later, so a start 11 h later has 88.53 days against the control's 89. Errors
are therefore compared within a start and never across, which is all the sign test
needs.
"""
import pathlib as pl
import sys

import numpy as np
import pandas as pd
import xarray as xr

# The control's scenario names live in CONFIG, which already records which
# directory holds which representation on the coarse grid, including the places
# where that naming is not uniform. Two tables that must agree is one too many.
sys.path.insert(0, str(pl.Path(__file__).resolve().parent))
import boundary_averaging_data as bad          # noqa: E402

HERE = pl.Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data" / "GP"
NC = DATA / "start_phase.nc"
RESULTS = HERE.parents[2] / "results" / "gp"

GRID = "coarse"
SPINUP_D = bad.SPINUP_D
FT2MM = 304.8
FT3_TO_M3 = 0.028316846592
REF_HOURS = 0.25

# Start tags as run_scenario.py forms them, _t<HHMM>. The control is the production
# run and carries no tag, so it is mapped through CONFIG rather than by pattern.
CONTROL = "1200"
STARTS = {
    CONTROL: (None, "production control, 89.00 d"),
    "2320": ("20100101232000", "worst for sampling at 6 h, 88.53 d"),
    "1525": ("20100101152500", "best for sampling at 6 h, 88.86 d"),
    "1920": ("20100101192000", "intermediate phase, 88.69 d"),
}
INTERVALS = {"04.00H": 4.0, "06.00H": 6.0}
REPS = {"sampled": "_instbnd", "averaged": "_meanbnd"}


def scenario(start_tag, interval_tag, rep):
    """Scenario id for one cell of the matrix, the control included."""
    if start_tag == CONTROL:
        cfg = bad.CONFIG[GRID]
        if interval_tag == "15.00M":
            return cfg["refs"]["15M instant" if rep == "sampled" else "15M mean"]
        _, inst, mean = cfg["runs"][interval_tag]
        return inst if rep == "sampled" else mean
    return f"gp_{GRID}_{interval_tag}_n244{REPS[rep]}_t{start_tag}"


def required_runs():
    out = []
    for s in STARTS:
        out.append(scenario(s, "15.00M", "sampled"))
        for iv in INTERVALS:
            out += [scenario(s, iv, r) for r in REPS]
    return out


def missing(results=RESULTS):
    """Scenarios that are absent or did not finish."""
    return [r for r in required_runs()
            if not all((results / r / f).is_file()
                       for f in ("gwf.obs.csv", "swmm_q.npz"))]


def _error(ref_t, ref_v, t, v, scale):
    """Root-mean-square error and mean error against an interpolated reference.

    The same convention as boundary_averaging_data._rmse -- the reference is
    interpolated onto the test times and the spin-up is dropped -- with the mean
    returned as well, because the bias is what separates the two representations
    below the Nyquist limit.
    """
    m = t >= SPINUP_D
    t, v = t[m], v[m]
    ri = np.column_stack([np.interp(t, ref_t, ref_v[:, j]) for j in range(v.shape[1])])
    e = (v - ri) * scale
    return float(np.sqrt((e ** 2).mean())), float(e.mean())


def compute(results=RESULTS):
    rows = []
    for start_tag in STARTS:
        ref = scenario(start_tag, "15.00M", "sampled")
        rht, rhv = bad._heads(results, ref)
        rst, rsv = bad._seep(results, ref, REF_HOURS / 24.0)
        for iv_tag, hours in INTERVALS.items():
            for rep in REPS:
                run = scenario(start_tag, iv_tag, rep)
                h_rmse, h_bias = _error(rht, rhv, *bad._heads(results, run), FT2MM)
                s_rmse, s_bias = _error(rst, rsv,
                                        *bad._seep(results, run, hours / 24.0),
                                        FT3_TO_M3)
                rows.append(dict(start=start_tag, interval=iv_tag, rep=rep,
                                 hours=hours, head_rmse=h_rmse, head_bias=h_bias,
                                 seep_rmse=s_rmse, seep_bias=s_bias))
    df = pd.DataFrame(rows)
    ds = df.set_index(["start", "interval", "rep"]).to_xarray()
    hours = ds["hours"].isel(start=0, rep=0).values
    ds = ds.drop_vars("hours").assign_coords(hours=("interval", hours))

    # The answer, formed here rather than left to whoever reads the archive: the
    # claim holds only if sampling is ahead at every start, so the sign is the
    # result and it belongs beside the numbers it comes from.
    d = ds["head_rmse"].sel(rep="sampled") - ds["head_rmse"].sel(rep="averaged")
    ds["head_rmse_diff"] = d
    ds["sampling_ahead"] = d < 0

    for v in ("head_rmse", "head_bias", "head_rmse_diff"):
        ds[v].attrs["units"] = "mm"
    for v in ("seep_rmse", "seep_bias"):
        ds[v].attrs["units"] = "m3/d"
    ds["hours"].attrs = {"units": "hours", "long_name": "coupling interval"}
    ds.attrs = {
        "title": "Coupled error by simulation start instant, coupling interval and "
                 "boundary representation",
        "summary": "Root-mean-square and mean error in simulated head and in "
                   "aquifer-sewer seepage, each against a 15-minute sampled "
                   "reference begun at the SAME instant, on the coarse grid. "
                   "sampling_ahead is the test: the claim in Section 9.1 holds only "
                   "if it is true at every start. The shifted runs are shorter than "
                   "the control, so errors compare within a start, never across.",
        "source": "docs/GP/scripts/start_phase_data.py",
        "plan": "docs/GP/START_PHASE_EXPERIMENT.md",
        "grid": GRID,
        "control_start": "2010-01-01 12:00",
        "spinup_days_excluded": SPINUP_D,
        "reference": "15-minute sampled run begun at the same instant",
    }
    return ds


def load_or_refresh(results=RESULTS, nc=NC, force=False):
    gaps = missing(results)
    if gaps and not force:
        if not nc.is_file():
            raise FileNotFoundError(
                f"neither the archive {nc} nor the simulation output exists; "
                f"{len(gaps)} runs absent, first: {gaps[0]}")
        return xr.open_dataset(nc, decode_timedelta=False), "archive"
    ds = compute(results)
    nc.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(nc)
    return ds, "results"


def report(ds):
    """The table, and the sign test that is the outcome of the experiment."""
    head = f"{'start':>6} {'interval':>9} | {'head RMSE, mm':^27} | {'ahead':>9}"
    print(head)
    print(f"{'':>6} {'':>9} | {'sampled':>13} {'averaged':>13} |")
    for s in ds["start"].values:
        for iv in ds["interval"].values:
            g = ds.sel(start=s, interval=iv)
            hs = float(g["head_rmse"].sel(rep="sampled"))
            ha = float(g["head_rmse"].sel(rep="averaged"))
            print(f"{str(s):>6} {str(iv):>9} | {hs:13.3f} {ha:13.3f} | "
                  f"{('sampled' if hs < ha else 'averaged'):>9}")
    ahead = np.asarray(ds["sampling_ahead"].values)
    print()
    if ahead.all():
        print("Sampling is ahead at every start and interval: the claim stands.")
    elif not ahead.any():
        print("Averaging is ahead everywhere: the claim is backwards, not unproven.")
    else:
        print("The sign changes with the start: the claim is false as written. "
              "Below the Nyquist limit the two differ by amounts too small to "
              "matter, and which is ahead depends on the start.")
    margin = np.abs(np.asarray(ds["head_rmse_diff"].values))
    print(f"margin |sampled - averaged|: {margin.min():.3f} to {margin.max():.3f} mm, "
          f"spread across starts {margin.max() - margin.min():.3f} mm")


if __name__ == "__main__":
    ds, src = load_or_refresh()
    print(f"{'refreshed from results/' if src == 'results' else 'read archive'}: {NC}")
    gaps = missing()
    if gaps:
        print(f"  {len(gaps)} of {len(required_runs())} runs absent; first: {gaps[0]}")
    print()
    report(ds)
