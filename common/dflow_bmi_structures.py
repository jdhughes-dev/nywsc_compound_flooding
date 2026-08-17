"""Read (and write) D-Flow FM structure quantities through the BMI by name.

D-Flow FM exposes its named structures -- pumps, weirs, orifices, gates,
generalstructures, culverts, sourcesinks, dambreak, observations, crosssections,
laterals -- as BMI variables, but NOT in the form the flat variable list suggests.
`get_var_name()` reports a bare category name such as ``sourcesinks``, and asking
for that directly fails::

    fm.get_var("sourcesinks")
    ValueError: type not found for variable sourcesinks

because ``get_var_type("sourcesinks")`` returns an empty string and bmi-python
raises before it ever reaches the library. The bare name is a category marker, not
a readable variable.

What works is a three-part key, ``<category>/<id>/<field>``, where ``<id>`` is the
structure id from the .ext file::

    fm.get_var("sourcesinks/AlternateSewer/discharge")   # -> array([0.25])

Verified against dflowfm.dll 2026.01 on the coarse Greenport model: the returned
array is a LIVE view into D-Flow FM memory, exactly like ``s1`` or ``hs``. A handle
taken once after initialize() keeps reporting the current value across update()
calls with no need to re-read it.

**Writing works, but only from inside the timestep.** Around a plain ``update()``
the write is inert: measured against a control over 10 steps with the real .bc
(flat 0 across that window, so the source contributes nothing on its own), writing
500 m3/s every step gave results bit-identical to the control -- same water level
at the source cell to six decimals, total-volume difference exactly 0 m3. Writing
before update() is wiped by the forcing re-evaluation and reads back 0.0; writing
after it persists in the buffer but is discarded at the next step before use.

That is a sequencing problem, not a read-only slot. ``update(dt)`` calls
``flow_run_sometimesteps``, which runs the whole user timestep internally, so a
write from Python can only ever land outside it. unstruc_bmi.F90 also exports the
halves, and between them is a window where the write survives::

    dfm_init_user_timestep(timetarget)  -> flow_init_usertimestep
                                           -> set_external_forcings   (.bc overwrites)
    <-- write here
    dfm_run_user_timestep()             -> flow_run_usertimestep      (consumes it)
    dfm_finalize_user_timestep()

Verified three ways over 10 steps: the split loop with no write reproduces
``update()`` to exactly 0.0 m3 (so the loop is equivalent), and with the write it
delivers 100.0% of the expected volume -- 500 m3/s * 300 s = 150,000 m3 per step,
every step. `step_user_timestep()` below implements this.

Editing FlowFM_bnd.ext is NOT required and does not help: the .bc must stay bound
(see below), and the mechanism is purely about when the write happens.

The mechanism is visible in fm_external_forcings_update.f90, which rebinds the whole
array from the EC (external forcing) module on every forcing update::

    source_sink_all_discharges_1d(1:size(source_sink_all_discharges)) => source_sink_all_discharges
    success = success .and. ec_gettimespacevalue(ecInstancePtr, &
                 item_discharge_salinity_temperature_sorsin, irefdate, tzone, &
                 tunit, time_in_seconds, source_sink_all_discharges_1d)

``ec_gettimespacevalue`` overwrites the array from the .bc at ``time_in_seconds``,
unconditionally. That is why a write placed around update() is lost, and why one
placed after dfm_init_user_timestep() survives -- the overwrite has already
happened for that step.

The .bc also cannot be unbound: ``discharge`` is a required key, and removing it
aborts initialization with ``ERROR: Incomplete block in file 'FlowFM_bnd.ext':
[sourcesink]. Key "discharge" is missing.`` Leave it in place; its value is simply
superseded each step by the write. A flat-zero series is a reasonable placeholder.

``qext`` also injects volume (verified at 100.0% likewise) and is what
step2_run_coupled_models uses for the groundwater exchange, but it carries NO
constituent, so it cannot deliver sewage tracer. For a tracer source the
source-sink route above is the one that works: ``tracersewageDelta`` stays driven
by its .bc, so with a constant delta the mass flux follows the written discharge
automatically.

Three sharp edges, which is why this module exists rather than a bare get_var call:

1. ``get_var_rank`` and ``get_var_type`` do NOT validate the key. Every
   ``sourcesinks/<anything>/<anything>`` reports rank=1, type='double'. They tell
   you nothing about whether the field exists.

2. An unrecognized field or id returns a NULL pointer, which bmi-python turns into
   ``None``. ``get_compound_field`` in unstruc_bmi.F90 gives a SourceSink exactly
   three fields, matching the ``shape(2) = 3`` it reports::

       discharge              source_sink_all_discharges(1, i)        always
       change_in_salinity     source_sink_all_discharges(isalt+1, i)  NULL if isalt == 0
       change_in_temperature  source_sink_all_discharges(itemp+1, i)  NULL if itemp == 0

   So on these models only ``discharge`` resolves -- the MDU sets Salinity = 0 and
   Temperature = 0, and those two cases return early. There is NO tracer field:
   ``tracersewageDelta`` is a .bc-only forcing and is not reachable through BMI,
   nor is ``area`` (ignored entirely for a point source).

3. Worst case, a wrong CATEGORY with a real id returns a non-NULL pointer to
   garbage. ``laterals/AlternateSewer/discharge`` handed back an array whose first
   read access-violated and killed the process -- no exception, no traceback. This
   is unrecoverable in-process, so the only defense is to not make the call.

`structure_ids()` parses the model's .ext files so `get_structure()` can refuse a
(category, id) pair the model does not actually define, turning what would be a
hard crash into a normal exception.
"""

