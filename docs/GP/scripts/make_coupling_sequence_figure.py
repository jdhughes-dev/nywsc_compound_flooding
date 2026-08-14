"""Schematic of the coupling sequence over two coupling intervals.

Bar width is the model time step each simulator integrates, and lanes are ordered by
execution rather than by physical position. Every connector enters the start of the
step that consumes it, and leaves the producing step where the value is formed: its
end for an instantaneous value, its middle or its whole span for a mean.
"""
import pathlib as pl

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch, Rectangle
from matplotlib.path import Path
import flopy.plot.styles as styles

# The flopy style supplies pdf.fonttype 42, savefig.dpi 300 and
# savefig.transparent True, so none of those is set here and savefig takes no dpi
# argument. It does NOT set ps.fonttype, so EPS output would still carry Type 3
# fonts, which publishers reject. Set it so the figure is safe in either format.
mpl.rcParams["ps.fonttype"] = 42

OUT = pl.Path(__file__).resolve().parent.parent / "figures" / "coupling_sequence.pdf"

# Three user steps per interval is exact at the finest coupling simulated: 15-minute
# coupling on a 300 s user step. At daily coupling the ratio is 288.
N_SUB, N_COUP = 3, 2
# Once the connectors became orthogonal they turn in the horizontal channels rather
# than in the gutter, so the gutter no longer has to be wide enough to hold three
# arrows side by side. What it still has to do is keep the two MODFLOW 6 blocks
# apart -- abutting them would read as one continuous step across both intervals,
# which is precisely the thing the figure exists to deny.
W_SUB, W_GUT = 1.0, 1.30
W_INT = N_SUB * W_SUB
PAD = 0.035                 # gap between abutting bars, so edges stay legible
FADE = 0.42                 # alpha for the repeated user time steps
GHOST = 0.22                # alpha for the stub of the interval after the last
W_STUB = 0.55

LANES = [("SWMM", 2.0, "#2ca02c"),
         ("D-Flow FM", 1.0, "#1f77b4"),
         ("MODFLOW 6", 0.0, "#d62728")]
LANE_Y = {n: y for n, y, _ in LANES}
LANE_C = {n: c for n, _, c in LANES}
H = 0.24

SW_B = LANE_Y["SWMM"] - H              # 1.76, bottom edge of the SWMM bars
DF_T = LANE_Y["D-Flow FM"] + H         # 1.24
DF_B = LANE_Y["D-Flow FM"] - H         # 0.76
MF_T = LANE_Y["MODFLOW 6"] + H         # 0.24

# Routing channels, chosen so no two runs are ever collinear -- every horizontal has
# its span to itself at that height, and verticals sharing an x have disjoint
# extents. Connectors do cross, which is legible; two lines lying on top of each
# other are not, because the upper one simply hides the other.
#
# Ordering in the band between MODFLOW 6 and D-Flow FM is forced rather than chosen.
# Three connectors land on the same edge at the start of an interval: the mean water
# level and the seepage both come down to the MODFLOW 6 bar, and Q^ext goes up to the
# D-Flow FM bar. Level < seepage < Q^ext is the only order in which the seepage shows
# above the water level and Q^ext stays clear of both.
Y_QS = 1.50
# Spacing is set by what each landing needs, working outward from the MODFLOW 6 bar
# at 0.24 and the D-Flow FM bar at 0.76: s1,hs and q^ext each need enough run below
# their head to read as a line rather than as a bare arrowhead, and the seepage has
# to clear s1,hs by enough to show above it.
Y_S1, Y_QJ_DN, Y_QE = 0.42, 0.52, 0.60
Y_QJ_UP = 1.58                    # Q_j delivery to SWMM
Y_QJ_IN = 1.00                    # Q_j collector, on the label's center line
# q^ext leaves through the RIGHT EDGE of the MODFLOW 6 bar rather than its top
# corner. s1,hs now runs below q^ext, so both would need a vertical on that corner
# and would lie on top of each other between the two channels. Leaving through the
# edge is no less true to "the end of the step" and keeps the corner for s1,hs.
Y_QE_EXIT = LANE_Y["MODFLOW 6"]


def bar(ax, lane, x0, x1, alpha=1.0):
    y = LANE_Y[lane]
    ax.add_patch(Rectangle((x0, y - H), x1 - x0, 2 * H, facecolor=LANE_C[lane],
                           edgecolor="none", alpha=alpha, zorder=3))


