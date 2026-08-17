"""Aquifer-sewer exchange across the three grids, at 15-minute coupling.

Drawn from ../../data/GP/sewer_exchange.nc, which sewer_exchange_data.py recomputes
when the simulation output is present and reads as-is when it is not.
"""
import pathlib as pl
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
import flopy.plot.styles as styles

sys.path.insert(0, str(pl.Path(__file__).resolve().parent))
import sewer_exchange_data as sed          # noqa: E402

mpl.rcParams["ps.fonttype"] = 42

OUT = pl.Path(__file__).resolve().parent.parent / "figures" / "sewer_exchange.pdf"
GRIDS = [("coarse", "#1f77b4", "Coarse, 6,491 cells"),
         ("medium", "#2ca02c", "Medium, 16,666"),
         ("high", "#d62728", "Fine, 41,091")]


def make(refresh=True):
    """Draw the figure; with refresh=False, read the archive as committed.

    The stage boundary in rebuild_manuscript.py depends on this: redrawing a
    figure should not quietly recompute its summary just because the
    simulation output happens to be present.
    """
    if refresh:
        ds, source = sed.load_or_refresh()
    else:
        ds, source = xr.open_dataset(sed.NC, decode_timedelta=False), "archive"
    print("exchange recomputed from results/" if source == "results"
          else "exchange read from archive")
    t = ds["time"].values
    spin = float(ds.attrs["spinup_days_excluded"])

    with styles.USGSPlot():
        fig, axs = plt.subplots(nrows=2, figsize=(7.5, 5.0), layout="constrained",
                                sharex=True)
        axA, axB = axs
        for grid, color, label in GRIDS:
            cum = ds["cum_net_m3"].sel(grid=grid).values
            conn = ds["connected_pct"].sel(grid=grid).values
            axA.plot(t, cum, "-", color=color, lw=1.2, label=label)
            # Raw, not smoothed: the band is the tidal swing in how many junctions
            # stand above the water table, which is the mechanism behind panel A.
            axB.plot(t, conn, "-", color=color, lw=0.4, alpha=0.85)

        for ax in (axA, axB):
            ax.axvspan(0, spin, color="0.85", zorder=0, lw=0)
            ax.tick_params(labelsize=7, top=False)
        # Turned into the shaded band rather than set beside it, which keeps it off
        # the curves entirely.
        axA.annotate("spin-up", xy=(spin / 2.0, 0.5),
                     xycoords=("data", "axes fraction"), rotation=90,
                     ha="center", va="center", fontsize=6.5, color="black")

        # Gathered in the upper left instead of tagged onto the curve ends: the
        # medium and fine curves finish within 8 percent of each other, so labels
        # placed there sat on top of one another and on the lines.
        axA.annotate("net infiltration, liters per day per\nmillimeter of diameter "
                     "per kilometer",
                     xy=(0.03, 0.95), xycoords="axes fraction", va="top",
                     fontsize=6.5, color="0.35")
        for i, (grid, color, label) in enumerate(GRIDS):
            r = float(ds["rate_L_d_mm_km"].sel(grid=grid))
            axA.annotate(f"{label.split(',')[0]}  {r:.1f}",
                         xy=(0.03, 0.80 - 0.085 * i), xycoords="axes fraction",
                         va="top", fontsize=6.5, color=color)

        styles.heading(ax=axA, letter="A", fontsize=7.5,
                       heading="Cumulative net exchange into the sewer, "
                               "in cubic meters")
        styles.heading(ax=axB, letter="B", fontsize=7.5,
                       heading="Junctions connected to the water table, in percent")
        styles.xlabel(ax=axB, label="Time, in days")

        handles, labels = axA.get_legend_handles_labels()
        leg = fig.legend(handles, labels, loc="outside lower center", ncol=3,
                         frameon=False, prop={"weight": "bold", "size": 7.5})
        styles.graph_legend_title(leg, fontsize=7.5)
        fig.savefig(OUT)
    print("wrote", OUT)
    df = ds[["cells", "rate_L_d_mm_km", "connected_mean_pct"]].to_dataframe()
    print(df.to_string())


if __name__ == "__main__":
    # --no-refresh was accepted by rebuild_manuscript.py and silently ignored here,
    # so redrawing this figure always recomputed its archive from results/.
    make(refresh="--no-refresh" not in sys.argv)
