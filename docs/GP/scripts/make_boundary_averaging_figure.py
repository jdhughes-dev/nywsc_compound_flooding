"""Error in the coupled solution against a 15-minute reference, for both reductions.

Drawn from ../../data/GP/boundary_averaging.nc, which boundary_averaging_data.py
recomputes when the simulation output is present and reads as-is when it is not.
"""
import pathlib as pl
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
import flopy.plot.styles as styles

sys.path.insert(0, str(pl.Path(__file__).resolve().parent))
import boundary_averaging_data as bad          # noqa: E402

mpl.rcParams["ps.fonttype"] = 42

FIGURES = pl.Path(__file__).resolve().parent.parent / "figures"
NYQUIST_H = bad.NYQUIST_H
C_I, C_M = "#d62728", "#1f77b4"
FT3_TO_M3 = 0.028316846592

# The instantaneous 15-minute simulation is the incumbent formulation, so it is the
# reference plotted. The archive also carries the averaged reference and the two
# agree; that check belongs in the notebook, not in the figure.
REF = "15M instant"


# Panel D was the maximum over the whole space-time field until it was found to be a
# single cell -- 1669 on the coarse grid in every run, at 7.9 times the 99.99th
# percentile, and moving by tens of percent while the field around it did not move at
# all. It is now the 99.99th percentile, which no single cell can carry, so the panel
# and the text say the same thing about the tracer.
PANELS = {"head": ("head_inst", "head_mean", "Aquifer head RMSE, in millimeters"),
          "seep": ("seep_inst", "seep_mean",
                   "Sewer seepage RMSE, in cubic meters per day"),
          "trac": ("trac_inst", "trac_mean", "Sewer tracer RMSE, dimensionless"),
          "amp": ("p9999_inst", "p9999_mean",
                  "Sewer tracer 99.99th percentile, percent from reference")}

# Coastal exchange is computed and archived as coast_inst/coast_mean but is NOT
# plotted here, and should not be. qext is the flux formed directly from the reduced
# boundary value, so scoring it against a reference built under one reduction mostly
# measures which reduction the run used rather than how accurate it is: against the
# sampled reference the sampled runs score 0.0017 to 0.43 and the averaged ones 0.66
# to 6.5, and merely changing to the averaged reference moves the sampled column to a
# nearly constant 0.25 to 0.39. Head and seepage do not behave that way because they
# are the aquifer's response rather than the boundary condition restated.
MOSAIC = [["head", "seep"], ["trac", "amp"]]
BOTTOM = set(MOSAIC[-1])


def output_path(grid):
    """The default grid keeps the bare name the manuscript already includes."""
    stem = "boundary_averaging" if grid == bad.DEFAULT_GRID \
        else f"boundary_averaging_{grid}"
    return FIGURES / f"{stem}.pdf"


