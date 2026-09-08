"""Rebuild mapping/<domain>/<resolution>/land_mask.npz from the uncoupled D-Flow FM map.

The masks were committed in 9de512d as binary .npz with no generator, and they are not
a minor input: the mask decides which surface CHD cells are dropped from the coupling
entirely (162 of 691 on coarse) and which GHB cells carry a permanent coastal drain
under coastal_seepage (20 of 72 on highres). Nothing in the repository could re-derive
or re-check them, so this does.

A land face is one D-Flow FM reports NaN water level for at EVERY snapshot and that
never holds depth. Both halves are required, and both are near-tautological on coarse
and midres, where every face is either exactly zero depth throughout or plainly wet --
the mask there is the same under any tolerance from 0 to 1 mm. Highres is the grid
that forces the question: four faces are NaN-stage at all 90 snapshots yet carry a
trace depth of 4e-6 to 1e-4 m at some of them. The committed mask counts the 4e-6 one
as land and the other three as water, which is a depth tolerance somewhere in
[4.02e-6, 4.08e-5] m rather than the exact zero the commit message implies. --depth-tol
defaults to 1e-5 m, inside that bracket, which reproduces all three committed masks
exactly; --depth-tol 0 is the strict reading and drops the single 4e-6 m face from the
highres mask. None of the four carry any GHB or CHD mapping weight, so nothing in the
coupling turns on the choice -- but it should be visible rather than buried in a binary.

The quantifier is doing real work and is not a tolerance question: 706 coarse faces are
NaN at some snapshot and only 609 at all of them.

The source is the UNCOUPLED base run, dflow-fm/<grid>/tides_atm_surge, not a coupled
scenario. Under coastal_seepage the drain discharges onto exactly these faces, and on
coarse that wets all 29 land-fed GHB cells within two coupling steps and they never dry
again -- so a coupled run no longer states which faces the hydrodynamic model carries
no water in. Only the uncoupled run does.

Default is to verify against what is committed and change nothing; --write overwrites.
Exit status is nonzero on any mismatch, so it can gate a figure rebuild.
"""
import argparse
import pathlib as pl
import sys

import numpy as np
import xarray as xr

ROOT = pl.Path(__file__).resolve().parent.parent
# Same rule as liss_settings.DFLOW_RESOLUTION_DICT and reclaim_maps.GRID_DIR, kept
# local so tools/ stays free of liss_settings' matplotlib and contextily imports.
GRID_DIR = {"coarse": "coarse", "medium": "midres", "high": "highres"}
DEPTH_TOL = 1.0e-5


def read_map(map_path):
    with xr.open_dataset(map_path, decode_times=False) as ds:
        return (ds["mesh2d_s1"].values,
                np.nan_to_num(ds["mesh2d_waterdepth"].values, nan=0.0),
                ds.sizes["time"])


def weights(domain, resolution, kind):
    """The GHB or CHD mapping weights for this grid, or None if not built."""
    hits = sorted((ROOT / "mapping" / domain / resolution).glob(f"*_{kind}.npz"))
    if not hits:
        return None
    with np.load(hits[0]) as npz:
        return npz[f"dflow2mf{kind}"]


def land_fed(w, land):
    """(entirely, partly) land-fed boundary cells -- the mask's actual consequence."""
    total = w.sum(axis=1)
    safe = np.where(total > 0.0, total, 1.0)
    frac = np.where(total > 0.0, w[:, land].sum(axis=1) / safe, np.nan)
    return int((frac >= 1.0 - 1e-12).sum()), int(((frac > 1e-12) & (frac < 1.0 - 1e-12)).sum())


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--domain", default="gp")
    p.add_argument("--resolution", default="all", choices=tuple(GRID_DIR) + ("all",))
    p.add_argument("--map", help="map file to read instead of the uncoupled base run; "
                                 "only meaningful with a single --resolution")
    p.add_argument("--depth-tol", type=float, default=DEPTH_TOL, metavar="M",
                   help=f"depth at or below which a face still counts as dry, in metres "
                        f"(default {DEPTH_TOL:g}; 0 is the strict reading)")
    p.add_argument("--write", action="store_true",
                   help="overwrite land_mask.npz; default only verifies")
    a = p.parse_args()

    resolutions = tuple(GRID_DIR) if a.resolution == "all" else (a.resolution,)
    if a.map and len(resolutions) > 1:
        sys.exit("--map takes a single --resolution")

    bad = 0
    for res in resolutions:
        base = ROOT / "dflow-fm" / GRID_DIR[res] / "tides_atm_surge"
        map_path = pl.Path(a.map) if a.map else base / "output" / "FlowFM_map.nc"
        out = ROOT / "mapping" / a.domain / res / "land_mask.npz"
        print(f"\n=== {res} ===")
        if not map_path.is_file():
            print(f"  no map at {map_path} -- cannot build")
            bad += 1
            continue
        print(f"  map        : {map_path.relative_to(ROOT)}")

        s1, hs, ntime = read_map(map_path)
        never_stage = np.isnan(s1).all(axis=0)
        land = never_stage & ~(hs > a.depth_tol).any(axis=0)
        strict = never_stage & ~(hs > 0.0).any(axis=0)
        print(f"  land       : {int(land.sum())} of {land.size} faces, over {ntime} snapshots"
              f"  (NaN-stage {int(never_stage.sum())}, tol {a.depth_tol:g} m)")
        if land.any():
            print(f"  deepest face counted as land: {hs[:, land].max():.3g} m")

        # Faces the tolerance decides. Report them and whether the coupling can see
        # them at all, rather than leaving the choice invisible.
        marginal = np.where(land ^ strict)[0]
        if marginal.size:
            touched = []
            for kind in ("ghb", "chd"):
                w = weights(a.domain, res, kind)
                if w is not None and w[:, marginal].sum() > 0.0:
                    touched.append(kind)
            print(f"  tolerance decides {marginal.size} face(s): {marginal.tolist()}"
                  f"  -- {'weight in ' + '/'.join(touched) if touched else 'no GHB or CHD weight, inert'}")

        for kind, label in (("ghb", "GHB"), ("chd", "surface CHD")):
            w = weights(a.domain, res, kind)
            if w is None:
                continue
            if w.shape[1] != land.size:
                print(f"  {label} weights disagree on the face count: {w.shape[1]} vs {land.size}")
                bad += 1
                continue
            ent, part = land_fed(w, land)
            print(f"  {label:11s}: {ent} entirely land-fed, {part} partly")

        if out.is_file():
            with np.load(out) as npz:
                ref = npz["land"]
            same = ref.shape == land.shape and np.array_equal(ref, land)
            print(f"  committed  : {int(ref.sum())} faces -- "
                  f"{'reproduced exactly' if same else 'DOES NOT MATCH'}")
            if not same:
                bad += 1
                if ref.shape == land.shape:
                    print(f"               {int((ref ^ land).sum())} faces differ: "
                          f"{int((land & ~ref).sum())} newly land, "
                          f"{int((ref & ~land).sum())} no longer land")
        else:
            print("  committed  : none on disk")

        if a.write:
            out.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(out, land=land)
            print(f"  wrote      : {out.relative_to(ROOT)}")

    print()
    if bad:
        print(f"{bad} resolution(s) did not verify")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
