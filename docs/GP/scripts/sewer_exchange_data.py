"""Aquifer-sewer exchange by grid, and its archive file.

Computed from each grid's 15-minute simulation, which is the finest coupling run
and the one the coupling-interval comparison uses as its reference, so what is left
varying between the three series is the D-Flow FM discretization alone. The
MODFLOW~6 and SWMM models are identical across them.

Archived to ../../data/GP/sewer_exchange.nc because swmm_q.npz and pipe_state.npz
live in results/, which is not under version control.

Sign convention follows the stored arrays: swmm_q.npz holds the MODFLOW well flux,
which is negative into the sewer, so it is negated here and positive means
infiltration.
"""
import pathlib as pl
import sys

import numpy as np
import pandas as pd
import xarray as xr

HERE = pl.Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data" / "GP"
NC = DATA / "sewer_exchange.nc"
RESULTS = HERE.parents[2] / "results" / "gp"
INP = HERE.parents[2] / "swmm" / "gp" / "gp_sewer.inp"

SPINUP_D = 5.0
FT3_TO_M3 = 0.028316846592      # exact; MODFLOW is in feet, the manuscript is in SI
FT3_TO_L = 28.316846592
# The customary rate the acceptance band is published in, per liter-based unit:
# 1 gal/(d in mi) = 0.09260 L/(d mm km). Recorded so a number in either unit can be
# checked against the other without looking the conversion up again.
GAL_IN_MI_TO_L_MM_KM = 3.785411784 / (25.4 * 1.609344)
DT_D = 0.25 / 24.0          # the 15-minute coupling interval, in days
N_CONN = 244

# Averaged coastal boundary: the reduction adopted in this work. At a 15-minute
# interval the two reductions agree on this quantity to four significant figures,
# which is itself worth knowing and is recorded in the attributes.
RUNS = {"coarse": "gp_coarse_15.00M_n244_meanbnd",
        "medium": "gp_medium_15.00M_n244_meanbnd",
        "high": "gp_high_15.00M_n244_meanbnd"}
CELLS = {"coarse": 6491, "medium": 16666, "high": 41091}


def _sections(inp, name):
    rows, inside = [], False
    for line in pl.Path(inp).read_text(errors="replace").splitlines():
        s = line.strip()
        if s.startswith("["):
            inside = s.upper().startswith(f"[{name}")
            continue
        if inside and s and not s.startswith(";"):
            rows.append(s.split())
    return rows


def pipe_normalization(inp=INP):
    """Millimeter-diameter-kilometers of sewer, the denominator of the rate.

    Summed as sum(D_j L_j) rather than taken as a median diameter times the total
    length. Diameters here run 0.15 to 0.30 m, so the two differ by 7 percent, and
    only the sum is what "per millimeter of diameter per kilometer" actually means.

    gp_sewer.inp declares FLOW_UNITS CMS, so its diameters and lengths are already
    in meters and no conversion is needed: millimeters times kilometers is meters
    times meters, and the sum is formed directly from what the file records.
    """
    length_m = {r[0]: float(r[3]) for r in _sections(inp, "CONDUITS") if len(r) >= 4}
    diam_m = {r[0]: float(r[2]) for r in _sections(inp, "XSECTIONS")
              if len(r) >= 3 and r[1].lower().startswith("circ")}
    mm_dia_km = sum(diam_m[k] * length_m[k] for k in length_m if k in diam_m)
    total_km = sum(length_m.values()) / 1000.0
    return mm_dia_km, total_km, len(length_m)


# 89 days at the 15-minute coupling interval. Checked rather than assumed, because
# presence of a file is not evidence that the run behind it finished.
EXPECTED_STEPS = int(round(89.0 / DT_D))


def missing(results=RESULTS):
    """Runs that are absent, incomplete, or short.

    Three things are checked, and the last is the one that matters. pipe_state.npz
    is required as well as swmm_q.npz because panel B is built from it and the
    earliest runs predate that output. Then the step count in swmm_q.npz must match
    the full simulation: a run killed part-way still leaves a loadable archive of
    everything up to the kill, and a shorter series would otherwise be integrated
    as though it were a whole one and written over a good summary.
    """
    out = []
    for run in RUNS.values():
        d = results / run
        if not all((d / f).is_file() for f in ("swmm_q.npz", "pipe_state.npz")):
            out.append(run)
            continue
        try:
            with np.load(d / "swmm_q.npz") as z:
                n = len(z.files)
        except Exception:
            out.append(run)
            continue
        if n != EXPECTED_STEPS:
            out.append(f"{run} ({n} of {EXPECTED_STEPS} steps)")
    return out


