"""Schematic of the coupling sequence over two coupling intervals.

Lanes are ordered by execution within a step -- SWMM, then D-Flow FM, then
MODFLOW 6 -- so the figure answers "which model runs first" directly rather than
implying a physical stacking.

Each coupling interval is drawn as N user-time-step columns followed by one
exchange column. The exchange column occupies no model time; it is given width so
the MODFLOW compute and its three arrows do not collide with the SWMM and D-Flow FM
boxes. It is shaded and labelled to make that clear.

N is drawn as three for legibility. In the simulations it is 96 at 8-hour coupling
with a 300 s user time step; the caption says so.
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
W_STEP, W_EXCH = 1.0, 1.7

LANES = [("SWMM", 2.0, "#2ca02c"),
         ("D-Flow FM", 1.0, "#1f77b4"),
         ("MODFLOW 6", 0.0, "#d62728")]
LANE_Y = {n: y for n, y, _ in LANES}
LANE_C = {n: c for n, _, c in LANES}
H = 0.22

cols, x = [], 0.0
for k in range(N_COUP):
    for s in range(N_SUB):
        cols.append(("step", x, x + W_STEP, k, s))
        x += W_STEP
    cols.append(("exch", x, x + W_EXCH, k, None))
    x += W_EXCH
X_END = x


def box(ax, lane, x0, x1):
    y = LANE_Y[lane]
    ax.add_patch(Rectangle((x0, y - H), x1 - x0, 2 * H, facecolor=LANE_C[lane],
                           edgecolor="white", linewidth=0.8, zorder=3))


def arrow(ax, x, a, b, color, label=None):
    ya, yb = LANE_Y[a], LANE_Y[b]
    y0 = ya - H if ya > yb else ya + H
    y1 = yb + H if ya > yb else yb - H
    ax.add_patch(FancyArrowPatch((x, y0), (x, y1), arrowstyle="-|>",
                                 mutation_scale=8, linewidth=1.1, color=color,
                                 shrinkA=0, shrinkB=0, zorder=5))
    if label:
        ax.text(x + 0.06, (y0 + y1) / 2.0, label, fontsize=7.5, ha="left",
                va="center", color=color, zorder=6)


with styles.USGSPlot():
    fig, ax = plt.subplots(figsize=(7.5, 3.6), layout="constrained")

    for k in range(N_COUP):
        xs = [c for c in cols if c[3] == k]
        x0, x1 = xs[0][1], xs[-1][2]
        if k % 2 == 0:
            # A Rectangle rather than axvspan: axvspan fills the whole y-range,
            # which here runs below the relocated bottom spine and bleeds the
            # shading down past the tick labels.
            ax.add_patch(Rectangle((x0, -0.62), x1 - x0, 3.05 - (-0.62),
                                   facecolor="0.95", edgecolor="none", zorder=0))
        ax.annotate("", xy=(x0 + 0.02, 2.66), xytext=(x1 - 0.02, 2.66),
                    arrowprops=dict(arrowstyle="<->", color="0.45", lw=0.8))
        ax.text((x0 + x1) / 2.0, 2.80, r"coupling interval $\Delta t_c$",
                ha="center", va="bottom", fontsize=7.5, color="0.3")

    for kind, x0, x1, k, s in cols:
        if kind == "step":
            box(ax, "SWMM", x0 + 0.10, x0 + 0.45)
            box(ax, "D-Flow FM", x0 + 0.55, x0 + 0.90)
            arrow(ax, x0 + 0.50, "SWMM", "D-Flow FM", LANE_C["SWMM"],
                  r"$\bar{q}_s$" if (k, s) == (0, 0) else None)
        else:
            ax.add_patch(Rectangle((x0, -0.42), x1 - x0, 3.0, facecolor="none",
                                   edgecolor="0.6", linewidth=0.7,
                                   linestyle=(0, (3, 2)), zorder=1))
            ax.text((x0 + x1) / 2.0, -0.50, "exchange", ha="center", va="top",
                    fontsize=7, color="0.35", style="italic")
            xm = (x0 + x1) / 2.0
            arrow(ax, x0 + 0.26, "D-Flow FM", "MODFLOW 6", LANE_C["D-Flow FM"],
                  r"$s_1,\,h_s$" if k == 0 else None)
            box(ax, "MODFLOW 6", xm - 0.20, xm + 0.20)
            arrow(ax, x1 - 0.66, "MODFLOW 6", "D-Flow FM", LANE_C["MODFLOW 6"],
                  r"$q^{\mathrm{ext}}$" if k == 0 else None)
            arrow(ax, x1 - 0.16, "MODFLOW 6", "SWMM", LANE_C["MODFLOW 6"],
                  r"$Q_j$" if k == 0 else None)

    for name, y, c in LANES:
        ax.text(-0.20, y, name, ha="right", va="center", fontsize=8.5)

    ticks, labels, n = [], [], 0
    for c in cols:
        if c[0] == "step":
            ticks.append(c[1])
            labels.append(r"$t_0$" if n == 0 else rf"$+{n}\Delta t_u$")
            n += 1
    ticks.append(X_END)
    labels.append(rf"$+{n}\Delta t_u$")

    ax.set_xlim(-1.75, X_END + 0.15)
    ax.set_ylim(-0.95, 3.05)
    ax.set_yticks([])
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, fontsize=7)
    for side in ("left", "right", "top"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_position(("data", -0.62))

    handles = [Patch(facecolor=c, edgecolor="white", label=f"{n} advances")
               for n, _, c in LANES]
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
    styles.heading(ax=ax, heading="Order of execution and exchanged state "
                                  "within two coupling intervals")

    fig.savefig(OUT)
print("wrote", OUT)
