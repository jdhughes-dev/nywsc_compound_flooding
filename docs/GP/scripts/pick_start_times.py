"""Choose the simulation start times for the start-phase experiment.

The question is whether the instant a coupled run begins decides which boundary
representation is the more accurate below the Nyquist limit. start_phase_analysis.py
bounds that on the fitted three-constituent record; this picks the start times a
coupled test should actually use, on the water level D-Flow FM simulated.

Why not 00, 06, 12, 18: those four clock times land at M2 phases of 0, 174, 348,
and 162 degrees. The first and third are the same phase to within 12 degrees, and
so are the second and fourth, so four runs would test two phases. Evenly spaced
phases are better and still miss the point -- the statistic is not monotonic in
phase, and its extremes fall between the quarter points. What is wanted is the
start that hurts sampling most and the one that hurts it least, because a claim
that the ordering cannot be reversed is a claim about the worst case.

The forcing sets a hard bound, and it runs the other way from what it first looks
like. The Q1 2010 meteo files cover 2010-01-01 00:00 to 2010-03-31 12:00, which
suggests 12 h of room before the production start -- but WaterLevel2010_surge.bc
begins at 2010-01-01 12:00, the production start itself, so an earlier window asks
for a water level the forcing does not carry and D-Flow stops on it. Confirmed by
smoke test: a start 65 minutes early fails with "Requested time preceeds current
forcing EC-timelevel". The envelope is exactly the production window.

So a start can only be moved LATER, holding the stop, which shortens the run by the
shift. A full M2 period costs 12.42 h out of 89 days, or half a percent, and every
phase is reachable. Phase here is measured forward from the production start, which
is also what the statistic below computes: entering the record n_skip steps in is a
run begun that much later.

Run it directly. It reads one existing coarse run's history file and writes nothing.
"""
import argparse
import datetime
import pathlib as pl

import numpy as np
import xarray as xr

HERE = pl.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
HIS = ROOT / "dflow-fm" / "coarse" / "run_gp_coarse_01.00D_n244" / "output" / "FlowFM_his.nc"
DATA = HERE.parents[1] / "data" / "GP"
NC = DATA / "start_phase_waterlevel.nc"

T_M2 = 12.4206                     # hours
PROD_START = datetime.datetime(2010, 1, 1, 12, 0)
DT_USER = 300.0                    # D-Flow FM user time step, seconds
MAX_LATER_H = 13.0                 # a full M2 period; the driver refuses more
DT_OUT = 300.0                     # his output step, seconds
SPINUP_D = 5.0                     # excluded, as everywhere else in this work
# Below the M2 Nyquist limit of 6.21 h, which is where the ordering claim lives and
# where the margin between the two is thinnest. 8 h is carried as a contrast.
INTERVALS = (2.0, 4.0, 6.0, 8.0)


def water_level(his, station):
    """The simulated water level, from the run output or from the archive.

    The his file lives in a D-Flow run directory, which is not version controlled
    and which the experiment plan says to delete once its results are extracted.
    Nothing under docs/ may depend on something that is meant to be deleted, so the
    series is archived beside the other summaries the first time it is read and is
    taken from there afterwards. One station of 5-minute water level for the
    simulated period is a few hundred kilobytes.
    """
    if his.is_file():
        ds = xr.open_dataset(his, decode_timedelta=False)
        names = [b.tobytes().decode("utf-8", "ignore").strip()
                 for b in ds["station_name"].values]
        if station is None:
            pick = [n for n in names if "greenport" in n.lower()]
            station = pick[0] if pick else "Kings Point"
        if station not in names:
            raise SystemExit(f"station {station!r} not in {his.name}; have {names}")
        s = ds["waterlevel"].isel(station=names.index(station)).values.astype(float)
        out = xr.Dataset(
            {"waterlevel": ("sample", s)},
            coords={"sample": np.arange(len(s))},
            attrs={
                "title": "Simulated water level for choosing start-phase start times",
                "summary": "One station of D-Flow FM water level at the his output "
                           "step, archived so pick_start_times.py runs from a clone. "
                           "The run directory it came from is not version controlled "
                           "and is deleted once its results are extracted.",
                "source": "docs/GP/scripts/pick_start_times.py",
                "station": station,
                "stations_available": ", ".join(names),
                "from_run": his.parent.parent.name,
                "dt_seconds": DT_OUT,
            },
        )
        NC.parent.mkdir(parents=True, exist_ok=True)
        out.to_netcdf(NC)
        return station, names, s, "run output"

    if not NC.is_file():
        raise SystemExit(
            f"neither the run output {his} nor the archive {NC} exists; "
            "run the daily coarse scenario, or fetch the archive"
        )
    ds = xr.open_dataset(NC, decode_timedelta=False)
    names = [n.strip() for n in ds.attrs.get("stations_available", "").split(",")]
    archived = ds.attrs.get("station", "unknown")
    if station is not None and station != archived:
        raise SystemExit(
            f"the archive holds station {archived!r}, not {station!r}; the his file "
            "is needed to extract a different one"
        )
    return archived, names, ds["waterlevel"].values.astype(float), "archive"