def compute(results=RESULTS):
    mm_dia_km, total_km, n_conduits = pipe_normalization()
    series, rows = {}, []
    for grid, run in RUNS.items():
        ws = results / run
        q = np.load(ws / "swmm_q.npz")
        arr = np.stack([q[k] for k in sorted(q.files, key=int)])
        n = len(arr)
        t = np.arange(1, n + 1) * DT_D
        net_rate = -arr.sum(axis=1)                 # ft3/d, positive into the sewer
        gross_rate = np.abs(arr).sum(axis=1)
        keep = t >= SPINUP_D                        # same spin-up the rest of the study drops
        days = float(t[keep][-1] - t[keep][0] + DT_D)
        net = float(net_rate[keep].sum() * DT_D)
        gross = float(gross_rate[keep].sum() * DT_D)

        conn = np.full(n, np.nan)
        ps = ws / "pipe_state.npz"
        if ps.is_file():
            s = np.load(ps)
            st = np.stack([s[k] for k in sorted(s.files, key=int)])
            conn = (N_CONN - st[:, 1]) / N_CONN * 100.0

        series[grid] = (t, np.cumsum(net_rate * DT_D) * FT3_TO_M3, conn)
        rows.append({
            "grid": grid, "cells": CELLS[grid],
            "net_m3": net * FT3_TO_M3, "gross_m3": gross * FT3_TO_M3,
            "rate_L_d_mm_km": (net / days) * FT3_TO_L / mm_dia_km,
            # Distinct from the connected_pct time series: merging the summary into
            # the same Dataset would otherwise silently replace it with this scalar.
            "connected_mean_pct": float(np.nanmean(conn[keep])),
        })

    t0 = series["coarse"][0]
    ds = xr.Dataset(
        {"cum_net_m3": (("grid", "time"), np.array([series[g][1] for g in RUNS])),
         "connected_pct": (("grid", "time"), np.array([series[g][2] for g in RUNS]))},
        coords={"grid": list(RUNS), "time": t0},
    )
    summary = pd.DataFrame(rows).set_index("grid").to_xarray()
    for v in summary.data_vars:
        ds[v] = summary[v]
    ds["time"].attrs = {"units": "d", "long_name": "days since start of simulation"}
    ds["cum_net_m3"].attrs["units"] = "m3"
    ds["connected_pct"].attrs["units"] = "percent"
    ds["rate_L_d_mm_km"].attrs["units"] = "L/d/mm/km"
    ds.attrs = {
        "title": "Aquifer-sewer exchange by D-Flow FM grid at 15-minute coupling",
        "summary": "Cumulative net exchange, connected-junction fraction, and the "
                   "infiltration rate per unit of pipe diameter and length, for "
                   "the three grids. Positive is infiltration into the sewer. The "
                   "acceptance band sewer standards publish is stated in gallons "
                   "per day per inch of diameter per mile and is converted here.",
        "source": "docs/GP/scripts/sewer_exchange_data.py",
        "reduction": "averaged coastal boundary; the sampled reduction agrees to "
                     "four significant figures at this coupling interval",
        "spinup_days_excluded": SPINUP_D,
        "mm_diameter_kilometers": mm_dia_km,
        "network_kilometers": total_km,
        "n_conduits": n_conduits,
        "acceptance_range_L_d_mm_km": "4.6-18.5 for new gravity sanitary sewers, "
                                      "converted from the published 50-200 gallons "
                                      "per day per inch of diameter per mile",
        "gal_in_mi_to_L_mm_km": GAL_IN_MI_TO_L_MM_KM,
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
    print(f"normalization: {ds.attrs['mm_diameter_kilometers']:.1f} "
          f"millimeter-diameter-kilometers over "
          f"{ds.attrs['network_kilometers']:.2f} km, "
          f"{ds.attrs['n_conduits']} conduits\n")
    print(ds[["cells", "net_m3", "rate_L_d_mm_km", "connected_mean_pct"]]
          .to_dataframe().to_string())
