import os
import pathlib as pl
import platform

import contextily as cx
import matplotlib as mpl

SCRIPT_PATH = pl.Path(__file__).resolve().parent
REPO_PATH = SCRIPT_PATH.parent
DFLOW_PATH = REPO_PATH / "dflow-fm"

DFLOW_RESOLUTION_DICT = {
    "gp": {
        "coarse": DFLOW_PATH / "coarse/tides_atm_surge",
        "medium": DFLOW_PATH / "midres/tides_atm_surge",
        "high": DFLOW_PATH / "highres/tides_atm_surge",
    },
    "pj": {
        "coarse": DFLOW_PATH / "coarse/tides_atm_surge_2018",
        "medium": DFLOW_PATH / "midres/tides_atm_surge_2018",
        "high": DFLOW_PATH / "highres/tides_atm_surge_2018",
    },
}


mpl.rcParams["animation.embed_limit"] = 2**128

_verbose = False

_platform = platform.system()
if _platform == "Linux":
    _ext = ".so"
elif _platform == "Darwin":
    _ext = ".dylib"
else:
    _ext = ".dll"

# The MODFLOW API library is not a conda package -- environment.yml pins flopy,
# modflowapi and xmipy, but the binary itself ships in the repo under
# modflow/mf6dll. Prefer a copy installed into the environment (e.g. by
# `get-modflow`) when one is actually there, and otherwise fall back to the repo
# copy that is versioned alongside the models.
#
# The repo path is anchored to THIS file rather than the cwd: notebooks live in
# several directories, and D-Flow FM's initialize() moves the working directory
# out from under any relative path.
_ENV_DLL_PATH = pl.Path(os.getenv("CONDA_PREFIX", ""))
_ENV_DLL_PATH = _ENV_DLL_PATH / ("Scripts" if _platform == "Windows" else "lib")
_REPO_DLL_PATH = REPO_PATH / "modflow" / "mf6dll"

libmf6 = (_ENV_DLL_PATH / f"libmf6{_ext}").resolve()
if not libmf6.is_file():
    libmf6 = (_REPO_DLL_PATH / f"libmf6{_ext}").resolve()
libmf6_source = "conda env" if libmf6.parent == _ENV_DLL_PATH.resolve() else "repo"

cx_provider = cx.providers.USGS.USTopo
mf6_model_crs = "EPSG:4456"

# Journal artwork specification (Environmental Modelling & Software, Elsevier).
# Figures are drawn at one of these widths and placed 1:1, never scaled in LaTeX --
# scaling shrinks the fonts with the figure, and "artwork where text is
# disproportionately small" is listed among the things not to submit.
FIG_FULL_IN = 190.0 / 25.4          # full page width,  190 mm
FIG_COL_IN = 90.0 / 25.4            # single column,     90 mm
# A full-width figure and its caption share a 7.52 in text block, so a figure much
# over 6.1 in tall pushes its caption off the page.
FIG_MAX_H_IN = 6.15

# PDF, not PNG. These are line drawings, and the specification puts bitmapped line
# drawings at a minimum of 1000 dpi -- the flopy styles set savefig.dpi to 300, so a
# raster export falls well short. Vector output removes the question. Figures
# carrying a basemap or a dense mesh are the exception: rasterize those artists with
# set_rasterized(True) and give the figure a dpi, so the heavy layer is a raster
# inside an otherwise vector file, rather than exporting the whole page as one.
fig_ext = ".pdf"
transparent = True

extentmax = (
    538104.4596371914,
    821308.8698173981,
    4388618.624104167,
    4601276.154973503,
)
extent = (
    716653.4849867643,
    725332.3893581643,
    4549340.078317634,
    4558903.549061629,
)
boxx = (
    716653.4849867643,
    716653.4849867643,
    725332.3893581643,
    725332.3893581643,
    716653.4849867643,
)
boxy = (
    4549340.078317634,
    4558903.549061629,
    4558903.549061629,
    4549340.078317634,
    4549340.078317634,
)


def set_title_string(date_time):
    s = str(date_time)[:13].replace("T", " ")
    return f"{s}:00:00"


def get_modflow_grid_name(domain="gp", boundary_condition="chd"):
    """ Get the modflow grid name
    """
    domain = domain.lower()
    boundary_condition = boundary_condition.lower()
    if domain not in ("gp", "pj"):
        assert False, "domain must be 'gp' or 'pj'"
    if boundary_condition not in ("chd", "ghb"):
        assert False, "boundary condition must be 'chd' or 'ghb'"
    return f"{domain}_{boundary_condition}"


def print_path():
    if _verbose:
        print(os.environ["PATH"])


def print_value(v):
    if _verbose:
        print(v)


def silent():
    return not _verbose


def verbosity():
    if _verbose:
        verbosity_level = 1
    else:
        verbosity_level = 0
    return verbosity_level


