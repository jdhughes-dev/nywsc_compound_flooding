"""Coastal exchange against coupling interval, on the medium grid.

Drawn from ../../data/GP/coastal_exchange.nc, which coastal_exchange_data.py
recomputes when the simulation output is present and reads as-is when it is not.

Panel A shows the whole run, because the point it makes is that the cumulative
curves end up on top of one another. Panel B shows a ten-day window rather than
the whole simulation: at 15-minute coupling the rate has 8,544 samples over 89
days, which drawn in full is a solid band, and a window is the only way the tidal
signal, and the collapse of its amplitude as the interval lengthens, are visible
at all. The volume is the upper panel because the text establishes that it
survives the interval before it shows that the rate does not.
"""
import pathlib as pl
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
import flopy.plot.styles as styles

sys.path.insert(0, str(pl.Path(__file__).resolve().parent))
import coastal_exchange_data as ced          # noqa: E402

mpl.rcParams["ps.fonttype"] = 42

OUT = pl.Path(__file__).resolve().parent.parent / "figures" / "coastal_exchange.pdf"
# Mid-run, after spin-up, and clear of the storm responses later in the record, so
# what panel B shows is the tidal signal and not an event.
WINDOW = (40.0, 50.0)
# Coarsest to finest, so the legend runs the way the interval axis does elsewhere.
ORDER = ["01.00D", "08.00H", "04.00H", "02.00H", "01.00H", "30.00M", "15.00M"]
LABEL = {"15.00M": "15 min", "30.00M": "30 min", "01.00H": "1 h", "02.00H": "2 h",
         "04.00H": "4 h", "08.00H": "8 h", "01.00D": "1 d"}


def make(refresh=True):
    if refresh:
        ds, source = ced.load_or_refresh()
    else:
        ds, source = xr.open_dataset(ced.NC, decode_timedelta=False), "archive"
    print("coastal exchange recomputed from results/" if source == "results"
          else "coastal exchange read from archive")

    iv = ds["interval"].values
    t, rate, cum = ds["time"].values, ds["rate"].values, ds["cum"].values
    cmap = plt.get_cmap("viridis")
    colors = {k: cmap(i / (len(ORDER) - 1)) for i, k in enumerate(ORDER)}

    with styles.USGSPlot():
        fig, (axA, axB) = plt.subplots(nrows=2, figsize=(7.5, 4.6),
                                       layout="constrained")
        for key in ORDER:
            m = iv == key
            if not m.any():
                continue
            w = m & (t >= WINDOW[0]) & (t <= WINDOW[1])
            axA.plot(t[m], cum[m], "-", color=colors[key], lw=1.0,
                     label=LABEL[key])
            axB.plot(t[w], rate[w], "-", color=colors[key], lw=0.9)

        axB.axhline(0.0, color="0.35", lw=0.7, linestyle=(0, (3, 2)), zorder=0)
        axB.set_xlim(*WINDOW)
        for ax in (axA, axB):
            ax.tick_params(labelsize=7, top=False)
        styles.xlabel(ax=axA, label="Time, in days")
        styles.xlabel(ax=axB, label="Time, in days")
        styles.heading(ax=axA, letter="A", fontsize=7.5,
                       heading="Cumulative coastal exchange, in millimeters")
        styles.heading(ax=axB, letter="B", fontsize=7.5,
                       heading="Coastal exchange rate, in millimeters per day")

        # The two numbers the figure exists to contrast, stated where they are read.
        rms = {str(k): float(v) for k, v in
               zip(ds["iv"].values, ds["rms_rate"].values)}
        cm = {str(k): float(v) for k, v in
              zip(ds["iv"].values, ds["cum_mm"].values)}
        span = 100.0 * (max(cm.values()) - min(cm.values())) / abs(cm["15.00M"])
        axA.annotate(f"cumulative spans {span:.1f} percent across the same intervals",
                     xy=(0.02, 0.08), xycoords="axes fraction", fontsize=6.5,
                     color="0.35")
        # Top right. The window opens on the largest flood of the ten days, so the
        # left of the panel is occupied at both the top and the bottom.
        axB.annotate(f"root-mean-square rate falls from {rms['15.00M']:.1f} to "
                     f"{rms['01.00D']:.1f} mm/d", xy=(0.98, 0.95),
                     xycoords="axes fraction", va="top", ha="right",
                     fontsize=6.5, color="0.35")

        handles, labels = axA.get_legend_handles_labels()
        leg = fig.legend(handles, labels, loc="outside lower center", ncol=7,
                         frameon=False, prop={"weight": "bold", "size": 7.5})
        styles.graph_legend_title(leg, fontsize=7.5)
        fig.savefig(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    make(refresh="--no-refresh" not in sys.argv)