def poly(ax, pts, color, label=None, lxy=None, ha="left", both=False, lw=1.1,
         alpha=1.0, head=True, zorder=5):
    """Orthogonal connector through the given vertices, head on the last segment.

    FancyArrowPatch takes a Path directly, which keeps the whole connector a
    single artist -- drawing it as separate segments would leave visible gaps at
    the corners at this line width. head=False gives a bare run, for a path that
    only gathers state rather than delivering it."""
    ax.add_patch(FancyArrowPatch(path=Path(pts),
                                 arrowstyle="-" if not head
                                 else ("<|-|>" if both else "-|>"),
                                 mutation_scale=8, linewidth=lw, color=color,
                                 shrinkA=0, shrinkB=0, zorder=zorder, alpha=alpha,
                                 joinstyle="miter", capstyle="butt"))
    if label and lxy:
        ax.text(lxy[0], lxy[1], label, fontsize=7.5, ha=ha, va="center",
                color=color, zorder=zorder + 1, alpha=alpha)


with styles.USGSPlot():
    fig, ax = plt.subplots(figsize=(7.5, 3.6), layout="constrained")
    # The USGS style puts ticks on all four sides; the top ones are noise here,
    # since only the bottom axis carries model time.
    ax.tick_params(top=False, which="both")

    starts = [k * (W_INT + W_GUT) for k in range(N_COUP)]
    X_END = starts[-1] + W_INT + W_GUT

    for k, x0 in enumerate(starts):
        xe = x0 + W_INT                       # end of the integrated interval
        xn = xe + W_GUT                       # start of the next interval
        # Gutter verticals, all at distinct x so nothing runs inside anything else:
        # the Q_j collector, the q^ext riser, and the Q_j junction.
        xi, xr, xc = xe + 0.22, xe + 0.46, xe + 0.70
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
            # Leaves the MIDDLE of the SWMM bar, not its end: the value handed over
            # is the mean across the step, formed from the cumulative outfall volume,
            # so the step's midpoint is where it belongs. It enters the start of the
            # D-Flow FM bar covering that same interval. Drawn on every step and
            # faded with its own bars, because this handoff happens every user time
            # step; only the leading one carries the label.
            xm = (a + b) / 2.0
            poly(ax, [(xm, SW_B), (xm, Y_QS), (a, Y_QS), (a, DF_T)],
                 LANE_C["SWMM"], r"$\bar{Q}_s$" if s == 0 else None,
                 lxy=((a + xm) / 2.0, Y_QS + 0.11), ha="center", alpha=al)

        # The gutter is a break in the time axis, so it is marked as one: a light
        # rule on each edge rather than a box. A box around a gutter this narrow
        # would crowd the connectors turning inside it, and would also suggest the
        # gutter contains something, when it contains no model time at all.
        for xv in (xe, xn):
            ax.plot([xv, xv], [-0.30, 2.44], color="0.6", linewidth=0.7,
                    linestyle=(0, (3, 2)), zorder=1)
        ax.text(xe + W_GUT / 2.0, -0.36, "exchange", ha="center", va="top",
                fontsize=7, color="0.35", style="italic")

        # Every endpoint lands on a real bar edge rather than on the nominal
        # interval bound, which sits PAD outside it.
        #
        # BACKWARD across the interval: from the end of the last D-Flow FM step to
        # the start of the MODFLOW 6 step that spans it. Drawn above the seepage,
        # because both deliver to that same start and the water level is the one
        # that sets the boundary.
        # Collected from EVERY D-Flow FM step in the interval, not read at the end of
        # the last one: the boundary is a wetted-fraction time average, so a single
        # tap on the final bar would draw the superseded method.
        for s in range(N_SUB):
            xt = x0 + (s + 0.5) * W_SUB
            poly(ax, [(xt, DF_B), (xt, Y_S1)], LANE_C["D-Flow FM"], head=False,
                 lw=0.75, alpha=1.0 if s == 0 else FADE)
        poly(ax, [(x0 + (N_SUB - 0.5) * W_SUB, Y_S1), (x0 + PAD, Y_S1), (x0 + PAD, MF_T)],
             LANE_C["D-Flow FM"], r"$\bar{s}_1,\,\bar{h}_s$",
             lxy=((x0 + xe) / 2.0, Y_S1 + 0.13), ha="center", zorder=8)
        # FORWARD into the start of the next D-Flow FM step, leaving through the
        # right edge of the MODFLOW 6 bar.
        poly(ax, [(xe - PAD, Y_QE_EXIT), (xr, Y_QE_EXIT), (xr, Y_QE),
                  (xn + PAD, Y_QE), (xn + PAD, DF_B)],
             LANE_C["MODFLOW 6"], r"$Q^{\mathrm{ext}}$",
             lxy=(xc + 0.10, Y_QE + 0.13), ha="left")
        # Q_j is the seepage between the aquifer and the sewer: the groundwater head
        # against the water surface in the pipe, or against the pipe invert once the
        # water table drops below it. It is a property of neither model, so it is
        # drawn as a junction rather than as a line between them -- head and stage
        # come in, and the flux goes out to the START of the next step in both.
        # Verified against the loop: update_swmm writes the API well package and
        # generated_inflow AFTER finalize_time_step, so neither is seen until the
        # following step, and both are then held across it.
        #
        # The earlier version ran a horizontal along the bottom edge of the SWMM
        # bars, which read as underlining them rather than entering them.
        # Head and stage enter on one line, not two. Only the difference between
        # them is ever formed -- the driving head is a single number -- so two
        # separate inputs would suggest the models contribute independently when
        # between them they contribute one value.
        # Same weight as the delivery arms: this is one exchange, and a hairline in
        # against a full-weight line out made the collection look like a lesser
        # thing than the delivery. The lighter gray still separates the two roles.
        poly(ax, [(xe - PAD, SW_B), (xi, SW_B), (xi, MF_T), (xe - PAD, MF_T)],
             "0.45", head=False)
        poly(ax, [(xi, Y_QJ_IN), (xc - 0.17, Y_QJ_IN)], "0.45")
        # Delivered to the start of the next SWMM and MODFLOW 6 bars. On MODFLOW 6
        # that is the same point s1,hs lands on, and the water level is drawn over
        # the seepage there -- both really do apply from that instant, so they are
        # shown converging rather than pushed apart. The seepage keeps its own
        # arrowhead on the stub at the right, where no water level arrives.
        xd = xn + PAD
        poly(ax, [(xc, 1.14), (xc, Y_QJ_UP), (xd, Y_QJ_UP), (xd, SW_B)], "0.25")
        poly(ax, [(xc, 0.86), (xc, Y_QJ_DN), (xd, Y_QJ_DN), (xd, MF_T)], "0.25",
             r"$Q_j$", lxy=(xc, 1.00), ha="center")

        # coupling interval span
        ax.annotate("", xy=(x0 + 0.02, 2.66), xytext=(xe - 0.02, 2.66),
                    arrowprops=dict(arrowstyle="<->", color="0.45", lw=0.8))
        ax.text((x0 + xe) / 2.0, 2.79, r"coupling interval $\Delta t_c$",
                ha="center", va="bottom", fontsize=7.5, color="0.3")

    # A stub of the interval after the last one, so the forward connectors land on
    # a real time step instead of stopping in blank space.
    bar(ax, "MODFLOW 6", X_END + PAD, X_END + W_STUB, GHOST)
    bar(ax, "SWMM", X_END + PAD, X_END + W_STUB, GHOST)
    bar(ax, "D-Flow FM", X_END + PAD, X_END + W_STUB, GHOST)

    # one user time step, called out on the first bar
    ax.annotate("", xy=(starts[0] + 0.02, 2.30), xytext=(starts[0] + W_SUB - 0.02, 2.30),
                arrowprops=dict(arrowstyle="<->", color="0.45", lw=0.8))
    ax.text(starts[0] + W_SUB / 2.0, 2.36, r"$\Delta t_u$", ha="center",
            va="bottom", fontsize=7.5, color="0.3")

    for name, y, c in LANES:
        ax.text(-0.22, y, name, ha="right", va="center", fontsize=8.5)

    # Both edges of a gutter are the SAME instant -- the gutter is zero model
    # time -- so both carry the tick. Labeling only one edge left the other
    # unlabeled and, worse, was inconsistent between the two gutters: the first
    # was labeled on the right, the second on the left.
    ticks, labels, n = [], [], 0
    for x0 in starts:
        for s in range(N_SUB):
            ticks.append(x0 + s * W_SUB)
            labels.append(r"$t_0$" if n == 0 else rf"$+{n}\Delta t_u$")
            n += 1
        ticks.append(x0 + W_INT)                 # gutter left edge
        labels.append(rf"$+{n}\Delta t_u$")
    ticks.append(X_END)                          # last gutter's right edge
    labels.append(rf"$+{n}\Delta t_u$")

    ax.set_xlim(-1.85, X_END + W_STUB + 0.12)
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
               label=r"$\bar{Q}_s$, mean outfall discharge"),
        Line2D([], [], color=LANE_C["D-Flow FM"], lw=1.4,
               label=r"$\bar{s}_1$, $\bar{h}_s$, mean level and depth"),
        Line2D([], [], color=LANE_C["MODFLOW 6"], lw=1.4,
               label=r"$Q^{\mathrm{ext}}$, boundary flow"),
        # Neutral, not a lane color: the seepage is a property of neither model.
        Line2D([], [], color="0.25", lw=1.4,
               label=r"$Q_j$, aquifer-sewer seepage"),
    ]
    styles.graph_legend(ax=ax, handles=handles,
                        labels=[h.get_label() for h in handles],
                        loc="lower center", bbox_to_anchor=(0.5, -0.34),
                        ncol=4, frameon=False, fontsize=7)
    styles.xlabel(ax=ax, label="Model time")
    styles.heading(ax=ax, heading="Model time steps, order of execution, and "
                                  "exchanged state")

    fig.savefig(OUT)
print("wrote", OUT)
