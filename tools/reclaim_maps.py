"""Delete FlowFM_map.nc from finished run directories, once the tracer is verified.

The map is the largest thing a run leaves behind -- 11 GB coarse, 28 GB midres, 72 GB
highres -- and nothing downstream reads it: the notebook has already reduced it to
results/<scenario>/dflow_tracer.nc, which is what every figure and archive uses. Left
in place it fills the disk in a few runs; the midres set had 84 GB of maps sitting in
three completed directories while the fourth run was live.

The map goes only when the tracer for that scenario opens as UGRID and carries times.
A killed netCDF write leaves a 48-byte header stub rather than a zero-byte file, so a
size check would accept one and the map that could rebuild it would then be gone;
finish_scenario.py exists precisely to rebuild a tracer from a map, and cannot if the
map has been deleted on a bad check.
"""
import argparse
import pathlib as pl
import sys

import xarray as xr

ROOT = pl.Path(__file__).resolve().parent.parent
GRID_DIR = {"coarse": "coarse", "medium": "midres", "high": "highres"}


def tracer_ok(scenario):
    t = ROOT / "results" / "gp" / scenario / "dflow_tracer.nc"
    if not t.is_file():
        return False, "no tracer"
    try:
        ds = xr.open_dataset(t)
    except Exception as exc:
        return False, f"unreadable ({type(exc).__name__})"
    if "mesh2d_sewage" not in ds.variables:
        return False, "no sewage variable"
    if not ds.sizes.get("time", 0):
        return False, "no time steps"
    return True, f"{ds.sizes['time']} times, {t.stat().st_size / 2**30:.2f} GB"


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--resolution", default="coarse", choices=tuple(GRID_DIR))
    p.add_argument("--scenario", help="one scenario; default is every run directory "
                                      "of this resolution that has a map left")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    base = ROOT / "dflow-fm" / GRID_DIR[a.resolution]
    runs = ([base / f"run_{a.scenario}"] if a.scenario
            else sorted(d for d in base.glob("run_*") if (d / "output/FlowFM_map.nc").is_file()))

    freed = 0
    for d in runs:
        m = d / "output" / "FlowFM_map.nc"
        if not m.is_file():
            print(f"  {d.name}: no map")
            continue
        scenario = d.name[len("run_"):]
        ok, why = tracer_ok(scenario)
        gb = m.stat().st_size / 2**30
        if not ok:
            print(f"  {d.name}: KEEPING map ({gb:.1f} GB) -- tracer {why}")
            continue
        if a.dry_run:
            print(f"  {d.name}: would free {gb:.1f} GB (tracer {why})")
        else:
            m.unlink()
            print(f"  {d.name}: freed {gb:.1f} GB (tracer {why})")
        freed += gb
    print(f"{'would free' if a.dry_run else 'freed'} {freed:.1f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
