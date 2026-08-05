"""Extract the station water levels from each run's D-Flow FM history file.

The history file is written into the RUN directory, which the sweep reuses: rerunning
a scenario overwrites its FlowFM_his.nc, and only the source_sink_* subset was ever
copied into results/. This pulls the station time series out to results/ so a rerun
cannot take them. It is a copy, not a computation -- nothing here changes a result.

The full history file is 82.9 MB, almost all of it cross sections and structures that
none of the comparison notebooks read. Water level at 30 stations is 3.1 MB raw and
compresses to a fraction of that, so every scenario can be kept.

Each station is classified, because a D-Flow FM history file reports a value at every
station whether or not the grid resolves it, and the three failure modes are not
distinguishable from the value alone:

    outside       every value NaN -- the station is off the grid entirely
    dry           one constant value, which is the BED level, not a water level
                  (coarse Port Jefferson reports 21.084 m; highres Willets Point
                  4.5 m). Plotted unguarded this is a flat line at plausible-looking
                  elevation, which is the dangerous case.
    disconnected  varies, but with no tidal signal -- the cell is wet and sitting
                  near the initial condition because the grid does not resolve the
                  channel connecting it to the sound (coarse New Haven varies over
                  0.006 m about -0.02 m against a true range near 4 m)
    ok            a real tidal signal

Coverage is NOT nested by resolution. The highres grid resolves Battery, which coarse
misses, but loses New London and Willets Point, which midres resolves -- at higher
resolution those stations fall on land cells. Any comparison across resolutions has to
intersect the ok sets rather than assume the finest grid is a superset.
"""
import argparse
import pathlib as pl
import sys

import numpy as np
import xarray as xr

# Tidal range across this domain is 2-4 m, so a station carrying any real signal
# clears this by an order of magnitude. It only has to separate "wet but not
# connected to the tide" from "resolved".
TIDE_MIN_RANGE_M = 0.25

RESOLUTIONS = ("coarse", "midres", "highres")


def station_names(ds):
    """D-Flow FM writes station_name as a char array; xarray hands it back as
    per-character integers rather than bytes, so it needs decoding either way."""
    out = []
    for row in ds["station_name"].values:
        if isinstance(row[0], (bytes, np.bytes_)):
            out.append(b"".join(row).decode().strip())
        else:
            out.append("".join(chr(int(c)) for c in row).strip())
    return out


def classify(series):
    finite = series[np.isfinite(series)]
    if finite.size == 0:
        return "outside", np.nan
    rng = float(finite.max() - finite.min())
    if np.unique(finite).size == 1:
        return "dry", rng
    if rng < TIDE_MIN_RANGE_M:
        return "disconnected", rng
    return "ok", rng


def last_time(his_path):
    """None if the file cannot be read as a history file yet."""
    if his_path.stat().st_size == 0:
        return None
    try:
        with xr.open_dataset(his_path) as ds:
            return ds["time"].values[-1]
    except Exception:
        return None


def extract(his_path, out_path, force=False):
    if out_path.is_file() and not force:
        return "skip (exists)"

    with xr.open_dataset(his_path) as ds:
        names = station_names(ds)
        wl = ds["waterlevel"].values.astype("float32")
        status, ranges = zip(*(classify(wl[:, i]) for i in range(wl.shape[1])))
        out = xr.Dataset(
            {
                "waterlevel": (("time", "station"), wl),
                "station_name": ("station", np.array(names, dtype=object)),
                "station_x": ("station", ds["station_x_coordinate"].values),
                "station_y": ("station", ds["station_y_coordinate"].values),
                "status": ("station", np.array(status, dtype=object)),
                "tidal_range": ("station", np.array(ranges, dtype="float32")),
            },
            coords={"time": ds["time"].values},
        )

    out["waterlevel"].attrs = {"units": "m", "long_name": "water level"}
    out["status"].attrs = {
        "long_name": "grid resolution of this station",
        "flag_meanings": "ok disconnected dry outside",
        "comment": (
            "dry means the reported value is the bed level, not a water level; "
            f"disconnected means tidal range below {TIDE_MIN_RANGE_M} m"
        ),
    }
    out.attrs = {
        "source": str(his_path),
        "source_bytes": his_path.stat().st_size,
        "created_by": "notebooks-GP/extract_station_his.py",
    }

    # Inherited chunks make these files an order of magnitude larger than they need
    # to be; set them against the dimensions actually being written.
    nt, ns = out.sizes["time"], out.sizes["station"]
    enc = {"waterlevel": {"zlib": True, "complevel": 4,
                          "chunksizes": (min(2048, nt), ns)}}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_netcdf(out_path, encoding=enc)
    n_ok = sum(s == "ok" for s in status)
    return f"{out_path.stat().st_size / 1e6:.2f} MB, {n_ok}/{ns} ok"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=pl.Path, default=pl.Path(__file__).resolve().parent.parent)
    ap.add_argument("--force", action="store_true", help="overwrite existing extracts")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    runs = sorted(p for res in RESOLUTIONS
                  for p in (args.root / "dflow-fm" / res).glob("run_*/output/FlowFM_his.nc"))
    if not runs:
        print("no run history files found", file=sys.stderr)
        return 1

    # An in-progress run cannot be recognized by size: D-Flow FM creates the history
    # file empty and then grows it, so a scenario caught mid-sweep reads as a valid
    # but truncated file and extracts silently. Every sweep covers the same window,
    # so the longest end time across all runs is the target, and anything short of it
    # is still being written.
    ends = {p: last_time(p) for p in runs}
    target = max(t for t in ends.values() if t is not None)
    print(f"target end {str(target)[:16]} ({len(runs)} runs)\n")

    for his in runs:
        scenario = his.parent.parent.name.removeprefix("run_")
        out = args.root / "results" / "gp" / scenario / "station_his.nc"
        if args.dry_run:
            print(f"{scenario:34s} -> {out.relative_to(args.root)}")
            continue
        print(f"{scenario:34s} ", end="", flush=True)
        end = ends[his]
        if end is None:
            print("skip (unreadable -- run in progress)")
            continue
        if end < target:
            print(f"skip (INCOMPLETE, ends {str(end)[:16]} -- run in progress)")
            continue
        try:
            print(extract(his, out, force=args.force))
        except Exception as exc:                       # keep going; report at the end
            print(f"FAILED: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
