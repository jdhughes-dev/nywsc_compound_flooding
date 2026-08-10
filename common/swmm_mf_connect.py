import itertools

import flopy
import geopandas as gpd
import pyswmm
from liss_settings import get_modflow_grid_name


def intersect_points_grid(
    domain="gp",
    boundary_condition="chd",
    sim_ws=None,
    swmm_pth=None,
    pts_pth=None,
    pts_name_col="Name",
    n_junctions=1000,
    set_layers=True,
    crs="epsg:4456",
    seed=0,
    junction_names=None,
):
    """
    Intersects specified points with a grid polygon and retrieves information about junctions.

    This function reads point data from a specified shapefile, samples a given number of junctions,
    and intersects these junctions with a provided grid polygon. It then retrieves the corresponding
    SWMM node information, including invert elevations, and returns the number of junctions sampled,
    a dictionary of cell IDs, a dictionary of SWMM nodes, and a dictionary of invert elevations in feet.

    Parameters:
    ----------
    domain : str
        Model domain name. Greenport (gp) or Port Jefferson (PJ). Default is gp.
    boundary_condition: str
        MODFLOW boundary condition. Constant head (chd) or general head boundary (ghb). Default is chd.
    sim_ws : str
        The workspace directory containing the MODFLOW 6 simulation files. If None, the function will
        attempt to load from the current working directory.
    swmm_pth : str
        The file path to the SWMM input file (.inp). If None, a default path is used.
    pts_pth : str
        The file path to the shapefile containing point data. If None, a default path is used.
    n_junctions : int
        The desired number of junctions to sample from the point data. Default is 12.
    seed : int
        Random seed for the junction draw. Default is 0, the value that used to be
        hard-coded. Only matters when n_junctions is below the number available;
        drawing the whole set returns every junction regardless.
    junction_names : sequence of str, optional
        Use exactly these junctions instead of drawing. Takes precedence over
        n_junctions and seed, and is the reproducible way to restate a selection,
        since pandas does not guarantee .sample() is stable across versions.
    set_layers : bool
        Flag for setting junction layers based model layers and elevations, 
        otherwise just add to layer 1. Default is True.
    crs : str, optional
        The coordinate reference system (CRS) to assign to the GeoDataFrame. Default is "epsg:4456".

    Returns:
    -------
    tuple
        A tuple containing:
        - n_junctions (int): The number of junctions actually sampled.
        - junctions (list): List of selected junction names.
        - mf6_cells (dict): A dictionary mapping junction names to their corresponding cell IDs.
        - swmm_inverts (dict): A dictionary mapping junction names to their invert elevations in feet.
    """
    domain = domain.lower()
    boundary_condition = boundary_condition.lower()
    if domain not in ("gp", "pj"):
        assert False, "domain must be 'gp' or 'pj'"
    if boundary_condition not in ("chd", "ghb"):
        assert False, "boundary condition must be 'chd' or 'ghb'"

    mf_grid_name = get_modflow_grid_name(
        domain=domain,
        boundary_condition=boundary_condition,
    )

    if sim_ws is None:
        sim_ws = f"../modflow/{mf_grid_name}/base"
    if pts_pth is None:
        pts_pth = f"../swmm/{domain}/gis/{domain}_junctions.shp"
    if swmm_pth is None:
        swmm_pth = f"../swmm/{domain}/{domain}_sewer.inp"

    
    # load MODFLOW
    mf_sim = flopy.mf6.MFSimulation.load(sim_ws=sim_ws, load_only=[], verbosity_level=0)
    gwf = gwf = mf_sim.get_model("gwf")
    mg = gwf.modelgrid
    # made grid polygons and add DIS information
    grid_poly = mg.geo_dataframe.set_crs(crs)
    grid_poly["row"] = [x[0] for x in itertools.product(range(mg.nrow), range(mg.ncol))]
    grid_poly["col"]=  [x[1] for x in itertools.product(range(mg.nrow), range(mg.ncol))]
    grid_poly["idom"] = mg.idomain[0].flatten()
    grid_poly["top"] = mg.top.flatten()
    for i,arr in enumerate(mg.botm):
        grid_poly[f"bot{i+1:02d}"] = arr.flatten()

    # load the horizontal location info for junctions
    pts = gpd.read_file(pts_pth).to_crs(grid_poly.crs)
    # pull in the junctions listed in SWMM for vertical info
    m_to_ft = 3.28084
    with pyswmm.Simulation(str(swmm_pth)) as swmm_sim:
        # Key the inverts BY NAME. The previous version built a list by iterating
        # pyswmm.Nodes (SWMM's node order) and assigned it positionally to a frame
        # in shapefile order, so unless the two orders happened to agree every
        # invert landed on the wrong junction -- only 2 of 244 matched here. That
        # corrupted both the exchange driving head AND the model layer each
        # junction is placed in, since set_layers keys on invert_elev_ft.
        inverts_by_name = {
            n.nodeid: n.invert_elevation * m_to_ft for n in pyswmm.Nodes(swmm_sim)
        }
    # some shapefile junctions might not be in SWMM?
    swmm_junctions = list(inverts_by_name)
    possible_junctions = pts.loc[pts[pts_name_col].isin(swmm_junctions)].copy()
    possible_junctions["invert_elev_ft"] = possible_junctions[pts_name_col].map(
        inverts_by_name
    )
    assert possible_junctions["invert_elev_ft"].notna().all(), (
        "some shapefile junctions have no SWMM invert after the name join"
    )

    # select junctions randomly, or take all if n_junctions is large enough
    if junction_names is None and n_junctions > len(possible_junctions):
        print("# of junctions selected greater than # of point features")
        n_junctions = len(possible_junctions)
        print(f"new n_junctions == {n_junctions}")

    # seed defaults to 0, which is the value that was hard-coded here, so every
    # result produced before the argument existed reproduces unchanged. It only has
    # an effect below the full set: sampling all 244 of 244 returns every junction
    # whatever the seed, differing at most in row order.
    if junction_names is not None:
        # An explicit list beats re-deriving the draw. pandas does not promise that
        # .sample() is stable across versions, so random_state alone reproduces a
        # selection on this install and not necessarily on a co-author's in a year;
        # the names do.
        missing = sorted(set(junction_names) - set(possible_junctions[pts_name_col]))
        assert not missing, f"junctions not present in the shapefile/SWMM join: {missing}"
        selected_junctions = possible_junctions.set_index(
            pts_name_col, drop=False
        ).loc[list(junction_names)].reset_index(drop=True)
        n_junctions = len(selected_junctions)
        print(f"junction selection taken from an explicit list of {n_junctions}")
    else:
        selected_junctions = possible_junctions.sample(
            n_junctions, random_state=seed
        )
        print(f"junction selection: {n_junctions} of {len(possible_junctions)}, "
              f"seed {seed}")

    # join desired junctions with model grid
    mf6_swmm_connect = (
        selected_junctions[["Name", "invert_elev_ft", "geometry"]]
        .sjoin(grid_poly)
        .set_index("Name")
    )
    # place each SWMM junction in the right model layer
    if set_layers:
        mf6_swmm_connect["lay"] = 9999
        # if any of the layers are above the top, just place in layer 1
        mf6_swmm_connect.loc[
            mf6_swmm_connect["invert_elev_ft"]>mf6_swmm_connect["top"], "lay"
        ] = 0
        
        divs = ["top"] + [f"bot{i+1:02d}" for i in range(mg.nlay)]
        for i in range(len(divs)-1):
            ul = divs[i] # upper layer
            ll = divs[i+1] # lower layer
            condition = (
                (mf6_swmm_connect["invert_elev_ft"]<mf6_swmm_connect[ul]) &
                (mf6_swmm_connect["invert_elev_ft"]>mf6_swmm_connect[ll]) &
                (mf6_swmm_connect["idom"]>0)
            )
            mf6_swmm_connect.loc[condition, "lay"] = int(i)
        # error if any layers are not set within model domain
        missing = "\n".join(mf6_swmm_connect[mf6_swmm_connect['lay']==9999].index.tolist())
        err_msg = f"junctions outside model domain:\n{missing}"
        assert mf6_swmm_connect["lay"].max() != 9999, err_msg
    else:
        # set all junctions to layer 1
        mf6_swmm_connect["lay"] = int(0)
    
    # final bits for export
    mf6_swmm_connect["cid"] = list(
        zip(
            mf6_swmm_connect["lay"],
            mf6_swmm_connect["row"],
            mf6_swmm_connect["col"]
        )    
    )
    mf6_cells = mf6_swmm_connect["cid"].to_dict()
    swmm_inverts = mf6_swmm_connect["invert_elev_ft"].to_dict()

    return (
        n_junctions,
        selected_junctions["Name"].tolist(),
        mf6_cells,
        swmm_inverts,
        possible_junctions,
    )


if __name__ == "main":
    intersect_points_grid()