def statistic(s, n_hold, n_skip, n_spin):
    """|mean offset| of the sampled record, mm, and both retained ranges, m.

    n_skip enters the record that many output steps in, which reproduces a run
    begun that much later in the tide.
    """
    x = s[n_skip:]
    nfull = (len(x) // n_hold) * n_hold
    if nfull == 0:
        return np.nan, np.nan, np.nan
    b = x[:nfull].reshape(-1, n_hold)
    sampled = np.repeat(b[:, -1], n_hold)
    averaged = np.repeat(b.mean(axis=1), n_hold)
    keep = np.arange(nfull) >= n_spin
    truth = x[:nfull][keep].mean()
    return (abs(sampled[keep].mean() - truth) * 1000.0,
            sampled[keep].max() - sampled[keep].min(),
            averaged[keep].max() - averaged[keep].min())


def reachable(phase_h):
    """The real start whose tidal phase matches phase_h, and its cost.

    A run can only be moved later, so the start is PROD_START + phase, and the
    shift is what the record loses off its front. Rounded to a whole number of user
    time steps, which the driver requires and which moves the phase by under
    2.5 minutes.
    """
    shift = round(phase_h * 3600.0 / DT_USER) * DT_USER / 3600.0
    start = PROD_START + datetime.timedelta(hours=shift)
    return start, shift, shift <= MAX_LATER_H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--his", type=pl.Path, default=HIS)
    ap.add_argument("--station", default=None,
                    help="default: a station matching 'greenport', else Kings Point")
    a = ap.parse_args()

    station, names, s, src = water_level(a.his, a.station)
    print(f"{src}: {len(s)} samples at {DT_OUT:.0f} s, station {station!r}")
    print(f"stations available: {', '.join(names)}\n")

    n_spin = int(SPINUP_D * 86400 / DT_OUT)
    phases = np.arange(0.0, T_M2, DT_OUT / 3600.0)      # one M2 period, 5 min steps

    for dtc in INTERVALS:
        n_hold = int(round(dtc * 3600.0 / DT_OUT))
        off = np.array([statistic(s, n_hold, int(round(p * 3600.0 / DT_OUT)), n_spin)[0]
                        for p in phases])
        i_hi, i_lo = int(np.nanargmax(off)), int(np.nanargmin(off))
        tag = "below Nyquist" if dtc < 6.21 else "above Nyquist"
        print(f"coupling interval {dtc:4.1f} h  ({tag})")
        print(f"    sampled |mean offset| over one M2 period: "
              f"{np.nanmin(off):.2f} to {np.nanmax(off):.2f} mm")
        for label, i in (("worst for sampling", i_hi), ("best for sampling", i_lo)):
            st, shift, ok = reachable(float(phases[i]))
            flag = "" if ok else f"   NOT REACHABLE, driver refuses > {MAX_LATER_H:g} h"
            print(f"    {label:<19} phase {phases[i]:5.2f} h  ->  start "
                  f"{st:%Y-%m-%d %H:%M} ({shift:5.2f} h later, "
                  f"{89 - shift / 24:5.2f} d of record), "
                  f"offset {off[i]:5.2f} mm{flag}")
        print()

    print("The production start is 2010-01-01 12:00 and is the control; it needs no "
          "new run." "\n"
          "Starts above are already rounded to the 300 s user time step, which the "
          "driver requires." "\n"
          "Pass one to run_scenario.py as --start-datetime yyyymmddhhmmss; the stop "
          "is held and the run is shortened, so each start needs its own 15-minute "
          "reference.")


if __name__ == "__main__":
    main()
