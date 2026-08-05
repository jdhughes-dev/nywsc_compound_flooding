"""Schematic of the coupling sequence over two coupling intervals.

Bar width is the model time step each simulator integrates, so the time-step
hierarchy is visible directly: one MODFLOW 6 bar spans the whole coupling
interval, while SWMM and D-Flow FM tile that same span with shorter bars, one per
user time step. The second and third of those are drawn faded and without arrows,
so the repeat reads as "and so on" rather than as three distinct exchanges.

Lanes are ordered by execution within a step -- SWMM, then D-Flow FM, then
MODFLOW 6 -- so the figure answers "which model runs first" directly rather than
implying a physical stacking.

Every exchange is drawn as an orthogonal polyline that leaves the END of the
producing model's time step and enters the START of the time step that consumes
it. The horizontal run is therefore the lag, read directly off the time axis:

    q_s      leaves the end of a SWMM user step and enters the start of the SAME
             D-Flow FM step, so it runs backward by exactly one user step. SWMM
             leads deliberately, so its outfall covers the interval D-Flow FM is
             about to integrate.
    s1,hs    leaves the end of the last D-Flow FM step in the interval and enters
             the start of the MODFLOW 6 step spanning that same interval, so it
             runs backward across the whole interval. Taking the boundary at the
             end of the step is consistent with MODFLOW 6's own backward-in-time
             step and introduces no lag.
    q^ext    leaves the end of the MODFLOW 6 step and enters the start of the next
    Q_j      interval, because neither can be recovered until MODFLOW 6 has
             finalized. These are the lagged exchanges, and the sweep over
             coupling intervals is what bounds that lag.

A narrow gutter separates the coupling intervals. It occupies no model time -- both
of its edges carry the same tick, and it is marked as an axis break rather than
boxed. Orthogonal connectors turn in the horizontal channels rather than inside it,
so it only has to be wide enough to keep the two MODFLOW 6 blocks from abutting,
which would read as one continuous step across both intervals.

Three user time steps per interval is not a simplification at the finest coupling
interval simulated -- 15-minute coupling on a 300 s user time step is exactly
three. The caption gives 288 as the ratio at daily coupling.
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

# Routing channels, chosen so no two runs are ever collinear -- every horizontal
# has its span to itself at that height, and the verticals that share an x have
# disjoint extents. Connectors do cross, which is legible; what is not legible is
# two lines lying on top of each other, where the upper one simply hides the other.
# The band between MODFLOW 6 and D-Flow FM carries two horizontals: s1,hs runs left
# of the gutter and q^ext runs right of it, so they never meet.
Y_QS, Y_S1, Y_QE = 1.50, 0.62, 0.52
Y_QJ_UP, Y_QJ_DN = 1.58, 0.36     # Q_j delivery channels
# The two collection arms have to arrive at different heights. Routing both along
# the centre line would make them collinear over most of their length, which is the
# one thing that genuinely hides a connector.
Y_QJ_IN_S, Y_QJ_IN_M = 1.12, 0.88


def bar(ax, lane, x0, x1, alpha=1.0):
    y = LANE_Y[lane]
    ax.add_patch(Rectangle((x0, y - H), x1 - x0, 2 * H, facecolor=LANE_C[lane],
                           edgecolor="none", alpha=alpha, zorder=3))


def poly(ax, pts, color, label=None, lxy=None, ha="left", both=False, lw=1.1):
    """Orthogonal connector through the given vertices, head on the last segment.

    FancyArrowPatch takes a Path directly, which keeps the whole connector a
    single artist -- drawing it as separate segments would leave visible gaps at
    the corners at this line width."""
    ax.add_patch(FancyArrowPatch(path=Path(pts),
                                 arrowstyle="<|-|>" if both else "-|>",
                                 mutation_scale=8, linewidth=lw, color=color,
                                 shrinkA=0, shrinkB=0, zorder=5,
                                 joinstyle="miter", capstyle="butt"))
    if label and lxy:
        ax.text(lxy[0], lxy[1], label, fontsize=7.5, ha=ha, va="center",
                color=color, zorder=6)


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
                # Backward by one user step: SWMM finishes the step, and D-Flow FM
                # then integrates that same step from its start.
                poly(ax, [(b, SW_B), (b, Y_QS), (a, Y_QS), (a, DF_T)],
                     LANE_C["SWMM"], r"$\bar{q}_s$",
                     lxy=((a + b) / 2.0, Y_QS + 0.11), ha="center")

        # The gutter is a break in the time axis, so it is marked as one: a light
        # rule on each edge rather than a box. A box around a gutter this narrow
        # would crowd the connectors turning inside it, and would also suggest the
        # gutter contains something, when it contains no model time at all.
        for xv in (xe, xn):
            ax.plot([xv, xv], [-0.30, 2.44], color="0.6", linewidth=0.7,
                    linestyle=(0, (3, 2)), zorder=1)
        ax.text(xe + W_GUT / 2.0, -0.36, "exchange", ha="center", va="top",
                fontsize=7, color="0.35", style="italic")

        # BACKWARD across the interval, into the start of the MODFLOW 6 step that
        # spans it.
        poly(ax, [(xe, DF_B), (xe, Y_S1), (x0, Y_S1), (x0, MF_T)],
             LANE_C["D-Flow FM"], r"$s_1,\,h_s$",
             lxy=((x0 + xe) / 2.0, Y_S1 - 0.13), ha="center")
        # FORWARD into the next interval. Both leave the same corner -- the end of
        # the MODFLOW 6 step -- because both come from the same solution.
        poly(ax, [(xe, MF_T), (xe, Y_QE), (xn, Y_QE), (xn, DF_B)],
             LANE_C["MODFLOW 6"], r"$q^{\mathrm{ext}}$",
             lxy=(xe + 0.38, Y_QE + 0.15), ha="left")
        # Q_j is collected from both models and delivered to both, so it is drawn
        # as a junction rather than as a line between them: two thin arms bring the
        # end-of-step state in from the SWMM and MODFLOW 6 bars, and two arms carry
        # the resulting flux out to the START of the next step in each. Verified
        # against the loop -- update_swmm writes the API well package and
        # generated_inflow AFTER finalize_time_step, so neither is seen until the
        # following step, and both are then held across it.
        #
        # The earlier version ran a horizontal along the bottom edge of the SWMM
        # bars, which read as underlining them rather than entering them.
        xi_s, xi_m, xc = xe + 0.18, xe + 0.34, xe + 0.70
        poly(ax, [(xe, SW_B), (xi_s, SW_B), (xi_s, Y_QJ_IN_S), (xc - 0.17, Y_QJ_IN_S)],
             "0.45", lw=0.75)
        poly(ax, [(xe, MF_T), (xi_m, MF_T), (xi_m, Y_QJ_IN_M), (xc - 0.17, Y_QJ_IN_M)],
             "0.45", lw=0.75)
        # Both arms enter just inside the next bars rather than exactly on their
        # left edge. s1,hs of the following interval already lands on that edge, and
        # its vertical run covers the whole of Q_j's, so drawn there the seepage arm
        # would sit inside the blue one and vanish.
        xd = xn + 0.16
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
    # time -- so both carry the tick. Labelling only one edge left the other
    # unlabelled and, worse, was inconsistent between the two gutters: the first
    # was labelled on the right, the second on the left.
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
               label=r"$\bar{q}_s$, mean outfall discharge"),
        Line2D([], [], color=LANE_C["D-Flow FM"], lw=1.4,
               label=r"$s_1$, $h_s$, water level and depth"),
        Line2D([], [], color=LANE_C["MODFLOW 6"], lw=1.4,
               label=r"$q^{\mathrm{ext}}$, boundary flow"),
        # Neutral, not a lane color: Q_j belongs to neither model, being computed
        # from both and applied to both.
        Line2D([], [], color="0.25", lw=1.4,
               label=r"$Q_j$, seepage (two-way)"),
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
