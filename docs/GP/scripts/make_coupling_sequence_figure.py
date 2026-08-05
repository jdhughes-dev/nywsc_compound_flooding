"""Schematic of the coupling sequence over two coupling intervals.

Bar width is the model time step each simulator integrates, so the time-step
hierarchy is visible directly: one MODFLOW 6 bar spans the whole coupling
interval, while SWMM and D-Flow FM tile that same span with shorter bars, one per
user time step. The second and third of those are drawn faded and without arrows,
so the repeat reads as "and so on" rather than as three distinct exchanges.

Lanes are ordered by execution within a step -- SWMM, then D-Flow FM, then
MODFLOW 6 -- so the figure answers "which model runs first" directly rather than
implying a physical stacking.

A gutter between coupling intervals carries the exchange arrows. It occupies no
model time; without it the arrows collide with the following interval's bars.

Three user time steps per interval is not a simplification at the finest coupling
interval simulated -- 15-minute coupling on a 300 s user time step is exactly
three. The caption gives 288 as the ratio at daily coupling.
"""
import pathlib as pl

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch, Rectangle
import flopy.plot.styles as styles

# The flopy style supplies pdf.fonttype 42, savefig.dpi 300 and
# savefig.transparent True, so none of those is set here and savefig takes no dpi
# argument. It does NOT set ps.fonttype, so EPS output would still carry Type 3
# fonts, which publishers reject. Set it so the figure is safe in either format.
mpl.rcParams["ps.fonttype"] = 42

OUT = pl.Path(__file__).resolve().parent.parent / "figures" / "coupling_sequence.pdf"

N_SUB, N_COUP = 3, 2
# The gutter must hold three labelled arrows side by side. At 1.15 the labels
# overlapped one another; the two that share the lower half also need horizontal
# separation, so it is wider than the arrows alone would require.
W_SUB, W_GUT = 1.0, 1.95
W_INT = N_SUB * W_SUB
PAD = 0.035                 # gap between abutting bars, so edges stay legible
FADE = 0.42                 # alpha for the repeated user time steps

LANES = [("SWMM", 2.0, "#2ca02c"),
         ("D-Flow FM", 1.0, "#1f77b4"),
         ("MODFLOW 6", 0.0, "#d62728")]
LANE_Y = {n: y for n, y, _ in LANES}
LANE_C = {n: c for n, _, c in LANES}
H = 0.24


def bar(ax, lane, x0, x1, alpha=1.0):
    y = LANE_Y[lane]
    ax.add_patch(Rectangle((x0, y - H), x1 - x0, 2 * H, facecolor=LANE_C[lane],
                           edgecolor="none", alpha=alpha, zorder=3))


def arrow(ax, x, a, b, color, label=None, ly=None):
    """ly places the label at an explicit height, so arrows sharing the same
    vertical span do not stack their labels on top of one another."""
    ya, yb = LANE_Y[a], LANE_Y[b]
    y0 = ya - H if ya > yb else ya + H
    y1 = yb + H if ya > yb else yb - H
    ax.add_patch(FancyArrowPatch((x, y0), (x, y1), arrowstyle="-|>",
                                 mutation_scale=8, linewidth=1.1, color=color,
                                 shrinkA=0, shrinkB=0, zorder=5))
    if label:
        ax.text(x + 0.07, (y0 + y1) / 2.0 if ly is None else ly, label,
                fontsize=7.5, ha="left", va="center", color=color, zorder=6)


