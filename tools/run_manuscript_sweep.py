"""Run the 46 coupled simulations the manuscript documents, under coastal seepage.

The run list is the one stated in Hughesetal_AWR_LISSCoupling.tex:

    "Each grid was simulated at seven coupling intervals -- 15 and 30 minutes and
    1, 2, 4, 8, and 24 hours -- under both sampling and averaging of the coastal
    boundary, with two further intervals, 6 and 12 hours, added on the coarse
    grid, giving 46 simulations in total."

Taking the list from the manuscript rather than from a runner's defaults is the
point of this script. tools/run_seep.sh carried three intervals, so "the set is
complete" meant complete as that script defined it, and the gap against the
manuscript went unnoticed for a week.

A run counts as finished only when its output is verified, never when the process
exits zero. run_scenario.py can return zero having written a tracer that is a
48-byte header stub, and a size check accepts one; the test here is that the tracer
reopens as UGRID and carries times, which is the property the figures need. Nothing
advances to the next scenario until the one before it passes.

Resumable: a verified scenario is skipped, so re-invoking after a stop or a crash
picks up where it left off and at most repeats the run that was in flight.

Writes tools/.sweep_status.json after every state change so progress can be read
without parsing logs. See tools/sweep_status.py.
"""
import argparse
import datetime as dt
import json
import pathlib as pl
import subprocess
import sys
import time

ROOT = pl.Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results" / "gp"
STATUS = ROOT / "tools" / ".sweep_status.json"
CONDA = "C:/Users/jdhug/miniforge3/condabin/conda.bat"

# The manuscript's seven intervals, in hours, plus the two added on coarse.
SEVEN = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 24.0]
COARSE_EXTRA = [6.0, 12.0]
GRIDS = {"coarse": SEVEN + COARSE_EXTRA, "medium": SEVEN, "high": SEVEN}

# Reduction of the D-Flow FM water level over the coupling interval, and the suffix
# each carries in the scenario id.
REDUCTIONS = [("mean", "_meanbnd"), ("instant", "_instbnd")]

# Measured wall time per run, in minutes, from the sweeps of 2026-09-05 to 09-15.
# Used only for the estimate before a grid has run here; once runs finish, the
# observed mean for that grid replaces it.
NOMINAL_MIN = {"coarse": 50.0, "medium": 128.0, "high": 290.0}


def tag(hours):
    """The coupling tag MODFLOW scenario ids use, e.g. 0.5 -> 30.00M."""
    if hours < 1.0:
        return f"{hours * 60:05.2f}M"
    if hours < 24.0:
        return f"{hours:05.2f}H"
    return f"{hours / 24:05.2f}D"


def scenario(grid, hours, suffix):
    return f"gp_{grid}_{tag(hours)}_n244{suffix}_seep"


def run_list():
    """The 46, ordered cheapest grid first and every mean before every instant."""
    out = []
    for grid, hours_list in GRIDS.items():
        for red, suffix in REDUCTIONS:
            for h in hours_list:
                out.append((grid, h, red, suffix, scenario(grid, h, suffix)))
    return out


def complete(name):
    """True only if the scenario's output is present and its tracer is readable.

    A killed netCDF write leaves a 48-byte header rather than an empty file, so the
    tracer is opened rather than measured.
    """
    d = RESULTS / name
    for f in ("gwf.obs.csv", "swmm_q.npz", "dflow_tracer.nc"):
        if not (d / f).is_file():
            return False
    try:
        import xarray as xr
        with xr.open_dataset(d / "dflow_tracer.nc") as ds:
            return "mesh2d_sewage" in ds.variables and ds.sizes.get("time", 0) > 0
    except Exception:
        return False


def load_prior():
    """The status left by the previous invocation, or an empty dict.

    The sweep is restarted after every stop -- a deadline, a crash, a reboot -- and
    a fresh state each time would reset the campaign's accumulated run time, which
    is the one number the calendar cannot supply.
    """
    if not STATUS.is_file():
        return {}
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def allowance(grid, history, safety):
    """Minutes to allow for a run of this grid before starting it under a deadline.

    The mean under-predicts: coarse 15.00M took 71.8 min against a 50 min nominal,
    and gp_high_08.00H_n244_instbnd_seep took 8 h 20 m against its sibling's 4 h 33 m.
    A deadline is a promise that the machine is idle at a stated hour, so this uses
    the worst time seen for the grid rather than the average, times a safety factor.
    """
    seen = [h["minutes"] for h in history if h["grid"] == grid]
    return max(max(seen, default=0.0), NOMINAL_MIN[grid]) * safety


