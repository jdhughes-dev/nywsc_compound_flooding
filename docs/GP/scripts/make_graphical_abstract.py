"""The graphical abstract, which the journal requires as a separate file.

Environmental Modelling & Software asks for 531 x 1328 px (h x w), or proportionally
more, legible at 5 x 13 cm. The canvas below is 13.28 x 5.31 cm, which is that pixel
specification at 254 dpi and just over the legibility size, so the figure is drawn at
the size it will be read at rather than at a size it will be reduced from. Nothing is
scaled afterwards: the point sizes here are the point sizes on the page.

Three panels, one per claim the paper makes:

  A  the three simulators are coupled in memory, none of them modified
  B  at intervals past the M2 Nyquist, sampling the tidal boundary costs an order of
     magnitude in aquifer head error that averaging does not
  C  and buying back that interval is nearly free

Panels B and C are drawn from the same archives as Figures 3 and 7 -- boundary
averaging on the coarse grid, and the run-time summary -- so the graphical abstract
cannot disagree with the document. It is a reduction of those figures, not a
restatement: B keeps one of four panels, and C drops the instantaneous series, whose
only job in Figure 7 is to show that the two reductions cost the same.

Panel A reuses the lane colors and the exchanged-quantity symbols of Figure 1 so that
a reader who arrives at the paper through this image meets the same vocabulary.

The file is NOT included in the document. It is submission artwork, and it deliberately
stays out of the .tex so that it never enters the figure numbering.
"""
import pathlib as pl
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import flopy.plot.styles as styles

sys.path.insert(0, str(pl.Path(__file__).resolve().parent))
import boundary_averaging_data as bad          # noqa: E402
import coupling_cost_data as ccd               # noqa: E402

# flopy's style supplies pdf.fonttype 42 but not ps.fonttype; set it so the figure is
# safe if it is ever converted to EPS, which the guide also accepts.
mpl.rcParams["ps.fonttype"] = 42

OUT = pl.Path(__file__).resolve().parent.parent / "figures" / "graphical_abstract.pdf"

# 1328 x 531 px at 254 dpi, in inches.
FIGSIZE = (1328 / 254.0, 531 / 254.0)

NYQUIST_H = bad.NYQUIST_H
REF = "15M instant"                    # the incumbent formulation, as in Figure 3
GRID = bad.DEFAULT_GRID                # coarse, the grid Figure 3 is drawn for

# Figure 3's assignment: red is the sampled boundary, blue the averaged one.
C_I, C_M = "#d62728", "#1f77b4"
# Figure 1's lane colors, by simulator.
LANE = {"SWMM": "#2ca02c", "D-Flow FM": "#1f77b4", "MODFLOW 6": "#d62728"}
# Figure 7's grid colors.
# The first label carries the noun, so the legend does not need a title to say what
# the three entries are.
GRIDS = [("coarse", "#1f77b4", "Coarse grid"),
         ("medium", "#2ca02c", "Medium"),
         ("high", "#d62728", "Fine")]

# Four ticks, not the nine intervals simulated. At 4.3 cm of panel width the full set
# overlaps into a smear, and the interval axis is read here for its decades rather
# than for which points were run -- that is what Figures 3 and 7 are for.
#
# Panels B and C share these ticks, including the 15-minute one, although B has no
# point there: 15 minutes is the reference its errors are measured against, so it is
# by construction the one interval with no error to plot. Giving B its own axis
# starting at 30 minutes would misalign the two panels, and a reader comparing them
# left to right would then be comparing different intervals at the same position.
TICKS = [(0.25, "15 min"), (1.0, "1 h"), (6.0, "6 h"), (24.0, "1 d")]

FS_HEAD, FS_TICK, FS_NOTE = 7.0, 6.0, 6.0


def interval_axis(ax):
    ax.set_xscale("log")
    ax.set_xticks([h for h, _ in TICKS])
    ax.set_xticklabels([lab for _, lab in TICKS], fontsize=FS_TICK)
    ax.tick_params(labelsize=FS_TICK, top=False, which="both")
    ax.minorticks_off()
    ax.axvline(NYQUIST_H, color="0.35", lw=0.8, linestyle=(0, (3, 2)), zorder=1)
    styles.xlabel(ax=ax, label="Coupling interval", fontsize=FS_HEAD)