import pathlib as pl
import re

# Category names D-Flow FM lists in get_var_name(). Only these are addressable as
# <category>/<id>/<field>; anything else is rejected before reaching the library.
CATEGORIES = (
    "pumps",
    "weirs",
    "orifices",
    "gates",
    "generalstructures",
    "culverts",
    "sourcesinks",
    "dambreak",
    "observations",
    "crosssections",
    "laterals",
)

# .ext block header -> BMI category. Only the blocks these models actually use are
# mapped; add to this as needed rather than guessing at a pluralization rule.
_BLOCK_TO_CATEGORY = {
    "sourcesink": "sourcesinks",
    "lateral": "laterals",
    "pump": "pumps",
}

_BLOCK = re.compile(r"^\s*\[(\w+)\]")
_ID = re.compile(r"^\s*id\s*=\s*(\S+)", re.IGNORECASE)


def structure_ids(model_dir):
    """Map BMI category -> set of structure ids defined in a model's .ext files.

    model_dir is the directory holding FlowFM.mdu; every *.ext beside it is read.
    """
    model_dir = pl.Path(model_dir)
    found = {}
    for ext in sorted(model_dir.glob("*.ext")):
        category = None
        for line in ext.read_text(errors="replace").splitlines():
            m = _BLOCK.match(line)
            if m:
                category = _BLOCK_TO_CATEGORY.get(m.group(1).lower())
                continue
            if category is None:
                continue
            m = _ID.match(line)
            if m:
                found.setdefault(category, set()).add(m.group(1))
    return found


def get_structure(fm, category, sid, field="discharge", known=None, required=True):
    """Return the live array for ``<category>/<sid>/<field>``.

    fm       an initialized bmi.wrapper.BMIWrapper
    known    the mapping from structure_ids(); when given, a (category, sid) pair
             the model does not define raises instead of risking the garbage
             pointer described in the module docstring. Pass None only if you have
             already established the pair is real.
    required raise when the library returns NULL; set False to get None back.

    The result aliases D-Flow FM's own memory. Hold it across update() calls to
    watch the value evolve, or .copy() it if you need a snapshot.
    """
    if category not in CATEGORIES:
        raise ValueError(
            f"{category!r} is not a D-Flow FM structure category; expected one of "
            f"{', '.join(CATEGORIES)}"
        )
    if known is not None:
        defined = known.get(category, set())
        if sid not in defined:
            raise KeyError(
                f"{sid!r} is not a {category} in this model (defined: "
                f"{sorted(defined) or 'none'}). Refusing the lookup: a wrong "
                "category/id pair can return a pointer to garbage that faults on "
                "read and kills the process."
            )

    key = f"{category}/{sid}/{field}"
    value = fm.get_var(key)
    if value is None and required:
        raise KeyError(
            f"{key!r} resolved to a NULL pointer. The id is defined, so the field "
            f"name is probably not exposed -- for sourcesinks only 'discharge' was "
            "readable in testing, even though the .ext also accepts area and "
            "tracersewageDelta."
        )
    return value


def bind_user_timestep(fm):
    """Declare ctypes signatures for the split user-timestep entry points.

    bmi-python does not wrap these, so they are called straight off fm.library.
    Fortran ``real(c_double), intent(in)`` without VALUE is passed by reference,
    hence the POINTER argtype on the init call.
    """
    import ctypes

    lib = fm.library
    lib.dfm_init_user_timestep.argtypes = [ctypes.POINTER(ctypes.c_double)]
    lib.dfm_init_user_timestep.restype = ctypes.c_int
    lib.dfm_run_user_timestep.argtypes = []
    lib.dfm_run_user_timestep.restype = ctypes.c_int
    lib.dfm_finalize_user_timestep.argtypes = []
    lib.dfm_finalize_user_timestep.restype = ctypes.c_int
    return lib


def step_user_timestep(fm, dt_user, overrides=None, known=None, lib=None):
    """Advance one user timestep, applying overrides where they actually take.

    Drop-in replacement for ``fm.update(dt_user)``. With overrides=None it is
    equivalent -- verified to 0.0 m3 of total-volume difference over 10 steps.

    overrides maps (category, id, field) -> value, applied after the external
    forcing has been re-evaluated and before the flow computation consumes it::

        lib = bind_user_timestep(fm)
        known = structure_ids(run_dir)
        step_user_timestep(fm, 300.0,
                           {("sourcesinks", "AlternateSewer", "discharge"): q_m3s},
                           known=known, lib=lib)

    dt_user must equal the model's DtUser; D-Flow FM checks this and warns
    otherwise, as it does not support a varying user timestep.
    """
    import ctypes

    import numpy as np

    if lib is None:
        lib = bind_user_timestep(fm)

    target = ctypes.c_double(fm.get_current_time() + dt_user)
    r_init = lib.dfm_init_user_timestep(ctypes.byref(target))

    for (category, sid, field), value in (overrides or {}).items():
        # Validate through the same guard that keeps a bad category from returning
        # a pointer to garbage.
        get_structure(fm, category, sid, field=field, known=known)
        fm.set_var(f"{category}/{sid}/{field}",
                   np.asarray(value, dtype="double").reshape(-1))

    r_run = lib.dfm_run_user_timestep()
    r_fin = lib.dfm_finalize_user_timestep()

    status = (r_init, r_run, r_fin)
    if any(status):
        raise RuntimeError(
            f"user timestep returned nonzero status (init, run, finalize) = {status}; "
            "DFM_NOERR is 0"
        )
    return status