def write_status(state):
    state["last_update"] = dt.datetime.now().isoformat()
    STATUS.write_text(json.dumps(state, indent=1), encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--grids", default="coarse,medium,high",
                   help="comma-separated subset, in the order to run them")
    p.add_argument("--deadline", default=None, metavar="YYYY-MM-DDTHH:MM",
                   help="stop starting new runs once the projected finish passes "
                        "this instant; the run in flight is always allowed to end")
    p.add_argument("--deadline-safety", type=float, default=1.25, metavar="F",
                   help="multiply the worst time seen for a grid by this before "
                        "testing a start against the deadline (default 1.25)")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    wanted = [g.strip() for g in a.grids.split(",") if g.strip()]
    runs = [r for r in run_list() if r[0] in wanted]
    deadline = dt.datetime.fromisoformat(a.deadline) if a.deadline else None

    done = [r for r in runs if complete(r[4])]
    todo = [r for r in runs if not complete(r[4])]
    print(f"manuscript run list: {len(run_list())} scenarios "
          f"({', '.join(f'{g} {len(h) * 2}' for g, h in GRIDS.items())})")
    print(f"selected: {len(runs)}   already verified: {len(done)}   to run: {len(todo)}")
    if deadline:
        print(f"deadline: {deadline:%Y-%m-%d %H:%M}")
    if a.dry_run:
        for g, h, red, suf, name in todo:
            print(f"  would run {name:44s} ({g}, {h} h, {red})")
        return 0

    prior = load_prior()
    observed = {}
    state = {"total": len(runs), "verified": len(done),
             "campaign_started": (prior.get("campaign_started") or prior.get("started")
                                  or dt.datetime.now().isoformat()),
             "started": dt.datetime.now().isoformat(),
             "current": None, "index": len(done),
             "history": list(prior.get("history", [])),
             "interrupted": list(prior.get("interrupted", [])),
             "finished": False,
             "deadline": deadline.isoformat() if deadline else None,
             "deadline_safety": a.deadline_safety}

    # A scenario left in flight in the prior status never finished: the sweep clears
    # `current` on every path out. Record it, so the campaign shows the interruption
    # and so its wall time is not counted as work that produced a result.
    if prior.get("current"):
        state["interrupted"].append({"name": prior["current"]["name"],
                                     "started": prior["current"]["started"],
                                     "noticed": dt.datetime.now().isoformat()})
        print(f"resuming: {prior['current']['name']} was in flight at the last stop "
              f"and is being run again")
    write_status(state)

    for i, (grid, hours, red, suffix, name) in enumerate(todo, start=1):
        per = observed.get(grid) or NOMINAL_MIN[grid]
        allow = allowance(grid, state["history"], a.deadline_safety)
        if deadline and dt.datetime.now() + dt.timedelta(minutes=allow) > deadline:
            print(f"\nstopping before {name}: a {grid} run is allowed "
                  f"{allow:.0f} min, which passes the deadline {deadline:%a %d %b %H:%M}")
            state["stopped_on_deadline"] = name
            write_status(state)
            break

        idx = len(done) + i
        state["current"] = {"name": name, "grid": grid, "hours": hours,
                            "reduction": red, "index": idx,
                            "started": dt.datetime.now().isoformat(),
                            "expected_min": per}
        state["index"] = idx
        write_status(state)
        print(f"\n=== {dt.datetime.now():%H:%M:%S}  [{idx}/{len(runs)}]  {name} ===",
              flush=True)

        t0 = time.time()
        rc = subprocess.call([CONDA, "run", "-n", "liss", "--no-capture-output",
                              "python", "-u", "notebooks-GP/run_scenario.py",
                              "--resolution", grid, "--coupling-hours", str(hours),
                              "--junctions", "244", "--coastal-averaging", red,
                              "--scenario-suffix", suffix, "--coastal-seepage"],
                             cwd=str(ROOT))
        mins = (time.time() - t0) / 60.0

        if rc != 0:
            print(f"=== {name}: run_scenario.py returned {rc} -- stopping ===")
            state["current"] = None
            state["failed"] = {"name": name, "rc": rc}
            write_status(state)
            return rc
        if not complete(name):
            print(f"=== {name}: exited zero but its output does not verify -- stopping ===")
            state["current"] = None
            state["failed"] = {"name": name, "rc": 0, "reason": "output did not verify"}
            write_status(state)
            return 1

        print(f"=== {dt.datetime.now():%H:%M:%S}  {name} verified in {mins:.1f} min ===",
              flush=True)
        state["history"].append({"name": name, "grid": grid, "minutes": round(mins, 1)})
        state["verified"] = len(done) + i
        state["current"] = None
        write_status(state)

        got = [h["minutes"] for h in state["history"] if h["grid"] == grid]
        observed[grid] = sum(got) / len(got)

        subprocess.call([CONDA, "run", "-n", "liss", "--no-capture-output",
                         "python", "-u", "tools/reclaim_maps.py",
                         "--resolution", grid], cwd=str(ROOT))

    state["finished"] = True
    state["current"] = None
    write_status(state)
    remaining = [r for r in runs if not complete(r[4])]
    print(f"\nSWEEP STOPPED {dt.datetime.now():%Y-%m-%d %H:%M:%S}   "
          f"verified {len(runs) - len(remaining)} of {len(runs)}, {len(remaining)} remaining")
    return 0


if __name__ == "__main__":
    sys.exit(main())