def panel_coupling(ax):
    """The three simulators in one process, and what crosses between them.

    Stacked in Figure 1's lane order (SWMM, D-Flow FM, MODFLOW 6) rather than in
    physical order, so the two figures can be read against each other. The seepage
    connects the top and bottom boxes and therefore routes outside the stack on the
    right; every other exchange is between neighbors and runs in the gutter.
    """
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Vertical budget, in axes fraction, laid out top down: a title, three boxes tall
    # enough for two lines of text, two gutters wide enough that an arrow reads as a
    # line rather than as a bare arrowhead, and two footer lines.
    x0, x1 = 0.02, 0.78           # the boxes; 0.78 to 1.0 is the seepage channel
    boxes = [("SWMM", 0.795, 0.915, "PySWMM toolkit"),
             ("D-Flow FM", 0.525, 0.645, "Basic Model Interface"),
             ("MODFLOW 6", 0.255, 0.375, "MODFLOW 6 API")]
    for name, lo, hi, iface in boxes:
        ax.add_patch(FancyBboxPatch((x0, lo), x1 - x0, hi - lo,
                                    boxstyle="round,pad=0,rounding_size=0.02",
                                    facecolor=LANE[name], edgecolor="none",
                                    alpha=0.90, zorder=3))
        ax.text((x0 + x1) / 2.0, (lo + hi) / 2.0 + 0.020, name, ha="center",
                va="center", fontsize=FS_HEAD, color="white", weight="bold",
                zorder=4)
        # The interface each simulator is driven through is the mechanism claim, so
        # it rides inside the box rather than in a caption that will not travel.
        ax.text((x0 + x1) / 2.0, (lo + hi) / 2.0 - 0.034, iface, ha="center",
                va="center", fontsize=5.0, color="white", zorder=4)

    def arrow(x, ylo, yhi, up, color, label, ha, lx, ly):
        a, b = (ylo, yhi) if up else (yhi, ylo)
        ax.add_patch(FancyArrowPatch((x, a), (x, b), arrowstyle="-|>",
                                     mutation_scale=5, lw=0.9, color=color,
                                     shrinkA=0, shrinkB=0, zorder=5))
        ax.text(lx, ly, label, ha=ha, va="center", fontsize=FS_NOTE, color=color,
                zorder=5)

    # SWMM -> D-Flow FM, alone in the upper gutter.
    arrow(0.14, 0.650, 0.790, False, LANE["SWMM"], r"$\bar{Q}_s$", "left", 0.18, 0.720)
    # The lower gutter carries two, in opposite directions. They are separated in x
    # AND their labels are staggered in y: side by side at the same height the two
    # labels touch, which is what a single gutter cannot fit.
    arrow(0.14, 0.380, 0.520, False, LANE["D-Flow FM"],
          r"$\bar{s}_1,\bar{h}_s$", "left", 0.18, 0.427)
    arrow(0.62, 0.380, 0.520, True, LANE["MODFLOW 6"],
          r"$Q^{\mathrm{ext}}$", "right", 0.58, 0.473)

    # The seepage is a property of neither model, so it is drawn neutral, as in
    # Figure 1's legend. It spans two boxes and so routes outside the stack.
    ax.add_patch(FancyArrowPatch((0.88, 0.315), (0.88, 0.855), arrowstyle="<|-|>",
                                 mutation_scale=5, lw=0.9, color="0.25",
                                 shrinkA=0, shrinkB=0, zorder=5))
    for y in (0.315, 0.855):
        ax.plot([0.78, 0.88], [y, y], color="0.25", lw=0.9, zorder=5)
    ax.text(0.92, 0.585, r"$Q_j$", ha="left", va="center", fontsize=FS_NOTE,
            color="0.25", zorder=5)

    ax.text(0.5, 0.975, "Three simulators, one process", ha="center", va="top",
            fontsize=FS_HEAD, color="0.25", weight="bold")
    # The gap the paper opens: the exchange has to happen inside the time step, and
    # BMI has no verb for that. Stated here because it is the reason for the work.
    ax.text(0.5, 0.135, "None modified, and coupled in memory", ha="center",
            va="center", fontsize=5.6, color="0.35", style="italic")
    ax.text(0.5, 0.045, "BMI defines no sub-time-step exchange", ha="center",
            va="center", fontsize=5.6, color="0.35", style="italic")


