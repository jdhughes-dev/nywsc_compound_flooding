"""Error in the coupled solution against a 15-minute reference, for both reductions.

Drawn from ../../data/GP/boundary_averaging.nc, which boundary_averaging_data.py
recomputes when the simulation output is present and reads as-is when it is not.
"""
import pathlib as pl
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import flopy.plot.styles as styles

sys.path.insert(0, str(pl.Path(__file__).resolve().parent))
import boundary_averaging_data as bad          # noqa: E402

mpl.rcParams["ps.fonttype"] = 42

FIGURES = pl.Path(__file__).resolve().parent.parent / "figures"
NYQUIST_H = bad.NYQUIST_H
C_I, C_M = "#d62728", "#1f77b4"

# The instantaneous 15-minute simulation is the incumbent formulation, so it is the
# reference plotted. The archive also carries the averaged reference and the two
# agree; that check belongs in the notebook, not in the figure.
REF = "15M instant"


PANELS = {"head": ("head_inst", "head_mean", "Aquifer head RMSE, in millimeters"),
          "seep": ("seep_inst", "seep_mean",
                   "Sewer seepage RMSE, in cubic feet per day"),
          "trac": ("trac_inst", "trac_mean", "Sewer tracer RMSE, dimensionless"),
          "peak": ("peak_inst", "peak_mean", "Peak sewer tracer concentration")}

MOSAIC = [["head", "seep"], ["trac", "peak"]]
BOTTOM = set(MOSAIC[-1])


def output_path(grid):
    """The default grid keeps the bare name the manuscript already includes."""
    stem = "boundary_averaging" if grid == bad.DEFAULT_GRID \
        else f"boundary_averaging_{grid}"
    return FIGURES / f"{stem}.pdf"


def make(grid=bad.DEFAULT_GRID):
    out = output_path(grid)
    ds, source = bad.load_or_refresh(grid=grid)
    print("statistics recomputed from results/" if source == "results"
          else f"statistics read from archive "
               f"({len(bad.missing(grid=grid))} runs absent)")

    sub = ds.sel(ref=REF)
    order = np.argsort(ds["hours"].values)
    h = ds["hours"].values[order]
    s = {v: sub[v].values[order] for v in sub.data_vars}
    peak_ref = float(ds.attrs["peak_reference_concentration"])

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
            ax.plot(h, s[ci], "o-", color=C_I, lw=1.2, ms=4, label="instantaneous")
            ax.plot(h, s[cm], "s-", color=C_M, lw=1.2, ms=4, label="time-averaged")
            ax.set_xscale("log")
            if key != "peak":
                # The peak panel is a concentration against a reference value, not an
                # error that spans decades, so a log scale would flatten the departure
                # that is the whole point of it.
                ax.set_yscale("log")
            else:
                ax.axhline(peak_ref, color="0.35", lw=0.9, linestyle=(0, (3, 2)),
                           zorder=1)
                ax.annotate("reference", xy=(0.02, peak_ref),
                            xycoords=("axes fraction", "data"),
                            xytext=(0, 3), textcoords="offset points",
                            fontsize=6.5, color="0.35")
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
            ax.annotate(r"$M_2$ Nyquist", xy=(NYQUIST_H, 0.96),
                        xycoords=("data", "axes fraction"),
                        xytext=(3, 0), textcoords="offset points",
                        fontsize=6.5, color="0.35", va="top", ha="left")
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
    make(sys.argv[1] if len(sys.argv) > 1 else bad.DEFAULT_GRID)
