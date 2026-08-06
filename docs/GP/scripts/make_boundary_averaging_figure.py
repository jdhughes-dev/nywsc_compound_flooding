"""Error in the coupled solution against a 30-minute reference, for both reductions.

Drawn from ../../data/boundary_averaging.nc, which boundary_averaging_data.py
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

OUT = pl.Path(__file__).resolve().parent.parent / "figures" / "boundary_averaging.pdf"
NYQUIST_H = bad.NYQUIST_H
C_I, C_M = "#d62728", "#1f77b4"

# The instantaneous 30-minute simulation is the incumbent formulation, so it is the
# reference plotted. The archive also carries the averaged reference and the two
# agree; that check belongs in the notebook, not in the figure.
REF = "30M instant"

ds, source = bad.load_or_refresh()
print("statistics recomputed from results/" if source == "results"
      else f"statistics read from archive ({len(bad.missing())} runs absent)")

sub = ds.sel(ref=REF)
order = np.argsort(ds["hours"].values)
h = ds["hours"].values[order]
s = {v: sub[v].values[order] for v in sub.data_vars}
peak_ref = float(ds.attrs["peak_reference_concentration"])

with styles.USGSPlot():
    fig, axs = plt.subplots(nrows=2, ncols=2, figsize=(7.5, 5.2), layout="constrained")
    panels = [(axs[0, 0], "head_inst", "head_mean", "Aquifer head RMSE, in millimeters"),
              (axs[0, 1], "seep_inst", "seep_mean",
               "Sewer seepage RMSE, in cubic feet per day"),
              (axs[1, 0], "trac_inst", "trac_mean", "Sewer tracer RMSE, dimensionless")]
    for i, (ax, ci, cm, lab) in enumerate(panels):
        ax.plot(h, s[ci], "o-", color=C_I, lw=1.2, ms=4, label="instantaneous")
        ax.plot(h, s[cm], "s-", color=C_M, lw=1.2, ms=4, label="time-averaged")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.axvline(NYQUIST_H, color="0.35", lw=0.9, linestyle=(0, (3, 2)), zorder=1)
        ax.set_xticks([2, 4, 8, 24])
        ax.set_xticklabels(["2 h", "4 h", "8 h", "1 d"], fontsize=7)
        ax.tick_params(labelsize=7, top=False)
        styles.heading(ax=ax, letter="ABCD"[i], heading=lab, fontsize=7.5)

    ax = axs[1, 1]
    ax.axhline(peak_ref, color="0.35", lw=0.9, linestyle=(0, (3, 2)), zorder=1)
    ax.plot(h, s["peak_inst"], "o-", color=C_I, lw=1.2, ms=4)
    ax.plot(h, s["peak_mean"], "s-", color=C_M, lw=1.2, ms=4)
    ax.axvline(NYQUIST_H, color="0.35", lw=0.9, linestyle=(0, (3, 2)), zorder=1)
    ax.set_xscale("log")
    ax.set_xticks([2, 4, 8, 24])
    ax.set_xticklabels(["2 h", "4 h", "8 h", "1 d"], fontsize=7)
    ax.tick_params(labelsize=7, top=False)
    styles.heading(ax=ax, letter="D", heading="Peak sewer tracer concentration",
                   fontsize=7.5)
    ax.annotate("reference", xy=(2.05, peak_ref), xytext=(2.05, peak_ref * 1.04),
                fontsize=6.5, color="0.35")

    for ax in axs.flat:
        styles.xlabel(ax=ax, label="Coupling interval")
        ax.annotate(r"$M_2$ Nyquist", xy=(NYQUIST_H, ax.get_ylim()[1]),
                    xytext=(NYQUIST_H * 1.06, ax.get_ylim()[1]),
                    fontsize=6.5, color="0.35", va="top")
    hs, ls = axs[0, 0].get_legend_handles_labels()
    styles.graph_legend(ax=axs[1, 0], handles=hs, labels=ls, loc="lower center",
                        bbox_to_anchor=(1.05, -0.42), ncol=2, frameon=False,
                        fontsize=7.5)
    fig.savefig(OUT, bbox_inches="tight")
print("wrote", OUT)