def panel_error(ax, ds):
    order = np.argsort(ds["hours"].values)
    h = ds["hours"].values[order]
    yi = ds["head_inst"].values[order]
    ym = ds["head_mean"].values[order]

    # "instantaneous", not "sampled", because that is what Figure 3's legend says.
    ax.plot(h, yi, "o-", color=C_I, lw=1.1, ms=3, label="instantaneous")
    ax.plot(h, ym, "s-", color=C_M, lw=1.1, ms=3, label="time-averaged")
    ax.set_yscale("log")
    interval_axis(ax)
    # Shorter than Figure 3's "Aquifer head RMSE, in millimeters". A heading is drawn
    # from the left spine and is not wrapped, so at 4 cm of panel width the longer
    # form runs off the canvas -- and the canvas size is fixed by the journal here,
    # so it cannot be grown to fit.
    styles.heading(ax=ax, heading="Head RMSE, in millimeters", fontsize=FS_HEAD)

    # The ratio at daily coupling, read off the data rather than written in, so the
    # number cannot drift from the archive it is drawn from.
    ratio = float(yi[-1] / ym[-1])
    ax.annotate(rf"$\times${ratio:.0f}", xy=(h[-1], np.sqrt(yi[-1] * ym[-1])),
                xytext=(-3, 0), textcoords="offset points", ha="right",
                va="center", fontsize=FS_NOTE, color="0.25", weight="bold")
    ax.annotate(r"$M_2$ Nyquist", xy=(NYQUIST_H, 0.04),
                xycoords=("data", "axes fraction"), xytext=(-3, 0),
                textcoords="offset points", fontsize=5.6, color="0.35",
                va="bottom", ha="right", rotation=90)
    leg = ax.legend(loc="upper left", frameon=False, handlelength=1.4,
                    borderpad=0.1, labelspacing=0.25, handletextpad=0.4,
                    prop={"weight": "bold", "size": FS_NOTE})
    leg.set_zorder(6)


def panel_cost(ax, df):
    """Run time against interval, relative to each series' own daily-coupling run.

    Only the averaged series is drawn. Figure 7 carries both because showing that the
    two reductions cost the same is part of its argument; here that would be three
    extra curves in 4 cm of width, saying something the abstract does not claim.
    """
    top = {}
    for grid, color, label in GRIDS:
        s = df[(df["grid"] == grid) & (df["reduction"] == "meanbnd")].sort_values("steps")
        if len(s) < 4:
            continue
        base = float(s.iloc[0]["minutes"])
        pct = 100.0 * (s["minutes"].values / base - 1.0)
        ax.plot(s["hours"].values, pct, "o-", color=color, lw=1.1, ms=3, label=label)
        top[grid] = pct[-1]

    ax.axhline(0.0, color="0.35", lw=0.8, zorder=0)
    interval_axis(ax)
    styles.heading(ax=ax, heading="Extra run time, in percent", fontsize=FS_HEAD)

    # The claim the panel exists to make. Placed mid-right rather than top-right: the
    # legend holds the top-left, and every curve has descended out of this band by
    # 2 hours, so it is the largest clear area in the panel.
    if "high" in top:
        ax.annotate(f"96$\\times$ the exchanges\nfor {top['high']:.0f} percent"
                    f"\non the fine grid",
                    xy=(0.97, 0.60), xycoords="axes fraction", ha="right",
                    va="center", fontsize=5.6, color="0.35", linespacing=1.35)
    leg = ax.legend(loc="upper left", frameon=False, handlelength=1.4,
                    borderpad=0.1, labelspacing=0.25, handletextpad=0.4,
                    prop={"weight": "bold", "size": FS_NOTE})
    leg.set_zorder(6)


def make(refresh=True):
    """Draw the graphical abstract; with refresh=False, read the archives as committed."""
    if refresh:
        bds, bsrc = bad.load_or_refresh(grid=GRID)
        cds, csrc = ccd.load_or_refresh()
    else:
        bds = xr.open_dataset(bad.archive_path(GRID), decode_timedelta=False)
        cds = xr.open_dataset(ccd.NC, decode_timedelta=False)
        bsrc = csrc = "archive"
    print("boundary averaging recomputed from results/" if bsrc == "results"
          else "boundary averaging read from archive")
    print("timings recomputed from logs/" if csrc == "logs"
          else "timings read from archive")

    sub = bds.sel(ref=REF)
    df = cds.to_dataframe().reset_index().dropna(subset=["minutes"])

    with styles.USGSPlot():
        # width_ratios: the schematic carries text at a fixed size and cannot be
        # compressed the way an axes with a log scale can.
        fig, axs = plt.subplots(ncols=3, figsize=FIGSIZE, layout="constrained",
                               width_ratios=[1.35, 1.0, 1.0])
        panel_coupling(axs[0])
        panel_error(axs[1], sub)
        panel_cost(axs[2], df)
        fig.get_layout_engine().set(w_pad=0.02, h_pad=0.01, wspace=0.03)
        # No bbox_inches="tight": the canvas size IS the deliverable here, and
        # trimming to the ink would return a figure of some other aspect ratio.
        fig.savefig(OUT)
    print("wrote", OUT, f"({FIGSIZE[0] * 2.54:.2f} x {FIGSIZE[1] * 2.54:.2f} cm)")


if __name__ == "__main__":
    make(refresh="--no-refresh" not in sys.argv)
