# Testing whether the start instant decides which representation wins

Section 9.1 claims that which of sampling and averaging is the more accurate below
the Nyquist limit is a property of the two representations and not of the instant
the simulation begins. Nothing in the manuscript measures that. `start_phase_analysis.py`
sweeps the **boundary water level** and never computes head, seepage, or tracer, so
the step from it to the ordering of the error curves in Figure 4 is an argument, not
a measurement. This is how to measure it.

## Why it is worth running

`pick_start_times.py` repeats the sweep on the water level D-Flow FM actually
simulated, rather than on the idealized three-constituent record, and the numbers
are not the same:

| coupling interval | idealized record | simulated record |
|---|---|---|
| 2 h | 0.00 – 0.95 mm | 0.01 – 1.77 mm |
| 4 h | 0.01 – 2.05 mm | 0.01 – 5.37 mm |
| 6 h | 0.10 – 3.40 mm | 0.08 – **14.65 mm** |
| 8 h | 0.05 – 5.45 mm | 0.02 – 7.67 mm |

The manuscript's bound comes from the left column. On the right, at 6 h coupling —
below the Nyquist limit, where the claim lives — the sampled mean offset moves by
almost 15 mm depending on the phase the run starts at. The aquifer attenuates a
displaced boundary mean heavily (several millimetres at the boundary accompany
0.2 mm of head bias in the 8 h comparison), so 15 mm at the boundary is perhaps
0.7 mm in head. The margins the ordering turns on are smaller than that: the
manuscript reports the two differing "by amounts too small to matter", root-mean-
square head error below 2.2 mm, with sampling ahead at 15 of 16 combinations. One
combination already goes the other way. The claim may well hold; it is not safe
enough to assert without measuring.

## What constrains the design

**Forcing — and this is the reverse of what it first looks like.** The meteo files
`Q12010_meteo.amp/amu/amv` cover 2010-01-01 00:00 to 2010-03-31 12:00, hourly, which
appears to leave 12 h of room before the production start. It does not. The surge
boundary series `WaterLevel2010_surge.bc` **begins at 2010-01-01 12:00, the
production start itself** — the paragraph this replaces checked its end, which is
2010-12-31, and not its beginning. An earlier window asks for a water level the
forcing does not carry, and D-Flow stops:

```
** WARNING: Requested time preceeds current forcing EC-timelevel by 0.045 days
**          = 3900.000 seconds ... in file: 'WaterLevel2010_surge.bc'.
** ERROR  : Error occurs when reading the restart file.
```

That is a real smoke test, at a start 65 minutes early. The forcing envelope is
exactly the production window, with no slack in either direction: earlier is blocked
by the surge series, later-stopping by the meteo.

So a start can only be moved **later, holding the stop**, which shortens the run by
the shift. A full M2 period costs 12.42 h out of 89 days, half a percent, and every
phase is reachable. Each start's own 15-minute reference shares its shortened window,
so the sign test is unaffected; only the absolute errors are not comparable with the
published ones, which is why the comparison is within a start and never across.

**Do not use 00:00, 06:00, 12:00, 18:00.** Those land at M2 phases of 0°, 174°,
348°, and 162°. First and third are the same phase to within 12°, and so are second
and fourth, so four runs would test two phases. Use the starts `pick_start_times.py`
reports instead: the phase that hurts sampling most and the one that hurts it least.
A claim that the ordering cannot be reversed is a claim about the worst case, so the
worst case is what to simulate.

**Platform.** D-Flow FM is a Windows executable, so the runs happen on the Windows
machine. Build the environment from `liss-windows.yml`.

**Every run and every saved result carries a unique start tag.** Nothing from this
experiment may land on a name an existing scenario could also produce. The tag is
`_t<HHMM>` in local run time, zero-padded, appended after the representation suffix,
so a scenario id reads `gp_coarse_06.00H_n244_meanbnd_t1054`. It is `_t` and not
`_s` because `run_scenario.py` already appends `_s<int>` for a non-default junction
seed, and `_s1054` could be read as either a seed or a start. That tag is carried by
the run directory, by both model run directories, and by every scenario in the
matrix including each start's own 15-minute reference
(`gp_coarse_15.00M_n244_meanbnd_t1054`), because a reference without the tag is the
production reference and comparing against it is the error this experiment is most
likely to make. The control is the one exception: it is the existing production run
and keeps its untagged name, so the data module maps the control start to the
unsuffixed ids explicitly rather than by pattern. The archive is
`docs/data/GP/start_phase.nc`, distinct from every archive already there, and its
results are indexed by start tag, interval and representation, so a number in it can
never be read as belonging to another start.

