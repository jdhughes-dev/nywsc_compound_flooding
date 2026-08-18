"""Does the simulation start time decide which boundary reduction scores better?

The coupled runs all begin at the same instant, which raises a fair question
about the finding that sampling scores better than averaging below the Nyquist
limit: is that a property of the reductions, or of the instant chosen? This
answers it without running a coupled model, on the same fitted water level the
reduction figure uses, by varying only the phase at which the record is entered.

Two things are reported for each coupling interval, over a full day of start
offsets:

  retained range   how much of the water-level range survives the reduction.
                   Averaging flattens the tide within the interval, by a
                   factor |sin(x)|/x with x = pi*dt/T; sampling keeps it all.
  mean offset      how far the reduced record's mean sits from the true mean.
                   Averaging preserves the mean exactly, by construction;
                   sampling displaces it by an amount that depends on which
                   tidal phases the sampling instants happen to occupy.

Neither of those depends on the start time, which is why the ordering below the
Nyquist limit cannot be reversed by starting six hours later. Where sampling
aliases, the mean offset is large and start-dependent, and that is where the
start date does set the size of the penalty.

Run it directly; it prints the numbers quoted in Section 4.1 and needs nothing
from results/ or from the archives.
"""
import numpy as np

# The three semidiurnal constituents fitted to the NOAA CO-OPS record at Kings
# Point, as in make_boundary_reduction_figure.py. K1 and O1 are dropped there and
# here for the same reason: they lengthen the sum without changing the argument.
MEAN_LEVEL = 0.032
CONSTITUENTS = [("M2", 12.4206, 1.110), ("S2", 12.0000, 0.225), ("N2", 12.6583, 0.287)]
T_M2 = 12.4206
DT_U = 300.0 / 3600.0          # D-Flow FM user time step, in hours
DAYS = 89.0                    # the simulated period
SPINUP_D = 5.0                 # excluded, as everywhere else in this work
INTERVALS = [0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 24.0]
OFFSETS_H = np.arange(0.0, 24.0, 0.1)

t = np.arange(0.0, DAYS * 24.0, DT_U)
keep = t >= SPINUP_D * 24.0


def stage(offset_h):
    """The fitted water level, entered offset_h into the record."""
    s = np.full_like(t, MEAN_LEVEL)
    for _, period, amp in CONSTITUENTS:
        s += amp * np.cos(2.0 * np.pi * (t + offset_h) / period)
    return s


def reduce_held(s, n):
    """Both reductions of s, each held across its own block of n samples."""
    nfull = (len(s) // n) * n
    b = s[:nfull].reshape(-1, n)
    return np.repeat(b[:, -1], n), np.repeat(b.mean(axis=1), n), nfull


def amplitude_kept(dtc, period=T_M2):
    x = np.pi * dtc / period
    return abs(np.sin(x) / x)


def main():
    print(f"{DAYS:.0f}-day record, {SPINUP_D:.0f}-day spin-up excluded, "
          f"start swept through {OFFSETS_H[-1] + OFFSETS_H[1]:.0f} h "
          f"in {len(OFFSETS_H)} steps\n")
    print(f"{'interval':>8} {'M2 kept':>8} | {'retained range, m':>24} | "
          f"{'|mean offset|, mm':>28}")
    print(f"{'hours':>8} {'frac':>8} | {'sampled':>11} {'averaged':>11} | "
          f"{'sampled med':>12} {'sampled max':>12} {'averaged':>9}")
    for dtc in INTERVALS:
        n = int(round(dtc / DT_U))
        rng_i, rng_m, off_i, off_m = [], [], [], []
        for off in OFFSETS_H:
            s = stage(off)
            si, sm, nfull = reduce_held(s, n)
            m = keep[:nfull]
            truth = s[:nfull][m].mean()
            rng_i.append(si[m].max() - si[m].min())
            rng_m.append(sm[m].max() - sm[m].min())
            off_i.append(abs(si[m].mean() - truth) * 1000.0)
            off_m.append(abs(sm[m].mean() - truth) * 1000.0)
        print(f"{dtc:8.1f} {amplitude_kept(dtc):8.3f} | {np.mean(rng_i):11.3f} "
              f"{np.mean(rng_m):11.3f} | {np.median(off_i):12.1f} "
              f"{np.max(off_i):12.1f} {np.max(off_m):9.3f}")

    print("\nStart offsets placing the sampled mean within 20 mm of the true mean:")
    for dtc in (8.0, 12.0, 24.0):
        n = int(round(dtc / DT_U))
        good = 0
        for off in OFFSETS_H:
            s = stage(off)
            si, _, nfull = reduce_held(s, n)
            m = keep[:nfull]
            good += abs(si[m].mean() - s[:nfull][m].mean()) * 1000.0 < 20.0
        print(f"  {dtc:5.1f} h  {good / len(OFFSETS_H):5.1%}")


if __name__ == "__main__":
    main()