def make(grid=bad.DEFAULT_GRID, refresh=True):
    """Draw the figure; with refresh=False, read the archive without recomputing.

    Recomputing reads every tracer and every qext series, tens of gigabytes per
    grid, which is the right default when the simulation output has changed and an
    absurd price for adjusting a label. --no-refresh is for the latter.
    """
    out = output_path(grid)
    if refresh:
        ds, source = bad.load_or_refresh(grid=grid)
        print("statistics recomputed from results/" if source == "results"
              else f"statistics read from archive "
                   f"({len(bad.missing(grid=grid))} runs absent)")
    else:
        ds = xr.open_dataset(bad.archive_path(grid), decode_timedelta=False)
        print(f"statistics read from {bad.archive_path(grid).name} without recomputing")

    sub = ds.sel(ref=REF)
    order = np.argsort(ds["hours"].values)
    h = ds["hours"].values[order]
    s = {v: sub[v].values[order] for v in sub.data_vars}
    amp_ref = float(ds.attrs["p9999_reference_concentration"])

    # Ticks are the intervals actually simulated, so they follow the archive rather
    # than a hard-coded list that would silently drop a point when one is added. The
    # sub-hour case is handled because the finest interval is 15 minutes and "%.0f h"
    # renders it as "0 h".
    TICK_H = list(h)
    TICK_LAB = [f"{v * 60:.0f} min" if v < 1 else f"{v:.0f} h" if v < 24
                else f"{v / 24:.0f} d" for v in h]

    with styles.USGSPlot():
        # sharex only: the four panels carry different quantities, so the y axes stay
        # independent and label_outer() would wrongly strip the right column's y labels.
        fig, axd = plt.subplot_mosaic(MOSAIC, figsize=(7.5, 4.5), layout="constrained",
                                      sharex=True)
        for letter, (key, (ci, cm, lab)) in zip("ABCD", PANELS.items()):
            ax = axd[key]
            yi, ym = s[ci], s[cm]
            if key == "seep":
                # MODFLOW works in feet and the archive records the seepage RMSE as
                # it comes out, in cubic feet per day. The manuscript is in SI, so
                # the conversion is applied here rather than by re-deriving the
                # archive, whose units attribute states what it holds.
                yi, ym = yi * FT3_TO_M3, ym * FT3_TO_M3
            if key == "amp":
                # Plotted as a percent departure, because the absolute values differ
                # by a factor of four between grids and the panel has to be read the
                # same way on each.
                yi = 100.0 * (yi - amp_ref) / amp_ref
                ym = 100.0 * (ym - amp_ref) / amp_ref
            ax.plot(h, yi, "o-", color=C_I, lw=1.2, ms=4, label="instantaneous")
            ax.plot(h, ym, "s-", color=C_M, lw=1.2, ms=4, label="time-averaged")
            ax.set_xscale("log")
            if key != "amp":
                # The amplitude panel is a concentration against a reference value,
                # not an error that spans decades, so a log scale would flatten the
                # departure that is the whole point of it.
                ax.set_yscale("log")
            else:
                ax.axhline(0.0, color="0.35", lw=0.9, linestyle=(0, (3, 2)), zorder=1)
                # Lifted well clear of the line: the 30-minute points sit on it,
                # and a 3 pt offset put the label on them.
                ax.annotate("reference", xy=(0.02, 0.0),
                            xycoords=("axes fraction", "data"),
                            xytext=(0, 9), textcoords="offset points",
                            fontsize=6.5, color="0.35")
                # A floor on the span, so that a tracer which does not respond reads
                # as flat instead of being magnified to fill the panel. On the coarse
                # grid the entire spread is 1.3 percent, which autoscaling turns into
                # a picture of structure that is not there.
                lo = float(min(yi.min(), ym.min()))
                hi = float(max(yi.max(), ym.max()))
                mid, half = 0.5 * (lo + hi), max(2.5, 0.65 * (hi - lo))
                ax.set_ylim(mid - half, mid + half)
            ax.axvline(NYQUIST_H, color="0.35", lw=0.9, linestyle=(0, (3, 2)), zorder=1)
            ax.set_xticks(TICK_H)
            ax.set_xticklabels(TICK_LAB, fontsize=7)
            ax.tick_params(labelsize=7, top=False)
            # The x axis is the same in all four, so only the bottom row carries its
            # labels and title; repeating them cost a band of white across the middle.
            if key in BOTTOM:
                styles.xlabel(ax=ax, label="Coupling interval")
            else:
                ax.tick_params(labelbottom=False)
            # Anchored in axes fraction, not to get_ylim()[1]: the data top IS the top
            # spine, so the label sat on it.
            # Left of the line: right of it the label ran toward the frame, and in
            # panel B into the data.
            ax.annotate(r"$M_2$ Nyquist", xy=(NYQUIST_H, 0.96),
                        xycoords=("data", "axes fraction"),
                        xytext=(-3, 0), textcoords="offset points",
                        fontsize=6.5, color="0.35", va="top", ha="right")
            styles.heading(ax=ax, letter=letter, heading=lab, fontsize=7.5)

        # A FIGURE legend placed "outside", not an axes legend anchored beyond its axes.
        # styles.graph_legend calls ax.legend, and constrained layout reserves no space
        # for a legend hanging outside an axes -- bbox_inches="tight" then grew the
        # canvas around it after the fact, which was the white space. graph_legend_title
        # applies the same EXPLANATION heading to any legend object, so nothing is lost.
        hs, ls = axd["head"].get_legend_handles_labels()
        leg = fig.legend(hs, ls, loc="outside lower center", ncol=2, frameon=False,
                         prop={"weight": "bold", "size": 7.5})
        styles.graph_legend_title(leg, fontsize=7.5)
        fig.savefig(out)
    print("wrote", out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    make(args[0] if args else bad.DEFAULT_GRID,
         refresh="--no-refresh" not in sys.argv)