**Disk.** Each run leaves an 80 MB-plus `FlowFM_his.nc` and a larger `_map.nc`.
Fifteen runs is tens of gigabytes and it is not to be kept. Follow the existing
archive pattern: a `*_data.py` module recomputes from `results/` when the output is
present and reads a small `.nc` from `docs/data/GP/` when it is not. The archives
already in that directory are 19 kB and 1.5 MB. Extract, verify, then delete the
run directory.

## Run matrix

Four starts, of which the production start is the control and already exists:

| start | role | record |
|---|---|---|
| 2010-01-01 12:00 | production, already run | 89.00 d |
| 2010-01-01 23:20 | worst for sampling at 6 h, offset 14.65 mm | 88.53 d |
| 2010-01-01 15:25 | best for sampling at 6 h, offset 0.08 mm | 88.86 d |
| 2010-01-01 19:20 | intermediate, guards against reading two points as a line | 88.69 d |

Those come from `pick_start_times.py`, already rounded to the 300 s user time step,
which the driver requires and which moves the phase by under 2.5 minutes.

Coarse grid only. It is the grid the interval sweep is densest on, and 15 runs on
midres is roughly 24 h of compute against 12.

Per new start: 4 h and 6 h coupling — below the Nyquist limit, where the claim lives
and the margin is thinnest — under **both** representations, plus a 15-minute
reference. Five runs each, fifteen in all.

Estimated cost from the run times in Figure 8A: the coarse daily run is about 35 min,
15-minute coupling 2.1 times that, 4 h and 6 h about 1.2. Roughly 3.8 h per start,
11 to 12 h for the three. One overnight run, sequential.

**The reference must share its start.** A run can only be compared against a
15-minute simulation begun at the same instant; the production 15-minute run is not
a valid reference for a shifted start. That is why each start carries its own.

## The code change this needs

**This is implemented.** `--start-datetime` moves the D-Flow window and holds its
length, `dflow_start_override` carries it into the notebook, and the scenario id
gains the `_t<HHMM>` tag automatically. What follows is what was done, kept because
the reasoning is what a reader needs if it has to change:

1. In `step2_run_coupled_models.ipynb`, a top-level `dflow_start_override = None`
   in the configuration cell.
2. Where the smoke test already rewrites `StopDateTime` on the **run copy** of the
   `.mdu` — never the base — rewrite `StartDateTime` too when the override is set,
   holding the 89-day length so `StopDateTime` moves with it.
3. In `run_scenario.py`, add `"dflow_start_override": "start_datetime"` to
   `OVERRIDES` and an `--start-datetime` argument.
4. Put the start in `scenario_suffix` so run directories and `results/` entries do
   not collide: `gp_coarse_06.00H_n244_meanbnd_s0247`, and so on.

Two things the driver already handles, which the change must not break. SWMM starts
at 2010-01-01 00:00 and is fast-forwarded to the D-Flow start, so an earlier start
shortens that catch-up and an earlier-than-midnight start would trip the existing
warning. And the stress periods, which are the harder of the two.

**The stress-period problem does not exist, and here is why.** It looked as though
a start away from midnight would break the alignment the study relies on --
"every interval divides a day, so that coupling steps coincide with the boundaries
of the daily stress periods" -- because `perlen` comes from the base model rather
than from the coupling frequency. The base TDIS settles it the other way:
`modflow/gp_chd/base/modflowsim.tdis` is 365 periods of one day with **no
START_DATE_TIME**, so MODFLOW's clock is relative and period 1 begins at whatever
instant the coupled run begins. `nstp` is then set to the number of coupling steps
in a day, so each period holds exactly one day of them and every period boundary
falls on a coupling step, at any start instant whatever.

So no TDIS change is needed and the control needs no re-run. What an earlier start
does move is which wall-clock hours a day of recharge and pumping spans -- period 1
covering 10:54 to 10:54 rather than 12:00 to 12:00 -- which is a sub-hour shift of
daily forcing, identical in every run of the matrix, and negligible beside a 3 m
tide. Confirm it in the smoke-test log rather than assuming it: the coupling step
count per stress period must be unchanged from a production run at the same
interval.

