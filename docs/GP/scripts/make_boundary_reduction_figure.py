"""How the two boundary reductions represent a tidal cell of a given wetness.

The stage is the sum of the three semidiurnal constituents fitted to the NOAA CO-OPS
record at Kings Point, and bed elevations are placed at quantiles of it so each row
is a cell wet for a stated fraction of the time.
"""
import pathlib as pl

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import flopy.plot.styles as styles

mpl.rcParams["ps.fonttype"] = 42

OUT = pl.Path(__file__).resolve().parent.parent / "figures" / "boundary_reduction.pdf"

# Least squares fit to NOAA 8516945 (Kings Point), NAVD 1988, 6-minute verified,
# January-March 2010. K1 and O1 came out at 0.083 and 0.060 m and are dropped; they
# add lines to read without changing the argument.
MEAN_LEVEL = 0.032
CONSTITUENTS = [("M2", 12.4206, 1.110), ("S2", 12.0000, 0.225), ("N2", 12.6583, 0.287)]

DT_U = 300.0 / 3600.0          # D-Flow FM user time step, in hours
DAYS = 6.0
INTERVALS = [2.0, 8.0, 24.0]   # hours; 2 h is below the M2 Nyquist limit, 8 and 24 above
# The fully wet row is the familiar aliasing-against-damping trade, since the
# conductance never changes there. The partly wet rows carry the failure that is easy
# to miss: sampled instantaneously, an intertidal cell reports either fully connected
# or entirely disconnected depending on where the sampling instant falls in the tide,
# so the boundary switches on and off at the beat between interval and tide while
# nothing physical changes.
WET_FRACTIONS = [1.00, 0.75, 0.50, 0.25]
NYQUIST_H = 12.4206 / 2

C_STAGE, C_INST, C_MEAN = "0.55", "#d62728", "#1f77b4"


def stage(t_h):
    s = np.full_like(t_h, MEAN_LEVEL)
    for _, period, amp in CONSTITUENTS:
        s += amp * np.cos(2.0 * np.pi * t_h / period)
    return s


def reduce_interval(t, s, w, dt_c):
    """Both reductions, evaluated per coupling interval.

    Returns interval start times and, for each method, the boundary head and the
    conductance multiplier. A head of NaN means the conductance is zero, i.e. the
    boundary is switched off for that interval entirely.
    """
    n = int(round(dt_c / DT_U))
    nfull = (len(t) // n) * n
    tt = t[:nfull].reshape(-1, n)
    ss = s[:nfull].reshape(-1, n)
    ww = w[:nfull].reshape(-1, n).astype(float)

    c_i = ww[:, -1]                                   # wet/dry at the sampling instant
    h_i = np.where(c_i > 0, ss[:, -1], np.nan)

    c_m = ww.mean(axis=1)                             # wetted fraction
    with np.errstate(invalid="ignore", divide="ignore"):
        h_m = np.where(c_m > 0, (ww * ss).sum(axis=1) / np.maximum(ww.sum(axis=1), 1e-12),
                       np.nan)
    return tt[:, 0], h_i, c_i, h_m, c_m


t = np.arange(0.0, DAYS * 24.0 + DT_U, DT_U)
s = stage(t)

with styles.USGSPlot():
    # Explicit spacing rather than constrained layout: each cell is a head panel
    # with its own conductance strip, and constrained layout spaced the strip as far
    # from its own panel as from the next row's, so it read as belonging to neither.
    fig = plt.figure(figsize=(7.5, 8.6))
    outer = fig.add_gridspec(len(WET_FRACTIONS), len(INTERVALS), hspace=0.62,
                             wspace=0.20, left=0.095, right=0.985, top=0.955,
                             bottom=0.085)

    for i, frac in enumerate(WET_FRACTIONS):
        # Bed elevation placed so the cell is wet exactly `frac` of the time. For the
        # fully wet row it goes below the lowest stage rather than at the minimum, so
        # the cell never grazes dry.
        z_b = s.min() - 0.15 if frac >= 1.0 else float(np.quantile(s, 1.0 - frac))
        w = s > z_b

        for j, dt_c in enumerate(INTERVALS):
            inner = outer[i, j].subgridspec(2, 1, height_ratios=[3.0, 1.0], hspace=0.06)
            axh = fig.add_subplot(inner[0])
            axc = fig.add_subplot(inner[1], sharex=axh)

            t0, h_i, c_i, h_m, c_m = reduce_interval(t, s, w, dt_c)

            axh.plot(t / 24.0, s, color=C_STAGE, lw=0.6, zorder=2)
            axh.axhline(z_b, color="0.3", lw=0.7, linestyle=(0, (3, 2)), zorder=1)
            axh.step(t0 / 24.0, h_i, where="post", color=C_INST, lw=1.1, zorder=4)
            axh.step(t0 / 24.0, h_m, where="post", color=C_MEAN, lw=1.1, zorder=3)
            # Intervals the instantaneous sample calls dry: no boundary at all.
            off = t0[c_i == 0] / 24.0
            if off.size:
                axh.plot(off, np.full_like(off, s.min() - 0.42), linestyle="none",
                         marker="x", ms=2.6, mew=0.8, color=C_INST, zorder=5)
            axh.set_ylim(s.min() - 0.62, s.max() + 0.25)
            axh.tick_params(labelsize=6, top=False, labelbottom=False)

            axc.step(t0 / 24.0, c_i, where="post", color=C_INST, lw=1.1)
            axc.step(t0 / 24.0, c_m, where="post", color=C_MEAN, lw=1.1)
            axc.set_ylim(-0.12, 1.18)
            axc.set_yticks([0, 1])
            axc.tick_params(labelsize=6, top=False)
            axc.set_xlim(0, DAYS)

            if i == 0:
                styles.heading(ax=axh, heading=f"{dt_c:.0f} h coupling"
                               + ("" if dt_c > NYQUIST_H else "  (below Nyquist)"),
                               fontsize=7.5)
            if j == 0:
                lab = "always wet" if frac >= 1.0 else f"wet {frac:.0%} of the time"
                axh.set_ylabel(f"{lab}\nstage, m", fontsize=6.5)
                axc.set_ylabel("cond.\nmult.", fontsize=6.5)
            if i == len(WET_FRACTIONS) - 1:
                axc.set_xlabel("Time, in days", fontsize=6.5)

    handles = [plt.Line2D([], [], color=C_STAGE, lw=1.2, label="D-Flow FM stage"),
               plt.Line2D([], [], color=C_INST, lw=1.4,
                          label="instantaneous (end of interval)"),
               plt.Line2D([], [], color=C_MEAN, lw=1.4,
                          label="wetted-fraction time average"),
               plt.Line2D([], [], color=C_INST, lw=0, marker="x", ms=4, mew=0.9,
                          label="boundary switched off")]
    fig.legend(handles=handles, labels=[h.get_label() for h in handles],
               loc="lower center", bbox_to_anchor=(0.5, 0.012), ncol=4,
               frameon=False, fontsize=7)
    fig.savefig(OUT, bbox_inches="tight")
print("wrote", OUT)
