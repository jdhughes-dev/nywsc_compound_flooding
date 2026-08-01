import pathlib as pl

# -----------------------------------------------------------------------------
# Configuration (defaults; the functions below accept overrides)
# -----------------------------------------------------------------------------
# Number of SWMM junctions in the discretization produced by
# swmm_mf_connect.intersect_points_grid(). This only LABELS the output .bc file
# and forcing block name (e.g. "..._n244__01.00D"); the discharge series itself
# is the single downstream-junction outflow (SWMM -> D-Flow FM) already stored
# in each sewer_<tag>.tim file. Set this to the actual number of connections used
# (intersect_points_grid caps the request to the available junctions, e.g. 244).
n_junctions = 244

# D-Flow FM source/sink base id. The forcing block "name" written below must
# match the [SourceSink] id referenced in FlowFM_bnd.ext.
source_id = "AlternateSewer"

# Reference time used by the "seconds since" unit in the .tim / .bc files.
ref_time = "2000-01-01 00:00:00"


def write_forcing(f, name, ref_time, quantity, unit, times, values):
    """Write a single [Forcing] timeSeries block to an open .bc file handle."""
    f.write("[Forcing]\n")
    f.write(f"name                  = {name}\n")
    f.write("function              = timeSeries\n")
    f.write("timeInterpolation     = linear\n")
    f.write("quantity              = time\n")
    f.write(f"unit                  = seconds since {ref_time}\n")
    f.write(f"quantity              = {quantity}\n")
    f.write(f"unit                  = {unit}\n")
    for t, v in zip(times, values):
        f.write(f"{t}  {v}\n")
    f.write("\n")


def write_bc(bc_path, name, times, discharge, tracer, ref_time=ref_time):
    """Write a complete Sewer_sourcesink .bc file (discharge + sewage tracer).

    Parameters
    ----------
    bc_path : path-like
        Output .bc file path.
    name : str
        [Forcing] block name; must match the [SourceSink] id in FlowFM_bnd.ext,
        e.g. "AlternateSewer_n500__01.00D".
    times, discharge, tracer : sequences
        Equal-length series: time (seconds since ref_time), sourcesink discharge
        (m3/s), and sewage tracer concentration (kg/m3).
    """
    with open(bc_path, "w") as f:
        f.write("[General]\n")
        f.write("fileVersion           = 1.01\n")
        f.write("fileType              = boundConds\n")
        f.write("\n")
        write_forcing(f, name, ref_time, "sourcesink_discharge", "m3/s", times, discharge)
        write_forcing(
            f, name, ref_time, "sourcesink_tracersewageDelta", "kg/m3", times, tracer
        )


def tim_to_bc(ws=None, n_junctions=n_junctions, source_id=source_id, ref_time=ref_time):
    """Regenerate Sewer_sourcesink_*.bc from every sewer_<tag>.tim in ``ws``.

    Each sewer_<coupling_tag>.tim holds the downstream outflow time series at a
    given MODFLOW coupling frequency. Columns: time(s)  discharge(m3/s)  tracer.
    """
    ws = pl.Path(".") if ws is None else pl.Path(ws)
    for file in sorted(ws.glob("sewer_*.tim")):
        # coupling tag, e.g. "01.00D" from "sewer_01.00D.tim"
        coupling_tag = file.stem[len("sewer_"):]
        print(f"processing...'{file}' (coupling tag {coupling_tag})")

        times, discharge, tracer = [], [], []
        with open(file, "r") as f:
            for line in f:
                t = line.split()
                if not t:
                    continue
                times.append(t[0])
                discharge.append(t[1])
                # col3 is the sewage tracer concentration (kg/m3); default if absent
                tracer.append(t[2] if len(t) > 2 else "1000.0")

        # The [Forcing] block "name" must match the [SourceSink] id in
        # FlowFM_bnd.ext (D-Flow FM matches the source by name), so it is just
        # source_id. The n-junctions label + coupling tag go in the FILENAME only.
        name = source_id
        bc_path = ws / f"Sewer_sourcesink_n{n_junctions:03d}__{coupling_tag}.bc"
        write_bc(bc_path, name, times, discharge, tracer, ref_time=ref_time)
        print(f"  wrote '{bc_path}'")


if __name__ == "__main__":
    tim_to_bc()
