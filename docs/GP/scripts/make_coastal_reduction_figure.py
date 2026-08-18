"""Coastal exchange volume against coupling interval, for both boundary reductions.

Drawn from ../../data/GP/coastal_reduction.nc, which coastal_reduction_data.py
recomputes when the simulation output is present and reads as-is when it is not.

One panel at the journal's single-column width, because the figure makes one
statement: the volume of water the coupling carries across the coast is
independent of the coupling interval under the average and is not under the
sample. A second panel would be a second statement, and the rate behavior it
would carry is already Figure~\\ref{fig:coastal}A.

Plotted as a percent departure rather than in millimeters. The three grids
exchange 223, 281, and 298 mm over the simulation, so in absolute units the
curves separate by grid -- which is a resolution result, reported elsewhere --
and the interval dependence this figure is about would be the small difference
between three widely spaced bands.
"""
import pathlib as pl
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
import flopy.plot.styles as styles

sys.path.insert(0, str(pl.Path(__file__).resolve().parent))
import coastal_reduction_data as crd          # noqa: E402

mpl.rcParams["ps.fonttype"] = 42

OUT = pl.Path(__file__).resolve().parent.parent / "figures" / "coastal_reduction.pdf"

# The reduction colors of Figures 2 and 3, so the two reductions are the same two
# colors everywhere in the manuscript.
C_I, C_M = "#d62728", "#1f77b4"
# Grid is carried by marker and dash alone. Three grids times two reductions is six
# curves in a 90 mm panel, and six colors would be unreadable at that size; two
# colors that mean the thing the figure is about are not.
GRID_STYLE = {"coarse": ("o", "-", "coarse"),
              "medium": ("s", (0, (4, 1.5)), "medium"),
              "high": ("^", (0, (1.2, 1.2)), "fine")}


def make(refresh=True):
    if refresh:
        ds, source = crd.load_or_refresh()
        print("volumes recomputed from results/" if source == "results"
              else f"volumes read from archive ({len(crd.missing())} runs absent)")
    else:
        ds = xr.open_dataset(crd.NC, decode_timedelta=False)
        print(f"volumes read from {crd.NC.name} without recomputing")

    h = ds["hours"].values
    # Every interval the manuscript discusses is labeled, which is all nine, and nine
    # will not fit one horizontal row of a 90 mm axis: 6 and 8 hours are 0.125 decades
    # apart, closer than any other pair, and their labels would touch.
    #
    # Turning the labels upright removes the constraint rather than working around it.
    # A vertical label occupies its line height along the axis, about 8 pt at 7 pt
    # type, against the 12 pt that 0.125 decades spans here. Forty-five degrees does
    # not fit: it needs that line height divided by sin 45, about 12 pt, which is the
    # whole of the gap. So the rotation is a right angle and all nine sit on one row.
    tick_h = list(h)
    tick_lab = [f"{v * 60:.0f} min" if v < 1 else f"{v:.0f} h" if v < 24
                else f"{v / 24:.0f} d" for v in tick_h]

    with styles.USGSPlot():
        # 3.54 in is 90 mm, the journal's single-column artwork width, so the figure
        # is placed 1:1 and its 7 pt annotations stay 7 pt on the page.
        fig, ax = plt.subplots(figsize=(3.54, 3.54), layout="constrained")

        ax.axhline(0.0, color="0.35", lw=0.9, linestyle=(0, (3, 2)), zorder=1)
        ax.axvline(crd.bad.NYQUIST_H, color="0.35", lw=0.9, linestyle=(0, (3, 2)),
                   zorder=1)

        for grid, (marker, dashes, _) in GRID_STYLE.items():
            g = ds.sel(grid=grid)
            for var, color in (("pct_inst", C_I), ("pct_mean", C_M)):
                y = g[var].values
                m = np.isfinite(y)      # 6 and 12 hours exist on the coarse grid only
                ax.plot(h[m], y[m], marker=marker, linestyle=dashes, color=color,
                        lw=1.1, ms=3.4, zorder=3)

        ax.set_xscale("log")
        ax.set_xticks(tick_h)
        ax.set_xticklabels(tick_lab, fontsize=7, rotation=90, ha="center",
                           va="top")
        ax.tick_params(labelsize=7, top=False)
        ax.set_ylim(-2.5, 40.0)
        styles.xlabel(ax=ax, label="Coupling interval")
        styles.ylabel(ax=ax, label="Cumulative coastal exchange,\nin percent from the "
                                   "15-minute simulation")

        ax.annotate(r"$M_2$ Nyquist", xy=(crd.bad.NYQUIST_H, 0.985),
                    xycoords=("data", "axes fraction"),
                    xytext=(3, 0), textcoords="offset points",
                    fontsize=6.5, color="0.35", va="top", ha="left")

        # Two legends, because the figure encodes two things and one combined legend
        # of six entries would not fit. Color carries the reduction, which is what
        # the figure is about, so it is the one named in words; the grid legend is
        # gray, to be read as a qualifier rather than as a third variable.
        # The words Figure 3 uses, not synonyms of them: the two reductions carry the
        # same two colors and the same two names in every figure that shows both.
        red = [plt.Line2D([], [], color=C_I, lw=1.4, label="instantaneous"),
               plt.Line2D([], [], color=C_M, lw=1.4, label="time-averaged")]
        grids = [plt.Line2D([], [], color="0.45", lw=1.0, ls=s, marker=m, ms=3.4,
                            label=lab) for m, s, lab in GRID_STYLE.values()]
        leg1 = ax.legend(handles=red, labels=[h.get_label() for h in red],
                         loc="upper left", frameon=False, fontsize=7,
                         handlelength=2.0, borderaxespad=0.4, labelspacing=0.3)
        # The USGS EXPLANATION heading, which the other figures carry. It sits over
        # the reduction entries and reads as covering the grid entries below them
        # as well, which is what it should do.
        styles.graph_legend_title(leg1, fontsize=7.5)
        ax.add_artist(leg1)
        ax.legend(handles=grids, labels=[h.get_label() for h in grids],
                  loc="upper left", frameon=False, fontsize=6.5,
                  handlelength=2.6, borderaxespad=0.4, labelspacing=0.25,
                  bbox_to_anchor=(0.0, 0.80))

        fig.savefig(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    make(refresh="--no-refresh" not in sys.argv)
