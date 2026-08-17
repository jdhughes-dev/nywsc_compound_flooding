"""Coastal exchange volume under the two boundary reductions, and its archive file.

Figure~\\ref{fig:averaging} scores the two reductions on the aquifer's RESPONSE --
head, seepage, tracer. This module scores them on the water itself: the volume
carried across the coastal boundary over the 89 days, at every coupling interval
and on all three grids, under sampling and under averaging.

The two are not the same statement. An error metric says the solution moved; a
cumulative volume says how much water the coupling put into the aquifer, which is
the quantity a water budget is written from. It is also the one place the
comparison can be made without a reference simulation arbitrating it: the volume
either depends on the coupling interval or it does not.

The quantity is the MODFLOW~6 GHB "INNER" and CHD "COASTAL" boundary flow,
normalized to a depth over the boundary cell area, following coastal_exchange_data
exactly -- same terms, same area, same sign convention (positive into the aquifer),
so a number here is comparable with one from there. The lateral "PERIMETER" term is
excluded as the regional boundary rather than the coast.

Run names come from boundary_averaging_data.CONFIG rather than a second table of
them. That module already had to record which directory holds which reduction on
each grid, including the places where the naming is not uniform, and two tables
that must agree is one table too many.
"""
import pathlib as pl

import numpy as np
import pandas as pd
import xarray as xr

import boundary_averaging_data as bad

HERE = pl.Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data" / "GP"
NC = DATA / "coastal_reduction.nc"
RESULTS = HERE.parents[2] / "results" / "gp"

GRIDS = ("coarse", "medium", "high")
MM_PER_FT = 25.4 * 12.0
CELL_AREA = 500.0 * 500.0          # the MODFLOW cell, in feet
NGHB, NCHD = 72, 691
AREA = (NGHB + NCHD) * CELL_AREA
SPINUP_D = bad.SPINUP_D

# The 15-minute pair is the finest simulated and anchors each grid's percent
# departure. It lives in CONFIG["refs"] rather than in CONFIG["runs"], because
# boundary_averaging_data scores everything else against it; here it is simply the
# shortest interval and belongs on the axis with the others.
REF_TAG = "15.00M"
REF_HOURS = 0.25


def entries(grid):
    """{tag: (hours, sampled run, averaged run)} for one grid, shortest first.

    The 6- and 12-hour intervals exist on the coarse grid alone, so the tag set is
    per grid rather than shared; the figure carries them as gaps on the other two.
    """
    cfg = bad.CONFIG[grid]
    out = {REF_TAG: (REF_HOURS, cfg["refs"]["15M instant"], cfg["refs"]["15M mean"])}
    for tag, (days, inst, mean) in cfg["runs"].items():
        out[tag] = (days * 24.0, inst, mean)
    return dict(sorted(out.items(), key=lambda kv: kv[1][0]))


def required_runs():
    return [r for g in GRIDS for _, i, m in entries(g).values() for r in (i, m)]


def missing(results=RESULTS):
    """Run directories that are absent or lack the boundary observations."""
    return [r for r in required_runs()
            if not all((results / r / f).is_file()
                       for f in ("gwf.ghb.obs.csv", "gwf.chd.obs.csv"))]


def _series(results, run):
    """Exchange rate in mm/d and its time axis in days, positive into the aquifer."""
    ghb = pd.read_csv(results / run / "gwf.ghb.obs.csv")
    chd = pd.read_csv(results / run / "gwf.chd.obs.csv")
    inner = next(c for c in ghb.columns if c.upper() == "INNER")
    coastal = next(c for c in chd.columns if c.upper() == "COASTAL")
    rate = MM_PER_FT * (ghb[inner].to_numpy() + chd[coastal].to_numpy()) / AREA
    return ghb["time"].to_numpy(), rate


def _stats(results, run):
    """(cumulative depth over the run, rms rate after spin-up)."""
    t, rate = _series(results, run)
    dt = float(np.median(np.diff(t)))
    return (float(np.cumsum(rate)[-1] * dt),
            float(np.sqrt((rate[t >= SPINUP_D] ** 2).mean())))


