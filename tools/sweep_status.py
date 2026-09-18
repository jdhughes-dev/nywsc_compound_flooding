"""One line of progress for the manuscript sweep, for periodic polling.

Reads tools/.sweep_status.json, which run_manuscript_sweep.py rewrites at every
state change, and reports the current scenario, its position in the run list, and
the campaign's time budget.

Two clocks are kept apart, because on this machine they diverge badly. Calendar
time is the span since the campaign began and includes every bugcheck, reboot and
overnight pause. Run time is the wall time actually spent inside runs, summed
across restarts, and it is the one that predicts what is left: a sweep that loses
a night to a crash burns calendar time and no run time at all. Both the elapsed
figure and the estimate to completion below are run time.

Estimates use the mean wall time observed for a grid across the whole campaign,
falling back to the measured figures from the 2026-09 sweeps until a grid has run.
A grid's runs vary by tens of minutes, so treat the totals as bounds to plan
around rather than predictions.
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
    history = s.get("history", [])

    # Per-grid mean from the campaign where available, measured defaults otherwise.
    per = dict(NOMINAL_MIN)
    for g in GRIDS:
        got = [h["minutes"] for h in history if h["grid"] == g]
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
        elapsed = (now - dt.datetime.fromisoformat(cur["started"])).total_seconds() / 60.0
        expect = per.get(cur["grid"], cur.get("expected_min", 0.0))
        left_cur = expect - elapsed
        head = (f"run {cur['index']} of {total}: {cur['name']}  "
                f"({elapsed:.0f} min elapsed, ~{hhmm(left_cur)} left)")
        # The current run is counted once, through left_cur.
        rest = [g for g, name in outstanding if name != cur["name"]]
    else:
        elapsed = left_cur = 0.0
        head = (f"no run in flight; {len(outstanding)} of {total} scenarios outstanding"
                if outstanding else f"all {total} scenarios verified")
        rest = [g for g, _name in outstanding]

    left_all = max(0.0, left_cur) + sum(per[g] for g in rest)
    done = total - len(outstanding)
    spent = sum(h["minutes"] for h in history) + elapsed

    print(f"{now:%Y-%m-%d %H:%M}  {head}")
    print(f"    verified {done} of {total}   remaining {len(outstanding)}")
    print(f"    run time {hhmm(spent)} spent, ~{hhmm(left_all)} to go "
          f"({hhmm(spent + left_all)} for the whole campaign)")

    began = s.get("campaign_started") or s.get("started")
    if began:
        began = dt.datetime.fromisoformat(began)
        span = (now - began).total_seconds() / 60.0
        print(f"    calendar {hhmm(span)} since {began:%a %d %b %H:%M}, "
              f"of which {hhmm(span - spent)} was not running")

    print(f"    unbroken from now, finishes "
          f"{now + dt.timedelta(minutes=left_all):%a %d %b %H:%M}")

    if s.get("deadline"):
        dl = dt.datetime.fromisoformat(s["deadline"])
        print(f"    deadline {dl:%a %d %b %H:%M} "
              f"({hhmm((dl - now).total_seconds() / 60.0)} away)")
    if s.get("stopped_on_deadline"):
        print(f"    held at the deadline before {s['stopped_on_deadline']}")

    # The campaign has already lost a finished set once, to a delete rather than to
    # a crash, so a run whose result has gone is worth saying out loud.
    gone = sorted({h["name"] for h in history if not complete(h["name"])})
    if gone:
        print(f"    NOTE {len(gone)} finished run(s) no longer on disk: "
              f"{', '.join(gone[:3])}{' ...' if len(gone) > 3 else ''}")
    if s.get("interrupted"):
        last = s["interrupted"][-1]
        print(f"    {len(s['interrupted'])} run(s) interrupted and redone "
              f"(last {last['name']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
