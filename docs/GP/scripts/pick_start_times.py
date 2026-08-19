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

The forcing sets a hard bound on what can be run. The Q1 2010 meteo files cover
2010-01-01 00:00 to 2010-03-31 12:00 and the production window is the last 89 days
of that, so a start can only be moved EARLIER, by at most 12 h. That is 0.97 of an
M2 period, so nearly every phase is reachable, and this reports the reachable start
for each phase it recommends.

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

T_M2 = 12.4206                     # hours
PROD_START = datetime.datetime(2010, 1, 1, 12, 0)
EARLIEST = datetime.datetime(2010, 1, 1, 0, 0)      # meteo record opens here
DT_OUT = 300.0                     # his output step, seconds
SPINUP_D = 5.0                     # excluded, as everywhere else in this work
# Below the M2 Nyquist limit of 6.21 h, which is where the ordering claim lives and
# where the margin between the two is thinnest. 8 h is carried as a contrast.
INTERVALS = (2.0, 4.0, 6.0, 8.0)


def water_level(his, station):
    ds = xr.open_dataset(his, decode_timedelta=False)
    names = [b.tobytes().decode("utf-8", "ignore").strip()
             for b in ds["station_name"].values]
    if station is None:
        pick = [n for n in names if "greenport" in n.lower()]
        station = pick[0] if pick else "Kings Point"
    if station not in names:
        raise SystemExit(f"station {station!r} not in {his.name}; have {names}")
    s = ds["waterlevel"].isel(station=names.index(station)).values.astype(float)
    return station, names, s


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
    """The latest feasible real start whose tidal phase matches phase_h.

    Phase is measured forward from the production start. A run can only be moved
    earlier, so the matching start is PROD_START - ((T - phase) mod T).
    """
    back = (T_M2 - phase_h) % T_M2
    start = PROD_START - datetime.timedelta(hours=back)
    return start, back, start >= EARLIEST


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--his", type=pl.Path, default=HIS)
    ap.add_argument("--station", default=None,
                    help="default: a station matching 'greenport', else Kings Point")
    a = ap.parse_args()

    station, names, s = water_level(a.his, a.station)
    print(f"{a.his.name}: {len(s)} samples at {DT_OUT:.0f} s, station {station!r}")
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
            st, back, ok = reachable(float(phases[i]))
            flag = "" if ok else "   NOT REACHABLE, meteo opens 2010-01-01 00:00"
            print(f"    {label:<19} phase {phases[i]:5.2f} h  ->  start "
                  f"{st:%Y-%m-%d %H:%M} ({back:4.2f} h earlier), "
                  f"offset {off[i]:5.2f} mm{flag}")
        print()

    print("The production start is 2010-01-01 12:00 and is the control; it needs no "
          "new run.\nRound each recommended start down to a multiple of the 300 s "
          "user time step before use.")


if __name__ == "__main__":
    main()
