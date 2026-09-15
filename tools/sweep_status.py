"""One line of progress for the manuscript sweep, for periodic polling.

Reads tools/.sweep_status.json, which run_manuscript_sweep.py rewrites at every
state change, and reports the current scenario, its position in the run list, and
two estimates: time left on the run in flight and time left on the whole sweep.

Estimates use the mean wall time observed for that grid in this sweep once a run of
it has finished, and the measured figures from the 2026-09 sweeps until then. A
grid's runs vary by tens of minutes, so treat the whole-sweep figure as a bound to
plan around rather than a prediction.
"""
import datetime as dt
import json
import pathlib as pl
import sys

ROOT = pl.Path(__file__).resolve().parent.parent
STATUS = ROOT / "tools" / ".sweep_status.json"
sys.path.insert(0, str(ROOT / "tools"))
from run_manuscript_sweep import GRIDS, NOMINAL_MIN, REDUCTIONS, complete, scenario


def hhmm(minutes):
    if minutes is None:
        return "unknown"
    minutes = max(0.0, minutes)
    h, m = divmod(int(round(minutes)), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def main():
    if not STATUS.is_file():
        print("sweep status: no run has started (tools/.sweep_status.json absent)")
        return 0
    s = json.loads(STATUS.read_text(encoding="utf-8"))

    # Per-grid mean from this sweep where available, measured defaults otherwise.
    per = dict(NOMINAL_MIN)
    for g in GRIDS:
        got = [h["minutes"] for h in s.get("history", []) if h["grid"] == g]
        if got:
            per[g] = sum(got) / len(got)

    outstanding = []
    for g, hours_list in GRIDS.items():
        for _red, suffix in REDUCTIONS:
            for h in hours_list:
                name = scenario(g, h, suffix)
                if not complete(name):
                    outstanding.append((g, name))

    cur = s.get("current")
    total = s.get("total", len(outstanding))
    now = dt.datetime.now()

    if s.get("failed"):
        f = s["failed"]
        print(f"sweep STOPPED on {f['name']} (rc={f['rc']}"
              f"{', ' + f['reason'] if f.get('reason') else ''})")
    if cur:
        started = dt.datetime.fromisoformat(cur["started"])
        elapsed = (now - started).total_seconds() / 60.0
        expect = per.get(cur["grid"], cur.get("expected_min", 0.0))
        left_cur = expect - elapsed
        head = (f"run {cur['index']} of {total}: {cur['name']}  "
                f"({elapsed:.0f} min elapsed, ~{hhmm(left_cur)} left)")
        # The current run is counted once, through left_cur.
        rest = [g for g, name in outstanding if name != cur["name"]]
    else:
        left_cur = 0.0
        head = (f"no run in flight; {len(outstanding)} of {total} scenarios outstanding"
                if outstanding else f"all {total} scenarios verified")
        rest = [g for g, _name in outstanding]

    left_all = max(0.0, left_cur) + sum(per[g] for g in rest)
    done = total - len(outstanding)
    print(f"{now:%Y-%m-%d %H:%M}  {head}")
    print(f"    verified {done} of {total}   remaining {len(outstanding)}   "
          f"whole sweep ~{hhmm(left_all)} (to {now + dt.timedelta(minutes=left_all):%a %d %b %H:%M})")
    if s.get("deadline"):
        print(f"    deadline {dt.datetime.fromisoformat(s['deadline']):%a %d %b %H:%M}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