with styles.USGSPlot():
    fig, ax = plt.subplots(figsize=(7.5, 3.6), layout="constrained")
    # The USGS style puts ticks on all four sides; the top ones are noise here,
    # since only the bottom axis carries model time.
    ax.tick_params(top=False, which="both")

    starts = [k * (W_INT + W_GUT) for k in range(N_COUP)]
    X_END = starts[-1] + W_INT + W_GUT

    for k, x0 in enumerate(starts):
        xe = x0 + W_INT                       # end of the integrated interval
        if k % 2 == 0:
            ax.add_patch(Rectangle((x0, -0.62), W_INT + W_GUT, 3.05 + 0.62,
                                   facecolor="0.95", edgecolor="none", zorder=0))

        # MODFLOW 6 integrates the whole coupling interval in one step
        bar(ax, "MODFLOW 6", x0 + PAD, xe - PAD)

        # SWMM and D-Flow FM tile the same span, one bar per user time step
        for s in range(N_SUB):
            a, b = x0 + s * W_SUB + PAD, x0 + (s + 1) * W_SUB - PAD
            al = 1.0 if s == 0 else FADE
            bar(ax, "SWMM", a, b, al)
            bar(ax, "D-Flow FM", a, b, al)
            if s == 0:
                arrow(ax, (a + b) / 2.0, "SWMM", "D-Flow FM", LANE_C["SWMM"],
                      r"$\bar{q}_s$" if k == 0 else None)

        # exchange gutter: no model time, arrows only
        ax.add_patch(Rectangle((xe, -0.42), W_GUT, 3.0, facecolor="none",
                               edgecolor="0.6", linewidth=0.7,
                               linestyle=(0, (3, 2)), zorder=1))
        ax.text(xe + W_GUT / 2.0, -0.50, "exchange", ha="center", va="top",
                fontsize=7, color="0.35", style="italic")
        # s1,hs and q^ext both span the lower half, so they are separated
        # horizontally; Q_j spans the full height and its label sits in the upper
        # half, clear of the other two.
        arrow(ax, xe + 0.22, "D-Flow FM", "MODFLOW 6", LANE_C["D-Flow FM"],
              r"$s_1,\,h_s$" if k == 0 else None, ly=0.50)
        arrow(ax, xe + 1.02, "MODFLOW 6", "D-Flow FM", LANE_C["MODFLOW 6"],
              r"$q^{\mathrm{ext}}$" if k == 0 else None, ly=0.50)
        arrow(ax, xe + 1.62, "MODFLOW 6", "SWMM", LANE_C["MODFLOW 6"],
              r"$Q_j$" if k == 0 else None, ly=1.55)

        # coupling interval span
        ax.annotate("", xy=(x0 + 0.02, 2.66), xytext=(xe - 0.02, 2.66),
                    arrowprops=dict(arrowstyle="<->", color="0.45", lw=0.8))
        ax.text((x0 + xe) / 2.0, 2.79, r"coupling interval $\Delta t_c$",
                ha="center", va="bottom", fontsize=7.5, color="0.3")

    # one user time step, called out on the first bar
    ax.annotate("", xy=(starts[0] + 0.02, 2.30), xytext=(starts[0] + W_SUB - 0.02, 2.30),
                arrowprops=dict(arrowstyle="<->", color="0.45", lw=0.8))
    ax.text(starts[0] + W_SUB / 2.0, 2.36, r"$\Delta t_u$", ha="center",
            va="bottom", fontsize=7.5, color="0.3")

    for name, y, c in LANES:
        ax.text(-0.22, y, name, ha="right", va="center", fontsize=8.5)

    ticks, labels, n = [], [], 0
    for x0 in starts:
        for s in range(N_SUB):
            ticks.append(x0 + s * W_SUB)
            labels.append(r"$t_0$" if n == 0 else rf"$+{n}\Delta t_u$")
            n += 1
    ticks.append(starts[-1] + W_INT)
    labels.append(rf"$+{n}\Delta t_u$")

    ax.set_xlim(-1.85, X_END + 0.10)
    ax.set_ylim(-0.95, 3.05)
    ax.set_yticks([])
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, fontsize=7)
    for side in ("left", "right", "top"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_position(("data", -0.62))

    handles = [Patch(facecolor=c, edgecolor="none",
                     label=f"{n} time step") for n, _, c in LANES]
    handles += [
        Line2D([], [], color=LANE_C["SWMM"], lw=1.4,
               label=r"$\bar{q}_s$, mean outfall discharge"),
        Line2D([], [], color=LANE_C["D-Flow FM"], lw=1.4,
               label=r"$s_1$, $h_s$, water level and depth"),
        Line2D([], [], color=LANE_C["MODFLOW 6"], lw=1.4,
               label=r"$q^{\mathrm{ext}}$, boundary flow; $Q_j$, seepage"),
    ]
    styles.graph_legend(ax=ax, handles=handles,
                        labels=[h.get_label() for h in handles],
                        loc="lower center", bbox_to_anchor=(0.5, -0.34),
                        ncol=3, frameon=False, fontsize=7)
    styles.xlabel(ax=ax, label="Model time")
    styles.heading(ax=ax, heading="Model time steps, order of execution, and "
                                  "exchanged state")

    fig.savefig(OUT)
print("wrote", OUT)
