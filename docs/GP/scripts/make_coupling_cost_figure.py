"""What the coupling interval costs in run time, by grid.

Drawn from ../../data/GP/coupling_cost.nc, which coupling_cost_data.py recomputes
when the run logs are present and reads as-is when they are not.

Panel A reports run time as a multiple of each series' own daily-coupling run, so
that the baseline falls at 1.0 where a reader expects a baseline to fall, and the
coarse grid reading 2.1 says directly that coupling every 15 minutes doubles it.

Panel B uses the daily-coupling run of each series as its own baseline rather than a
fitted intercept, so the collapse it shows is a property of the measurements and not
of the line drawn through them.
"""
import pathlib as pl
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
import flopy.plot.styles as styles

sys.path.insert(0, str(pl.Path(__file__).resolve().parent))
import coupling_cost_data as ccd          # noqa: E402

mpl.rcParams["ps.fonttype"] = 42

OUT = pl.Path(__file__).resolve().parent.parent / "figures" / "coupling_cost.pdf"
NYQUIST_H = 12.4206 / 2
# Ordered coarse to fine, so the legend reads the way the scenario table does. The
# cell count is carried in the label because it is the only thing that differs
# between the three sets of simulations -- the MODFLOW and SWMM models are the same
# in all of them -- and a reader should not have to go back to the table for it.
GRIDS = [("coarse", "#1f77b4", "Coarse, 6,491 cells"),
         ("medium", "#2ca02c", "Medium, 16,666"),
         ("high", "#d62728", "Fine, 41,091")]
# Filled is the reduction adopted in this work; open is the incumbent. They cost the
# same, which is worth showing rather than asserting.
REDUCTIONS = [("meanbnd", "o", True, "time-averaged"),
              ("instbnd", "s", False, "instantaneous")]


def series(df, grid, reduction):
    sub = df[(df["grid"] == grid) & (df["reduction"] == reduction)].dropna(
        subset=["minutes"]).sort_values("steps")
    return sub if len(sub) >= 4 else None


def make(refresh=True):
    """Draw the figure; with refresh=False, read the archive as committed.

    The stage boundary in rebuild_manuscript.py depends on this: redrawing a
    figure should not quietly recompute its summary just because the
    simulation output happens to be present.
    """
    if refresh:
        ds, source = ccd.load_or_refresh()
    else:
        ds, source = xr.open_dataset(ccd.NC, decode_timedelta=False), 'archive'
    print("timings recomputed from logs/" if source == "logs"
          else "timings read from archive")
    df = ds.to_dataframe().reset_index().dropna(subset=["minutes"])
    fit = ccd.fits(df)
    print(fit.to_string(index=False))

    with styles.USGSPlot():
        fig, axs = plt.subplots(ncols=2, figsize=(7.5, 3.2), layout="constrained")
        axA, axB = axs
        dx, dy = [], []
        baselines = {}
        for grid, color, label in GRIDS:
            for reduction, marker, filled, _ in REDUCTIONS:
                s = series(df, grid, reduction)
                if s is None:
                    continue
                base = s.iloc[0]                      # the daily-coupling run
                baselines.setdefault(grid, []).append(float(base["minutes"]))
                face = color if filled else "none"
                axA.plot(s["hours"], s["minutes"] / base["minutes"],
                         marker=marker, color=color, mfc=face, lw=1.1, ms=4,
                         label=label if reduction == "meanbnd" else None)
                extra_steps = s["steps"] - base["steps"]
                extra_min = s["minutes"] - base["minutes"]
                axB.plot(extra_steps, extra_min, marker=marker, color=color,
                         mfc=face, lw=0, ms=4)
                dx.extend(extra_steps[1:]); dy.extend(extra_min[1:])

        # Pooled marginal cost through the origin: by construction the baseline run
        # contributes no extra steps and no extra time.
        dx, dy = np.array(dx, float), np.array(dy, float)
        slope = float(dx @ dy / (dx @ dx))
        xs = np.array([0.0, dx.max()])
        axB.plot(xs, slope * xs, "-", color="0.35", lw=0.9, zorder=0)
        axB.annotate(f"{slope * 60:.2f} s per coupling step", xy=(0.05, 0.90),
                     xycoords="axes fraction", fontsize=7, color="0.35")

        axA.set_xscale("log")
        # A multiple puts the baseline at 1.0 instead of at the axis floor, where it
        # would otherwise have to be inferred from the daily-coupling point.
        axA.axhline(1.0, color="0.35", lw=0.7, linestyle=(0, (3, 2)), zorder=0)
        axA.axvline(NYQUIST_H, color="0.35", lw=0.9, linestyle=(0, (3, 2)), zorder=0)
        ticks = sorted(df["hours"].unique())
        axA.set_xticks(ticks)
        axA.set_xticklabels([f"{v * 60:.0f} min" if v < 1 else f"{v:.0f} h" if v < 24
                             else f"{v / 24:.0f} d" for v in ticks], fontsize=7)
        axA.tick_params(labelsize=7, top=False)
        axA.annotate(r"$M_2$ Nyquist", xy=(NYQUIST_H, 0.96),
                     xycoords=("data", "axes fraction"), xytext=(3, 0),
                     textcoords="offset points", fontsize=6.5, color="0.35",
                     va="top", ha="left")
        # The panel is a ratio, so the absolute cost the ratio is taken against is
        # otherwise invisible -- and that cost is the whole reason the three curves
        # separate.
        # Upper right: every curve descends to one at daily coupling, so that
        # corner is the only part of the panel the data never occupies.
        axA.annotate("daily-coupling run time", xy=(0.46, 0.84),
                     xycoords="axes fraction", fontsize=6.5, color="0.35")
        for i, (grid, color, _) in enumerate(GRIDS):
            if grid in baselines:
                mean_min = sum(baselines[grid]) / len(baselines[grid])
                axA.annotate(f"{mean_min:.0f} min", xy=(0.46, 0.76 - 0.075 * i),
                             xycoords="axes fraction", fontsize=6.5, color=color)
        styles.xlabel(ax=axA, label="Coupling interval")
        styles.heading(ax=axA, letter="A", fontsize=7.5,
                       heading="Run time as a multiple of the daily-coupling run")

        axB.tick_params(labelsize=7, top=False)
        styles.xlabel(ax=axB, label="Additional coupling steps")
        styles.heading(ax=axB, letter="B", fontsize=7.5,
                       heading="Additional run time, in minutes")

        handles, labels = axA.get_legend_handles_labels()
        marker_keys = [plt.Line2D([], [], color="0.35", marker=m, mfc="0.35" if f
                                  else "none", lw=0, ms=4, label=lab)
                       for _, m, f, lab in REDUCTIONS]
        leg = fig.legend(handles + marker_keys,
                         labels + [k.get_label() for k in marker_keys],
                         loc="outside lower center", ncol=5, frameon=False,
                         prop={"weight": "bold", "size": 7.5})
        styles.graph_legend_title(leg, fontsize=7.5)
        fig.savefig(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    make(refresh="--no-refresh" not in sys.argv)