## Directions for the session that runs it

Run these on the Windows machine, from the repository root, in the `liss` environment.

**1. Pick the starts.** This needs no D-Flow and can be done anywhere:

```
python docs/GP/scripts/pick_start_times.py
```

Take the worst-for-sampling and best-for-sampling starts at 6 h, round each down to
a multiple of 300 s, and choose one intermediate phase between them.

**2. Make the change above**, then prove it on a short run before committing 12 h:

```
python -u notebooks-GP/run_scenario.py --resolution coarse --coupling-hours 6     --start-datetime 20100101230000 --coastal-averaging mean     --scenario-suffix _meanbnd --smoke-days 2
```

**This has been run.** It completes in 1.3 minutes and reports:

```
scenario       : gp_coarse_06.00H_n244_smoke2d_meanbnd_t2300
START OVERRIDE : 2010-01-01 12:00:00 -> 2010-01-01 23:00:00 (11 h later);
                 stop held at 2010-03-31 12:00:00, window 89 d -> 88.54 d
advanced SWMM 23.00 h to align with the D-Flow start
SMOKE TEST     : ... (2 d, 8 coupling steps)
```

which is the whole of what needed proving: the window opens where it was asked to,
SWMM's catch-up lengthened from 12 h to 23 h and its record still covers the run,
and 6-hour coupling still gives 4 steps per one-day stress period, unchanged from a
production run.

Confirm in the log that the D-Flow window opens at the requested instant, that SWMM
reports a shorter fast-forward than the production runs, and that the run completes.
A 2-day smoke test is cheap; a wrong start discovered after 12 h is not.

**3. Run the matrix.** Sequentially — the runs contend for cores and the timings
above assume one at a time:

```
for each start S in {S1, S2, S3}:
  for each (interval, averaging) in {(0.25, both), (4, on), (4, off), (6, on), (6, off)}:
      python -u notebooks-GP/run_scenario.py --resolution coarse ^
          --coupling-hours <interval> --start-datetime <S> --scenario-suffix <tag> ^
          [--coastal-averaging <on|off>]
```

Check the exact flag names against `run_scenario.py --help`; the averaging knob is
`coastal_boundary_averaging` in the notebook.

**4. Extract, then delete.** Write `docs/GP/scripts/start_phase_data.py` on the model
of `coastal_exchange_data.py`: a `NC` under `docs/data/GP/`, a `missing()` that
reports which scenarios are absent, and a `load_or_refresh()` that recomputes from
`results/` and falls back to the archive. It needs to store, per start and per
interval and per representation, only the root-mean-square head error against that
start's own 15-minute reference, the mean (bias) of that error, and the same two for
aquifer–sewer seepage. That is a few dozen numbers — kilobytes. Verify the archive
reproduces the production start's published values before deleting anything, then
delete the run directories.

**5. Answer the question.** For each start and interval, take the sign of
`rms_sampled - rms_averaged`. The claim holds if the sign is the same at every start.
Head is deterministic — same binaries, same input — so a repeated run is identical
and a sign is a sign, not noise.

Decide the outcome by this, written down before looking:

- **Sign holds at every start, at both intervals.** The claim stands. Say in 9.1
  that it was tested against the phases that most and least favour sampling, and give
  the range of the margin.
- **Sign flips at any start.** The claim is false as written. It becomes: below the
  Nyquist limit the two differ by amounts too small to matter, and which is ahead
  depends on the start.
- **Sign holds but the margin is smaller than the change in it across starts.** The
  ordering is real for this start and not robust. Report it that way; it is the most
  likely outcome given the numbers above, and it is a more useful sentence than
  either of the other two.

## Report it in prose, not in a figure

Whatever the outcome, it goes into Section 9.1 as text. The manuscript carries eight
figures already, a ninth earns its place only by showing something prose cannot, and
this result is a handful of signs and margins — the kind of thing a sentence states
better than a panel. Two starts, two intervals and two representations is a table at
best, and the outcome that matters is a single sign and the range of a margin.

## What this does not test

One day of start phase, on one grid, at two intervals. It does not test a different
season or spring–neap phase — a 24 h shift moves about 7 percent of the 14.8-day
beat, and the meteo record does not reach far enough to do better. The existing
sentence that the daily-coupling penalty "is particular to this start date" already
covers that and should stay.
