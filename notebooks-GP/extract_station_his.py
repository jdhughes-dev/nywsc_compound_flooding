"""Extract the station water levels from each run's D-Flow FM history file.

The history file lives in the run directory, which the sweep reuses, so a rerun
overwrites it; this copies the station series into results/ before that can happen.
Each station is tagged with whether the grid actually resolves it.
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
    """A history file reports a value at every station whether or not the grid
    resolves it, and the failure modes are not distinguishable from the value alone.

    dry is the dangerous one: the constant reported is the BED level, not a water
    level -- coarse Port Jefferson gives a flat 21.084 m -- so unguarded it plots as
    a plausible-looking line. disconnected means the cell is wet but sitting near the
    initial condition because the grid does not resolve the channel to the sound.

    Coverage is not nested by resolution: the highres grid resolves Battery, which
    coarse misses, but loses New London, which midres resolves. Comparisons across
    resolutions must intersect the ok sets.
    """
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
