"""Run the start-phase matrix of docs/GP/START_PHASE_EXPERIMENT.md.

Three start instants besides the production control, and at each one the two
coupling intervals where the ordering claim lives -- 4 and 6 hours, both below the
M2 Nyquist limit -- under both representations, plus the 15-minute reference that
start has to be scored against. Five runs per start, fifteen in all, coarse grid,
sequentially: the runs contend for cores and the timings assume one at a time.

Resumable, like run_sweep.py and for the same reason. A scenario whose results
directory already holds gwf.obs.csv is skipped, so an interrupted matrix is
continued by issuing the same command again and at most the run in flight is lost.

The reference is the SAMPLED 15-minute run, which is what the manuscript scores
against. It is one run per start rather than two: on the production start the
ordering at 4 and 6 hours holds under both the sampled and the averaged reference,
so the choice is not what decides the sign there. If a start comes out marginal,
add its averaged reference before believing the margin.
"""
import pathlib as pl
import subprocess
import sys
import time

HERE = pl.Path(__file__).resolve().parent
RESULTS = HERE.parent / "results" / "gp"

# From pick_start_times.py, rounded to the 300 s user time step. Later than the
# production start, never earlier: the surge series begins at the production start.
STARTS = [
    ("20100101232000", "worst for sampling at 6 h (14.65 mm), 88.53 d"),
    ("20100101152500", "best for sampling at 6 h (0.08 mm), 88.86 d"),
    ("20100101192000", "intermediate phase, 88.69 d"),
]

# (coupling hours, --coastal-averaging, --scenario-suffix)
MATRIX = [
    (0.25, "instant", "_instbnd"),
    (4.0, "instant", "_instbnd"),
    (4.0, "mean", "_meanbnd"),
    (6.0, "instant", "_instbnd"),
    (6.0, "mean", "_meanbnd"),
]


def tag(hours):
    if hours < 1.0:
        return f"{hours * 60:05.2f}M"
    return f"{hours:05.2f}H" if hours < 24 else "01.00D"


def scenario_of(start, hours, suffix):
    return f"gp_coarse_{tag(hours)}_n244{suffix}_t{start[8:12]}"


def finished(name):
    return (RESULTS / name / "gwf.obs.csv").is_file()


def main():
    todo = [(s, h, a, x) for s, _ in STARTS for h, a, x in MATRIX]
    done = [t for t in todo if finished(scenario_of(t[0], t[1], t[3]))]
    print(f"start-phase matrix: {len(todo)} runs, {len(done)} already finished\n")
    for start, note in STARTS:
        print(f"  {start[:4]}-{start[4:6]}-{start[6:8]} {start[8:10]}:{start[10:12]}  {note}")
    print()

    t_all = time.perf_counter()
    ok = True
    for i, (start, hours, avg, suffix) in enumerate(todo, 1):
        name = scenario_of(start, hours, suffix)
        if finished(name):
            print(f"[{i:2d}/{len(todo)}] skip     {name}  (already run)", flush=True)
            continue
        print(f"[{i:2d}/{len(todo)}] running  {name}", flush=True)
        t0 = time.perf_counter()
        rc = subprocess.run(
            [sys.executable, "-u", "run_scenario.py",
             "--resolution", "coarse", "--coupling-hours", str(hours),
             "--start-datetime", start, "--coastal-averaging", avg,
             "--scenario-suffix", suffix],
            cwd=str(HERE),
        ).returncode
        mins = (time.perf_counter() - t0) / 60.0
        print(f"[{i:2d}/{len(todo)}] {'OK  ' if rc == 0 else 'FAIL'}     {name}  "
              f"{mins:.1f} min", flush=True)
        if rc != 0:
            ok = False
            print("        stopping: a failed run leaves the matrix incomplete and "
                  "the next run would hide it", flush=True)
            break
    print(f"\ntotal {(time.perf_counter() - t_all) / 60.0:.1f} min  "
          f"{'matrix complete' if ok else 'MATRIX INCOMPLETE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
