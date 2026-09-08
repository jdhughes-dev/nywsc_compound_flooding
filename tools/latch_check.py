"""Did the coastal drain wet the flat and then switch itself off?

coastal_seepage (e505014) adds drn_coastal on the 72 GHB cells with conductance
C0*(1 - wetted fraction), so an exposed flat keeps an outlet. The drained water is
returned to D-Flow FM through ghb2qext -- onto the same faces -- and on the coarse grid
that is a feedback rather than a boundary condition: in both coarse seep runs all 29
land-fed GHB cells go from dry to fully wet within two coupling steps and never dry
again over 89 days, after which the drain carries nothing and the GHB stands at full
conductance. The same cells are dry in every one of ~8,500 steps of the three surviving
pre-change runs (_t1525, _t1920, _t2320), so it is the change that wets them.

If that is what happens, the run is not measuring "the flat seeps" but "the GHB is
fully on at cells the hydrodynamic grid calls land", which is a different change from
the one the commit describes and it sits under the headline coastal-exchange numbers.

A land-fed cell that has NOT latched holds wetted fraction 1 - (its land fraction),
exactly and for every step -- that is what the published pre-change runs show. So the
two outcomes are cleanly separable, and both are counted here. The intertidal cells are
the control: they cycle with the tide whether or not the land-fed ones latch.
"""
import argparse
import glob
import pathlib as pl
import sys

import numpy as np

ROOT = pl.Path(__file__).resolve().parent.parent
RES_FROM_NAME = {"coarse": "coarse", "medium": "medium", "high": "high"}


def infer_resolution(scenario):
    for token, res in RES_FROM_NAME.items():
        if f"_{token}_" in scenario:
            return res
    return None


def load(scenario, res):
    """Wetted fraction and drain fraction per coupling step, normalized on the base."""
    d = ROOT / "results" / "gp" / scenario
    c0 = np.loadtxt(ROOT / "modflow/gp_chd/base/external/ghb.dat", usecols=4)
    z = np.load(d / "ghb_cond.npz")
    keys = sorted(z.files, key=int)
    # Normalize on the BASE template, never on step 0: step 0 may itself be partly dry,
    # so a step-0 ratio can exceed 1 and look like drift.
    wet = np.stack([z[k] for k in keys]) / c0[None, :]
    drain = None
    if (d / "drn_cond.npz").is_file():
        dz = np.load(d / "drn_cond.npz")
        drain = np.stack([dz[k] for k in keys]) / c0[None, :]
    return wet, drain, c0


def land_fraction(res):
    w = np.load(glob.glob(str(ROOT / "mapping/gp" / res / "*_ghb.npz"))[0])["dflow2mfghb"]
    land = np.load(ROOT / "mapping/gp" / res / "land_mask.npz")["land"]
    return w[:, land].sum(axis=1) / w.sum(axis=1)


def report(scenario, res, quiet):
    wet, drain, c0 = load(scenario, res)
    lf = land_fraction(res)
    idx = np.where(lf > 1e-12)[0]
    nstep = wet.shape[0]
    print(f"\n=== {scenario} ===  {nstep} coupling steps, {wet.shape[1]} GHB cells, "
          f"{len(idx)} land-fed")

    if not quiet and len(idx):
        print("  cell  land   wmin   wmax  wmean  first-full  last-not-full  drain steps")
    latched = held = 0
    for i in idx:
        w = wet[:, i]
        full = w > 0.999
        first = int(np.argmax(full)) if full.any() else -1
        lastn = int(np.max(np.where(~full)[0])) if (~full).any() else -1
        nd = int((drain[:, i] > 1e-9).sum()) if drain is not None else -1
        if full.any() and lastn < first:
            latched += 1
        if abs(w.mean() - (1.0 - lf[i])) < 1e-6 and np.ptp(w) < 1e-6:
            held += 1
        if not quiet:
            print(f"  {i:4d}  {lf[i]:.3f}  {w.min():.3f}  {w.max():.3f}  {w.mean():.3f}"
                  f"  {first:10d}  {lastn:13d}  {nd:11d}")

    if len(idx):
        print(f"  latched (fully wet and never dry again): {latched} of {len(idx)}")
        print(f"  held at 1 - land fraction, every step  : {held} of {len(idx)}")

    # The control: cells that dry with the tide rather than because they are land.
    varies = ((wet.min(axis=0) < 1.0 - 1e-6) & (wet.max(axis=0) > 1e-9))
    tidal = np.where(varies & (lf <= 1e-12))[0]
    print(f"  intertidal cells with no land contribution: {len(tidal)}")

    if drain is not None:
        open_steps = int((drain > 1e-9).any(axis=1).sum())
        print(f"  drain open on {open_steps} of {nstep} steps ({100 * open_steps / nstep:.1f}%)"
              f", mean share of total GHB conductance {100 * (drain.mean(0) * c0).sum() / c0.sum():.2f}%")
    else:
        print("  no drn_cond.npz -- run without coastal_seepage")

    d = ROOT / "results" / "gp" / scenario
    if (d / "drn_flow.npz").is_file():
        f = np.load(d / "drn_flow.npz")
        F = np.stack([f[k] for k in sorted(f.files, key=int)])
        print(f"  drain flow: mean {F.sum(1).mean():.4g} m3/s, max {F.sum(1).max():.4g}, "
              f"nonzero on {int((np.abs(F).sum(1) > 1e-12).sum())} steps")
    return latched, len(idx)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("scenario", nargs="+", help="results/gp/<scenario> directory name(s)")
    p.add_argument("--resolution", choices=tuple(RES_FROM_NAME),
                   help="default is inferred from the scenario name")
    p.add_argument("--quiet", action="store_true", help="summary only, no per-cell table")
    a = p.parse_args()

    missing = 0
    for scenario in a.scenario:
        res = a.resolution or infer_resolution(scenario)
        if res is None:
            print(f"\n=== {scenario} ===  cannot infer resolution; pass --resolution")
            missing += 1
            continue
        if not (ROOT / "results/gp" / scenario / "ghb_cond.npz").is_file():
            print(f"\n=== {scenario} ===  no ghb_cond.npz -- not finished, or never ran")
            missing += 1
            continue
        report(scenario, res, a.quiet)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