def get_dflow_control_path(domain="gp", resolution="coarse"):
    domain = domain.lower()
    resolution = resolution.lower()
    if domain not in ("gp", "pj"):
        assert False, "domain must be 'gp' or 'pj'"
    if resolution not in ("coarse", "medium", "high"):
        assert False, "resolution must be 'coarse', 'medium', or 'high'"
    return DFLOW_RESOLUTION_DICT[domain][resolution] / "FlowFM.mdu"


def _get_control_file_data(control_path):
    if control_path is None:
        control_path = pl.Path("../dflow-fm/coarse/tides/base/FlowFM.mdu")
    with open(control_path, "r") as f:
        lines = f.readlines()
    return lines


def _get_data(control_path, tag="NetFile"):
    value = None
    for line in _get_control_file_data(control_path):
        if line.startswith(tag):
            value = line.split(sep="=")[1].split(sep="#")[0].strip()
    return value


def get_dflow_grid_name(control_path=None):
    grid_file = _get_data(control_path)
    if grid_file is not None:
        grid_file = pl.Path(grid_file).stem
    return grid_file


def get_dflow_dtuser(control_path=None):
    dtuser = _get_data(control_path, tag="DtUser")
    if dtuser is not None:
        dtuser = float(dtuser)
    return dtuser


def get_sfincs_grid_name(control_path=None):
    grid_file = _get_data(control_path, tag="qtrfile")
    if grid_file is not None:
        grid_file = pl.Path(grid_file).stem
    return grid_file


def get_sfincs_dtuser(control_path=None):
    dtuser = _get_data(control_path, tag="dtmapout")
    if dtuser is not None:
        dtuser = float(dtuser)
    return dtuser


def get_modflow_coupling_tag(mf_couple_freq_hours):
    if mf_couple_freq_hours > 24.0:
        assert False, "coupling frequency must be 24 hours or less"
    elif mf_couple_freq_hours == 24.0:
        tag = f"{mf_couple_freq_hours / 24:05.2f}D"
    elif mf_couple_freq_hours >= 1.0:
        tag = f"{mf_couple_freq_hours:05.2f}H"
    else:
        tag = f"{mf_couple_freq_hours * 60.0:05.2f}M"
    return tag


# ---------------------------------------------------------------------------
# Scenario naming and layout
#
# A scenario is one (D-Flow FM discretization, MODFLOW<->D-Flow coupling
# frequency, number of SWMM<->MODFLOW connections) combination. step2 writes
# using these helpers and the step3 notebooks read using them, so the two can
# never drift apart. Every path is anchored to the repo rather than the cwd --
# D-Flow FM's initialize() moves the working directory, and the notebooks live
# in several different directories.
# ---------------------------------------------------------------------------


def get_scenario_name(
    domain="gp", resolution="coarse", mf_couple_freq_hours=8.0, n_connections=244
):
    """Scenario id, e.g. 'gp_coarse_08.00H_n244'.

    n_connections is the number of SWMM<->MODFLOW connections actually resolved
    by swmm_mf_connect.intersect_points_grid(), NOT the number requested.
    """
    tag = get_modflow_coupling_tag(mf_couple_freq_hours)
    return f"{domain}_{resolution}_{tag}_n{n_connections:03d}"


def get_results_path(
    domain="gp", resolution="coarse", mf_couple_freq_hours=8.0, n_connections=244
):
    """Scenario results directory written by step2 and read by step3."""
    scenario = get_scenario_name(domain, resolution, mf_couple_freq_hours, n_connections)
    return REPO_PATH / "results" / domain / scenario


def get_modflow_run_path(
    domain="gp",
    boundary_condition="chd",
    resolution="coarse",
    mf_couple_freq_hours=8.0,
    n_connections=244,
):
    """Scenario MODFLOW run directory (holds gwf.hds, gwf.cbc, the obs csvs)."""
    scenario = get_scenario_name(domain, resolution, mf_couple_freq_hours, n_connections)
    grid_name = get_modflow_grid_name(domain=domain, boundary_condition=boundary_condition)
    return REPO_PATH / "modflow" / grid_name / f"run_{scenario}"


def get_dflow_run_path(
    domain="gp", resolution="coarse", mf_couple_freq_hours=8.0, n_connections=244
):
    """Scenario D-Flow FM run directory (a sibling of the base scenario dir)."""
    scenario = get_scenario_name(domain, resolution, mf_couple_freq_hours, n_connections)
    base = get_dflow_control_path(domain, resolution).parent
    return base.parent / f"run_{scenario}"


def get_dflow_map_path(
    domain="gp", resolution="coarse", mf_couple_freq_hours=8.0, n_connections=244
):
    """Full D-Flow FM map file for a scenario.

    This is the untrimmed output and can be many GB. For the sewage tracer
    prefer results/<domain>/<scenario>/dflow_tracer.nc, which step2 writes with
    only mesh2d_sewage + mesh2d_waterdepth and the UGRID geometry.
    """
    run = get_dflow_run_path(domain, resolution, mf_couple_freq_hours, n_connections)
    return run / "output" / "FlowFM_map.nc"