def compute(results=RESULTS):
    tags, hours = {}, {}
    for grid in GRIDS:
        for tag, (h, _, _) in entries(grid).items():
            tags[tag] = None
            hours[tag] = h
    order = sorted(tags, key=lambda t: hours[t])

    shape = (len(GRIDS), len(order))
    cum_i, cum_m = np.full(shape, np.nan), np.full(shape, np.nan)
    rms_i, rms_m = np.full(shape, np.nan), np.full(shape, np.nan)
    for gi, grid in enumerate(GRIDS):
        got = entries(grid)
        for ti, tag in enumerate(order):
            if tag not in got:
                continue
            _, inst, mean = got[tag]
            cum_i[gi, ti], rms_i[gi, ti] = _stats(results, inst)
            cum_m[gi, ti], rms_m[gi, ti] = _stats(results, mean)

    ref = cum_i[:, order.index(REF_TAG)]
    ds = xr.Dataset(
        {"cum_inst": (("grid", "interval"), cum_i),
         "cum_mean": (("grid", "interval"), cum_m),
         "rms_inst": (("grid", "interval"), rms_i),
         "rms_mean": (("grid", "interval"), rms_m),
         "cum_ref": ("grid", ref),
         # Held as a percent so the figure does not have to re-derive it, and so a
         # reader with the archive alone has the number the text quotes.
         "pct_inst": (("grid", "interval"), 100.0 * (cum_i - ref[:, None]) / ref[:, None]),
         "pct_mean": (("grid", "interval"), 100.0 * (cum_m - ref[:, None]) / ref[:, None])},
        coords={"grid": list(GRIDS), "interval": order,
                "hours": ("interval", [hours[t] for t in order])},
    )
    for v in ("cum_inst", "cum_mean", "cum_ref"):
        ds[v].attrs["units"] = "mm"
    for v in ("rms_inst", "rms_mean"):
        ds[v].attrs["units"] = "mm/d"
    for v in ("pct_inst", "pct_mean"):
        ds[v].attrs["units"] = "percent"
    ds["hours"].attrs = {"units": "hours", "long_name": "coupling interval"}
    ds.attrs = {
        "title": "Coastal exchange volume by coupling interval and boundary reduction",
        "summary": "Cumulative coastal exchange over the 89-day simulation, as a "
                   "depth over the MODFLOW 6 boundary cell area, for an "
                   "end-of-interval (inst) and a wetted-fraction time-averaged "
                   "(mean) reduction of the D-Flow FM boundary, on three grids. "
                   "Positive is flow into the aquifer. pct_* is the departure from "
                   "the 15-minute sampled simulation on the same grid. The 6- and "
                   "12-hour intervals were simulated on the coarse grid only.",
        "source": "docs/GP/scripts/coastal_reduction_data.py",
        "reference_interval": REF_TAG,
        "excluded_term": "PERIMETER, the lateral regional boundary",
        "spinup_days_excluded_from_rms": SPINUP_D,
        "m2_nyquist_hours": bad.NYQUIST_H,
        "boundary_cells": NGHB + NCHD,
    }
    return ds


def load_or_refresh(results=RESULTS, nc=NC, force=False):
    gaps = missing(results)
    if gaps and not force:
        if not nc.is_file():
            raise FileNotFoundError(
                f"neither the archive {nc} nor the simulation output exists; "
                f"missing runs: {', '.join(gaps[:4])}")
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
    with pd.option_context("display.width", 200):
        for grid in ds["grid"].values:
            g = ds.sel(grid=grid)
            print(f"\n{grid}  (15-minute reference {float(g['cum_ref']):.2f} mm)")
            print(pd.DataFrame(
                {"hours": g["hours"].values,
                 "cum_inst": g["cum_inst"].values, "cum_mean": g["cum_mean"].values,
                 "pct_inst": g["pct_inst"].values, "pct_mean": g["pct_mean"].values,
                 "rms_inst": g["rms_inst"].values, "rms_mean": g["rms_mean"].values},
                index=ds["interval"].values).to_string(float_format="%.2f"))
