"""Coastal exchange by coupling interval on one grid, and its archive file.

The quantity is the boundary flow MODFLOW~6 reports through the GHB "INNER" and CHD
"COASTAL" observations, normalized to a depth over the boundary cell area, which is
what step3_plot_compare_coastal_exchange.ipynb plots. The lateral "PERIMETER" term is
excluded: it is the regional boundary rather than the coast and it dominates the sum.

Sign does NOT follow the notebook. MODFLOW reports boundary flow positive into the
model and the notebook negates it, so that positive is discharge out of the aquifer
and the cumulative curve runs negative -- the coast is net into the aquifer in this
density-coupled model. The negation is dropped here, so positive is flow into the
aquifer and the cumulative is positive, which reads as the magnitude of the process
being described rather than as a deficit. Both panels of the figure use the one
convention; comparing a number here against the notebook flips its sign.

This is NOT the qext sum. qext is the flux formed from the reduced boundary value, so
comparing it across reductions mostly measures which reduction a run used. Here every
series shares a grid and a reduction and differs only in the coupling interval, so
the comparison is of the interval alone.

One grid is archived, the medium one. It carries the largest interval sensitivity of
the three, so it is the conservative choice rather than a flattering one, and the
cumulative depth it reports is a third of the gross flux rather than a small residual
of it -- which is what makes this metric trustworthy where the cross-grid qext
comparison was not.
"""
import pathlib as pl
import sys

import numpy as np
import pandas as pd
import xarray as xr

HERE = pl.Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data" / "GP"
NC = DATA / "coastal_exchange.nc"
RESULTS = HERE.parents[2] / "results" / "gp"

GRID = "medium"
MM_PER_FT = 25.4 * 12.0
CELL_AREA = 500.0 * 500.0          # the MODFLOW cell, in feet
NGHB, NCHD = 72, 691
AREA = (NGHB + NCHD) * CELL_AREA
SPINUP_D = 5.0

INTERVALS = [("15.00M", 0.25), ("30.00M", 0.5), ("01.00H", 1.0), ("02.00H", 2.0),
             ("04.00H", 4.0), ("08.00H", 8.0), ("01.00D", 24.0)]


def scenario(grid, hours, results=RESULTS):
    sys.path.insert(0, str(HERE.parents[2] / "common"))
    from liss_settings import get_results_path
    ws = get_results_path("gp", grid, hours, 244)
    return ws.parent / (ws.name + "_meanbnd")


def missing(results=RESULTS):
    out = []
    for tag, h in INTERVALS:
        ws = scenario(GRID, h, results)
        if not all((ws / f).is_file()
                   for f in ("gwf.ghb.obs.csv", "gwf.chd.obs.csv")):
            out.append(ws.name)
    return out


def compute(results=RESULTS):
    rows = []
    for tag, hours in INTERVALS:
        ws = scenario(GRID, hours, results)
        ghb = pd.read_csv(ws / "gwf.ghb.obs.csv")
        chd = pd.read_csv(ws / "gwf.chd.obs.csv")
        inner = next(c for c in ghb.columns if c.upper() == "INNER")
        coastal = next(c for c in chd.columns if c.upper() == "COASTAL")
        rate = MM_PER_FT * (ghb[inner].to_numpy() + chd[coastal].to_numpy()) / AREA
        t = ghb["time"].to_numpy()
        dt = float(np.median(np.diff(t)))
        rows.append(pd.DataFrame({"interval": tag, "hours": hours, "time": t,
                                  "rate": rate, "cum": np.cumsum(rate) * dt}))
    df = pd.concat(rows, ignore_index=True)

    # Tidy form on a single sample dimension, because the seven series have
    # different lengths -- 89 steps at daily coupling against 8,544 at 15 minutes --
    # and padding them onto a common axis would invent values.
    ds = xr.Dataset({c: ("sample", df[c].to_numpy())
                     for c in ("time", "rate", "cum")},
                    coords={"sample": np.arange(len(df)),
                            "interval": ("sample", df["interval"].to_numpy())})
    summary = []
    for tag, hours in INTERVALS:
        sub = df[df["interval"] == tag]
        keep = sub["time"] >= SPINUP_D
        dt = float(np.median(np.diff(sub["time"])))
        summary.append({"iv": tag, "hours": hours,
                        "cum_mm": float(sub["cum"].iloc[-1]),
                        "rms_rate": float(np.sqrt((sub["rate"][keep] ** 2).mean())),
                        "gross_mm": float(np.abs(sub["rate"]).sum() * dt)})
    # A dimension of its own. "interval" is already a coordinate along sample, so
    # reusing the name makes xarray broadcast the summary against every sample and
    # the dataset comes back as a cross product.
    s = pd.DataFrame(summary).set_index("iv").to_xarray()
    for v in ("hours", "cum_mm", "rms_rate", "gross_mm"):
        ds[v] = s[v]
    ds["rate"].attrs["units"] = "mm/d"
    ds["cum"].attrs["units"] = "mm"
    ds["time"].attrs["units"] = "d"
    ds.attrs = {
        "title": f"Coastal exchange by coupling interval, {GRID} grid",
        "summary": "Boundary flow through the GHB INNER and CHD COASTAL observations, "
                   "as a depth over the boundary cell area. Positive is flow into the "
                   "aquifer. Every series shares the grid and the averaged "
                   "boundary reduction and differs only in coupling interval.",
        "source": "docs/GP/scripts/coastal_exchange_data.py",
        "grid": GRID,
        "reduction": "averaged",
        "excluded_term": "PERIMETER, the lateral regional boundary",
        "spinup_days_excluded_from_rms": SPINUP_D,
        "boundary_cells": NGHB + NCHD,
    }
    return ds


def load_or_refresh(results=RESULTS, nc=NC, force=False):
    if missing(results) and not force:
        if not nc.is_file():
            raise FileNotFoundError(f"neither {nc} nor the simulation output exists")
        return xr.open_dataset(nc, decode_timedelta=False), "archive"
    ds = compute(results)
    nc.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(nc)
    return ds, "results"


if __name__ == "__main__":
    ds, src = load_or_refresh()
    print(f"{'refreshed from results/' if src == 'results' else 'read archive'}: {NC}")
    print(ds[["hours", "cum_mm", "rms_rate"]].to_dataframe().to_string())
