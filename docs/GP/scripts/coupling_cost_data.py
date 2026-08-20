"""Run times by grid and coupling interval, and their archive file.

The timings come from the per-scenario run logs, which are not under version
control -- they are working output of run_scenario.py, one per run, and several
gigabytes over the whole study. So the extracted table is archived to
../../data/GP/coupling_cost.nc and the figure is drawn from that, which is what
lets a co-author with only the repository rebuild it. When the logs are present
the archive is recomputed rather than trusted, the same rule
boundary_averaging_data.py follows.

Only full n=244 runs are included. Smoke tests are short by construction, and the
junction-count runs change the SWMM side, so neither belongs in a comparison whose
point is the cost of the coupling interval alone.
"""
import pathlib as pl
import re
import sys

import numpy as np
import pandas as pd
import xarray as xr

HERE = pl.Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data" / "GP"
NC = DATA / "coupling_cost.nc"
LOGS = HERE.parents[2] / "logs"

# Cells per D-Flow FM grid, as reported in the manuscript's scenario table. The
# MODFLOW and SWMM models are identical across all three, which is why the marginal
# cost of a coupling step should not depend on which grid is being driven.
CELLS = {"coarse": 6491, "medium": 16666, "high": 41091}
HOURS = {"15.00M": 0.25, "30.00M": 0.5, "01.00H": 1.0, "02.00H": 2.0, "04.00H": 4.0,
         "06.00H": 6.0, "08.00H": 8.0, "12.00H": 12.0, "01.00D": 24.0}

RUN_TIME = re.compile(r"^run time:\s*([\d.]+) min \((\d+) coupling steps\)", re.M)
# gp_<grid>_<tag>_n<NNN>[_<reduction>]_<date>_<time>.log
STEM = re.compile(r"^gp_(coarse|medium|high)_(\d\d\.\d\d[MHD])_n(\d+)_?(\w*?)_\d{8}_\d{6}$")

# Runs carrying the _t<HHMM> start tag of docs/GP/START_PHASE_EXPERIMENT.md share
# logs/ with the production sweeps and would otherwise enter the fit as series of
# their own -- _instbnd_t1525 and the rest -- on any refresh. EXPECTED below catches
# a series that has gone missing but says nothing about one that should never have
# been there, and the figure selects its series by name, so the contamination would
# sit in the archive unseen. Those runs are a different experiment: they hold three
# intervals each, at a shifted start, and their run times answer no question this
# module asks.
TAGGED = re.compile(r"_t\d{4}$")


def scan(logs=LOGS):
    """One row per scenario, taking the most recent log when a run was repeated."""
    rows = {}
    for f in sorted(logs.glob("*.log")):
        m = STEM.match(f.stem)
        if not m:
            continue
        grid, tag, n, reduction = m.groups()
        if int(n) != 244 or "smoke" in f.stem or TAGGED.search(reduction or ""):
            continue
        rt = RUN_TIME.search(f.read_text(errors="replace"))
        if not rt:
            continue                       # run died before the loop finished
        key = (grid, tag, reduction or "instbnd")
        cand = (f.stem, float(rt.group(1)), int(rt.group(2)))
        if key not in rows or cand[0] > rows[key][0]:
            rows[key] = cand
    return pd.DataFrame(
        [{"grid": g, "interval": t, "reduction": r, "hours": HOURS[t],
          "cells": CELLS[g], "minutes": mins, "steps": steps}
         for (g, t, r), (_, mins, steps) in rows.items()]
    ).sort_values(["grid", "reduction", "hours"]).reset_index(drop=True)


def fits(df):
    """Fixed and marginal cost per grid and reduction.

    minutes = intercept + slope * steps. The intercept is what D-Flow FM costs on
    its own and the slope is what one MODFLOW/SWMM exchange adds; separating them is
    the point, because only the second is what a shorter coupling interval buys.
    """
    out = []
    for (g, r), sub in df.groupby(["grid", "reduction"]):
        if len(sub) < 4:
            continue
        slope, intercept = np.polyfit(sub["steps"], sub["minutes"], 1)
        lo = sub.loc[sub["steps"].idxmin(), "minutes"]
        hi = sub.loc[sub["steps"].idxmax(), "minutes"]
        out.append({"grid": g, "reduction": r, "cells": CELLS[g],
                    "intercept_min": intercept, "marginal_s": slope * 60.0,
                    "r2": float(np.corrcoef(sub["steps"], sub["minutes"])[0, 1] ** 2),
                    "penalty_pct": 100.0 * (hi / lo - 1.0),
                    "n_intervals": len(sub)})
    return pd.DataFrame(out)


# The series the figure is drawn from. Named explicitly so that a partial logs/
# directory is detected as partial: without this the module would recompute from
# whatever it happened to find and overwrite the archive with fewer series, which
# is the one failure mode an archive exists to prevent.
EXPECTED = {
    ("coarse", "instbnd"): 9, ("coarse", "meanbnd"): 9,
    ("medium", "instbnd"): 7, ("medium", "meanbnd"): 7,
    ("high", "instbnd"): 7, ("high", "meanbnd"): 7,
}


def missing(logs=LOGS):
    """Series that are absent or short in logs/, as (grid, reduction) labels."""
    if not logs.is_dir():
        return ["logs/"]
    df = scan(logs)
    if df.empty:
        return ["logs/"]
    have = df.groupby(["grid", "reduction"]).size().to_dict()
    return [f"{g}/{r} ({have.get((g, r), 0)} of {n})"
            for (g, r), n in sorted(EXPECTED.items()) if have.get((g, r), 0) < n]


def compute(logs=LOGS):
    df = scan(logs)
    ds = df.set_index(["grid", "reduction", "interval"]).to_xarray()
    ds = ds.assign_attrs(
        title="Coupled-model run time by grid and coupling interval",
        summary="Wall-clock run time of each full 89-day simulation, with the number "
                "of coupling steps it performed. The MODFLOW and SWMM models are "
                "identical across grids, so the marginal cost of an exchange is "
                "grid-independent while the hydrodynamic cost it is measured against "
                "is not.",
        source="docs/GP/scripts/coupling_cost_data.py",
        machine="single workstation, runs executed sequentially",
    )
    for v, u in (("minutes", "min"), ("hours", "h"), ("steps", "1"), ("cells", "1")):
        if v in ds:
            ds[v].attrs["units"] = u
    return ds


def load_or_refresh(logs=LOGS, nc=NC, force=False):
    if missing(logs) and not force:
        if not nc.is_file():
            raise FileNotFoundError(f"neither {nc} nor the run logs exist")
        return xr.open_dataset(nc, decode_timedelta=False), "archive"
    ds = compute(logs)
    nc.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(nc)
    return ds, "logs"


if __name__ == "__main__":
    ds, src = load_or_refresh()
    print(f"{'refreshed from logs/' if src == 'logs' else 'read archive'}: {NC}")
    df = ds.to_dataframe().reset_index().dropna(subset=["minutes"])
    print(df[["grid", "reduction", "interval", "steps", "minutes"]].to_string(index=False))
    print()
    print(fits(df).to_string(index=False))
