import pathlib as pl
import platform
import os

import matplotlib as mpl
import contextily as cx

mpl.rcParams['animation.embed_limit'] = 2**128

_platform = platform.system() 
_DLL_PATH = pl.Path(os.getenv('CONDA_PREFIX'))
if _platform == "Windows":
    _DLL_PATH = _DLL_PATH / "Scripts"
else:
    _DLL_PATH = _DLL_PATH / "lib"
# _DLL_PATH = pl.Path("../modflow/mf6dll")
if _platform == "Linux":
    _ext = ".so"
elif _platform == "Darwin":
    _ext = ".dylib"
else:
    _ext = ".dll"
libmf6 = (_DLL_PATH / f"libmf6{_ext}").resolve()

cx_provider = cx.providers.USGS.USTopo
mf6_model_crs = "EPSG:4456"

fig_ext = ".png"
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
    
    mf_couple_freq_hours = 0.25    
    
    